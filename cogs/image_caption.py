"""ESMBot-style white-bar caption rendering (Pillow)."""

from __future__ import annotations

import io
import os
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", "caption.otf"
)

# Discord bot uploads are typically capped at 8 MiB without boosts
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
# Decoding limits: one frame, and all frames of an animation combined (RGBA = 4 B/px)
MAX_FRAME_PIXELS = 40_000_000
MAX_ANIMATION_PIXELS = 40_000_000
MAX_FRAMES = 1000
Image.MAX_IMAGE_PIXELS = MAX_FRAME_PIXELS
# Antialiased caption text in GIFs uses these grays (always kept in the palette)
GRAY_STEP = 17
GRAY_RAMP = tuple((v, v, v) for v in range(0, 256, GRAY_STEP))


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if os.path.isfile(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


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
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines or [""]


def _build_caption_bar(width: int, caption: str) -> Image.Image:
    """White caption strip laid out like esmBot's libvips/Pango text.

    Font size width/10, wrap width width - 2*(width/25), line pitch ascent+descent,
    centred lines; the bar is the tight text ink height plus one font size.
    """
    width = max(1, width)
    size = max(12, width // 10)
    text_width = max(1, width - ((width // 25) * 2))
    font = _load_font(size)
    try:
        ascent, descent = font.getmetrics()
    except AttributeError:
        ascent, descent = size, size // 4
    pitch = max(1, ascent + descent)

    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines = _wrap_lines(measure, caption, font, text_width)
    mask = Image.new("L", (width, pitch * len(lines) + size), 0)
    draw = ImageDraw.Draw(mask)
    for index, line in enumerate(lines):
        x = (width - draw.textlength(line, font=font)) / 2
        draw.text((x, index * pitch), line, font=font, fill=255)

    ink = mask.getbbox() or (0, 0, width, pitch)
    ink_height = ink[3] - ink[1]
    bar_height = ink_height + size
    bar = Image.new("RGBA", (width, bar_height), (255, 255, 255, 255))
    bar.paste(
        Image.new("RGBA", (width, ink_height), (0, 0, 0, 255)),
        (0, (bar_height - ink_height) // 2),
        mask.crop((0, ink[1], width, ink[3])),
    )
    return bar


def _stack_caption(frame: Image.Image, caption_bar: Image.Image) -> Image.Image:
    frame_rgba = frame.convert("RGBA")
    if caption_bar.width != frame_rgba.width:
        caption_bar = caption_bar.resize(
            (
                frame_rgba.width,
                max(1, int(caption_bar.height * frame_rgba.width / caption_bar.width)),
            ),
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


def _is_animated(img: Image.Image) -> bool:
    n_frames = getattr(img, "n_frames", 1) or 1
    if n_frames > 1:
        return True
    return bool(getattr(img, "is_animated", False))


def _frame_duration_ms(frame: Image.Image) -> int:
    duration = frame.info.get("duration", 40)
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        duration = 40
    # Duration 0 means "as fast as possible" and can freeze in Discord
    return duration if duration > 0 else 40


def _extract_animated_frames(
    img: Image.Image, scale: float = 1.0
) -> Tuple[List[Image.Image], List[int]]:
    """Return RGBA frames (optionally downscaled) + durations. seek() applies GIF disposal."""
    frames: List[Image.Image] = []
    durations: List[int] = []
    n_frames = getattr(img, "n_frames", 1) or 1
    size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
    for index in range(n_frames):
        img.seek(index)
        frame = img.convert("RGBA")
        if scale < 0.999:
            frame = frame.resize(size, Image.Resampling.BOX)
        frames.append(frame)
        durations.append(_frame_duration_ms(img))
    img.seek(0)
    return frames, durations


def _flatten_rgb(frame: Image.Image) -> Image.Image:
    rgb = Image.new("RGB", frame.size, (255, 255, 255))
    rgba = frame.convert("RGBA")
    rgb.paste(rgba, mask=rgba.split()[-1])
    return rgb


def _palette_image(colors: List[Tuple[int, int, int]]) -> Image.Image:
    pal: List[int] = []
    for color in colors[:256]:
        pal.extend(color)
    pal.extend([0, 0, 0] * (256 - len(colors[:256])))
    image = Image.new("P", (1, 1))
    image.putpalette(pal)
    return image


def _palette_with_black_white(used_colors: List[Tuple[int, int, int]]) -> Image.Image:
    """Keep every used color; add the caption gray ramp, stealing the nearest slots if full."""
    colors: List[Tuple[int, int, int]] = []
    seen = set()
    for color in used_colors:
        if color in seen:
            continue
        seen.add(color)
        colors.append(color)

    def add_or_replace(target: Tuple[int, int, int]) -> None:
        if target in seen:
            return
        if len(colors) < 256:
            colors.append(target)
            seen.add(target)
            return
        best_i = 0
        best_d = 10**9
        for i, color in enumerate(colors):
            if color in GRAY_RAMP:
                continue
            dist = sum((color[j] - target[j]) ** 2 for j in range(3))
            if dist < best_d:
                best_d = dist
                best_i = i
        seen.discard(colors[best_i])
        colors[best_i] = target
        seen.add(target)

    for gray in GRAY_RAMP:
        add_or_replace(gray)
    return _palette_image(colors)


def _remap_to_palette(rgb: Image.Image, pal_img: Image.Image) -> Image.Image:
    """Map each pixel to an exact palette index; nearest-color if needed. No dither."""
    raw = list(pal_img.getpalette() or [])
    raw.extend([0] * (768 - len(raw)))
    raw = raw[:768]
    pal_colors = [tuple(raw[i : i + 3]) for i in range(0, 768, 3)]
    index_of: dict = {}
    unique_entries = []
    for i, color in enumerate(pal_colors):
        if color in index_of:
            continue
        index_of[color] = i
        unique_entries.append((i, color))

    color_to_index = {}
    counted = rgb.getcolors(maxcolors=rgb.size[0] * rgb.size[1]) or []
    for _, pixel in counted:
        idx = index_of.get(pixel)
        if idx is None:
            best_i, best_d = unique_entries[0][0], 10**9
            pr, pg, pb = pixel
            for cand_i, (cr, cg, cb) in unique_entries:
                dist = (pr - cr) ** 2 + (pg - cg) ** 2 + (pb - cb) ** 2
                if dist < best_d:
                    best_d = dist
                    best_i = cand_i
                    if dist == 0:
                        break
            idx = best_i
        color_to_index[pixel] = idx

    indices = [color_to_index[pixel] for pixel in rgb.getdata()]
    out = Image.new("P", rgb.size)
    out.putpalette(raw)
    out.putdata(indices)
    return out


def _collect_gif_palette(img: Image.Image) -> Optional[Image.Image]:
    """Exact RGB colors from a palette GIF (global + per-frame local palettes)."""
    n_frames = getattr(img, "n_frames", 1) or 1
    unique: List[Tuple[int, int, int]] = []
    seen = set()
    for index in range(n_frames):
        img.seek(index)
        if img.mode != "P":
            img.seek(0)
            return None
        raw = img.getpalette() or []
        used_indices = set(img.getdata())
        for index_value in used_indices:
            offset = index_value * 3
            if offset + 2 >= len(raw):
                continue
            color = (raw[offset], raw[offset + 1], raw[offset + 2])
            if color in seen:
                continue
            seen.add(color)
            unique.append(color)
            if len(unique) > 256:
                img.seek(0)
                return None
    img.seek(0)
    if not unique:
        return None
    return _palette_with_black_white(unique)


def _adaptive_palette(frames: List[Image.Image]) -> Image.Image:
    """Pick 256 colors from every frame (nearest thumbs, so original hues stay)."""
    samples: List[Image.Image] = []
    for frame in frames:
        rgb = _flatten_rgb(frame)
        if max(rgb.size) > 128:
            rgb = rgb.copy()
            rgb.thumbnail((128, 128), Image.Resampling.NEAREST)
        samples.append(rgb)
    width = max(sample.width for sample in samples)
    height = sum(sample.height for sample in samples)
    sheet = Image.new("RGB", (width, height), (255, 255, 255))
    y = 0
    for sample in samples:
        sheet.paste(sample, (0, y))
        y += sample.height
    method = getattr(Image.Quantize, "MAXCOVERAGE", Image.Quantize.MEDIANCUT)
    body_colors = 256 - len(GRAY_RAMP)
    reduced = sheet.quantize(colors=body_colors, method=method, dither=Image.Dither.NONE)
    raw = list(reduced.getpalette() or [])
    used = [tuple(raw[i : i + 3]) for i in range(0, min(len(raw), body_colors * 3), 3)]
    return _palette_with_black_white(used)


def _frames_palette(
    frames: List[Image.Image], source_palette: Optional[Image.Image]
) -> Image.Image:
    if source_palette is not None:
        return source_palette
    unique: List[Tuple[int, int, int]] = []
    seen = set()
    for frame in frames:
        counted = _flatten_rgb(frame).getcolors(maxcolors=256)
        if counted is None:
            return _adaptive_palette(frames)
        for _, color in counted:
            if color in seen:
                continue
            seen.add(color)
            unique.append(color)
            if len(unique) > 256:
                return _adaptive_palette(frames)
    return _palette_with_black_white(unique)


def _frame_palette(frame: Image.Image) -> Image.Image:
    rgb = _flatten_rgb(frame)
    counted = rgb.getcolors(maxcolors=256)
    if counted is not None:
        return _palette_with_black_white([color for _, color in counted])
    return _adaptive_palette([frame])


def _caption_bar_gray(bar: Image.Image) -> Image.Image:
    """Snap antialiased caption text onto GRAY_RAMP so it maps exactly into the palette."""
    luma = bar.convert("L")
    step = GRAY_STEP
    return luma.point(lambda px: min(255, round(px / step) * step), mode="L").convert("RGB")


def _body_to_p(frame: Image.Image, palette_img: Image.Image) -> Image.Image:
    """Quantize the original frame only (never the caption bar)."""
    return _remap_to_palette(_flatten_rgb(frame), palette_img)


def _stack_paletted(bar_rgb: Image.Image, body_p: Image.Image) -> Image.Image:
    if bar_rgb.width != body_p.width:
        bar_rgb = bar_rgb.resize(
            (body_p.width, max(1, int(bar_rgb.height * body_p.width / bar_rgb.width))),
            Image.Resampling.NEAREST,
        )
    bar_p = _remap_to_palette(bar_rgb.convert("RGB"), body_p)
    out = Image.new("P", (body_p.width, bar_p.height + body_p.height))
    out.putpalette(body_p.getpalette() or [])
    out.paste(bar_p, (0, 0))
    out.paste(body_p, (0, bar_p.height))
    return out


def _scale_frames(frames: List[Image.Image], factor: float) -> List[Image.Image]:
    if factor >= 0.999:
        return frames
    scaled = []
    for frame in frames:
        width = max(1, int(frame.width * factor))
        height = max(1, int(frame.height * factor))
        scaled.append(frame.resize((width, height), Image.Resampling.BOX))
    return scaled


def _save_gif(
    frames: List[Image.Image],
    durations: List[int],
    loop: int,
    caption_bar: Image.Image,
    palette_img: Optional[Image.Image] = None,
    force_global_palette: bool = False,
) -> bytes:
    if not frames:
        raise ValueError("GIF has no frames")
    bar_gray = _caption_bar_gray(caption_bar)
    if palette_img is not None or force_global_palette:
        shared = _frames_palette(frames, palette_img)
        paletted = [_stack_paletted(bar_gray, _body_to_p(frame, shared)) for frame in frames]
    else:
        paletted = [
            _stack_paletted(bar_gray, _body_to_p(frame, _frame_palette(frame)))
            for frame in frames
        ]
    buf = io.BytesIO()
    paletted[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=paletted[1:],
        duration=durations,
        loop=loop,
        disposal=2,
        optimize=False,
    )
    return buf.getvalue()


def caption_image(image_bytes: bytes, caption: str) -> Tuple[bytes, str]:
    """
    Add an ESMBot-style top caption bar.
    Returns (output_bytes, extension) where extension is 'gif' or 'png'.
    Animated GIF/WebP/APNG stay animated GIFs.
    """
    if not (caption or "").strip():
        raise ValueError("Caption text is empty")

    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Image.DecompressionBombError:
        raise ValueError("That image is too large to caption.") from None
    with img:
        if img.width * img.height > MAX_FRAME_PIXELS:
            raise ValueError("That image is too large to caption.")
        if _is_animated(img):
            n_frames = getattr(img, "n_frames", 1) or 1
            if n_frames > MAX_FRAMES:
                raise ValueError("That GIF has too many frames to caption.")
            total_pixels = img.width * img.height * n_frames
            scale = min(1.0, (MAX_ANIMATION_PIXELS / total_pixels) ** 0.5)
            source_palette = _collect_gif_palette(img) if scale >= 0.999 else None
            raw_frames, durations = _extract_animated_frames(img, scale)
            loop = int(img.info.get("loop", 0) or 0)
            bar = _build_caption_bar(raw_frames[0].width, caption)

            data = _save_gif(raw_frames, durations, loop, bar, source_palette)
            if len(data) > MAX_OUTPUT_BYTES:
                data = _save_gif(
                    raw_frames, durations, loop, bar, None, force_global_palette=True
                )
            scale = 1.0
            while len(data) > MAX_OUTPUT_BYTES and scale > 0.35:
                scale *= 0.75
                smaller = _scale_frames(raw_frames, scale)
                smaller_bar = bar.resize(
                    (
                        smaller[0].width,
                        max(1, int(bar.height * smaller[0].width / bar.width)),
                    ),
                    Image.Resampling.NEAREST,
                )
                data = _save_gif(
                    smaller, durations, loop, smaller_bar, None, force_global_palette=True
                )
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
