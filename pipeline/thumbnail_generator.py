"""
Thumbnail Generator for 어쩌다지식 YouTube Pipeline.

Generates YouTube thumbnails (1280×720 JPEG) using Pillow compositing.
Supports 4 Korean YouTube thumbnail templates:
  - shock    (충격형): image left, bold text right — high CTR hook
  - list     (리스트형): large number + topic image + text
  - question (질문형): full-bleed darkened image + centered question text
  - compare  (비교형): left/right image split with VS divider

ThumbnailMeta is defined in script_generator.py to avoid circular imports.
This module imports it from there.

Dependencies: Pillow (PIL)
Fonts: Nanum Gothic (preferred), DejaVu Sans (CI fallback)
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import ThumbnailMeta from script_generator (defined there to avoid circular
# imports — script_generator has no dependency on thumbnail_generator)
# ---------------------------------------------------------------------------
from pipeline.script_generator import ThumbnailMeta  # noqa: E402

# ---------------------------------------------------------------------------
# Category → accent color mapping
# ---------------------------------------------------------------------------

CATEGORY_COLORS: dict[str, str] = {
    "psychology": "#A855F7",  # Purple
    "life":       "#F97316",  # Orange
    "tech":       "#06B6D4",  # Cyan
}


# ---------------------------------------------------------------------------
# ThumbnailGenerator
# ---------------------------------------------------------------------------


class ThumbnailGenerator:
    """
    Generates YouTube thumbnail images at 1280×720 px (JPEG quality 95).

    Four templates:
      shock    — image left 55 %, gradient overlay, bold text right
      list     — large number top-left, faded bg image, text bottom
      question — full-bleed darkened image, centred question text
      compare  — left / right split with VS divider

    Usage:
        gen = ThumbnailGenerator(image_generator=img_gen)
        path = gen.generate(meta, output_path, scene_images=[...])
    """

    CANVAS_W = 1280
    CANVAS_H = 720

    # Font fallback chains — try Korean (Nanum) first, then DejaVu for CI
    FONT_PATHS: dict[str, list[str]] = {
        "bold": [
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
        "regular": [
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ],
    }

    def __init__(
        self,
        image_generator=None,
        assets_dir: Path = None,
    ):
        """
        Args:
            image_generator: ImageGenerator instance (optional).
                             When provided, Flux.1 generates a dedicated
                             background image from meta.background_prompt.
            assets_dir: Directory for static assets (unused currently,
                        reserved for logo overlays, etc.).
        """
        self.image_gen = image_generator
        self.assets_dir = assets_dir or Path("assets")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        meta: ThumbnailMeta,
        output_path: Path,
        scene_images: list[Path] = None,
    ) -> Path:
        """
        Generate a YouTube thumbnail image and save it as JPEG.

        Args:
            meta: ThumbnailMeta with text content, template choice, prompts.
            output_path: Destination path for the 1280×720 JPEG.
            scene_images: Existing scene images used as background fallback
                          when Flux.1 is unavailable or background_prompt is empty.

        Returns:
            Path to the saved thumbnail image.
        """
        from PIL import Image

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Determine which template to use
        template = self.select_template(meta, "")

        # 2. Obtain background image
        bg = self._get_background_image(meta, scene_images or [])

        # 3. Apply template compositing
        if template == "shock":
            result = self._apply_shock_template(bg, meta)
        elif template == "list":
            result = self._apply_list_template(bg, meta)
        elif template == "question":
            result = self._apply_question_template(bg, meta)
        elif template == "compare":
            result = self._apply_compare_template(bg, meta, scene_images or [])
        else:
            logger.warning(f"Unknown template '{template}', falling back to shock")
            result = self._apply_shock_template(bg, meta)

        # 4. Apply subtle vignette
        result = self._apply_vignette(result)

        # 5. Save
        result = result.convert("RGB")
        result.save(str(output_path), "JPEG", quality=95)
        logger.info(f"[ThumbnailGenerator] Saved: {output_path.name} (template={template})")
        return output_path

    def generate_variants(
        self,
        meta: ThumbnailMeta,
        output_dir: Path,
        scene_images: list[Path] = None,
        count: int = 2,
    ) -> list[Path]:
        """
        Generate `count` thumbnail variants for A/B testing.

        Variants differ by a slight crop/zoom of the background image.

        Args:
            meta: ThumbnailMeta driving text and template.
            output_dir: Directory to save thumbnails.
            scene_images: Scene images for background fallback.
            count: Number of variants to generate (default 2).

        Returns:
            List of paths to generated thumbnails.
        """
        from PIL import Image

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []
        scene_images = scene_images or []

        for i in range(count):
            variant_path = output_dir / f"thumbnail_v{i + 1}.jpg"

            # For variant > 0, slightly zoom in on the background
            if i == 0 or not scene_images:
                current_meta = meta
            else:
                # Use next scene image for variety
                next_meta = ThumbnailMeta(
                    template=meta.template,
                    main_text=meta.main_text,
                    sub_text=meta.sub_text,
                    number_text=meta.number_text,
                    background_prompt=meta.background_prompt,
                    keyword_badge=meta.keyword_badge,
                    accent_color=meta.accent_color,
                )
                current_meta = next_meta

            # Generate with a slightly different crop if we have multiple images
            bg_images_for_variant = scene_images[i:] + scene_images[:i] if scene_images else []
            path = self.generate(current_meta, variant_path, bg_images_for_variant)
            paths.append(path)

        return paths

    def select_template(self, meta: ThumbnailMeta, topic_category: str) -> str:
        """
        Auto-select best template.

        Priority:
          1. meta.template if not empty / "auto"
          2. "list"     if meta.number_text is set
          3. "question" if main_text or sub_text contains "?"
          4. "shock"    (default)
        """
        if meta.template and meta.template not in ("", "auto"):
            return meta.template
        if meta.number_text:
            return "list"
        if "?" in meta.main_text or "?" in meta.sub_text:
            return "question"
        return "shock"

    # ------------------------------------------------------------------
    # Background acquisition
    # ------------------------------------------------------------------

    def _get_background_image(
        self, meta: ThumbnailMeta, scene_images: list[Path]
    ):
        """
        Obtain a background image.

        Priority:
          1. Flux.1 generation via self.image_gen + meta.background_prompt
          2. First available scene image
          3. Gradient fallback
        """
        from PIL import Image

        if self.image_gen and meta.background_prompt:
            try:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                    tmp_path = Path(f.name)
                thumb_prompt = (
                    f"YouTube thumbnail style, dramatic close-up, "
                    f"high contrast lighting, {meta.background_prompt}, "
                    f"no text, no letters"
                )
                self.image_gen.generate(
                    thumb_prompt, tmp_path, image_composition="closeup"
                )
                img = Image.open(tmp_path).convert("RGB")
                img = img.resize((self.CANVAS_W, self.CANVAS_H), Image.LANCZOS)
                tmp_path.unlink(missing_ok=True)
                return img
            except Exception as e:
                logger.warning(
                    f"[ThumbnailGenerator] Flux.1 bg failed: {e}, trying scene image"
                )

        if scene_images:
            try:
                img = Image.open(scene_images[0]).convert("RGB")
                return img.resize((self.CANVAS_W, self.CANVAS_H), Image.LANCZOS)
            except Exception as e:
                logger.warning(f"[ThumbnailGenerator] Scene image load failed: {e}")

        return self._create_gradient_bg(meta.accent_color)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _load_font(self, style: str, size: int):
        """Load a font with Nanum → DejaVu fallback chain."""
        from PIL import ImageFont

        paths = self.FONT_PATHS.get(style, self.FONT_PATHS["regular"])
        for font_path in paths:
            try:
                return ImageFont.truetype(font_path, size)
            except (OSError, IOError):
                continue
        logger.debug(
            f"[ThumbnailGenerator] No TTF found for style={style}, using default"
        )
        return ImageFont.load_default()

    def _create_gradient_bg(self, accent_color: str):
        """Create a dark gradient background as final fallback."""
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (self.CANVAS_W, self.CANVAS_H), (20, 20, 30))
        draw = ImageDraw.Draw(img)

        # Parse accent color
        try:
            ac = accent_color.lstrip("#")
            r, g, b = int(ac[0:2], 16), int(ac[2:4], 16), int(ac[4:6], 16)
        except Exception:
            r, g, b = 255, 68, 68

        # Gradient from dark → accent-tinted dark
        for y in range(self.CANVAS_H):
            t = y / self.CANVAS_H
            pr = int(20 + t * (r // 6))
            pg = int(20 + t * (g // 6))
            pb = int(30 + t * (b // 6))
            draw.line([(0, y), (self.CANVAS_W, y)], fill=(pr, pg, pb))

        return img

    def _apply_vignette(self, img):
        """Apply a subtle dark vignette to all four edges."""
        from PIL import Image, ImageDraw

        vignette = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(vignette)
        w, h = img.size
        strength = 110  # max alpha at edges

        for i in range(min(w, h) // 4):
            alpha = int(strength * (1 - i / (min(w, h) // 4)) ** 1.5)
            if alpha <= 0:
                break
            draw.rectangle(
                [i, i, w - i - 1, h - i - 1],
                outline=(0, 0, 0, alpha),
            )

        result = Image.alpha_composite(img.convert("RGBA"), vignette)
        return result.convert("RGB")

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        """Convert '#RRGGBB' to (R, G, B) tuple."""
        h = hex_color.lstrip("#")
        try:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except Exception:
            return 255, 68, 68

    def _draw_text_outlined(
        self,
        draw,
        xy: tuple[int, int],
        text: str,
        font,
        fill: tuple | str = "white",
        stroke_width: int = 3,
        stroke_fill: tuple | str = (0, 0, 0),
    ) -> None:
        """Draw text with outline for legibility on any background."""
        x, y = xy
        # Draw stroke by offsetting in all 8 directions
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_fill)
        draw.text((x, y), text, font=font, fill=fill)

    def _get_text_size(self, draw, text: str, font) -> tuple[int, int]:
        """Return (width, height) of text bounding box."""
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def _split_korean_text(self, text: str, max_chars: int = 8) -> list[str]:
        """
        Split Korean text into lines of at most `max_chars` characters.

        Prefers to break at spaces; falls back to hard character splits.
        """
        if not text:
            return [""]

        words = text.split()
        lines: list[str] = []
        current = ""

        for word in words:
            if not current:
                current = word
            elif len(current) + 1 + len(word) <= max_chars:
                current += " " + word
            else:
                lines.append(current)
                current = word

        if current:
            lines.append(current)

        # Hard-split any line that is still too long
        final: list[str] = []
        for line in lines:
            while len(line) > max_chars:
                final.append(line[:max_chars])
                line = line[max_chars:]
            if line:
                final.append(line)

        return final or [""]

    def _draw_badge(
        self,
        draw,
        text: str,
        x: int,
        y: int,
        color: str,
        font_size: int = 32,
    ) -> None:
        """Draw a filled rounded-rectangle badge with white text."""
        from PIL import ImageDraw

        font = self._load_font("bold", font_size)
        tw, th = self._get_text_size(draw, text, font)
        pad_x, pad_y = 18, 10
        rect_w = tw + pad_x * 2
        rect_h = th + pad_y * 2
        r, g, b = self._hex_to_rgb(color)

        # Fill rectangle (PIL doesn't have rounded-rect fill easily — use plain rect)
        draw.rectangle(
            [x, y, x + rect_w, y + rect_h],
            fill=(r, g, b, 220),
        )
        self._draw_text_outlined(
            draw,
            (x + pad_x, y + pad_y),
            text,
            font=font,
            fill="white",
            stroke_width=1,
            stroke_fill=(0, 0, 0),
        )

    def _draw_channel_name(self, draw, x: int, y: int, anchor: str = "rs") -> None:
        """Draw '어쩌다지식' channel watermark. anchor 'rs' = right baseline."""
        font = self._load_font("bold", 36)
        text = "어쩌다지식"
        if anchor == "rs":
            tw, th = self._get_text_size(draw, text, font)
            tx = x - tw
            ty = y - th
        else:
            tx, ty = x, y
        self._draw_text_outlined(draw, (tx, ty), text, font=font,
                                  fill=(200, 200, 200), stroke_width=2)

    # ------------------------------------------------------------------
    # Template implementations
    # ------------------------------------------------------------------

    def _apply_shock_template(self, bg, meta: ThumbnailMeta):
        """
        충격형 template:
          Left 55 %  — background image (slightly brightened)
          Right 45 % — dark gradient overlay + bold Korean text stack
          Bottom-left — keyword badge
          Bottom-right — channel name
        """
        from PIL import Image, ImageDraw, ImageEnhance

        canvas = bg.copy().convert("RGBA")

        # ---- Dark gradient overlay on right half ----
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        split_x = int(self.CANVAS_W * 0.52)
        for x in range(split_x, self.CANVAS_W):
            alpha = int(210 * (x - split_x) / (self.CANVAS_W - split_x))
            ov_draw.line([(x, 0), (x, self.CANVAS_H)], fill=(0, 0, 0, alpha))
        canvas = Image.alpha_composite(canvas, overlay)
        draw = ImageDraw.Draw(canvas)

        # ---- sub_text — small, top-right area ----
        if meta.sub_text:
            sub_font = self._load_font("regular", 40)
            sub_x = int(self.CANVAS_W * 0.57)
            self._draw_text_outlined(
                draw, (sub_x, 65), meta.sub_text,
                font=sub_font, fill=(220, 220, 220), stroke_width=2,
            )

        # ---- main_text — large, centre-right ----
        main_font = self._load_font("bold", 92)
        lines = self._split_korean_text(meta.main_text, max_chars=8)
        line_h = 108
        y_start = self.CANVAS_H // 2 - (len(lines) * line_h) // 2

        r, g, b = self._hex_to_rgb(meta.accent_color)

        for i, line in enumerate(lines):
            y = y_start + i * line_h
            lx = int(self.CANVAS_W * 0.57)
            # Subtle accent tint on alternating lines for visual rhythm
            fill_color = "white" if i % 2 == 0 else (r, g, b)
            self._draw_text_outlined(
                draw, (lx, y), line,
                font=main_font, fill=fill_color, stroke_width=5,
            )

        # ---- keyword badge — bottom-left ----
        if meta.keyword_badge:
            self._draw_badge(
                draw, meta.keyword_badge,
                28, self.CANVAS_H - 82,
                meta.accent_color, font_size=30,
            )

        # ---- channel name — bottom-right ----
        self._draw_channel_name(draw, self.CANVAS_W - 24, self.CANVAS_H - 24)

        return canvas.convert("RGB")

    def _apply_list_template(self, bg, meta: ThumbnailMeta):
        """
        리스트형 template:
          Full-canvas faded background image
          Top-left  — very large number_text in accent color
          Bottom-left — main_text (medium, white)
          Bottom-left — channel name below main_text
        """
        from PIL import Image, ImageDraw, ImageEnhance

        # Fade background
        enhancer = ImageEnhance.Brightness(bg.convert("RGB"))
        canvas = enhancer.enhance(0.55).convert("RGBA")
        draw = ImageDraw.Draw(canvas)

        r, g, b = self._hex_to_rgb(meta.accent_color)

        # ---- number_text — very large, top-left ----
        if meta.number_text:
            num_font = self._load_font("bold", 180)
            self._draw_text_outlined(
                draw, (40, 20), meta.number_text,
                font=num_font, fill=(r, g, b), stroke_width=6,
                stroke_fill=(0, 0, 0),
            )

        # ---- main_text — medium, bottom-left ----
        main_font = self._load_font("bold", 72)
        lines = self._split_korean_text(meta.main_text, max_chars=12)
        line_h = 84
        n_lines = len(lines)
        y_base = self.CANVAS_H - 40 - n_lines * line_h - 50  # 50px for channel name

        for i, line in enumerate(lines):
            y = y_base + i * line_h
            self._draw_text_outlined(
                draw, (40, y), line,
                font=main_font, fill="white", stroke_width=4,
            )

        # ---- channel name ----
        ch_font = self._load_font("bold", 34)
        self._draw_text_outlined(
            draw, (40, self.CANVAS_H - 52), "어쩌다지식",
            font=ch_font, fill=(180, 180, 180), stroke_width=2,
        )

        # ---- keyword badge — top-right ----
        if meta.keyword_badge:
            tw, _ = self._get_text_size(draw, meta.keyword_badge, self._load_font("bold", 30))
            badge_x = self.CANVAS_W - tw - 60
            self._draw_badge(draw, meta.keyword_badge, badge_x, 28, meta.accent_color, font_size=30)

        return canvas.convert("RGB")

    def _apply_question_template(self, bg, meta: ThumbnailMeta):
        """
        질문형 template:
          Full-bleed background image darkened 40 %
          Centre — large question main_text
          Below   — smaller sub_text
          Bottom  — channel name (left) + keyword badge (right)
        """
        from PIL import Image, ImageDraw, ImageEnhance

        enhancer = ImageEnhance.Brightness(bg.convert("RGB"))
        canvas = enhancer.enhance(0.60).convert("RGBA")
        draw = ImageDraw.Draw(canvas)

        r, g, b = self._hex_to_rgb(meta.accent_color)

        # ---- main_text — large, centred ----
        main_font = self._load_font("bold", 88)
        lines = self._split_korean_text(meta.main_text, max_chars=12)
        line_h = 100
        total_text_h = len(lines) * line_h
        y_start = self.CANVAS_H // 2 - total_text_h // 2 - 20

        for i, line in enumerate(lines):
            y = y_start + i * line_h
            tw, _ = self._get_text_size(draw, line, main_font)
            x = (self.CANVAS_W - tw) // 2
            fill_color = (r, g, b) if i == 0 else "white"
            self._draw_text_outlined(
                draw, (x, y), line,
                font=main_font, fill=fill_color, stroke_width=5,
            )

        # ---- sub_text — smaller, below main ----
        if meta.sub_text:
            sub_font = self._load_font("regular", 46)
            tw, _ = self._get_text_size(draw, meta.sub_text, sub_font)
            sx = (self.CANVAS_W - tw) // 2
            sy = y_start + total_text_h + 16
            self._draw_text_outlined(
                draw, (sx, sy), meta.sub_text,
                font=sub_font, fill=(210, 210, 210), stroke_width=2,
            )

        # ---- channel name — bottom-left ----
        ch_font = self._load_font("bold", 34)
        self._draw_text_outlined(
            draw, (30, self.CANVAS_H - 52), "어쩌다지식",
            font=ch_font, fill=(180, 180, 180), stroke_width=2,
        )

        # ---- keyword badge — bottom-right ----
        if meta.keyword_badge:
            badge_font_size = 30
            badge_font = self._load_font("bold", badge_font_size)
            tw, th = self._get_text_size(draw, meta.keyword_badge, badge_font)
            pad_x = 18
            badge_x = self.CANVAS_W - tw - pad_x * 2 - 20
            self._draw_badge(draw, meta.keyword_badge, badge_x, self.CANVAS_H - 68, meta.accent_color, badge_font_size)

        return canvas.convert("RGB")

    def _apply_compare_template(self, bg, meta: ThumbnailMeta, scene_images: list[Path] = None):
        """
        비교형 template:
          Left half  — first image (faded), sub_text label
          Right half — second image (faded), main_text label
          Centre     — bold "VS" divider in accent color
          Bottom     — channel name centred
        """
        from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

        scene_images = scene_images or []

        # Obtain left and right backgrounds
        left_bg = bg.copy()

        if len(scene_images) >= 2:
            try:
                right_img = Image.open(scene_images[1]).convert("RGB")
                right_bg = right_img.resize((self.CANVAS_W, self.CANVAS_H), Image.LANCZOS)
            except Exception:
                right_bg = bg.copy()
        else:
            # Flip the same image horizontally for right side
            right_bg = bg.transpose(Image.FLIP_LEFT_RIGHT)

        half_w = self.CANVAS_W // 2
        canvas = Image.new("RGB", (self.CANVAS_W, self.CANVAS_H))

        # Fade both halves
        def fade(img):
            return ImageEnhance.Brightness(img.convert("RGB")).enhance(0.50)

        left_faded = fade(left_bg).crop((0, 0, half_w, self.CANVAS_H))
        right_faded = fade(right_bg).crop((half_w, 0, self.CANVAS_W, self.CANVAS_H))

        canvas.paste(left_faded, (0, 0))
        canvas.paste(right_faded, (half_w, 0))

        draw = ImageDraw.Draw(canvas.convert("RGBA"))
        canvas_rgba = canvas.convert("RGBA")
        draw = ImageDraw.Draw(canvas_rgba)

        r, g, b = self._hex_to_rgb(meta.accent_color)

        # ---- Vertical centre divider line ----
        for y in range(self.CANVAS_H):
            draw.line(
                [(half_w - 3, y), (half_w + 3, y)],
                fill=(r, g, b, 200),
            )

        # ---- "VS" text at centre ----
        vs_font = self._load_font("bold", 96)
        vs_text = "VS"
        vs_w, vs_h = self._get_text_size(draw, vs_text, vs_font)
        vs_x = (self.CANVAS_W - vs_w) // 2
        vs_y = (self.CANVAS_H - vs_h) // 2
        self._draw_text_outlined(
            draw, (vs_x, vs_y), vs_text,
            font=vs_font, fill=(r, g, b), stroke_width=6,
        )

        # ---- sub_text — left side label ----
        if meta.sub_text:
            sub_font = self._load_font("bold", 54)
            sub_lines = self._split_korean_text(meta.sub_text, max_chars=8)
            sub_y = self.CANVAS_H // 2 - len(sub_lines) * 62 // 2
            for i, line in enumerate(sub_lines):
                lw, _ = self._get_text_size(draw, line, sub_font)
                lx = (half_w - lw) // 2
                self._draw_text_outlined(
                    draw, (lx, sub_y + i * 62), line,
                    font=sub_font, fill="white", stroke_width=4,
                )

        # ---- main_text — right side label ----
        main_font = self._load_font("bold", 54)
        main_lines = self._split_korean_text(meta.main_text, max_chars=8)
        main_y = self.CANVAS_H // 2 - len(main_lines) * 62 // 2
        for i, line in enumerate(main_lines):
            lw, _ = self._get_text_size(draw, line, main_font)
            lx = half_w + (half_w - lw) // 2
            self._draw_text_outlined(
                draw, (lx, main_y + i * 62), line,
                font=main_font, fill=(r, g, b), stroke_width=4,
            )

        # ---- channel name — bottom-centred ----
        ch_font = self._load_font("bold", 34)
        ch_text = "어쩌다지식"
        ch_w, ch_h = self._get_text_size(draw, ch_text, ch_font)
        self._draw_text_outlined(
            draw, ((self.CANVAS_W - ch_w) // 2, self.CANVAS_H - ch_h - 20),
            ch_text, font=ch_font, fill=(180, 180, 180), stroke_width=2,
        )

        return canvas_rgba.convert("RGB")
