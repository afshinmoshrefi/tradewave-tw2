"""Release fingerprint and fail-closed Tara policy regressions."""

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
APPSERVER = ROOT / "appserver" / "appserver"
sys.path.insert(0, str(APPSERVER))

import tara_release_fingerprint as fingerprint  # noqa: E402
from tara_runtime_policy import public_policy, validate_policy  # noqa: E402

VERIFY_PATH = ROOT / "ops" / "verify_tara_release.py"


def test_release_policy_is_exact_and_contains_no_routing_switches():
    assert validate_policy()
    assert public_policy() == {
        "policy_version": "tara-model-policy-v2",
        "primary_provider": "openai",
        "primary_model": "gpt-5.6-luna",
        "fallback_provider": "anthropic",
        "fallback_model": "claude-haiku-4-5-20251001",
    }
    encoded = json.dumps(public_policy()).lower()
    assert "percent" not in encoded
    assert "bucket" not in encoded
    assert "environment" not in encoded


def test_runtime_fingerprint_is_stable_nonsecret_and_tracks_frontend_bundle(
    tmp_path, monkeypatch
):
    frontend = tmp_path / "build"
    bundle_dir = frontend / "static" / "js"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "main.test.js").write_bytes(b"exact compiled bundle")
    monkeypatch.setattr(fingerprint, "_release_sha", lambda: "a" * 40)

    first = fingerprint.runtime_fingerprint(frontend)
    second = fingerprint.runtime_fingerprint(frontend)

    assert first == second
    assert first["release_sha"] == "a" * 40
    assert first["primary_model"] == "gpt-5.6-luna"
    assert first["frontend_bundle_hash"] != "not-supplied"
    assert len(first["prompt_hash"]) == 64
    assert len(first["planner_hash"]) == 64
    assert len(first["nonsecret_config_hash"]) == 64
    assert len(first["fingerprint"]) == 64
    encoded = json.dumps(first).lower()
    assert "openai_key" not in encoded
    assert "anthropic_token" not in encoded
    assert "tara_gateway_key" not in encoded


def test_release_sha_uses_only_the_exact_worktree_safe_directory(monkeypatch):
    captured = {}

    def fake_check_output(command, **kwargs):
        captured["command"] = command
        return "b" * 40 + "\n"

    monkeypatch.setattr(fingerprint.subprocess, "check_output", fake_check_output)

    assert fingerprint._release_sha() == "b" * 40
    assert captured["command"][0:2] == ["git", "-c"]
    assert captured["command"][2] == f"safe.directory={fingerprint.REPO_ROOT}"
    assert "--global" not in captured["command"]


def test_fingerprint_route_uses_the_existing_chatbot_blueprint_prefix():
    import chatbot
    # Flask stores blueprint routes as deferred callables, so register it on a tiny
    # app and assert the final public path rather than relying on implementation details.
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(chatbot.chatbot_bp, url_prefix="/chatbot")
    paths = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/chatbot/runtime-fingerprint" in paths
    assert "/chatbot/chatbot/runtime-fingerprint" not in paths


def test_credential_preflight_fails_closed_and_parity_mismatch_fails(monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("verify_tara_release", VERIFY_PATH)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)

    for name in ("OPENAI_KEY", "ANTHROPIC_TOKEN", "TARA_GATEWAY_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="missing required Tara credentials"):
        verifier.credential_preflight()

    monkeypatch.setenv("OPENAI_KEY", "test-openai")
    monkeypatch.setenv("ANTHROPIC_TOKEN", "test-anthropic")
    monkeypatch.setenv("TARA_GATEWAY_KEY", "test-gateway")
    monkeypatch.delenv("TARA_OPENAI_CANARY_PERCENT", raising=False)
    verifier.credential_preflight(require_no_legacy_canary=True)

    assert verifier.assert_approved_fingerprint({"fingerprint": "approved"}, "approved")
    with pytest.raises(RuntimeError, match="does not match"):
        verifier.assert_approved_fingerprint({"fingerprint": "different"}, "approved")
