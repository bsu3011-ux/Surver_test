"""
Video Assembler for 어쩌다지식 YouTube Pipeline.

Uses moviepy + ffmpeg to assemble:
  - Intro clip (intro.mp4)
  - Per-scene: image + narration audio
  - BGM at 15% volume
  - SRT subtitles overlay (clean white text, bottom center)

Output: 1920x1080, H.264, 30fps MP4
"""

from __future__ import annotations

import logging
import math
import os
import random
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Video specs
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
BGM_VOLUME = 0.15  # 15% of original BGM volume

# Subtitle styling
SUBTITLE_FONT_SIZE = 52
SUBTITLE_COLOR = "white"
SUBTITLE_STROKE_COLOR = "black"
SUBTITLE_STROKE_WIDTH = 2.5
SUBTITLE_MARGIN_BOTTOM = 80

# BGM mood → subdirectory mapping
BGM_MOOD_MAP = {
    "psychology": "calm",
    "life": "upbeat",
    "tech": "electronic",
}


@dataclass
class AssemblyResult:
    """Result of video assembly."""
    output_path: Path
    duration_seconds: float
    srt_path: Optional[Path]
    intro_included: bool
    bgm_used: Optional[str]


class VideoAssembler:
    """Assembles final video from scenes, audio, images, BGM, and subtitles."""

    def __init__(self, assets_dir: str | Path = "assets"):
        self.assets_dir = Path(assets_dir)
        self.intro_path = self.assets_dir / "intro.mp4"
        self.bgm_dir = self.assets_dir / "bgm"
        logger.info(f"VideoAssembler initialized. Assets dir: {self.assets_dir}")

    def assemble(
        self,
        script_result,  # ScriptResult from script_generator
        audio_files: list[Path],
        image_files: list[Path],
        output_path: str | Path,
        include_intro: bool = True,
    ) -> AssemblyResult:
        """
        Assemble all components into a final MP4 video.

        Args:
            script_result: ScriptResult with scenes and metadata.
            audio_files: MP3 audio files, one per scene (same order as script_result.scenes).
            image_files: JPEG image files, one per scene.
            output_path: Where to save the final MP4.
            include_intro: Whether to prepend intro.mp4 if it exists.

        Returns:
            AssemblyResult with output path, duration, SRT path, etc.
        """
        from moviepy.editor import (
            AudioFileClip,
            ImageClip,
            VideoFileClip,
            concatenate_videoclips,
            CompositeAudioClip,
            AudioClip,
        )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        scenes = script_result.scenes
        category = getattr(script_result, "category", "life")

        if len(audio_files) != len(image_files):
            raise ValueError(
                f"Mismatch: {len(audio_files)} audio files vs {len(image_files)} image files"
            )
        if len(audio_files) != len(scenes):
            logger.warning(
                f"Scene count mismatch: {len(scenes)} scenes, {len(audio_files)} audio files. "
                "Using min count."
            )

        n_scenes = min(len(scenes), len(audio_files), len(image_files))
        logger.info(f"Assembling video: {n_scenes} scenes, category={category}")

        # ------------------------------------------------------------------
        # 1. Build scene clips (image + narration audio)
        # ------------------------------------------------------------------
        scene_clips = []
        srt_entries = []
        cumulative_time = 0.0

        for i in range(n_scenes):
            audio_path = Path(audio_files[i])
            image_path = Path(image_files[i])

            if not audio_path.exists():
                logger.error(f"Audio file missing: {audio_path}")
                continue
            if not image_path.exists():
                logger.error(f"Image file missing: {image_path}")
                continue

            # Load audio to get exact duration
            audio_clip = AudioFileClip(str(audio_path))
            duration = audio_clip.duration

            # Create image clip matching audio duration
            img_clip = (
                ImageClip(str(image_path))
                .set_duration(duration)
                .set_audio(audio_clip)
                .set_fps(VIDEO_FPS)
            )

            # Resize to 1920x1080 (maintain aspect, crop/letterbox)
            img_clip = self._fit_to_resolution(img_clip, VIDEO_WIDTH, VIDEO_HEIGHT)
            scene_clips.append(img_clip)

            # Collect subtitle entry
            narration = scenes[i].narration.strip()
            srt_entries.append({
                "start": cumulative_time,
                "end": cumulative_time + duration,
                "text": narration,
            })
            cumulative_time += duration

        if not scene_clips:
            raise RuntimeError("No valid scene clips could be assembled")

        # ------------------------------------------------------------------
        # 2. Concatenate scene clips
        # ------------------------------------------------------------------
        main_video = concatenate_videoclips(scene_clips, method="compose")
        logger.info(f"Main content duration: {main_video.duration:.1f}s")

        # ------------------------------------------------------------------
        # 3. Prepend intro clip
        # ------------------------------------------------------------------
        intro_included = False
        intro_duration = 0.0
        if include_intro and self.intro_path.exists():
            try:
                intro_clip = VideoFileClip(str(self.intro_path))
                intro_clip = self._fit_to_resolution(intro_clip, VIDEO_WIDTH, VIDEO_HEIGHT)
                intro_clip = intro_clip.set_fps(VIDEO_FPS)
                intro_duration = intro_clip.duration

                # Shift subtitle timings by intro duration
                for entry in srt_entries:
                    entry["start"] += intro_duration
                    entry["end"] += intro_duration

                main_video = concatenate_videoclips([intro_clip, main_video], method="compose")
                intro_included = True
                logger.info(f"Intro prepended: {intro_duration:.1f}s")
            except Exception as e:
                logger.warning(f"Could not load intro.mp4: {e}. Skipping intro.")
        else:
            if include_intro:
                logger.info("Intro file not found, skipping.")

        # ------------------------------------------------------------------
        # 4. Select and mix BGM
        # ------------------------------------------------------------------
        bgm_path = self._select_bgm(category)
        bgm_used = None
        if bgm_path:
            try:
                main_video = self._add_bgm(main_video, bgm_path)
                bgm_used = str(bgm_path)
                logger.info(f"BGM added: {bgm_path.name}")
            except Exception as e:
                logger.warning(f"Failed to add BGM: {e}. Continuing without BGM.")
        else:
            logger.info("No BGM files found, skipping BGM.")

        # ------------------------------------------------------------------
        # 5. Generate SRT subtitle file
        # ------------------------------------------------------------------
        srt_path = output_path.with_suffix(".srt")
        self._write_srt(srt_entries, srt_path)
        logger.info(f"SRT file written: {srt_path.name}")

        # ------------------------------------------------------------------
        # 6. Write final video (without subtitle overlay — use ffmpeg burn-in)
        # ------------------------------------------------------------------
        temp_video_path = output_path.with_stem(output_path.stem + "_raw")
        logger.info(f"Writing raw video to {temp_video_path.name}...")

        main_video.write_videofile(
            str(temp_video_path),
            fps=VIDEO_FPS,
            codec="libx264",
            audio_codec="aac",
            audio_bitrate="192k",
            bitrate="8000k",
            preset="medium",
            threads=os.cpu_count() or 4,
            logger=None,  # Suppress moviepy progress bars
        )
        main_video.close()

        # ------------------------------------------------------------------
        # 7. Burn subtitles via ffmpeg (cleaner than moviepy text overlay)
        # ------------------------------------------------------------------
        logger.info("Burning subtitles into video...")
        self._burn_subtitles(temp_video_path, srt_path, output_path)

        # Clean up raw video
        if temp_video_path.exists():
            temp_video_path.unlink()

        total_duration = cumulative_time + intro_duration
        logger.info(
            f"Video assembly complete: {output_path.name} | "
            f"{total_duration:.1f}s | intro={intro_included}"
        )

        return AssemblyResult(
            output_path=output_path,
            duration_seconds=total_duration,
            srt_path=srt_path,
            intro_included=intro_included,
            bgm_used=bgm_used,
        )

    def _fit_to_resolution(self, clip, width: int, height: int):
        """Resize clip to target resolution, maintaining aspect ratio with black bars."""
        from moviepy.editor import ColorClip, CompositeVideoClip

        clip_ratio = clip.w / clip.h
        target_ratio = width / height

        if abs(clip_ratio - target_ratio) < 0.01:
            # Same ratio — just resize
            return clip.resize((width, height))
        elif clip_ratio > target_ratio:
            # Wider than target — fit width, add top/bottom bars
            new_w = width
            new_h = int(width / clip_ratio)
            resized = clip.resize((new_w, new_h))
            bg = ColorClip((width, height), color=(0, 0, 0), duration=clip.duration)
            y_offset = (height - new_h) // 2
            return CompositeVideoClip([bg, resized.set_position(("center", y_offset))])
        else:
            # Taller than target — fit height, add left/right bars
            new_h = height
            new_w = int(height * clip_ratio)
            resized = clip.resize((new_w, new_h))
            bg = ColorClip((width, height), color=(0, 0, 0), duration=clip.duration)
            x_offset = (width - new_w) // 2
            return CompositeVideoClip([bg, resized.set_position((x_offset, "center"))])

    def _select_bgm(self, category: str) -> Optional[Path]:
        """Select a random BGM file matching the topic category mood."""
        mood = BGM_MOOD_MAP.get(category, "upbeat")
        mood_dir = self.bgm_dir / mood

        if not mood_dir.exists():
            logger.warning(f"BGM mood directory not found: {mood_dir}")
            return None

        audio_files = list(mood_dir.glob("*.mp3")) + list(mood_dir.glob("*.wav"))
        if not audio_files:
            logger.warning(f"No audio files in BGM dir: {mood_dir}")
            return None

        selected = random.choice(audio_files)
        logger.debug(f"Selected BGM: {selected.name} (mood={mood})")
        return selected

    def _add_bgm(self, video, bgm_path: Path):
        """Add background music at BGM_VOLUME level, looped to video duration."""
        from moviepy.editor import AudioFileClip, CompositeAudioClip, afx

        bgm = AudioFileClip(str(bgm_path))

        # Loop BGM if shorter than video
        video_duration = video.duration
        if bgm.duration < video_duration:
            n_loops = math.ceil(video_duration / bgm.duration)
            from moviepy.editor import concatenate_audioclips
            bgm = concatenate_audioclips([bgm] * n_loops)

        # Trim to video length
        bgm = bgm.subclip(0, video_duration)

        # Apply fade in/out
        bgm = bgm.audio_fadein(2.0).audio_fadeout(3.0)

        # Lower volume
        bgm = bgm.volumex(BGM_VOLUME)

        # Mix with existing audio
        if video.audio:
            mixed_audio = CompositeAudioClip([video.audio, bgm])
        else:
            mixed_audio = bgm

        return video.set_audio(mixed_audio)

    def _write_srt(self, entries: list[dict], srt_path: Path) -> None:
        """Write SRT subtitle file from scene timing entries."""
        lines = []
        for i, entry in enumerate(entries, start=1):
            start_ts = self._seconds_to_srt_time(entry["start"])
            end_ts = self._seconds_to_srt_time(entry["end"])
            text = self._wrap_text(entry["text"], max_chars_per_line=40)
            lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n")

        srt_path.write_text("\n".join(lines), encoding="utf-8")

    def _seconds_to_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT timestamp format HH:MM:SS,mmm."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _wrap_text(self, text: str, max_chars_per_line: int = 40) -> str:
        """Wrap Korean text at word/character boundaries for subtitle display."""
        if len(text) <= max_chars_per_line:
            return text

        # Split on Korean punctuation or spaces
        words = text.split()
        lines = []
        current = ""
        for word in words:
            if len(current) + len(word) + 1 <= max_chars_per_line:
                current = (current + " " + word).strip()
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)

        # Max 2 lines in subtitle
        if len(lines) > 2:
            lines = [" ".join(lines[:len(lines)//2]), " ".join(lines[len(lines)//2:])]

        return "\n".join(lines)

    def _burn_subtitles(self, raw_video: Path, srt_path: Path, output_path: Path) -> None:
        """Use ffmpeg to burn subtitles into video with Korean font styling."""
        # FFmpeg subtitles filter with force_style for Korean appearance
        subtitle_style = (
            f"FontSize={SUBTITLE_FONT_SIZE},"
            f"PrimaryColour=&H00FFFFFF,"    # White text
            f"OutlineColour=&H00000000,"    # Black outline
            f"BackColour=&H66000000,"        # Semi-transparent background
            f"Outline={int(SUBTITLE_STROKE_WIDTH)},"
            f"Shadow=0,"
            f"Bold=1,"
            f"MarginV={SUBTITLE_MARGIN_BOTTOM},"
            f"Alignment=2"                  # Bottom center
        )

        # Escape the SRT path for ffmpeg filter
        srt_str = str(srt_path).replace("\\", "/").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(raw_video),
            "-vf", f"subtitles={srt_str}:force_style='{subtitle_style}'",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-b:v", "8000k",
            "-c:a", "copy",
            str(output_path),
        ]

        logger.debug(f"FFmpeg subtitle burn command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg subtitle burn failed: {result.stderr[-500:]}")
            # Fallback: just copy raw video without subtitles
            import shutil
            shutil.copy2(raw_video, output_path)
            logger.warning("Subtitle burn failed, using video without subtitles")
        else:
            logger.info("Subtitle burn successful")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    assembler = VideoAssembler()
    print("VideoAssembler ready.")
    print(f"  Intro path: {assembler.intro_path} (exists: {assembler.intro_path.exists()})")
    print(f"  BGM dir: {assembler.bgm_dir} (exists: {assembler.bgm_dir.exists()})")
