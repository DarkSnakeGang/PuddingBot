"""Wall Research Board-tab PNG (local Board snake design).

Matches Documents/GoogleSnakeWallResearch gui/static/index.html showTour():
dark checkerboard, zero gap, blue tapered body, Google-Snake head at path end.
"""

from __future__ import annotations

import io
import math
import os
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Board CSS: --board-cell 42px, --board-gap 0. Render at 3× then downsample.
SCALE = 3
BASE_CELL = 42
CELL = BASE_CELL * SCALE
GAP = 0
FRAME = 3 * SCALE
FRAME_RADIUS = 6 * SCALE
PAD = 10 * SCALE

BG = (18, 20, 26)
BOARD_BG = (18, 18, 22)       # #121216
FRAME_COL = (46, 46, 54)      # --board-frame
CHK_A = (26, 26, 31)          # --board-chk-a
CHK_B = (36, 36, 44)          # --board-chk-b
WALL = (5, 5, 5)              # --board-wall
HEAD_COL = (0x5B, 0x8D, 0xEF)
TIP_COL = (0x2A, 0x4A, 0xB8)
EYE = (255, 255, 255)
PUPIL = (0x1A, 0x3A, 0x8A)
NOSTRIL = (0x2A, 0x4A, 0x9A)
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


def _mix(t: float) -> Tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(round(h + (p - h) * t)) for h, p in zip(HEAD_COL, TIP_COL))


def _cell_origin(r: int, c: int, x0: float, y0: float) -> Point:
    return (x0 + c * CELL, y0 + r * CELL)


def _cell_center(r: int, c: int, x0: float, y0: float) -> Point:
    x, y = _cell_origin(r, c, x0, y0)
    return (x + CELL / 2, y + CELL / 2)


def _rot(local_x: float, local_y: float, ux: float, uy: float, ox: float, oy: float) -> Point:
    """Map head-local coords (forward = +x) into image space using facing (ux, uy)."""
    # SVG rotate(atan2(uy,ux)) then +x is forward.
    return (ox + local_x * ux - local_y * uy, oy + local_x * uy + local_y * ux)


def _circle(draw: ImageDraw.ImageDraw, center: Point, radius: float, fill, *, alpha_img=None) -> None:
    x, y = center
    r = max(0.5, radius)
    box = (x - r, y - r, x + r, y + r)
    if alpha_img is not None:
        ImageDraw.Draw(alpha_img).ellipse(box, fill=fill)
    else:
        draw.ellipse(box, fill=fill)


def _stroke_seg(
    draw: ImageDraw.ImageDraw,
    a: Point,
    b: Point,
    width: float,
    color: Tuple[int, int, int],
) -> None:
    w = max(1, int(round(width)))
    r = width / 2
    draw.line([a, b], fill=color, width=w)
    for x, y in (a, b):
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


