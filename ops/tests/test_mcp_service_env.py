"""Least-privilege MCP runtime environment and service-key release gates."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load():
    path = ROOT / "ops" / "mcp_service_env.py"
    spec = importlib.util.spec_from_file_location("mcp_service_env_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _source() -> str:
    return "\n".join(
        (
            "POSTGRES_DSN='must-not-leak'",
            "STRIPE_SECRET_KEY='must-not-leak'",
            "TRADEWAVE_API_KEY='must-not-leak'",
            "WORKOS_AUTHKIT_DOMAIN='https://example.authkit.app/'",
            "TW2_MCP_PUBLIC_URL=https://mcp-dev.trxstat.com/",
            "",
        )
    )


def _render(module, source: Path, output: Path, key: str = "tw_svc_" + "A" * 43):
    module.read_dedicated_runtime = lambda _path: {"MCP_GATEWAY_KEY": key}
    module.render(
        str(source), "/etc/tradewave/mcpserver.env", str(output),
        "mcp-dev.trxstat.com",
    )


def test_render_has_exact_runtime_allowlist_and_never_copies_platform_secrets(tmp_path):
    module = _load()
    source = tmp_path / "secrets.env"
    output = tmp_path / "mcpserver.env"
    source.write_text(_source(), encoding="utf-8")
    _render(module, source, output)

    values = module.validate(str(output))
    assert tuple(values) == module.RUNTIME_KEYS
    assert values["TW2_MCP_PUBLIC_URL"] == "https://mcp-dev.trxstat.com"
    assert values["TW2_MCP_PUBLIC_HOST"] == "mcp-dev.trxstat.com"
    assert not ({"POSTGRES_DSN", "STRIPE_SECRET_KEY", "TRADEWAVE_API_KEY"} & values.keys())
    assert output.stat().st_mode & 0o777 == 0o600


def test_render_requires_provisioner_to_create_the_dedicated_environment(tmp_path):
    module = _load()
    with pytest.raises(module.ConfigError, match="cannot read dedicated MCP environment"):
        module.read_dedicated_runtime(tmp_path / "absent-mcpserver.env")


def test_render_rejects_broad_key_overwrite_after_k1_provision(tmp_path):
    module = _load()
    source = tmp_path / "secrets.env"
    output = tmp_path / "mcpserver.env.candidate"
    source.write_text(
        _source() + "MCP_GATEWAY_KEY=tw_svc_" + "B" * 43 + "\n",
        encoding="utf-8",
    )
    module.read_dedicated_runtime = lambda _path: {
        "MCP_GATEWAY_KEY": "tw_svc_" + "A" * 43
    }
    with pytest.raises(module.ConfigError, match="forbidden in the platform secrets"):
        module.render(
            str(source), "/etc/tradewave/mcpserver.env", str(output),
            "mcp-dev.trxstat.com",
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "suffix, message",
    (
        ("\nTW2_MCP_PUBLIC_URL=https://evil.example", "duplicate assignment"),
    ),
)
def test_render_rejects_duplicate_security_assignments(tmp_path, suffix, message):
    module = _load()
    source = tmp_path / "secrets.env"
    source.write_text(_source() + suffix + "\n", encoding="utf-8")
    with pytest.raises(module.ConfigError, match=message):
        _render(module, source, tmp_path / "out")


def test_render_rejects_an_ordinary_customer_key(tmp_path):
    module = _load()
    source = tmp_path / "secrets.env"
    source.write_text(_source(), encoding="utf-8")
    with pytest.raises(module.ConfigError, match="service-key token"):
        _render(module, source, tmp_path / "out", "tw_ordinary_customer_key")


@pytest.mark.parametrize("length", [42, 44])
def test_render_rejects_noncanonical_service_key_lengths(tmp_path, length):
    module = _load()
    source = tmp_path / "secrets.env"
    source.write_text(_source(), encoding="utf-8")
    with pytest.raises(module.ConfigError, match="service-key token"):
        _render(module, source, tmp_path / "out", "tw_svc_" + "A" * length)


def test_validate_rejects_any_extra_runtime_key(tmp_path):
    module = _load()
    source = tmp_path / "secrets.env"
    output = tmp_path / "mcpserver.env"
    source.write_text(_source(), encoding="utf-8")
    _render(module, source, output)
    output.write_text(output.read_text() + "POSTGRES_DSN=forbidden\n", encoding="utf-8")
    with pytest.raises(module.ConfigError, match="not allowed"):
        module.validate(str(output))


def test_gateway_gate_requires_service_semantics_and_known_user(tmp_path, monkeypatch):
    module = _load()
    source = tmp_path / "secrets.env"
    output = tmp_path / "mcpserver.env"
    source.write_text(
        _source()
        + "TW_MCP_SMOKE_WORKOS_SUB=user_test_smoke\n"
        + "TW_MCP_SMOKE_EXPECT_TIER=strategist\n",
        encoding="utf-8",
    )
    _render(module, source, output)
    seen = []

    def fake_get(url, key, principal):
        seen.append(principal)
        if principal is None:
            return 401, {"error": {"code": "unauthorized", "message": "missing principal"}}
        if principal == "user_test_smoke":
            return 200, {"tier": "strategist"}
        return 401, {"error": {"code": "unauthorized", "message": "unknown user"}}

    monkeypatch.setattr(module, "_gateway_get", fake_get)
    assert module.check_gateway_key(str(output), str(source)) is True
    assert seen[0] is None and seen[-1] == "user_test_smoke"


def test_gateway_gate_fails_closed_without_known_smoke_principal(tmp_path, monkeypatch):
    module = _load()
    source = tmp_path / "secrets.env"
    output = tmp_path / "mcpserver.env"
    source.write_text(_source(), encoding="utf-8")
    _render(module, source, output)

    def classified(url, key, principal):
        message = "missing principal" if principal is None else "unknown user"
        return 401, {"error": {"code": "unauthorized", "message": message}}

    monkeypatch.setattr(module, "_gateway_get", classified)
    with pytest.raises(module.ConfigError, match="release-required"):
        module.check_gateway_key(str(output), str(source))


def test_process_gate_rejects_broad_secret_inheritance(tmp_path, monkeypatch):
    module = _load()
    source = tmp_path / "secrets.env"
    output = tmp_path / "mcpserver.env"
    source.write_text(_source(), encoding="utf-8")
    _render(module, source, output)
    runtime = module.validate(str(output))
    environ = b"\0".join(f"{key}={value}".encode() for key, value in runtime.items())
    environ += b"\0POSTGRES_DSN=must-not-leak\0"
    original = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: environ if str(self).endswith("/environ") else original(self),
    )
    with pytest.raises(module.ConfigError, match="POSTGRES_DSN"):
        module.check_process_env(str(output), os.getpid())


def test_platform_secrets_reject_embedded_verifier_token(tmp_path):
    module = _load()
    source = tmp_path / "secrets.env"
    source.write_text(
        _source() + "TW_MCP_VERIFY_TOKEN=tw_live_" + "a" * 32 + "\n",
        encoding="utf-8",
    )
    with pytest.raises(module.ConfigError, match="must not be stored"):
        _render(module, source, tmp_path / "out")


def test_dedicated_verifier_parser_has_one_exact_regular_key_only():
    module = _load()
    valid = "tw_live_" + "a" * 32
    assert module._parse_verifier_env(
        f"# root only\nTW_MCP_VERIFY_TOKEN={valid}\n".encode(), Path("/root/verifier")
    ) == valid
    for raw, match in (
        (f"TW_MCP_VERIFY_TOKEN={valid}\n" * 2, "exactly one"),
        ("TW_MCP_VERIFY_TOKEN=tw_demo_explore\n", "regular tw_live_"),
        (f"TW_MCP_VERIFY_TOKEN={valid}\nPOSTGRES_DSN=x\n", "may contain only"),
        ("", "exactly one"),
    ):
        with pytest.raises(module.ConfigError, match=match):
            module._parse_verifier_env(raw.encode(), Path("/root/verifier"))


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"tier": "demo", "tier_name": "Demo", "rate": {"per_minute": 120, "per_day": 5000}},
        {"tier": "free", "tier_name": "Free", "rate": {"per_minute": 120, "per_day": 5000}},
        {"tier": "dev", "tier_name": "Dev", "rate": {"per_minute": 120, "per_day": 5000}},
        {"tier": "mcp", "tier_name": "MCP", "rate": {"per_minute": 120, "per_day": 5000}},
        {"tier": "pro", "tier_name": "Pro", "rate": {"per_minute": 119, "per_day": 5000}},
        {"tier": "pro", "tier_name": "Pro", "rate": {"per_minute": 120, "per_day": 4999}},
    ],
)
def test_verifier_preflight_rejects_substitution_and_under_capacity(monkeypatch, body):
    module = _load()
    monkeypatch.setattr(
        module,
        "validate",
        lambda _path: {"API_BASE_URL": "http://127.0.0.1:8088/v1"},
    )
    monkeypatch.setattr(module, "read_verifier_env", lambda _path: "tw_live_" + "a" * 32)
    monkeypatch.setattr(module, "_gateway_get", lambda *_args: (200, body))
    with pytest.raises(module.ConfigError, match="dedicated ordinary Pro"):
        module.check_verifier_key("runtime", "verifier")


def test_verifier_preflight_accepts_exact_live_capacity(monkeypatch):
    module = _load()
    monkeypatch.setattr(
        module,
        "validate",
        lambda _path: {"API_BASE_URL": "http://127.0.0.1:8088/v1"},
    )
    monkeypatch.setattr(module, "read_verifier_env", lambda _path: "tw_live_" + "a" * 32)
    monkeypatch.setattr(
        module,
        "_gateway_get",
        lambda *_args: (
            200,
            {
                "tier": "pro",
                "tier_name": "Pro",
                "rate": {"per_minute": 120, "per_day": 5000},
            },
        ),
    )
    assert module.check_verifier_key("runtime", "verifier") is True


def test_exec_with_verifier_injects_env_without_argv_or_stdout(monkeypatch, capsys):
    module = _load()
    raw = "tw_live_" + "c" * 32
    observed = {}
    monkeypatch.setattr(module, "read_verifier_env", lambda _path: raw)
    monkeypatch.setenv("UNRELATED_CALLER_SECRET", "must-not-reach-child")
    monkeypatch.setenv("TW_MCP_EXPECT_AUTHORIZATION_SERVER", "https://auth.example")
    for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    ):
        monkeypatch.setenv(name, "hostile-inherited-value")

    def capture(program, argv, environment):
        observed.update(program=program, argv=argv, environment=environment)

    monkeypatch.setattr(module.os, "execvpe", capture)
    module.exec_with_verifier("/root/verifier", ["--", "/bin/probe", "--url", "https://mcp"])
    assert observed["program"] == "/bin/probe"
    assert raw not in observed["argv"]
    assert observed["environment"]["TW_MCP_VERIFY_TOKEN"] == raw
    assert "UNRELATED_CALLER_SECRET" not in observed["environment"]
    assert not {
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    } & observed["environment"].keys()
    assert observed["environment"]["TW_MCP_EXPECT_AUTHORIZATION_SERVER"] == "https://auth.example"
    assert raw not in capsys.readouterr().out


def test_exec_with_verifier_rejects_path_resolution(monkeypatch):
    module = _load()
    monkeypatch.setattr(
        module, "read_verifier_env", lambda _path: pytest.fail("token file was read")
    )
    with pytest.raises(module.ConfigError, match="absolute executable"):
        module.exec_with_verifier("/root/verifier", ["python3", "probe.py"])


@pytest.mark.parametrize("payload, message", ((b"not-json", "invalid JSON"), (b"[]", "invalid payload")))
def test_gateway_preflight_sanitizes_malformed_payloads(monkeypatch, payload, message):
    module = _load()

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return payload

    class Opener:
        @staticmethod
        def open(_request, timeout):
            return Response()

    monkeypatch.setattr(module.urllib.request, "build_opener", lambda *_args: Opener())
    with pytest.raises(module.ConfigError, match=message):
        module._gateway_get("http://127.0.0.1:8088/v1/me", "secret", None)


def test_gateway_preflight_installs_an_explicit_empty_proxy_handler(monkeypatch):
    module = _load()
    handlers = []

    class Opener:
        @staticmethod
        def open(_request, timeout):
            raise OSError("expected stop")

    def capture(*items):
        handlers.extend(items)
        return Opener()

    monkeypatch.setattr(module.urllib.request, "build_opener", capture)
    with pytest.raises(module.ConfigError, match="could not connect"):
        module._gateway_get("http://127.0.0.1:8088/v1/me", "secret", None)
    proxy_handlers = [
        item for item in handlers if isinstance(item, module.urllib.request.ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}


def test_gateway_preflight_rejects_oversized_payload_without_echo(monkeypatch):
    module = _load()
    payload = b"x" * 1_048_577

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return payload

    class Opener:
        @staticmethod
        def open(_request, timeout):
            return Response()

    monkeypatch.setattr(module.urllib.request, "build_opener", lambda *_args: Opener())
    with pytest.raises(module.ConfigError, match="oversized") as error:
        module._gateway_get("http://127.0.0.1:8088/v1/me", "secret", None)
    assert "xxxx" not in str(error.value)


def _api_source() -> str:
    return "\n".join(
        (
            "POSTGRES_DSN=postgresql://gateway",
            "APPSERVER_JWT_SECRET=fallback-hmac",
            "SERVICE_API_KEY=service-key",
            "TW2_APPSERVER_URL=http://127.0.0.1:5000",
            "TW2_PUBLIC_HOST=tw2-dev.trxstat.com",
            "TW2_ENV=dev",
            "TW2_API_PRICING_LIVE=yes",
            "MAILERLITE_API_KEY=",  # unrelated empty values must not block the gateway
            "OPENAI_KEY='$hostile-but-unrelated'",
            "",
        )
    )


def _api_runtime(module):
    return module._normalise_api_runtime(
        {
            "POSTGRES_DSN": "postgresql://gateway",
            "API_KEY_HMAC_SECRET": "hmac",
            "SERVICE_API_KEY": "service",
            "TW2_ENV": "dev",
            "TW2_PUBLIC_HOST": "tw2-dev.trxstat.com",
        },
        source=True,
    )


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() != 0,
    reason="atomic API environment metadata requires POSIX root",
)
def test_api_atomic_publish_replaces_one_safe_target_with_exact_metadata(tmp_path):
    module = _load()
    target = tmp_path / "apiserver.env"
    target.write_bytes(b"old-complete-value\n")
    target.chmod(0o600)
    os.chown(target, 0, 0)

    module._publish_api_runtime(_api_runtime(module), str(target))

    assert module.validate_api(str(target)) == _api_runtime(module)
    metadata = target.stat()
    assert (metadata.st_uid, metadata.st_gid, metadata.st_mode & 0o777, metadata.st_nlink) == (0, 0, 0o600, 1)
    assert not list(tmp_path.glob(".apiserver.env.tmp-*"))


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() != 0,
    reason="atomic API environment metadata requires POSIX root",
)
@pytest.mark.parametrize("seam", ["write", "fsync", "replace"])
def test_api_atomic_publish_failure_never_tears_existing_target(tmp_path, monkeypatch, seam):
    module = _load()
    target = tmp_path / "apiserver.env"
    original = b"old-complete-value\n"
    target.write_bytes(original)
    target.chmod(0o600)
    os.chown(target, 0, 0)

    def fail(*_args, **_kwargs):
        raise OSError(f"injected {seam} failure")

    monkeypatch.setattr(module.os, seam, fail)
    with pytest.raises(module.ConfigError, match="atomically publish"):
        module._publish_api_runtime(_api_runtime(module), str(target))

    assert target.read_bytes() == original
    assert not list(tmp_path.glob(".apiserver.env.tmp-*"))


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() != 0,
    reason="atomic API environment metadata requires POSIX root",
)
@pytest.mark.parametrize("unsafe", ["mode", "symlink", "hardlink"])
def test_api_atomic_publish_rejects_unsafe_preexisting_target(tmp_path, unsafe):
    module = _load()
    target = tmp_path / "apiserver.env"
    if unsafe == "symlink":
        backing = tmp_path / "backing"
        backing.write_bytes(b"attacker\n")
        target.symlink_to(backing)
    else:
        target.write_bytes(b"old\n")
        target.chmod(0o644 if unsafe == "mode" else 0o600)
        os.chown(target, 0, 0)
        if unsafe == "hardlink":
            os.link(target, tmp_path / "second-name")

    with pytest.raises(module.ConfigError, match="metadata is unsafe"):
        module._publish_api_runtime(_api_runtime(module), str(target))
    assert not list(tmp_path.glob(".apiserver.env.tmp-*"))


def test_api_environment_resolves_exact_allowlist_without_unrelated_secrets(tmp_path):
    module = _load()
    source = tmp_path / "secrets.env"
    source.write_text(_api_source(), encoding="utf-8")
    selected = module.read_platform_assignments(source, allowed=module.API_SOURCE_KEYS)
    runtime = module._normalise_api_runtime(selected, source=True)
    assert tuple(runtime) == module.API_RUNTIME_KEYS
    assert runtime["API_KEY_HMAC_SECRET"] == "fallback-hmac"
    assert runtime["TW2_API_PRICING_LIVE"] == "true"
    assert runtime["TW2_DEMO_API_KEY"] == "tw_demo_explore"
    assert not ({"APPSERVER_JWT_SECRET", "OPENAI_KEY", "MAILERLITE_API_KEY"} & runtime.keys())


def test_api_environment_rejects_duplicate_relevant_key_but_ignores_unrelated_syntax(tmp_path):
    module = _load()
    source = tmp_path / "secrets.env"
    source.write_text(_api_source() + "POSTGRES_DSN=duplicate\n", encoding="utf-8")
    with pytest.raises(module.ConfigError, match="duplicate assignment"):
        module.read_platform_assignments(source, allowed=module.API_SOURCE_KEYS)


def test_api_environment_requires_public_host_outside_dev():
    module = _load()
    values = {
        "POSTGRES_DSN": "postgresql://gateway",
        "APPSERVER_JWT_SECRET": "hmac",
        "SERVICE_API_KEY": "service",
        "TW2_ENV": "prod",
    }
    with pytest.raises(module.ConfigError, match="TW2_PUBLIC_HOST is required"):
        module._normalise_api_runtime(values, source=True)


@pytest.mark.parametrize(
    "hostile",
    ("HTTP_PROXY", "PYTHONPATH", "PYTHONHOME", "GUNICORN_CMD_ARGS", "WEB_CONCURRENCY"),
)
def test_api_process_environment_rejects_hostile_inheritance(monkeypatch, hostile):
    module = _load()
    expected = module._normalise_api_runtime(
        {
            "POSTGRES_DSN": "postgresql://gateway",
            "API_KEY_HMAC_SECRET": "hmac",
            "SERVICE_API_KEY": "service",
            "TW2_ENV": "dev",
            "TW2_PUBLIC_HOST": "tw2-dev.trxstat.com",
        },
        source=True,
    )
    monkeypatch.setattr(module, "validate_api", lambda _path: expected)
    environment = dict(expected)
    environment["TW2_FEATURED_HISTORY_FILE"] = "/run/tradewave-gateway/featured_history.json"
    environment[hostile] = "must-not-reach-gunicorn"
    raw = b"\0".join(f"{key}={value}".encode() for key, value in environment.items()) + b"\0"
    original = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: raw if str(self).endswith("/environ") else original(self),
    )
    with pytest.raises(module.ConfigError, match=hostile):
        module.check_api_process_env(
            "/etc/tradewave/apiserver.env",
            os.getpid(),
            "/run/tradewave-gateway/featured_history.json",
        )
