"""
TTS Generator for 어쩌다지식 YouTube Pipeline.

Primary: Naver ClovaVoice TTS — most natural Korean voice for 20-30대 audience.
Fallback: Google Cloud Text-to-Speech (Neural2-C voice).

Audio output: MP3 format with per-scene emotion-driven prosody adjustments.

Required environment variables:
  NAVER_CLIENT_ID        — Naver Cloud Platform API key ID (for ClovaVoice)
  NAVER_CLIENT_SECRET    — Naver Cloud Platform API key secret (for ClovaVoice)
  GOOGLE_APPLICATION_CREDENTIALS — GCP service account JSON path (for Google TTS fallback)
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Google TTS defaults (kept for fallback)
# ---------------------------------------------------------------------------
DEFAULT_VOICE_NAME = "ko-KR-Neural2-C"
DEFAULT_LANGUAGE_CODE = "ko-KR"
DEFAULT_SPEAKING_RATE = 1.05
DEFAULT_PITCH = 0.0
DEFAULT_VOLUME_GAIN_DB = 0.0


# ---------------------------------------------------------------------------
# ClovaVoice TTS — Primary provider
# ---------------------------------------------------------------------------

class ClovaVoiceTTS:
    """
    Naver ClovaVoice TTS — most natural Korean voice.

    API docs: https://api.ncloud-docs.com/docs/ai-naver-clovaspeech-tts
    Pricing: pay-per-character (free tier available)

    Best voices for 어쩌다지식 (20-30대 채널):
      "clara"    — young female, bright and friendly (DEFAULT)
      "nminsang" — young male, energetic
      "dara"     — adult female, warm and articulate
      "nara"     — standard female, clear and neutral
    """

    BASE_URL = "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts"

    DEFAULT_SPEAKER = "clara"  # young female, bright and friendly

    MAX_RETRIES = 3
    RETRY_DELAY = 3  # seconds

    # Emotion → speed/pitch adjustments
    # speed: -5 (slowest) to 5 (fastest); pitch: -5 (lowest) to 5 (highest)
    EMOTION_PARAMS: dict[str, dict[str, int]] = {
        "hook":       {"speed": -1, "pitch": 2},   # slightly slower + higher = dramatic opener
        "surprising": {"speed": -2, "pitch": 3},   # slow reveal with rising pitch
        "curious":    {"speed": 0,  "pitch": 1},   # neutral pace, slight upward lilt
        "calm":       {"speed": 1,  "pitch": 0},   # slightly faster, even tone for info delivery
        "building":   {"speed": -1, "pitch": 1},   # building tension: slower + slight rise
        "warm":       {"speed": 1,  "pitch": -1},  # warm farewell: relaxed pace, lower pitch
        "cta":        {"speed": 0,  "pitch": 0},   # clear and neutral for subscribe prompt
        "neutral":    {"speed": 0,  "pitch": 0},
    }

    def __init__(
        self,
        api_key_id: str = None,
        api_key: str = None,
        speaker: str = DEFAULT_SPEAKER,
    ):
        """
        Initialize ClovaVoice TTS.

        Args:
            api_key_id: Naver Cloud Platform Client ID.
                        Falls back to NAVER_CLIENT_ID env var.
            api_key: Naver Cloud Platform Client Secret.
                     Falls back to NAVER_CLIENT_SECRET env var.
            speaker: Voice speaker ID (e.g. "clara", "nminsang", "dara", "nara").
        """
        self.api_key_id = api_key_id or os.environ.get("NAVER_CLIENT_ID", "")
        self.api_key = api_key or os.environ.get("NAVER_CLIENT_SECRET", "")
        self.speaker = speaker

        if not self.api_key_id or not self.api_key:
            raise ValueError(
                "Naver ClovaVoice requires NAVER_CLIENT_ID and NAVER_CLIENT_SECRET env vars "
                "(or pass api_key_id / api_key to the constructor)."
            )

        logger.info(f"ClovaVoiceTTS initialized: speaker={speaker}")

    def synthesize(self, text: str, output_path: Path, emotion: str = "neutral") -> float:
        """
        Synthesize Korean text to MP3 with emotion-appropriate voice parameters.

        Args:
            text: Korean narration text.
            output_path: Destination MP3 file path.
            emotion: Emotion label from Emotion Spine
                     (hook / curious / surprising / calm / building / warm / cta / neutral).

        Returns:
            Estimated audio duration in seconds.

        Raises:
            RuntimeError: If synthesis fails after all retries.
        """
        import requests as _requests

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        text = text.strip()
        if not text:
            raise ValueError("Cannot synthesize empty text")

        params = self.EMOTION_PARAMS.get(emotion, self.EMOTION_PARAMS["neutral"])

        headers = {
            "X-NCP-APIGW-API-KEY-ID": self.api_key_id,
            "X-NCP-APIGW-API-KEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # ClovaVoice accepts form-encoded POST body
        data = {
            "speaker": self.speaker,
            "volume": "0",          # 0 = default volume
            "speed": str(params["speed"]),
            "pitch": str(params["pitch"]),
            "format": "mp3",
            "text": text,
        }

        last_error: Optional[Exception] = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = _requests.post(
                    self.BASE_URL,
                    headers=headers,
                    data=data,
                    timeout=60,
                )
                response.raise_for_status()

                # ClovaVoice returns MP3 bytes directly
                audio_bytes = response.content
                if len(audio_bytes) < 100:
                    raise RuntimeError(
                        f"ClovaVoice returned suspiciously small response "
                        f"({len(audio_bytes)} bytes): {response.text[:200]}"
                    )

                output_path.write_bytes(audio_bytes)
                duration = self._estimate_duration(output_path, text)
                logger.info(
                    f"[ClovaVoice] Synthesized: {output_path.name} "
                    f"({duration:.1f}s, {len(audio_bytes):,} bytes, "
                    f"emotion={emotion}, speed={params['speed']}, pitch={params['pitch']})"
                )
                return duration

            except _requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                logger.warning(
                    f"[ClovaVoice] HTTP {status} error "
                    f"(attempt {attempt}/{self.MAX_RETRIES}): {e}"
                )
                last_error = e
                # 429 = rate limit; 5xx = server error — both worth retrying
                if status == 429 or status >= 500:
                    if attempt < self.MAX_RETRIES:
                        time.sleep(self.RETRY_DELAY * attempt)
                else:
                    raise  # 4xx client errors are not retryable

            except _requests.exceptions.RequestException as e:
                logger.warning(
                    f"[ClovaVoice] Request error "
                    f"(attempt {attempt}/{self.MAX_RETRIES}): {type(e).__name__}: {e}"
                )
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)

        raise RuntimeError(
            f"ClovaVoice synthesis failed after {self.MAX_RETRIES} attempts"
        ) from last_error

    def _estimate_duration(self, output_path: Path, text: str) -> float:
        """
        Estimate audio duration from file size and character count.

        Korean TTS MP3 from ClovaVoice is typically ~128kbps.
        """
        try:
            file_size = output_path.stat().st_size
            # 128kbps = 16,000 bytes/second for MP3
            size_estimate = file_size / 16000
        except OSError:
            size_estimate = 0.0

        # Character-based estimate: Korean speech ~4 chars/sec at neutral speed
        char_estimate = len(text) / 4.0
        if size_estimate > 0:
            return (size_estimate + char_estimate) / 2
        return char_estimate


# ---------------------------------------------------------------------------
# Google Cloud TTS helpers (existing code, kept as fallback)
# ---------------------------------------------------------------------------

def _apply_ssml_hint(text: str, ssml_hint: str) -> str:
    """
    Wrap plain Korean text in SSML markup based on the tts_ssml_hint field.

    Returns an SSML string ready for Google TTS SynthesisInput(ssml=...).
    If the hint is empty or unrecognized, returns a plain SSML wrapper.
    """
    # Insert a short pause before numbers/statistics
    if ssml_hint == "pause_before_stat":
        # Insert 400ms break before digit sequences
        processed = re.sub(r"(\d)", r'<break time="400ms"/>\1', text, count=1)
        return f"<speak>{processed}</speak>"

    elif ssml_hint == "slow_emphasis":
        return f'<speak><prosody rate="slow">{text}</prosody></speak>'

    elif ssml_hint == "excited_pace":
        return f'<speak><prosody rate="fast">{text}</prosody></speak>'

    elif ssml_hint == "slow_whisper":
        return (
            f'<speak><prosody rate="slow" volume="soft">{text}</prosody></speak>'
        )

    elif ssml_hint == "emphasize_number":
        # Wrap digit sequences in strong emphasis
        processed = re.sub(
            r"(\d[\d,%.]*)",
            r'<emphasis level="strong">\1</emphasis>',
            text,
        )
        return f"<speak>{processed}</speak>"

    else:
        # No hint or unrecognized — plain SSML wrapper (still valid for Google TTS)
        return f"<speak>{text}</speak>"


class _GoogleTTS:
    """
    Internal Google Cloud TTS wrapper used by TTSGenerator as fallback.
    Preserves all original functionality from the previous version.
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 3
    MAX_CHARS_PER_REQUEST = 1000

    def __init__(
        self,
        voice_name: str = DEFAULT_VOICE_NAME,
        language_code: str = DEFAULT_LANGUAGE_CODE,
        speaking_rate: float = DEFAULT_SPEAKING_RATE,
        pitch: float = DEFAULT_PITCH,
        volume_gain_db: float = DEFAULT_VOLUME_GAIN_DB,
        credentials_path: Optional[str] = None,
    ):
        from google.cloud import texttospeech

        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        self.client = texttospeech.TextToSpeechClient()
        self.voice_name = voice_name
        self.language_code = language_code
        self.speaking_rate = speaking_rate
        self.pitch = pitch
        self.volume_gain_db = volume_gain_db

        self._voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
        )
        self._audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate,
            pitch=pitch,
            volume_gain_db=volume_gain_db,
            sample_rate_hertz=24000,
        )
        logger.info(
            f"[GoogleTTS] Initialized: voice={voice_name}, "
            f"rate={speaking_rate}, pitch={pitch}"
        )

    def synthesize(
        self,
        text: str,
        output_path: Path,
        ssml_hint: str = "",
    ) -> float:
        """Synthesize text (or SSML) to MP3, with optional SSML prosody hints."""
        from google.cloud import texttospeech

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        text = text.strip()
        if not text:
            raise ValueError("Cannot synthesize empty text")

        logger.info(f"[GoogleTTS] Synthesizing {len(text)} chars → {output_path.name}")

        # For SSML hints, use SSML input if the text fits in one request
        if ssml_hint and ssml_hint not in ("", "normal") and len(text) <= self.MAX_CHARS_PER_REQUEST:
            ssml_text = _apply_ssml_hint(text, ssml_hint)
            synthesis_input = texttospeech.SynthesisInput(ssml=ssml_text)
            audio_bytes = self._synthesize_input(synthesis_input)
        else:
            # Chunked plain-text synthesis for long texts
            chunks = self._split_text(text)
            if len(chunks) == 1:
                synthesis_input = texttospeech.SynthesisInput(text=chunks[0])
                audio_bytes = self._synthesize_input(synthesis_input)
            else:
                audio_bytes = self._synthesize_and_concat(chunks)

        output_path.write_bytes(audio_bytes)
        duration = self._estimate_duration(audio_bytes, len(text))
        logger.info(
            f"[GoogleTTS] Synthesized: {output_path.name} "
            f"({duration:.1f}s, {len(audio_bytes):,} bytes)"
        )
        return duration

    def _synthesize_input(self, synthesis_input) -> bytes:
        """Synthesize a single SynthesisInput with retry logic."""
        from google.api_core import exceptions as gcp_exceptions

        last_error: Optional[Exception] = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self.client.synthesize_speech(
                    input=synthesis_input,
                    voice=self._voice,
                    audio_config=self._audio_config,
                )
                return response.audio_content
            except gcp_exceptions.ResourceExhausted as e:
                logger.warning(
                    f"[GoogleTTS] Quota exceeded (attempt {attempt}/{self.MAX_RETRIES}): {e}"
                )
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt * 2)
            except gcp_exceptions.ServiceUnavailable as e:
                logger.warning(
                    f"[GoogleTTS] Service unavailable (attempt {attempt}/{self.MAX_RETRIES}): {e}"
                )
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)
            except gcp_exceptions.InvalidArgument as e:
                logger.error(f"[GoogleTTS] Invalid argument: {e}")
                raise
            except Exception as e:
                logger.warning(
                    f"[GoogleTTS] Error (attempt {attempt}/{self.MAX_RETRIES}): "
                    f"{type(e).__name__}: {e}"
                )
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)

        raise RuntimeError(
            f"Google TTS synthesis failed after {self.MAX_RETRIES} attempts"
        ) from last_error

    def _synthesize_and_concat(self, chunks: list[str]) -> bytes:
        from google.cloud import texttospeech

        all_audio = b""
        for i, chunk in enumerate(chunks):
            logger.debug(
                f"[GoogleTTS] Chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)"
            )
            synthesis_input = texttospeech.SynthesisInput(text=chunk)
            audio = self._synthesize_input(synthesis_input)
            all_audio += audio
            if i < len(chunks) - 1:
                time.sleep(0.5)
        return all_audio

    def _split_text(self, text: str) -> list[str]:
        if len(text) <= self.MAX_CHARS_PER_REQUEST:
            return [text]

        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks, current_chunk = [], ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= self.MAX_CHARS_PER_REQUEST:
                current_chunk = (current_chunk + " " + sentence).strip()
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        return chunks or [text[: self.MAX_CHARS_PER_REQUEST]]

    def _estimate_duration(self, audio_bytes: bytes, text_length: int) -> float:
        chars_per_second = 4.0 * self.speaking_rate
        estimated = text_length / chars_per_second
        bytes_per_second = 16000
        if len(audio_bytes) > 1000:
            size_estimate = len(audio_bytes) / bytes_per_second
            return (estimated + size_estimate) / 2
        return estimated

    def get_voice_info(self) -> dict:
        return {
            "voice_name": self.voice_name,
            "language_code": self.language_code,
            "speaking_rate": self.speaking_rate,
            "pitch": self.pitch,
            "volume_gain_db": self.volume_gain_db,
        }


