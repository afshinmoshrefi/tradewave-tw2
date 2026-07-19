"""Small, deterministic TradeWave chart renderer for MCP image content.

The gateway remains the source of every number.  This module only turns the
PatternCard's derived chart data into branded PNGs; it never reads prices or calls
another service.  Rendering in the MCP process avoids browser screenshots and keeps
the images consistent across ChatGPT, Claude, and other MCP clients.
"""

from __future__ import annotations

import io
import math
from typing import Any

from PIL import Image, ImageDraw, ImageFont


_BG = "#07111f"
_PANEL = "#0d1a2b"
_GRID = "#334155"
_TEXT = "#e5edf7"
_MUTED = "#9fb0c5"
_BLUE = "#3385e5"
_BLUE_FILL = "#163d70"
_ORANGE = "#ff7b39"
_GREEN = "#32c48d"
_RED = "#f15b64"


def _font(size: int, bold: bool = False):
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _canvas(title: str, subtitle: str, width: int, height: int):
    image = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((14, 14, width - 14, height - 14), 16, fill=_PANEL)
    draw.text((38, 28), title, font=_font(24, True), fill=_TEXT)
    draw.text((38, 62), subtitle, font=_font(13), fill=_MUTED)
    return image, draw


def _number(v: Any) -> float | None:
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def render_trend_chart(card: dict[str, Any]) -> bytes | None:
    chart = card.get("chart") or {}
    points = [
        (str(p.get("date") or ""), _number(p.get("index")))
        for p in (chart.get("trend_chart") or [])
        if isinstance(p, dict) and _number(p.get("index")) is not None
    ]
    if len(points) < 2:
        return None

    symbol = str(card.get("symbol") or "Pattern")
    setup = card.get("setup") or {}
    hold = int(setup.get("hold_days") or 0)
    title = f"{symbol} seasonal trend"
    subtitle = (
        "Normalized TradeWave seasonal index (0-100), not a price. "
        f"Highlighted window: {setup.get('entry_date') or '?'} to {setup.get('exit_date') or '?'}"
    )
    width, height = 960, 430
    image, draw = _canvas(title, subtitle, width, height)
    left, top, right, bottom = 72, 112, width - 34, height - 58
    values = [p[1] for p in points if p[1] is not None]
    lo, hi = min(values), max(values)
    pad = max(2.0, (hi - lo) * 0.12)
    lo, hi = max(0.0, lo - pad), min(100.0, hi + pad)
    if hi <= lo:
        hi = lo + 1.0

    def xy(i: int, value: float):
        x = left + (right - left) * i / max(1, len(points) - 1)
        y = bottom - (bottom - top) * (value - lo) / (hi - lo)
        return x, y

    for j in range(5):
        value = lo + (hi - lo) * j / 4
        y = xy(0, value)[1]
        draw.line((left, y, right, y), fill=_GRID, width=1)
        draw.text((22, y - 8), f"{value:.0f}", font=_font(12), fill=_MUTED)

    hold_last = min(max(hold, 1), len(points) - 1)
    hx = xy(hold_last, points[hold_last][1])[0]
    draw.rectangle((left, top, hx, bottom), fill=_BLUE_FILL)
    coords = [xy(i, value) for i, (_, value) in enumerate(points)]
    draw.line(coords, fill=_BLUE, width=4, joint="curve")
    draw.line((left, top, left, bottom), fill=_ORANGE, width=2)
    draw.line((hx, top, hx, bottom), fill=_ORANGE, width=2)

    label_indices = sorted({0, hold_last, len(points) - 1, len(points) // 2})
    for i in label_indices:
        x, _ = coords[i]
        label = points[i][0][5:] if len(points[i][0]) >= 10 else points[i][0]
        draw.text((x - 22, bottom + 14), label, font=_font(11), fill=_MUTED)
    draw.text((left + 8, top + 8), "ENTRY", font=_font(11, True), fill=_ORANGE)
    draw.text((max(left + 60, hx - 34), top + 8), "EXIT", font=_font(11, True), fill=_ORANGE)
    return _png(image)


def render_year_evidence_chart(card: dict[str, Any]) -> bytes | None:
    chart = card.get("chart") or {}
    rows = [r for r in (chart.get("per_year_bars") or []) if isinstance(r, dict)]
    if not rows:
        return None

    symbol = str(card.get("symbol") or "Pattern")
    direction = str(card.get("direction") or "long").upper()
    title = f"{symbol} year-by-year evidence"
    subtitle = (
        f"{direction} trade return (diamond) with favorable/adverse excursion range. "
        "All values are percentages."
    )
    width, height = 960, 470
    image, draw = _canvas(title, subtitle, width, height)
    left, top, right, bottom = 72, 112, width - 34, height - 62

    values = [0.0]
    for row in rows:
        values.extend(v for v in (
            _number(row.get("net_pct")), _number(row.get("mfe_pct")), _number(row.get("mae_pct"))
        ) if v is not None)
    lo, hi = min(values), max(values)
    pad = max(1.0, (hi - lo) * 0.12)
    lo, hi = lo - pad, hi + pad
    if hi <= lo:
        hi = lo + 1.0

    def y(value: float):
        return bottom - (bottom - top) * (value - lo) / (hi - lo)

    for j in range(5):
        value = lo + (hi - lo) * j / 4
        yy = y(value)
        draw.line((left, yy, right, yy), fill=_GRID, width=1)
        draw.text((18, yy - 8), f"{value:+.0f}%", font=_font(12), fill=_MUTED)
    zero_y = y(0.0)
    draw.line((left, zero_y, right, zero_y), fill=_TEXT, width=1)

    step = (right - left) / max(1, len(rows))
    for i, row in enumerate(rows):
        x = left + step * (i + 0.5)
        net = _number(row.get("net_pct")) or 0.0
        mfe = _number(row.get("mfe_pct"))
        mae = _number(row.get("mae_pct"))
        if mfe is not None and mae is not None:
            draw.line((x, y(mfe), x, y(mae)), fill=_BLUE, width=max(5, int(step * 0.26)))
        yy = y(net)
        diamond = [(x, yy - 8), (x + 8, yy), (x, yy + 8), (x - 8, yy)]
        draw.polygon(diamond, fill=_GREEN if net > 0 else _RED)
        label = str(row.get("year") or "")
        draw.text((x - 16, bottom + 16), label, font=_font(11), fill=_MUTED)
    return _png(image)


def render_card_charts(card: dict[str, Any]) -> list[tuple[str, bytes]]:
    """Return chart title/PNG pairs in the recommended evidence order."""
    rendered: list[tuple[str, bytes]] = []
    year_chart = render_year_evidence_chart(card)
    if year_chart:
        rendered.append(("TradeWave year-by-year evidence", year_chart))
    trend_chart = render_trend_chart(card)
    if trend_chart:
        rendered.append(("TradeWave seasonal trend", trend_chart))
    return rendered
