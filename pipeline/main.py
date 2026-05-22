"""
Main orchestrator for 어쩌다지식 YouTube Automation Pipeline.

Pipeline stages:
  1. topic     — Select next topic from queue
  2. script    — Generate script with Claude claude-opus-4-7
  3. tts       — Synthesize narration audio (per scene)
  4. images    — Generate illustrations (per scene)
  5. thumbnail — Generate YouTube thumbnail (1280×720 JPEG)
  6. assemble  — Combine into video with BGM + subtitles
  7. review    — Upload to Drive + Telegram approval gate
  8. upload    — Publish to YouTube with thumbnail (on approval)

Usage:
  python pipeline/main.py                           # Full pipeline, auto topic
  python pipeline/main.py --topic-id topic_001      # Force specific topic
  python pipeline/main.py --skip-to tts             # Resume from TTS stage
  python pipeline/main.py --skip-to upload --run-id <id>  # Resume upload only
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure project root is in path when run as script
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from pipeline.topic_manager import TopicManager, Topic
from pipeline.script_generator import ScriptGenerator, ScriptResult
from pipeline.tts_generator import TTSGenerator
from pipeline.image_generator import ImageGenerator
from pipeline.video_assembler import VideoAssembler
from pipeline.review_gate import ReviewGate
from pipeline.youtube_uploader import YouTubeUploader

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "pipeline.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)

# Import after basicConfig to avoid circular import issues
import logging.handlers

logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Pipeline state management
# ---------------------------------------------------------------------------

STAGES = ["topic", "script", "tts", "images", "thumbnail", "assemble", "review", "upload"]
RUNS_DIR = PROJECT_ROOT / "data" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)


def load_run_state(run_id: str) -> dict:
    """Load pipeline run state from JSON file."""
    state_file = RUNS_DIR / f"{run_id}.json"
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return {}


def save_run_state(run_id: str, state: dict) -> None:
    """Persist pipeline run state to JSON file."""
    state["run_id"] = run_id
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    state_file = RUNS_DIR / f"{run_id}.json"
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    logger.debug(f"Run state saved: {state_file.name}")


def update_stage(run_id: str, stage: str, status: str, data: dict = None) -> None:
    """Update a specific stage's status in the run state."""
    state = load_run_state(run_id)
    state.setdefault("stages", {})[stage] = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **(data or {}),
    }
    if status == "completed":
        state["last_completed_stage"] = stage
    elif status == "failed":
        state["failed_stage"] = stage
    save_run_state(run_id, state)


# ---------------------------------------------------------------------------
# Stage functions
# ---------------------------------------------------------------------------

def stage_topic(run_id: str, state: dict, topic_id: Optional[str] = None) -> Topic:
    """Stage 1: Select topic from queue."""
    logger.info("=" * 60)
    logger.info("STAGE 1: TOPIC SELECTION")
    logger.info("=" * 60)

    tm = TopicManager(queue_file=PROJECT_ROOT / "data" / "topic_queue.json")
    topic = tm.get_next_topic(topic_id=topic_id)

    if not topic:
        raise RuntimeError("No available topics in queue. Add more topics first.")

    logger.info(f"Selected topic: [{topic.category}] {topic.title_idea}")

    state["topic"] = topic.to_dict()
    update_stage(run_id, "topic", "completed", {"topic_id": topic.id, "title": topic.title_idea})

    return topic


def stage_script(run_id: str, state: dict, topic: Topic) -> ScriptResult:
    """Stage 2: Generate script with Claude."""
    logger.info("=" * 60)
    logger.info("STAGE 2: SCRIPT GENERATION")
    logger.info("=" * 60)

    gen = ScriptGenerator()
    script = gen.generate_script(topic)

    logger.info(f"Script: '{script.title}' | {len(script.scenes)} scenes")
    for i, scene in enumerate(script.scenes):
        logger.info(f"  Scene {i}: ~{scene.duration_estimate:.0f}s | {scene.narration[:60]}...")

    state["script"] = script.to_dict()
    update_stage(run_id, "script", "completed", {
        "title": script.title,
        "scene_count": len(script.scenes),
        "estimated_duration_s": sum(s.duration_estimate for s in script.scenes),
    })

    return script


