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
from zoneinfo import ZoneInfo


AI_MIN_CALENDAR_DAYS = 10
AI_MAX_CALENDAR_DAYS = 90
AI_CHECKPOINT_CALENDAR_DAYS = (30, 60, 90)
AI_MAX_DAYS_BEFORE_ENTRY = 5
_MARKET_TZ = ZoneInfo("America/New_York")

# Only these provider states may enter Tara's factual ledger. Provider messages
# can contain operational detail (and are not a trusted prose source), so each
# code maps to release-owned copy. Unknown codes collapse to the generic state.
_UNAVAILABLE_REASON_BY_CODE = {
    "vix_blocked": "Volatility safety gate is active.",
    "pattern_profile_unavailable": (
        "No qualifying, complete recalculated pattern profile is available for this horizon."
    ),
    "pattern_definitions_unavailable": (
        "The recalculated pattern profile is unavailable for this horizon."
    ),
    "selected_recurrence_insufficient_history": (
        "The selected recurrence does not have enough completed history at this horizon."
    ),
    "nonfinite_pattern_profile": (
        "The recalculated pattern profile is unavailable for this horizon."
    ),
    "prebuilt_profile_mismatch": (
        "The recalculated pattern profile is unavailable for this horizon."
    ),
    "target_entry_unavailable": (
        "A valid price entry could not be established for this horizon."
    ),
    "invalid_checkpoint_context": "The AI context is unavailable for this pattern.",
    "tier_unavailable": "The matching model tier is temporarily unavailable.",
    "context_scoring_failed": "Current-condition scoring is temporarily unavailable.",
    "provider_unavailable": "Current-condition scoring is temporarily unavailable.",
}


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


def _market_today(
    now: Optional[_datetime.datetime] = None,
) -> _datetime.date:
    """Return the New York market date, independent of the server timezone."""

    instant = now or _datetime.datetime.now(_datetime.timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=_datetime.timezone.utc)
    return instant.astimezone(_MARKET_TZ).date()