def _draw_snake(draw: ImageDraw.ImageDraw, pts: Sequence[Point], cell: float) -> None:
    """Port of Board-tab showTour body + Google-Snake head (head = path end)."""
    n = len(pts)
    if n == 0:
        return
    head_i = n - 1
    neck_i = n - 2 if n > 1 else 0
    ux, uy = 0.0, -1.0
    if n > 1:
        dx = pts[head_i][0] - pts[neck_i][0]
        dy = pts[head_i][1] - pts[neck_i][1]
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length

    tip_pull = head_pull = 0.0
    if n > 1:
        gap_px = math.hypot(pts[0][0] - pts[head_i][0], pts[0][1] - pts[head_i][1])
        if gap_px < cell * 1.25:
            tip_pull = cell * 0.45
            head_pull = cell * 0.2

    tip_x, tip_y = pts[0]
    if n > 1 and tip_pull:
        dx = pts[1][0] - pts[0][0]
        dy = pts[1][1] - pts[0][1]
        length = math.hypot(dx, dy) or 1.0
        tip_x += (dx / length) * tip_pull
        tip_y += (dy / length) * tip_pull

    head_x = pts[head_i][0] - ux * head_pull
    head_y = pts[head_i][1] - uy * head_pull

    head_w = cell * 0.7
    tip_w = cell * 0.32

    def t_at(i: int) -> float:
        return 0.0 if n <= 1 else (head_i - i) / head_i

    def width_at(t: float) -> float:
        return head_w * (1 - t) + tip_w * t

    poly: List[Tuple[float, float, float]] = [(tip_x, tip_y, 1.0)]
    for i in range(1, head_i):
        poly.append((pts[i][0], pts[i][1], t_at(i)))
    poly.append((head_x, head_y, 0.0))

    for i in range(len(poly) - 1):
        x0, y0, t0 = poly[i]
        x1, y1, t1 = poly[i + 1]
        steps = 4
        for s in range(steps):
            u0 = s / steps
            u1 = (s + 1) / steps
            xa = x0 + (x1 - x0) * u0
            ya = y0 + (y1 - y0) * u0
            xb = x0 + (x1 - x0) * u1
            yb = y0 + (y1 - y0) * u1
            t = t0 * (1 - (u0 + u1) / 2) + t1 * ((u0 + u1) / 2)
            _stroke_seg(draw, (xa, ya), (xb, yb), width_at(t), _mix(t))

    # Head (Google Snake style)
    col = _mix(0)
    neck_r = head_w / 2
    bulge_r = neck_r * 0.82
    bulge_x = neck_r * 0.12
    bulge_y = neck_r * 0.92
    snout_r = neck_r * 1.02
    snout_x = neck_r * 0.78
    eye_r = max(2.6 * (cell / 42), bulge_r * 0.72)
    eye_x = bulge_x + bulge_r * 0.02
    eye_y = bulge_y
    pupil_r = max(1.3 * (cell / 42), eye_r * 0.4)
    pupil_fwd = eye_r * 0.38
    pupil_in = eye_r * 0.1
    nostril_r = max(0.7 * (cell / 42), neck_r * 0.08)
    nostril_x = snout_x + snout_r * 0.58
    nostril_y = neck_r * 0.14

    for lx, ly, rad, fill in (
        (0.0, 0.0, neck_r, col),
        (bulge_x, -bulge_y, bulge_r, col),
        (bulge_x, bulge_y, bulge_r, col),
        (snout_x, 0.0, snout_r, col),
    ):
        _circle(draw, _rot(lx, ly, ux, uy, head_x, head_y), rad, fill)

    for lx, ly, rad, fill in (
        (eye_x, -eye_y, eye_r, EYE),
        (eye_x, eye_y, eye_r, EYE),
        (eye_x + pupil_fwd, -eye_y + pupil_in, pupil_r, PUPIL),
        (eye_x + pupil_fwd, eye_y - pupil_in, pupil_r, PUPIL),
        (nostril_x, -nostril_y, nostril_r, NOSTRIL),
        (nostril_x, nostril_y, nostril_r, NOSTRIL),
    ):
        _circle(draw, _rot(lx, ly, ux, uy, head_x, head_y), rad, fill)


