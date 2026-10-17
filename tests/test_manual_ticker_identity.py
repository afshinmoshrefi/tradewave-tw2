"""Manual ticker identity must match the requested code and market before writing."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "appserver" / "appserver"))
import appserver as api
import get_name_from_ticker as resolver


class Cache:
    def __init__(self, values=None):
        self.values = values or {}
        self.writes = []

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value
        self.writes.append(key)


def unwrap(route):
    while hasattr(route, "__wrapped__"):
        route = route.__wrapped__
    return route


@pytest.fixture
def provider(monkeypatch):
    calls = []
    rows = [
        {"Code": "BFAM", "Exchange": "US", "Name": "Bright Horizons"},
        {"Code": "BATS", "Exchange": "LSE", "Name": "British American Tobacco"},
        {"Code": "CIGI", "Exchange": "US", "Name": "Colliers Bats"},
        {"Code": "BP", "Exchange": "US", "Name": "BP ADR"},
    ]

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return rows

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(resolver.requests, "get", get)
    return calls, rows


@pytest.mark.parametrize("market,symbol,name", [
    ("US", "BFA", None),
    ("US", "BFAM", "Bright Horizons"),
    ("US", "BATS", None),
    ("LSE", "BATS", "British American Tobacco"),
    ("US", "BP", "BP ADR"),
    (" us ", " bp ", "BP ADR"),
])
def test_exact_code_and_exchange(provider, market, symbol, name):
    assert resolver.get_security_name_from_ticker(market, symbol) == name
    assert provider[0][0][1]["timeout"] == 10
    assert provider[0][0][0].endswith(symbol.strip().upper())


def test_normalizes_provider_identity(provider):
    provider[1][:] = [{"Code": " bp ", "Exchange": " us ", "Name": "BP ADR"}]
    assert resolver.get_security_name_from_ticker("US", "BP") == "BP ADR"


def test_provider_failure_fails_closed(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr(resolver.requests, "get", fail)
    assert resolver.get_security_name_from_ticker("US", "BP") is None


def test_csv_markets_keep_exact_lookup(monkeypatch, tmp_path):
    (tmp_path / "FOREX_symbols.csv").write_text("symbols,name\nEURUSD,Euro Dollar\n")
    monkeypatch.setattr(resolver.config, "ddir", str(tmp_path))
    assert resolver.get_security_name_from_ticker(" forex ", " eurusd ") == "Euro Dollar"
    assert resolver.get_security_name_from_ticker("FOREX", "EUR") is None
    assert resolver.get_security_name_from_ticker("INDX", " spx ") == "S&P 500 Index"


def test_legacy_poisoned_cache_is_ignored(monkeypatch, provider):
    cache = Cache({"security_name_US_BFA": json.dumps("Bright Horizons"),
                   "security_name_US_BP": json.dumps("Wrong company")})
    monkeypatch.setattr(api, "redis_client", cache)
    with api.app.test_request_context():
        assert unwrap(api.NameFromTicker)("4", "BFA").get_json() == {"name": ""}
        assert unwrap(api.NameFromTicker)("4", " bp ").get_json() == {"name": "BP ADR"}
        count = len(provider[0])
        assert unwrap(api.NameFromTicker)("0", "BP").get_json() == {"name": "BP ADR"}
        assert len(provider[0]) == count
    assert cache.writes == ["security_name_exact_v2_US_BP"]
    assert cache.values["security_name_US_BFA"] == json.dumps("Bright Horizons")


def add(monkeypatch, resource, symbol, items=None, watchlist_exists=True):
    cache = Cache({
        "user_watchlists_test-user": json.dumps([
            {"name": "test-list", "resourceId": resource}
        ] if watchlist_exists else []),
        "user_watchlist_items_test-user_test-list": json.dumps(items or []),
    })
    monkeypatch.setattr(api, "redis_client2", cache)
    monkeypatch.setattr(api, "redis_client", Cache())
    monkeypatch.setattr(api.jwt, "decode", lambda *a, **k: {"user": "test-user", "user_level": "6"})
    monkeypatch.setattr(api.config, "num_watchlist_items_allowed_by_level", {"6": 100})
    with api.app.test_request_context("/?token=test", method="POST"):
        data = unwrap(api.add_user_watchlist_item)("test-list", symbol).get_json()
    return data, cache


@pytest.mark.parametrize("symbol", ["BFA", "BATS"])
def test_direct_add_rejects_fuzzy_hit_without_writing(monkeypatch, provider, symbol):
    data, cache = add(monkeypatch, "4", symbol)
    assert data["watchlist_items"] == "invalid_symbol"
    assert cache.writes == []


def test_invalid_existing_symbol_is_not_reported_as_valid_duplicate(monkeypatch, provider):
    data, cache = add(monkeypatch, "4", "BATS", ["BATS"])
    assert data["watchlist_items"] == "invalid_symbol"
    assert cache.writes == []


@pytest.mark.parametrize("resource,symbol", [(str(i), " bp ") for i in range(5)] + [("12", "BATS")])
def test_valid_add_uses_watchlist_exchange(monkeypatch, provider, resource, symbol):
    data, cache = add(monkeypatch, resource, symbol)
    assert data == {"watchlist_items": [symbol.strip().upper()]}
    assert cache.writes == ["user_watchlist_items_test-user_test-list"]


@pytest.mark.parametrize("resource,exchange", [("5", "INDX"), ("6", "INDX"), ("8", "FOREX"), ("9", "FOREX")])
def test_other_merged_groups_keep_market_validation(monkeypatch, resource, exchange):
    seen = []
    monkeypatch.setattr(api, "_exact_security_name", lambda e, s: seen.append((e, s)) or "Valid")
    data, _ = add(monkeypatch, resource, " spx ")
    assert data == {"watchlist_items": ["SPX"]}
    assert seen == [(exchange, "SPX")]


def test_valid_duplicate_keeps_response_contract(monkeypatch, provider):
    data, cache = add(monkeypatch, "4", "BP", ["BP"])
    assert data == {"watchlist_items": "duplicate"}
    assert cache.writes == []


def test_missing_watchlist_fails_closed(monkeypatch, provider):
    data, cache = add(monkeypatch, "4", "BP", watchlist_exists=False)
    assert data["watchlist_items"] == "invalid_watchlist"
    assert cache.writes == []
