"""Watchlist CSV detection supplements US misses from exact provider codes."""

import base64
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "appserver" / "appserver"))

import appserver as appserver_module  # noqa: E402
from us_exchange_catalog import (  # noqa: E402
    CACHE_KEY, CACHE_TTL_SECONDS, REQUEST_TIMEOUT, USCatalogUnavailable,
    load_us_symbol_codes,
)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.set_calls = []

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None):
        self.values[key] = value
        self.set_calls.append((key, value, ex))


class FakeResponse:
    def __init__(self, rows):
        self.rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return self.rows


def _unwrapped_route():
    route = appserver_module.detect_symbols_group
    while hasattr(route, "__wrapped__"):
        route = route.__wrapped__
    return route


def _detect(monkeypatch, tmp_path, csv_by_group, exchange_by_group, symbols,
            catalog_rows=None, catalog_error=None, cache=None):
    cache = cache or FakeRedis()
    resource_paths = {}
    for resource_id, csv_symbols in csv_by_group.items():
        path = tmp_path / (resource_id + ".csv")
        path.write_text("symbols\n" + "\n".join(csv_symbols) + "\n", encoding="utf-8")
        resource_paths[resource_id] = str(path)
    monkeypatch.setattr(appserver_module.config, "available_resources_path", resource_paths)
    monkeypatch.setattr(
        appserver_module.config,
        "available_resources",
        {rid: "RESOURCE " + rid for rid in resource_paths},
    )
    monkeypatch.setattr(appserver_module.config, "exchange_mapping", exchange_by_group)
    monkeypatch.setattr(appserver_module.config, "EOD_token", "unit-test-token")
    monkeypatch.setattr(appserver_module, "redis_client", cache)
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        if catalog_error:
            raise catalog_error
        return FakeResponse(catalog_rows or [])

    monkeypatch.setattr(appserver_module.requests, "get", get)
    encoded = base64.b64encode(",".join(symbols).encode("utf-8")).decode("ascii")
    route = _unwrapped_route()
    with appserver_module.app.test_request_context("/detect_symbols_group/" + encoded):
        response = route(encoded)
        return response.get_json(), calls, cache


def test_us_catalog_rescues_exact_code_preserves_order_and_schema(monkeypatch, tmp_path):
    data, calls, cache = _detect(
        monkeypatch,
        tmp_path,
        {"4": ["AAME", "AAN", "AAOI"]},
        {"4": "US"},
        ["AAME", "AAN", "AAOI", "BP", "NOPE"],
        [{"Code": "BP", "Name": "BP PLC ADR", "Exchange": "NYSE"}],
    )

    assert data == {
        "detected_group": {"resource_id": "4", "resource_name": "RESOURCE 4"},
        "valid_symbols": ["AAME", "AAN", "AAOI", "BP"],
        "invalid_symbols": ["NOPE"],
        "all_groups": [{"resource_id": "4", "resource_name": "RESOURCE 4", "match_count": 3}],
    }
    assert len(calls) == 1
    assert calls[0][0] == "https://eodhd.com/api/exchange-symbol-list/US"
    assert calls[0][1]["params"] == {"api_token": "unit-test-token", "fmt": "json"}
    assert calls[0][1]["timeout"] == REQUEST_TIMEOUT
    catalog_cache_write = next(call for call in cache.set_calls if call[0] == CACHE_KEY)
    assert catalog_cache_write[2] == CACHE_TTL_SECONDS


def test_invalid_ticker_stays_invalid_and_catalog_cache_is_reused(monkeypatch, tmp_path):
    cache = FakeRedis()
    rows = [{"Code": "BP"}]
    first, calls1, cache = _detect(
        monkeypatch, tmp_path, {"4": ["AAPL"]}, {"4": "US"},
        ["AAPL", "BP", "NOPE"], rows, cache=cache,
    )
    second, calls2, _ = _detect(
        monkeypatch, tmp_path, {"4": ["AAPL"]}, {"4": "US"},
        ["AAPL", "BP", "NOPE"], rows, cache=cache,
    )

    assert first["valid_symbols"] == second["valid_symbols"] == ["AAPL", "BP"]
    assert first["invalid_symbols"] == second["invalid_symbols"] == ["NOPE"]
    assert len(calls1) == 1
    assert calls2 == []


