"""Deployment contracts for the generated developer portal."""

from pathlib import Path
import re

import pytest


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
ASSEMBLER = ROOT / "ops" / "assemble_developer_portal.sh"
INSTALLER = ROOT / "ops" / "install_developer_portal_nginx.sh"
NGINX_TEMPLATE = ROOT / "ops" / "nginx" / "tradewave-developer-portal.conf"


def test_portal_generators_run_as_repo_owner_not_root():
    script = ASSEMBLER.read_text(encoding="utf-8")

    assert "GENERATOR_USER=flask" in script
    assert 'chown -R "$GENERATOR_USER:$GENERATOR_USER" "$path"' in script
    assert "sudo \\" in script
    assert "--preserve-env=" in script
    assert '-u "$GENERATOR_USER" -- "$PY" "$script"' in script
    assert script.index('chown -R "$GENERATOR_USER:$GENERATOR_USER"') < script.index(
        "run_gen api_marketing/generate.py"
    )


def test_nginx_renderer_checks_real_placeholders_not_comment_wildcard():
    installer = INSTALLER.read_text(encoding="utf-8")
    template = NGINX_TEMPLATE.read_text(encoding="utf-8")
    placeholders = set(re.findall(r"__TW2_[A-Z0-9_]+__", template))

    assert placeholders == {
        "__TW2_DEVELOPER_PORT__",
        "__TW2_API_PUBLIC_HOST__",
        "__TW2_MCP_PUBLIC_HOST__",
        "__TW2_DEVELOPERS_PUBLIC_HOST__",
    }
    assert "grep -Eq '__TW2_[A-Z0-9_]+__'" in installer
    assert "grep -q '__TW2_'" not in installer
    assert all(placeholder in installer for placeholder in placeholders)


def test_mcp_setup_trailing_slash_redirects_to_clean_url():
    template = NGINX_TEMPLATE.read_text(encoding="utf-8")

    assert "absolute_redirect off;" in template
    assert "location = /mcp/" in template
    assert "return 308 /mcp;" in template


def test_mcp_endpoint_has_path_aware_oauth_discovery():
    template = NGINX_TEMPLATE.read_text(encoding="utf-8")

    assert "location = /.well-known/oauth-protected-resource/mcp" in template
    assert (
        "proxy_pass http://tw2_mcpserver/.well-known/oauth-protected-resource;"
        in template
    )


def test_playground_policy_extends_only_developer_vhost():
    template = NGINX_TEMPLATE.read_text(encoding='utf-8')
    installer = INSTALLER.read_text(encoding='utf-8')
    portal = template.split('server_name __TW2_DEVELOPERS_PUBLIC_HOST__;')[1]
    assert 'include /etc/nginx/snippets/developer_security_headers.conf;' in portal
    assert 'include /etc/nginx/snippets/security_headers.conf;' not in portal
    assert "connect-src 'self' https://$TW2_API_PUBLIC_HOST" in installer
    assert '/etc/nginx/snippets/developer_security_headers.conf' in installer
    shared = (ROOT / 'ops/nginx/snippets/security_headers.conf').read_text(encoding='utf-8')
    assert 'api-dev.trxstat.com' not in shared
    assert "object-src 'none'" in shared and "frame-ancestors 'self'" in shared