# ---------------------------------------------------------------------------
# TTSGenerator — Public facade
# ---------------------------------------------------------------------------

class TTSGenerator:
    """
    TTS facade for 어쩌다지식 pipeline.

    Tries Naver ClovaVoice first (most natural Korean voice), falls back to
    Google Cloud TTS if ClovaVoice is unavailable or fails.

    Usage:
        tts = TTSGenerator()                      # auto mode: clova → google
        tts = TTSGenerator(provider="clova")      # force ClovaVoice
        tts = TTSGenerator(provider="google")     # force Google TTS

        duration = tts.synthesize(text, path, emotion="hook")
        duration = tts.synthesize_scene(scene, path)   # reads scene.emotion automatically
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 3

    def __init__(
        self,
        provider: str = "auto",
        # ClovaVoice options
        clova_speaker: str = ClovaVoiceTTS.DEFAULT_SPEAKER,
        naver_client_id: Optional[str] = None,
        naver_client_secret: Optional[str] = None,
        # Google TTS options (used as fallback or when provider="google")
        voice_name: str = DEFAULT_VOICE_NAME,
        language_code: str = DEFAULT_LANGUAGE_CODE,
        speaking_rate: float = DEFAULT_SPEAKING_RATE,
        pitch: float = DEFAULT_PITCH,
        volume_gain_db: float = DEFAULT_VOLUME_GAIN_DB,
        credentials_path: Optional[str] = None,
    ):
        """
        Initialize TTSGenerator.

        Args:
            provider: "clova" | "google" | "auto".
                      "auto" tries ClovaVoice first; if credentials are missing
                      or a call fails, it falls back to Google TTS.
            clova_speaker: ClovaVoice speaker ID (default: "clara").
            naver_client_id: Naver API key ID (env: NAVER_CLIENT_ID).
            naver_client_secret: Naver API secret (env: NAVER_CLIENT_SECRET).
            voice_name: Google TTS voice name.
            language_code: BCP-47 language code for Google TTS.
            speaking_rate: Google TTS speaking rate.
            pitch: Google TTS pitch in semitones.
            volume_gain_db: Google TTS volume gain.
            credentials_path: Path to GCP service account JSON.
        """
        if provider not in ("clova", "google", "auto"):
            raise ValueError(f"provider must be 'clova', 'google', or 'auto', got '{provider}'")

        self.provider = provider
        self._clova: Optional[ClovaVoiceTTS] = None
        self._google: Optional[_GoogleTTS] = None

        # Initialize ClovaVoice if needed
        if provider in ("clova", "auto"):
            try:
                self._clova = ClovaVoiceTTS(
                    api_key_id=naver_client_id,
                    api_key=naver_client_secret,
                    speaker=clova_speaker,
                )
            except ValueError as e:
                if provider == "clova":
                    raise
                logger.warning(
                    f"[TTSGenerator] ClovaVoice init failed (will use Google TTS): {e}"
                )
                self._clova = None

        # Initialize Google TTS if needed
        if provider in ("google", "auto"):
            try:
                self._google = _GoogleTTS(
                    voice_name=voice_name,
                    language_code=language_code,
                    speaking_rate=speaking_rate,
                    pitch=pitch,
                    volume_gain_db=volume_gain_db,
                    credentials_path=credentials_path,
                )
            except Exception as e:
                if provider == "google":
                    raise
                if self._clova is None:
                    raise RuntimeError(
                        "Both ClovaVoice and Google TTS initialization failed. "
                        "Check environment variables."
                    ) from e
                logger.warning(
                    f"[TTSGenerator] Google TTS init failed (ClovaVoice only mode): {e}"
                )
                self._google = None

        active = "ClovaVoice" if self._clova else "Google TTS"
        fallback = " + Google TTS fallback" if (self._clova and self._google) else ""
        logger.info(f"[TTSGenerator] Ready — primary: {active}{fallback}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        output_path: Path,
        emotion: str = "neutral",
        tts_ssml_hint: str = "",
    ) -> float:
        """
        Synthesize Korean text to MP3 with emotion-aware prosody.

        Tries ClovaVoice first (if available), falls back to Google TTS on error.

        Args:
            text: Korean narration text.
            output_path: Destination MP3 path.
            emotion: Emotion Spine label (hook/curious/surprising/calm/building/warm/cta/neutral).
            tts_ssml_hint: SSML prosody hint for Google TTS fallback
                           (e.g. "pause_before_stat", "slow_emphasis").

        Returns:
            Audio duration in seconds.
        """
        output_path = Path(output_path)

        # Try ClovaVoice
        if self._clova is not None:
            try:
                return self._clova.synthesize(text, output_path, emotion=emotion)
            except Exception as e:
                if self._google is None:
                    raise
                logger.warning(
                    f"[TTSGenerator] ClovaVoice failed, falling back to Google TTS: "
                    f"{type(e).__name__}: {e}"
                )

        # Google TTS fallback
        if self._google is not None:
            return self._google.synthesize(text, output_path, ssml_hint=tts_ssml_hint)

        raise RuntimeError("No TTS provider is available")

    def synthesize_scene(self, scene, output_path: Path) -> float:
        """
        Convenience method: synthesize a Scene object using its emotion and tts_ssml_hint fields.

        Args:
            scene: Scene dataclass from script_generator (must have .narration,
                   .emotion, and optionally .tts_ssml_hint attributes).
            output_path: Destination MP3 path.

        Returns:
            Audio duration in seconds.
        """
        emotion = getattr(scene, "emotion", "neutral")
        ssml_hint = getattr(scene, "tts_ssml_hint", "")
        logger.debug(
            f"synthesize_scene: scene {getattr(scene, 'index', '?')} "
            f"emotion={emotion} ssml_hint={ssml_hint!r}"
        )
        return self.synthesize(
            text=scene.narration,
            output_path=output_path,
            emotion=emotion,
            tts_ssml_hint=ssml_hint,
        )

    def get_voice_info(self) -> dict:
        """Return information about the active TTS configuration."""
        info = {"provider": self.provider}
        if self._clova:
            info["clova_speaker"] = self._clova.speaker
        if self._google:
            info.update(self._google.get_voice_info())
        return info


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    tts = TTSGenerator()
    test_text = (
        "안녕하세요! 어쩌다지식 채널에 오신 것을 환영합니다. "
        "오늘은 정말 흥미로운 이야기를 들려드릴 텐데요, "
        "끝까지 봐주시면 분명히 도움이 될 거예요."
    )

    output = Path("/tmp/test_tts.mp3")
    duration = tts.synthesize(test_text, output, emotion="hook")
    print(f"Duration: {duration:.1f}s | File: {output}")
    print(f"Voice info: {tts.get_voice_info()}")
