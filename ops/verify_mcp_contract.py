#!/usr/bin/env python3
"""Fail-closed release probe for the public TradeWave MCP contract.

The probe intentionally uses only the Python standard library so it can run from
the deploy host without borrowing the application virtualenv.  It performs a real
authenticated Streamable HTTP session (initialize -> initialized -> tools/list),
then compares the published inventory and every input schema with the frozen
17-tool contract.

Authentication normally comes from systemd's ``verify-env`` credential file.
The environment variable remains only as an explicit test/manual fallback.
Customer, demo, and implicit fallback credentials are rejected.

The token is never printed and is deliberately not accepted as a command-line
argument, which keeps it out of process listings and shell history.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any


PROTOCOL_VERSION = "2025-11-25"
LEGACY_PROTOCOL_VERSION = "2025-06-18"
GHOST_TOOLS = {"get_opportunity_for_symbol"}
READ_ONLY_TOOLS = {
    "explain_pick",
    "list_markets",
    "whoami",
    "describe_tradewave",
    "list_symbols",
    "get_symbol_patterns",
    "get_seasonal_pattern",
    "get_opportunity_chart",
    "get_daily_pick",
    "get_pick_track_record",
}
DIRECTION_VALUES = {"long", "short"}
VIEW_VALUES = {"decision", "table", "full"}
RANK_VALUES = {"edge", "win_rate", "sharpe", "ml", "avg_return"}
LIST_PE_VALUES = {"consecutive", "pe"}
CHART_PE_VALUES = LIST_PE_VALUES | {"pe0", "pe1", "pe2", "pe3"}
_VERIFIER_KEY_RE = re.compile(r"^tw_live_[0-9a-f]{32}$")
_CREDENTIAL_NAME = "verify-env"
_MAX_CREDENTIAL_BYTES = 4096
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
PERIOD_VALUES = {
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
    "nov", "dec", "q1", "q2", "q3", "q4", "spring", "summer", "fall",
    "winter", "ytd", "year_end", "buy_hold",
}
SCORE_MARKET_VALUES = {"0", "1", "2", "3", "4", "11"}


def _parse_verifier_credential(raw: bytes, source: str) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{source} is not valid UTF-8") from exc
    values: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.fullmatch(r"TW_MCP_VERIFY_TOKEN=([^\s'\"`$;\\]+)", stripped)
        if match is None:
            raise ValueError(f"{source} may contain only one literal TW_MCP_VERIFY_TOKEN")
        values.append(match.group(1))
    if len(values) != 1 or not _VERIFIER_KEY_RE.fullmatch(values[0]):
        raise ValueError(f"{source} must contain exactly one dedicated regular release-verifier key")
    return values[0]


def load_verifier_token() -> str:
    credentials_directory = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if credentials_directory:
        if os.environ.get("TW_MCP_VERIFY_TOKEN"):
            raise ValueError("environment verifier token is forbidden when systemd credentials are present")
        if (
            not os.path.isabs(credentials_directory)
            or os.path.abspath(credentials_directory) != credentials_directory
        ):
            raise ValueError("CREDENTIALS_DIRECTORY must be a canonical absolute path")
        path = os.path.join(credentials_directory, _CREDENTIAL_NAME)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags)
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("systemd verifier credential is not a private regular file")
            if metadata.st_size > _MAX_CREDENTIAL_BYTES:
                raise ValueError("systemd verifier credential is oversized")
            raw = bytearray()
            while True:
                chunk = os.read(fd, 1024)
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > _MAX_CREDENTIAL_BYTES:
                    raise ValueError("systemd verifier credential is oversized")
        finally:
            os.close(fd)
        return _parse_verifier_credential(bytes(raw), path)

    token = os.environ.get("TW_MCP_VERIFY_TOKEN", "")
    if not _VERIFIER_KEY_RE.fullmatch(token):
        raise ValueError(
            "TW_MCP_VERIFY_TOKEN must be the dedicated regular release-verifier key"
        )
    return token

# Exact public argument names, required arguments, and non-null JSON types.  This
# is intentionally independent of mcpserver.server imports: the release check must
# catch a stale process or stale connector catalog, not agree with whichever code
# happened to be imported locally.
EXPECTED_SCHEMAS: dict[str, dict[str, Any]] = {
    "find_best_opportunities": {
        "required": set(),
        "properties": {
            "markets": {"array", "string"},
            "window": {"string"},
            "direction": {"string"},
            "min_win_rate": {"number"},
            "min_years": {"integer"},
            "min_days": {"integer"},
            "max_days": {"integer"},
            "min_avg_return": {"number"},
            "min_median_return": {"number"},
            "min_sharpe": {"number"},
            "pe_cycle": {"string"},
            "years": {"integer"},
            "min_winning_years": {"integer"},
            "rank_by": {"string"},
            "limit": {"integer"},
            "view": {"string"},
        },
    },
    "analyze_symbol": {
        "required": {"symbol"},
        "properties": {
            "symbol": {"string"},
            "market": {"string"},
            "direction": {"string"},
            "days_out": {"integer"},
            "entry_date": {"string"},
            "pe_cycle": {"string"},
            "years": {"integer"},
            "period": {"string"},
            "reverse": {"boolean"},
            "view": {"string"},
            "include_chart": {"boolean"},
        },
    },
    "explain_pick": {"required": set(), "properties": {}},
    "morning_briefing": {"required": set(), "properties": {}},
    "whats_seasonal_now": {
        "required": set(),
        "properties": {
            "markets": {"array", "string"},
            "min_win_rate": {"number"},
            "view": {"string"},
        },
    },
    "compare_opportunities": {
        "required": {"symbols"},
        "properties": {
            "symbols": {"array"},
            "market": {"string"},
            "view": {"string"},
        },
    },
    "list_markets": {"required": set(), "properties": {}},
    "whoami": {"required": set(), "properties": {}},
    "describe_tradewave": {"required": set(), "properties": {}},
    "list_symbols": {
        "required": {"market"},
        "properties": {
            "market": {"string"},
            "prefix": {"string"},
            "limit": {"integer"},
        },
    },
    "get_seasonal_opportunities": {
        "required": {"market"},
        "properties": {
            "market": {"string"},
            "from_date": {"string"},
            "direction": {"string"},
            "min_win_rate": {"number"},
            "min_days": {"integer"},
            "max_days": {"integer"},
            "min_avg_return": {"number"},
            "min_median_return": {"number"},
            "min_sharpe": {"number"},
            "pe_cycle": {"string"},
            "years": {"integer"},
            "min_winning_years": {"integer"},
            "limit": {"integer"},
        },
    },
    "get_symbol_patterns": {
        "required": {"symbol", "market"},
        "properties": {
            "symbol": {"string"},
            "market": {"string"},
            "pe_cycle": {"string"},
            "years": {"integer"},
            "min_winning_years": {"integer"},
            "min_days": {"integer"},
            "max_days": {"integer"},
            "min_avg_return": {"number"},
            "min_sharpe": {"number"},
        },
    },
    "get_seasonal_pattern": {
        "required": {"market", "symbol"},
        "properties": {
            "market": {"string"},
            "symbol": {"string"},
            "pe_cycle": {"string"},
            "years": {"integer"},
            "period": {"string"},
            "reverse": {"boolean"},
        },
    },
    "get_opportunity_chart": {
        "required": {"market", "symbol"},
        "properties": {
            "market": {"string"},
            "symbol": {"string"},
            "entry_date": {"string"},
            "days_out": {"integer"},
            "direction": {"string"},
            "years": {"string"},
            "pe_cycle": {"string"},
            "period": {"string"},
            "reverse": {"boolean"},
        },
    },
    "score_opportunities": {
        "required": {"opportunities"},
        "properties": {"opportunities": {"array"}, "market": {"string"}},
    },
    "get_daily_pick": {"required": set(), "properties": {}},
    "get_pick_track_record": {"required": set(), "properties": {}},
}


class ProbeError(RuntimeError):
    """A release-blocking probe failure."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    _NoRedirect,
)


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    payload: Mapping[str, Any] | None = None,
    timeout: float = 20.0,
) -> tuple[int, Mapping[str, str], bytes]:
    body = None
    request_headers = dict(headers or {})
    # Cloudflare blocks urllib's default Python-urllib user agent (error 1010).
    # Use a stable, identifiable release-probe identity instead of weakening the
    # edge rule or masquerading as a browser.
    request_headers.setdefault("User-Agent", "TradeWave-MCP-Release-Gate/1.0")
    request_headers.setdefault("Accept-Encoding", "identity")
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(
        url, data=body, headers=request_headers, method=method
    )
    try:
        with _OPENER.open(req, timeout=timeout) as response:
            body = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(body) > _MAX_RESPONSE_BYTES:
                raise ProbeError(f"response exceeded {_MAX_RESPONSE_BYTES} bytes for {url}")
            return response.status, response.headers, body
    except urllib.error.HTTPError as exc:
        body = exc.read(_MAX_RESPONSE_BYTES + 1)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise ProbeError(f"error response exceeded {_MAX_RESPONSE_BYTES} bytes for {url}")
        return exc.code, exc.headers, body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProbeError(f"request failed for {url}: {exc}") from exc


