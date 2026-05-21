"""
TTS Generator for 어쩌다지식 YouTube Pipeline.

Uses Google Cloud Text-to-Speech (Neural2-C voice) to synthesize Korean narration.
Returns audio files in MP3 format along with duration in seconds.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from google.cloud import texttospeech
from google.api_core import exceptions as gcp_exceptions

logger = logging.getLogger(__name__)

# Default voice settings for 어쩌다지식
DEFAULT_VOICE_NAME = "ko-KR-Neural2-C"
DEFAULT_LANGUAGE_CODE = "ko-KR"
DEFAULT_SPEAKING_RATE = 1.05
DEFAULT_PITCH = 0.0
DEFAULT_VOLUME_GAIN_DB = 0.0


class TTSGenerator:
    """Synthesizes Korean narration using Google Cloud TTS Neural2-C voice."""

    MAX_RETRIES = 3
    RETRY_DELAY = 3  # seconds

    # Google TTS has a 5000 byte limit per request for Neural2 voices
    # We chunk at character level to stay safe
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
        """
        Initialize TTS generator.

        Args:
            voice_name: Google TTS voice name.
            language_code: BCP-47 language code.
            speaking_rate: Speaking rate multiplier (1.0 = normal).
            pitch: Pitch adjustment in semitones.
            volume_gain_db: Volume gain in dB.
            credentials_path: Path to service account JSON. If None, uses
                              GOOGLE_APPLICATION_CREDENTIALS env var.
        """
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        self.client = texttospeech.TextToSpeechClient()
        self.voice_name = voice_name
        self.language_code = language_code
        self.speaking_rate = speaking_rate
        self.pitch = pitch
        self.volume_gain_db = volume_gain_db

        # Voice selection params
        self._voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
        )

        # Audio config
        self._audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate,
            pitch=pitch,
            volume_gain_db=volume_gain_db,
            sample_rate_hertz=24000,
        )

        logger.info(
            f"TTSGenerator initialized: voice={voice_name}, "
            f"rate={speaking_rate}, pitch={pitch}"
        )

    def synthesize(self, text: str, output_path: str | Path) -> float:
        """
        Synthesize Korean text to MP3 audio file.

        Args:
            text: Korean narration text to synthesize.
            output_path: Path where the MP3 file will be saved.

        Returns:
            Duration of the synthesized audio in seconds.

        Raises:
            gcp_exceptions.GoogleAPIError: On unrecoverable API errors.
            IOError: On file write errors.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        text = text.strip()
        if not text:
            raise ValueError("Cannot synthesize empty text")

        logger.info(f"Synthesizing {len(text)} chars to {output_path.name}")

        # Split long text into chunks and concatenate audio
        chunks = self._split_text(text)
        logger.debug(f"Text split into {len(chunks)} chunk(s)")

        if len(chunks) == 1:
            audio_bytes = self._synthesize_chunk(chunks[0])
        else:
            audio_bytes = self._synthesize_and_concat(chunks)

        # Write audio file
        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        # Calculate duration from file size (MP3 at 24kHz, ~128kbps for Neural2)
        # More accurate: use mutagen or pydub if available
        duration = self._estimate_duration(audio_bytes, len(text))
        logger.info(f"Synthesized audio: {output_path.name} ({duration:.1f}s, {len(audio_bytes):,} bytes)")

        return duration

    def _synthesize_chunk(self, text: str) -> bytes:
        """Synthesize a single text chunk with retry logic."""
        last_error: Optional[Exception] = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                synthesis_input = texttospeech.SynthesisInput(text=text)
                response = self.client.synthesize_speech(
                    input=synthesis_input,
                    voice=self._voice,
                    audio_config=self._audio_config,
                )
                return response.audio_content
            except gcp_exceptions.ResourceExhausted as e:
                logger.warning(f"TTS quota exceeded (attempt {attempt}/{self.MAX_RETRIES}): {e}")
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt * 2)
            except gcp_exceptions.ServiceUnavailable as e:
                logger.warning(f"TTS service unavailable (attempt {attempt}/{self.MAX_RETRIES}): {e}")
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)
            except gcp_exceptions.InvalidArgument as e:
                logger.error(f"TTS invalid argument: {e}")
                raise
            except Exception as e:
                logger.warning(f"TTS error (attempt {attempt}/{self.MAX_RETRIES}): {type(e).__name__}: {e}")
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)

        raise RuntimeError(f"TTS synthesis failed after {self.MAX_RETRIES} attempts") from last_error

    def _synthesize_and_concat(self, chunks: list[str]) -> bytes:
        """Synthesize multiple chunks and concatenate MP3 audio bytes."""
        # For MP3 files, we can concatenate the raw bytes (works for most players)
        # For perfect results, use pydub AudioSegment if available
        all_audio = b""
        for i, chunk in enumerate(chunks):
            logger.debug(f"Synthesizing chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)")
            audio = self._synthesize_chunk(chunk)
            all_audio += audio
            # Small delay between requests to avoid quota issues
            if i < len(chunks) - 1:
                time.sleep(0.5)
        return all_audio

    def _split_text(self, text: str) -> list[str]:
        """Split text into chunks that fit within API limits."""
        if len(text) <= self.MAX_CHARS_PER_REQUEST:
            return [text]

        chunks = []
        # Split on sentence boundaries (Korean sentence endings)
        sentences = self._split_sentences(text)
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= self.MAX_CHARS_PER_REQUEST:
                current_chunk += sentence + " "
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + " "

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text[:self.MAX_CHARS_PER_REQUEST]]

    def _split_sentences(self, text: str) -> list[str]:
        """Split Korean text into sentences."""
        import re
        # Split on Korean sentence endings: .!? followed by space or end
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _estimate_duration(self, audio_bytes: bytes, text_length: int) -> float:
        """Estimate audio duration from byte size and speaking rate."""
        # MP3 at 24kHz Neural2 is approximately 16kbps per second of mono audio
        # But it varies — use characters as a rough guide:
        # Korean TTS at rate 1.05: ~4 chars/second
        chars_per_second = 4.0 * self.speaking_rate
        estimated = text_length / chars_per_second

        # Also try to estimate from file size (MP3 128kbps = 16000 bytes/sec)
        # This is more accurate
        bytes_per_second = 16000  # approximate for 128kbps
        if len(audio_bytes) > 1000:
            size_estimate = len(audio_bytes) / bytes_per_second
            # Average of both estimates
            return (estimated + size_estimate) / 2

        return estimated

    def get_voice_info(self) -> dict:
        """Return current voice configuration."""
        return {
            "voice_name": self.voice_name,
            "language_code": self.language_code,
            "speaking_rate": self.speaking_rate,
            "pitch": self.pitch,
            "volume_gain_db": self.volume_gain_db,
        }


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    tts = TTSGenerator()
    test_text = "안녕하세요! 어쩌다지식 채널에 오신 것을 환영합니다. 오늘은 정말 흥미로운 이야기를 들려드릴 텐데요, 끝까지 봐주시면 분명히 도움이 될 거예요."

    output = Path("/tmp/test_tts.mp3")
    duration = tts.synthesize(test_text, output)
    print(f"Duration: {duration:.1f}s | File: {output}")
