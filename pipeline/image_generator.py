"""
Image Generator for 어쩌다지식 YouTube Pipeline.

Uses Google Vertex AI Imagen 3 to generate Korean webtoon-style illustrations
for each scene in the video.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Style prefix applied to all prompts
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


class ImageGenerator:
    """Generates scene illustrations using Google Vertex AI Imagen 3."""

    MAX_RETRIES = 3
    RETRY_DELAY = 10  # seconds — Imagen can be slow

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: str = "us-central1",
        model_name: str = "imagen-3.0-generate-001",
        credentials_path: Optional[str] = None,
    ):
        """
        Initialize the image generator.

        Args:
            project_id: GCP project ID. If None, reads GOOGLE_CLOUD_PROJECT env var.
            location: Vertex AI region.
            model_name: Imagen model name.
            credentials_path: Path to service account JSON.
        """
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
            f"ImageGenerator initialized: project={self.project_id}, "
            f"model={model_name}, location={location}"
        )

    def _get_model(self):
        """Lazy-load the Vertex AI model to avoid import overhead at startup."""
        if self._model is None:
            import vertexai
            from vertexai.preview.vision_models import ImageGenerationModel

            vertexai.init(project=self.project_id, location=self.location)
            self._model = ImageGenerationModel.from_pretrained(self.model_name)
            logger.debug(f"Imagen model loaded: {self.model_name}")
        return self._model

    def generate(
        self,
        prompt: str,
        output_path: str | Path,
        style: str = "default",
        category: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Path:
        """
        Generate an illustration for a scene.

        Args:
            prompt: English image description for the scene.
            output_path: Where to save the generated image (JPEG).
            style: Style variant key (default/psychology/life/tech).
            category: Topic category — overrides style if provided.
            seed: Optional seed for reproducibility.

        Returns:
            Path to the saved image file.

        Raises:
            RuntimeError: If image generation fails after all retries.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine style prefix
        if category and category in STYLE_PREFIXES:
            style_key = category
        elif style in STYLE_PREFIXES:
            style_key = style
        else:
            style_key = "default"

        style_prefix = STYLE_PREFIXES[style_key]
        full_prompt = f"{style_prefix} {prompt}"

        # Truncate if too long (Imagen limit is ~1500 chars)
        if len(full_prompt) > 1400:
            full_prompt = full_prompt[:1400]
            logger.warning("Prompt truncated to 1400 chars")

        logger.info(f"Generating image for: {prompt[:80]}...")
        logger.debug(f"Full prompt: {full_prompt}")

        last_error: Optional[Exception] = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = self._call_imagen(full_prompt, seed=seed)
                # Save image
                result.save(str(output_path))
                logger.info(f"Image saved: {output_path.name}")
                return output_path

            except Exception as e:
                error_str = str(e).lower()
                logger.warning(
                    f"Image generation attempt {attempt}/{self.MAX_RETRIES} failed: "
                    f"{type(e).__name__}: {e}"
                )
                last_error = e

                # Check for safety filter block
                if "safety" in error_str or "block" in error_str or "policy" in error_str:
                    logger.warning("Prompt blocked by safety filter. Trying with safer prompt...")
                    prompt = self._sanitize_prompt(prompt)
                    full_prompt = f"{style_prefix} {prompt}"
                    if attempt >= self.MAX_RETRIES:
                        break
                elif "quota" in error_str or "rate" in error_str:
                    if attempt < self.MAX_RETRIES:
                        wait = self.RETRY_DELAY * attempt * 2
                        logger.info(f"Rate limited, waiting {wait}s...")
                        time.sleep(wait)
                elif attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)

        # Fallback: generate a simple placeholder image
        logger.error(f"All Imagen attempts failed. Creating placeholder image.")
        return self._create_placeholder(output_path, prompt, style_key)

    def _call_imagen(self, prompt: str, seed: Optional[int] = None) -> object:
        """Call Vertex AI Imagen API and return the first generated image."""
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
        """Remove potentially problematic keywords from prompt."""
        remove_words = ["violence", "gore", "blood", "weapon", "nude", "nsfw", "death"]
        sanitized = prompt
        for word in remove_words:
            sanitized = sanitized.replace(word, "")
        return sanitized.strip() or "Abstract colorful digital illustration, knowledge concept"

    def _create_placeholder(self, output_path: Path, prompt: str, style: str) -> Path:
        """Create a simple colored placeholder image when Imagen fails."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            width, height = 1920, 1080
            style_colors = {
                "psychology": (147, 112, 219),  # Purple
                "life": (255, 165, 0),           # Orange
                "tech": (0, 191, 255),            # Deep sky blue
                "default": (100, 149, 237),       # Cornflower blue
            }
            bg_color = style_colors.get(style, style_colors["default"])

            img = Image.new("RGB", (width, height), bg_color)
            draw = ImageDraw.Draw(img)

            # Add gradient-like effect
            for y in range(height):
                alpha = int(255 * (1 - y / height * 0.4))
                r = min(255, bg_color[0] + int(40 * y / height))
                g = min(255, bg_color[1] + int(20 * y / height))
                b = min(255, bg_color[2] + int(30 * y / height))
                draw.line([(0, y), (width, y)], fill=(r, g, b))

            # Add channel name as watermark
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
                small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
            except OSError:
                font = ImageFont.load_default()
                small_font = font

            draw.text((width // 2, height // 2 - 40), "어쩌다지식", font=font, fill="white",
                      anchor="mm" if hasattr(ImageFont, "truetype") else None)
            draw.text((width // 2, height // 2 + 40), prompt[:60], font=small_font,
                      fill=(220, 220, 220), anchor="mm" if hasattr(ImageFont, "truetype") else None)

            img.save(str(output_path), "JPEG", quality=95)
            logger.info(f"Placeholder image created: {output_path.name}")
            return output_path

        except ImportError:
            logger.error("Pillow not installed, cannot create placeholder image")
            raise RuntimeError(f"Imagen failed and Pillow not available for fallback") from None

    def generate_batch(
        self,
        prompts: list[str],
        output_dir: Path,
        style: str = "default",
        category: Optional[str] = None,
        prefix: str = "scene",
    ) -> list[Path]:
        """
        Generate images for multiple prompts.

        Args:
            prompts: List of English image prompts.
            output_dir: Directory to save images.
            style: Style variant.
            category: Topic category for style selection.
            prefix: Filename prefix (e.g., "scene" → scene_000.jpg).

        Returns:
            List of paths to generated images (same order as prompts).
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = []
        total = len(prompts)
        for i, prompt in enumerate(prompts):
            output_path = output_dir / f"{prefix}_{i:03d}.jpg"
            logger.info(f"Generating image {i + 1}/{total}: {output_path.name}")

            path = self.generate(
                prompt=prompt,
                output_path=output_path,
                style=style,
                category=category,
            )
            paths.append(path)

            # Respect Imagen rate limits (default: 2 images/minute on free tier)
            if i < total - 1:
                time.sleep(2)

        return paths


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
    path = gen.generate(test_prompt, output, category="psychology")
    print(f"Generated image: {path}")