def _body_excerpt(body: bytes, limit: int = 400) -> str:
    text = body.decode("utf-8", errors="replace").strip().replace("\n", " ")
    return text[:limit]


def _json_messages(body: bytes) -> list[dict[str, Any]]:
    """Decode either application/json or Streamable HTTP SSE response bodies."""
    text = body.decode("utf-8", errors="strict").strip()
    if not text:
        return []
    if text.startswith("{") or text.startswith("["):
        value = json.loads(text)
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        raise ProbeError("MCP response JSON was neither an object nor a list")

    messages: list[dict[str, Any]] = []
    data_lines: list[str] = []
    for line in text.splitlines() + [""]:
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif not line.strip() and data_lines:
            value = json.loads("\n".join(data_lines))
            if isinstance(value, dict):
                messages.append(value)
            data_lines = []
    if not messages:
        raise ProbeError("MCP response was neither JSON nor a decodable SSE message")
    return messages


def _message_for_id(body: bytes, request_id: int) -> dict[str, Any]:
    try:
        messages = _json_messages(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"invalid MCP response body: {exc}") from exc
    for message in messages:
        if message.get("id") == request_id:
            if "error" in message:
                raise ProbeError(f"MCP JSON-RPC error: {message['error']}")
            return message
    raise ProbeError(f"MCP response did not contain JSON-RPC id {request_id}")


def _non_null_types(schema: Any) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    found: set[str] = set()
    schema_type = schema.get("type")
    if isinstance(schema_type, str) and schema_type != "null":
        found.add(schema_type)
    elif isinstance(schema_type, list):
        found.update(str(item) for item in schema_type if item != "null")
    for keyword in ("anyOf", "oneOf"):
        variants = schema.get(keyword)
        if isinstance(variants, list):
            for variant in variants:
                found.update(_non_null_types(variant))
    return found


def _schemas_of_type(schema: Any, wanted: str) -> list[dict[str, Any]]:
    """Return all schema/union branches whose direct JSON type is *wanted*."""
    if not isinstance(schema, dict):
        return []
    found: list[dict[str, Any]] = []
    schema_type = schema.get("type")
    if schema_type == wanted or (
        isinstance(schema_type, list) and wanted in schema_type
    ):
        found.append(schema)
    for keyword in ("anyOf", "oneOf"):
        variants = schema.get(keyword)
        if isinstance(variants, list):
            for variant in variants:
                found.extend(_schemas_of_type(variant, wanted))
    return found


def _expect_keyword(schema: dict[str, Any], keyword: str, value: Any, label: str) -> None:
    if schema.get(keyword) != value:
        raise ProbeError(
            f"{label}: {keyword} drift; got={schema.get(keyword)!r}, want={value!r}"
        )


