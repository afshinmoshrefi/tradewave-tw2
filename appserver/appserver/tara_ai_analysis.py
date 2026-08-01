"""Build the bounded AI-score context used by Tara's pattern analysis.

TradeWave's chart labels use inclusive calendar-day counts: the entry date is day 1.
The legacy ML scorer still accepts the analytics-engine ``daysOut`` value, so every
request made here converts a displayed N-calendar-day horizon to ``daysOut=N-1``.

This module is intentionally independent of Flask, Redis, and the score provider.  It
builds and validates the score plan; ``appserver.py`` supplies cached/provider results.
"""

from __future__ import annotations

import datetime as _datetime
import math
import re
from typing import Any, Dict, Mapping, Optional, Sequence


AI_MIN_CALENDAR_DAYS = 10
AI_MAX_CALENDAR_DAYS = 90
AI_CHECKPOINT_CALENDAR_DAYS = (30, 60, 90)
AI_MAX_DAYS_BEFORE_ENTRY = 5


def _integer(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _score_key(symbol: str, engine_days_out: int, direction: str) -> str:
    return f"{symbol}|{engine_days_out}|{direction}"


def build_analysis_score_plan(
    wave_viewer: Any,
    *,
    today: Optional[_datetime.date] = None,
) -> Optional[Dict[str, Any]]:
    """Return a validated score plan for one loaded pattern.

    A pattern of 10-90 displayed calendar days receives one like-for-like score.  A
    longer pattern receives 30/60/90-calendar-day checkpoints from the same entry and
    in the same direction.  Those checkpoints are deliberately not represented as a
    score of the full long-duration pattern.
    """

    if not isinstance(wave_viewer, Mapping):
        return None
    symbol = str(wave_viewer.get("symbol") or "").strip().upper()
    entry_text = str(wave_viewer.get("start_date") or "").strip()
    calendar_days = _integer(wave_viewer.get("days_out"))
    direction_text = str(wave_viewer.get("direction") or "").strip().lower()
    if (
        not re.fullmatch(r"[A-Z0-9.$^-]{1,15}", symbol)
        or calendar_days is None
        or not 1 <= calendar_days <= 366
        or direction_text not in {"long", "short"}
    ):
        return None
    try:
        entry_date = _datetime.datetime.strptime(entry_text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None

    mode = "checkpoints" if calendar_days > AI_MAX_CALENDAR_DAYS else "pattern"
    base = {
        "mode": mode,
        "full_pattern_calendar_days": calendar_days,
        "entry_date": entry_text,
    }
    current_date = today or _datetime.date.today()
    days_to_entry = (entry_date - current_date).days
    if days_to_entry > AI_MAX_DAYS_BEFORE_ENTRY:
        return {**base, "status": "too_early", "days_to_entry": days_to_entry}
    if days_to_entry < 0:
        return {**base, "status": "after_entry"}
    if calendar_days < AI_MIN_CALENDAR_DAYS:
        return {**base, "status": "unsupported_duration"}

    horizons: Sequence[int]
    if mode == "checkpoints":
        horizons = AI_CHECKPOINT_CALENDAR_DAYS
    else:
        horizons = (calendar_days,)
    scorer_direction = "s" if direction_text == "short" else "l"
    opportunities = []
    for horizon in horizons:
        # TradeWave calendar-day invariant: entry date is day 1, so the legacy
        # analytics/scorer value is always one less than the displayed horizon.
        engine_days_out = horizon - 1
        opportunities.append(
            {
                "symbol": symbol,
                "date": entry_text,
                "daysOut": engine_days_out,
                "direction": scorer_direction,
                "calendar_days": horizon,
                "score_key": _score_key(symbol, engine_days_out, scorer_direction),
            }
        )
    return {**base, "status": "ready", "opportunities": opportunities}


def _clean_score(raw: Any) -> Optional[Dict[str, float]]:
    if not isinstance(raw, Mapping):
        return None
    ml_score = _number(raw.get("ml_score"))
    win_prob = _number(raw.get("win_prob"))
    pred_return = _number(raw.get("pred_return"))
    pred_mfe = _number(raw.get("pred_mfe"))
    if ml_score is not None and not 0 <= ml_score <= 100:
        ml_score = None
    if win_prob is not None and not 0 <= win_prob <= 1:
        win_prob = None
    if pred_return is not None and not -1000 <= pred_return <= 1000:
        pred_return = None
    if pred_mfe is not None and not -1000 <= pred_mfe <= 1000:
        pred_mfe = None
    cleaned = {
        key: value
        for key, value in (
            ("ai_score", ml_score),
            ("win_probability", win_prob),
            ("predicted_return_pct", pred_return),
            ("predicted_mfe_pct", pred_mfe),
        )
        if value is not None
    }
    return cleaned or None


def finalize_analysis_score_context(
    plan: Any,
    scores_by_key: Any = None,
) -> Optional[Dict[str, Any]]:
    """Turn internal scorer results into Tara's small, allowlisted context."""

    if not isinstance(plan, Mapping):
        return None
    status = str(plan.get("status") or "")
    mode = str(plan.get("mode") or "")
    full_days = _integer(plan.get("full_pattern_calendar_days"))
    if mode not in {"pattern", "checkpoints"} or full_days is None:
        return None
    public = {
        "status": status,
        "mode": mode,
        "full_pattern_calendar_days": full_days,
    }
    if status == "too_early":
        days_to_entry = _integer(plan.get("days_to_entry"))
        if days_to_entry is not None:
            public["days_to_entry"] = days_to_entry
        return public
    if status != "ready":
        return public

    score_map = scores_by_key if isinstance(scores_by_key, Mapping) else {}
    horizons = []
    for opportunity in plan.get("opportunities") or ():
        if not isinstance(opportunity, Mapping):
            continue
        calendar_days = _integer(opportunity.get("calendar_days"))
        score_key = str(opportunity.get("score_key") or "")
        score = _clean_score(score_map.get(score_key))
        if calendar_days is None or score is None:
            continue
        horizons.append({"calendar_days": calendar_days, **score})

    public["status"] = "available" if horizons else "unavailable"
    if horizons:
        public["horizons"] = horizons
    return public
