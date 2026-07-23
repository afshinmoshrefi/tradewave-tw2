"""Render and publish metadata for a deterministic daily-pick social card."""

from __future__ import annotations

import datetime as dt
import html
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps


WIDTH, HEIGHT = 1200, 630
IMAGE_RELPATH_PREFIX = "assets/social"
SOCIAL_META_START = "<!-- daily-pick-social:start -->"
SOCIAL_META_END = "<!-- daily-pick-social:end -->"

SITE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BACKGROUND = SITE_DIR / "static" / "social" / "daily-pick-card-bg.png"
DEFAULT_LOGO = SITE_DIR / "static" / "favicon-white.png"

WHITE = (248, 250, 252)
MUTED = (174, 184, 205)
SUBTLE = (124, 137, 163)
INDIGO = (129, 140, 248)
CYAN = (34, 211, 238)
GREEN = (100, 220, 140)
PANEL = (10, 15, 31, 255)
PANEL_BORDER = (76, 91, 126, 255)

FONT_CANDIDATES = {
    "bold": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ),
    "regular": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ),
}


def _font(style: str, size: int):
    for candidate in FONT_CANDIDATES[style]:
        if os.path.isfile(candidate):
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> dt.date:
    return dt.date.fromisoformat(str(value))


def _friendly_date(value: Any) -> str:
    parsed = _date(value)
    return "%s %d" % (parsed.strftime("%b"), parsed.day)


def _direction(value: Any) -> str:
    return (
        "SHORT"
        if str(value or "").strip().lower() in {"s", "short", "sell"}
        else "LONG"
    )


def _history_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw.isdigit():
        return "%s-YEAR HISTORY" % raw
    match = re.fullmatch(r"pe([0-3])-(\d+)", raw)
    if match:
        phase, samples = match.groups()
        phase_label = "PE" if phase == "0" else "PE+%s" % phase
        return "%s %s SAMPLES" % (samples, phase_label)
    return "HISTORICAL SAMPLE"


def card_filename(pick: Dict[str, Any]) -> str:
    featured_date = _date(pick["featured_date"]).isoformat()
    symbol = str(pick.get("symbol") or "pick").strip().lower()
    safe_symbol = "".join(ch for ch in symbol if ch.isalnum() or ch in "-.")
    return "daily-pick-%s-%s.png" % (featured_date, safe_symbol or "pick")


def card_relative_path(pick: Dict[str, Any]) -> str:
    return "%s/%s" % (IMAGE_RELPATH_PREFIX, card_filename(pick))


def card_alt_text(pick: Dict[str, Any]) -> str:
    symbol = str(pick.get("symbol") or "").strip().upper()
    probability = _number(pick.get("win_prob"))
    if probability is not None and 0 <= probability <= 1:
        probability *= 100
    suffix = (
        " with %.0f%% estimated win probability" % probability
        if probability is not None
        else ""
    )
    return "TradeWave daily AI pick: %s%s" % (symbol, suffix)


def social_metadata(pick: Dict[str, Any], domain_root: str) -> Dict[str, str]:
    domain_root = domain_root.rstrip("/") + "/"
    symbol = str(pick.get("symbol") or "").strip().upper()
    days = int(pick.get("daysOut") or 0)
    probability = _number(pick.get("win_prob"))
    if probability is not None and 0 <= probability <= 1:
        probability *= 100
    probability_copy = (
        " with %.0f%% estimated win probability" % probability
        if probability is not None
        else ""
    )
    return {
        "title": "TradeWave AI Pick: $%s" % symbol,
        "description": (
            "%s seasonal window, %d days%s. See every pick and outcome "
            "in the public ledger."
        )
        % (_direction(pick.get("direction")).title(), days, probability_copy),
        "image_url": domain_root + card_relative_path(pick),
        "image_alt": card_alt_text(pick),
        "page_url": domain_root
        + "scorecard.html?pick="
        + _date(pick["featured_date"]).isoformat(),
    }


def social_meta_block(metadata: Dict[str, str]) -> str:
    values = {key: html.escape(value, quote=True) for key, value in metadata.items()}
    return "\n".join(
        [
            SOCIAL_META_START,
            '<meta property="og:title" content="%s">' % values["title"],
            '<meta property="og:description" content="%s">' % values["description"],
            '<meta property="og:url" content="%s">' % values["page_url"],
            '<meta property="og:image" content="%s">' % values["image_url"],
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            '<meta property="og:image:alt" content="%s">' % values["image_alt"],
            '<meta name="twitter:card" content="summary_large_image">',
            '<meta name="twitter:title" content="%s">' % values["title"],
            '<meta name="twitter:description" content="%s">' % values["description"],
            '<meta name="twitter:image" content="%s">' % values["image_url"],
            '<meta name="twitter:image:alt" content="%s">' % values["image_alt"],
            SOCIAL_META_END,
        ]
    )


def _draw_stat(draw, box, value, label, color):
    draw.rounded_rectangle(
        box, radius=16, fill=PANEL, outline=PANEL_BORDER, width=1
    )
    draw.text((box[0] + 20, box[1] + 15), value, font=_font("bold", 28), fill=color)
    draw.text(
        (box[0] + 20, box[1] + 54),
        label,
        font=_font("regular", 13),
        fill=MUTED,
    )