def _resolve_local_ref(root: dict[str, Any], node: Any, label: str) -> Any:
    """Resolve a local JSON Pointer such as ``#/$defs/_ScoreOpportunity``.

    FastMCP/Pydantic legitimately de-duplicates nested models into ``$defs``.
    Release validation must inspect the referenced schema, not mistake the ref
    wrapper for an untyped payload. External refs remain forbidden here.
    """
    resolved = node
    seen: set[str] = set()
    while isinstance(resolved, dict) and "$ref" in resolved:
        ref = resolved.get("$ref")
        if not isinstance(ref, str) or not ref.startswith("#/") or ref in seen:
            raise ProbeError(f"{label}: invalid/cyclic local schema ref {ref!r}")
        seen.add(ref)
        target: Any = root
        for raw_part in ref[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or part not in target:
                raise ProbeError(f"{label}: unresolved local schema ref {ref!r}")
            target = target[part]
        if not isinstance(target, dict):
            raise ProbeError(f"{label}: local schema ref does not target an object")
        # JSON Schema permits siblings next to $ref. Preserve them as overrides.
        resolved = {**target, **{k: v for k, v in resolved.items() if k != "$ref"}}
    return resolved


def _typed_branch(schema: Any, wanted: str, label: str) -> dict[str, Any]:
    branches = _schemas_of_type(schema, wanted)
    if len(branches) != 1:
        raise ProbeError(
            f"{label}: expected one {wanted} schema branch, got {len(branches)}"
        )
    return branches[0]


def _expect_enum(schema: Any, values: set[str], label: str) -> None:
    branch = _typed_branch(schema, "string", label)
    actual = branch.get("enum")
    if not isinstance(actual, list) or set(actual) != values or len(actual) != len(values):
        raise ProbeError(
            f"{label}: enum drift; got={actual!r}, want={sorted(values)!r}"
        )


def _expect_bounds(
    schema: Any,
    wanted_type: str,
    minimum: int | float,
    maximum: int | float,
    label: str,
) -> None:
    branch = _typed_branch(schema, wanted_type, label)
    _expect_keyword(branch, "minimum", minimum, label)
    _expect_keyword(branch, "maximum", maximum, label)


def _validate_bounded_schema(
    name: str, schema: dict[str, Any], properties: dict[str, Any]
) -> None:
    """Submission-critical abuse bounds that must survive connector publishing."""
    if name in {"find_best_opportunities", "whats_seasonal_now"}:
        markets = properties["markets"]
        arrays = _schemas_of_type(markets, "array")
        strings = _schemas_of_type(markets, "string")
        if len(arrays) != 1 or len(strings) != 1:
            raise ProbeError(f"{name}.markets: expected one array and one string union branch")
        _expect_keyword(arrays[0], "minItems", 1, f"{name}.markets[]")
        _expect_keyword(arrays[0], "maxItems", 15, f"{name}.markets[]")
        items = arrays[0].get("items")
        if not isinstance(items, dict) or items.get("type") != "string":
            raise ProbeError(f"{name}.markets[]: items must be strings")
        _expect_keyword(items, "maxLength", 64, f"{name}.markets[] item")
        _expect_keyword(strings[0], "maxLength", 512, f"{name}.markets string")

    if "direction" in properties:
        _expect_enum(properties["direction"], DIRECTION_VALUES, f"{name}.direction")
    if "view" in properties:
        _expect_enum(properties["view"], VIEW_VALUES, f"{name}.view")
    if "rank_by" in properties:
        _expect_enum(properties["rank_by"], RANK_VALUES, f"{name}.rank_by")
    if "period" in properties:
        _expect_enum(properties["period"], PERIOD_VALUES, f"{name}.period")
    if "pe_cycle" in properties:
        pe_values = (
            CHART_PE_VALUES
            if name in {"get_seasonal_pattern", "get_opportunity_chart"}
            else LIST_PE_VALUES
        )
        _expect_enum(properties["pe_cycle"], pe_values, f"{name}.pe_cycle")
    if name == "score_opportunities":
        _expect_enum(
            properties["market"], SCORE_MARKET_VALUES, "score_opportunities.market"
        )
        score_market = _typed_branch(
            properties["market"], "string", "score_opportunities.market"
        )
        _expect_keyword(score_market, "maxLength", 2, "score_opportunities.market")

    if "min_win_rate" in properties:
        _expect_bounds(
            properties["min_win_rate"], "number", 0, 1, f"{name}.min_win_rate"
        )
    for field in ("min_days", "max_days", "days_out"):
        if field in properties:
            _expect_bounds(properties[field], "integer", 1, 366, f"{name}.{field}")
    if "min_years" in properties:
        _expect_bounds(properties["min_years"], "integer", 1, 99, f"{name}.min_years")
    if "years" in properties and name != "get_opportunity_chart":
        _expect_bounds(properties["years"], "integer", 1, 99, f"{name}.years")
    if "min_winning_years" in properties:
        _expect_bounds(
            properties["min_winning_years"],
            "integer",
            0,
            99,
            f"{name}.min_winning_years",
        )
    if "limit" in properties:
        maximum = 1000 if name == "list_symbols" else 100
        _expect_bounds(properties["limit"], "integer", 1, maximum, f"{name}.limit")
    if name == "list_symbols":
        prefix = _typed_branch(properties["prefix"], "string", "list_symbols.prefix")
        _expect_keyword(prefix, "minLength", 1, "list_symbols.prefix")
        _expect_keyword(prefix, "maxLength", 15, "list_symbols.prefix")
    if name == "get_opportunity_chart":
        years = _typed_branch(properties["years"], "string", "get_opportunity_chart.years")
        _expect_keyword(years, "minLength", 1, "get_opportunity_chart.years")
        _expect_keyword(years, "maxLength", 2, "get_opportunity_chart.years")
        _expect_keyword(
            years,
            "pattern",
            r"^(?:[1-9]|[1-9]\d)$",
            "get_opportunity_chart.years",
        )

    if name == "compare_opportunities":
        array = _schemas_of_type(properties["symbols"], "array")
        if len(array) != 1:
            raise ProbeError("compare_opportunities.symbols: expected one array schema")
        _expect_keyword(array[0], "minItems", 2, "compare_opportunities.symbols")
        _expect_keyword(array[0], "maxItems", 10, "compare_opportunities.symbols")
        items = array[0].get("items")
        if not isinstance(items, dict) or items.get("type") != "string":
            raise ProbeError("compare_opportunities.symbols items must be strings")
        _expect_keyword(items, "minLength", 1, "compare_opportunities.symbols item")
        _expect_keyword(items, "maxLength", 64, "compare_opportunities.symbols item")

    if name == "score_opportunities":
        array = _schemas_of_type(properties["opportunities"], "array")
        if len(array) != 1:
            raise ProbeError("score_opportunities.opportunities: expected one array schema")
        _expect_keyword(array[0], "minItems", 1, "score_opportunities.opportunities")
        _expect_keyword(array[0], "maxItems", 100, "score_opportunities.opportunities")
        item = _resolve_local_ref(
            schema, array[0].get("items"), "score_opportunities.opportunities item"
        )
        if not isinstance(item, dict) or item.get("type") != "object":
            raise ProbeError("score_opportunities.opportunities items must be typed objects")
        item_properties = item.get("properties") or {}
        expected = {"symbol", "date", "days_out", "direction"}
        if set(item_properties) != expected or set(item.get("required") or []) != expected:
            raise ProbeError(
                "score_opportunities.opportunities item must require exactly "
                "symbol/date/days_out/direction"
            )
        symbol = item_properties["symbol"]
        date = item_properties["date"]
        days_out = item_properties["days_out"]
        direction = item_properties["direction"]
        if symbol.get("type") != "string" or date.get("type") != "string" \
                or days_out.get("type") != "integer" or direction.get("type") != "string":
            raise ProbeError("score_opportunities item field types drifted")
        _expect_keyword(symbol, "maxLength", 64, "score item.symbol")
        _expect_keyword(date, "maxLength", 32, "score item.date")
        _expect_keyword(days_out, "minimum", 1, "score item.days_out")
        _expect_keyword(days_out, "maximum", 366, "score item.days_out")
        _expect_enum(direction, DIRECTION_VALUES, "score item.direction")
        _expect_keyword(direction, "maxLength", 5, "score item.direction")

    # Every other public top-level string must retain a finite, submission-safe
    # cap. Symbol/market token aliases intentionally use 64 while general text
    # uses 128, so enforce the safe upper bound instead of flattening both types.
    # The two markets union string branches intentionally use 512 and are checked
    # separately above.
    for property_name, property_schema in properties.items():
        if property_name == "markets":
            continue
        for string_schema in _schemas_of_type(property_schema, "string"):
            bound = string_schema.get("maxLength")
            if not isinstance(bound, int) or isinstance(bound, bool) or not 1 <= bound <= 128:
                raise ProbeError(
                    f"{name}.{property_name}: maxLength must be an integer in 1..128; "
                    f"got={bound!r}"
                )


def validate_tool_inventory(tools: list[dict[str, Any]]) -> None:
    names = [tool.get("name") for tool in tools]
    if len(names) != len(set(names)):
        raise ProbeError(f"duplicate tool names published: {names}")

    actual = {name for name in names if isinstance(name, str)}
    expected = set(EXPECTED_SCHEMAS)
    ghosts = actual & GHOST_TOOLS
    if ghosts:
        raise ProbeError(f"deleted/ghost tool aliases are still published: {sorted(ghosts)}")
    if len(actual) == 15:
        raise ProbeError("stale 15-tool connector inventory detected; release requires 17")
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ProbeError(
            f"tool inventory drift (got {len(actual)}, want 17); missing={missing}, extra={extra}"
        )


def validate_legacy_inventory(tools: list[dict[str, Any]]) -> None:
    """Minimal first-migration rollback check for the known pre-contract server."""
    names = [tool.get("name") for tool in tools]
    if not names or any(not isinstance(name, str) or not name for name in names):
        raise ProbeError("legacy rollback tools/list returned no valid tool names")
    if len(names) != len(set(names)):
        raise ProbeError(f"legacy rollback published duplicate tool names: {names}")


def validate_tools(tools: list[dict[str, Any]]) -> None:
    validate_tool_inventory(tools)

    by_name = {tool["name"]: tool for tool in tools}
    for name, contract in EXPECTED_SCHEMAS.items():
        tool = by_name[name]
        description = tool.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ProbeError(f"{name}: missing tool description")
        if "SignalCard" in description or "NO_SIGNAL" in description:
            raise ProbeError(f"{name}: stale SignalCard/NO_SIGNAL terminology published")

        annotations = tool.get("annotations")
        expected_read_only = name in READ_ONLY_TOOLS
        expected_annotations = {
            "readOnlyHint": expected_read_only,
            "idempotentHint": expected_read_only,
            "openWorldHint": False,
            "destructiveHint": False,
        }
        if not isinstance(annotations, dict):
            raise ProbeError(f"{name}: missing tool annotations")
        for annotation, expected_value in expected_annotations.items():
            if annotations.get(annotation) is not expected_value:
                raise ProbeError(
                    f"{name}: annotation {annotation} drift; "
                    f"got={annotations.get(annotation)!r}, want={expected_value!r}"
                )

        schema = tool.get("inputSchema")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ProbeError(f"{name}: inputSchema must be an object schema")
        properties = schema.get("properties") or {}
        if not isinstance(properties, dict):
            raise ProbeError(f"{name}: inputSchema.properties is not an object")
        actual_properties = set(properties)
        expected_properties = set(contract["properties"])
        if actual_properties != expected_properties:
            raise ProbeError(
                f"{name}: property drift; missing={sorted(expected_properties - actual_properties)}, "
                f"extra={sorted(actual_properties - expected_properties)}"
            )
        required = schema.get("required") or []
        if set(required) != set(contract["required"]):
            raise ProbeError(
                f"{name}: required drift; got={sorted(required)}, "
                f"want={sorted(contract['required'])}"
            )
        for property_name, expected_types in contract["properties"].items():
            actual_types = _non_null_types(properties[property_name])
            if actual_types != expected_types:
                raise ProbeError(
                    f"{name}.{property_name}: JSON type drift; "
                    f"got={sorted(actual_types)}, want={sorted(expected_types)}"
                )
        _validate_bounded_schema(name, schema, properties)


def _normalize_https_url(
    value: str, label: str, *, trim_trailing_slash: bool
) -> str:
    """Return a strict, comparison-safe HTTPS URL for this release surface."""
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ProbeError(f"{label} is not a valid URL: {value!r}") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ProbeError(f"{label} must be an absolute HTTPS URL: {value!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ProbeError(f"{label} must not contain userinfo")
    if parsed.query or parsed.fragment:
        raise ProbeError(f"{label} must not contain a query or fragment")
    path = parsed.path or ""
    if "%" in path or "\\" in path or "//" in path:
        raise ProbeError(f"{label} has ambiguous path syntax: {path!r}")
    if any(segment in {".", ".."} for segment in path.split("/")):
        raise ProbeError(f"{label} has a dot-segment path: {path!r}")
    if trim_trailing_slash:
        path = path.rstrip("/")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = f"[{host}]"
    netloc = host if port in {None, 443} else f"{host}:{port}"
    return urllib.parse.urlunsplit(("https", netloc, path, "", ""))


def _resource_url(base_url: str) -> str:
    return _normalize_https_url(
        base_url, "configured MCP resource", trim_trailing_slash=True
    )


def _discovery_url(base_url: str) -> str:
    resource = urllib.parse.urlsplit(_resource_url(base_url))
    path = "/.well-known/oauth-protected-resource" + resource.path
    return urllib.parse.urlunsplit((resource.scheme, resource.netloc, path, "", ""))


def _validate_discovery_document(
    body: bytes,
    *,
    expected_resource: str,
    expected_authorization_server: str | None,
) -> list[str]:
    try:
        metadata = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"OAuth discovery did not return JSON: {exc}") from exc
    resource = metadata.get("resource") if isinstance(metadata, dict) else None
    if not isinstance(resource, str):
        raise ProbeError(f"OAuth discovery resource is missing: {resource!r}")
    normalized_resource = _normalize_https_url(
        resource, "OAuth discovery resource", trim_trailing_slash=True
    )
    if normalized_resource != expected_resource:
        raise ProbeError(
            "OAuth discovery resource does not match the configured MCP endpoint; "
            f"got={normalized_resource!r}, want={expected_resource!r}"
        )
    auth_servers = metadata.get("authorization_servers") or []
    if not isinstance(auth_servers, list) or not auth_servers:
        raise ProbeError("OAuth discovery authorization_servers must be a nonempty list")
    normalized_servers = []
    for server in auth_servers:
        if not isinstance(server, str):
            raise ProbeError("OAuth discovery authorization_servers must all be URLs")
        normalized_servers.append(
            _normalize_https_url(
                server, "OAuth authorization server", trim_trailing_slash=True
            )
        )
    if len(set(normalized_servers)) != len(normalized_servers):
        raise ProbeError("OAuth discovery contains duplicate authorization servers")
    if expected_authorization_server:
        expected_server = _normalize_https_url(
            expected_authorization_server,
            "configured WorkOS authorization server",
            trim_trailing_slash=True,
        )
        if normalized_servers != [expected_server]:
            raise ProbeError(
                "OAuth discovery authorization server does not match configured WorkOS; "
                f"got={normalized_servers!r}, want={[expected_server]!r}"
            )
    return normalized_servers


def _authorization_server_metadata_url(issuer: str) -> str:
    parsed = urllib.parse.urlsplit(
        _normalize_https_url(issuer, "OAuth authorization server", trim_trailing_slash=True)
    )
    path = "/.well-known/oauth-authorization-server" + parsed.path
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _validate_authorization_server_metadata(body: bytes, expected_issuer: str) -> None:
    try:
        metadata = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"OAuth authorization-server metadata is not JSON: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ProbeError("OAuth authorization-server metadata must be an object")
    issuer = _normalize_https_url(
        metadata.get("issuer"), "OAuth metadata issuer", trim_trailing_slash=True
    )
    expected = _normalize_https_url(
        expected_issuer, "expected OAuth issuer", trim_trailing_slash=True
    )
    if issuer != expected:
        raise ProbeError(f"OAuth metadata issuer mismatch; got={issuer!r}, want={expected!r}")

    endpoint_contract = {
        "authorization_endpoint": expected + "/oauth2/authorize",
        "token_endpoint": expected + "/oauth2/token",
    }
    for field, wanted in endpoint_contract.items():
        actual = _normalize_https_url(
            metadata.get(field), f"OAuth metadata {field}", trim_trailing_slash=True
        )
        if actual != wanted:
            raise ProbeError(f"OAuth metadata {field} mismatch; got={actual!r}, want={wanted!r}")

    registration = metadata.get("registration_endpoint")
    cimd = metadata.get("client_id_metadata_document_supported") is True
    if registration:
        actual_registration = _normalize_https_url(
            registration, "OAuth registration_endpoint", trim_trailing_slash=True
        )
        wanted_registration = expected + "/oauth2/register"
        if actual_registration != wanted_registration:
            raise ProbeError(
                "OAuth metadata registration_endpoint mismatch; "
                f"got={actual_registration!r}, want={wanted_registration!r}"
            )
    elif not cimd:
        raise ProbeError(
            "OAuth metadata advertises neither dynamic registration nor Client ID Metadata Document"
        )

    required_values = {
        "scopes_supported": {"offline_access"},
        "grant_types_supported": {"authorization_code", "refresh_token"},
        "response_types_supported": {"code"},
        "code_challenge_methods_supported": {"S256"},
        # ChatGPT's dynamically registered WorkOS client is public and exchanges
        # its PKCE code without a client secret.
        "token_endpoint_auth_methods_supported": {"none"},
    }
    for field, required in required_values.items():
        values = metadata.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ProbeError(f"OAuth metadata {field} must be a string list")
        missing = required - set(values)
        if missing:
            raise ProbeError(f"OAuth metadata {field} is missing {sorted(missing)}")


def verify_authorization_server_metadata(issuer: str, timeout: float) -> None:
    url = _authorization_server_metadata_url(issuer)
    status, _, body = _request(url, timeout=timeout)
    if status != 200:
        raise ProbeError(
            "OAuth authorization-server metadata returned "
            f"{status}: {_body_excerpt(body)}"
        )
    _validate_authorization_server_metadata(body, issuer)


def verify_discovery(
    base_url: str,
    timeout: float,
    expected_authorization_server: str | None = None,
) -> None:
    expected_resource = _resource_url(base_url)
    canonical = _discovery_url(base_url)
    status, _, body = _request(canonical, timeout=timeout)
    if status != 200:
        raise ProbeError(
            f"OAuth protected-resource discovery returned {status}: {_body_excerpt(body)}"
        )
    authorization_servers = _validate_discovery_document(
        body,
        expected_resource=expected_resource,
        expected_authorization_server=expected_authorization_server,
    )
    if len(authorization_servers) != 1:
        raise ProbeError("release gate requires exactly one OAuth authorization server")
    verify_authorization_server_metadata(authorization_servers[0], timeout)

    slash_url = canonical + "/"
    slash_status, slash_headers, slash_body = _request(slash_url, timeout=timeout)
    if slash_status in {301, 302, 303, 307, 308}:
        location = slash_headers.get("Location", "")
        target = urllib.parse.urljoin(slash_url, location)
        normalized_target = _normalize_https_url(
            target, "OAuth trailing-slash redirect", trim_trailing_slash=False
        )
        if normalized_target != canonical:
            raise ProbeError(
                "OAuth trailing-slash redirect must stay on-origin and target the "
                f"canonical discovery endpoint; got={target!r}, want={canonical!r}"
            )
        redirected_status, _, redirected_body = _request(target, timeout=timeout)
        if redirected_status != 200:
            raise ProbeError(
                f"OAuth canonical redirect target returned {redirected_status}: "
                f"{_body_excerpt(redirected_body)}"
            )
        _validate_discovery_document(
            redirected_body,
            expected_resource=expected_resource,
            expected_authorization_server=expected_authorization_server,
        )
    elif slash_status != 200:
        raise ProbeError(
            f"OAuth trailing-slash discovery returned {slash_status}: "
            f"{_body_excerpt(slash_body)}"
        )
    else:
        _validate_discovery_document(
            slash_body,
            expected_resource=expected_resource,
            expected_authorization_server=expected_authorization_server,
        )


def _rpc_headers(
    token: str,
    session_id: str | None = None,
    *,
    protocol_version: str = PROTOCOL_VERSION,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": protocol_version,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return headers


def _challenge_parameter(challenge: str, name: str) -> str | None:
    matches = re.findall(
        rf"(?:^|,)\s*{re.escape(name)}\s*=\s*(?:\"([^\"\\]*(?:\\.[^\"\\]*)*)\"|([^,\s]+))",
        challenge,
        flags=re.IGNORECASE,
    )
    if len(matches) > 1:
        raise ProbeError(f"401 WWW-Authenticate contains duplicate {name}")
    if not matches:
        return None
    quoted, bare = matches[0]
    if quoted:
        try:
            return bytes(quoted, "utf-8").decode("unicode_escape")
        except UnicodeDecodeError as exc:
            raise ProbeError(f"401 WWW-Authenticate has invalid {name}") from exc
    return bare


def validate_unauthenticated_challenge(
    base_url: str,
    status: int,
    headers: Mapping[str, str],
    body: bytes,
) -> None:
    if status != 401:
        raise ProbeError(
            f"unauthenticated initialize returned {status}, want 401: "
            f"{_body_excerpt(body)}"
        )
    challenge = headers.get("WWW-Authenticate", "")
    scheme = re.match(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s+", challenge)
    if scheme is None or scheme.group(1).lower() != "bearer":
        raise ProbeError("401 WWW-Authenticate scheme must be Bearer")
    parameters = challenge[scheme.end():]
    error = _challenge_parameter(parameters, "error")
    description = _challenge_parameter(parameters, "error_description")
    resource_metadata = _challenge_parameter(parameters, "resource_metadata")
    if error != "invalid_token":
        raise ProbeError("401 Bearer challenge must contain error=invalid_token")
    if not description or not description.strip():
        raise ProbeError("401 Bearer challenge must contain a nonempty error_description")
    if not resource_metadata:
        raise ProbeError("401 Bearer challenge is missing resource_metadata")
    normalized_metadata = _normalize_https_url(
        resource_metadata,
        "401 resource_metadata",
        trim_trailing_slash=False,
    )
    expected_metadata = _discovery_url(base_url)
    if normalized_metadata != expected_metadata:
        raise ProbeError(
            "401 resource_metadata does not identify this MCP endpoint; "
            f"got={normalized_metadata!r}, want={expected_metadata!r}"
        )


def verify_unauthenticated_challenge(base_url: str, timeout: float) -> None:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "tradewave-release-gate", "version": "1"},
        },
    }
    status, headers, body = _request(
        base_url,
        method="POST",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        payload=initialize,
        timeout=timeout,
    )
    validate_unauthenticated_challenge(base_url, status, headers, body)


