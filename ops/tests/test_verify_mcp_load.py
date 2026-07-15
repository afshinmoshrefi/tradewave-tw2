"""Hermetic protocol test for the real-public-session load-gate client."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ops"))
import verify_mcp_load as load  # noqa: E402
import verify_mcp_contract as contract  # noqa: E402


def _whoami_result(*, is_error=False):
    payload = {
        "tier": "pro",
        "tier_name": "Pro",
        "rate": {"per_minute": 120, "per_day": 5000},
        "ml_remaining_today": None,
        "markets_in_scope": [{"id": "2", "name": "S&P 500"}],
        "example_prompts": ["Find the best seasonal trades"],
    }
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    "You are on the Pro plan with unlimited ML scorings/day.\n\n"
                    + json.dumps(payload, separators=(",", ":"))
                ),
            }
        ],
        "isError": is_error,
    }


def _transport(
    *,
    fail_session=None,
    whoami_delay=0.0,
    serialize_whoami=False,
    protocol_version=load.PROTOCOL_VERSION,
    delete_status=200,
    initialize_barrier=None,
    wire=None,
):
    calls = []
    if wire is None:
        wire = []
    whoami_lock = threading.Lock()
    record_lock = threading.Lock()

    def response(status, *, headers=None, payload=None):
        content = b"" if payload is None else json.dumps(payload).encode("utf-8")
        return load.HttpResponse(status, headers or {}, content)

    def handler(method, _url, headers, message):
        with record_lock:
            calls.append((method, headers.get("Mcp-Session-Id")))
            wire.append(
                {
                    "method": method,
                    "protocol_header": headers.get("MCP-Protocol-Version"),
                    "message": message,
                }
            )
        if method == "DELETE":
            return response(delete_status)
        method = message["method"]
        if method == "initialize":
            if initialize_barrier is not None:
                initialize_barrier.wait(timeout=2)
            session_id = f"session-{message['id']}"
            return response(
                200,
                headers={"Mcp-Session-Id": session_id},
                payload={
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "protocolVersion": protocol_version,
                        "serverInfo": {"name": "test", "version": "1"},
                    },
                },
            )
        if method == "notifications/initialized":
            return response(202)
        if method == "tools/list":
            return response(
                200,
                payload={
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "tools": [
                            {"name": name} for name in contract.EXPECTED_SCHEMAS
                        ]
                    },
                },
            )
        if method == "tools/call":
            if serialize_whoami:
                with whoami_lock:
                    time.sleep(whoami_delay)
            elif whoami_delay:
                time.sleep(whoami_delay)
            session_id = headers.get("Mcp-Session-Id")
            return response(
                200,
                payload={
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": _whoami_result(is_error=session_id == fail_session),
                },
            )
        raise AssertionError(method)

    return handler, calls


def test_twenty_independent_full_sessions_pass():
    transport, calls = _transport()
    metrics = asyncio.run(
        load.run_load(
            "https://mcp.example/",
            "secret",
            clients=20,
            request_factory=lambda _number: transport,
        )
    )
    assert metrics["clients"] == 20
    assert len(calls) == 20 * 5
    initialized_sessions = [session for method, session in calls if method == "DELETE"]
    assert len(set(initialized_sessions)) == 20


def test_twenty_initialize_requests_enter_concurrently():
    barrier = threading.Barrier(20)
    transport, _calls = _transport(initialize_barrier=barrier)
    metrics = asyncio.run(
        load.run_load(
            "https://mcp.example/",
            "secret",
            clients=20,
            request_factory=lambda _number: transport,
        )
    )
    assert metrics["clients"] == 20


def test_legacy_smoke_uses_legacy_protocol_on_every_wire_message():
    wire = []
    transport, _calls = _transport(
        protocol_version=load.LEGACY_PROTOCOL_VERSION,
        wire=wire,
    )
    metrics = asyncio.run(
        load.run_load(
            "https://mcp.example/",
            "secret",
            clients=2,
            legacy_smoke=True,
            request_factory=lambda _number: transport,
        )
    )
    assert metrics["clients"] == 2
    assert wire
    assert {item["protocol_header"] for item in wire} == {
        load.LEGACY_PROTOCOL_VERSION
    }
    initialize = [
        item["message"]
        for item in wire
        if item["message"] and item["message"].get("method") == "initialize"
    ]
    assert len(initialize) == 2
    assert {
        item["params"]["protocolVersion"] for item in initialize
    } == {load.LEGACY_PROTOCOL_VERSION}


def test_legacy_smoke_codifies_seeded_runtime_delete_as_exact_200():
    transport, _calls = _transport(
        protocol_version=load.LEGACY_PROTOCOL_VERSION,
        delete_status=405,
    )
    with pytest.raises(load.LoadProbeError, match="DELETE failed for 2/2.*DELETE HTTP 405"):
        asyncio.run(
            load.run_load(
                "https://mcp.example/",
                "secret",
                clients=2,
                legacy_smoke=True,
                request_factory=lambda _number: transport,
            )
        )


def test_any_whoami_error_fails_the_gate():
    transport, _calls = _transport(fail_session="session-1003")
    with pytest.raises(load.LoadProbeError, match="whoami failed for 1/20"):
        asyncio.run(
            load.run_load(
                "https://mcp.example/",
                "secret",
                clients=20,
                request_factory=lambda _number: transport,
            )
        )


def test_serialized_sessions_fail_the_phase_wall_clock_slo():
    transport, _calls = _transport(whoami_delay=0.02, serialize_whoami=True)
    with pytest.raises(load.LoadProbeError, match="whoami phase took.*serializing"):
        asyncio.run(
            load.run_load(
                "https://mcp.example/",
                "secret",
                clients=20,
                phase_max_seconds=0.15,
                request_factory=lambda _number: transport,
            )
        )


def test_slow_parallel_whoami_fails_the_p95_slo():
    transport, _calls = _transport(whoami_delay=0.03)
    with pytest.raises(load.LoadProbeError, match="latency SLO failed: whoami_p95"):
        asyncio.run(
            load.run_load(
                "https://mcp.example/",
                "secret",
                clients=20,
                phase_max_seconds=1.0,
                whoami_p95_max_seconds=0.01,
                request_factory=lambda _number: transport,
            )
        )


@pytest.mark.parametrize(
    "changes",
    (
        {"tier": "demo", "tier_name": "Demo"},
        {"tier": "dev", "tier_name": "Dev"},
        {"tier": "mcp", "tier_name": "MCP"},
        {"rate": {"per_minute": 119, "per_day": 5000}},
        {"rate": {"per_minute": 120, "per_day": 4999}},
    ),
)
def test_whoami_proof_rejects_token_substitution_or_under_capacity(changes):
    result = _whoami_result()
    lead, payload_text = result["content"][0]["text"].split("\n\n", 1)
    payload = json.loads(payload_text)
    payload.update(changes)
    result["content"][0]["text"] = lead + "\n\n" + json.dumps(payload)
    with pytest.raises(contract.ProbeError, match="dedicated Pro"):
        contract.validate_whoami_result(result)


def test_load_main_rejects_demo_and_customer_fallbacks_before_network(monkeypatch):
    monkeypatch.delenv("TW_MCP_VERIFY_TOKEN", raising=False)
    monkeypatch.setenv("TRADEWAVE_API_KEY", "tw_live_" + "a" * 32)
    monkeypatch.setenv("TW2_DEMO_API_KEY", "tw_demo_explore")
    monkeypatch.setattr(
        load,
        "run_load",
        lambda *_args, **_kwargs: pytest.fail("network probe ran without dedicated verifier"),
    )
    assert load.main(["--url", "https://mcp.example/"]) == 2
