"""Protocol-compatibility release gates must validate a usable exact catalog."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load_verifier():
    path = ROOT / "ops" / "verify_mcp_contract.py"
    spec = importlib.util.spec_from_file_location("verify_mcp_protocol", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _json_body(request_id: int, result: dict) -> bytes:
    return json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "result": result}
    ).encode()


def _install_protocol_responder(monkeypatch, verifier, names: list[str]):
    calls: list[tuple[str, str | None]] = []

    def fake_request(_url, *, method="GET", headers=None, payload=None, **_kwargs):
        rpc_method = payload.get("method") if isinstance(payload, dict) else None
        calls.append((method, rpc_method))
        if headers:
            assert headers.get("MCP-Protocol-Version") == verifier.LEGACY_PROTOCOL_VERSION
        if rpc_method == "initialize":
            return (
                200,
                {"Mcp-Session-Id": "legacy-session"},
                _json_body(
                    payload["id"],
                    {"protocolVersion": verifier.LEGACY_PROTOCOL_VERSION},
                ),
            )
        if rpc_method == "notifications/initialized":
            return 202, {}, b""
        if rpc_method == "tools/list":
            cursor = payload["params"].get("cursor")
            midpoint = len(names) // 2
            page_names = names[:midpoint] if cursor is None else names[midpoint:]
            result = {"tools": [{"name": name} for name in page_names]}
            if cursor is None:
                result["nextCursor"] = "second-page"
            return 200, {}, _json_body(payload["id"], result)
        if method == "DELETE":
            return 204, {}, b""
        raise AssertionError((method, payload))

    monkeypatch.setattr(verifier, "_request", fake_request)
    return calls


def test_legacy_handshake_paginates_and_requires_exact_seventeen(monkeypatch):
    verifier = _load_verifier()
    names = list(verifier.EXPECTED_SCHEMAS)
    calls = _install_protocol_responder(monkeypatch, verifier, names)

    verifier.verify_protocol_handshake(
        "https://mcp.example.test/",
        "test-token",
        1.0,
        verifier.LEGACY_PROTOCOL_VERSION,
    )

    assert calls == [
        ("POST", "initialize"),
        ("POST", "notifications/initialized"),
        ("POST", "tools/list"),
        ("POST", "tools/list"),
        ("DELETE", None),
    ]


@pytest.mark.parametrize(
    "names",
    [
        lambda expected: expected[:15],
        lambda expected: expected + ["get_opportunity_for_symbol"],
    ],
)
def test_legacy_handshake_rejects_stale_or_ghost_catalog(monkeypatch, names):
    verifier = _load_verifier()
    published = names(list(verifier.EXPECTED_SCHEMAS))
    calls = _install_protocol_responder(monkeypatch, verifier, published)

    with pytest.raises(verifier.ProbeError, match="tool inventory drift|ghost|stale 15-tool"):
        verifier.verify_protocol_handshake(
            "https://mcp.example.test/",
            "test-token",
            1.0,
            verifier.LEGACY_PROTOCOL_VERSION,
        )

    assert ("DELETE", None) not in calls