def stage_tts(run_id: str, state: dict, script: ScriptResult) -> list[Path]:
    """Stage 3: Generate TTS audio for all scenes."""
    logger.info("=" * 60)
    logger.info("STAGE 3: TEXT-TO-SPEECH")
    logger.info("=" * 60)

    run_audio_dir = PROJECT_ROOT / "data" / "runs" / run_id / "audio"
    run_audio_dir.mkdir(parents=True, exist_ok=True)

    tts = TTSGenerator()
    audio_files = []
    total_duration = 0.0

    for i, scene in enumerate(script.scenes):
        audio_path = run_audio_dir / f"scene_{i:03d}.mp3"

        if audio_path.exists():
            logger.info(f"  Scene {i}: Using cached audio ({audio_path.name})")
            audio_files.append(audio_path)
            continue

        logger.info(f"  Scene {i}/{len(script.scenes) - 1}: Synthesizing ({len(scene.narration)} chars)...")
        duration = tts.synthesize(scene.narration, audio_path)
        audio_files.append(audio_path)
        total_duration += duration
        logger.info(f"    -> {audio_path.name} ({duration:.1f}s)")

    logger.info(f"TTS complete: {len(audio_files)} files, ~{total_duration / 60:.1f} min total")

    state["audio_files"] = [str(p) for p in audio_files]
    update_stage(run_id, "tts", "completed", {
        "audio_dir": str(run_audio_dir),
        "file_count": len(audio_files),
        "total_duration_s": total_duration,
    })

    return audio_files


def stage_images(run_id: str, state: dict, script: ScriptResult) -> list[Path]:
    """Stage 4: Generate AI illustrations for all scenes."""
    logger.info("=" * 60)
    logger.info("STAGE 4: IMAGE GENERATION")
    logger.info("=" * 60)

    run_image_dir = PROJECT_ROOT / "data" / "runs" / run_id / "images"
    run_image_dir.mkdir(parents=True, exist_ok=True)

    gen = ImageGenerator()
    image_files = []

    for i, scene in enumerate(script.scenes):
        image_path = run_image_dir / f"scene_{i:03d}.jpg"

        if image_path.exists():
            logger.info(f"  Scene {i}: Using cached image ({image_path.name})")
            image_files.append(image_path)
            continue

        logger.info(f"  Scene {i}/{len(script.scenes) - 1}: Generating image...")
        logger.debug(f"    Prompt: {scene.image_prompt[:80]}...")

        path = gen.generate(
            prompt=scene.image_prompt,
            output_path=image_path,
            category=script.category,
        )
        image_files.append(path)
        logger.info(f"    -> {path.name}")

    logger.info(f"Image generation complete: {len(image_files)} images")

    state["image_files"] = [str(p) for p in image_files]
    update_stage(run_id, "images", "completed", {
        "image_dir": str(run_image_dir),
        "file_count": len(image_files),
    })

    return image_files


def stage_thumbnail(
    run_id: str,
    state: dict,
    script: ScriptResult,
    image_files: list[Path],
    image_gen=None,
) -> Path:
    """Stage 5: Generate YouTube thumbnail (1280×720 JPEG)."""
    logger.info("=" * 60)
    logger.info("STAGE 5: THUMBNAIL GENERATION")
    logger.info("=" * 60)

    from pipeline.thumbnail_generator import ThumbnailGenerator
    from pipeline.script_generator import ThumbnailMeta

    output_dir = PROJECT_ROOT / "data" / "runs" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    thumbnail_path = output_dir / f"thumbnail_{run_id}.jpg"

    if thumbnail_path.exists():
        logger.info(f"Using cached thumbnail: {thumbnail_path.name}")
    else:
        gen = ThumbnailGenerator(
            image_generator=image_gen,
            assets_dir=PROJECT_ROOT / "assets",
        )

        meta = script.thumbnail
        if not meta:
            # Fallback: create basic meta from script title + category
            category_badges = {"psychology": "심리학", "life": "잡학", "tech": "테크"}
            meta = ThumbnailMeta(
                template="shock",
                main_text=script.title[:12],
                sub_text="어쩌다지식",
                background_prompt=(
                    f"Korean person looking surprised, {script.category} concept, "
                    f"dramatic lighting, close-up face"
                ),
                keyword_badge=category_badges.get(script.category, "지식"),
            )
            logger.info(
                f"No thumbnail meta from script — using fallback (title={script.title[:12]})"
            )

        thumbnail_path = gen.generate(
            meta=meta,
            output_path=thumbnail_path,
            scene_images=image_files,
        )
        logger.info(f"Thumbnail generated: {thumbnail_path.name}")

    state["thumbnail_path"] = str(thumbnail_path)
    update_stage(run_id, "thumbnail", "completed", {"thumbnail_path": str(thumbnail_path)})

    return thumbnail_path