def render_board_png(
    grid: Sequence[Sequence[int]],
    tour: Optional[Sequence[Cell]] = None,
    *,
    is_cycle: bool = False,
    caption: str = "",
) -> bytes:
    """PNG matching the local Wall Research Board tab (blue snake)."""
    title_h = 18 * SCALE if caption else 0
    grid_w = 10 * CELL
    grid_h = 9 * CELL
    inner_x = PAD + FRAME
    inner_y = title_h + PAD + FRAME
    width = PAD * 2 + FRAME * 2 + grid_w
    height = title_h + PAD * 2 + FRAME * 2 + grid_h

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    if caption:
        draw.text((PAD, 6 * SCALE), caption, fill=TEXT, font=_font(10 * SCALE))

    # Framed board
    draw.rounded_rectangle(
        (PAD, title_h + PAD, PAD + FRAME * 2 + grid_w, title_h + PAD + FRAME * 2 + grid_h),
        radius=FRAME_RADIUS,
        fill=BOARD_BG,
        outline=FRAME_COL,
        width=FRAME,
    )

    for r in range(9):
        for c in range(10):
            x, y = _cell_origin(r, c, inner_x, inner_y)
            if grid[r][c] == 2:
                fill = WALL
            else:
                fill = CHK_B if (r + c) & 1 else CHK_A
            draw.rectangle((x, y, x + CELL, y + CELL), fill=fill)

    if tour:
        pts: List[Point] = [_cell_center(r, c, inner_x, inner_y) for r, c in tour]
        # Soft drop shadow (Board feDropShadow)
        shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        _draw_snake_shadow(
            sdraw,
            [(p[0], p[1] + CELL * 0.05) for p in pts],
            float(CELL),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1.0, CELL * 0.045)))
        base = img.convert("RGBA")
        img = Image.alpha_composite(base, shadow).convert("RGB")
        draw = ImageDraw.Draw(img)
        _draw_snake(draw, pts, float(CELL))

    out = img.resize((width // SCALE, height // SCALE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _draw_snake_shadow(draw: ImageDraw.ImageDraw, pts: Sequence[Point], cell: float) -> None:
    """Same geometry as _draw_snake but flat translucent black for blur shadow."""
    n = len(pts)
    if n == 0:
        return
    head_i = n - 1
    neck_i = n - 2 if n > 1 else 0
    ux, uy = 0.0, -1.0
    if n > 1:
        dx = pts[head_i][0] - pts[neck_i][0]
        dy = pts[head_i][1] - pts[neck_i][1]
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
    tip_pull = head_pull = 0.0
    if n > 1:
        gap_px = math.hypot(pts[0][0] - pts[head_i][0], pts[0][1] - pts[head_i][1])
        if gap_px < cell * 1.25:
            tip_pull = cell * 0.45
            head_pull = cell * 0.2
    tip_x, tip_y = pts[0]
    if n > 1 and tip_pull:
        dx = pts[1][0] - pts[0][0]
        dy = pts[1][1] - pts[0][1]
        length = math.hypot(dx, dy) or 1.0
        tip_x += (dx / length) * tip_pull
        tip_y += (dy / length) * tip_pull
    head_x = pts[head_i][0] - ux * head_pull
    head_y = pts[head_i][1] - uy * head_pull
    head_w = cell * 0.7
    tip_w = cell * 0.32

    def t_at(i: int) -> float:
        return 0.0 if n <= 1 else (head_i - i) / head_i

    def width_at(t: float) -> float:
        return head_w * (1 - t) + tip_w * t

    poly = [(tip_x, tip_y, 1.0)]
    for i in range(1, head_i):
        poly.append((pts[i][0], pts[i][1], t_at(i)))
    poly.append((head_x, head_y, 0.0))
    ink = (0, 0, 0, 100)
    for i in range(len(poly) - 1):
        x0, y0, t0 = poly[i]
        x1, y1, t1 = poly[i + 1]
        for s in range(4):
            u0, u1 = s / 4, (s + 1) / 4
            xa = x0 + (x1 - x0) * u0
            ya = y0 + (y1 - y0) * u0
            xb = x0 + (x1 - x0) * u1
            yb = y0 + (y1 - y0) * u1
            t = t0 * (1 - (u0 + u1) / 2) + t1 * ((u0 + u1) / 2)
            w = width_at(t)
            r = w / 2
            draw.line([(xa, ya), (xb, yb)], fill=ink, width=max(1, int(round(w))))
            for x, y in ((xa, ya), (xb, yb)):
                draw.ellipse((x - r, y - r, x + r, y + r), fill=ink)
    neck_r = head_w / 2
    for lx, ly, rad in (
        (0.0, 0.0, neck_r),
        (neck_r * 0.12, -neck_r * 0.92, neck_r * 0.82),
        (neck_r * 0.12, neck_r * 0.92, neck_r * 0.82),
        (neck_r * 0.78, 0.0, neck_r * 1.02),
    ):
        cx, cy = _rot(lx, ly, ux, uy, head_x, head_y)
        draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=ink)
