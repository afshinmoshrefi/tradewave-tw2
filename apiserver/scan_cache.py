"""Shared, deployment-neutral cache for reusable API scan data.

The cache stores only a price-safe scan core. Authentication, rate limiting,
entitlements, ML quota, tier notes, and final response projection remain outside
this module and run for every request. Redis coordinates all gunicorn workers and
future API nodes. A small local semaphore protects the appserver if Redis is down.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import redis

from . import settings
from .gateway_redis import create_client

log = logging.getLogger("apiserver.scan_cache")

_CACHE_SCHEMA = 1
_CACHE_PREFIX = "tw:api:scan-core:v1:"
_FLIGHT_RESULT_TTL_SECONDS = 2
_redis = create_client()
_local_build_slots = threading.BoundedSemaphore(settings.SCAN_CACHE_LOCAL_BUILD_SLOTS)

_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class BuildResult:
    value: dict[str, Any]
    cacheable: bool = True


@dataclass(frozen=True)
class CacheResult:
    value: dict[str, Any]
    status: str  # HIT | MISS | WAIT | BYPASS


class ScanBuildBusy(RuntimeError):
    """A cold scan is already being built and did not publish within the wait."""


def make_key(payload: dict[str, Any]) -> str:
    """Canonical, credential-free cache key for normalized scan inputs."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return _CACHE_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _decode(raw) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        envelope = json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(envelope, dict) or envelope.get("schema") != _CACHE_SCHEMA:
        return None
    value = envelope.get("value")
    return value if isinstance(value, dict) else None


def _read(key: str) -> dict[str, Any] | None:
    return _decode(_redis.get(key))


def _run_builder(builder: Callable[[], BuildResult | dict[str, Any]]) -> BuildResult:
    acquired = _local_build_slots.acquire(timeout=settings.SCAN_CACHE_WAIT_SECONDS)
    if not acquired:
        raise ScanBuildBusy("all local cold-scan build slots are occupied")
    try:
        built = builder()
    finally:
        _local_build_slots.release()
    if isinstance(built, BuildResult):
        return built
    if not isinstance(built, dict):
        raise TypeError("scan cache builder must return dict or BuildResult")
    return BuildResult(built)


def _release_lock(lock_key: str, token: str) -> None:
    try:
        _redis.eval(_RELEASE_LOCK_LUA, 1, lock_key, token)
    except redis.RedisError as exc:
        log.warning("scan cache lock release failed: %s", exc)


def _clear_flight_result(key: str) -> None:
    try:
        _redis.delete(key + ":flight")
    except redis.RedisError as exc:
        log.warning("scan cache stale flight-result cleanup failed: %s", exc)


def _owner_build(key: str, lock_key: str, token: str,
                 builder: Callable[[], BuildResult | dict[str, Any]]) -> CacheResult:
    try:
        built = _run_builder(builder)
        if built.cacheable and settings.SCAN_CACHE_TTL_SECONDS > 0:
            envelope = json.dumps(
                {"schema": _CACHE_SCHEMA, "value": built.value},
                separators=(",", ":"),
                ensure_ascii=True,
            )
            try:
                _redis.setex(key, settings.SCAN_CACHE_TTL_SECONDS, envelope)
            except redis.RedisError as exc:
                log.warning("scan cache publish failed; serving computed result: %s", exc)
                return CacheResult(built.value, "BYPASS")
        elif not built.cacheable:
            # A partial/degraded core must not enter the normal cache. Publish it only
            # as a two-second single-flight handoff so requests already waiting on this
            # owner share its exact result instead of each rebuilding under an outage.
            envelope = json.dumps(
                {"schema": _CACHE_SCHEMA, "value": built.value},
                separators=(",", ":"),
                ensure_ascii=True,
            )
            try:
                _redis.setex(key + ":flight", _FLIGHT_RESULT_TTL_SECONDS, envelope)
            except redis.RedisError as exc:
                log.warning("scan cache degraded flight-result publish failed: %s", exc)
        return CacheResult(built.value, "MISS" if built.cacheable else "BYPASS")
    finally:
        _release_lock(lock_key, token)


def _local_bypass(builder: Callable[[], BuildResult | dict[str, Any]], reason: Exception) -> CacheResult:
    log.warning("scan cache unavailable; using bounded local build: %s", reason)
    built = _run_builder(builder)
    return CacheResult(built.value, "BYPASS")


def _after_lock_acquired(key: str, lock_key: str, token: str,
                         builder: Callable[[], BuildResult | dict[str, Any]],
                         cached_status: str) -> CacheResult:
    """Recheck after NX succeeds, closing the read-miss/lock-acquire race.

    Another owner can publish and release between this caller's initial cache read and
    its SET NX. Without this second read, the caller becomes a redundant cold owner even
    though the result is already present. The short degraded flight result is checked too,
    so a burst never repeats a just-finished partial build.
    """
    try:
        cached = _read(key)
        if cached is not None:
            _release_lock(lock_key, token)
            return CacheResult(cached, cached_status)
        flight_result = _read(key + ":flight")
        if flight_result is not None:
            _release_lock(lock_key, token)
            return CacheResult(flight_result, "WAIT")
    except redis.RedisError as exc:
        _release_lock(lock_key, token)
        return _local_bypass(builder, exc)
    _clear_flight_result(key)
    return _owner_build(key, lock_key, token, builder)


def get_or_build(key: str, builder: Callable[[], BuildResult | dict[str, Any]]) -> CacheResult:
    """Return a cached core or coordinate exactly one cold build across API nodes.

    Waiters never duplicate a healthy owner's work. If Redis is unavailable, each
    process permits only a bounded number of local cold builds. If the wait expires,
    the caller receives ScanBuildBusy and should return a retryable 503 rather than
    creating an appserver stampede.
    """
    if settings.SCAN_CACHE_TTL_SECONDS <= 0:
        built = _run_builder(builder)
        return CacheResult(built.value, "BYPASS")

    try:
        cached = _read(key)
    except redis.RedisError as exc:
        return _local_bypass(builder, exc)
    if cached is not None:
        return CacheResult(cached, "HIT")

    lock_key = key + ":lock"
    token = uuid.uuid4().hex
    try:
        acquired = bool(_redis.set(
            lock_key, token, nx=True, ex=settings.SCAN_CACHE_LOCK_SECONDS
        ))
    except redis.RedisError as exc:
        return _local_bypass(builder, exc)
    if acquired:
        return _after_lock_acquired(
            key, lock_key, token, builder, cached_status="HIT"
        )

    deadline = time.monotonic() + settings.SCAN_CACHE_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(0.05)
        try:
            cached = _read(key)
            if cached is not None:
                return CacheResult(cached, "WAIT")
            flight_result = _read(key + ":flight")
            if flight_result is not None:
                return CacheResult(flight_result, "WAIT")
            # The owner may have exited without publishing a degraded result or may
            # have crashed. Re-acquire only after its token is gone; NX enforces that.
            acquired = bool(_redis.set(
                lock_key, token, nx=True, ex=settings.SCAN_CACHE_LOCK_SECONDS
            ))
        except redis.RedisError as exc:
            return _local_bypass(builder, exc)
        if acquired:
            return _after_lock_acquired(
                key, lock_key, token, builder, cached_status="WAIT"
            )

    raise ScanBuildBusy("shared cold scan did not publish before the wait deadline")