def stage_assemble(
    run_id: str,
    state: dict,
    script: ScriptResult,
    audio_files: list[Path],
    image_files: list[Path],
) -> Path:
    """Stage 6: Assemble video from scenes, audio, images, BGM, subtitles."""
    logger.info("=" * 60)
    logger.info("STAGE 6: VIDEO ASSEMBLY")
    logger.info("=" * 60)

    output_dir = PROJECT_ROOT / "data" / "runs" / run_id
    output_path = output_dir / f"output_{run_id}.mp4"

    assembler = VideoAssembler(assets_dir=PROJECT_ROOT / "assets")
    result = assembler.assemble(
        script_result=script,
        audio_files=audio_files,
        image_files=image_files,
        output_path=output_path,
    )

    file_size_mb = output_path.stat().st_size / 1024 / 1024
    logger.info(
        f"Assembly complete: {output_path.name} | "
        f"{result.duration_seconds:.1f}s | {file_size_mb:.1f} MB | "
        f"intro={'yes' if result.intro_included else 'no'}"
    )

    state["video_path"] = str(output_path)
    state["srt_path"] = str(result.srt_path) if result.srt_path else None
    update_stage(run_id, "assemble", "completed", {
        "video_path": str(output_path),
        "duration_s": result.duration_seconds,
        "file_size_mb": file_size_mb,
        "intro_included": result.intro_included,
        "bgm_used": result.bgm_used,
    })

    return output_path


def stage_review(
    run_id: str,
    state: dict,
    video_path: Path,
    script: ScriptResult,
    thumbnail_path: Optional[Path] = None,
) -> str:
    """Stage 7: Upload to Drive + Telegram approval gate. Returns decision."""
    logger.info("=" * 60)
    logger.info("STAGE 7: REVIEW GATE")
    logger.info("=" * 60)

    if thumbnail_path and thumbnail_path.exists():
        logger.info(f"Thumbnail available for review: {thumbnail_path.name}")
    else:
        logger.info("No thumbnail available for this review submission")

    gate = ReviewGate()
    record = gate.submit_for_review(
        video_id=run_id,
        video_path=video_path,
        script_result=script,
    )

    logger.info(f"Submitted for review. Drive URL: {record.drive_url}")
    logger.info("Waiting for Telegram approval (up to 24 hours)...")

    decision = gate.wait_for_approval(run_id)

    logger.info(f"Review decision: {decision}")
    update_stage(run_id, "review", "completed", {
        "drive_url": record.drive_url,
        "decision": decision,
        "telegram_message_id": record.telegram_message_id,
    })

    return decision


