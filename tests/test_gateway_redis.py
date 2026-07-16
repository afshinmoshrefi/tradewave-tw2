"""Deployment-neutral gateway Redis selection."""

import pytest

from apiserver import gateway_redis

pytestmark = pytest.mark.unit


def test_explicit_gateway_url_is_used_for_split_topology(monkeypatch):
    captured = {}
    sentinel = object()

    def from_url(url, **kwargs):
        captured.update(url=url, kwargs=kwargs)
        return sentinel

    monkeypatch.setattr(
        gateway_redis.settings,
        "GATEWAY_REDIS_URL",
        "rediss://gateway.example.test:6380/4",
    )
    monkeypatch.setattr(gateway_redis.redis.Redis, "from_url", from_url)
    assert gateway_redis.create_client() is sentinel
    assert captured["url"] == "rediss://gateway.example.test:6380/4"
    assert captured["kwargs"]["decode_responses"] is False
    assert captured["kwargs"]["socket_connect_timeout"] == 1.0


def test_co_located_fallback_keeps_gateway_on_configured_db(monkeypatch):
    captured = {}
    sentinel = object()

    def client(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(gateway_redis.settings, "GATEWAY_REDIS_URL", "")
    monkeypatch.setattr(gateway_redis.settings, "REDIS_HOST", "127.0.0.9")
    monkeypatch.setattr(gateway_redis.settings, "REDIS_PORT", 6381)
    monkeypatch.setattr(gateway_redis.settings, "REDIS_DB", 4)
    monkeypatch.setattr(gateway_redis.redis, "Redis", client)
    assert gateway_redis.create_client() is sentinel
    assert captured["host"] == "127.0.0.9"
    assert captured["port"] == 6381
    assert captured["db"] == 4
