"""Generate the branded, date-specific close-ledger X link card."""

from __future__ import annotations

import datetime as dt
import html
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

from PIL import Image, ImageDraw, ImageOps

from daily_pick_social_card import (
    CYAN,
    DEFAULT_BACKGROUND,
    GREEN,
    HEIGHT,
    INDIGO,
    MUTED,
    PANEL,
    PANEL_BORDER,
    SUBTLE,
    WEEKDAY_BACKGROUNDS,
    WHITE,
    WIDTH,
    _font,
)
from pick_stats import is_win, reached_target


RED = (248, 113, 113)


def _date(value: Any) -> dt.date:
    return dt.date.fromisoformat(str(value))


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(value: Any) -> str:
    return "%+.1f%%" % _number(value)


def close_card_relative_path(market_date: str) -> str:
    return "assets/social/daily-close-%s.png" % _date(market_date).isoformat()


def close_page_relative_path(market_date: str) -> str:
    return "close-ledger/%s.html" % _date(market_date).isoformat()


def close_page_url(market_date: str, domain_root: str) -> str:
    return domain_root.rstrip("/") + "/" + close_page_relative_path(market_date)


def _result_label(entry: Dict[str, Any]) -> str:
    if reached_target(entry):
        return "TARGET HIT %s  |  CLOSE %s" % (
            _pct(entry.get("pred_return")),
            _pct(entry.get("actual_return")),
        )
    if is_win(entry):
        return "PROFITABLE CLOSE %s  |  TARGET NOT HIT" % _pct(
            entry.get("actual_return")
        )
    return "PEAK %s  |  TARGET %s MISSED  |  CLOSE %s" % (
        _pct(entry.get("peak_return")),
        _pct(entry.get("pred_return")),
        _pct(entry.get("actual_return")),
    )


def generate_close_card(
    entries: Iterable[Dict[str, Any]],
    market_date: str,
    output_root: str | Path,
) -> Path:
    rows = list(entries)
    parsed_date = _date(market_date)
    output_path = Path(output_root) / close_card_relative_path(market_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    background_path = WEEKDAY_BACKGROUNDS.get(
        parsed_date.weekday(), DEFAULT_BACKGROUND
    )
    background = Image.open(background_path).convert("RGB")
    card = ImageOps.fit(
        background, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS
    ).convert("RGBA")
    overlay = Image.new("RGBA", card.size, (3, 6, 18, 174))
    card = Image.alpha_composite(card, overlay)
    draw = ImageDraw.Draw(card)

    wins = sum(1 for entry in rows if is_win(entry))
    losses = len(rows) - wins
    date_label = parsed_date.strftime("%b %d, %Y").upper()

    draw.text((62, 46), "TRADEWAVE AI", font=_font("bold", 21), fill=WHITE)
    draw.text(
        (62, 76),
        "PUBLIC, FORWARD-TRACKED RESEARCH",
        font=_font("regular", 12),
        fill=MUTED,
    )
    draw.text((62, 123), "CLOSE LEDGER", font=_font("bold", 48), fill=WHITE)
    draw.text((62, 181), date_label, font=_font("bold", 17), fill=CYAN)

    summary = "%d WINDOW%s CLOSED   •   %d WIN%s   •   %d LOSS%s" % (
        len(rows),
        "" if len(rows) == 1 else "S",
        wins,
        "" if wins == 1 else "S",
        losses,
        "" if losses == 1 else "ES",
    )
    draw.rounded_rectangle(
        (62, 221, 1138, 272),
        radius=16,
        fill=PANEL,
        outline=PANEL_BORDER,
        width=1,
    )
    draw.text((86, 236), summary, font=_font("bold", 17), fill=INDIGO)

    visible_rows = rows[:6]
    row_height = 48 if len(visible_rows) >= 5 else 57
    y = 294
    for entry in visible_rows:
        won = is_win(entry)
        accent = GREEN if won else RED
        symbol = str(entry.get("symbol") or "").upper()
        draw.rounded_rectangle(
            (62, y, 1138, y + row_height - 7),
            radius=12,
            fill=(8, 13, 28, 225),
            outline=(52, 65, 94, 255),
            width=1,
        )
        draw.text(
            (82, y + 9),
            "WIN" if won else "LOSS",
            font=_font("bold", 15),
            fill=accent,
        )
        draw.text((160, y + 7), symbol, font=_font("bold", 21), fill=WHITE)
        draw.text(
            (315, y + 10),
            _result_label(entry),
            font=_font("regular", 15),
            fill=MUTED,
        )
        y += row_height

    if len(rows) > len(visible_rows):
        draw.text(
            (82, y + 2),
            "+ %d more in the public ledger" % (len(rows) - len(visible_rows)),
            font=_font("regular", 14),
            fill=SUBTLE,
        )

    draw.line((62, 570, 1138, 570), fill=(113, 128, 160, 255), width=1)
    draw.text(
        (62, 591),
        "FULL HISTORY: TRADEWAVE.AI/SCORECARD",
        font=_font("bold", 13),
        fill=WHITE,
    )
    draw.text(
        (830, 591),
        "Research only. Not financial advice.",
        font=_font("regular", 11),
        fill=SUBTLE,
    )

    temporary = output_path.with_name(".%s.tmp" % output_path.name)
    try:
        card.convert("RGB").save(temporary, format="PNG", optimize=True)
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    try:
        output_path.chmod(0o644)
    except OSError:
        pass
    return output_path


def _page_rows(entries: List[Dict[str, Any]]) -> str:
    rendered = []
    for entry in entries:
        verdict = "WIN" if is_win(entry) else "LOSS"
        rendered.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                html.escape(str(entry.get("symbol") or "").upper()),
                verdict,
                html.escape(_result_label(entry)),
            )
        )
    return "\n".join(rendered)


