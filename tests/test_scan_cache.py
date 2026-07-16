"""Shared scan-core cache: key safety, single-flight, and degraded behavior."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import redis

from apiserver import scan_cache

pytestmark = pytest.mark.unit


class _FakeRedis:
    def __init__(self):
        self.values = {}
        self.lock = threading.RLock()

    def get(self, key):
        with self.lock:
            return self.values.get(key)

    def set(self, key, value, nx=False, ex=None):
        del ex
        with self.lock:
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

    def setex(self, key, ttl, value):
        del ttl
        with self.lock:
            self.values[key] = value
        return True

    def delete(self, key):
        with self.lock:
            return 1 if self.values.pop(key, None) is not None else 0

    def eval(self, script, numkeys, key, token):
        del script, numkeys
        with self.lock:
            if self.values.get(key) == token:
                del self.values[key]
                return 1
        return 0


class _UnavailableRedis:
    def __getattr__(self, _name):
        def unavailable(*_args, **_kwargs):
            raise redis.ConnectionError("redis unavailable")
        return unavailable


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(scan_cache.settings, "SCAN_CACHE_TTL_SECONDS", 120)
    monkeypatch.setattr(scan_cache.settings, "SCAN_CACHE_WAIT_SECONDS", 1.0)
    monkeypatch.setattr(scan_cache.settings, "SCAN_CACHE_LOCK_SECONDS", 15)
    monkeypatch.setattr(scan_cache, "_local_build_slots", threading.BoundedSemaphore(1))


def test_key_is_canonical_hashed_and_contains_no_credential_material():
    first = scan_cache.make_key({"markets": ["2", "4"], "depth": 5})
    second = scan_cache.make_key({"depth": 5, "markets": ["2", "4"]})
    assert first == second
    assert first.startswith("tw:api:scan-core:v1:")
    assert "Bearer" not in first and "user" not in first
    assert len(first.rsplit(":", 1)[-1]) == 64


def test_sequential_miss_then_hit_builds_once(monkeypatch):
    backend = _FakeRedis()
    monkeypatch.setattr(scan_cache, "_redis", backend)
    calls = {"count": 0}

    def build():
        calls["count"] += 1
        return {"candidates": [{"symbol": "AAPL"}]}

    first = scan_cache.get_or_build("scan-key", build)
    second = scan_cache.get_or_build("scan-key", build)
    assert (first.status, second.status) == ("MISS", "HIT")
    assert first.value == second.value
    assert calls["count"] == 1


def test_concurrent_cold_requests_have_one_builder(monkeypatch):
    backend = _FakeRedis()
    monkeypatch.setattr(scan_cache, "_redis", backend)
    calls = {"count": 0}
    calls_lock = threading.Lock()
    start = threading.Barrier(20)

    def build():
        with calls_lock:
            calls["count"] += 1
        time.sleep(0.1)
        return {"evaluated_count": 5, "candidates": []}

    def request():
        start.wait()
        return scan_cache.get_or_build("shared-cold-key", build)

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _index: request(), range(20)))

    assert calls["count"] == 1
    assert sum(result.status == "MISS" for result in results) == 1
    assert all(result.value["evaluated_count"] == 5 for result in results)
    assert all(result.status in {"MISS", "WAIT", "HIT"} for result in results)


def test_degraded_build_is_not_published(monkeypatch):
    backend = _FakeRedis()
    monkeypatch.setattr(scan_cache, "_redis", backend)
    calls = {"count": 0}

    def build():
        calls["count"] += 1
        return scan_cache.BuildResult({"candidates": []}, cacheable=False)

    assert scan_cache.get_or_build("degraded", build).status == "BYPASS"
    # The two-second flight handoff may serve a request that races just after the
    # owner. It is separate from the normal cache and prevents an outage stampede.
    assert scan_cache.get_or_build("degraded", build).status == "WAIT"
    assert calls["count"] == 1
    assert "degraded" not in backend.values
    backend.delete("degraded:flight")
    assert scan_cache.get_or_build("degraded", build).status == "BYPASS"
    assert calls["count"] == 2


def test_concurrent_degraded_requests_share_only_the_flight_result(monkeypatch):
    backend = _FakeRedis()
    monkeypatch.setattr(scan_cache, "_redis", backend)
    calls = {"count": 0}
    calls_lock = threading.Lock()
    start = threading.Barrier(10)

    def build():
        with calls_lock:
            calls["count"] += 1
        time.sleep(0.1)
        return scan_cache.BuildResult({"partial": True}, cacheable=False)

    def request():
        start.wait()
        return scan_cache.get_or_build("degraded-burst", build)

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _index: request(), range(10)))

    assert calls["count"] == 1
    assert all(result.value == {"partial": True} for result in results)
    assert sum(result.status == "BYPASS" for result in results) == 1
    assert all(result.status in {"BYPASS", "WAIT"} for result in results)
    assert "degraded-burst" not in backend.values


def test_invalid_envelope_is_replaced(monkeypatch):
    backend = _FakeRedis()
    backend.values["bad"] = json.dumps({"schema": 999, "value": {"wrong": True}})
    monkeypatch.setattr(scan_cache, "_redis", backend)
    result = scan_cache.get_or_build("bad", lambda: {"right": True})
    assert result.status == "MISS"
    assert result.value == {"right": True}


def test_invalid_utf8_cache_value_is_treated_as_a_miss(monkeypatch):
    backend = _FakeRedis()
    backend.values["bad-bytes"] = b"\xff\xfe"
    monkeypatch.setattr(scan_cache, "_redis", backend)
    result = scan_cache.get_or_build("bad-bytes", lambda: {"right": True})
    assert result.status == "MISS"
    assert result.value == {"right": True}


def test_redis_outage_uses_bounded_local_build(monkeypatch):
    monkeypatch.setattr(scan_cache, "_redis", _UnavailableRedis())
    result = scan_cache.get_or_build("outage", lambda: {"usable": True})
    assert result.status == "BYPASS"
    assert result.value == {"usable": True}


def test_redis_outage_does_not_create_unbounded_local_builds(monkeypatch):
    monkeypatch.setattr(scan_cache, "_redis", _UnavailableRedis())
    monkeypatch.setattr(scan_cache.settings, "SCAN_CACHE_WAIT_SECONDS", 0.05)
    entered = threading.Event()
    release = threading.Event()

    def slow_build():
        entered.set()
        release.wait(timeout=1)
        return {"ok": True}

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(scan_cache.get_or_build, "one", slow_build)
        assert entered.wait(timeout=1)
        waiter = pool.submit(scan_cache.get_or_build, "two", lambda: {"duplicate": True})
        with pytest.raises(scan_cache.ScanBuildBusy):
            waiter.result(timeout=1)
        release.set()
        assert owner.result(timeout=1).status == "BYPASS"


def test_wait_deadline_returns_retryable_busy_instead_of_duplicate(monkeypatch):
    backend = _FakeRedis()
    backend.values["held:lock"] = "another-owner"
    monkeypatch.setattr(scan_cache, "_redis", backend)
    monkeypatch.setattr(scan_cache.settings, "SCAN_CACHE_WAIT_SECONDS", 0.08)
    calls = {"count": 0}

    def build():
        calls["count"] += 1
        return {"duplicate": True}

    with pytest.raises(scan_cache.ScanBuildBusy):
        scan_cache.get_or_build("held", build)
    assert calls["count"] == 0


def test_lock_winner_rechecks_cache_before_building(monkeypatch):
    """Reproduce a publish between initial GET miss and SET NX success."""
    backend = _FakeRedis()
    calls = {"count": 0}
    original_set = backend.set

    def publish_then_acquire(key, value, nx=False, ex=None):
        if key == "race:lock" and nx and "race" not in backend.values:
            backend.values["race"] = json.dumps({
                "schema": scan_cache._CACHE_SCHEMA,
                "value": {"from_first_owner": True},
            })
        return original_set(key, value, nx=nx, ex=ex)

    backend.set = publish_then_acquire
    monkeypatch.setattr(scan_cache, "_redis", backend)

    def duplicate_build():
        calls["count"] += 1
        return {"duplicate": True}

    result = scan_cache.get_or_build("race", duplicate_build)
    assert result.status == "HIT"
    assert result.value == {"from_first_owner": True}
    assert calls["count"] == 0
