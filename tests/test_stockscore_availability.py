"""Trend-score provider failures must never masquerade as real zero scores."""

from pathlib import Path
import json
import sys

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "appserver" / "appserver"))

import appserver as appserver_module  # noqa: E402


class _Redis:
    def __init__(self, initial=None):
        self.values = dict(initial or {})

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def expire(self, key, seconds):
        return True


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_unconfigured_provider_returns_explicitly_unavailable(monkeypatch):
    monkeypatch.setattr(appserver_module, "redis_client", _Redis())
    monkeypatch.setattr(appserver_module.config, "stockscore_url", "")

    result = appserver_module.stockscore_with_availability("2", "ROST", "2026-08-01")

    assert result == (0, 0, 0, 0, False)
    assert appserver_module.stockscore("2", "ROST", "2026-08-01") == (0, 0, 0, 0)


def test_real_zero_from_provider_is_marked_available_and_cached(monkeypatch):
    redis = _Redis()
    monkeypatch.setattr(appserver_module, "redis_client", redis)
    monkeypatch.setattr(appserver_module.config, "stockscore_url", "http://scores/")
    monkeypatch.setattr(
        appserver_module.requests,
        "get",
        lambda *args, **kwargs: _Response({
            "lscore": 0,
            "sscore": 100,
            "lscore1": 5,
            "sscore1": 95,
        }),
    )

    result = appserver_module.stockscore_with_availability("2", "ROST", "2026-08-01")
    cached = json.loads(redis.values["stockscore_2_ROST"])

    assert result == (0, 100, 5, 95, True)
    assert cached["available"] is True


def test_provider_exception_returns_unavailable_instead_of_raising(monkeypatch):
    monkeypatch.setattr(appserver_module, "redis_client", _Redis())
    monkeypatch.setattr(appserver_module.config, "stockscore_url", "http://scores/")

    def fail(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(appserver_module.requests, "get", fail)

    assert appserver_module.stockscore_with_availability(
        "2", "ROST", "2026-08-01"
    ) == (0, 0, 0, 0, False)


def test_legacy_success_cache_without_flag_remains_available(monkeypatch):
    payload = json.dumps({"lscore": 72, "sscore": 28, "lscore1": 68, "sscore1": 32})
    monkeypatch.setattr(
        appserver_module, "redis_client", _Redis({"stockscore_2_ROST": payload})
    )

    assert appserver_module.stockscore_with_availability(
        "2", "ROST", "2026-08-01"
    ) == (72, 28, 68, 32, True)