def stage_upload(
    run_id: str,
    state: dict,
    video_path: Path,
    script: ScriptResult,
    thumbnail_path: Optional[Path] = None,
) -> str:
    """Stage 8: Upload to YouTube (with thumbnail if available). Returns video URL."""
    logger.info("=" * 60)
    logger.info("STAGE 8: YOUTUBE UPLOAD")
    logger.info("=" * 60)

    uploader = YouTubeUploader()
    video_url = uploader.upload(video_path, script)

    # Set custom thumbnail immediately after upload if available
    if thumbnail_path and thumbnail_path.exists():
        # Extract video_id from the returned URL
        video_id = video_url.split("/")[-1] if video_url else ""
        if video_id:
            success = uploader.update_thumbnail(video_id, thumbnail_path)
            if success:
                logger.info(f"Thumbnail uploaded for video {video_id}: {thumbnail_path.name}")
            else:
                logger.warning(
                    f"Thumbnail upload failed for video {video_id} — "
                    f"set manually at https://studio.youtube.com"
                )
        else:
            logger.warning("Could not extract video ID from URL — skipping thumbnail upload")
    else:
        logger.info("No thumbnail provided — YouTube will auto-select a frame")

    logger.info(f"YouTube upload complete: {video_url}")
    update_stage(run_id, "upload", "completed", {"youtube_url": video_url})

    state["youtube_url"] = video_url

    # Mark topic as used only after successful upload
    topic_data = state.get("topic", {})
    if topic_data.get("id"):
        tm = TopicManager(queue_file=PROJECT_ROOT / "data" / "topic_queue.json")
        tm.mark_used(topic_data["id"])
        logger.info(f"Topic {topic_data['id']} marked as used")

    return video_url


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(
    topic_id: Optional[str] = None,
    skip_to: Optional[str] = None,
    run_id: Optional[str] = None,
) -> dict:
    """
    Run the full 어쩌다지식 video production pipeline.

    Args:
        topic_id: Force a specific topic by ID.
        skip_to: Resume from a specific stage (e.g., "tts", "assemble").
        run_id: Resume a specific run by ID (required when using skip_to).

    Returns:
        Final state dict with all stage results.
    """
    # Generate or reuse run ID
    if run_id:
        state = load_run_state(run_id)
        logger.info(f"Resuming run: {run_id}")
    else:
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        state = {}
        logger.info(f"Starting new run: {run_id}")

    save_run_state(run_id, state)

    # Determine which stages to run
    if skip_to and skip_to in STAGES:
        start_index = STAGES.index(skip_to)
    else:
        start_index = 0

    stages_to_run = STAGES[start_index:]
    logger.info(f"Stages to run: {', '.join(stages_to_run)}")

    # ---------------------
    # TOPIC
    # ---------------------
    topic: Optional[Topic] = None
    if "topic" in stages_to_run:
        try:
            topic = stage_topic(run_id, state, topic_id=topic_id)
        except Exception as e:
            update_stage(run_id, "topic", "failed", {"error": str(e)})
            logger.error(f"Topic stage failed: {e}", exc_info=True)
            raise
    else:
        # Reconstruct from saved state
        topic_data = state.get("topic")
        if topic_data:
            from pipeline.topic_manager import Topic
            topic = Topic.from_dict(topic_data)
            logger.info(f"Reusing topic from state: {topic.title_idea}")

    if not topic:
        raise RuntimeError("No topic available — check run state or queue")

    # ---------------------
    # SCRIPT
    # ---------------------
    script: Optional[ScriptResult] = None
    if "script" in stages_to_run:
        try:
            script = stage_script(run_id, state, topic)
        except Exception as e:
            update_stage(run_id, "script", "failed", {"error": str(e)})
            logger.error(f"Script stage failed: {e}", exc_info=True)
            raise
    else:
        script_data = state.get("script")
        if script_data:
            script = ScriptResult.from_dict(script_data)
            logger.info(f"Reusing script from state: {script.title}")

    if not script:
        raise RuntimeError("No script available — check run state")

    # ---------------------
    # TTS
    # ---------------------
    audio_files: list[Path] = []
    if "tts" in stages_to_run:
        try:
            audio_files = stage_tts(run_id, state, script)
        except Exception as e:
            update_stage(run_id, "tts", "failed", {"error": str(e)})
            logger.error(f"TTS stage failed: {e}", exc_info=True)
            raise
    else:
        audio_paths = state.get("audio_files", [])
        audio_files = [Path(p) for p in audio_paths]
        logger.info(f"Reusing {len(audio_files)} audio files from state")

    # ---------------------
    # IMAGES
    # ---------------------
    image_files: list[Path] = []
    image_gen_instance = None  # Reuse for thumbnail stage to share style + avoid re-init
    if "images" in stages_to_run:
        try:
            image_files = stage_images(run_id, state, script)
        except Exception as e:
            update_stage(run_id, "images", "failed", {"error": str(e)})
            logger.error(f"Image stage failed: {e}", exc_info=True)
            raise
    else:
        image_paths = state.get("image_files", [])
        image_files = [Path(p) for p in image_paths]
        logger.info(f"Reusing {len(image_files)} image files from state")

    # ---------------------
    # THUMBNAIL
    # ---------------------
    thumbnail_path: Optional[Path] = None
    if "thumbnail" in stages_to_run:
        try:
            # Attempt to reuse image_gen_instance if available; otherwise pass None
            # so ThumbnailGenerator creates its own or falls back to scene images
            thumbnail_path = stage_thumbnail(
                run_id, state, script, image_files, image_gen=image_gen_instance
            )
        except Exception as e:
            update_stage(run_id, "thumbnail", "failed", {"error": str(e)})
            logger.error(f"Thumbnail stage failed: {e}", exc_info=True)
            # Non-fatal: pipeline continues without a thumbnail
            logger.warning("Continuing pipeline without thumbnail")
            thumbnail_path = None
    else:
        tp = state.get("thumbnail_path")
        if tp:
            thumbnail_path = Path(tp)
            if thumbnail_path.exists():
                logger.info(f"Reusing thumbnail from state: {thumbnail_path.name}")
            else:
                logger.warning(f"Cached thumbnail path not found: {tp}")
                thumbnail_path = None

    # ---------------------
    # ASSEMBLE
    # ---------------------
    video_path: Optional[Path] = None
    if "assemble" in stages_to_run:
        try:
            video_path = stage_assemble(run_id, state, script, audio_files, image_files)
        except Exception as e:
            update_stage(run_id, "assemble", "failed", {"error": str(e)})
            logger.error(f"Assembly stage failed: {e}", exc_info=True)
            raise
    else:
        vp = state.get("video_path")
        if vp:
            video_path = Path(vp)
            logger.info(f"Reusing video from state: {video_path.name}")

    if not video_path or not video_path.exists():
        raise RuntimeError("No video file available — check run state or re-run assembly")

    # ---------------------
    # REVIEW
    # ---------------------
    decision = "approved"  # Default if review stage is skipped
    if "review" in stages_to_run:
        try:
            decision = stage_review(run_id, state, video_path, script, thumbnail_path)
        except Exception as e:
            update_stage(run_id, "review", "failed", {"error": str(e)})
            logger.error(f"Review stage failed: {e}", exc_info=True)
            raise

        if decision == "rejected":
            logger.warning(f"Video rejected by reviewer. Run ID: {run_id}")
            state["final_status"] = "rejected"
            save_run_state(run_id, state)
            print(f"\n❌ Video was rejected. Run ID: {run_id}")
            return state
        elif decision == "timeout":
            logger.warning("Review timed out. Use --skip-to upload to manually upload later.")
            state["final_status"] = "timeout"
            save_run_state(run_id, state)
            print(f"\n⚠️  Review timed out. To upload manually, run:")
            print(f"   python pipeline/main.py --skip-to upload --run-id {run_id}")
            return state

    # ---------------------
    # UPLOAD
    # ---------------------
    youtube_url = ""
    if "upload" in stages_to_run:
        try:
            youtube_url = stage_upload(run_id, state, video_path, script, thumbnail_path)
        except Exception as e:
            update_stage(run_id, "upload", "failed", {"error": str(e)})
            logger.error(f"Upload stage failed: {e}", exc_info=True)
            raise

    state["final_status"] = "completed"
    save_run_state(run_id, state)

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE!")
    logger.info(f"  Run ID:   {run_id}")
    logger.info(f"  Title:    {script.title}")
    logger.info(f"  YouTube:  {youtube_url}")
    logger.info("=" * 60)

    return state


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main():
    """Parse CLI arguments and run the pipeline."""
    parser = argparse.ArgumentParser(
        description="어쩌다지식 AI YouTube 자동화 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python pipeline/main.py                              # 전체 파이프라인 실행
  python pipeline/main.py --topic-id topic_001         # 특정 주제로 실행
  python pipeline/main.py --skip-to tts               # TTS 단계부터 재개
  python pipeline/main.py --skip-to upload --run-id run_20240101_120000_abc123
        """,
    )
    parser.add_argument(
        "--topic-id",
        type=str,
        default=None,
        help="강제로 사용할 주제 ID (예: topic_001)",
    )
    parser.add_argument(
        "--skip-to",
        type=str,
        choices=STAGES,
        default=None,
        help=f"이 단계부터 재개: {', '.join(STAGES)}",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="재개할 실행 ID (--skip-to 사용 시 필요)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 API 호출 없이 파이프라인 흐름만 확인",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="로그 레벨",
    )

    args = parser.parse_args()

    # Apply log level
    logging.getLogger().setLevel(args.log_level)

    if args.skip_to and not args.run_id:
        # Check if a recent run state exists
        logger.warning(
            "--skip-to requires --run-id to restore state. "
            "Starting from scratch with the specified stage."
        )

    if args.dry_run:
        logger.info("DRY RUN MODE — no API calls will be made")
        print("파이프라인 단계:")
        for i, stage in enumerate(STAGES, 1):
            print(f"  {i}. {stage}")
        return

    try:
        final_state = run_pipeline(
            topic_id=args.topic_id,
            skip_to=args.skip_to,
            run_id=args.run_id,
        )

        status = final_state.get("final_status", "unknown")
        youtube_url = final_state.get("youtube_url", "")

        if status == "completed":
            print(f"\n✅ 파이프라인 완료!")
            print(f"   YouTube URL: {youtube_url}")
        elif status == "rejected":
            print(f"\n❌ 영상이 반려되었습니다.")
        elif status == "timeout":
            print(f"\n⚠️  리뷰 타임아웃. 수동 업로드가 필요합니다.")
        else:
            print(f"\n상태: {status}")

    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        print("\n⚠️  파이프라인이 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        print(f"\n❌ 파이프라인 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
