"""Public URL contracts shared by the main site and developer portal."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
PORTAL_URLS = ROOT / "site" / "lib" / "portal_urls.py"
PUBLIC_HOST_KEYS = (
    "TW2_PUBLIC_HOST",
    "TW2_DEVELOPERS_PUBLIC_HOST",
    "TW2_API_PUBLIC_HOST",
    "TW2_MCP_PUBLIC_HOST",
)


def _load_portal_urls(monkeypatch, name, hosts):
    for key, value in zip(PUBLIC_HOST_KEYS, hosts):
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location(f"portal_urls_{name}", PORTAL_URLS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("name", "hosts"),
    (
        (
            "dev",
            (
                "tw2-dev.trxstat.com",
                "developers-dev.trxstat.com",
                "api-dev.trxstat.com",
                "mcp-dev.trxstat.com",
            ),
        ),
        (
            "staging",
            (
                "tw2-stage.trxstat.com",
                "developers-stage.trxstat.com",
                "api-stage.trxstat.com",
                "mcp-stage.trxstat.com",
            ),
        ),
        (
            "prod",
            (
                "tradewave.ai",
                "developers.tradewave.ai",
                "api.tradewave.ai",
                "mcp.tradewave.ai",
            ),
        ),
    ),
)
def test_public_url_matrix_and_footer_targets(monkeypatch, name, hosts):
    urls = _load_portal_urls(monkeypatch, name, hosts)
    main, developers, api, mcp = hosts

    assert urls.MAIN_URL == f"https://{main}"
    assert urls.PORTAL_URL == f"https://{developers}"
    assert urls.DOCS_HOME_URL == f"https://{developers}/docs/"
    assert urls.LEARN_HOME_URL == f"https://{developers}/learn/"
    assert urls.PLAYGROUND_URL == f"https://{developers}/playground/"
    assert urls.MCP_SETUP_URL == f"https://{developers}/mcp"
    assert urls.MCP_REFERENCE_URL == f"https://{developers}/docs/mcp-reference.html"
    assert urls.MCP_CONNECT_GUIDE_URL == f"https://{developers}/learn/connect-an-ai-agent-mcp.html"
    assert urls.API_BASE == f"https://{api}/v1"
    assert urls.MCP_URL == f"https://{mcp}"
    assert urls.DEVELOPER_FOOTER_LINKS == (
        ("Developer Portal", f"https://{developers}"),
        ("API Docs", f"https://{developers}/docs/quickstart.html"),
        ("MCP for ChatGPT & Claude", f"https://{developers}/mcp"),
    )


def test_non_dev_portal_host_is_required(monkeypatch):
    with pytest.raises(RuntimeError, match="TW2_DEVELOPERS_PUBLIC_HOST is not set"):
        _load_portal_urls(
            monkeypatch,
            "missing_developer_host",
            ("tradewave.ai", "", "api.tradewave.ai", "mcp.tradewave.ai"),
        )


def test_explicit_prod_environment_cannot_fall_back_to_dev_hosts(monkeypatch):
    monkeypatch.setenv("TW2_ENV", "prod")
    for key in PUBLIC_HOST_KEYS:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="TW2_PUBLIC_HOST is not set"):
        _load_portal_urls(
            monkeypatch,
            "prod_without_hosts",
            ("", "", "", ""),
        )


def test_home_footer_uses_distinct_real_destinations():
    generator = (ROOT / "site" / "generate_home_page.py").read_text(encoding="utf-8")
    template = (ROOT / "site" / "templates" / "index-dark-blue.html").read_text(
        encoding="utf-8"
    )
    developer_column = template[
        template.index("<h4>Developers</h4>") : template.index(
            "<h4>Legal</h4>"
        )
    ]

    assert "DEVELOPER_FOOTER_LINKS = portal_urls.DEVELOPER_FOOTER_LINKS" in generator
    assert '"developer_footer_links": DEVELOPER_FOOTER_LINKS' in generator
    assert "content.developer_footer_links" in developer_column
    assert "content.developers_url" not in developer_column
    assert "SDKs" not in developer_column
    assert 'href="/insights/"' in template
    assert "Python and TypeScript SDKs" not in template


def test_rendered_marketing_pages_use_clean_mcp_url(monkeypatch):
    hosts = (
        "tw2-dev.trxstat.com",
        "developers-dev.trxstat.com",
        "api-dev.trxstat.com",
        "mcp-dev.trxstat.com",
    )
    for key, value in zip(PUBLIC_HOST_KEYS, hosts):
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TW2_ENV", "dev")
    monkeypatch.delitem(sys.modules, "portal_urls", raising=False)
    monkeypatch.delitem(sys.modules, "portal_seo", raising=False)

    generator_path = ROOT / "site" / "api_marketing" / "generate.py"
    spec = importlib.util.spec_from_file_location("api_marketing_url_test", generator_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    rendered = module.build_index() + module.build_use_cases()
    assert 'href="https://developers-dev.trxstat.com/mcp"' in rendered
    assert 'href="mcp.html"' not in rendered

    mcp_page = module.build_mcp()
    assert "Sign in on the TradeWave page" in mcp_page
    assert "no API key" not in mcp_page
    assert "do not need an API key" not in mcp_page
    assert "No credential" not in mcp_page
    assert "Developer option: connect with a TradeWave API key" not in mcp_page
    assert "https://developers-dev.trxstat.com/learn/connect-an-ai-agent-mcp.html" in mcp_page
    assert "Open the step-by-step setup guide" in mcp_page
    assert '>Open the Setup Guide</a>' in mcp_page
    assert "Get API Key" not in mcp_page
    assert '>Connect TradeWave</a>' in mcp_page
    assert 'data-preserve-cta="true"' in mcp_page
    assert "Connect TradeWave in three steps" in mcp_page
    assert "For data buyers and institutions" not in mcp_page
    assert "placeable order ticket" not in mcp_page
    assert "Build me a Q3 seasonal portfolio" not in mcp_page
    assert "Claude - Strategist plan" not in mcp_page
    assert "Claude - Pro plan" not in mcp_page
    assert "Claude - Free plan" not in mcp_page
    assert "tw_demo_explore" not in mcp_page


def test_mcp_tool_docs_describe_oauth_before_byok():
    docs = (ROOT / "api" / "MCP_TOOLS.md").read_text(encoding="utf-8")

    assert "TradeWave account authorization (recommended for ChatGPT and Claude)" in docs
    assert "does **not** create, copy, or paste an API key" in docs
    assert "Bring your own API key (developer alternative)" in docs
    assert "BYOK for v1" not in docs
    assert "quota depends on authentication path" in docs
    assert "metered daily: free 5/day" not in docs


def test_mcp_learning_guide_is_login_first(monkeypatch):
    hosts = (
        "tw2-dev.trxstat.com",
        "developers-dev.trxstat.com",
        "api-dev.trxstat.com",
        "mcp-dev.trxstat.com",
    )
    for key, value in zip(PUBLIC_HOST_KEYS, hosts):
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TW2_ENV", "dev")
    monkeypatch.setenv("TW2_MCP_LIVE", "1")
    for module_name in ("portal_urls", "portal_seo", "generate_api_docs"):
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    generator_path = ROOT / "site" / "api_learn" / "generate_learn_api.py"
    spec = importlib.util.spec_from_file_location("mcp_learning_auth_test", generator_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    articles = module.load_articles()
    index = next(i for i, article in enumerate(articles)
                 if article["slug"] == "connect-an-ai-agent-mcp")
    article = articles[index]
    rendered = module.build_article(
        article,
        articles[index - 1] if index else None,
        articles[index + 1] if index + 1 < len(articles) else None,
        articles,
    )

    assert 'data-preserve-cta="true">Connect TradeWave</a>' in rendered
    assert ">Get API Key</a>" not in rendered
    assert "Developer API Key (optional)" not in rendered
    assert "Connect TradeWave" in rendered
    assert "Settings → Security and login" in rendered
    assert "Customize → Connectors" in rendered
    assert "Confirm the connection" in rendered
    assert "For data buyers and institutions" not in rendered
    assert "has not launched" not in rendered
    assert "activates at launch" not in rendered
    assert "<strong>Preview.</strong>" not in rendered


def test_footer_hosts_are_gated_on_both_deployment_tiers():
    deploy = (ROOT / "ops" / "deploy.sh").read_text(encoding="utf-8")
    secrets = (ROOT / "ops" / "staging" / "make_staging_secrets.sh").read_text(
        encoding="utf-8"
    )
    prod_target = (ROOT / "ops" / "staging" / "prod_target.env").read_text(
        encoding="utf-8"
    )

    assert 'for box in "$WEB" "$APP"; do' in deploy
    for key in (
        "TW2_API_PUBLIC_HOST",
        "TW2_DEVELOPERS_PUBLIC_HOST",
        "TW2_MCP_PUBLIC_HOST",
    ):
        assert f'check_portal_host "$box" {key}' in deploy
    assert "MCP launch state is live on both publishing tiers" in deploy
    assert "TW2_MCP_LIVE is not enabled on $box" in deploy
    assert "grep -Eiq '^TW2_MCP_LIVE=(1|true|yes)$'" in deploy
    assert "WorkOS MCP issuer matches the web client and supports registration" in deploy
    assert "actual_workos_issuer" in deploy
    assert '"registration_endpoint"' in deploy
    assert '"client_id_metadata_document_supported"' in deploy
    assert "TW2_MCP_LIVE=1" in secrets
    assert "WEB_DST=/tmp/staging_web_secrets.env" in secrets
    assert '@${TGT_APP_VLAN}:5432/tradewave' in secrets
    assert 'APP $DST -> ${TGT_APP_PUB}:${TGT_SSH_PORT}' in secrets
    assert 'WEB $WEB_DST -> ${TGT_WEB_PUB}:${TGT_SSH_PORT}' in secrets
    assert "Copy the same per-env file" not in secrets
    assert 'TGT_WEB_HOST="${TGT_WEB_HOST:-tradewave.ai}"' in prod_target


def test_release_gate_checks_footer_and_mcp_routes():
    verify = (ROOT / "ops" / "verify_deploy.sh").read_text(encoding="utf-8")

    for route in ("/docs/", "/learn/", "/playground/", "/mcp"):
        assert f"wc_app {route} \"$DEVHOST\"" in verify
    assert '"https://$DEVHOST/docs/quickstart.html"' in verify
    assert '"https://$DEVHOST/mcp"' in verify
    assert 'wc_app / "$MCPHOST"' in verify
    assert "wc_app /learn/connect-an-ai-agent-mcp.html" in verify
    assert "portal MCP setup guide is launch-ready" in verify
    assert "has not launched|activates at launch" in verify
    assert "mcp discovery advertises the configured WorkOS issuer" in verify
    assert "WorkOS issuer publishes Dynamic Client Registration" in verify
    assert "WorkOS issuer publishes CIMD support" in verify
    assert '[ "$mcp_redirect_code" = 308 ]' in verify
    assert '[ "$mcp_redirect_location" = "Location: /mcp" ]' in verify
    assert "portal /mcp/ -> relative /mcp redirect" in verify


def test_sitemap_uses_clean_mcp_setup_url():
    generator = (ROOT / "site" / "api_docs" / "generate_seo_files.py").read_text(
        encoding="utf-8"
    )

    assert 'name == "mcp.html"' in generator
    assert "loc = portal_urls.MCP_SETUP_URL" in generator