def test_non_us_group_does_not_use_us_catalog_for_cross_market_collision(monkeypatch, tmp_path):
    data, calls, _ = _detect(
        monkeypatch, tmp_path,
        {"12": ["VOD"]}, {"12": "LSE"}, ["VOD", "BP"],
        [{"Code": "BP"}],
    )

    assert data["detected_group"]["resource_id"] == "12"
    assert data["valid_symbols"] == ["VOD"]
    assert data["invalid_symbols"] == ["BP"]
    assert calls == []


def test_all_csv_matches_do_not_call_provider(monkeypatch, tmp_path):
    data, calls, _ = _detect(
        monkeypatch, tmp_path, {"4": ["AAPL", "BP"]}, {"4": "US"},
        ["AAPL", "BP"], catalog_error=RuntimeError("should not run"),
    )

    assert data["valid_symbols"] == ["AAPL", "BP"]
    assert data["invalid_symbols"] == []
    assert calls == []


@pytest.mark.parametrize("catalog_rows", [[], [{"Code": 7}], [{"Code": " BP "}]])
def test_malformed_catalog_fails_closed(monkeypatch, tmp_path, catalog_rows):
    data, calls, _ = _detect(
        monkeypatch, tmp_path, {"4": ["AAPL"]}, {"4": "US"},
        ["AAPL", "BP"], catalog_rows=catalog_rows,
    )

    assert data == {"error": "symbol_catalog_unavailable"}
    assert len(calls) == 1


def test_catalog_failure_returns_explicit_error_without_partial_results(monkeypatch, tmp_path):
    data, calls, _ = _detect(
        monkeypatch, tmp_path, {"4": ["AAPL"]}, {"4": "US"},
        ["AAPL", "BP"], catalog_error=RuntimeError("provider response has secret"),
    )

    assert data == {"error": "symbol_catalog_unavailable"}
    assert len(calls) == 1
    assert "secret" not in json.dumps(data)


def test_missing_token_fails_closed_without_provider_request():
    calls = []
    with pytest.raises(USCatalogUnavailable):
        load_us_symbol_codes(
            lambda *args, **kwargs: calls.append((args, kwargs)), "", FakeRedis()
        )
    assert calls == []


def test_cache_read_failure_fetches_and_cache_write_failure_keeps_catalog():
    class BrokenCache:
        def get(self, key):
            raise RuntimeError("cache unavailable")

        def set(self, key, value, ex=None):
            raise RuntimeError("cache unavailable")

    calls = []

    class Response(FakeResponse):
        pass

    class HttpClient:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response([{"Code": "BP"}])

    codes = load_us_symbol_codes(HttpClient(), "unit-test-token", BrokenCache())
    assert codes == {"BP"}
    assert len(calls) == 1


def test_input_is_deduplicated_in_order_and_over_500_is_rejected(monkeypatch, tmp_path):
    data, calls, _ = _detect(
        monkeypatch, tmp_path, {"4": ["AAPL"]}, {"4": "US"},
        ["AAPL", "AAPL"], catalog_error=RuntimeError("should not run"),
    )
    assert data["valid_symbols"] == ["AAPL"]
    assert calls == []

    encoded = base64.b64encode(",".join("S" + str(i) for i in range(501)).encode()).decode()
    route = _unwrapped_route()
    with appserver_module.app.test_request_context("/detect_symbols_group/" + encoded):
        response = route(encoded)
    assert response.get_json() == {"error": "too_many_symbols"}
