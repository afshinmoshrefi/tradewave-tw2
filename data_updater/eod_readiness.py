"""Deterministic readiness proof for the appserver EOD market-data sync.

The update server exposes per-symbol rows only; it has no batch generation or
completion manifest.  This module therefore builds a bounded local proof from
the terminal rows of the supported US-stock and ETF target populations.  It
also owns the marker fingerprint contract consumed by the ML-score warmer.
"""

from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import json
import re
from typing import Any, Dict, Mapping, Optional, Sequence

import pytz


STATUS_SCHEMA_VERSION = "tw2-eod-readiness-v2"
READINESS_POLICY_VERSION = "us-etf-active-cohort-v1"
REQUIRED_EXCHANGES = ("ETF", "US")
NY_TZ = pytz.timezone("America/New_York")
SESSION_CLOSE = dt.time(16, 0)

# Historical/delisted Wilshire members remain in the resource list, so an
# all-file same-date rule would never become ready.  The population floor makes
# the proof broad, while the recent-cohort ratio catches a partially published
# upstream session.  Values were checked against the existing dev corpus:
# roughly 72% of US targets and 98% of ETF targets are in the recent cohort.
DEFAULT_COVERAGE_POLICY: Mapping[str, Mapping[str, Any]] = {
    "US": {
        "minimum_recent_coverage_ratio": 0.60,
        "minimum_completion_ratio": 0.98,
        "minimum_complete_count": 100,
    },
    "ETF": {
        "minimum_recent_coverage_ratio": 0.90,
        "minimum_completion_ratio": 0.98,
        "minimum_complete_count": 25,
    },
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def terminal_row_fingerprint(values: Sequence[Any]) -> str:
    """Hash the provider-contract terminal row without numpy JSON concerns."""

    normalized = []
    for value in values:
        text = str(value).strip()
        try:
            number = decimal.Decimal(text)
        except decimal.InvalidOperation:
            normalized.append(text)
            continue
        if not number.is_finite():
            normalized.append(text.lower())
        elif number == 0:
            normalized.append("0")
        else:
            normalized.append(format(number.normalize(), "f"))
    return fingerprint(normalized)


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> dt.date:
    first = dt.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    if month == 12:
        first_next_month = dt.date(year + 1, 1, 1)
    else:
        first_next_month = dt.date(year, month + 1, 1)
    last = first_next_month - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> dt.date:
    """Gregorian computus, valid for the modern NYSE calendar."""

    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def _nearest_weekday(day: dt.date) -> dt.date:
    if day.weekday() == 5:
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


def nyse_full_day_holidays(year: int) -> frozenset[dt.date]:
    """Return regular full-day US equity-market holidays for ``year``.

    Unscheduled closures are deliberately absent.  On such a day the coverage
    gate expects a session and fails closed instead of guessing that the prior
    data generation is complete.
    """

    holidays = {
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
        _easter_sunday(year) - dt.timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),  # Memorial Day
        _nearest_weekday(dt.date(year, 7, 4)),  # Independence Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving Day
        _nearest_weekday(dt.date(year, 12, 25)),  # Christmas Day
    }
    if year >= 2022:
        holidays.add(_nearest_weekday(dt.date(year, 6, 19)))

    # NYSE does not observe New Year's Day on the preceding Friday when
    # January 1 falls on Saturday.  A Sunday occurrence is observed Monday.
    new_year = dt.date(year, 1, 1)
    if new_year.weekday() == 6:
        holidays.add(new_year + dt.timedelta(days=1))
    elif new_year.weekday() < 5:
        holidays.add(new_year)
    return frozenset(holidays)


def is_us_equity_session(day: dt.date) -> bool:
    return day.weekday() < 5 and day not in nyse_full_day_holidays(day.year)


def previous_us_equity_session(day: dt.date) -> dt.date:
    candidate = day - dt.timedelta(days=1)
    for _ in range(14):
        if is_us_equity_session(candidate):
            return candidate
        candidate -= dt.timedelta(days=1)
    raise ValueError("could not resolve the prior US equity session")


def latest_completed_us_equity_session(
    now: Optional[dt.datetime] = None,
) -> dt.date:
    """Resolve the latest session whose regular close has already occurred."""

    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = NY_TZ.localize(current)
    local = current.astimezone(NY_TZ)
    candidate = local.date()
    if local.time().replace(tzinfo=None) < SESSION_CLOSE:
        candidate -= dt.timedelta(days=1)
    for _ in range(14):
        if is_us_equity_session(candidate):
            return candidate
        candidate -= dt.timedelta(days=1)
    raise ValueError("could not resolve the latest completed US equity session")


