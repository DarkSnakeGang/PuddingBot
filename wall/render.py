"""Wall Research Board-tab PNG of a 10×9 wall grid and ham tour.

Mirrors gui/static/index.html showTour() + .grid/.cell styles:
  --board-cell 42px, --board-gap 4px, border-radius 6px
  empty #dfe7f0, solved empty #c8d2dc, wall #3b4250
  snake #14532d / #3ecf7a, start #e6c35c, end #6eb0ea
"""

from __future__ import annotations

import io
import os
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

# Board tab base unit is 42px cells / 4px gap; render at 3× then downsample.
SCALE = 3
BASE_CELL = 42
BASE_GAP = 4
BASE_RADIUS = 6

CELL = BASE_CELL * SCALE
GAP = BASE_GAP * SCALE
RADIUS = BASE_RADIUS * SCALE
PAD = 14 * SCALE

BG = (18, 20, 26)           # --bg
CELL_EMPTY = (223, 231, 240)  # #dfe7f0
CELL_SOLVED = (200, 210, 220)  # #c8d2dc (.grid.solved .cell)
CELL_WALL = (59, 66, 80)      # #3b4250
SNAKE_DARK = (20, 83, 45)     # #14532d
SNAKE_LIGHT = (62, 207, 122)  # #3ecf7a
ARROW = (12, 47, 28)          # #0c2f1c
START_FILL = (230, 195, 92)   # #e6c35c
START_STROKE = (26, 20, 0)    # #1a1400
END_FILL = (110, 176, 234)    # #6eb0ea
END_STROKE = (11, 28, 44)     # #0b1c2c
TEXT = (232, 236, 241)

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


def _cell_origin(r: int, c: int, y0: float = 0.0) -> Point:
    return (PAD + c * (CELL + GAP), y0 + PAD + r * (CELL + GAP))


def _cell_center(r: int, c: int, y0: float = 0.0) -> Point:
    x, y = _cell_origin(r, c, y0)
    return (x + CELL / 2, y + CELL / 2)


def _polyline(draw: ImageDraw.ImageDraw, pts: Sequence[Point], fill, width: float) -> None:
    """Rounded stroke like SVG stroke-linecap/join round."""
    if len(pts) < 2:
        return
    r = width / 2
    draw.line(list(pts), fill=fill, width=max(1, int(round(width))), joint="curve")
    for x, y in pts:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def _triangle(draw: ImageDraw.ImageDraw, p1: Point, p2: Point, p3: Point, fill) -> None:
    draw.polygon([p1, p2, p3], fill=fill)


def _segment_arrows(draw: ImageDraw.ImageDraw, pts: Sequence[Point]) -> None:
    # showTour: h=7*scale, w=5.5*scale at mid 0.62 along each segment
    h, w = 7.0 * SCALE, 5.5 * SCALE
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
    # showTour: tip 16*scale, side 4/10*scale
    if len(pts) < 2:
        return
    ax, ay = pts[0]
    bx, by = pts[1]
    dx, dy = bx - ax, by - ay
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / length, dy / length
    tip = (ax + ux * 16 * SCALE, ay + uy * 16 * SCALE)
    left = (ax - ux * 4 * SCALE - uy * 10 * SCALE, ay - uy * 4 * SCALE + ux * 10 * SCALE)
    right = (ax - ux * 4 * SCALE + uy * 10 * SCALE, ay - uy * 4 * SCALE - ux * 10 * SCALE)
    _triangle(draw, tip, left, right, START_STROKE)


def _circle(draw: ImageDraw.ImageDraw, center: Point, radius: float, fill, stroke, stroke_w: float) -> None:
    x, y = center
    sw = max(1, int(round(stroke_w)))
    box = (x - radius, y - radius, x + radius, y + radius)
    draw.ellipse(box, fill=fill, outline=stroke, width=sw)


def _inset_ring(draw: ImageDraw.ImageDraw, origin: Point, color) -> None:
    """Match .cell.snake.start/end { box-shadow: inset 0 0 0 3px … }."""
    x, y = origin
    inset = 3 * SCALE
    draw.rounded_rectangle(
        (x + inset, y + inset, x + CELL - inset, y + CELL - inset),
        radius=max(1, RADIUS - inset),
        outline=color,
        width=inset,
    )


def render_board_png(
    grid: Sequence[Sequence[int]],
    tour: Optional[Sequence[Cell]] = None,
    *,
    is_cycle: bool = False,
    caption: str = "",
) -> bytes:
    """PNG matching the Wall Research Board tab grid + snake SVG."""
    title_h = 18 * SCALE if caption else 0
    grid_w = 10 * CELL + 9 * GAP
    grid_h = 9 * CELL + 8 * GAP
    width = PAD * 2 + grid_w
    height = title_h + PAD * 2 + grid_h

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    if caption:
        draw.text((PAD, 6 * SCALE), caption, fill=TEXT, font=_font(10 * SCALE))

    y0 = float(title_h)
    solved = bool(tour)
    empty_fill = CELL_SOLVED if solved else CELL_EMPTY

    for r in range(9):
        for c in range(10):
            x, y = _cell_origin(r, c, y0)
            fill = CELL_WALL if grid[r][c] == 2 else empty_fill
            draw.rounded_rectangle(
                (x, y, x + CELL, y + CELL),
                radius=RADIUS,
                fill=fill,
            )

    if tour:
        pts: List[Point] = [_cell_center(r, c, y0) for r, c in tour]
        if is_cycle and len(pts) > 1:
            pts.append(pts[0])

        _polyline(draw, pts, SNAKE_DARK, 26 * SCALE)
        _polyline(draw, pts, SNAKE_LIGHT, 20 * SCALE)
        _segment_arrows(draw, pts)

        sr, sc = tour[0]
        _inset_ring(draw, _cell_origin(sr, sc, y0), START_FILL)
        if not is_cycle:
            er, ec = tour[-1]
            _inset_ring(draw, _cell_origin(er, ec, y0), END_FILL)
            _circle(draw, pts[-1], 9 * SCALE, END_FILL, END_STROKE, 2 * SCALE)
        _circle(draw, pts[0], 11 * SCALE, START_FILL, START_STROKE, 2 * SCALE)
        _head_arrow(draw, pts)

    # Downsample 3× → Board-native resolution (sharp on Discord)
    out = img.resize((width // SCALE, height // SCALE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
