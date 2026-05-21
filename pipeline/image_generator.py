"""
Image Generator for 어쩌다지식 YouTube Pipeline.

Primary:  Flux.1 via fal.ai HTTP API — superior prompt adherence and visual consistency.
Fallback: Google Vertex AI Imagen 3 — existing provider, unchanged.

Style consistency: a per-video "Style Bible" prompt prefix is injected into every scene
image prompt so all illustrations share the same visual language.

Required environment variables:
  FAL_KEY               — fal.ai API key (for Flux.1)
  GOOGLE_CLOUD_PROJECT  — GCP project ID (for Imagen fallback)
  GOOGLE_APPLICATION_CREDENTIALS — GCP service account JSON path (for Imagen fallback)
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared style/quality constants (used by both providers)
# ---------------------------------------------------------------------------

# Style prefixes used by the legacy Imagen path (kept unchanged)
STYLE_PREFIXES = {
    "default": (
        "Digital illustration, clean modern Korean webtoon style, vibrant colors, "
        "16:9 aspect ratio, no text, no letters, no watermarks,"
    ),
    "psychology": (
        "Digital illustration, soft pastel tones, Korean webtoon style, warm and inviting, "
        "psychological concept visualization, 16:9 aspect ratio, no text, no letters,"
    ),
    "life": (
        "Digital illustration, bright cheerful colors, everyday Korean life scene, "
        "webtoon style, clean modern look, 16:9 aspect ratio, no text, no letters,"
    ),
    "tech": (
        "Digital illustration, futuristic tech aesthetic, neon accents, Korean webtoon style, "
        "sleek modern design, 16:9 aspect ratio, no text, no letters,"
    ),
}

NEGATIVE_PROMPT = (
    "text, watermark, signature, blurry, low quality, deformed, ugly, "
    "nsfw, violence, dark, depressing"
)


# ---------------------------------------------------------------------------
# FluxImageGenerator — Primary provider (fal.ai Flux.1)
# ---------------------------------------------------------------------------

class FluxImageGenerator:
    """
    Flux.1 image generation via fal.ai HTTP API.

    No fal-client SDK required — uses plain HTTP POST to the fal.run endpoint.
    Supports a per-session style reference prompt for visual consistency across scenes.

    Models:
      MODEL_DEV     — fal-ai/flux/dev     ($0.025/image, best quality, 28 steps)
      MODEL_SCHNELL — fal-ai/flux/schnell ($0.003/mp, fastest, 4 steps)
    """

    MODEL_DEV = "fal-ai/flux/dev"
    MODEL_SCHNELL = "fal-ai/flux/schnell"

    MAX_RETRIES = 3
    RETRY_DELAY = 10  # seconds — Flux.1 dev can take 15-30s

    # Composition hints appended to each prompt
    COMPOSITION_HINTS: dict[str, str] = {
        "wide":         "wide establishing shot, full scene visible",
        "closeup":      "close-up detail shot, focused subject",
        "abstract":     "abstract visualization, conceptual art style",
        "infographic":  "infographic style, data visualization",
        "split_screen": "split composition showing contrast or comparison",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = MODEL_DEV,
    ):
        """
        Initialize FluxImageGenerator.

        Args:
            api_key: fal.ai API key. Falls back to FAL_KEY env var.
            model: fal.ai model endpoint string (MODEL_DEV or MODEL_SCHNELL).
        """
        self.api_key = api_key or os.environ.get("FAL_KEY", "")
        if not self.api_key:
            raise ValueError(
                "fal.ai API key required. Set FAL_KEY env var or pass api_key to constructor."
            )
        self.model = model
        self._style_reference_prompt: str = ""
        logger.info(f"[FluxImageGenerator] Initialized: model={model}")

    def set_style_reference(self, style_description: str) -> None:
        """
        Set the consistent visual style injected at the start of every prompt.

        Call this once before generating all scene images to ensure visual consistency
        across the entire video. The style string is prepended to each image prompt.

        Args:
            style_description: E.g. the output of generate_style_reference().
        """
        self._style_reference_prompt = style_description.strip()
        logger.debug(
            f"[FluxImageGenerator] Style reference set: {self._style_reference_prompt[:80]}..."
        )

    def generate(
        self,
        prompt: str,
        output_path: Path,
        image_composition: str = "wide",
    ) -> Path:
        """
        Generate a scene image via fal.ai Flux.1 API.

        Args:
            prompt: English scene description (scene.image_prompt).
            output_path: Destination JPEG path.
            image_composition: Framing style from Emotion Spine
                               (wide/closeup/abstract/infographic/split_screen).

        Returns:
            Path to saved image file.

        Raises:
            RuntimeError: If generation fails after all retries.
        """
        import requests as _requests

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        comp_hint = self.COMPOSITION_HINTS.get(image_composition, "")
        parts = [p for p in [self._style_reference_prompt, comp_hint, prompt] if p]
        full_prompt = " ".join(parts)

        # Truncate if needed (Flux.1 handles ~1000 tokens but keep reasonable)
        if len(full_prompt) > 1400:
            full_prompt = full_prompt[:1400]
            logger.warning("[FluxImageGenerator] Prompt truncated to 1400 chars")

        headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": full_prompt,
            "image_size": "landscape_16_9",
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
            "num_images": 1,
            "enable_safety_checker": True,
        }

        logger.info(f"[FluxImageGenerator] Generating: {prompt[:80]}...")
        logger.debug(f"[FluxImageGenerator] Full prompt: {full_prompt[:120]}...")

        last_error: Optional[Exception] = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = _requests.post(
                    f"https://fal.run/{self.model}",
                    json=payload,
                    headers=headers,
                    timeout=120,
                )
                response.raise_for_status()
                result = response.json()

                images = result.get("images", [])
                if not images:
                    raise RuntimeError(
                        f"fal.ai returned no images. Response: {result}"
                    )

                image_url = images[0]["url"]
                img_response = _requests.get(image_url, timeout=60)
                img_response.raise_for_status()

                output_path.write_bytes(img_response.content)
                logger.info(
                    f"[FluxImageGenerator] Saved: {output_path.name} "
                    f"({len(img_response.content):,} bytes, composition={image_composition})"
                )
                return output_path

            except _requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                logger.warning(
                    f"[FluxImageGenerator] HTTP {status} error "
                    f"(attempt {attempt}/{self.MAX_RETRIES}): {e}"
                )
                last_error = e
                if status == 429 or status >= 500:
                    if attempt < self.MAX_RETRIES:
                        wait = self.RETRY_DELAY * attempt
                        logger.info(f"[FluxImageGenerator] Waiting {wait}s before retry...")
                        time.sleep(wait)
                else:
                    raise  # 4xx client errors (bad prompt, auth) — don't retry

            except _requests.exceptions.RequestException as e:
                logger.warning(
                    f"[FluxImageGenerator] Request error "
                    f"(attempt {attempt}/{self.MAX_RETRIES}): {type(e).__name__}: {e}"
                )
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)

            except RuntimeError as e:
                logger.warning(
                    f"[FluxImageGenerator] Runtime error "
                    f"(attempt {attempt}/{self.MAX_RETRIES}): {e}"
                )
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)

        raise RuntimeError(
            f"Flux.1 image generation failed after {self.MAX_RETRIES} attempts"
        ) from last_error


# ---------------------------------------------------------------------------
# Style Bible — per-category visual identity strings for Flux.1
# ---------------------------------------------------------------------------

def generate_style_reference(
    category: str,
    channel_name: str = "어쩌다지식",
) -> str:
    """
    Return the consistent style description used as a prefix for all scene images.

    This string is injected at the front of every image prompt to ensure all
    illustrations in the video share the same visual language.

    Args:
        category: Topic category key ("psychology", "life", "tech").
        channel_name: Channel name (for documentation; not included in prompt).

    Returns:
        Style prompt string to pass to FluxImageGenerator.set_style_reference().
    """
    style_by_category: dict[str, str] = {
        "psychology": (
            "Korean webtoon illustration style, soft pastel palette (lavender, mint, peach), "
            "clean bold outlines, minimalist backgrounds, warm and approachable mood, "
            "no text or letters, 16:9 composition,"
        ),
        "life": (
            "Korean webtoon illustration style, bright cheerful colors (sky blue, warm yellow, coral), "
            "clean modern aesthetic, everyday Korean life setting, friendly and relatable mood, "
            "no text or letters, 16:9 composition,"
        ),
        "tech": (
            "Korean webtoon illustration style, cool blue and purple tones with neon accents, "
            "futuristic clean design, digital and technological mood, sleek modern aesthetic, "
            "no text or letters, 16:9 composition,"
        ),
    }
    style = style_by_category.get(category, style_by_category["life"])
    logger.debug(
        f"[StyleBible] Style reference for category='{category}': {style[:80]}..."
    )
    return style


# ---------------------------------------------------------------------------
# Legacy Google Imagen wrapper (unchanged, used as fallback)
# ---------------------------------------------------------------------------

class _ImagenGenerator:
    """
    Internal Google Vertex AI Imagen 3 wrapper.
    Preserves all original functionality from the previous ImageGenerator class.
    Used as fallback when Flux.1 fails or FAL_KEY is not set.
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 10

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: str = "us-central1",
        model_name: str = "imagen-3.0-generate-001",
        credentials_path: Optional[str] = None,
    ):
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise ValueError(
                "GCP project ID required. Set GOOGLE_CLOUD_PROJECT env var or pass project_id."
            )

        self.location = location
        self.model_name = model_name
        self._model = None  # Lazy initialization

        logger.info(
            f"[ImagenGenerator] Initialized: project={self.project_id}, "
            f"model={model_name}, location={location}"
        )

    def _get_model(self):
        if self._model is None:
            import vertexai
            from vertexai.preview.vision_models import ImageGenerationModel

            vertexai.init(project=self.project_id, location=self.location)
            self._model = ImageGenerationModel.from_pretrained(self.model_name)
            logger.debug(f"[ImagenGenerator] Model loaded: {self.model_name}")
        return self._model

    def generate(
        self,
        prompt: str,
        output_path: Path,
        style: str = "default",
        category: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if category and category in STYLE_PREFIXES:
            style_key = category
        elif style in STYLE_PREFIXES:
            style_key = style
        else:
            style_key = "default"

        style_prefix = STYLE_PREFIXES[style_key]
        full_prompt = f"{style_prefix} {prompt}"

        if len(full_prompt) > 1400:
            full_prompt = full_prompt[:1400]
            logger.warning("[ImagenGenerator] Prompt truncated to 1400 chars")

        logger.info(f"[ImagenGenerator] Generating: {prompt[:80]}...")

        last_error: Optional[Exception] = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = self._call_imagen(full_prompt, seed=seed)
                result.save(str(output_path))
                logger.info(f"[ImagenGenerator] Saved: {output_path.name}")
                return output_path

            except Exception as e:
                error_str = str(e).lower()
                logger.warning(
                    f"[ImagenGenerator] Attempt {attempt}/{self.MAX_RETRIES} failed: "
                    f"{type(e).__name__}: {e}"
                )
                last_error = e

                if "safety" in error_str or "block" in error_str or "policy" in error_str:
                    logger.warning("[ImagenGenerator] Prompt blocked by safety filter. Sanitizing...")
                    prompt = self._sanitize_prompt(prompt)
                    full_prompt = f"{style_prefix} {prompt}"
                    if attempt >= self.MAX_RETRIES:
                        break
                elif "quota" in error_str or "rate" in error_str:
                    if attempt < self.MAX_RETRIES:
                        wait = self.RETRY_DELAY * attempt * 2
                        logger.info(f"[ImagenGenerator] Rate limited, waiting {wait}s...")
                        time.sleep(wait)
                elif attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)

        logger.error("[ImagenGenerator] All attempts failed. Creating placeholder image.")
        return self._create_placeholder(output_path, prompt, style_key)

    def _call_imagen(self, prompt: str, seed: Optional[int] = None) -> object:
        model = self._get_model()
        generate_kwargs = {
            "prompt": prompt,
            "number_of_images": 1,
            "aspect_ratio": "16:9",
            "negative_prompt": NEGATIVE_PROMPT,
            "safety_filter_level": "block_some",
            "person_generation": "allow_adult",
        }
        if seed is not None:
            generate_kwargs["seed"] = seed
        images = model.generate_images(**generate_kwargs)
        if not images or len(images.images) == 0:
            raise RuntimeError("Imagen returned no images")
        return images.images[0]

    def _sanitize_prompt(self, prompt: str) -> str:
        remove_words = ["violence", "gore", "blood", "weapon", "nude", "nsfw", "death"]
        sanitized = prompt
        for word in remove_words:
            sanitized = sanitized.replace(word, "")
        return sanitized.strip() or "Abstract colorful digital illustration, knowledge concept"

    def _create_placeholder(self, output_path: Path, prompt: str, style: str) -> Path:
        try:
            from PIL import Image, ImageDraw, ImageFont

            width, height = 1920, 1080
            style_colors = {
                "psychology": (147, 112, 219),
                "life": (255, 165, 0),
                "tech": (0, 191, 255),
                "default": (100, 149, 237),
            }
            bg_color = style_colors.get(style, style_colors["default"])

            img = Image.new("RGB", (width, height), bg_color)
            draw = ImageDraw.Draw(img)

            for y in range(height):
                r = min(255, bg_color[0] + int(40 * y / height))
                g = min(255, bg_color[1] + int(20 * y / height))
                b = min(255, bg_color[2] + int(30 * y / height))
                draw.line([(0, y), (width, y)], fill=(r, g, b))

            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60
                )
                small_font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36
                )
            except OSError:
                font = ImageFont.load_default()
                small_font = font

            anchor = "mm" if hasattr(ImageFont, "truetype") else None
            draw.text(
                (width // 2, height // 2 - 40), "어쩌다지식",
                font=font, fill="white", anchor=anchor,
            )
            draw.text(
                (width // 2, height // 2 + 40), prompt[:60],
                font=small_font, fill=(220, 220, 220), anchor=anchor,
            )

            img.save(str(output_path), "JPEG", quality=95)
            logger.info(f"[ImagenGenerator] Placeholder created: {output_path.name}")
            return output_path

        except ImportError:
            logger.error("[ImagenGenerator] Pillow not installed, cannot create placeholder")
            raise RuntimeError(
                "Imagen failed and Pillow not available for fallback"
            ) from None


# ---------------------------------------------------------------------------
# ImageGenerator — Public facade
# ---------------------------------------------------------------------------

class ImageGenerator:
    """
    Facade: tries Flux.1 (fal.ai) first, falls back to Google Imagen 3.

    Usage:
        gen = ImageGenerator()                   # auto mode: flux → imagen
        gen = ImageGenerator(provider="flux")    # force Flux.1
        gen = ImageGenerator(provider="imagen")  # force Imagen

        # For visual consistency across all scene images, call setup_style() first:
        gen.setup_style("psychology")

        # Single image:
        path = gen.generate(prompt, output_path, image_composition="wide")

        # All scenes at once (calls setup_style internally):
        paths = gen.generate_batch(scenes, output_dir, category="psychology")
    """

    def __init__(
        self,
        provider: str = "auto",
        # Flux.1 options
        fal_api_key: Optional[str] = None,
        flux_model: str = FluxImageGenerator.MODEL_DEV,
        # Imagen options
        project_id: Optional[str] = None,
        location: str = "us-central1",
        model_name: str = "imagen-3.0-generate-001",
        credentials_path: Optional[str] = None,
    ):
        """
        Initialize ImageGenerator.

        Args:
            provider: "flux" | "imagen" | "auto".
                      "auto" tries Flux.1 first; if FAL_KEY is missing or a call fails,
                      it falls back to Google Imagen.
            fal_api_key: fal.ai API key (env: FAL_KEY).
            flux_model: Flux.1 model endpoint (MODEL_DEV or MODEL_SCHNELL).
            project_id: GCP project ID for Imagen (env: GOOGLE_CLOUD_PROJECT).
            location: Vertex AI region for Imagen.
            model_name: Imagen model name.
            credentials_path: GCP service account JSON path.
        """
        if provider not in ("flux", "imagen", "auto"):
            raise ValueError(
                f"provider must be 'flux', 'imagen', or 'auto', got '{provider}'"
            )

        self.provider = provider
        self._flux: Optional[FluxImageGenerator] = None
        self._imagen: Optional[_ImagenGenerator] = None
        self._current_style: str = ""

        # Initialize Flux.1 if needed
        if provider in ("flux", "auto"):
            try:
                self._flux = FluxImageGenerator(
                    api_key=fal_api_key,
                    model=flux_model,
                )
            except ValueError as e:
                if provider == "flux":
                    raise
                logger.warning(
                    f"[ImageGenerator] Flux.1 init failed (will use Imagen): {e}"
                )
                self._flux = None

        # Initialize Imagen if needed
        if provider in ("imagen", "auto"):
            try:
                self._imagen = _ImagenGenerator(
                    project_id=project_id,
                    location=location,
                    model_name=model_name,
                    credentials_path=credentials_path,
                )
            except Exception as e:
                if provider == "imagen":
                    raise
                if self._flux is None:
                    raise RuntimeError(
                        "Both Flux.1 and Imagen initialization failed. "
                        "Check FAL_KEY and GOOGLE_CLOUD_PROJECT env vars."
                    ) from e
                logger.warning(
                    f"[ImageGenerator] Imagen init failed (Flux.1 only mode): {e}"
                )
                self._imagen = None

        active = "Flux.1" if self._flux else "Imagen"
        fallback = " + Imagen fallback" if (self._flux and self._imagen) else ""
        logger.info(f"[ImageGenerator] Ready — primary: {active}{fallback}")

    # ------------------------------------------------------------------
    # Style Bible
    # ------------------------------------------------------------------

    def setup_style(self, category: str) -> str:
        """
        Set the consistent visual style for all images in this video session.

        Call once before generate_batch() or before any generate() calls that
        should share the same visual language.

        Args:
            category: Topic category ("psychology", "life", "tech").

        Returns:
            The style prompt string that was set (for logging/debugging).
        """
        style = generate_style_reference(category)
        self._current_style = style
        if self._flux:
            self._flux.set_style_reference(style)
        logger.info(
            f"[ImageGenerator] Style set for category='{category}': {style[:80]}..."
        )
        return style

    # ------------------------------------------------------------------
    # Public generate methods
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        output_path: Path,
        image_composition: str = "wide",
        category: Optional[str] = None,
        style: str = "default",
        seed: Optional[int] = None,
    ) -> Path:
        """
        Generate a scene image with style consistency and automatic provider fallback.

        Args:
            prompt: English scene description.
            output_path: Destination JPEG path.
            image_composition: Framing style from Emotion Spine
                               (wide/closeup/abstract/infographic/split_screen).
            category: Topic category (used for Imagen style and Flux style setup if
                      setup_style() hasn't been called yet).
            style: Imagen style key (fallback provider only).
            seed: Optional seed for Imagen reproducibility.

        Returns:
            Path to the generated image file.
        """
        output_path = Path(output_path)

        # If category given but style not yet configured, do it now
        if category and self._flux and not self._current_style:
            self.setup_style(category)

        # Try Flux.1
        if self._flux is not None:
            try:
                return self._flux.generate(
                    prompt=prompt,
                    output_path=output_path,
                    image_composition=image_composition,
                )
            except Exception as e:
                if self._imagen is None:
                    raise
                logger.warning(
                    f"[ImageGenerator] Flux.1 failed, falling back to Imagen: "
                    f"{type(e).__name__}: {e}"
                )

        # Imagen fallback
        if self._imagen is not None:
            return self._imagen.generate(
                prompt=prompt,
                output_path=output_path,
                style=style,
                category=category,
                seed=seed,
            )

        raise RuntimeError("No image generation provider is available")

    def generate_batch(
        self,
        scenes: list,
        output_dir: Path,
        category: str,
        prefix: str = "scene",
    ) -> list[Path]:
        """
        Generate images for all scenes with consistent visual style.

        Sets up the Style Bible once, then generates each scene image using
        the scene's image_prompt and image_composition fields.

        Args:
            scenes: List of Scene objects (must have .image_prompt and optionally
                    .image_composition attributes).
            output_dir: Directory to save generated images.
            category: Topic category key — determines the Style Bible.
            prefix: Filename prefix (e.g. "scene" → scene_000.jpg).

        Returns:
            List of image file paths (same order as scenes).
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Set consistent style for the whole video
        self.setup_style(category)

        paths: list[Path] = []
        total = len(scenes)

        for i, scene in enumerate(scenes):
            output_path = output_dir / f"{prefix}_{i:03d}.jpg"
            image_composition = getattr(scene, "image_composition", "wide")
            prompt = getattr(scene, "image_prompt", "")

            logger.info(
                f"[ImageGenerator] Scene {i + 1}/{total}: "
                f"composition={image_composition}, prompt={prompt[:60]}..."
            )

            path = self.generate(
                prompt=prompt,
                output_path=output_path,
                image_composition=image_composition,
                category=category,
            )
            paths.append(path)

            # Small delay between requests to avoid rate limits
            if i < total - 1:
                time.sleep(1)

        return paths


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    gen = ImageGenerator()
    test_prompt = (
        "A young Korean person looking surprised at their smartphone while surrounded "
        "by floating social media icons and dopamine molecules"
    )
    output = Path("/tmp/test_image.jpg")
    path = gen.generate(test_prompt, output, image_composition="wide", category="psychology")
    print(f"Generated image: {path}")
