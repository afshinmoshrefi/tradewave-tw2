#!/usr/bin/env python3
"""Release-blocking public MCP concurrency probe.

Creates independent public TLS clients and MCP sessions, synchronizes each
protocol phase, calls the cheap read-only ``whoami`` tool through the gateway,
and closes every session.  This is deliberately a real nginx/FastMCP/gateway
probe; the deploy runs it only after the candidate has been activated inside the
automatic rollback transaction.
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import importlib.util
import json
import ssl
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable, Mapping

_CONTRACT_PATH = Path(__file__).resolve().with_name("verify_mcp_contract.py")
_CONTRACT_SPEC = importlib.util.spec_from_file_location(
    "_tradewave_trusted_verify_mcp_contract", _CONTRACT_PATH
)
if _CONTRACT_SPEC is None or _CONTRACT_SPEC.loader is None:
    raise RuntimeError("cannot load the fixed MCP contract verifier")
_CONTRACT = importlib.util.module_from_spec(_CONTRACT_SPEC)
_CONTRACT_SPEC.loader.exec_module(_CONTRACT)

PROTOCOL_VERSION = _CONTRACT.PROTOCOL_VERSION
LEGACY_PROTOCOL_VERSION = _CONTRACT.LEGACY_PROTOCOL_VERSION
ProbeError = _CONTRACT.ProbeError
_message_for_id = _CONTRACT._message_for_id
load_verifier_token = _CONTRACT.load_verifier_token
validate_legacy_inventory = _CONTRACT.validate_legacy_inventory
validate_tool_inventory = _CONTRACT.validate_tool_inventory
validate_whoami_result = _CONTRACT.validate_whoami_result


class LoadProbeError(RuntimeError):
    """A release-blocking concurrent protocol failure."""


DEFAULT_PHASE_MAX_SECONDS = 5.0
DEFAULT_WHOAMI_P95_MAX_SECONDS = 2.0
DEFAULT_WHOAMI_MAX_SECONDS = 3.0
DEFAULT_SESSION_P95_MAX_SECONDS = 12.0
DEFAULT_SESSION_MAX_SECONDS = 15.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes


SyncRequest = Callable[
    [str, str, Mapping[str, str], dict[str, object] | None], HttpResponse
]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class StdlibHttpClient:
    """One proxy-free stdlib HTTPS client boundary per logical MCP session."""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            _NoRedirect(),
        )

    @staticmethod
    def _read_bounded(response) -> bytes:  # noqa: ANN001
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ProbeError("MCP response exceeded the load-gate safety bound")
        return payload

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: dict[str, object] | None,
    ) -> HttpResponse:
        payload = None
        if body is not None:
            payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers=dict(headers),
            method=method,
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                return HttpResponse(
                    status_code=response.status,
                    headers=response.headers,
                    content=self._read_bounded(response),
                )
        except urllib.error.HTTPError as exc:
            try:
                content = self._read_bounded(exc)
            finally:
                exc.close()
            return HttpResponse(
                status_code=exc.code,
                headers=exc.headers,
                content=content,
            )


@dataclass
class Session:
    number: int
    request: SyncRequest
    executor: concurrent.futures.ThreadPoolExecutor
    started_at: float
    session_id: str = ""
    whoami_seconds: float = 0.0
    total_seconds: float = 0.0


async def _request(
    session: Session,
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: dict[str, object] | None = None,
) -> HttpResponse:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        session.executor,
        partial(session.request, method, url, headers, body),
    )


def _headers(
    token: str, protocol_version: str, session_id: str | None = None
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": protocol_version,
        "User-Agent": "TradeWave-MCP-Load-Gate/1.0",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return headers


async def _phase(
    name: str,
    sessions: list[Session],
    operation,
    *,
    max_seconds: float,
) -> float:
    started = time.perf_counter()
    results = await asyncio.gather(
        *(operation(session) for session in sessions), return_exceptions=True
    )
    elapsed = time.perf_counter() - started
    failures = [
        f"client {session.number}: {result}"
        for session, result in zip(sessions, results)
        if isinstance(result, BaseException)
    ]
    if failures:
        excerpt = "; ".join(failures[:5])
        if len(failures) > 5:
            excerpt += f"; ... {len(failures) - 5} more"
        raise LoadProbeError(
            f"{name} failed for {len(failures)}/{len(sessions)} sessions: {excerpt}"
        )
    if elapsed > max_seconds:
        raise LoadProbeError(
            f"{name} phase took {elapsed:.3f}s, exceeding {max_seconds:.3f}s SLO; "
            "concurrent sessions may be serializing"
        )
    return elapsed


async def _initialize(
    session: Session, url: str, token: str, protocol_version: str
) -> None:
    request_id = 1000 + session.number
    response = await _request(
        session,
        "POST",
        url,
        _headers(token, protocol_version),
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {
                    "name": f"tradewave-load-gate-{session.number}",
                    "version": "1",
                },
            },
        },
    )
    if response.status_code != 200:
        raise ProbeError(f"initialize HTTP {response.status_code}")
    message = _message_for_id(response.content, request_id)
    result = message.get("result")
    if not isinstance(result, dict) or result.get("protocolVersion") != protocol_version:
        raise ProbeError("initialize did not negotiate the required protocol")
    session_id = response.headers.get("Mcp-Session-Id")
    if not session_id:
        raise ProbeError("initialize omitted Mcp-Session-Id")
    session.session_id = session_id


async def _initialized(
    session: Session, url: str, token: str, protocol_version: str
) -> None:
    response = await _request(
        session,
        "POST",
        url,
        _headers(token, protocol_version, session.session_id),
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        },
    )
    if response.status_code not in {200, 202}:
        raise ProbeError(f"notifications/initialized HTTP {response.status_code}")


async def _tools_list(
    session: Session,
    url: str,
    token: str,
    protocol_version: str,
    *,
    legacy_smoke: bool,
) -> None:
    request_id = 1500 + session.number
    response = await _request(
        session,
        "POST",
        url,
        _headers(token, protocol_version, session.session_id),
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": {},
        },
    )
    if response.status_code != 200:
        raise ProbeError(f"tools/list HTTP {response.status_code}")
    message = _message_for_id(response.content, request_id)
    result = message.get("result")
    tools = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(tools, list):
        raise ProbeError("tools/list omitted tools[]")
    if legacy_smoke:
        validate_legacy_inventory(tools)
    else:
        validate_tool_inventory(tools)


async def _whoami(
    session: Session, url: str, token: str, protocol_version: str
) -> None:
    request_id = 2000 + session.number
    started = time.perf_counter()
    response = await _request(
        session,
        "POST",
        url,
        _headers(token, protocol_version, session.session_id),
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": "whoami", "arguments": {}},
        },
    )
    session.whoami_seconds = time.perf_counter() - started
    if response.status_code != 200:
        raise ProbeError(f"whoami HTTP {response.status_code}")
    message = _message_for_id(response.content, request_id)
    validate_whoami_result(message.get("result"))


async def _delete(
    session: Session,
    url: str,
    token: str,
    protocol_version: str,
    *,
    legacy_smoke: bool,
) -> None:
    response = await _request(
        session,
        "DELETE",
        url,
        _headers(token, protocol_version, session.session_id),
    )
    accepted = {200} if legacy_smoke else {200, 204}
    if response.status_code not in accepted:
        raise ProbeError(f"DELETE HTTP {response.status_code}")
    session.total_seconds = time.perf_counter() - session.started_at


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * percentile) + 0.999999) - 1))
    return ordered[index]


async def run_load(
    url: str,
    token: str,
    *,
    clients: int = 20,
    timeout: float = 20.0,
    legacy_smoke: bool = False,
    phase_max_seconds: float = DEFAULT_PHASE_MAX_SECONDS,
    whoami_p95_max_seconds: float = DEFAULT_WHOAMI_P95_MAX_SECONDS,
    whoami_max_seconds: float = DEFAULT_WHOAMI_MAX_SECONDS,
    session_p95_max_seconds: float = DEFAULT_SESSION_P95_MAX_SECONDS,
    session_max_seconds: float = DEFAULT_SESSION_MAX_SECONDS,
    request_factory: Callable[[int], SyncRequest] | None = None,
) -> dict[str, float]:
    if clients < 1 or clients > 100:
        raise LoadProbeError("clients must be in 1..100")
    thresholds = {
        "phase_max_seconds": phase_max_seconds,
        "whoami_p95_max_seconds": whoami_p95_max_seconds,
        "whoami_max_seconds": whoami_max_seconds,
        "session_p95_max_seconds": session_p95_max_seconds,
        "session_max_seconds": session_max_seconds,
    }
    if any(value <= 0 for value in thresholds.values()):
        raise LoadProbeError("all latency SLO thresholds must be positive")
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise LoadProbeError("public load gate requires an absolute HTTPS URL")
    if not parsed.path:
        url += "/"

    def default_factory(_number: int) -> SyncRequest:
        return StdlibHttpClient(timeout).request

    factory = request_factory or default_factory
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=clients,
        thread_name_prefix="tradewave-mcp-load",
    )
    try:
        sessions = [
            Session(
                number=i,
                request=factory(i),
                executor=executor,
                started_at=time.perf_counter(),
            )
            for i in range(clients)
        ]
        phases: dict[str, float] = {}
        protocol_version = LEGACY_PROTOCOL_VERSION if legacy_smoke else PROTOCOL_VERSION
        phases["initialize"] = await _phase(
            "initialize",
            sessions,
            lambda item: _initialize(item, url, token, protocol_version),
            max_seconds=phase_max_seconds,
        )
        session_ids = [session.session_id for session in sessions]
        if len(set(session_ids)) != clients:
            raise LoadProbeError("initialize did not create independent unique MCP sessions")
        phases["initialized"] = await _phase(
            "notifications/initialized",
            sessions,
            lambda item: _initialized(item, url, token, protocol_version),
            max_seconds=phase_max_seconds,
        )
        phases["tools_list"] = await _phase(
            "tools/list",
            sessions,
            lambda item: _tools_list(
                item,
                url,
                token,
                protocol_version,
                legacy_smoke=legacy_smoke,
            ),
            max_seconds=phase_max_seconds,
        )
        phases["whoami"] = await _phase(
            "whoami",
            sessions,
            lambda item: _whoami(item, url, token, protocol_version),
            max_seconds=phase_max_seconds,
        )
        phases["delete"] = await _phase(
            "DELETE",
            sessions,
            lambda item: _delete(
                item,
                url,
                token,
                protocol_version,
                legacy_smoke=legacy_smoke,
            ),
            max_seconds=phase_max_seconds,
        )
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    whoami = [session.whoami_seconds for session in sessions]
    total = [session.total_seconds for session in sessions]
    metrics = {
        "clients": float(clients),
        "whoami_p50": statistics.median(whoami),
        "whoami_p95": _percentile(whoami, 0.95),
        "whoami_max": max(whoami),
        "session_p50": statistics.median(total),
        "session_p95": _percentile(total, 0.95),
        "session_max": max(total),
        **{f"phase_{name}": elapsed for name, elapsed in phases.items()},
    }
    violations = []
    for metric, limit in (
        ("whoami_p95", whoami_p95_max_seconds),
        ("whoami_max", whoami_max_seconds),
        ("session_p95", session_p95_max_seconds),
        ("session_max", session_max_seconds),
    ):
        if metrics[metric] > limit:
            violations.append(f"{metric}={metrics[metric]:.3f}s > {limit:.3f}s")
    if violations:
        raise LoadProbeError("latency SLO failed: " + "; ".join(violations))
    return metrics


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify independent public MCP sessions under 20-chat concurrency"
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--clients", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--phase-max-seconds", type=float, default=DEFAULT_PHASE_MAX_SECONDS)
    parser.add_argument(
        "--whoami-p95-max-seconds", type=float, default=DEFAULT_WHOAMI_P95_MAX_SECONDS
    )
    parser.add_argument(
        "--whoami-max-seconds", type=float, default=DEFAULT_WHOAMI_MAX_SECONDS
    )
    parser.add_argument(
        "--session-p95-max-seconds", type=float, default=DEFAULT_SESSION_P95_MAX_SECONDS
    )
    parser.add_argument(
        "--session-max-seconds", type=float, default=DEFAULT_SESSION_MAX_SECONDS
    )
    parser.add_argument(
        "--legacy-smoke",
        action="store_true",
        help="First seeded rollback only: allow its pre-17 nonempty unique inventory",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        token = load_verifier_token()
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    try:
        metrics = asyncio.run(
            run_load(
                args.url,
                token,
                clients=args.clients,
                timeout=args.timeout,
                legacy_smoke=args.legacy_smoke,
                phase_max_seconds=args.phase_max_seconds,
                whoami_p95_max_seconds=args.whoami_p95_max_seconds,
                whoami_max_seconds=args.whoami_max_seconds,
                session_p95_max_seconds=args.session_p95_max_seconds,
                session_max_seconds=args.session_max_seconds,
            )
        )
    except (LoadProbeError, ProbeError, OSError, asyncio.TimeoutError) as exc:
        print(f"FAIL: public MCP load gate: {exc}", file=sys.stderr)
        return 1
    completed = int(metrics["clients"])
    print(
        f"PASS: {completed}/{completed} independent public MCP sessions; "
        "whoami p50={whoami_p50:.3f}s p95={whoami_p95:.3f}s max={whoami_max:.3f}s; "
        "full-session p50={session_p50:.3f}s p95={session_p95:.3f}s "
        "max={session_max:.3f}s; phase walls initialize={phase_initialize:.3f}s "
        "initialized={phase_initialized:.3f}s tools/list={phase_tools_list:.3f}s "
        "whoami={phase_whoami:.3f}s DELETE={phase_delete:.3f}s".format(**metrics)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