def validate_whoami_result(result: Any) -> str:
    """Validate the cheapest real MCP -> gateway call and return its text."""
    if not isinstance(result, dict):
        raise ProbeError("whoami tools/call result is missing")
    if result.get("isError") is True:
        raise ProbeError("whoami tools/call returned isError=true")
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise ProbeError("whoami tools/call returned no content")
    texts = [
        item.get("text")
        for item in content
        if isinstance(item, dict)
        and item.get("type") == "text"
        and isinstance(item.get("text"), str)
        and item.get("text").strip()
    ]
    if not texts:
        raise ProbeError("whoami tools/call returned no nonempty text content")
    text = "\n".join(texts)
    lowered = text.lower()
    for failure in (
        "rate limit exceeded",
        "temporarily unreachable",
        "still computing",
        "401 unauthorized",
        "403 forbidden",
        "invalid api key",
    ):
        if failure in lowered:
            raise ProbeError(f"whoami exposed gateway failure text: {failure!r}")
    if "You are on the " not in text or " plan with " not in text:
        raise ProbeError("whoami response is missing the expected tier identity lead")
    _, separator, payload_text = text.partition("\n\n")
    if not separator:
        raise ProbeError("whoami response is missing its structured capability payload")
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"whoami capability payload is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProbeError("whoami capability payload must be an object")
    rate = payload.get("rate")
    per_minute = rate.get("per_minute") if isinstance(rate, dict) else None
    per_day = rate.get("per_day") if isinstance(rate, dict) else None
    if not (
        payload.get("tier") == "pro"
        and payload.get("tier_name") == "Pro"
        and isinstance(per_minute, int)
        and not isinstance(per_minute, bool)
        and per_minute >= 120
        and isinstance(per_day, int)
        and not isinstance(per_day, bool)
        and per_day >= 5_000
    ):
        raise ProbeError(
            "whoami capability payload is not the dedicated Pro release-gate capacity"
        )
    if "ml_remaining_today" not in payload:
        raise ProbeError("whoami capability payload is missing ML allowance")
    if not isinstance(payload.get("markets_in_scope"), list):
        raise ProbeError("whoami capability payload is missing markets_in_scope[]")
    if not isinstance(payload.get("example_prompts"), list):
        raise ProbeError("whoami capability payload is missing example_prompts[]")
    return text