def build_analysis_score_plan(
    wave_viewer: Any,
    *,
    today: Optional[_datetime.date] = None,
) -> Optional[Dict[str, Any]]:
    """Return a validated score plan for one loaded pattern.

    The current like-for-like score remains primary through 90 displayed calendar
    days. Patterns over 30 days also receive supported shorter comparisons. A longer
    pattern receives 30/60/90 checkpoints, none labeled as its full-window score.
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
        or not 1 <= calendar_days <= 367
        or direction_text not in {"long", "short"}
    ):
        return None
    try:
        entry_date = _datetime.datetime.strptime(entry_text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None

    mode = "duration_comparison" if calendar_days > 30 else "pattern"
    base = {
        "mode": mode,
        "full_pattern_calendar_days": calendar_days,
        "entry_date": entry_text,
    }
    current_date = today or _market_today()
    days_to_entry = (entry_date - current_date).days
    if days_to_entry > AI_MAX_DAYS_BEFORE_ENTRY:
        return {**base, "status": "too_early", "days_to_entry": days_to_entry}
    if days_to_entry < 0:
        return {**base, "status": "after_entry"}
    if calendar_days < AI_MIN_CALENDAR_DAYS:
        return {**base, "status": "unsupported_duration"}

    horizons: Sequence[int]
    if mode == "duration_comparison" and calendar_days > AI_MAX_CALENDAR_DAYS:
        horizons = AI_CHECKPOINT_CALENDAR_DAYS
    elif mode == "duration_comparison":
        # The context scorer supplies the shorter standard horizons; this exact
        # opportunity keeps the current duration as Tara's primary reading.
        horizons = (calendar_days,)
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


def _clean_unavailable(raw: Any) -> Optional[Dict[str, str]]:
    """Return a bounded, release-owned unavailable reason from a scorer result."""

    if not isinstance(raw, Mapping):
        return None
    error = raw.get("error")
    error = error if isinstance(error, Mapping) else {}
    raw_status = str(raw.get("status") or "").strip().lower()
    if raw_status != "unavailable" and not error and raw.get("vix_blocked") is not True:
        return None
    code = str(error.get("code") or "").strip().lower()
    if raw.get("vix_blocked") is True:
        code = "vix_blocked"
    if code not in _UNAVAILABLE_REASON_BY_CODE:
        code = "provider_unavailable"
    return {
        "status": "unavailable",
        "error_code": code,
        "unavailable_reason": _UNAVAILABLE_REASON_BY_CODE[code],
    }


def _clean_selected_recurrence(raw: Any) -> Optional[Dict[str, Any]]:
    """Allowlist selected-screen evidence without making it score eligibility."""

    if not isinstance(raw, Mapping):
        return None
    recurrence = raw.get("selected_recurrence")
    if not isinstance(recurrence, Mapping):
        return None
    status = str(recurrence.get("status") or "").strip().lower()
    if status not in {
        "qualified",
        "below_threshold",
        "insufficient_history",
        "not_enforced",
    }:
        return None
    sample_size = _integer(recurrence.get("sample_size"))
    positive_years = _integer(recurrence.get("positive_years"))
    required_years = _integer(recurrence.get("required_positive_years"))
    requested = _integer(recurrence.get("requested_observations"))
    if (
        sample_size is None
        or sample_size < 0
        or positive_years is None
        or not 0 <= positive_years <= sample_size
        or requested is None
        or requested <= 0
        or requested < sample_size
        or (
            required_years is not None
            and not 1 <= required_years <= requested
        )
    ):
        return None
    if (
        status == "below_threshold"
        and (
            required_years is None
            or sample_size < requested
            or positive_years >= required_years
        )
    ):
        return None
    if (
        status == "qualified"
        and (
            required_years is None
            or sample_size < requested
            or positive_years < required_years
        )
    ):
        return None
    if status == "insufficient_history" and sample_size >= requested:
        return None
    cleaned: Dict[str, Any] = {
        "selected_recurrence_status": status,
        "positive_years": positive_years,
        "sample_size": sample_size,
        "requested_observations": requested,
    }
    if required_years is not None:
        cleaned["required_positive_years"] = required_years
    return cleaned


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
    if mode not in {"pattern", "duration_comparison", "checkpoints"} or full_days is None:
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
    available_count = 0
    for opportunity in plan.get("opportunities") or ():
        if not isinstance(opportunity, Mapping):
            continue
        calendar_days = _integer(opportunity.get("calendar_days"))
        score_key = str(opportunity.get("score_key") or "")
        raw_score = score_map.get(score_key)
        score = _clean_score(raw_score)
        if calendar_days is None:
            continue
        if score is not None:
            horizons.append({"calendar_days": calendar_days, **score})
            available_count += 1
            continue
        unavailable = _clean_unavailable(raw_score)
        if unavailable is not None:
            horizons.append({"calendar_days": calendar_days, **unavailable})

    public["status"] = "available" if available_count else "unavailable"
    if horizons:
        public["horizons"] = horizons
    return public


def finalize_analysis_checkpoint_bundle(
    plan: Any,
    bundle: Any,
) -> Optional[Dict[str, Any]]:
    """Allowlist a recalculated scorer bundle without discarding horizon errors."""

    if not isinstance(plan, Mapping) or not isinstance(bundle, Mapping):
        return finalize_analysis_score_context(plan)
    mode = str(plan.get("mode") or "")
    full_days = _integer(plan.get("full_pattern_calendar_days"))
    if mode not in {"duration_comparison", "checkpoints"} or full_days is None:
        return finalize_analysis_score_context(plan)

    horizons = []
    available_count = 0
    for raw in bundle.get("horizons") or ():
        if not isinstance(raw, Mapping):
            continue
        calendar_days = _integer(raw.get("calendar_days"))
        allowed_days = set(AI_CHECKPOINT_CALENDAR_DAYS)
        if full_days <= AI_MAX_CALENDAR_DAYS:
            allowed_days.add(full_days)
        if calendar_days not in allowed_days or calendar_days > full_days:
            continue
        item: Dict[str, Any] = {"calendar_days": calendar_days}
        if raw.get("is_current") is True:
            item["is_current"] = True
        raw_status = str(raw.get("status") or "").lower()
        if raw_status == "available":
            cleaned = _clean_score(raw)
            if cleaned is None:
                continue
            item.update(cleaned)
            recurrence = _clean_selected_recurrence(raw)
            if recurrence is not None:
                item.update(recurrence)
            item["status"] = "available"
            available_count += 1
        elif raw_status == "below_threshold":
            recurrence = _clean_selected_recurrence(raw)
            if (
                recurrence is None
                or recurrence.get("selected_recurrence_status") != "below_threshold"
                or recurrence.get("required_positive_years") is None
                or recurrence["required_positive_years"] <= recurrence["positive_years"]
            ):
                continue
            item.update(recurrence)
            item["status"] = "below_threshold"
        elif raw_status == "unavailable":
            unavailable = _clean_unavailable(raw)
            if unavailable is None:
                continue
            item.update(unavailable)
        else:
            continue
        horizons.append(item)

    public: Dict[str, Any] = {
        "status": (
            "available"
            if available_count
            else "below_threshold"
            if any(item.get("status") == "below_threshold" for item in horizons)
            else "unavailable"
        ),
        "mode": "duration_comparison",
        "basis": "duration_comparison",
        "checkpoint_status": str(bundle.get("status") or "unavailable"),
        "full_pattern_calendar_days": full_days,
    }
    if horizons:
        public["horizons"] = sorted(
            horizons, key=lambda item: item["calendar_days"]
        )
    return public
