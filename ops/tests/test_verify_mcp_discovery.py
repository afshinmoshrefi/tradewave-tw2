"""Focused fail-closed tests for the public OAuth discovery release gate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "verify_mcp_contract_discovery", ROOT / "ops/verify_mcp_contract.py"
)
verifier = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(verifier)


def _document(resource="https://mcp.example", issuer="https://auth.example"):
    return json.dumps(
        {"resource": resource, "authorization_servers": [issuer]}
    ).encode()


def _metadata(issuer="https://auth.example", **overrides):
    value = {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/oauth2/authorize",
        "token_endpoint": issuer + "/oauth2/token",
        "registration_endpoint": issuer + "/oauth2/register",
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }
    value.update(overrides)
    return json.dumps(value).encode()


AS_METADATA = "https://auth.example/.well-known/oauth-authorization-server"


def test_exact_resource_workos_and_same_origin_canonical_redirect(monkeypatch):
    canonical = "https://mcp.example/.well-known/oauth-protected-resource"
    calls = []

    def request(url, **_kwargs):
        calls.append(url)
        if url == AS_METADATA:
            return 200, {}, _metadata()
        if url == canonical + "/":
            return 308, {"Location": canonical}, b""
        return 200, {}, _document()

    monkeypatch.setattr(verifier, "_request", request)
    verifier.verify_discovery(
        "https://MCP.EXAMPLE/", 1, "https://auth.example/"
    )
    assert calls == [canonical, AS_METADATA, canonical + "/", canonical]


@pytest.mark.parametrize(
    "advertised",
    ["https://other.example", "https://mcp.example/other"],
)
def test_resource_must_equal_configured_mcp_endpoint(monkeypatch, advertised):
    monkeypatch.setattr(
        verifier,
        "_request",
        lambda *_args, **_kwargs: (200, {}, _document(resource=advertised)),
    )
    with pytest.raises(verifier.ProbeError, match="does not match"):
        verifier.verify_discovery(
            "https://mcp.example/", 1, "https://auth.example"
        )


def test_authorization_server_must_equal_configured_workos(monkeypatch):
    monkeypatch.setattr(
        verifier,
        "_request",
        lambda *_args, **_kwargs: (
            200,
            {},
            _document(issuer="https://attacker.example"),
        ),
    )
    with pytest.raises(verifier.ProbeError, match="configured WorkOS"):
        verifier.verify_discovery(
            "https://mcp.example", 1, "https://auth.example"
        )


@pytest.mark.parametrize(
    "location",
    [
        "https://attacker.example/.well-known/oauth-protected-resource",
        "https://mcp.example/wrong",
        "http://mcp.example/.well-known/oauth-protected-resource",
    ],
)
def test_trailing_slash_redirect_cannot_escape_canonical_endpoint(
    monkeypatch, location
):
    canonical = "https://mcp.example/.well-known/oauth-protected-resource"

    def request(url, **_kwargs):
        if url == AS_METADATA:
            return 200, {}, _metadata()
        if url == canonical:
            return 200, {}, _document()
        return 308, {"Location": location}, b""

    monkeypatch.setattr(verifier, "_request", request)
    with pytest.raises(verifier.ProbeError):
        verifier.verify_discovery(
            "https://mcp.example", 1, "https://auth.example"
        )


def test_trailing_slash_200_document_is_revalidated(monkeypatch):
    canonical = "https://mcp.example/.well-known/oauth-protected-resource"

    def request(url, **_kwargs):
        if url == AS_METADATA:
            return 200, {}, _metadata()
        if url == canonical:
            return 200, {}, _document()
        return 200, {}, _document(resource="https://attacker.example")

    monkeypatch.setattr(verifier, "_request", request)
    with pytest.raises(verifier.ProbeError, match="does not match"):
        verifier.verify_discovery(
            "https://mcp.example", 1, "https://auth.example"
        )


def test_path_resource_uses_rfc_well_known_path_semantics(monkeypatch):
    canonical = "https://mcp.example/.well-known/oauth-protected-resource/mcp"
    calls = []

    def request(url, **_kwargs):
        calls.append(url)
        if url == AS_METADATA:
            return 200, {}, _metadata()
        if url == canonical + "/":
            return 308, {"Location": canonical}, b""
        return 200, {}, _document(resource="https://mcp.example/mcp/")

    monkeypatch.setattr(verifier, "_request", request)
    verifier.verify_discovery(
        "https://mcp.example/mcp", 1, "https://auth.example"
    )
    assert calls[0] == canonical


@pytest.mark.parametrize(
    "override, match",
    [
        ({"scopes_supported": ["openid"]}, "offline_access"),
        ({"grant_types_supported": ["authorization_code"]}, "refresh_token"),
        ({"code_challenge_methods_supported": ["plain"]}, "S256"),
        ({"token_endpoint_auth_methods_supported": ["client_secret_basic"]}, "none"),
        ({"registration_endpoint": None}, "neither dynamic registration"),
        ({"issuer": "https://attacker.example"}, "issuer mismatch"),
    ],
)
def test_authorization_server_metadata_is_release_blocking(override, match):
    with pytest.raises(verifier.ProbeError, match=match):
        verifier._validate_authorization_server_metadata(_metadata(**override), "https://auth.example")


def test_authorization_server_metadata_accepts_cimd_instead_of_dcr():
    verifier._validate_authorization_server_metadata(
        _metadata(
            registration_endpoint=None,
            client_id_metadata_document_supported=True,
        ),
        "https://auth.example",
    )


def test_main_honors_configured_workos_env(monkeypatch):
    observed = {}

    def discovery(_url, _timeout, expected_authorization_server=None):
        observed["issuer"] = expected_authorization_server

    monkeypatch.setenv(
        "TW_MCP_EXPECT_AUTHORIZATION_SERVER", "https://auth.example"
    )
    monkeypatch.setenv("TW_MCP_VERIFY_TOKEN", "tw_live_" + "a" * 32)
    monkeypatch.setattr(verifier, "verify_discovery", discovery)
    monkeypatch.setattr(verifier, "verify_mcp", lambda *_args, **_kwargs: None)
    assert verifier.main(["--url", "https://mcp.example/"]) == 0
    assert observed["issuer"] == "https://auth.example"


def test_exact_bearer_challenge_is_required():
    verifier.validate_unauthenticated_challenge(
        "https://mcp.example/",
        401,
        {
            "WWW-Authenticate": (
                'Bearer error="invalid_token", '
                'error_description="Authentication required", '
                'resource_metadata="https://mcp.example/.well-known/oauth-protected-resource"'
            )
        },
        b"",
    )


@pytest.mark.parametrize(
    "challenge, match",
    (
        (
            'Basic error="invalid_token", error_description="Authentication required", '
            'resource_metadata="https://mcp.example/.well-known/oauth-protected-resource"',
            "scheme must be Bearer",
        ),
        (
            'Bearer error_description="Authentication required", '
            'resource_metadata="https://mcp.example/.well-known/oauth-protected-resource"',
            "error=invalid_token",
        ),
        (
            'Bearer error="invalid_token", error_description="", '
            'resource_metadata="https://mcp.example/.well-known/oauth-protected-resource"',
            "nonempty error_description",
        ),
        (
            'Bearer error="invalid_token", error_description="Authentication required", '
            'resource_metadata="https://attacker.example/.well-known/oauth-protected-resource"',
            "does not identify",
        ),
    ),
)
def test_inexact_auth_challenge_is_release_blocking(challenge, match):
    with pytest.raises(verifier.ProbeError, match=match):
        verifier.validate_unauthenticated_challenge(
            "https://mcp.example/", 401, {"WWW-Authenticate": challenge}, b""
        )


def test_unauthenticated_only_never_loads_a_bearer(monkeypatch):
    monkeypatch.delenv("TW_MCP_VERIFY_TOKEN", raising=False)
    monkeypatch.setattr(verifier, "verify_discovery", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        verifier, "verify_unauthenticated_challenge", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        verifier,
        "load_verifier_token",
        lambda: pytest.fail("postcommit no-bearer mode loaded a credential"),
    )
    assert verifier.main(["--url", "https://mcp.example/", "--unauthenticated-only"]) == 0


def test_contract_request_uses_identity_encoding_and_bounded_read(monkeypatch):
    observed = {}

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit):
            observed["limit"] = limit
            return b"x" * limit

    class Opener:
        @staticmethod
        def open(request, timeout):
            observed["encoding"] = request.get_header("Accept-encoding")
            return Response()

    monkeypatch.setattr(verifier, "_OPENER", Opener())
    with pytest.raises(verifier.ProbeError, match="exceeded"):
        verifier._request("https://mcp.example/", timeout=1)
    assert observed == {
        "encoding": "identity",
        "limit": verifier._MAX_RESPONSE_BYTES + 1,
    }


def test_main_rejects_demo_and_customer_fallbacks_before_discovery(monkeypatch):
    monkeypatch.delenv("TW_MCP_VERIFY_TOKEN", raising=False)
    monkeypatch.setenv("TRADEWAVE_API_KEY", "tw_live_" + "a" * 32)
    monkeypatch.setenv("TW2_DEMO_API_KEY", "tw_demo_explore")
    monkeypatch.setattr(
        verifier,
        "verify_discovery",
        lambda *_args, **_kwargs: pytest.fail("discovery ran without dedicated verifier"),
    )
    assert verifier.main(["--url", "https://mcp.example/"]) == 2


def test_main_reads_systemd_credential_without_token_environment(tmp_path, monkeypatch):
    credential_dir = tmp_path / "credentials"
    credential_dir.mkdir()
    (credential_dir / "verify-env").write_text(
        "# systemd credential\nTW_MCP_VERIFY_TOKEN=tw_live_" + "b" * 32 + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credential_dir.resolve()))
    monkeypatch.delenv("TW_MCP_VERIFY_TOKEN", raising=False)
    monkeypatch.setattr(verifier, "verify_discovery", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(verifier, "verify_mcp", lambda *_args, **_kwargs: None)
    assert verifier.main(["--url", "https://mcp.example/"]) == 0


@pytest.mark.parametrize(
    "body",
    [
        "TW_MCP_VERIFY_TOKEN=tw_live_" + "a" * 32 + "\nPOSTGRES_DSN=secret\n",
        ("TW_MCP_VERIFY_TOKEN=tw_live_" + "a" * 32 + "\n") * 2,
        "export TW_MCP_VERIFY_TOKEN=tw_live_" + "a" * 32 + "\n",
    ],
)
def test_systemd_credential_parser_fails_closed(tmp_path, monkeypatch, body):
    credential_dir = tmp_path / "credentials"
    credential_dir.mkdir()
    (credential_dir / "verify-env").write_text(body, encoding="utf-8")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credential_dir.resolve()))
    monkeypatch.delenv("TW_MCP_VERIFY_TOKEN", raising=False)
    assert verifier.main(["--url", "https://mcp.example/"]) == 2


def test_systemd_credential_rejects_ambiguous_environment_token(tmp_path, monkeypatch):
    credential_dir = tmp_path / "credentials"
    credential_dir.mkdir()
    (credential_dir / "verify-env").write_text(
        "TW_MCP_VERIFY_TOKEN=tw_live_" + "a" * 32 + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credential_dir.resolve()))
    monkeypatch.setenv("TW_MCP_VERIFY_TOKEN", "tw_live_" + "b" * 32)
    assert verifier.main(["--url", "https://mcp.example/"]) == 2
