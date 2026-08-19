"""Warm commonly viewed US stock/ETF ML scores after authoritative EOD sync.

The job is intentionally bounded. It re-fetches the marker's target calendar
date for six default US stock/ETF table contexts, then adds recently popular
logical contexts. A generation is advertised through an atomic active pointer
only after every selected score has reached a terminal available/unavailable
state.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote

import jwt
import redis
import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
APPSERVER_MODULE_DIR = REPO_ROOT / "appserver" / "appserver"
for search_path in (str(REPO_ROOT), str(APPSERVER_MODULE_DIR)):
    if search_path not in sys.path:
        sys.path.insert(0, search_path)

import config  # noqa: E402
from data_updater.eod_readiness import (  # noqa: E402
    latest_completed_us_equity_session,
    target_table_date,
    validate_success_marker,
)
from ml_checkpoint_context import (  # noqa: E402
    ALLOWED_RESOURCE_IDS,
    CACHE_SCHEMA_VERSION,
    CONTEXT_CONTRACT_VERSION,
    DEFAULT_CONSECUTIVE_CONTEXTS,
    CheckpointContextError,
    CheckpointProviderError,
    CheckpointScoringService,
    build_checkpoint_plan,
    build_usage_context,
    metadata_fingerprint,
    model_days_out_for_source,
    normalize_legacy_score_result,
    normalize_scorer_metadata,
    ranked_usage_contexts,
    read_cached_legacy_score,
    valid_scorer_metadata,
    write_cached_legacy_score,
)


DEFAULT_STATUS_FILE = "/var/lib/tradewave/eod/update_status.json"
ACTIVE_GENERATION_KEY = f"{CACHE_SCHEMA_VERSION}:prefetch:active"
GENERATION_RETENTION_SECONDS = 21 * 24 * 60 * 60
_REQUIRED_SCORER_IDENTITY_FIELDS = (
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


def _json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _decode_json(raw: Any) -> Optional[Any]:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError):
        return None


class _StagedPipeline:
    """Minimal Redis pipeline used by checkpoint cache writes during warming."""

    def __init__(self, publication: "_StagedCachePublication") -> None:
        self.publication = publication
        self.calls: List[Tuple[str, Any, Optional[int]]] = []

    def set(self, key: str, value: Any, *, ex: Optional[int] = None) -> "_StagedPipeline":
        self.calls.append((str(key), value, ex))
        return self

    def execute(self) -> List[Any]:
        return self.publication._stage_many(self.calls)


class _StagedCachePublication:
    """Keep EOD-warmed score records invisible until one final transaction.

    Interactive score requests continue to use the ordinary Redis client and
    publish on demand.  Only the EOD warmer receives this proxy.  Cache reads
    made by that warmer see its own generation-scoped staged records first;
    every other reader continues to see the previously published live keys.
    """

    _VERSIONED_SCORE_PREFIXES = (
        f"{CACHE_SCHEMA_VERSION}:legacy:value:",
        f"{CACHE_SCHEMA_VERSION}:legacy:index:",
        f"{CACHE_SCHEMA_VERSION}:checkpoint:value:",
        f"{CACHE_SCHEMA_VERSION}:checkpoint:index:",
    )

    def __init__(self, redis_client: Any, generation_id: str) -> None:
        self._redis = redis_client
        self._stage_prefix = (
            f"{CACHE_SCHEMA_VERSION}:prefetch:staged:{generation_id}:"
        )
        self._staged_live_keys: set[str] = set()

    @property
    def staged_count(self) -> int:
        return len(self._staged_live_keys)

    @staticmethod
    def _value_text(value: Any) -> str:
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise CheckpointProviderError(
                    "staged cache value must be UTF-8 JSON"
                ) from exc
        if isinstance(value, str):
            return value
        raise CheckpointProviderError("staged cache value must be JSON text")

    def _is_score_cache_key(self, key: str) -> bool:
        # ml4 remains intercepted while older callers coexist; new exact-window
        # writes use the same model/data-versioned value+pointer shape as the
        # checkpoint cache.
        return key.startswith("ml4_") or key.startswith(self._VERSIONED_SCORE_PREFIXES)

    def _stage_key(self, live_key: str) -> str:
        digest = hashlib.sha256(live_key.encode("utf-8")).hexdigest()
        return f"{self._stage_prefix}{digest}"

    def _stage_record(
        self,
        live_key: str,
        value: Any,
        ttl_seconds: Optional[int],
    ) -> Dict[str, Any]:
        value_text = self._value_text(value)
        ttl = max(int(ttl_seconds or 0), 60)
        identity = {
            "live_key": live_key,
            "value": value_text,
            "ttl_seconds": ttl,
        }
        return {
            **identity,
            "record_hash": _hash(identity),
        }

    def _read_stage_record(self, live_key: str) -> Optional[Dict[str, Any]]:
        record = _decode_json(self._redis.get(self._stage_key(live_key)))
        if not isinstance(record, Mapping):
            return None
        try:
            identity = {
                "live_key": str(record["live_key"]),
                "value": self._value_text(record["value"]),
                "ttl_seconds": max(int(record["ttl_seconds"]), 60),
            }
        except (KeyError, TypeError, ValueError, CheckpointProviderError):
            return None
        if identity["live_key"] != live_key:
            return None
        if str(record.get("record_hash") or "") != _hash(identity):
            return None
        return identity

    def _stage_many(
        self,
        calls: Sequence[Tuple[str, Any, Optional[int]]],
    ) -> List[Any]:
        pipeline = self._redis.pipeline(transaction=True)
        staged_keys: List[Optional[str]] = []
        for key, value, ttl_seconds in calls:
            if self._is_score_cache_key(key):
                record = self._stage_record(key, value, ttl_seconds)
                pipeline.set(
                    self._stage_key(key),
                    _json(record),
                    ex=GENERATION_RETENTION_SECONDS,
                )
                staged_keys.append(key)
            else:
                # Scorer health metadata is not a selected score result and may
                # retain its ordinary short-lived cache behavior.
                pipeline.set(key, value, ex=ttl_seconds)
                staged_keys.append(None)
        results = pipeline.execute()
        for index, live_key in enumerate(staged_keys):
            if live_key is not None and index < len(results) and results[index] is True:
                self._staged_live_keys.add(live_key)
        return list(results)

    def get(self, key: str) -> Any:
        live_key = str(key)
        if self._is_score_cache_key(live_key):
            staged = self._read_stage_record(live_key)
            if staged is not None:
                return staged["value"].encode("utf-8")
        return self._redis.get(key)

    def set(self, key: str, value: Any, *, ex: Optional[int] = None) -> Any:
        live_key = str(key)
        if not self._is_score_cache_key(live_key):
            return self._redis.set(key, value, ex=ex)
        results = self._stage_many([(live_key, value, ex)])
        return results[0] if results else False

    def pipeline(self, transaction: bool = True) -> _StagedPipeline:
        if transaction is not True:
            raise CheckpointProviderError("staged cache writes must be transactional")
        return _StagedPipeline(self)

    def lock(self, *args: Any, **kwargs: Any) -> Any:
        return self._redis.lock(*args, **kwargs)

    def publish(
        self,
        *,
        manifest_key: str,
        manifest: Mapping[str, Any],
        active_key: str,
        active_pointer: Mapping[str, Any],
    ) -> None:
        """Atomically expose every staged score key and the complete manifest."""

        staged: List[Dict[str, Any]] = []
        for live_key in sorted(self._staged_live_keys):
            record = self._read_stage_record(live_key)
            if record is None:
                raise CheckpointProviderError(
                    "staged cache verification failed before publication"
                )
            staged.append(record)

        pipeline = self._redis.pipeline(transaction=True)
        for record in staged:
            pipeline.set(
                record["live_key"],
                record["value"],
                ex=record["ttl_seconds"],
            )
        pipeline.set(
            manifest_key,
            _json(manifest),
            ex=GENERATION_RETENTION_SECONDS,
        )
        pipeline.set(
            active_key,
            _json(active_pointer),
            ex=GENERATION_RETENTION_SECONDS,
        )
        results = pipeline.execute()
        if len(results) != len(staged) + 2 or not all(result is True for result in results):
            raise CheckpointProviderError("atomic staged-cache publication failed")


def _positive_env_int(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(max(value, 1), maximum)


def _valid_prefetch_metadata(metadata: Any) -> bool:
    """Require a complete V3/62 scorer identity before warming any score."""

    return valid_scorer_metadata(metadata)


def _live_scorer_metadata(
    *,
    http_client: Any,
    scorer_url: str,
) -> Optional[Dict[str, str]]:
    """Fetch scorer identity directly, bypassing the 60-second Redis cache."""

    response = http_client.get(f"{scorer_url.rstrip('/')}/health", timeout=3)
    if response.status_code != 200:
        return None
    payload = response.json()
    if not isinstance(payload, Mapping):
        return None
    metadata = normalize_scorer_metadata(payload.get("metadata", payload))
    return metadata if _valid_prefetch_metadata(metadata) else None


def _read_authoritative_status(
    path: str,
    *,
    now: Optional[dt.datetime] = None,
) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as handle:
            status = json.load(handle)
    except (OSError, ValueError):
        return None
    expected_target = target_table_date(now).isoformat()
    expected_session = latest_completed_us_equity_session(now).isoformat()
    if not validate_success_marker(
        status,
        expected_target_table_date=expected_target,
        expected_completed_session=expected_session,
    ):
        return None
    return dict(status)


def _local_appserver_url() -> str:
    explicit = os.environ.get("TW2_ML_PREFETCH_APPSERVER_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    environment = os.environ.get("TW2_ENV", "").strip().lower()
    if environment in {"staging", "prod"}:
        return "http://127.0.0.1"
    return "http://127.0.0.1:5000"


def _prefetch_token() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode(
        {
            "user": "ml-prefetch",
            "user_level": "6",
            "lid": sorted(ALLOWED_RESOURCE_IDS),
            "ipv4": "127.0.0.1",
            "country_code": "US",
            "zip": "prefetch",
            "is_admin": True,
            "is_service_account": True,
            "aud": "tw2-appserver",
            "iss": "tw2-web",
            "iat": now,
            "exp": now + dt.timedelta(minutes=30),
        },
        config.APPSERVER_JWT_SECRET,
        algorithm="HS256",
    )


def _empty_seed_context(
    resource_id: str,
    table_context: Mapping[str, Any],
) -> Dict[str, Any]:
    identity = {
        "resource_id": resource_id,
        "table_context": dict(table_context),
        "opportunity_set_hash": _hash([]),
    }
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        **identity,
        "is_default": table_context.get("is_default") is True,
        "opportunities": [],
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "context_hash": _hash(identity),
        "seeded": True,
    }


_PE_LOOKBACK_RE = re.compile(r"^pe[0-3]-([1-9][0-9]*)$", re.I)
_DISPLAY_DAY_RANGE_RE = re.compile(r"^([1-9][0-9]{0,2})-([1-9][0-9]{0,2})$")


def _target_date(value: Any) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("target_table_date must use YYYY-MM-DD") from exc


def _partial_years(value: Any) -> str:
    selected = value
    if isinstance(value, Mapping):
        selected = value.get(
            "min_winning_years",
            value.get("partialYears", value.get("selection")),
        )
    text = str(selected or "").strip()
    if not text.isdigit() or not 1 <= int(text) <= 100:
        raise ValueError("partial years must be an integer string from 1 through 100")
    return str(int(text))


def _logical_table_context(
    context: Mapping[str, Any],
    *,
    target: dt.date,
) -> Dict[str, Any]:
    """Normalize one saved view into a date-independent OppList4 query."""

    resource_id = str(context.get("resource_id") or "")
    if resource_id not in ALLOWED_RESOURCE_IDS:
        raise ValueError("unsupported prefetch resource")
    source = context.get("table_context")
    if not isinstance(source, Mapping):
        raise ValueError("prefetch context is missing table_context")
    mode = "pe" if str(source.get("mode") or "").lower().startswith("pe") else "consecutive"
    years_value = source.get("years")
    if not isinstance(years_value, str):
        raise ValueError("years must remain a string")
    years = years_value.strip().lower()
    pe_match = _PE_LOOKBACK_RE.fullmatch(years)
    if pe_match is not None:
        if mode != "pe":
            raise ValueError("PE cycle years require PE mode")
        years = pe_match.group(1)
    if not years.isdigit() or int(years) <= 0:
        raise ValueError("years must be a positive lookback string")
    years = str(int(years))
    partial_years = _partial_years(source.get("partial"))
    displayed_range = str(source.get("day_range") or "-").strip()
    if displayed_range != "-":
        match = _DISPLAY_DAY_RANGE_RE.fullmatch(displayed_range)
        if match is None:
            raise ValueError("invalid displayed day range")
        start, end = int(match.group(1)), int(match.group(2))
        if not 1 <= start <= end <= 367:
            raise ValueError("displayed day range is outside the supported range")
        displayed_range = f"{start}-{end}"
    is_default = (
        source.get("is_default") is True or context.get("is_default") is True
    )
    table_context = {
        "years": years,
        "partial": {
            "min_winning_years": partial_years,
            "mode": mode,
        },
        "mode": mode,
        "date": target.isoformat(),
        "day_range": displayed_range,
        "is_default": is_default,
    }
    result = {
        "resource_id": resource_id,
        "table_context": table_context,
    }
    if context.get("views") is not None:
        try:
            result["views"] = max(float(context["views"]), 0.0)
        except (TypeError, ValueError):
            result["views"] = 0.0
    return result


def _default_logical_contexts(target: dt.date) -> List[Dict[str, Any]]:
    contexts: List[Dict[str, Any]] = []
    for resource_id in sorted(ALLOWED_RESOURCE_IDS, key=int):
        years, partial_years = DEFAULT_CONSECUTIVE_CONTEXTS[resource_id]
        contexts.append(
            _logical_table_context(
                {
                    "resource_id": resource_id,
                    "is_default": True,
                    "table_context": {
                        "years": years,
                        "partial": partial_years,
                        "mode": "consecutive",
                        "day_range": "-",
                        "is_default": True,
                    },
                },
                target=target,
            )
        )
    return contexts


def _logical_context_key(context: Mapping[str, Any]) -> str:
    table = context["table_context"]
    identity = {
        "resource_id": context["resource_id"],
        "years": table["years"],
        "partial": table["partial"],
        "mode": table["mode"],
        "day_range": table["day_range"],
    }
    return _hash(identity)


def _dedupe_logical_contexts(
    defaults: Sequence[Mapping[str, Any]],
    popular: Sequence[Mapping[str, Any]],
    *,
    target: dt.date,
    popular_limit: int,
) -> List[Dict[str, Any]]:
    """Retarget saved views and rank equivalent logical queries together."""

    selected: List[Dict[str, Any]] = []
    seen = set()
    for context in defaults:
        try:
            normalized = _logical_table_context(context, target=target)
        except (TypeError, ValueError):
            continue
        key = _logical_context_key(normalized)
        if key not in seen:
            selected.append(normalized)
            seen.add(key)

    aggregated: Dict[str, Dict[str, Any]] = {}
    for context in popular:
        try:
            normalized = _logical_table_context(context, target=target)
        except (TypeError, ValueError):
            continue
        key = _logical_context_key(normalized)
        if key in seen:
            continue
        views = float(normalized.get("views") or 0.0)
        if key not in aggregated:
            normalized["views"] = views
            normalized["table_context"]["is_default"] = False
            aggregated[key] = normalized
        else:
            aggregated[key]["views"] = float(aggregated[key]["views"]) + views
    ranked = sorted(
        aggregated.values(),
        key=lambda item: (-float(item.get("views") or 0), _logical_context_key(item)),
    )
    selected.extend(ranked[: max(int(popular_limit), 0)])
    return selected


def _opplist_engine_day_range(displayed_range: Any) -> Optional[str]:
    """Convert the displayed inclusive-day range at the OppList4 boundary."""

    text = str(displayed_range or "-").strip()
    if text == "-":
        return "-"
    match = _DISPLAY_DAY_RANGE_RE.fullmatch(text)
    if match is None:
        raise ValueError("invalid displayed day range")
    # Entry day is calendar day 1, while OppList4 stores the zero-based engine
    # offset. Intersect with the TradeWave source range of 1..367 days. Source
    # rows under 10 days are later mapped to V3's 10-day scoring identity.
    raw_start = max(int(match.group(1)) - 1, 0)
    raw_end = min(int(match.group(2)) - 1, 366)
    if raw_start > raw_end:
        return None
    return f"{raw_start}-{raw_end}"


def fetch_target_contexts(
    *,
    logical_contexts: Sequence[Mapping[str, Any]],
    target: dt.date,
    http_client: Any,
    appserver_url: str,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Re-fetch logical default/popular views for one target calendar date."""

    month = calendar.month_name[target.month]
    day = str(target.day)
    token = _prefetch_token()
    contexts: List[Dict[str, Any]] = []
    failures: List[str] = []

    for raw_context in logical_contexts:
        try:
            logical = _logical_table_context(raw_context, target=target)
            resource_id = logical["resource_id"]
            table_context = logical["table_context"]
            years = table_context["years"]
            partial_years = table_context["partial"]["min_winning_years"]
            mode = table_context["mode"]
            engine_range = _opplist_engine_day_range(table_context["day_range"])
        except (KeyError, TypeError, ValueError) as exc:
            failures.append(f"logical context: {type(exc).__name__}")
            continue
        if engine_range is None:
            contexts.append(_empty_seed_context(resource_id, table_context))
            continue
        url = (
            f"{appserver_url}/OppList4/{resource_id}/{quote(month)}/{day}/"
            f"{years}/{partial_years}/{engine_range}/0/0"
        )
        try:
            response = http_client.get(
                url,
                params={
                    "mode": mode,
                    "token": token,
                    "target_date": target.isoformat(),
                },
                timeout=90,
            )
            if response.status_code != 200:
                failures.append(
                    f"target resource {resource_id}: HTTP {response.status_code}"
                )
                contexts.append(_empty_seed_context(resource_id, table_context))
                continue
            payload = response.json()
            rows = payload.get("OppList") if isinstance(payload, Mapping) else None
            if not isinstance(rows, list):
                failures.append(f"target resource {resource_id}: invalid OppList")
                contexts.append(_empty_seed_context(resource_id, table_context))
                continue
            opportunities = []
            for row in rows:
                if not isinstance(row, list) or len(row) < 4:
                    continue
                try:
                    entry = dt.date.fromisoformat(str(row[0]))
                    raw_days = int(row[2])
                except (TypeError, ValueError):
                    continue
                # OppList4 may consolidate weekend/holiday rows. Never warm a
                # current-condition score for a row whose entry has passed.
                if entry < target:
                    continue
                opportunities.append({
                    "date": entry.isoformat(),
                    "symbol": str(row[1]).upper(),
                    # OppList4 returns the engine offset. The React display adds
                    # one and removes it again before MLScoreBatch.
                    "daysOut": raw_days,
                    "direction": (
                        "l" if str(row[3]).lower().startswith("l") else "s"
                    ),
                    "years": years,
                    "partial": table_context["partial"],
                    "mode": mode,
                    "selection_origin": "scanner",
                })
            detail = build_usage_context(
                resource_id,
                {
                    "table_context": table_context,
                    "opportunities": opportunities,
                },
                # Browser usage telemetry deliberately stores at most 100 rows.
                # This trusted authoritative refetch must retain every validated
                # default row so the later 2,500-row selection fence, not the
                # telemetry snapshot cap, owns warm coverage.
                stored_row_limit=len(opportunities),
            )
            if detail is None:
                detail = _empty_seed_context(resource_id, table_context)
            else:
                detail["is_default"] = table_context.get("is_default") is True
                detail["seeded"] = True
            if logical.get("views") is not None:
                detail["views"] = logical["views"]
            contexts.append(detail)
        except Exception as exc:
            failures.append(
                f"target resource {resource_id}: {type(exc).__name__}"
            )
            contexts.append(_empty_seed_context(resource_id, table_context))
    return contexts, failures


