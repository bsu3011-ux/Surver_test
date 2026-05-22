"""
Video Assembler for 어쩌다지식 YouTube Pipeline.

Uses moviepy + ffmpeg to assemble:
  - Intro clip (intro.mp4)
  - Per-scene: animated Ken Burns image clip + narration audio
  - BGM with per-scene volume automation (driven by Emotion Spine bgm_intensity)
  - 0.3s crossfade transitions between scene clips
  - SRT subtitles burned in via ffmpeg

Ken Burns effects are applied per-scene using the scene.ken_burns field from
the Emotion Spine metadata, generating smooth camera movements via FFmpeg zoompan.

BGM volume is modulated per scene based on scene.bgm_intensity (0.0–1.0),
building an FFmpeg volume keyframe expression that matches the narrative arc.

Output: 1920x1080, H.264, 30fps MP4
"""

from __future__ import annotations

import logging
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Video specs
# ---------------------------------------------------------------------------
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
BGM_VOLUME = 0.15          # Default flat BGM volume (used when no scenes provided)
CROSSFADE_DURATION = 0.3   # Seconds of crossfade between scene clips

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

# ---------------------------------------------------------------------------
# Ken Burns FFmpeg zoompan filter templates
#
# Placeholders:
#   {frames} — total frames for the clip (duration * VIDEO_FPS)
#   {w}      — output width  (VIDEO_WIDTH)
#   {h}      — output height (VIDEO_HEIGHT)
#
# 'on' is the FFmpeg zoompan output frame counter variable (1-based).
# ---------------------------------------------------------------------------
KEN_BURNS_FILTERS: dict[str, str] = {
    # Slow centre zoom-in from 1.0 to 1.15x
    "slow_zoom": (
        "zoompan=z='min(zoom+0.0008,1.15)':d={frames}"
        ":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}"
    ),
    # Fast centre zoom-in from 1.0 to 1.20x — for hook / surprising scenes
    "fast_zoom": (
        "zoompan=z='min(zoom+0.002,1.20)':d={frames}"
        ":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}"
    ),
    # Pan left (start right-of-centre, move to left) — warm farewell, reflection
    "pan_left": (
        "zoompan=z=1.08:d={frames}"
        ":x='(iw-iw/zoom)/2-((iw-iw/zoom)/2)*on/{frames}'"
        ":y='ih/2-(ih/zoom/2)':s={w}x{h}"
    ),
    # Pan right (start left-of-centre, move to right) — exploration, curiosity
    "pan_right": (
        "zoompan=z=1.08:d={frames}"
        ":x='iw/zoom/2+((iw-iw/zoom)/2)*on/{frames}'"
        ":y='ih/2-(ih/zoom/2)':s={w}x{h}"
    ),
    # No movement — CTA, stable information scenes
    "static": (
        "zoompan=z=1.0:d={frames}"
        ":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}"
    ),
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _get_scene_clip(self, scene, image_path: Path, audio_clip,
                        run_dir: Optional[Path] = None, scene_index: int = 0):
        """
        Get video clip for a scene.
        Priority: Wan2.1 pre-generated clip > Ken Burns from image.

        Args:
            scene: Scene object with ken_burns attribute.
            image_path: Source image file for Ken Burns fallback.
            audio_clip: moviepy AudioFileClip to set on the returned clip.
            run_dir: Optional run directory to search for pre-generated Wan2.1 clips.
            scene_index: Scene index used for clip filename lookup.

        Returns:
            moviepy VideoClip with audio attached, sized to VIDEO_WIDTH x VIDEO_HEIGHT.
        """
        # Check for pre-generated Wan2.1 clip
        if run_dir:
            wan_clip_path = run_dir / "video_clips" / f"scene_{scene_index:03d}.mp4"
            if wan_clip_path.exists():
                logger.info(f"    Scene {scene_index}: Using Wan2.1 clip")
                from moviepy.editor import VideoFileClip, concatenate_videoclips
                clip = VideoFileClip(str(wan_clip_path))
                # Loop if Wan2.1 clip is shorter than audio
                if clip.duration < audio_clip.duration:
                    loops = math.ceil(audio_clip.duration / clip.duration)
                    clip = concatenate_videoclips([clip] * loops)
                clip = clip.subclip(0, audio_clip.duration)
                clip = self._fit_to_resolution(clip, VIDEO_WIDTH, VIDEO_HEIGHT)
                return clip.set_audio(audio_clip)

        # Fall back to Ken Burns
        ken_burns = getattr(scene, "ken_burns", "slow_zoom")
        logger.info(f"    Scene {scene_index}: Ken Burns ({ken_burns})")
        tmp_dir = Path(tempfile.mkdtemp())
        kb_path = tmp_dir / f"kb_{scene_index:03d}.mp4"
        kb_path = self._apply_ken_burns(image_path, kb_path,
                                        ken_burns, audio_clip.duration)
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(str(kb_path))
        return clip.set_audio(audio_clip)

    def assemble(
        self,
        script_result,       # ScriptResult from script_generator
        audio_files: list[Path],
        image_files: list[Path],
        output_path: str | Path,
        include_intro: bool = True,
        run_dir: Optional[Path] = None,  # NEW: for Wan2.1 clip lookup
    ) -> AssemblyResult:
        """
        Assemble all components into a final MP4 video.

        Args:
            script_result: ScriptResult with scenes (including Emotion Spine metadata).
            audio_files: MP3 audio files, one per scene (same order as script_result.scenes).
            image_files: JPEG image files, one per scene.
            output_path: Where to save the final MP4.
            include_intro: Whether to prepend intro.mp4 if it exists.

        Returns:
            AssemblyResult with output path, duration, SRT path, etc.
        """
        from moviepy.editor import (
            AudioFileClip,
            VideoFileClip,
            concatenate_videoclips,
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
        # 1. Build scene clips with Wan2.1 (if available) or Ken Burns + audio
        # ------------------------------------------------------------------
        scene_clips = []
        srt_entries = []
        cumulative_time = 0.0
        scene_durations: list[float] = []
        wan_clip_count = 0
        ken_burns_count = 0

        with tempfile.TemporaryDirectory(prefix="ej_kb_") as tmp_dir:
            tmp_path = Path(tmp_dir)

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

                scene = scenes[i]

                # Determine if a pre-generated Wan2.1 clip exists for this scene
                wan_available = (
                    run_dir is not None
                    and (run_dir / "video_clips" / f"scene_{i:03d}.mp4").exists()
                )

                try:
                    video_clip = self._get_scene_clip(
                        scene=scene,
                        image_path=image_path,
                        audio_clip=audio_clip,
                        run_dir=run_dir,
                        scene_index=i,
                    )
                    if wan_available:
                        wan_clip_count += 1
                    else:
                        ken_burns_count += 1
                except Exception as e:
                    logger.warning(
                        f"_get_scene_clip failed for scene {i} (using static Ken Burns fallback): "
                        f"{type(e).__name__}: {e}"
                    )
                    # Fallback: static Ken Burns via FFmpeg
                    kb_clip_path = tmp_path / f"kb_{i:03d}_static.mp4"
                    self._apply_ken_burns(
                        image_path=image_path,
                        output_path=kb_clip_path,
                        ken_burns="static",
                        duration=duration,
                    )
                    video_clip = VideoFileClip(str(kb_clip_path))
                    audio_clip_fb = AudioFileClip(str(audio_path))
                    video_clip = video_clip.set_audio(audio_clip_fb)
                    ken_burns_count += 1

                # Ensure clip duration matches audio (zoompan / looping can be slightly off)
                if abs(video_clip.duration - duration) > 0.1:
                    video_clip = video_clip.set_duration(duration)

                scene_clips.append(video_clip)
                scene_durations.append(duration)

                # SRT subtitle entry
                narration = scene.narration.strip()
                srt_entries.append({
                    "start": cumulative_time,
                    "end": cumulative_time + duration,
                    "text": narration,
                })
                cumulative_time += duration

            logger.info(
                f"Scene clip sources: {wan_clip_count} Wan2.1 clip(s), "
                f"{ken_burns_count} Ken Burns clip(s)"
            )

            if not scene_clips:
                raise RuntimeError("No valid scene clips could be assembled")

            # ------------------------------------------------------------------
            # 2. Apply crossfade transitions between scene clips
            # ------------------------------------------------------------------
            if len(scene_clips) > 1:
                clips_with_transitions = [scene_clips[0]]
                for clip in scene_clips[1:]:
                    clip = clip.crossfadein(CROSSFADE_DURATION)
                    clips_with_transitions.append(clip)
                main_video = concatenate_videoclips(
                    clips_with_transitions,
                    padding=-CROSSFADE_DURATION,
                    method="compose",
                )
                logger.info(
                    f"Applied {CROSSFADE_DURATION}s crossfades between {len(scene_clips)} clips"
                )
            else:
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

                    main_video = concatenate_videoclips(
                        [intro_clip, main_video], method="compose"
                    )
                    intro_included = True
                    logger.info(f"Intro prepended: {intro_duration:.1f}s")
                except Exception as e:
                    logger.warning(f"Could not load intro.mp4: {e}. Skipping intro.")
            else:
                if include_intro:
                    logger.info("Intro file not found, skipping.")

            # ------------------------------------------------------------------
            # 4. Select and mix BGM with narrative arc volume automation
            # ------------------------------------------------------------------
            bgm_path = self._select_bgm(category)
            bgm_used = None
            if bgm_path:
                try:
                    main_video = self._add_bgm_with_automation(
                        video=main_video,
                        bgm_path=bgm_path,
                        scenes=scenes,
                        intro_duration=intro_duration,
                        scene_durations=scene_durations,
                    )
                    bgm_used = str(bgm_path)
                    logger.info(f"BGM added with volume automation: {bgm_path.name}")
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
            # 6. Write raw video (without subtitle overlay)
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
                logger=None,
            )
            main_video.close()
            for clip in scene_clips:
                try:
                    clip.close()
                except Exception:
                    pass

        # ------------------------------------------------------------------
        # 7. Burn subtitles via ffmpeg
        # ------------------------------------------------------------------
        logger.info("Burning subtitles into video...")
        self._burn_subtitles(temp_video_path, srt_path, output_path)

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

    # ------------------------------------------------------------------
    # Ken Burns effect
    # ------------------------------------------------------------------

    def _apply_ken_burns(
        self,
        image_path: Path,
        output_path: Path,
        ken_burns: str,
        duration: float,
    ) -> Path:
        """
        Convert a static image to an animated clip with a Ken Burns camera effect.

        Uses FFmpeg's zoompan filter. The output is a 1920x1080, 30fps H.264 MP4
        with no audio track (audio is added separately via moviepy).

        Args:
            image_path: Source JPEG/PNG image.
            output_path: Destination MP4 clip path.
            ken_burns: Effect type key from KEN_BURNS_FILTERS
                       (slow_zoom/fast_zoom/pan_left/pan_right/static).
            duration: Clip duration in seconds.

        Returns:
            Path to the generated animated clip.

        Raises:
            subprocess.CalledProcessError: If FFmpeg fails.
        """
        frames = int(duration * VIDEO_FPS)
        # Guard against zero-frame clips (very short audio)
        frames = max(frames, VIDEO_FPS)

        filter_template = KEN_BURNS_FILTERS.get(ken_burns, KEN_BURNS_FILTERS["slow_zoom"])
        vf_filter = filter_template.format(frames=frames, w=VIDEO_WIDTH, h=VIDEO_HEIGHT)

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-vf", vf_filter,
            "-t", str(duration),
            "-r", str(VIDEO_FPS),
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-an",          # No audio track in this clip
            str(output_path),
        ]

        logger.debug(
            f"Ken Burns [{ken_burns}] — {image_path.name} → {output_path.name} "
            f"({duration:.1f}s, {frames} frames)"
        )
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg Ken Burns failed (exit {result.returncode}): "
                f"{result.stderr[-300:]}"
            )
        return output_path

    # ------------------------------------------------------------------
    # BGM with narrative arc volume automation
    # ------------------------------------------------------------------

    def _build_bgm_volume_filter(
        self,
        scenes: list,
        intro_duration: float,
        scene_durations: list[float],
    ) -> str:
        """
        Build an FFmpeg volume filter expression with per-scene BGM intensity keyframes.

        The expression uses nested if(lt(t, ...)) calls so FFmpeg evaluates the
        correct volume for each point in time.  Volume is interpolated as a step
        function — each scene boundary triggers a volume change.

        Args:
            scenes: Scene objects with .bgm_intensity (0.0–1.0).
            intro_duration: Duration of the prepended intro clip in seconds.
            scene_durations: Actual duration of each scene clip in seconds
                             (same order as scenes).

        Returns:
            FFmpeg volume filter string, e.g.
            "volume='if(lt(t,5),0.5,if(lt(t,10),0.2,...,0.15))':eval=frame"
        """
        # Build (boundary_time, volume) pairs
        keyframes: list[tuple[float, float]] = []
        current_t = intro_duration  # scenes start after intro

        for i, scene in enumerate(scenes):
            intensity = getattr(scene, "bgm_intensity", BGM_VOLUME)
            # Clamp to [0.05, 1.0] — never completely silence or over-amplify BGM
            vol = max(0.05, min(1.0, float(intensity)))
            # Scale: bgm_intensity is already the desired fraction of the BGM track
            keyframes.append((current_t, vol))
            if i < len(scene_durations):
                current_t += scene_durations[i]

        if not keyframes:
            return f"volume={BGM_VOLUME}:eval=frame"

        # Build nested if() expression from last to first
        # Base case: use the last scene's volume after all keyframes
        default_vol = keyframes[-1][1]
        expr = str(round(default_vol, 4))

        # Wrap from inner-most to outer-most
        for boundary_t, vol in reversed(keyframes):
            expr = f"if(lt(t,{boundary_t:.3f}),{vol:.4f},{expr})"

        return f"volume='{expr}':eval=frame"

    def _add_bgm_with_automation(
        self,
        video,
        bgm_path: Path,
        scenes: list,
        intro_duration: float,
        scene_durations: list[float],
    ):
        """
        Add background music with per-scene volume automation driven by Emotion Spine.

        Falls back to flat BGM_VOLUME if volume filter construction fails.

        Args:
            video: moviepy VideoClip with narration audio already set.
            bgm_path: Path to the BGM audio file.
            scenes: Scene objects with .bgm_intensity fields.
            intro_duration: Duration of prepended intro in seconds.
            scene_durations: Actual duration of each scene clip in seconds.

        Returns:
            Updated VideoClip with BGM mixed in.
        """
        from moviepy.editor import AudioFileClip, CompositeAudioClip, concatenate_audioclips

        bgm = AudioFileClip(str(bgm_path))

        # Loop BGM if shorter than video
        video_duration = video.duration
        if bgm.duration < video_duration:
            n_loops = math.ceil(video_duration / bgm.duration)
            bgm = concatenate_audioclips([bgm] * n_loops)

        # Trim to video length
        bgm = bgm.subclip(0, video_duration)

        # Apply fade in/out
        bgm = bgm.audio_fadein(2.0).audio_fadeout(3.0)

        # Apply per-scene volume via moviepy's volumex with a callable
        # Build a lookup list: (start_time, end_time, volume) per scene
        volume_segments: list[tuple[float, float, float]] = []
        t = intro_duration
        for i, scene in enumerate(scenes):
            intensity = getattr(scene, "bgm_intensity", BGM_VOLUME)
            vol = max(0.05, min(1.0, float(intensity)))
            dur = scene_durations[i] if i < len(scene_durations) else 0.0
            volume_segments.append((t, t + dur, vol))
            t += dur

        def volume_at_time(t_sec: float) -> float:
            """Return BGM volume fraction at time t_sec."""
            for start, end, vol in volume_segments:
                if start <= t_sec < end:
                    return vol
            # Intro or post-content: use moderate volume
            return BGM_VOLUME

        try:
            bgm = bgm.fl(lambda gf, t: gf(t) * volume_at_time(t), keep_duration=True)
        except Exception as e:
            logger.warning(
                f"Per-scene BGM volume automation failed, using flat volume: {e}"
            )
            bgm = bgm.volumex(BGM_VOLUME)

        # Mix with narration audio
        if video.audio:
            mixed_audio = CompositeAudioClip([video.audio, bgm])
        else:
            mixed_audio = bgm

        return video.set_audio(mixed_audio)

    # ------------------------------------------------------------------
    # Helpers (mostly unchanged from original)
    # ------------------------------------------------------------------

    def _fit_to_resolution(self, clip, width: int, height: int):
        """Resize clip to target resolution, maintaining aspect ratio with black bars."""
        from moviepy.editor import ColorClip, CompositeVideoClip

        clip_ratio = clip.w / clip.h
        target_ratio = width / height

        if abs(clip_ratio - target_ratio) < 0.01:
            return clip.resize((width, height))
        elif clip_ratio > target_ratio:
            new_w = width
            new_h = int(width / clip_ratio)
            resized = clip.resize((new_w, new_h))
            bg = ColorClip((width, height), color=(0, 0, 0), duration=clip.duration)
            y_offset = (height - new_h) // 2
            return CompositeVideoClip([bg, resized.set_position(("center", y_offset))])
        else:
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
            lines = [
                " ".join(lines[: len(lines) // 2]),
                " ".join(lines[len(lines) // 2 :]),
            ]

        return "\n".join(lines)

    def _burn_subtitles(
        self, raw_video: Path, srt_path: Path, output_path: Path
    ) -> None:
        """Use ffmpeg to burn subtitles into video with Korean font styling."""
        subtitle_style = (
            f"FontSize={SUBTITLE_FONT_SIZE},"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BackColour=&H66000000,"
            f"Outline={int(SUBTITLE_STROKE_WIDTH)},"
            f"Shadow=0,"
            f"Bold=1,"
            f"MarginV={SUBTITLE_MARGIN_BOTTOM},"
            f"Alignment=2"
        )

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
    print(f"  Ken Burns effects: {list(KEN_BURNS_FILTERS.keys())}")