def verify_protocol_handshake(
    base_url: str, token: str, timeout: float, protocol_version: str
) -> None:
    """Prove one additional revision negotiates and publishes the exact catalog."""
    request_id = 9001
    status, headers, body = _request(
        base_url,
        method="POST",
        headers=_rpc_headers(token, protocol_version=protocol_version),
        payload={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {
                    "name": "tradewave-protocol-compat-gate",
                    "version": "1",
                },
            },
        },
        timeout=timeout,
    )
    if status != 200:
        raise ProbeError(
            f"protocol {protocol_version} initialize returned {status}: "
            f"{_body_excerpt(body)}"
        )
    result = _message_for_id(body, request_id).get("result")
    if not isinstance(result, dict) or result.get("protocolVersion") != protocol_version:
        negotiated = result.get("protocolVersion") if isinstance(result, dict) else None
        raise ProbeError(
            f"protocol compatibility negotiated {negotiated!r}, want {protocol_version}"
        )
    session_id = headers.get("Mcp-Session-Id")
    if not session_id:
        raise ProbeError(f"protocol {protocol_version} initialize omitted Mcp-Session-Id")
    notify_status, _, notify_body = _request(
        base_url,
        method="POST",
        headers=_rpc_headers(
            token, session_id, protocol_version=protocol_version
        ),
        payload={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        },
        timeout=timeout,
    )
    if notify_status not in {200, 202}:
        raise ProbeError(
            f"protocol {protocol_version} initialized notification returned "
            f"{notify_status}: {_body_excerpt(notify_body)}"
        )

    tools: list[dict[str, Any]] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    for page_number in range(1, 65):
        list_id = request_id + page_number
        params = {"cursor": cursor} if cursor is not None else {}
        list_status, _, list_body = _request(
            base_url,
            method="POST",
            headers=_rpc_headers(
                token, session_id, protocol_version=protocol_version
            ),
            payload={
                "jsonrpc": "2.0",
                "id": list_id,
                "method": "tools/list",
                "params": params,
            },
            timeout=timeout,
        )
        if list_status != 200:
            raise ProbeError(
                f"protocol {protocol_version} tools/list returned {list_status}: "
                f"{_body_excerpt(list_body)}"
            )
        list_result = _message_for_id(list_body, list_id).get("result")
        if not isinstance(list_result, dict) or not isinstance(
            list_result.get("tools"), list
        ):
            raise ProbeError(
                f"protocol {protocol_version} tools/list result is missing tools[]"
            )
        tools.extend(list_result["tools"])
        next_cursor = list_result.get("nextCursor")
        if next_cursor is None:
            break
        if not isinstance(next_cursor, str) or not next_cursor:
            raise ProbeError(
                f"protocol {protocol_version} tools/list returned an invalid nextCursor"
            )
        if next_cursor in seen_cursors:
            raise ProbeError(
                f"protocol {protocol_version} tools/list repeated nextCursor"
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    else:
        raise ProbeError(
            f"protocol {protocol_version} tools/list exceeded the pagination safety bound"
        )
    validate_tool_inventory(tools)

    delete_status, _, delete_body = _request(
        base_url,
        method="DELETE",
        headers=_rpc_headers(
            token, session_id, protocol_version=protocol_version
        ),
        timeout=timeout,
    )
    if delete_status not in {200, 204}:
        raise ProbeError(
            f"protocol {protocol_version} DELETE returned {delete_status}: "
            f"{_body_excerpt(delete_body)}"
        )


def verify_mcp(
    base_url: str,
    token: str,
    timeout: float,
    *,
    strict_contract: bool = True,
    legacy_smoke: bool = False,
) -> None:
    protocol_version = LEGACY_PROTOCOL_VERSION if legacy_smoke else PROTOCOL_VERSION
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "tradewave-release-gate", "version": "1"},
        },
    }

    # Prove the exact public OAuth challenge before exercising bearer traffic.
    verify_unauthenticated_challenge(base_url, timeout)

    status, headers, body = _request(
        base_url,
        method="POST",
        headers=_rpc_headers(token, protocol_version=protocol_version),
        payload=initialize,
        timeout=timeout,
    )
    if status != 200:
        raise ProbeError(
            f"authenticated initialize returned {status}: {_body_excerpt(body)}"
        )
    message = _message_for_id(body, 1)
    result = message.get("result")
    if not isinstance(result, dict):
        raise ProbeError("initialize result is missing")
    if result.get("protocolVersion") != protocol_version:
        raise ProbeError(
            f"initialize negotiated {result.get('protocolVersion')!r}, want {protocol_version}"
        )
    if not isinstance(result.get("serverInfo"), dict):
        raise ProbeError("initialize result is missing serverInfo")

    session_id = headers.get("Mcp-Session-Id")
    if not session_id:
        raise ProbeError("initialize response is missing Mcp-Session-Id")

    initialized = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }
    notify_status, _, notify_body = _request(
        base_url,
        method="POST",
        headers=_rpc_headers(token, session_id, protocol_version=protocol_version),
        payload=initialized,
        timeout=timeout,
    )
    if notify_status not in {200, 202}:
        raise ProbeError(
            f"notifications/initialized returned {notify_status}: {_body_excerpt(notify_body)}"
        )

    tools: list[dict[str, Any]] = []
    cursor: str | None = None
    request_id = 2
    while True:
        params = {"cursor": cursor} if cursor else {}
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": params,
        }
        page_status, _, page_body = _request(
            base_url,
            method="POST",
            headers=_rpc_headers(token, session_id, protocol_version=protocol_version),
            payload=payload,
            timeout=timeout,
        )
        if page_status != 200:
            raise ProbeError(
                f"authenticated tools/list returned {page_status}: {_body_excerpt(page_body)}"
            )
        page_message = _message_for_id(page_body, request_id)
        page = page_message.get("result")
        if not isinstance(page, dict) or not isinstance(page.get("tools"), list):
            raise ProbeError("tools/list result is missing tools[]")
        tools.extend(tool for tool in page["tools"] if isinstance(tool, dict))
        next_cursor = page.get("nextCursor")
        if not next_cursor:
            break
        if not isinstance(next_cursor, str) or next_cursor == cursor:
            raise ProbeError("tools/list returned an invalid/repeated nextCursor")
        cursor = next_cursor
        request_id += 1
        if request_id > 20:
            raise ProbeError("tools/list exceeded the pagination safety bound")

    if legacy_smoke:
        validate_legacy_inventory(tools)
    elif strict_contract:
        validate_tools(tools)
    else:
        validate_tool_inventory(tools)

    # Inventory alone can pass while the MCP -> gateway route or auth forwarding
    # is broken. whoami is read-only and cheap, and proves the full live path.
    request_id += 1
    call_status, _, call_body = _request(
        base_url,
        method="POST",
        headers=_rpc_headers(token, session_id, protocol_version=protocol_version),
        payload={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": "whoami", "arguments": {}},
        },
        timeout=timeout,
    )
    if call_status != 200:
        raise ProbeError(
            f"authenticated whoami tools/call returned {call_status}: "
            f"{_body_excerpt(call_body)}"
        )
    call_message = _message_for_id(call_body, request_id)
    validate_whoami_result(call_message.get("result"))

    # Close the session when supported. A failure here is not a contract failure;
    # older Streamable HTTP clients/servers may legitimately omit DELETE handling.
    _request(
        base_url,
        method="DELETE",
        headers=_rpc_headers(token, session_id, protocol_version=protocol_version),
        timeout=timeout,
    )
    if not legacy_smoke:
        verify_protocol_handshake(
            base_url, token, timeout, LEGACY_PROTOCOL_VERSION
        )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify TradeWave OAuth discovery and exact 17-tool MCP contract"
    )
    parser.add_argument("--url", required=True, help="Public MCP endpoint, normally https://host/")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout seconds")
    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Skip public OAuth discovery checks (local troubleshooting only)",
    )
    parser.add_argument(
        "--inventory-only",
        action="store_true",
        help=(
            "Compatibility rollback only: verify auth/transport/HTTPS and exact 17 names, "
            "but do not require the newest schema/annotation contract"
        ),
    )
    parser.add_argument(
        "--legacy-smoke",
        action="store_true",
        help=(
            "First-migration rollback only: require protected/authenticated transport, "
            "nonempty unique inventory, discovery integrity, and a real whoami call"
        ),
    )
    parser.add_argument(
        "--unauthenticated-only",
        action="store_true",
        help="Postcommit gate: verify OAuth discovery and exact no-bearer challenge only",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    selected_modes = sum(
        bool(value)
        for value in (args.inventory_only, args.legacy_smoke, args.unauthenticated_only)
    )
    if selected_modes > 1:
        print(
            "FAIL: --inventory-only, --legacy-smoke, and --unauthenticated-only are mutually exclusive",
            file=sys.stderr,
        )
        return 2
    if args.unauthenticated_only and args.skip_discovery:
        print("FAIL: --unauthenticated-only requires public OAuth discovery", file=sys.stderr)
        return 2
    parsed = urllib.parse.urlsplit(args.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        print("FAIL: --url must be an absolute http(s) URL", file=sys.stderr)
        return 2
    if not args.skip_discovery and parsed.scheme != "https":
        print("FAIL: public release verification requires an HTTPS URL", file=sys.stderr)
        return 2
    base_url = args.url
    if not parsed.path:
        base_url += "/"

    token = ""
    if not args.unauthenticated_only:
        try:
            token = load_verifier_token()
        except (OSError, ValueError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2
    expected_authorization_server = (
        os.environ.get("TW_MCP_EXPECT_AUTHORIZATION_SERVER")
        or os.environ.get("WORKOS_AUTHKIT_DOMAIN")
        or None
    )
    try:
        if not args.skip_discovery:
            verify_discovery(
                base_url,
                args.timeout,
                expected_authorization_server=expected_authorization_server,
            )
        if args.unauthenticated_only:
            verify_unauthenticated_challenge(base_url, args.timeout)
        else:
            verify_mcp(
                base_url,
                token,
                args.timeout,
                strict_contract=not (args.inventory_only or args.legacy_smoke),
                legacy_smoke=args.legacy_smoke,
            )
    except ProbeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if args.unauthenticated_only:
        print(
            "PASS: canonical OAuth protected-resource + authorization-server metadata; "
            "exact unauthenticated Bearer challenge passed"
        )
        return 0
    if args.legacy_smoke:
        scope = "legacy authenticated inventory + whoami smoke"
    elif args.inventory_only:
        scope = "tool inventory + whoami"
    else:
        scope = (
            "tool/schema/annotation contract + whoami + current/legacy protocol negotiation"
        )
    print(
        f"PASS: authenticated initialize + {scope}; "
        "OAuth protected-resource + authorization-server metadata passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