def fetch_default_contexts(
    *,
    status: Mapping[str, Any],
    http_client: Any,
    appserver_url: str,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Compatibility wrapper for callers that seed only the six defaults."""

    target = _target_date(status["target_table_date"])
    return fetch_target_contexts(
        logical_contexts=_default_logical_contexts(target),
        target=target,
        http_client=http_client,
        appserver_url=appserver_url,
    )


def _normalized_eligible_opportunity(
    resource_id: str,
    opportunity: Any,
    *,
    minimum_entry_date: Optional[dt.date],
) -> Optional[Tuple[Tuple[Any, ...], Dict[str, Any]]]:
    if not isinstance(opportunity, Mapping):
        return None
    if minimum_entry_date is not None:
        try:
            entry_date = dt.date.fromisoformat(
                str(opportunity.get("date") or "")
            )
        except ValueError:
            return None
        if entry_date < minimum_entry_date:
            return None
    raw_days = opportunity.get("daysOut")
    if isinstance(raw_days, bool):
        return None
    try:
        numeric_days = float(str(raw_days).strip())
    except (TypeError, ValueError):
        return None
    if not numeric_days.is_integer():
        return None
    days_out = int(numeric_days)
    # OppList4 supplies the analytics-engine offset. Eligible source windows
    # are 1..367 inclusive calendar days, hence raw 0..366.
    if not 0 <= days_out <= 366:
        return None
    identity = (
        resource_id,
        str(opportunity.get("symbol") or ""),
        str(opportunity.get("date") or ""),
        str(days_out),
        str(opportunity.get("direction") or ""),
        _json(opportunity.get("years")),
        _json(opportunity.get("partial")),
    )
    normalized = dict(opportunity)
    normalized["daysOut"] = days_out
    return identity, normalized


def _select_opportunities_with_coverage(
    contexts: Sequence[Mapping[str, Any]],
    *,
    popular_rows_per_context: int,
    popular_max_rows: int,
    max_total_rows: int,
    minimum_entry_date: Optional[dt.date] = None,
) -> Tuple[List[Tuple[str, Dict[str, Any]]], Dict[str, Any]]:
    """Select defaults first and report every bounded-coverage tradeoff."""

    selected: List[Tuple[str, Dict[str, Any]]] = []
    seen = set()
    counts = {
        "default": {"eligible_rows": 0, "selected_rows": 0},
        "popular": {"eligible_rows": 0, "selected_rows": 0},
    }
    popular_selected = 0

    # Defaults always get first use of the global safety budget regardless of
    # input ordering. Popular views remain bounded per context and in aggregate.
    for default_group in (True, False):
        for context in contexts:
            if (context.get("is_default") is True) is not default_group:
                continue
            resource_id = str(context.get("resource_id") or "")
            if resource_id not in ALLOWED_RESOURCE_IDS:
                continue
            rows = context.get("opportunities")
            if not isinstance(rows, list):
                continue
            selected_in_context = 0
            group_name = "default" if default_group else "popular"
            for opportunity in rows:
                eligible = _normalized_eligible_opportunity(
                    resource_id,
                    opportunity,
                    minimum_entry_date=minimum_entry_date,
                )
                if eligible is None:
                    continue
                identity, normalized = eligible
                if identity in seen:
                    continue
                seen.add(identity)
                counts[group_name]["eligible_rows"] += 1

                within_context = (
                    default_group
                    or selected_in_context < popular_rows_per_context
                )
                within_popular_total = (
                    default_group or popular_selected < popular_max_rows
                )
                if (
                    not within_context
                    or not within_popular_total
                    or len(selected) >= max_total_rows
                ):
                    continue
                selected.append((resource_id, normalized))
                selected_in_context += 1
                counts[group_name]["selected_rows"] += 1
                if not default_group:
                    popular_selected += 1

    for group in counts.values():
        group["truncated_rows"] = max(
            group["eligible_rows"] - group["selected_rows"], 0
        )
        group["truncated"] = group["truncated_rows"] > 0
    eligible_rows = sum(group["eligible_rows"] for group in counts.values())
    selected_rows = len(selected)
    coverage = {
        "eligible_rows": eligible_rows,
        "selected_rows": selected_rows,
        "truncated_rows": max(eligible_rows - selected_rows, 0),
        "truncated": eligible_rows > selected_rows,
        "default": counts["default"],
        "popular": counts["popular"],
        "limits": {
            "global_max_rows": max_total_rows,
            "popular_rows_per_context": popular_rows_per_context,
            "popular_max_rows": popular_max_rows,
        },
    }
    return selected, coverage


def _selected_opportunities(
    contexts: Sequence[Mapping[str, Any]],
    *,
    rows_per_context: int,
    max_total_rows: int,
    minimum_entry_date: Optional[dt.date] = None,
) -> List[Tuple[str, Dict[str, Any]]]:
    """Compatibility wrapper used by focused selection tests."""

    selected, _coverage = _select_opportunities_with_coverage(
        contexts,
        popular_rows_per_context=rows_per_context,
        popular_max_rows=max_total_rows,
        max_total_rows=max_total_rows,
        minimum_entry_date=minimum_entry_date,
    )
    return selected


def _legacy_tier(days_out: int) -> Optional[str]:
    # Source patterns span 1..90 inclusive calendar days here. V3's minimum
    # model horizon is 10 days, so raw offsets 0..8 share scoring offset 9.
    if not 0 <= days_out <= 89:
        return None
    scoring_days_out = model_days_out_for_source(days_out)
    if scoring_days_out <= 30:
        return "10_30"
    if scoring_days_out <= 60:
        return "31_60"
    return "61_90"


def _terminal_legacy_score(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply the same bounded contract used by interactive appserver reads."""

    return normalize_legacy_score_result(result)


def warm_legacy_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    redis_client: Any,
    http_client: Any,
    scorer_url: str,
    expected_metadata: Mapping[str, Any],
    ttl_seconds: int,
    request_batch_size: int,
) -> Tuple[int, List[str]]:
    by_tier: Dict[
        str,
        Dict[Tuple[str, str, int, str], List[Mapping[str, Any]]],
    ] = {}
    for opportunity in rows:
        tier = _legacy_tier(int(opportunity["daysOut"]))
        if tier is not None:
            scoring_identity = (
                str(opportunity["symbol"]),
                str(opportunity["date"]),
                model_days_out_for_source(opportunity["daysOut"]),
                str(opportunity["direction"]),
            )
            by_tier.setdefault(tier, {}).setdefault(
                scoring_identity, []
            ).append(opportunity)
    completed = 0
    failures: List[str] = []
    for tier, tier_groups in by_tier.items():
        groups = list(tier_groups.items())
        for start in range(0, len(groups), request_batch_size):
            batch = groups[start : start + request_batch_size]
            provider_rows = [
                {
                    "symbol": identity[0],
                    "date": identity[1],
                    "daysOut": identity[2],
                    "direction": identity[3],
                }
                for identity, _source_rows in batch
            ]
            try:
                response = http_client.post(
                    f"{scorer_url.rstrip('/')}/score",
                    json={"opportunities": provider_rows, "tier": tier},
                    timeout=60,
                )
                if response.status_code != 200:
                    failures.append(f"legacy {tier}: HTTP {response.status_code}")
                    continue
                payload = response.json()
                results = payload.get("results") if isinstance(payload, Mapping) else None
                if not isinstance(results, list):
                    failures.append(f"legacy {tier}: invalid response")
                    continue
                response_metadata = payload.get("metadata")
                if (
                    not valid_scorer_metadata(response_metadata)
                    or metadata_fingerprint(response_metadata)
                    != metadata_fingerprint(expected_metadata)
                ):
                    failures.append(f"legacy {tier}: scorer metadata mismatch")
                    continue
                result_map = {
                    (
                        str(item.get("symbol") or ""),
                        str(item.get("date") or ""),
                        int(item.get("daysOut") or 0),
                        str(item.get("direction") or ""),
                    ): item
                    for item in results
                    if isinstance(item, Mapping)
                }
                for identity, source_rows in batch:
                    result = result_map.get(identity)
                    if result is None:
                        failures.append(
                            f"legacy {tier}: missing {identity[0]} {identity[2]}"
                        )
                        continue
                    try:
                        score = _terminal_legacy_score(result)
                    except (ValueError, CheckpointProviderError) as exc:
                        failures.append(f"legacy {tier}: {exc}")
                        continue
                    error = score.get("error") if isinstance(score, Mapping) else None
                    if (
                        score.get("status") == "unavailable"
                        and isinstance(error, Mapping)
                        and error.get("retryable") is True
                    ):
                        failures.append(
                            f"legacy {tier}: retryable provider state for "
                            f"{identity[0]} {identity[2]}"
                        )
                        continue
                    try:
                        write_cached_legacy_score(
                            redis_client,
                            identity[0],
                            identity[1],
                            identity[2],
                            identity[3],
                            score,
                            metadata=response_metadata,
                            ttl_seconds=ttl_seconds,
                        )
                        round_trip = read_cached_legacy_score(
                            redis_client,
                            identity[0],
                            identity[1],
                            identity[2],
                            identity[3],
                            expected_metadata=expected_metadata,
                        )
                    except CheckpointProviderError as exc:
                        failures.append(f"legacy {tier}: cache verification failed ({exc})")
                        continue
                    if round_trip != score:
                        failures.append(
                            f"legacy {tier}: cache verification failed for "
                            f"{identity[0]} {identity[2]}"
                        )
                        continue
                    completed += len(source_rows)
            except Exception as exc:
                failures.append(f"legacy {tier}: {type(exc).__name__}")
    return completed, failures


