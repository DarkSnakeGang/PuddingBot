"""Pillow chart helpers for FastSnakeStats progression and activity heatmaps."""

from __future__ import annotations

import calendar
import io
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()


def _parse_iso_seconds(iso_time: str) -> Optional[float]:
    """Parse ISO-8601 duration (PTxxS / PT1M2.3S) or bare number to seconds."""
    if iso_time is None:
        return None
    text = str(iso_time).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    if not text.startswith("PT"):
        return None
    body = text[2:]
    seconds = 0.0
    num = ""
    for ch in body:
        if ch.isdigit() or ch == ".":
            num += ch
            continue
        if not num:
            continue
        value = float(num)
        num = ""
        if ch == "H":
            seconds += value * 3600
        elif ch == "M":
            seconds += value * 60
        elif ch == "S":
            seconds += value
    if num:
        seconds += float(num)
    return seconds


def progression_chart_png(
    flips: List[Dict],
    *,
    title: str = "WR Progression",
    high_score: bool = False,
) -> Optional[bytes]:
    """Line chart of progression points. Returns PNG bytes or None if <2 points."""
    points: List[Tuple[datetime, float]] = []
    for flip in flips:
        date_str = flip.get("d") or ""
        try:
            dt = datetime.fromisoformat(date_str[:10])
        except ValueError:
            continue
        raw = flip.get("t")
        if high_score:
            try:
                y = float(raw)
            except (TypeError, ValueError):
                y = _parse_iso_seconds(str(raw or "")) or 0.0
        else:
            y = _parse_iso_seconds(str(raw or ""))
            if y is None:
                continue
        points.append((dt, float(y)))

    if len(points) < 2:
        return None

    points.sort(key=lambda p: p[0])
    width, height = 900, 420
    margin_l, margin_r, margin_t, margin_b = 70, 24, 48, 56
    img = Image.new("RGB", (width, height), (24, 28, 36))
    draw = ImageDraw.Draw(img)
    font = _font(14)
    font_sm = _font(11)
    title_font = _font(18)

    draw.text((margin_l, 12), title, fill=(240, 240, 245), font=title_font)

    xs = [p[0].timestamp() for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 <= x0:
        x1 = x0 + 1
    if y1 <= y0:
        y1 = y0 + 1
    # Pad Y slightly
    pad = (y1 - y0) * 0.08 or 1
    y0 -= pad
    y1 += pad

    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    def to_xy(ts: float, val: float) -> Tuple[int, int]:
        px = margin_l + int((ts - x0) / (x1 - x0) * plot_w)
        py = margin_t + int((1 - (val - y0) / (y1 - y0)) * plot_h)
        return px, py

    # Axes
    draw.rectangle(
        [margin_l, margin_t, width - margin_r, height - margin_b],
        outline=(60, 68, 82),
        width=1,
    )

    coords = [to_xy(ts, val) for ts, val in zip(xs, ys)]
    if len(coords) >= 2:
        draw.line(coords, fill=(80, 180, 255), width=2)
    for cx, cy in coords:
        draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(255, 200, 80))

    # Y labels
    for frac in (0.0, 0.5, 1.0):
        val = y0 + (y1 - y0) * (1 - frac) if not high_score else y0 + (y1 - y0) * frac
        # Use actual axis mapping: top = y1 for times (lower is better visually still top=max)
        axis_val = y1 - (y1 - y0) * frac
        _, py = to_xy(x0, axis_val)
        label = f"{axis_val:.2f}" if axis_val < 100 else f"{axis_val:.0f}"
        draw.text((8, py - 6), label, fill=(160, 168, 180), font=font_sm)

    # X labels (first / mid / last)
    for idx in (0, len(points) // 2, len(points) - 1):
        dt, val = points[idx]
        px, _ = to_xy(xs[idx], val)
        label = dt.strftime("%Y-%m-%d")
        draw.text((px - 30, height - margin_b + 8), label, fill=(160, 168, 180), font=font_sm)

    y_caption = "Score" if high_score else "Time (s)"
    draw.text((margin_l, height - 22), y_caption, fill=(160, 168, 180), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def activity_heatmap_png(
    year_entries: List[Dict],
    year: str,
    *,
    metric: str = "flips",
    title: Optional[str] = None,
) -> Optional[bytes]:
    """Year calendar heatmap PNG. year_entries: {date, flips?, newWrs?}."""
    if not year_entries:
        return None
    try:
        year_i = int(year)
    except ValueError:
        return None

    by_date: Dict[str, float] = {}
    for entry in year_entries:
        d = entry.get("date") or ""
        if not d.startswith(year):
            continue
        val = entry.get(metric)
        if val is None:
            val = entry.get("flips" if metric == "flips" else "newWrs", 0)
        by_date[d] = float(val or 0)

    max_v = max(by_date.values()) if by_date else 0
    cell = 14
    gap = 2
    label_w = 28
    month_h = 18
    rows = 7  # Sun..Sat
    # Weeks in year ~53
    cols = 53
    width = label_w + cols * (cell + gap) + 24
    height = month_h + rows * (cell + gap) + 60
    img = Image.new("RGB", (width, height), (24, 28, 36))
    draw = ImageDraw.Draw(img)
    font = _font(12)
    font_sm = _font(10)
    metric_label = "Flips" if metric == "flips" else "New WRs"
    draw.text(
        (12, 8),
        title or f"Activity {year} — {metric_label}",
        fill=(240, 240, 245),
        font=font,
    )

    # Color scale: dark → teal
    def color_for(v: float) -> Tuple[int, int, int]:
        if v <= 0 or max_v <= 0:
            return (40, 46, 56)
        t = min(1.0, v / max_v)
        # interpolate (40,46,56) → (26, 188, 156)
        return (
            int(40 + (26 - 40) * t),
            int(46 + (188 - 46) * t),
            int(56 + (156 - 56) * t),
        )

    # Find first day of year weekday (Mon=0.. in Python; we use Sun=0)
    jan1 = datetime(year_i, 1, 1).date()
    # Python weekday Mon=0; convert to Sun=0
    start_wd = (jan1.weekday() + 1) % 7

    day_labels = ["S", "M", "T", "W", "T", "F", "S"]
    for i, lab in enumerate(day_labels):
        if i % 2 == 1:
            continue
        y = month_h + i * (cell + gap)
        draw.text((6, y), lab, fill=(120, 128, 140), font=font_sm)

    month_drawn = set()
    for day_of_year in range(366 if calendar.isleap(year_i) else 365):
        d = datetime(year_i, 1, 1).date().fromordinal(jan1.toordinal() + day_of_year)
        date_str = d.isoformat()
        wd = (d.weekday() + 1) % 7
        week = (start_wd + day_of_year) // 7
        x = label_w + week * (cell + gap)
        y = month_h + wd * (cell + gap)
        v = by_date.get(date_str, 0)
        draw.rectangle([x, y, x + cell - 1, y + cell - 1], fill=color_for(v))
        if d.day == 1 and d.month not in month_drawn:
            month_drawn.add(d.month)
            draw.text(
                (x, 22),
                calendar.month_abbr[d.month],
                fill=(160, 168, 180),
                font=font_sm,
            )

    # Legend
    legend_y = month_h + rows * (cell + gap) + 12
    draw.text((label_w, legend_y), "Less", fill=(140, 148, 160), font=font_sm)
    lx = label_w + 36
    for i, frac in enumerate((0, 0.25, 0.5, 0.75, 1.0)):
        draw.rectangle(
            [lx + i * (cell + gap), legend_y, lx + i * (cell + gap) + cell - 1, legend_y + cell - 1],
            fill=color_for(frac * max_v if max_v else 0),
        )
    draw.text(
        (lx + 5 * (cell + gap) + 8, legend_y),
        "More",
        fill=(140, 148, 160),
        font=font_sm,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
