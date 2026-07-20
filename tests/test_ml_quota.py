"""Concurrency tests for the gateway ML allowance ledger."""

import threading
from concurrent.futures import ThreadPoolExecutor

import redis

from apiserver import ml_quota


class _AtomicRedis:
    def __init__(self, initial=0):
        self.value = initial
        self.eval_calls = []
        self._lock = threading.Lock()

    def eval(self, script, key_count, key, *args):
        assert key_count == 1 and key.startswith("mlq:")
        with self._lock:
            self.eval_calls.append((script, key, args))
            if script == ml_quota._CONSUME_LUA:
                limit, requested, _ttl = map(int, args)
                grant = min(requested, max(0, limit - self.value))
                self.value += grant
                return grant
            if script == ml_quota._REFUND_LUA:
                amount, _ttl = map(int, args)
                self.value = max(0, self.value - amount)
                return self.value
            raise AssertionError("unexpected Lua program")


class _UnavailableRedis:
    def eval(self, *_args):
        raise redis.RedisError("counter unavailable")


def _customer(limit=5):
    return {"user_id": "quota-race-test", "entitlements": {"ml_daily_limit": limit}}


def test_twenty_simultaneous_consumers_cannot_overspend_last_unit(monkeypatch):
    ledger = _AtomicRedis(initial=4)
    monkeypatch.setattr(ml_quota, "_redis", ledger)
    start = threading.Barrier(20)

    def consume_one(_index):
        start.wait(timeout=5)
        return ml_quota.consume(_customer(), 1)

    with ThreadPoolExecutor(max_workers=20) as executor:
        grants = list(executor.map(consume_one, range(20)))

    assert sum(grants) == 1
    assert ledger.value == 5
    assert len(ledger.eval_calls) == 20


def test_refund_and_consume_are_individually_atomic(monkeypatch):
    ledger = _AtomicRedis(initial=3)
    monkeypatch.setattr(ml_quota, "_redis", ledger)
    ml_quota.refund(_customer(), 2)
    assert ml_quota.consume(_customer(), 10) == 4
    ml_quota.refund(_customer(), 99)
    assert ledger.value == 0


def test_redis_outage_fails_open_except_for_zero_limit(monkeypatch):
    monkeypatch.setattr(ml_quota, "_redis", _UnavailableRedis())
    assert ml_quota.consume(_customer(5), 3) == 3
    assert ml_quota.consume(_customer(0), 3) == 0


def test_unlimited_tier_never_touches_redis(monkeypatch):
    monkeypatch.setattr(ml_quota, "_redis", _UnavailableRedis())
    assert ml_quota.consume(_customer(None), 7) == 7
    ml_quota.refund(_customer(None), 7)


def test_public_demo_ml_allowance_uses_the_per_client_metering_bucket(monkeypatch):
    ledger = _AtomicRedis()
    monkeypatch.setattr(ml_quota, "_redis", ledger)
    demo = _customer(25)
    demo.update({"user_id": "demo", "metering_id": "demo:visitor-a"})

    assert ml_quota.consume(demo, 1) == 1
    assert ledger.eval_calls[0][1].startswith("mlq:demo:visitor-a:")