def warm_checkpoint_rows(
    rows: Sequence[Tuple[str, Mapping[str, Any]]],
    *,
    service: CheckpointScoringService,
    row_batch_size: int,
) -> Tuple[int, List[str]]:
    plans = []
    failures: List[str] = []
    for resource_id, opportunity in rows:
        try:
            plans.append(build_checkpoint_plan(resource_id, opportunity))
        except CheckpointContextError as exc:
            failures.append(
                f"checkpoint {opportunity.get('symbol')}: {str(exc)[:120]}"
            )
    completed = 0
    for start in range(0, len(plans), row_batch_size):
        batch = plans[start : start + row_batch_size]
        bundles = service.score_bundles(
            batch,
            max_request_items=sum(
                len(plan.get("requests") or ()) for plan in batch
            ),
        )
        for plan in batch:
            bundle = bundles.get(plan["ui_key"])
            if bundle is None:
                failures.append(f"checkpoint {plan['ui_key']}: provider incomplete")
                continue
            retryable = any(
                isinstance(item, Mapping)
                and item.get("status") == "unavailable"
                and isinstance(item.get("error"), Mapping)
                and item["error"].get("retryable") is True
                for item in bundle.get("horizons") or ()
            )
            if retryable:
                failures.append(
                    f"checkpoint {plan['ui_key']}: retryable provider state"
                )
                continue
            try:
                published = service.cached_bundle(plan)
            except Exception as exc:
                failures.append(
                    f"checkpoint {plan['ui_key']}: cache verification failed "
                    f"({type(exc).__name__})"
                )
                continue
            if published is None:
                failures.append(
                    f"checkpoint {plan['ui_key']}: cache verification failed"
                )
                continue
            completed += 1
    return completed, failures


