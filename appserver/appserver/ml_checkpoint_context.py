"""V3 scorer orchestration for recalculated duration comparisons.

The V3 scorer owns model-faithful pattern-profile construction. TradeWave sends
only an immutable pattern identity plus UI provenance. In particular, this
module must never synthesize the scorer's learned pattern features from the
user-selected historical cohort.

TradeWave windows are inclusive calendar windows: a displayed N-day checkpoint
ends on entry + (N - 1), and the legacy analytics offset is N - 1. The scorer
accepts calendar_days and derives that offset itself.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import re
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


CACHE_SCHEMA_VERSION = "ml6"
CONTEXT_CONTRACT_VERSION = "tw2-duration-comparison-v2"
CHECKPOINT_CALENDAR_DAYS = (30, 60, 90)
ALLOWED_RESOURCE_IDS = frozenset({"0", "1", "2", "3", "4", "11"})
USAGE_MAX_STORED_ROWS = 100
USAGE_RETENTION_SECONDS = 21 * 24 * 60 * 60

DEFAULT_CONSECUTIVE_CONTEXTS = {
    "0": ("10", "8"),
    "1": ("10", "8"),
    "2": ("10", "9"),
    "3": ("10", "9"),
    "4": ("10", "9"),
    "11": ("10", "8"),
}
DEFAULT_PE_CONTEXT = ("6", "6")

_SYMBOL_RE = re.compile(r"^[A-Z0-9.$^-]{1,15}$")
_PE_YEARS_RE = re.compile(r"^pe([0-3])-([1-9][0-9]*)$", re.I)
_DAY_RANGE_RE = re.compile(r"^([1-9][0-9]{0,2})-([1-9][0-9]{0,2})$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_METADATA_FIELDS = (
    "model_release",
    "feature_schema_version",
    "feature_schema_hash",
    "context_schema_version",
    "pattern_profile_schema_version",
    "model_manifest_hash",
    "data_as_of",
    "data_generation_hash",
    "data_source_manifest_hash",
    "context_data_complete",
)

_LEGACY_UNAVAILABLE_COPY = {
    "vix_blocked": "Volatility safety gate is active.",
    "target_entry_unavailable": "A valid price entry could not be established for this date.",
    "target_price_unavailable": "Price history is not available for this ticker.",
    "pattern_profile_unavailable": "No qualifying historical profile is available for this horizon.",
    "selected_recurrence_insufficient_history": "The selected recurrence does not have enough completed history at this horizon.",
    "pattern_definitions_unavailable": "Historical pattern definitions are unavailable for this horizon.",
    "nonfinite_pattern_profile": "The historical profile is incomplete for this horizon.",
    "prebuilt_profile_mismatch": "The historical profile could not be verified for this horizon.",
    "incomplete_feature_vector": "The historical profile is incomplete for this horizon.",
    "tier_unavailable": "The model tier is temporarily unavailable.",
    "context_scoring_failed": "Current-condition scoring is temporarily unavailable.",
    "provider_unavailable": "Current-condition scoring is temporarily unavailable.",
}


class CheckpointContextError(ValueError):
    """The caller supplied an invalid or incomplete pattern identity."""


class CheckpointProviderError(RuntimeError):
    """The scorer returned a response that cannot safely be cached or displayed."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CheckpointContextError("provenance must be finite JSON data") from exc


def _hash_payload(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _redis_json(raw: Any) -> Optional[Any]:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError):
        return None


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise CheckpointContextError(f"{field} must be an integer")
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise CheckpointContextError(f"{field} must be an integer") from exc
    if not math.isfinite(number) or not number.is_integer():
        raise CheckpointContextError(f"{field} must be an integer")
    return int(number)


def _direction(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"l", "long"}:
        return "l"
    if text in {"s", "short"}:
        return "s"
    raise CheckpointContextError("direction must be l/long or s/short")


