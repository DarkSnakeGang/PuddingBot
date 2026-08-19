"""Wall Research Board-tab style PNG of a 10×9 wall grid and ham tour."""

from __future__ import annotations

import io
import os
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

COLS, ROWS = 10, 9
CELL = 84  # 2× the Board tab 42px cells, then downsampled
GAP = 8
PAD = 28
RADIUS = 12

BG = (18, 20, 26)
CELL_EMPTY = (200, 210, 220)
CELL_WALL = (59, 66, 80)
SNAKE_DARK = (20, 83, 45)
SNAKE_LIGHT = (62, 207, 122)
ARROW = (12, 47, 28)
START_FILL = (230, 195, 92)
START_STROKE = (26, 20, 0)
END_FILL = (110, 176, 234)
END_STROKE = (11, 28, 44)
TEXT = (232, 236, 241)
MUTED = (147, 160, 176)

Point = Tuple[float, float]
Cell = Tuple[int, int]


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "segoeui.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    )
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _cell_origin(r: int, c: int) -> Point:
    return (PAD + c * (CELL + GAP), PAD + r * (CELL + GAP))


def _cell_center(r: int, c: int) -> Point:
    x, y = _cell_origin(r, c)
    return (x + CELL / 2, y + CELL / 2)


def _polyline(draw: ImageDraw.ImageDraw, pts: Sequence[Point], fill, width: int) -> None:
    if len(pts) < 2:
        return
    r = width / 2
    draw.line(list(pts), fill=fill, width=width, joint="curve")
    for x, y in pts:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def _triangle(draw: ImageDraw.ImageDraw, p1: Point, p2: Point, p3: Point, fill) -> None:
    draw.polygon([p1, p2, p3], fill=fill)


def _segment_arrows(draw: ImageDraw.ImageDraw, pts: Sequence[Point]) -> None:
    h, w = 14.0, 11.0
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        dx, dy = bx - ax, by - ay
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / length, dy / length
        mx = ax + ux * length * 0.62
        my = ay + uy * length * 0.62
        _triangle(
            draw,
            (mx + ux * h, my + uy * h),
            (mx - ux * h - uy * w, my - uy * h + ux * w),
            (mx - ux * h + uy * w, my - uy * h - ux * w),
            ARROW,
        )


def _head_arrow(draw: ImageDraw.ImageDraw, pts: Sequence[Point]) -> None:
    if len(pts) < 2:
        return
    ax, ay = pts[0]
    bx, by = pts[1]
    dx, dy = bx - ax, by - ay
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / length, dy / length
    tip = (ax + ux * 32, ay + uy * 32)
    left = (ax - ux * 8 - uy * 20, ay - uy * 8 + ux * 20)
    right = (ax - ux * 8 + uy * 20, ay - uy * 8 - ux * 20)
    _triangle(draw, tip, left, right, START_STROKE)


def _circle(draw: ImageDraw.ImageDraw, center: Point, radius: float, fill, stroke, stroke_w: int) -> None:
    x, y = center
    box = (x - radius, y - radius, x + radius, y + radius)
    draw.ellipse(box, fill=fill, outline=stroke, width=stroke_w)


def render_board_png(
    grid: Sequence[Sequence[int]],
    tour: Optional[Sequence[Cell]] = None,
    *,
    is_cycle: bool = False,
    caption: str = "",
) -> bytes:
    """PNG matching the Wall Research Board tab: rounded cells + green snake."""
    title_h = 52 if caption else 0
    legend_h = 44
    grid_w = COLS * CELL + (COLS - 1) * GAP
    grid_h = ROWS * CELL + (ROWS - 1) * GAP
    width = PAD * 2 + grid_w
    height = title_h + PAD * 2 + grid_h + legend_h

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    if caption:
        font = _font(28)
        draw.text((PAD, 14), caption, fill=TEXT, font=font)

    y_shift = title_h

    def origin(r: int, c: int) -> Point:
        x, y = _cell_origin(r, c)
        return (x, y + y_shift)

    def center(r: int, c: int) -> Point:
        x, y = _cell_center(r, c)
        return (x, y + y_shift)

    for r in range(ROWS):
        for c in range(COLS):
            x, y = origin(r, c)
            fill = CELL_WALL if grid[r][c] == 2 else CELL_EMPTY
            draw.rounded_rectangle(
                (x, y, x + CELL, y + CELL),
                radius=RADIUS,
                fill=fill,
            )

    if tour:
        pts: List[Point] = [center(r, c) for r, c in tour]
        if is_cycle and len(pts) > 1:
            pts.append(pts[0])
        _polyline(draw, pts, SNAKE_DARK, 52)
        _polyline(draw, pts, SNAKE_LIGHT, 40)
        _segment_arrows(draw, pts)
        start = pts[0]
        sr, sc = tour[0]
        sx, sy = origin(sr, sc)
        draw.rounded_rectangle(
            (sx + 4, sy + 4, sx + CELL - 4, sy + CELL - 4),
            radius=RADIUS - 2,
            outline=START_FILL,
            width=6,
        )
        if not is_cycle:
            er, ec = tour[-1]
            ex, ey = origin(er, ec)
            draw.rounded_rectangle(
                (ex + 4, ey + 4, ex + CELL - 4, ey + CELL - 4),
                radius=RADIUS - 2,
                outline=END_FILL,
                width=6,
            )
            _circle(draw, pts[-1], 18, END_FILL, END_STROKE, 4)
        _circle(draw, start, 22, START_FILL, START_STROKE, 4)
        _head_arrow(draw, pts)

    legend_y = title_h + PAD + grid_h + 16
    legend_font = _font(22)
    lx = PAD
    _circle(draw, (lx + 12, legend_y + 12), 10, START_FILL, START_STROKE, 2)
    draw.text((lx + 28, legend_y), "start", fill=MUTED, font=legend_font)
    lx += 120
    if not is_cycle:
        _circle(draw, (lx + 12, legend_y + 12), 10, END_FILL, END_STROKE, 2)
        draw.text((lx + 28, legend_y), "end", fill=MUTED, font=legend_font)
        lx += 100
    draw.rounded_rectangle((lx, legend_y + 2, lx + 22, legend_y + 24), radius=4, fill=CELL_WALL)
    draw.text((lx + 30, legend_y), "wall", fill=MUTED, font=legend_font)

    out = img.resize((width // 2, height // 2), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