def _write_manifest(
    redis_client: Any,
    key: str,
    payload: Mapping[str, Any],
) -> None:
    redis_client.set(key, _json(payload), ex=GENERATION_RETENTION_SECONDS)


def run_prefetch(
    *,
    status_file: str,
    redis_client: Any,
    http_client: Any,
    now: Optional[dt.datetime] = None,
) -> int:
    status = _read_authoritative_status(status_file, now=now)
    if status is None:
        print("ML prefetch deferred: authoritative EOD success marker is absent.")
        return 0
    target = _target_date(status["target_table_date"])
    scorer_url = str(config.ml_scorer_url or "").rstrip("/")
    if not scorer_url:
        print("ML prefetch failed: TW2_ML_SCORER_URL is not configured.")
        return 1

    ttl_seconds = _positive_env_int("TW2_ML_PREFETCH_TTL_SECONDS", 172800, 604800)
    metadata_service = CheckpointScoringService(
        redis_client=redis_client,
        scorer_url=scorer_url,
        http_client=http_client,
        ttl_seconds=ttl_seconds,
        request_timeout=60,
        scorer_mode=config.ml_scorer_mode,
    )
    try:
        metadata = metadata_service.scorer_metadata()
    except Exception as exc:
        print(f"ML prefetch failed: scorer metadata unavailable ({type(exc).__name__}).")
        return 1
    if metadata is None:
        try:
            legacy_metadata = metadata_service.legacy_scorer_metadata()
        except Exception as exc:
            print(f"ML prefetch failed: scorer metadata unavailable ({type(exc).__name__}).")
            return 1
        if normalize_scorer_metadata(legacy_metadata).get("scorer_mode") == "v2":
            print("ML prefetch deferred: V2 supports live exact scoring but not V3 context warming.")
            return 0
    if not _valid_prefetch_metadata(metadata):
        print("ML prefetch failed: scorer metadata is incomplete or not V3/62.")
        return 1
    scorer_data_as_of = str(metadata.get("data_as_of") or "")
    completed_session = str(status["completed_session"])
    latest_us_date = str(status["latest_us_date"])
    if not (
        scorer_data_as_of == completed_session == latest_us_date
    ):
        print(
            "ML prefetch failed: scorer data_as_of does not match the "
            "authoritative EOD session."
        )
        return 1
    data_alignment = {
        "aligned": True,
        "scorer_data_as_of": scorer_data_as_of,
        "eod_completed_session": completed_session,
        "latest_us_date": latest_us_date,
    }
    scorer_fingerprint = metadata_fingerprint(metadata)
    popular_limit = _positive_env_int("TW2_ML_PREFETCH_POPULAR_CONTEXTS", 8, 50)
    usage_days = _positive_env_int("TW2_ML_PREFETCH_USAGE_DAYS", 14, 30)
    # Usage telemetry retains at most 100 rows for one logical view. Keep a
    # selected popular view whole up to that same bound; the separate 180-row
    # popular aggregate and 2,500-row global limits still own total work. A
    # smaller per-view default left the most-viewed 39-row table partly cold.
    rows_per_context = _positive_env_int(
        "TW2_ML_PREFETCH_ROWS_PER_CONTEXT", 100, 100
    )
    # The historical MAX_ROWS setting bounded the entire job and left most
    # default-table rows cold. Retain it as a popular-view cap only; defaults
    # now receive first use of a separate explicit global safety budget.
    legacy_popular_max = _positive_env_int(
        "TW2_ML_PREFETCH_MAX_ROWS", 180, 1000
    )
    popular_max_rows = _positive_env_int(
        "TW2_ML_PREFETCH_POPULAR_MAX_ROWS", legacy_popular_max, 1000
    )
    global_max_rows = _positive_env_int(
        "TW2_ML_PREFETCH_GLOBAL_MAX_ROWS", 2500, 5000
    )
    legacy_batch_size = _positive_env_int(
        "TW2_ML_PREFETCH_LEGACY_BATCH_SIZE", 25, 100
    )
    checkpoint_row_batch = _positive_env_int(
        "TW2_ML_PREFETCH_CHECKPOINT_ROW_BATCH", 10, 20
    )
    selection_policy = {
        "popular_contexts": popular_limit,
        "usage_days": usage_days,
        "popular_rows_per_context": rows_per_context,
        "popular_max_rows": popular_max_rows,
        "global_max_rows": global_max_rows,
        "legacy_batch_size": legacy_batch_size,
        "checkpoint_row_batch": checkpoint_row_batch,
    }
    policy_fingerprint = _hash(selection_policy)
    active = _decode_json(redis_client.get(ACTIVE_GENERATION_KEY))
    if (
        isinstance(active, Mapping)
        and str(active.get("contract_version") or "")
        == CONTEXT_CONTRACT_VERSION
        and str(active.get("latest_us_date") or "") == str(status["latest_us_date"])
        and str(active.get("target_table_date") or "")
        == str(status["target_table_date"])
        and str(active.get("scorer_data_as_of") or "") == scorer_data_as_of
        and str(active.get("eod_generation_fingerprint") or "")
        == str(status["generation_fingerprint"])
        and str(active.get("eod_completeness_fingerprint") or "")
        == str(status["completeness_fingerprint"])
        and str(active.get("eod_readiness_fingerprint") or "")
        == str(status["readiness_fingerprint"])
        and str(active.get("scorer_fingerprint") or "") == scorer_fingerprint
        and str(active.get("policy_fingerprint") or "") == policy_fingerprint
    ):
        active_manifest = _decode_json(
            redis_client.get(str(active.get("manifest_key") or ""))
        )
        if (
            isinstance(active_manifest, Mapping)
            and active_manifest.get("status") == "complete"
        ):
            print(
                "ML prefetch already complete for current US data and scorer "
                f"generation {str(active.get('generation_id') or '')[:12]}."
            )
            return 0

    popular_snapshots = ranked_usage_contexts(
        redis_client,
        days=usage_days,
        # Equivalent table queries from multiple old dates are aggregated
        # below, so read enough exact snapshots to fill the bounded logical set.
        limit=max(popular_limit * 5, popular_limit),
    )
    logical_contexts = _dedupe_logical_contexts(
        _default_logical_contexts(target),
        popular_snapshots,
        target=target,
        popular_limit=popular_limit,
    )
    contexts, seed_failures = fetch_target_contexts(
        logical_contexts=logical_contexts,
        target=target,
        http_client=http_client,
        appserver_url=_local_appserver_url(),
    )
    default_context_count = sum(
        1 for item in contexts if item.get("is_default") is True
    )
    popular_context_count = max(len(contexts) - default_context_count, 0)
    selected, selection_coverage = _select_opportunities_with_coverage(
        contexts,
        popular_rows_per_context=rows_per_context,
        popular_max_rows=popular_max_rows,
        max_total_rows=global_max_rows,
        minimum_entry_date=target,
    )

    generation_identity = {
        "cache_schema": CACHE_SCHEMA_VERSION,
        "contract_version": CONTEXT_CONTRACT_VERSION,
        "latest_us_date": str(status["latest_us_date"]),
        "market_date": str(status["market_date"]),
        "target_table_date": str(status["target_table_date"]),
        "eod_completed_session": str(status["completed_session"]),
        "eod_generation_fingerprint": str(status["generation_fingerprint"]),
        "eod_completeness_fingerprint": str(
            status["completeness_fingerprint"]
        ),
        "eod_readiness_fingerprint": str(status["readiness_fingerprint"]),
        "scorer_data_as_of": scorer_data_as_of,
        "data_alignment": data_alignment,
        "scorer_fingerprint": scorer_fingerprint,
        "contexts": [str(item.get("context_hash") or "") for item in contexts],
        "selected_rows_hash": _hash(selected),
        "selection_policy": selection_policy,
    }
    generation_id = _hash(generation_identity)
    manifest_key = f"{CACHE_SCHEMA_VERSION}:prefetch:generation:{generation_id}"
    existing = _decode_json(redis_client.get(manifest_key))
    if isinstance(existing, Mapping) and existing.get("status") == "complete":
        print(f"ML prefetch already complete for generation {generation_id[:12]}.")
        return 0

    lock = redis_client.lock(
        f"{CACHE_SCHEMA_VERSION}:prefetch:lock:{generation_id}",
        timeout=45 * 60,
        blocking_timeout=0,
    )
    if not lock.acquire(blocking=False):
        print(f"ML prefetch generation {generation_id[:12]} is already running.")
        return 0
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        publication = _StagedCachePublication(redis_client, generation_id)
        warm_service = CheckpointScoringService(
            redis_client=publication,
            scorer_url=scorer_url,
            http_client=http_client,
            ttl_seconds=ttl_seconds,
            request_timeout=60,
            scorer_mode=config.ml_scorer_mode,
        )
        legacy_rows = [
            opportunity
            for _resource_id, opportunity in selected
            if int(opportunity["daysOut"]) < 90
        ]
        checkpoint_rows = [
            (resource_id, opportunity)
            for resource_id, opportunity in selected
            if int(opportunity["daysOut"]) >= 30
        ]
        legacy_identities = {
            (
                str(row["symbol"]),
                str(row["date"]),
                model_days_out_for_source(row["daysOut"]),
                str(row["direction"]),
            )
            for row in legacy_rows
        }
        short_source_rows = [
            row for row in legacy_rows if int(row["daysOut"]) < 9
        ]
        short_identities = {
            (
                str(row["symbol"]),
                str(row["date"]),
                model_days_out_for_source(row["daysOut"]),
                str(row["direction"]),
            )
            for row in short_source_rows
        }
        warming_manifest = {
            "status": "warming",
            "generation_id": generation_id,
            "identity": generation_identity,
            "target_table_date": target.isoformat(),
            "data_alignment": data_alignment,
            "started_at": started,
            "default_contexts": default_context_count,
            "popular_contexts": popular_context_count,
            "selected_rows": len(selected),
            "eligible_rows": selection_coverage["eligible_rows"],
            "truncated_rows": selection_coverage["truncated_rows"],
            "selection_truncated": selection_coverage["truncated"],
            "selection_coverage": selection_coverage,
            "legacy_source_rows": len(legacy_rows),
            "legacy_unique_requests": len(legacy_identities),
            "legacy_deduplicated_rows": len(legacy_rows) - len(legacy_identities),
            "short_source_rows": len(short_source_rows),
            "short_unique_requests": len(short_identities),
            "short_deduplicated_rows": len(short_source_rows) - len(short_identities),
        }
        _write_manifest(redis_client, manifest_key, warming_manifest)
        legacy_completed, legacy_failures = warm_legacy_rows(
            legacy_rows,
            redis_client=publication,
            http_client=http_client,
            scorer_url=scorer_url,
            expected_metadata=metadata,
            ttl_seconds=ttl_seconds,
            request_batch_size=legacy_batch_size,
        )
        checkpoint_completed, checkpoint_failures = warm_checkpoint_rows(
            checkpoint_rows,
            service=warm_service,
            row_batch_size=checkpoint_row_batch,
        )
        failures = seed_failures + legacy_failures + checkpoint_failures
        if legacy_completed != len(legacy_rows):
            failures.append(
                "legacy completion count did not match the selected exact-window rows"
            )
        if checkpoint_completed != len(checkpoint_rows):
            failures.append(
                "checkpoint completion count did not match the selected comparison rows"
            )
        final_scorer_verification: Dict[str, Any] = {
            "verified": False,
            "scorer_fingerprint": None,
            "data_as_of": None,
        }
        if failures:
            final_scorer_verification["reason"] = "skipped_after_warm_failure"
        else:
            try:
                live_metadata = _live_scorer_metadata(
                    http_client=http_client,
                    scorer_url=scorer_url,
                )
            except Exception as exc:
                live_metadata = None
                final_scorer_verification["reason"] = (
                    f"live_health_unavailable:{type(exc).__name__}"
                )
            if live_metadata is None:
                failures.append("final live scorer metadata was unavailable")
                final_scorer_verification.setdefault(
                    "reason", "live_health_unavailable"
                )
            else:
                live_fingerprint = metadata_fingerprint(live_metadata)
                live_data_as_of = str(live_metadata.get("data_as_of") or "")
                final_scorer_verification.update(
                    {
                        "scorer_fingerprint": live_fingerprint,
                        "data_as_of": live_data_as_of,
                    }
                )
                if (
                    live_fingerprint != scorer_fingerprint
                    or live_data_as_of != scorer_data_as_of
                ):
                    failures.append(
                        "scorer identity changed before atomic publication"
                    )
                    final_scorer_verification["reason"] = "identity_changed"
                else:
                    final_scorer_verification["verified"] = True
        finished = dt.datetime.now(dt.timezone.utc).isoformat()
        staged_terminal_rows = legacy_completed + checkpoint_completed
        published_warmed_rows = len(selected) if not failures else 0
        final_selection_coverage = {
            **selection_coverage,
            "warmed_rows": published_warmed_rows,
            "default": {
                **selection_coverage["default"],
                "warmed_rows": (
                    selection_coverage["default"]["selected_rows"]
                    if not failures
                    else 0
                ),
            },
            "popular": {
                **selection_coverage["popular"],
                "warmed_rows": (
                    selection_coverage["popular"]["selected_rows"]
                    if not failures
                    else 0
                ),
            },
        }
        final_manifest = {
            **warming_manifest,
            "status": "complete" if not failures else "failed",
            "completed_at": finished,
            "legacy_planned": len(legacy_rows),
            "legacy_completed": legacy_completed,
            "checkpoint_planned": len(checkpoint_rows),
            "checkpoint_completed": checkpoint_completed,
            "staged_terminal_rows": staged_terminal_rows,
            "warmed_rows": published_warmed_rows,
            "selection_coverage": final_selection_coverage,
            "final_scorer_verification": final_scorer_verification,
            "staged_cache_entries": publication.staged_count,
            "failures": failures[:50],
        }
        if failures:
            _write_manifest(redis_client, manifest_key, final_manifest)
            print(
                f"ML prefetch generation {generation_id[:12]} failed "
                f"with {len(failures)} bounded errors; active generation unchanged."
            )
            return 1

        active_pointer = {
            "generation_id": generation_id,
            "manifest_key": manifest_key,
            "contract_version": CONTEXT_CONTRACT_VERSION,
            "latest_us_date": str(status["latest_us_date"]),
            "target_table_date": target.isoformat(),
            "scorer_data_as_of": scorer_data_as_of,
            "eod_generation_fingerprint": str(
                status["generation_fingerprint"]
            ),
            "eod_completeness_fingerprint": str(
                status["completeness_fingerprint"]
            ),
            "eod_readiness_fingerprint": str(
                status["readiness_fingerprint"]
            ),
            "scorer_fingerprint": scorer_fingerprint,
            "policy_fingerprint": policy_fingerprint,
            "activated_at": finished,
        }
        # This is the sole live publication boundary. Before this transaction,
        # normal readers can see only the prior live score values and pointers.
        try:
            publication.publish(
                manifest_key=manifest_key,
                manifest=final_manifest,
                active_key=ACTIVE_GENERATION_KEY,
                active_pointer=active_pointer,
            )
        except Exception as exc:
            # A dropped local Redis acknowledgement can occur after EXEC. Check
            # the committed boundary before classifying it as a failed publish.
            committed_active = _decode_json(
                redis_client.get(ACTIVE_GENERATION_KEY)
            )
            committed_manifest = _decode_json(redis_client.get(manifest_key))
            if not (
                isinstance(committed_active, Mapping)
                and committed_active.get("generation_id") == generation_id
                and isinstance(committed_manifest, Mapping)
                and committed_manifest.get("status") == "complete"
            ):
                publish_failed = {
                    **final_manifest,
                    "status": "failed",
                    "warmed_rows": 0,
                    "selection_coverage": {
                        **final_selection_coverage,
                        "warmed_rows": 0,
                        "default": {
                            **final_selection_coverage["default"],
                            "warmed_rows": 0,
                        },
                        "popular": {
                            **final_selection_coverage["popular"],
                            "warmed_rows": 0,
                        },
                    },
                    "failures": [
                        *final_manifest.get("failures", []),
                        f"atomic publication failed ({type(exc).__name__})",
                    ][:50],
                }
                _write_manifest(redis_client, manifest_key, publish_failed)
                print(
                    f"ML prefetch generation {generation_id[:12]} failed at "
                    "the atomic publication boundary; active generation unchanged."
                )
                return 1
        print(
            f"ML prefetch complete {generation_id[:12]}: "
            f"{legacy_completed} exact rows, {checkpoint_completed} checkpoint rows."
        )
        return 0
    finally:
        try:
            lock.release()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status-file",
        default=os.environ.get("TW2_EOD_UPDATE_STATUS_FILE", DEFAULT_STATUS_FILE),
    )
    args = parser.parse_args()
    redis_client = redis.Redis(host="localhost", port=6379, db=0)
    return run_prefetch(
        status_file=args.status_file,
        redis_client=redis_client,
        http_client=requests.Session(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