def _entry_date(value: Any) -> dt.date:
    try:
        return dt.datetime.strptime(str(value or ""), "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise CheckpointContextError("date must use YYYY-MM-DD") from exc


def _json_safe(value: Any) -> Any:
    """Return an independent, bounded JSON value for cache identity/provenance."""

    encoded = _canonical_json(value)
    if len(encoded) > 4096:
        raise CheckpointContextError("partial provenance is too large")
    return json.loads(encoded)


def _mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "pe" if text in {"pe", "pe0", "pe1", "pe2", "pe3"} else "consecutive"


def _statistical_partial(value: Any, *, mode: str) -> Any:
    """Allowlist recurrence-selection data before scorer/cache/telemetry use.

    ``partial`` comes from an authenticated browser, not a trusted server.  It
    may identify the selected historical cohort, but it must never become a
    place to persist user identity, tokens, free text, or selection-origin
    telemetry.  Older clients sent the winning-year threshold as a scalar or
    under one of three field names, so those shapes remain compatible.
    """

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        selected = None
        for field in ("min_winning_years", "partialYears", "year2"):
            if value.get(field) not in (None, ""):
                selected = value[field]
                break
        result: Dict[str, Any] = {}
        if selected is not None:
            winning_years = _integer(selected, "min_winning_years")
            if not 1 <= winning_years <= 100:
                raise CheckpointContextError(
                    "min_winning_years must be between 1 and 100"
                )
            result["min_winning_years"] = str(winning_years)
        if isinstance(value.get("enabled"), bool):
            result["enabled"] = value["enabled"]
        result["mode"] = _mode(value.get("mode") or mode)
        return result
    if isinstance(value, (str, int, float)):
        winning_years = _integer(value, "min_winning_years")
        if not 1 <= winning_years <= 100:
            raise CheckpointContextError(
                "min_winning_years must be between 1 and 100"
            )
        return str(winning_years)
    raise CheckpointContextError("partial must contain recurrence-selection data")


def _sanitized_table_context(value: Any) -> Dict[str, Any]:
    """Return only bounded statistical fields used by the warm-selection policy."""

    source = value if isinstance(value, Mapping) else {}
    result: Dict[str, Any] = {}
    mode = _mode(source.get("mode"))
    if source.get("years") is not None:
        years = source["years"]
        if not isinstance(years, str):
            raise CheckpointContextError("years must be a string")
        years = years.strip().lower()
        if not years or len(years) > 32:
            raise CheckpointContextError("years must be a nonempty string")
        result["years"] = years
    result["partial"] = _statistical_partial(source.get("partial"), mode=mode)
    result["mode"] = mode

    if source.get("date") not in (None, ""):
        result["date"] = _entry_date(source["date"]).isoformat()
    day_range = str(source.get("day_range") or "-").strip()
    if day_range == "-":
        result["day_range"] = day_range
    else:
        match = _DAY_RANGE_RE.fullmatch(day_range)
        if not match:
            raise CheckpointContextError("day_range must be '-' or start-end")
        start, end = (int(match.group(1)), int(match.group(2)))
        if not 1 <= start <= end <= 367:
            raise CheckpointContextError("day_range is outside the supported range")
        result["day_range"] = f"{start}-{end}"
    if isinstance(source.get("is_default"), bool):
        result["is_default"] = source["is_default"]
    return result


def _years_identity(value: Any, mode: str, entry: dt.date) -> Tuple[str, str]:
    if not isinstance(value, str):
        raise CheckpointContextError("years must be a string")
    requested = value.strip().lower()
    if not requested or len(requested) > 32:
        raise CheckpointContextError("years must be a nonempty string")
    pe_match = _PE_YEARS_RE.fullmatch(requested)
    if pe_match:
        return requested, requested
    if not requested.isdigit() or int(requested) <= 0:
        raise CheckpointContextError(
            'years must be a plain lookback such as "20" or a cycle slice such as "pe2-10"'
        )
    if mode == "pe":
        return f"pe{entry.year % 4}-{requested}", requested
    return requested, requested


def _partial_provenance(
    opportunity: Mapping[str, Any],
    *,
    mode: str,
    requested_years: str,
) -> Dict[str, Any]:
    supplied = opportunity.get("partial")
    if supplied is None:
        supplied = opportunity.get(
            "partialYears",
            opportunity.get("min_winning_years", opportunity.get("year2")),
        )
    selection = _statistical_partial(supplied, mode=mode)
    return {
        "selection": selection,
        "mode": mode,
        "requested_years": requested_years,
    }


def checkpoint_ui_key(opportunity: Mapping[str, Any]) -> str:
    symbol = str(opportunity.get("symbol") or "").strip().upper()
    days_out = _integer(opportunity.get("daysOut"), "daysOut")
    direction = _direction(opportunity.get("direction"))
    if days_out >= 30:
        entry = _entry_date(opportunity.get("date")).isoformat()
        return f"{symbol}|{entry}|{days_out}|{direction}"
    return f"{symbol}|{days_out}|{direction}"


def legacy_score_keys(
    symbol: Any,
    entry_date: Any,
    days_out: Any,
    direction: Any,
) -> Tuple[str, str]:
    """Return the unambiguous additive key followed by the legacy alias."""

    normalized_symbol = str(symbol or "").strip().upper()
    normalized_date = _entry_date(entry_date).isoformat()
    normalized_days = _integer(days_out, "daysOut")
    normalized_direction = _direction(direction)
    return (
        f"{normalized_symbol}|{normalized_date}|{normalized_days}|{normalized_direction}",
        f"{normalized_symbol}|{normalized_days}|{normalized_direction}",
    )


def normalize_legacy_score_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Give the legacy scorer's terminal failures an explicit additive shape."""

    if not isinstance(result, Mapping):
        raise CheckpointProviderError("legacy scorer result must be an object")
    raw_error = result.get("error")
    if raw_error or result.get("vix_blocked") is True or result.get("status") == "unavailable":
        error = raw_error if isinstance(raw_error, Mapping) else {}
        requested_code = str(error.get("code") or "").strip().lower()
        vix_blocked = (
            result.get("vix_blocked") is True
            or requested_code == "vix_blocked"
        )
        code = (
            "vix_blocked"
            if vix_blocked
            else requested_code
            if requested_code in _LEGACY_UNAVAILABLE_COPY
            else "provider_unavailable"
        )
        message = _LEGACY_UNAVAILABLE_COPY[code]
        return {
            "status": "unavailable",
            "ml_score": None,
            "win_prob": None,
            "pred_return": None,
            "pred_mfe": None,
            "error": {
                "code": code,
                "message": message,
                "retryable": bool(error.get("retryable", code != "vix_blocked")),
            },
        }
    return {
        "status": "available",
        "ml_score": _score_number(result.get("ml_score"), "ml_score", minimum=0, maximum=100),
        "win_prob": _score_number(result.get("win_prob"), "win_prob", minimum=0, maximum=1),
        "pred_return": _score_number(result.get("pred_return"), "pred_return", minimum=-1000, maximum=1000),
        "pred_mfe": _score_number(result.get("pred_mfe"), "pred_mfe", minimum=-1000, maximum=1000),
    }


def checkpoint_pending_opportunity(
    opportunity: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> Dict[str, Any]:
    """Preserve every fallback-derived identity field across browser polling.

    Older clients post only the returned ``pending`` rows on their next poll.
    Enrich those rows from the already-validated plan so PE mode and table-level
    years/partial defaults cannot silently fall back to consecutive mode.
    """

    pending = dict(opportunity)
    source = plan.get("source") if isinstance(plan, Mapping) else None
    source = source if isinstance(source, Mapping) else {}
    provenance = source.get("partial")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    if pending.get("years") is None:
        pending["years"] = provenance.get("requested_years")
    if pending.get("partial") is None and pending.get("partialYears") is None:
        pending["partial"] = provenance.get("selection")
    if not pending.get("mode"):
        pending["mode"] = provenance.get("mode") or "consecutive"
    if not pending.get("selection_origin"):
        pending["selection_origin"] = str(
            source.get("selection_origin") or "scanner"
        )[:64]
    return pending


def build_checkpoint_plan(
    resource_id: Any,
    opportunity: Mapping[str, Any],
    *,
    fallback_years: Optional[str] = None,
    fallback_partial: Any = None,
    fallback_mode: str = "consecutive",
    selection_origin: Optional[str] = None,
) -> Dict[str, Any]:
    """Build shorter standard checkpoints for a displayed source pattern.

    The current full-window score remains primary through 90 calendar days.
    Only standard horizons strictly shorter than that window are recalculated;
    a source beyond 90 days receives all three supported checkpoints.
    """

    resource = str(resource_id)
    if resource not in ALLOWED_RESOURCE_IDS:
        raise CheckpointContextError("checkpoint scoring is limited to US stocks and ETFs")
    if not isinstance(opportunity, Mapping):
        raise CheckpointContextError("opportunity must be an object")
    symbol = str(opportunity.get("symbol") or "").strip().upper()
    if not _SYMBOL_RE.fullmatch(symbol):
        raise CheckpointContextError("invalid symbol")
    entry = _entry_date(opportunity.get("date"))
    raw_days_out = _integer(opportunity.get("daysOut"), "daysOut")
    full_calendar_days = raw_days_out + 1
    if full_calendar_days <= 30:
        raise CheckpointContextError(
            "duration comparisons are only available for patterns over 30 days"
        )
    if full_calendar_days > 367:
        raise CheckpointContextError("source pattern is outside the supported TradeWave range")
    direction = _direction(opportunity.get("direction"))
    mode = _mode(opportunity.get("mode") or fallback_mode)
    years_value = opportunity.get("years", fallback_years)
    years, requested_years = _years_identity(years_value, mode, entry)

    enriched = dict(opportunity)
    if enriched.get("partial") is None and enriched.get("partialYears") is None:
        enriched["partial"] = fallback_partial
    if selection_origin:
        enriched["selection_origin"] = selection_origin
    source_selection_origin = str(
        enriched.get("selection_origin") or "scanner"
    )[:64]
    partial = _partial_provenance(
        enriched,
        mode=mode,
        requested_years=requested_years,
    )
    comparison_days = tuple(
        calendar_days
        for calendar_days in CHECKPOINT_CALENDAR_DAYS
        if calendar_days < full_calendar_days
    )
    scorer_requests = [
        {
            "resource_id": resource,
            "symbol": symbol,
            "date": entry.isoformat(),
            "calendar_days": calendar_days,
            "direction": direction,
            "years": years,
            "partial": partial,
        }
        for calendar_days in comparison_days
    ]
    source = {
        "resource_id": resource,
        "symbol": symbol,
        "date": entry.isoformat(),
        "daysOut": raw_days_out,
        "calendar_days": full_calendar_days,
        "direction": direction,
        "years": years,
        "partial": partial,
        # Telemetry/explanation metadata only. It is intentionally outside the
        # scorer request and every request-derived cache key.
        "selection_origin": source_selection_origin,
    }
    return {
        "contract_version": CONTEXT_CONTRACT_VERSION,
        "ui_key": f"{symbol}|{entry.isoformat()}|{raw_days_out}|{direction}",
        "source": source,
        "requests": scorer_requests,
        "comparison_calendar_days": list(comparison_days),
        "display_horizon_days": (
            full_calendar_days if full_calendar_days <= 90 else 90
        ),
        "includes_current_score": full_calendar_days <= 90,
    }


def normalize_scorer_metadata(value: Any) -> Dict[str, str]:
    source = value if isinstance(value, Mapping) else {}
    aliases = {
        "model_release": ("model_release", "model_version"),
        "feature_schema_version": ("feature_schema_version", "feature_schema"),
        "feature_schema_hash": ("feature_schema_hash",),
        "context_schema_version": ("context_schema_version", "context_schema"),
        "pattern_profile_schema_version": ("pattern_profile_schema_version",),
        "model_manifest_hash": ("model_manifest_hash", "manifest_hash"),
        "data_as_of": ("data_as_of", "latest_data_date"),
        "data_generation_hash": ("data_generation_hash",),
        "data_source_manifest_hash": ("data_source_manifest_hash",),
        "context_data_complete": ("context_data_complete",),
    }
    result: Dict[str, str] = {}
    for target, candidates in aliases.items():
        selected = ""
        for candidate in candidates:
            candidate_value = source.get(candidate)
            if candidate_value not in (None, ""):
                selected = str(candidate_value)
                break
        result[target] = selected or "unknown"
    return result


def metadata_fingerprint(metadata: Mapping[str, Any]) -> str:
    identity = {
        "contract_version": CONTEXT_CONTRACT_VERSION,
        **{field: str(metadata.get(field) or "unknown") for field in _METADATA_FIELDS},
    }
    return _hash_payload(identity)


def _metadata_matches(cached: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    for field in _METADATA_FIELDS:
        wanted = str(expected.get(field) or "unknown")
        if wanted != "unknown" and str(cached.get(field) or "unknown") != wanted:
            return False
    return True


def valid_scorer_metadata(value: Any) -> bool:
    """Require a complete V3 identity before a cache can be trusted or published."""

    metadata = normalize_scorer_metadata(value)
    if any(
        not str(metadata.get(field) or "").strip()
        or str(metadata.get(field)).strip().lower() == "unknown"
        for field in _METADATA_FIELDS
    ):
        return False
    if str(metadata.get("context_data_complete")).strip().lower() != "true":
        return False
    if "v3" not in str(metadata.get("model_release")).lower():
        return False
    feature_schema = str(metadata.get("feature_schema_version")).lower()
    if "v3" not in feature_schema or "62" not in feature_schema:
        return False
    try:
        _entry_date(metadata.get("data_as_of"))
    except CheckpointContextError:
        return False
    return True


def scorer_metadata_matches(left: Any, right: Any) -> bool:
    """Compare two complete scorer identities without wildcard/unknown semantics."""

    if not valid_scorer_metadata(left) or not valid_scorer_metadata(right):
        return False
    normalized_left = normalize_scorer_metadata(left)
    normalized_right = normalize_scorer_metadata(right)
    return all(
        normalized_left[field] == normalized_right[field]
        for field in _METADATA_FIELDS
    )


def _legacy_cache_identity(
    symbol: Any,
    entry_date: Any,
    days_out: Any,
    direction: Any,
) -> Dict[str, Any]:
    return {
        "symbol": str(symbol or "").strip().upper(),
        "date": _entry_date(entry_date).isoformat(),
        "daysOut": _integer(days_out, "daysOut"),
        "direction": _direction(direction),
    }


def legacy_pointer_key(
    symbol: Any,
    entry_date: Any,
    days_out: Any,
    direction: Any,
) -> str:
    identity = _legacy_cache_identity(symbol, entry_date, days_out, direction)
    return f"{CACHE_SCHEMA_VERSION}:legacy:index:{_hash_payload(identity)}"


def legacy_lock_key(
    symbol: Any,
    entry_date: Any,
    days_out: Any,
    direction: Any,
) -> str:
    """Return the distributed single-flight key for one exact-window score."""

    return legacy_pointer_key(
        symbol, entry_date, days_out, direction
    ).replace(":index:", ":lock:", 1)


def legacy_value_key(
    symbol: Any,
    entry_date: Any,
    days_out: Any,
    direction: Any,
    metadata: Mapping[str, Any],
) -> str:
    identity = {
        "request": _legacy_cache_identity(symbol, entry_date, days_out, direction),
        "scorer": normalize_scorer_metadata(metadata),
    }
    return f"{CACHE_SCHEMA_VERSION}:legacy:value:{_hash_payload(identity)}"


def read_cached_legacy_score(
    redis_client: Any,
    symbol: Any,
    entry_date: Any,
    days_out: Any,
    direction: Any,
    *,
    expected_metadata: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    """Read an exact-window score only for the current model/data generation."""

    if not valid_scorer_metadata(expected_metadata):
        return None
    identity = _legacy_cache_identity(symbol, entry_date, days_out, direction)
    pointer = _redis_json(
        redis_client.get(
            legacy_pointer_key(symbol, entry_date, days_out, direction)
        )
    )
    if not isinstance(pointer, Mapping):
        return None
    pointer_metadata = pointer.get("scorer")
    if not isinstance(pointer_metadata, Mapping) or not _metadata_matches(
        pointer_metadata, expected_metadata
    ):
        return None
    value_key = str(pointer.get("value_key") or "")
    if not value_key.startswith(f"{CACHE_SCHEMA_VERSION}:legacy:value:"):
        return None
    cached = _redis_json(redis_client.get(value_key))
    if not isinstance(cached, Mapping):
        return None
    if str(cached.get("request_hash") or "") != _hash_payload(identity):
        return None
    try:
        return normalize_legacy_score_result(cached.get("score"))
    except CheckpointProviderError:
        return None


def write_cached_legacy_score(
    redis_client: Any,
    symbol: Any,
    entry_date: Any,
    days_out: Any,
    direction: Any,
    score: Mapping[str, Any],
    *,
    metadata: Mapping[str, Any],
    ttl_seconds: int,
) -> None:
    """Atomically publish a versioned exact-window value and its live pointer."""

    normalized_metadata = normalize_scorer_metadata(metadata)
    if not valid_scorer_metadata(normalized_metadata):
        raise CheckpointProviderError("legacy scorer metadata is incomplete")
    identity = _legacy_cache_identity(symbol, entry_date, days_out, direction)
    normalized_score = normalize_legacy_score_result(score)
    value_key = legacy_value_key(
        symbol, entry_date, days_out, direction, normalized_metadata
    )
    pointer_key = legacy_pointer_key(symbol, entry_date, days_out, direction)
    value = {
        "request_hash": _hash_payload(identity),
        "score": normalized_score,
        "scorer": normalized_metadata,
        "cached_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    pointer = {
        "value_key": value_key,
        "scorer": normalized_metadata,
        "contract_version": CONTEXT_CONTRACT_VERSION,
    }
    pipeline = redis_client.pipeline(transaction=True)
    pipeline.set(value_key, _canonical_json(value), ex=max(int(ttl_seconds), 60))
    pipeline.set(pointer_key, _canonical_json(pointer), ex=max(int(ttl_seconds), 60))
    pipeline.execute()


def _score_number(
    value: Any,
    field: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool):
        raise CheckpointProviderError(f"scorer {field} is invalid")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CheckpointProviderError(f"scorer {field} is missing") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise CheckpointProviderError(f"scorer {field} is outside its valid range")
    return number


def _result_for_request(payload: Mapping[str, Any], request_item: Mapping[str, Any]) -> Mapping[str, Any]:
    results = payload.get("results")
    if isinstance(results, list):
        candidates: Iterable[Any] = results
    elif isinstance(payload.get("result"), Mapping):
        candidates = (payload["result"],)
    else:
        candidates = (payload,)
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        try:
            matches = (
                str(candidate.get("resource_id")) == request_item["resource_id"]
                and str(candidate.get("symbol") or "").upper() == request_item["symbol"]
                and str(candidate.get("date") or "") == request_item["date"]
                and _integer(candidate.get("calendar_days"), "calendar_days")
                == request_item["calendar_days"]
                and _direction(candidate.get("direction")) == request_item["direction"]
                and str(candidate.get("years") or "") == request_item["years"]
                and _canonical_json(candidate.get("partial")) == _canonical_json(request_item["partial"])
            )
        except CheckpointContextError:
            matches = False
        if matches:
            return candidate
    raise CheckpointProviderError("scorer response identity did not match the request")


def _normalize_selected_recurrence(value: Any) -> Dict[str, Any]:
    """Validate the small historical explanation returned by the scorer."""

    if not isinstance(value, Mapping):
        raise CheckpointProviderError("scorer selected recurrence is missing")
    sample_size = _integer(value.get("sample_size"), "sample_size")
    positive_years = _integer(value.get("positive_years"), "positive_years")
    requested = _integer(
        value.get("requested_observations"), "requested_observations"
    )
    required_value = value.get("required_positive_years")
    required = (
        None
        if required_value is None
        else _integer(required_value, "required_positive_years")
    )
    if (
        requested <= 0
        or sample_size < 0
        or sample_size > requested
        or positive_years < 0
        or positive_years > sample_size
        or (required is not None and not 1 <= required <= requested)
    ):
        raise CheckpointProviderError("scorer selected recurrence is invalid")

    def optional_number(
        field: str, minimum: float = -1000, maximum: float = 1000
    ) -> Optional[float]:
        raw = value.get(field)
        if raw is None:
            return None
        return _score_number(raw, field, minimum=minimum, maximum=maximum)

    result = {
        "status": str(value.get("status") or "")[:40],
        "mode": str(value.get("mode") or "consecutive")[:20],
        "years": str(value.get("years") or "")[:32],
        "requested_observations": requested,
        "sample_size": sample_size,
        "positive_years": positive_years,
        "required_positive_years": required,
        "win_rate": optional_number("win_rate", 0, 1),
        "average_return_pct": optional_number("average_return_pct"),
        "median_return_pct": optional_number("median_return_pct"),
        "average_favorable_excursion_pct": optional_number(
            "average_favorable_excursion_pct"
        ),
        "complete": value.get("complete") is True,
    }
    if value.get("pe_phase") is not None:
        pe_phase = _integer(value.get("pe_phase"), "pe_phase")
        if pe_phase not in (1, 2, 3, 4):
            raise CheckpointProviderError("scorer PE phase is invalid")
        result["pe_phase"] = pe_phase
    return result


def normalize_checkpoint_response(
    request_item: Mapping[str, Any],
    payload: Any,
    *,
    expected_metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate one scorer response before it can enter Redis or the UI."""

    if not isinstance(payload, Mapping):
        raise CheckpointProviderError("scorer response must be an object")
    metadata = normalize_scorer_metadata(payload.get("metadata", payload))
    if not valid_scorer_metadata(metadata):
        raise CheckpointProviderError("scorer metadata is incomplete")
    if expected_metadata is not None and not scorer_metadata_matches(
        metadata, expected_metadata
    ):
        raise CheckpointProviderError("scorer metadata changed during the request")
    result = _result_for_request(payload, request_item)
    expected_tier = {
        30: "10_30",
        60: "31_60",
        90: "61_90",
    }.get(int(request_item["calendar_days"]))
    if expected_tier is None or str(result.get("tier") or "") != expected_tier:
        raise CheckpointProviderError("scorer tier did not match the checkpoint")
    if str(result.get("status") or "").lower() == "below_threshold":
        selected = _normalize_selected_recurrence(
            result.get("selected_recurrence")
        )
        required = selected.get("required_positive_years")
        if (
            selected.get("status") != "below_threshold"
            or required is None
            or selected["positive_years"] >= required
            or not selected.get("complete")
        ):
            raise CheckpointProviderError(
                "scorer below-threshold explanation is inconsistent"
            )
        context_hash = str(result.get("context_hash") or "").strip().lower()
        if not _SHA256_RE.fullmatch(context_hash):
            raise CheckpointProviderError("scorer context_hash is invalid")
        return {
            "status": "below_threshold",
            "calendar_days": request_item["calendar_days"],
            "daysOut": request_item["calendar_days"] - 1,
            "tier": expected_tier,
            "basis": "recalculated_pattern",
            "pattern_recalculated": True,
            "ml_score": None,
            "win_prob": None,
            "pred_return": None,
            "pred_mfe": None,
            "selected_recurrence": selected,
            "context_hash": context_hash,
            "scorer": metadata,
        }
    error = result.get("error")
    if result.get("status") == "unavailable" or isinstance(error, Mapping):
        error_source = error if isinstance(error, Mapping) else {}
        unavailable = {
            "status": "unavailable",
            "calendar_days": request_item["calendar_days"],
            "daysOut": request_item["calendar_days"] - 1,
            "tier": expected_tier,
            "basis": "recalculated_pattern",
            "pattern_recalculated": False,
            "error": {
                "code": str(error_source.get("code") or "pattern_profile_unavailable")[:80],
                "message": str(
                    error_source.get("message") or "Recalculated checkpoint is unavailable."
                )[:240],
                "retryable": bool(error_source.get("retryable", False)),
            },
            "scorer": metadata,
        }
        if (
            str(error_source.get("code") or "")
            == "selected_recurrence_insufficient_history"
            and isinstance(error_source.get("details"), Mapping)
        ):
            unavailable["selected_recurrence"] = (
                _normalize_selected_recurrence(error_source["details"])
            )
        return unavailable
    if result.get("pattern_recalculated") is not True:
        raise CheckpointProviderError("scorer did not confirm pattern recalculation")
    profile = result.get("pattern_profile")
    profile_source = profile if isinstance(profile, Mapping) else {}
    qualifying_combo_count = _integer(
        profile_source.get("qualifying_combo_count", 0),
        "qualifying_combo_count",
    )
    if qualifying_combo_count <= 0:
        raise CheckpointProviderError(
            "scorer qualifying_combo_count must be positive"
        )
    profile_hash = str(profile_source.get("profile_hash") or "").strip().lower()
    context_hash = str(result.get("context_hash") or "").strip().lower()
    feature_vector_hash = str(result.get("feature_vector_hash") or "").strip().lower()
    if not _SHA256_RE.fullmatch(profile_hash):
        raise CheckpointProviderError("scorer profile_hash is invalid")
    if not _SHA256_RE.fullmatch(context_hash):
        raise CheckpointProviderError("scorer context_hash is invalid")
    if not _SHA256_RE.fullmatch(feature_vector_hash):
        raise CheckpointProviderError("scorer feature_vector_hash is invalid")
    return {
        "status": "available",
        "calendar_days": request_item["calendar_days"],
        "daysOut": request_item["calendar_days"] - 1,
        "tier": expected_tier,
        "basis": "recalculated_pattern",
        "pattern_recalculated": True,
        "ml_score": _score_number(result.get("ml_score"), "ml_score", minimum=0, maximum=100),
        "win_prob": _score_number(result.get("win_prob"), "win_prob", minimum=0, maximum=1),
        "pred_return": _score_number(
            result.get("pred_return"), "pred_return", minimum=-1000, maximum=1000
        ),
        "pred_mfe": _score_number(
            result.get("pred_mfe"), "pred_mfe", minimum=-1000, maximum=1000
        ),
        "pattern_profile": {
            "source": str(profile_source.get("source") or "dynamic_recalculation")[:80],
            "qualifying_combo_count": qualifying_combo_count,
            "profile_hash": profile_hash,
        },
        "selected_recurrence": _normalize_selected_recurrence(
            result.get("selected_recurrence")
        ),
        "context_hash": context_hash,
        "feature_vector_hash": feature_vector_hash,
        "scorer": metadata,
    }


def checkpoint_pointer_key(request_item: Mapping[str, Any]) -> str:
    base = {
        "cache_schema": CACHE_SCHEMA_VERSION,
        "contract_version": CONTEXT_CONTRACT_VERSION,
        **request_item,
    }
    return f"{CACHE_SCHEMA_VERSION}:checkpoint:index:{_hash_payload(base)}"


def checkpoint_value_key(
    request_item: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    exact = {
        "cache_schema": CACHE_SCHEMA_VERSION,
        "contract_version": CONTEXT_CONTRACT_VERSION,
        "request": request_item,
        "scorer": {
            field: str(metadata.get(field) or "unknown") for field in _METADATA_FIELDS
        },
    }
    return f"{CACHE_SCHEMA_VERSION}:checkpoint:value:{_hash_payload(exact)}"


def checkpoint_lock_key(request_item: Mapping[str, Any]) -> str:
    return checkpoint_pointer_key(request_item).replace(":index:", ":lock:", 1)


def read_cached_checkpoint(
    redis_client: Any,
    request_item: Mapping[str, Any],
    *,
    expected_metadata: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    pointer = _redis_json(redis_client.get(checkpoint_pointer_key(request_item)))
    if not isinstance(pointer, Mapping):
        return None
    metadata = pointer.get("scorer")
    if expected_metadata:
        if not isinstance(metadata, Mapping):
            return None
        if not _metadata_matches(metadata, expected_metadata):
            return None
    exact_key = str(pointer.get("value_key") or "")
    if not exact_key.startswith(f"{CACHE_SCHEMA_VERSION}:checkpoint:value:"):
        return None
    cached = _redis_json(redis_client.get(exact_key))
    if not isinstance(cached, Mapping):
        return None
    if str(cached.get("request_hash") or "") != _hash_payload(request_item):
        return None
    checkpoint = cached.get("checkpoint")
    return dict(checkpoint) if isinstance(checkpoint, Mapping) else None


def write_cached_checkpoint(
    redis_client: Any,
    request_item: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    *,
    ttl_seconds: int,
) -> None:
    metadata = normalize_scorer_metadata(checkpoint.get("scorer"))
    value_key = checkpoint_value_key(request_item, metadata)
    pointer_key = checkpoint_pointer_key(request_item)
    value = {
        "request_hash": _hash_payload(request_item),
        "checkpoint": checkpoint,
        "cached_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    pointer = {
        "value_key": value_key,
        "scorer": metadata,
        "contract_version": CONTEXT_CONTRACT_VERSION,
    }
    pipeline = redis_client.pipeline(transaction=True)
    pipeline.set(value_key, _canonical_json(value), ex=max(int(ttl_seconds), 60))
    pipeline.set(pointer_key, _canonical_json(pointer), ex=max(int(ttl_seconds), 60))
    pipeline.execute()


def assemble_checkpoint_bundle(
    plan: Mapping[str, Any],
    checkpoints: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    expected_days = tuple(
        int(item["calendar_days"]) for item in plan.get("requests") or ()
    )
    by_days = {
        int(item.get("calendar_days")): dict(item)
        for item in checkpoints
        if isinstance(item, Mapping) and item.get("calendar_days") in expected_days
    }
    if not expected_days or set(by_days) != set(expected_days):
        raise CheckpointProviderError("checkpoint bundle is incomplete")
    horizons = [by_days[days] for days in expected_days]
    available = [item for item in horizons if item.get("status") == "available"]
    status = (
        "available"
        if len(available) == len(horizons)
        else "partial"
        if available
        else "unavailable"
    )
    display_days = int(plan.get("display_horizon_days") or expected_days[-1])
    display = by_days.get(display_days)
    scorer_identities = {
        metadata_fingerprint(item.get("scorer", {})) for item in horizons
    }
    if len(scorer_identities) != 1:
        raise CheckpointProviderError("checkpoint horizons use mixed scorer identities")
    bundle: Dict[str, Any] = {
        "status": status,
        "basis": "recalculated_checkpoints",
        "pattern_recalculated": bool(available),
        "full_pattern_calendar_days": int(plan["source"]["calendar_days"]),
        "display_horizon_days": display_days,
        "display_status": (
            str(display.get("status") or "unavailable")
            if display is not None else "loading"
        ),
        "ml_score": display.get("ml_score") if display is not None else None,
        "win_prob": display.get("win_prob") if display is not None else None,
        "pred_return": display.get("pred_return") if display is not None else None,
        "pred_mfe": display.get("pred_mfe") if display is not None else None,
        "horizons": horizons,
        "source": dict(plan["source"]),
        "scorer": dict(
            (display or horizons[-1]).get("scorer") or {}
        ),
        "mixed_scorer_identity": False,
    }
    return bundle


def assemble_duration_comparison_bundle(
    plan: Mapping[str, Any],
    checkpoint_bundle: Optional[Mapping[str, Any]],
    *,
    current_score: Optional[Mapping[str, Any]] = None,
    loading: bool = False,
) -> Dict[str, Any]:
    """Combine shorter recalculations with the unchanged current score.

    For a 31-90-day source, the current exact-window V3 result remains the
    table value and is marked ``Current`` in details.  For a source beyond the
    model range, 90 days remains the displayed bounded checkpoint.
    """

    full_days = int(plan["source"]["calendar_days"])
    requested_days = tuple(
        int(item["calendar_days"]) for item in plan.get("requests") or ()
    )
    raw_horizons = (
        list(checkpoint_bundle.get("horizons") or ())
        if isinstance(checkpoint_bundle, Mapping)
        else []
    )
    by_days = {
        int(item.get("calendar_days")): dict(item)
        for item in raw_horizons
        if isinstance(item, Mapping) and item.get("calendar_days") in requested_days
    }
    horizons: List[Dict[str, Any]] = []
    for calendar_days in requested_days:
        item = by_days.get(calendar_days)
        if item is None:
            item = {
                "status": "loading" if loading else "unavailable",
                "calendar_days": calendar_days,
                "daysOut": calendar_days - 1,
                "basis": "recalculated_pattern",
                "pattern_recalculated": False,
                "error": {
                    "code": "loading" if loading else "provider_unavailable",
                    "message": (
                        "Duration comparison is loading."
                        if loading else "Duration comparison is unavailable."
                    ),
                    "retryable": bool(loading),
                },
            }
        item["is_current"] = False
        horizons.append(item)

    if full_days <= 90:
        if current_score is None:
            current = {
                "status": "loading" if loading else "unavailable",
                "ml_score": None,
                "win_prob": None,
                "pred_return": None,
                "pred_mfe": None,
                "error": {
                    "code": "loading" if loading else "provider_unavailable",
                    "message": (
                        "Current-duration score is loading."
                        if loading else "Current-duration score is unavailable."
                    ),
                    "retryable": bool(loading),
                },
            }
        else:
            current = normalize_legacy_score_result(current_score)
        current = {
            **current,
            "calendar_days": full_days,
            "daysOut": full_days - 1,
            "basis": "full_pattern",
            "pattern_recalculated": False,
            "is_current": True,
        }
        horizons.append(current)

    horizons.sort(key=lambda item: int(item["calendar_days"]))
    display_days = full_days if full_days <= 90 else 90
    display = next(
        (item for item in horizons if int(item["calendar_days"]) == display_days),
        None,
    )
    available = [item for item in horizons if item.get("status") == "available"]
    terminal = [
        item for item in horizons
        if item.get("status") in {"available", "below_threshold", "unavailable"}
    ]
    if len(available) == len(horizons):
        status = "available"
    elif available:
        status = "partial"
    elif len(terminal) == len(horizons):
        status = "unavailable"
    else:
        status = "loading"
    return {
        "status": status,
        "basis": "duration_comparison",
        "pattern_recalculated": any(
            item.get("pattern_recalculated") is True for item in horizons
        ),
        "full_pattern_calendar_days": full_days,
        "display_horizon_days": display_days,
        "display_status": str(
            (display or {}).get("status") or "unavailable"
        ),
        "ml_score": (display or {}).get("ml_score"),
        "win_prob": (display or {}).get("win_prob"),
        "pred_return": (display or {}).get("pred_return"),
        "pred_mfe": (display or {}).get("pred_mfe"),
        "horizons": horizons,
        "source": dict(plan["source"]),
        "scorer": dict(
            (checkpoint_bundle or {}).get("scorer") or {}
        ),
        "mixed_scorer_identity": False,
    }


class CheckpointScoringService:
    """Redis-backed, single-flight caller for the scorer's context endpoint."""

    def __init__(
        self,
        *,
        redis_client: Any,
        scorer_url: str,
        http_client: Any,
        ttl_seconds: int,
        request_timeout: int = 35,
    ) -> None:
        self.redis = redis_client
        self.scorer_url = str(scorer_url or "").rstrip("/")
        self.http = http_client
        self.ttl_seconds = max(int(ttl_seconds), 60)
        self.request_timeout = max(int(request_timeout), 1)
        self._metadata_key = (
            f"{CACHE_SCHEMA_VERSION}:scorer:metadata:"
            f"{hashlib.sha256(self.scorer_url.encode('utf-8')).hexdigest()[:20]}"
        )

    def scorer_metadata(self) -> Optional[Dict[str, str]]:
        cached = _redis_json(self.redis.get(self._metadata_key))
        if isinstance(cached, Mapping):
            normalized = normalize_scorer_metadata(cached)
            if valid_scorer_metadata(normalized):
                return normalized
        if not self.scorer_url:
            return None
        response = self.http.get(f"{self.scorer_url}/health", timeout=3)
        if response.status_code != 200:
            return None
        payload = response.json()
        if not isinstance(payload, Mapping):
            return None
        metadata = normalize_scorer_metadata(payload.get("metadata", payload))
        if not valid_scorer_metadata(metadata):
            return None
        self.redis.set(self._metadata_key, _canonical_json(metadata), ex=60)
        return metadata

    def cached_bundle(self, plan: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            expected = self.scorer_metadata()
        except Exception as exc:
            logging.warning("ML checkpoint metadata lookup failed: %s", exc)
            expected = None
        if expected is None:
            return None
        cached = [
            read_cached_checkpoint(self.redis, item, expected_metadata=expected)
            for item in plan["requests"]
        ]
        if any(item is None for item in cached):
            return None
        return assemble_checkpoint_bundle(plan, cached)

    def score_bundles(
        self,
        plans: Sequence[Mapping[str, Any]],
        *,
        max_request_items: int = 60,
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Score cache misses for many rows in one bounded provider batch.

        Locks remain checkpoint-granular, while the network call is batch-granular.
        That prevents a cold opportunity table from turning into three network calls
        per row and still guarantees a single writer for each exact cache identity.
        """

        output: Dict[str, Optional[Dict[str, Any]]] = {
            str(plan.get("ui_key") or ""): None for plan in plans
        }
        if not plans or not self.scorer_url:
            return output
        try:
            expected = self.scorer_metadata()
        except Exception as exc:
            logging.warning("ML checkpoint metadata lookup failed: %s", exc)
            expected = None

        unique_requests: Dict[str, Mapping[str, Any]] = {}
        for plan in plans:
            for request_item in plan.get("requests") or ():
                if isinstance(request_item, Mapping):
                    unique_requests.setdefault(_hash_payload(request_item), request_item)

        resolved: Dict[str, Dict[str, Any]] = {}
        missing: List[Tuple[str, Mapping[str, Any]]] = []
        for request_hash, request_item in unique_requests.items():
            cached = (
                read_cached_checkpoint(
                    self.redis, request_item, expected_metadata=expected
                )
                if expected is not None
                else None
            )
            if cached is None:
                missing.append((request_hash, request_item))
            else:
                resolved[request_hash] = cached

        # The caller controls row chunking, but enforce a second hard ceiling at
        # the provider boundary so an accidental giant poll cannot create a giant
        # inference request.
        selected_missing = missing[: max(int(max_request_items), 1)]
        owned: List[Tuple[str, Mapping[str, Any], Any]] = []
        waiting: List[Tuple[str, Mapping[str, Any]]] = []
        try:
            for request_hash, request_item in selected_missing:
                lock = self.redis.lock(
                    checkpoint_lock_key(request_item),
                    timeout=max(self.request_timeout * 2, 60),
                    blocking_timeout=0,
                )
                if lock.acquire(blocking=False):
                    cached = (
                        read_cached_checkpoint(
                            self.redis, request_item, expected_metadata=expected
                        )
                        if expected is not None
                        else None
                    )
                    if cached is not None:
                        resolved[request_hash] = cached
                        lock.release()
                    else:
                        owned.append((request_hash, request_item, lock))
                else:
                    waiting.append((request_hash, request_item))

            if owned:
                provider_items = [dict(request_item) for _, request_item, _ in owned]
                response = self.http.post(
                    f"{self.scorer_url}/score/context",
                    json={"opportunities": provider_items},
                    timeout=self.request_timeout,
                )
                if response.status_code == 200:
                    payload = response.json()
                    for request_hash, request_item, _lock in owned:
                        try:
                            checkpoint = normalize_checkpoint_response(
                                request_item,
                                payload,
                                expected_metadata=expected,
                            )
                        except CheckpointProviderError as exc:
                            logging.warning(
                                "ML checkpoint scorer response rejected: %s", exc
                            )
                            continue
                        error = checkpoint.get("error")
                        if (
                            checkpoint.get("status") == "unavailable"
                            and isinstance(error, Mapping)
                            and error.get("retryable") is True
                        ):
                            # Preserve the scorer's structured VIX/temporary state
                            # for this response, but do not make it a durable cache
                            # fact. The UI and Tara must not see endless "pending".
                            resolved[request_hash] = checkpoint
                            continue
                        write_cached_checkpoint(
                            self.redis,
                            request_item,
                            checkpoint,
                            ttl_seconds=self.ttl_seconds,
                        )
                        resolved[request_hash] = checkpoint
                else:
                    logging.warning(
                        "ML checkpoint scorer returned HTTP %s for batch size %s",
                        response.status_code,
                        len(provider_items),
                    )
        except Exception as exc:
            logging.warning("ML checkpoint scorer batch unavailable: %s", exc)
        finally:
            for _request_hash, _request_item, lock in owned:
                try:
                    lock.release()
                except Exception:
                    logging.warning("ML checkpoint single-flight lock expired")

        if waiting:
            deadline = time.monotonic() + 2.0
            while waiting and time.monotonic() < deadline:
                remaining: List[Tuple[str, Mapping[str, Any]]] = []
                for request_hash, request_item in waiting:
                    cached = (
                        read_cached_checkpoint(
                            self.redis, request_item, expected_metadata=expected
                        )
                        if expected is not None
                        else None
                    )
                    if cached is None:
                        remaining.append((request_hash, request_item))
                    else:
                        resolved[request_hash] = cached
                waiting = remaining
                if waiting:
                    time.sleep(0.1)

        for plan in plans:
            checkpoints = []
            for request_item in plan.get("requests") or ():
                request_hash = _hash_payload(request_item)
                checkpoint = resolved.get(request_hash)
                if checkpoint is None:
                    checkpoints = []
                    break
                checkpoints.append(checkpoint)
            if checkpoints:
                output[str(plan.get("ui_key") or "")] = assemble_checkpoint_bundle(
                    plan, checkpoints
                )
        return output

    def score_bundle(self, plan: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """Single-row convenience path used by Tara; still one batched POST."""

        return self.score_bundles(
            [plan], max_request_items=max(len(plan.get("requests") or ()), 1)
        ).get(
            str(plan.get("ui_key") or "")
        )


def is_default_table_context(
    resource_id: str,
    *,
    years: Any,
    partial: Any,
    mode: Any,
) -> bool:
    mode_text = "pe" if str(mode or "").lower().startswith("pe") else "consecutive"
    partial_value = partial
    if isinstance(partial, Mapping):
        partial_value = partial.get(
            "min_winning_years",
            partial.get("partialYears", partial.get("selection")),
        )
    selected = (str(years or ""), str(partial_value or ""))
    if mode_text == "pe":
        plain_years = selected[0].split("-", 1)[-1]
        return (plain_years, selected[1]) == DEFAULT_PE_CONTEXT
    return selected == DEFAULT_CONSECUTIVE_CONTEXTS.get(str(resource_id))


def build_usage_context(
    resource_id: Any,
    request_body: Mapping[str, Any],
    *,
    stored_row_limit: int = USAGE_MAX_STORED_ROWS,
) -> Optional[Dict[str, Any]]:
    """Build a validated, non-user context for targeted post-EOD prefetch.

    Browser telemetry retains the default 100-row storage bound. The trusted
    OppList4 warmer can request a larger explicit bound after re-fetching an
    authoritative table; this never changes the browser-recording contract.
    """

    resource = str(resource_id)
    if resource not in ALLOWED_RESOURCE_IDS or not isinstance(request_body, Mapping):
        return None
    table_context = _sanitized_table_context(request_body.get("table_context"))
    opportunities = request_body.get("opportunities")
    if not isinstance(opportunities, list):
        return None
    fallback_years = table_context.get("years")
    fallback_partial = table_context.get("partial")
    fallback_mode = str(table_context.get("mode") or "consecutive")
    displayed_range = table_context.get("day_range", "-")
    raw_range: Optional[Tuple[int, int]] = None
    if displayed_range != "-":
        start_text, end_text = str(displayed_range).split("-", 1)
        raw_range = (int(start_text) - 1, int(end_text) - 1)
    try:
        storage_limit = min(max(int(stored_row_limit), 0), 5000)
    except (TypeError, ValueError) as exc:
        raise CheckpointContextError("stored_row_limit is invalid") from exc
    all_identities: List[Dict[str, Any]] = []
    stored: List[Dict[str, Any]] = []
    for opportunity in opportunities:
        if not isinstance(opportunity, Mapping):
            continue
        try:
            raw_days = _integer(opportunity.get("daysOut"), "daysOut")
            if not 9 <= raw_days <= 366:
                continue
            if raw_range is not None and not raw_range[0] <= raw_days <= raw_range[1]:
                # React scores its stable baseline plus the currently visible
                # ranged rows. Popular-view telemetry must retain only the
                # identities actually inside that displayed range.
                continue
            identity = {
                "symbol": str(opportunity.get("symbol") or "").strip().upper(),
                "date": str(opportunity.get("date") or ""),
                "daysOut": raw_days,
                "direction": _direction(opportunity.get("direction")),
                "years": opportunity.get("years", fallback_years),
                "partial": _statistical_partial(
                    opportunity.get("partial", fallback_partial),
                    mode=_mode(opportunity.get("mode", fallback_mode)),
                ),
                "mode": _mode(opportunity.get("mode", fallback_mode)),
            }
            if not _SYMBOL_RE.fullmatch(identity["symbol"]):
                raise CheckpointContextError("invalid symbol")
            entry = _entry_date(identity["date"])
            mode_text = _mode(identity["mode"])
            _years_identity(identity["years"], mode_text, entry)
            all_identities.append(identity)
            if len(stored) < storage_limit:
                # Full validation here prevents a malformed browser item from
                # becoming a later unauthenticated scorer request.
                if raw_days >= 30:
                    build_checkpoint_plan(
                        resource,
                        identity,
                        fallback_years=fallback_years,
                        fallback_partial=fallback_partial,
                        fallback_mode=fallback_mode,
                    )
                stored.append(identity)
        except CheckpointContextError:
            continue
    if not all_identities:
        return None
    context_identity = {
        "resource_id": resource,
        "table_context": table_context,
        "opportunity_set_hash": _hash_payload(all_identities),
    }
    years = table_context.get("years")
    partial = table_context.get("partial")
    mode = table_context.get("mode")
    detail = {
        "schema_version": CACHE_SCHEMA_VERSION,
        **context_identity,
        "is_default": (
            is_default_table_context(
                resource, years=years, partial=partial, mode=mode
            )
            and table_context.get("is_default", True) is not False
        ),
        "opportunities": stored,
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    detail["context_hash"] = _hash_payload(context_identity)
    return detail


def record_usage_context(
    redis_client: Any,
    detail: Mapping[str, Any],
    *,
    market_date: Optional[str] = None,
) -> None:
    date_text = market_date or dt.datetime.now(dt.timezone.utc).date().isoformat()
    context_hash = str(detail["context_hash"])
    usage_key = f"{CACHE_SCHEMA_VERSION}:usage:{date_text}"
    detail_key = f"{CACHE_SCHEMA_VERSION}:usage-context:{context_hash}"
    pipeline = redis_client.pipeline(transaction=True)
    pipeline.zincrby(usage_key, 1, context_hash)
    pipeline.expire(usage_key, USAGE_RETENTION_SECONDS)
    pipeline.set(
        detail_key,
        _canonical_json(detail),
        ex=USAGE_RETENTION_SECONDS,
    )
    pipeline.execute()


def ranked_usage_contexts(
    redis_client: Any,
    *,
    days: int = 14,
    limit: int = 40,
    today: Optional[dt.date] = None,
) -> List[Dict[str, Any]]:
    """Return default-first, then most-viewed contexts across recent UTC days."""

    totals: Dict[str, float] = {}
    anchor = today or dt.datetime.now(dt.timezone.utc).date()
    for offset in range(max(int(days), 1)):
        date_text = (anchor - dt.timedelta(days=offset)).isoformat()
        raw_rows = redis_client.zrevrange(
            f"{CACHE_SCHEMA_VERSION}:usage:{date_text}",
            0,
            max(int(limit) * 3, 1) - 1,
            withscores=True,
        )
        for raw_hash, score in raw_rows:
            context_hash = (
                raw_hash.decode("utf-8") if isinstance(raw_hash, bytes) else str(raw_hash)
            )
            totals[context_hash] = totals.get(context_hash, 0.0) + float(score)
    contexts: List[Dict[str, Any]] = []
    for context_hash, views in totals.items():
        detail = _redis_json(
            redis_client.get(f"{CACHE_SCHEMA_VERSION}:usage-context:{context_hash}")
        )
        if not isinstance(detail, Mapping):
            continue
        resource = str(detail.get("resource_id") or "")
        if resource not in ALLOWED_RESOURCE_IDS:
            continue
        item = dict(detail)
        item["views"] = views
        contexts.append(item)
    contexts.sort(
        key=lambda item: (
            0 if item.get("is_default") is True else 1,
            -float(item.get("views") or 0),
            str(item.get("context_hash") or ""),
        )
    )
    return contexts[: max(int(limit), 0)]
