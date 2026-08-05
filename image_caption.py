"""ESMBot-style white-bar caption rendering (Pillow)."""

from __future__ import annotations

import io
import os
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageSequence

FONT_PATH = os.path.join(
    os.path.dirname(__file__), "assets", "fonts", "caption.otf"
)

# Discord upload safety margin
MAX_OUTPUT_BYTES = 24 * 1024 * 1024


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if os.path.isfile(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_lines(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int
) -> List[str]:
    text = (text or "").strip()
    if not text:
        return [""]

    lines: List[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            w, _ = _text_size(draw, trial, font)
            if w <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines or [""]


def _build_caption_bar(width: int, caption: str) -> Image.Image:
    """White caption strip matching esmBot layout (font ~width/10, pad ~width/25)."""
    width = max(1, width)
    size = max(12, width // 10)
    text_width = max(1, width - ((width // 25) * 2))
    font = _load_font(size)

    # Probe wrap with a throwaway image
    probe = Image.new("RGB", (width, size), "white")
    draw = ImageDraw.Draw(probe)
    lines = _wrap_lines(draw, f" {caption} ", font, text_width)
    line_heights = []
    total_text_h = 0
    for line in lines:
        _, h = _text_size(draw, line if line else " ", font)
        line_heights.append(h)
        total_text_h += h
    # Extra vertical room like esmBot: text.height() + size
    bar_height = max(size * 2, total_text_h + size)

    bar = Image.new("RGBA", (width, bar_height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(bar)
    y = (bar_height - total_text_h) // 2
    for line, h in zip(lines, line_heights):
        w, _ = _text_size(draw, line if line else " ", font)
        x = (width - w) // 2
        draw.text((x, y), line, font=font, fill=(0, 0, 0, 255))
        y += h
    return bar


def _stack_caption(frame: Image.Image, caption_bar: Image.Image) -> Image.Image:
    frame_rgba = frame.convert("RGBA")
    # Caption bar may be for a different width if frames vary; resize bar to frame width
    if caption_bar.width != frame_rgba.width:
        caption_bar = caption_bar.resize(
            (frame_rgba.width, max(1, int(caption_bar.height * frame_rgba.width / caption_bar.width))),
            Image.Resampling.LANCZOS,
        )
    out = Image.new(
        "RGBA",
        (frame_rgba.width, caption_bar.height + frame_rgba.height),
        (255, 255, 255, 255),
    )
    out.paste(caption_bar, (0, 0))
    out.paste(frame_rgba, (0, caption_bar.height), frame_rgba)
    return out


def caption_image(image_bytes: bytes, caption: str) -> Tuple[bytes, str]:
    """
    Add an ESMBot-style top caption bar.
    Returns (output_bytes, extension) where extension is 'gif' or 'png'.
    """
    if not (caption or "").strip():
        raise ValueError("Caption text is empty")

    with Image.open(io.BytesIO(image_bytes)) as img:
        is_gif = (
            getattr(img, "is_animated", False)
            and getattr(img, "n_frames", 1) > 1
            and (img.format or "").upper() == "GIF"
        )

        if is_gif:
            frames_out: List[Image.Image] = []
            durations: List[int] = []
            # Build bar from first frame width
            first = img.convert("RGBA")
            bar = _build_caption_bar(first.width, caption)

            for frame in ImageSequence.Iterator(img):
                durations.append(int(frame.info.get("duration", 40) or 40))
                composed = _stack_caption(frame, bar)
                # GIF palette
                frames_out.append(composed.convert("P", palette=Image.Palette.ADAPTIVE, colors=255))

            buf = io.BytesIO()
            frames_out[0].save(
                buf,
                format="GIF",
                save_all=True,
                append_images=frames_out[1:],
                duration=durations,
                loop=img.info.get("loop", 0),
                disposal=2,
                optimize=False,
            )
            data = buf.getvalue()
            if len(data) > MAX_OUTPUT_BYTES:
                raise ValueError("Captioned GIF is too large to upload to Discord")
            return data, "gif"

        rgba = img.convert("RGBA")
        bar = _build_caption_bar(rgba.width, caption)
        composed = _stack_caption(rgba, bar)
        buf = io.BytesIO()
        composed.convert("RGBA").save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        if len(data) > MAX_OUTPUT_BYTES:
            raise ValueError("Captioned image is too large to upload to Discord")
        return data, "png"