def generate_close_page(
    entries: Iterable[Dict[str, Any]],
    market_date: str,
    output_root: str | Path,
    domain_root: str,
) -> Path:
    rows = list(entries)
    parsed_date = _date(market_date)
    wins = sum(1 for entry in rows if is_win(entry))
    losses = len(rows) - wins
    page_url = close_page_url(market_date, domain_root)
    image_url = (
        domain_root.rstrip("/") + "/" + close_card_relative_path(market_date)
    )
    title = "TradeWave Close Ledger — %s" % parsed_date.strftime("%b %d, %Y")
    description = "%d AI windows closed: %d wins, %d losses." % (
        len(rows),
        wins,
        losses,
    )
    escaped = {
        "title": html.escape(title, quote=True),
        "description": html.escape(description, quote=True),
        "page_url": html.escape(page_url, quote=True),
        "image_url": html.escape(image_url, quote=True),
    }
    document = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{page_url}">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{page_url}">
<meta property="og:image" content="{image_url}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{image_url}">
<style>
body{{margin:0;background:#050814;color:#f8fafc;font:16px system-ui,sans-serif}}
main{{max-width:900px;margin:48px auto;padding:0 24px}}
h1{{font-size:42px;margin-bottom:8px}}p{{color:#aeb8cd}}
table{{width:100%;border-collapse:collapse;margin:28px 0}}
td{{padding:16px;border-bottom:1px solid #25304a}}
a{{color:#22d3ee}}
</style></head><body><main>
<h1>{title}</h1><p>{description}</p>
<table><tbody>{rows}</tbody></table>
<p><a href="/scorecard.html">See every daily pick and outcome →</a></p>
<p>Research only. Not financial advice.</p>
</main></body></html>
""".format(rows=_page_rows(rows), **escaped)

    output_path = Path(output_root) / close_page_relative_path(market_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(".%s.tmp" % output_path.name)
    try:
        temporary.write_text(document, encoding="utf-8")
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    try:
        output_path.chmod(0o644)
    except OSError:
        pass
    return output_path


def generate_close_assets(
    entries: Iterable[Dict[str, Any]],
    market_date: str,
    output_root: str | Path,
    domain_root: str,
) -> Dict[str, str]:
    rows = list(entries)
    image_path = generate_close_card(rows, market_date, output_root)
    page_path = generate_close_page(
        rows, market_date, output_root, domain_root
    )
    return {
        "image_path": str(image_path),
        "page_path": str(page_path),
        "page_url": close_page_url(market_date, domain_root),
    }