def target_table_date(
    now: Optional[dt.datetime] = None,
) -> dt.date:
    """Return the UI table date targeted by a post-EOD warm.

    After the New York close, the UI's next calendar-day table is the target.
    Before the close it is the current New York calendar date.  Consequently a
    23:05 run and its 00:05/01:05 retries agree across the UTC/local rollover.
    """

    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = NY_TZ.localize(current)
    local = current.astimezone(NY_TZ)
    target = local.date()
    if local.time().replace(tzinfo=None) >= SESSION_CLOSE:
        target += dt.timedelta(days=1)
    return target


def _date_or_none(value: Any) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _normalized_policy(
    policy: Optional[Mapping[str, Mapping[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    selected = policy or DEFAULT_COVERAGE_POLICY
    normalized: Dict[str, Dict[str, Any]] = {}
    for exchange in REQUIRED_EXCHANGES:
        rule = selected.get(exchange, {})
        normalized[exchange] = {
            "minimum_recent_coverage_ratio": float(
                rule.get("minimum_recent_coverage_ratio", 1.0)
            ),
            "minimum_completion_ratio": float(
                rule.get("minimum_completion_ratio", 1.0)
            ),
            "minimum_complete_count": int(rule.get("minimum_complete_count", 1)),
        }
    return normalized


def evaluate_eod_readiness(
    *,
    targets_by_exchange: Mapping[str, Sequence[str]],
    observations: Mapping[str, Mapping[str, Any]],
    completed_session: dt.date,
    resource_ids: Sequence[str],
    policy: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Evaluate broad and internally consistent US/ETF terminal-row evidence.

    Observation keys use ``EXCHANGE:SYMBOL``.  A complete observation has
    ``state='verified'``, an ISO ``terminal_date``, and a SHA-256
    ``terminal_row_fingerprint``.  Every target, including an absent one, is
    incorporated into the generation fingerprint.
    """

    selected_policy = _normalized_policy(policy)
    prior_session = previous_us_equity_session(completed_session)
    completed_iso = completed_session.isoformat()
    prior_iso = prior_session.isoformat()
    normalized_targets: Dict[str, list[str]] = {}
    generation_rows = []
    exchanges: Dict[str, Dict[str, Any]] = {}

    for exchange in REQUIRED_EXCHANGES:
        symbols = sorted(
            {
                str(symbol).strip().upper()
                for symbol in targets_by_exchange.get(exchange, ())
                if str(symbol).strip() and "." not in str(symbol)
            }
        )
        normalized_targets[exchange] = symbols
        target_count = len(symbols)
        recent_count = 0
        complete_count = 0
        future_count = 0
        verified_count = 0
        stale_count = 0
        invalid_count = 0
        recent_date_counts: Dict[str, int] = {}
        state_counts: Dict[str, int] = {}

        for symbol in symbols:
            key = f"{exchange}:{symbol}"
            raw = observations.get(key)
            observation = raw if isinstance(raw, Mapping) else {}
            state = str(observation.get("state") or "not_processed")
            terminal_value = observation.get("terminal_date")
            terminal_day = _date_or_none(terminal_value)
            row_hash = str(observation.get("terminal_row_fingerprint") or "")
            row_hash_valid = bool(_SHA256_RE.fullmatch(row_hash))
            state_counts[state] = state_counts.get(state, 0) + 1

            if state == "verified" and terminal_day is not None and row_hash_valid:
                verified_count += 1
            if terminal_day is None:
                invalid_count += 1
            elif terminal_day < prior_session:
                stale_count += 1
            else:
                recent_count += 1
                terminal_iso = terminal_day.isoformat()
                recent_date_counts[terminal_iso] = (
                    recent_date_counts.get(terminal_iso, 0) + 1
                )
                if terminal_day > completed_session:
                    future_count += 1
                if (
                    terminal_day == completed_session
                    and state == "verified"
                    and row_hash_valid
                ):
                    complete_count += 1

            generation_rows.append(
                [
                    key,
                    terminal_day.isoformat() if terminal_day is not None else "",
                    row_hash if row_hash_valid else "",
                    state,
                ]
            )

        recent_coverage_ratio = _ratio(recent_count, target_count)
        completion_ratio = _ratio(complete_count, recent_count)
        rule = selected_policy[exchange]
        ready = (
            target_count > 0
            and complete_count >= rule["minimum_complete_count"]
            and recent_coverage_ratio
            >= rule["minimum_recent_coverage_ratio"]
            and completion_ratio >= rule["minimum_completion_ratio"]
            and future_count == 0
        )
        exchanges[exchange] = {
            "ready": ready,
            "target_count": target_count,
            "verified_count": verified_count,
            "recent_count": recent_count,
            "complete_count": complete_count,
            "stale_count": stale_count,
            "invalid_count": invalid_count,
            "future_count": future_count,
            "recent_coverage_ratio": recent_coverage_ratio,
            "completion_ratio": completion_ratio,
            "recent_date_counts": dict(sorted(recent_date_counts.items())),
            "state_counts": dict(sorted(state_counts.items())),
            **rule,
        }

    scope_identity = {
        "resource_ids": sorted({str(value) for value in resource_ids}, key=int),
        "targets": normalized_targets,
    }
    scope_fingerprint = fingerprint(scope_identity)
    generation_identity = {
        "completed_session": completed_iso,
        "scope_fingerprint": scope_fingerprint,
        "terminal_rows": sorted(generation_rows),
    }
    generation_fingerprint = fingerprint(generation_identity)
    coverage = {
        "policy_version": READINESS_POLICY_VERSION,
        "required_exchanges": list(REQUIRED_EXCHANGES),
        "completed_session": completed_iso,
        "previous_session": prior_iso,
        "ready": all(exchanges[name]["ready"] for name in REQUIRED_EXCHANGES),
        "exchanges": exchanges,
    }
    completeness_identity = {
        "schema_version": STATUS_SCHEMA_VERSION,
        "completed_session": completed_iso,
        "previous_session": prior_iso,
        "scope_fingerprint": scope_fingerprint,
        "generation_fingerprint": generation_fingerprint,
        "coverage": coverage,
    }
    return {
        "ready": coverage["ready"],
        "completed_session": completed_iso,
        "expected_session_date": completed_iso,
        "previous_session": prior_iso,
        "scope_fingerprint": scope_fingerprint,
        "generation_fingerprint": generation_fingerprint,
        "completeness_fingerprint": fingerprint(completeness_identity),
        "coverage": coverage,
    }


_MARKER_FINGERPRINT_FIELDS = (
    "schema_version",
    "ok",
    "started_at",
    "completed_at",
    "market_date",
    "target_table_date",
    "completed_session",
    "expected_session_date",
    "previous_session",
    "latest_us_date",
    "total",
    "updated",
    "skipped",
    "missing",
    "failed",
    "source",
    "scope_fingerprint",
    "generation_fingerprint",
    "completeness_fingerprint",
    "coverage",
)


def _marker_fingerprint_payload(marker: Mapping[str, Any]) -> Dict[str, Any]:
    return {field: marker.get(field) for field in _MARKER_FINGERPRINT_FIELDS}


def build_status_marker(
    *,
    base: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build a self-verifying status marker bound to one EOD generation."""

    marker = {
        **dict(base),
        "schema_version": STATUS_SCHEMA_VERSION,
        "completed_session": readiness["completed_session"],
        "expected_session_date": readiness["expected_session_date"],
        "previous_session": readiness["previous_session"],
        "scope_fingerprint": readiness["scope_fingerprint"],
        "generation_fingerprint": readiness["generation_fingerprint"],
        "completeness_fingerprint": readiness["completeness_fingerprint"],
        "coverage": readiness["coverage"],
    }
    marker["ok"] = bool(
        readiness.get("ready") is True
        and int(marker.get("failed") or 0) == 0
        and str(marker.get("latest_us_date") or "")
        == str(readiness.get("completed_session") or "")
    )
    marker["readiness_fingerprint"] = fingerprint(
        _marker_fingerprint_payload(marker)
    )
    return marker


def _coverage_is_valid(
    coverage: Any,
    *,
    completed_session: str,
    previous_session: str,
    policy: Mapping[str, Mapping[str, Any]],
) -> bool:
    if not isinstance(coverage, Mapping):
        return False
    if (
        coverage.get("policy_version") != READINESS_POLICY_VERSION
        or coverage.get("required_exchanges") != list(REQUIRED_EXCHANGES)
        or coverage.get("completed_session") != completed_session
        or coverage.get("previous_session") != previous_session
        or coverage.get("ready") is not True
    ):
        return False
    exchanges = coverage.get("exchanges")
    if not isinstance(exchanges, Mapping):
        return False
    for exchange in REQUIRED_EXCHANGES:
        summary = exchanges.get(exchange)
        if not isinstance(summary, Mapping) or summary.get("ready") is not True:
            return False
        try:
            target_count = int(summary["target_count"])
            verified_count = int(summary["verified_count"])
            recent_count = int(summary["recent_count"])
            complete_count = int(summary["complete_count"])
            stale_count = int(summary["stale_count"])
            invalid_count = int(summary["invalid_count"])
            future_count = int(summary["future_count"])
            recent_ratio = float(summary["recent_coverage_ratio"])
            completion_ratio = float(summary["completion_ratio"])
        except (KeyError, TypeError, ValueError):
            return False
        if (
            min(
                target_count,
                verified_count,
                recent_count,
                complete_count,
                stale_count,
                invalid_count,
                future_count,
            )
            < 0
            or verified_count > target_count
            or recent_count > target_count
            or complete_count > recent_count
            or stale_count + invalid_count + recent_count != target_count
            or recent_ratio != _ratio(recent_count, target_count)
            or completion_ratio != _ratio(complete_count, recent_count)
        ):
            return False
        rule = policy[exchange]
        if any(
            summary.get(name) != expected
            for name, expected in rule.items()
        ):
            return False
        expected_ready = (
            target_count > 0
            and complete_count >= rule["minimum_complete_count"]
            and recent_ratio >= rule["minimum_recent_coverage_ratio"]
            and completion_ratio >= rule["minimum_completion_ratio"]
            and future_count == 0
        )
        if not expected_ready:
            return False
        state_counts = summary.get("state_counts")
        if not isinstance(state_counts, Mapping):
            return False
        try:
            normalized_states = {
                str(name): int(value) for name, value in state_counts.items()
            }
            if (
                any(value < 0 for value in normalized_states.values())
                or sum(normalized_states.values()) != target_count
                or verified_count > normalized_states.get("verified", 0)
            ):
                return False
        except (TypeError, ValueError):
            return False
        recent_date_counts = summary.get("recent_date_counts")
        if not isinstance(recent_date_counts, Mapping):
            return False
        normalized_dates: Dict[dt.date, int] = {}
        try:
            for value, count in recent_date_counts.items():
                day = dt.date.fromisoformat(str(value))
                normalized_dates[day] = int(count)
            if (
                any(count < 0 for count in normalized_dates.values())
                or any(
                    day < dt.date.fromisoformat(previous_session)
                    for day in normalized_dates
                )
                or sum(normalized_dates.values()) != recent_count
                or sum(
                    count
                    for day, count in normalized_dates.items()
                    if day > dt.date.fromisoformat(completed_session)
                )
                != future_count
                or complete_count
                > normalized_dates.get(dt.date.fromisoformat(completed_session), 0)
            ):
                return False
        except (TypeError, ValueError):
            return False
    return True


def validate_success_marker(
    marker: Any,
    *,
    expected_market_date: Optional[str] = None,
    expected_target_table_date: Optional[str] = None,
    expected_completed_session: Optional[str] = None,
    policy: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> bool:
    """Verify a successful marker and every recomputable fingerprint link."""

    if not isinstance(marker, Mapping):
        return False
    if marker.get("schema_version") != STATUS_SCHEMA_VERSION or marker.get("ok") is not True:
        return False
    market_day = _date_or_none(marker.get("market_date"))
    target_table_day = _date_or_none(marker.get("target_table_date"))
    completed_day = _date_or_none(marker.get("completed_session"))
    expected_session_day = _date_or_none(marker.get("expected_session_date"))
    previous_day = _date_or_none(marker.get("previous_session"))
    if (
        market_day is None
        or target_table_day is None
        or completed_day is None
        or expected_session_day is None
        or previous_day is None
    ):
        return False
    if (
        completed_day > market_day
        or expected_session_day != completed_day
        or target_table_day not in {market_day, market_day + dt.timedelta(days=1)}
        or previous_day != previous_us_equity_session(completed_day)
    ):
        return False
    if expected_market_date is not None and market_day.isoformat() != expected_market_date:
        return False
    if (
        expected_target_table_date is not None
        and target_table_day.isoformat() != expected_target_table_date
    ):
        return False
    if (
        expected_completed_session is not None
        and completed_day.isoformat() != expected_completed_session
    ):
        return False
    if str(marker.get("latest_us_date") or "") != completed_day.isoformat():
        return False
    try:
        if int(marker.get("failed")) != 0:
            return False
        for field in ("total", "updated", "skipped", "missing"):
            if int(marker.get(field)) < 0:
                return False
    except (TypeError, ValueError):
        return False
    for field in (
        "scope_fingerprint",
        "generation_fingerprint",
        "completeness_fingerprint",
        "readiness_fingerprint",
    ):
        if not _SHA256_RE.fullmatch(str(marker.get(field) or "")):
            return False

    selected_policy = _normalized_policy(policy)
    coverage = marker.get("coverage")
    if not _coverage_is_valid(
        coverage,
        completed_session=completed_day.isoformat(),
        previous_session=previous_day.isoformat(),
        policy=selected_policy,
    ):
        return False
    completeness_identity = {
        "schema_version": STATUS_SCHEMA_VERSION,
        "completed_session": completed_day.isoformat(),
        "previous_session": previous_day.isoformat(),
        "scope_fingerprint": marker["scope_fingerprint"],
        "generation_fingerprint": marker["generation_fingerprint"],
        "coverage": coverage,
    }
    if marker["completeness_fingerprint"] != fingerprint(completeness_identity):
        return False
    return marker["readiness_fingerprint"] == fingerprint(
        _marker_fingerprint_payload(marker)
    )