def generate_daily_pick_card(
    pick: Dict[str, Any],
    output_root: str | Path,
    background_path: str | Path = DEFAULT_BACKGROUND,
    logo_path: str | Path = DEFAULT_LOGO,
) -> Path:
    output_root = Path(output_root)
    output_path = output_root / card_relative_path(pick)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    background = Image.open(background_path).convert("RGB")
    card = ImageOps.fit(
        background, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS
    ).convert("RGBA")
    shade = Image.new("RGBA", card.size, (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    for x in range(820):
        alpha = int(176 * (1 - (x / 820.0) ** 2))
        shade_draw.line([(x, 0), (x, HEIGHT)], fill=(3, 5, 15, alpha))
    card = Image.alpha_composite(card, shade)
    draw = ImageDraw.Draw(card)

    symbol = str(pick.get("symbol") or "").strip().upper()
    featured_date = _friendly_date(pick["featured_date"]).upper()
    direction = _direction(pick.get("direction"))
    days = int(pick.get("daysOut") or 0)
    start_date = _date(pick["date"])
    end_value = pick.get("end_date") or (
        start_date + dt.timedelta(days=days)
    ).isoformat()
    window = "%s - %s  /  %d DAYS" % (
        _friendly_date(start_date.isoformat()).upper(),
        _friendly_date(end_value).upper(),
        days,
    )
    probability = _number(pick.get("win_prob"))
    if probability is not None and 0 <= probability <= 1:
        probability *= 100
    avg_profit = _number(pick.get("avg_profit"))
    sharpe = _number(pick.get("sharpe_ratio"))

    logo = Image.open(logo_path).convert("RGBA")
    logo.thumbnail((42, 42), Image.Resampling.LANCZOS)
    card.alpha_composite(logo, (64, 47))
    draw.text((120, 52), "TRADEWAVE AI", font=_font("bold", 21), fill=WHITE)
    draw.text(
        (120, 79),
        "PUBLIC, FORWARD-TRACKED RESEARCH",
        font=_font("regular", 12),
        fill=MUTED,
    )
    draw.rounded_rectangle(
        (432, 48, 586, 83),
        radius=17,
        fill=(31, 32, 70, 255),
        outline=(95, 99, 190, 255),
    )
    draw.text(
        (454, 58),
        "DAILY PICK  /  %s" % featured_date,
        font=_font("bold", 11),
        fill=INDIGO,
    )

    draw.text((62, 132), "TODAY'S AI PICK", font=_font("bold", 16), fill=CYAN)
    draw.text(
        (58, 155),
        "$%s" % symbol,
        font=_font("bold", 104),
        fill=WHITE,
        stroke_width=1,
    )
    draw.rounded_rectangle(
        (64, 282, 190, 319),
        radius=18,
        fill=(16, 51, 42, 255),
        outline=(62, 163, 110, 255),
    )
    draw.text((89, 292), direction, font=_font("bold", 14), fill=GREEN)
    draw.text(
        (211, 291), "SEASONAL WINDOW", font=_font("bold", 14), fill=MUTED
    )
    draw.text((64, 337), window, font=_font("bold", 23), fill=WHITE)
    draw.text(
        (64, 373),
        _history_label(pick.get("years")),
        font=_font("regular", 13),
        fill=SUBTLE,
    )

    _draw_stat(
        draw,
        (62, 420, 250, 508),
        "%.0f%%" % probability if probability is not None else "--",
        "EST. WIN PROBABILITY",
        GREEN,
    )
    _draw_stat(
        draw,
        (266, 420, 454, 508),
        "%+.1f%%" % avg_profit if avg_profit is not None else "--",
        "HISTORICAL AVG",
        CYAN,
    )
    _draw_stat(
        draw,
        (470, 420, 658, 508),
        "%.2f" % sharpe if sharpe is not None else "--",
        "SHARPE RATIO",
        INDIGO,
    )
    draw.line((64, 552, 658, 552), fill=(113, 128, 160, 255), width=1)
    draw.text(
        (64, 572),
        "FULL HISTORY + EVERY OUTCOME",
        font=_font("bold", 12),
        fill=WHITE,
    )
    draw.text(
        (315, 572),
        "tradewave.ai/scorecard",
        font=_font("regular", 12),
        fill=CYAN,
    )
    draw.text(
        (64, 596),
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


def refresh_scorecard_social_meta(
    pick: Dict[str, Any], output_root: str | Path, domain_root: str
) -> Dict[str, str]:
    output_root = Path(output_root)
    generate_daily_pick_card(pick, output_root)
    metadata = social_metadata(pick, domain_root)
    scorecard_path = output_root / "scorecard.html"
    source = scorecard_path.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(SOCIAL_META_START) + r".*?" + re.escape(SOCIAL_META_END),
        re.DOTALL,
    )
    updated, count = pattern.subn(social_meta_block(metadata), source)
    if count != 1:
        raise RuntimeError(
            "scorecard social metadata block is missing or duplicated (found %d)"
            % count
        )
    temporary = scorecard_path.with_name(".scorecard.html.social.tmp")
    try:
        temporary.write_text(updated, encoding="utf-8")
        os.replace(temporary, scorecard_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    try:
        scorecard_path.chmod(0o644)
    except OSError:
        pass
    return metadata
