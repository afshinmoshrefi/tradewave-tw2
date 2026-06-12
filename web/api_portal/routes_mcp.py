"""MCP connect page: the MCP endpoint URL + per-client setup. Consumer apps
(ChatGPT, Claude.ai) connect via OAuth - paste the server URL, click Connect,
sign in with your TradeWave account; no API key involved. Dev tools (Claude
Desktop, Cursor) use BYOK - the customer pastes their OWN API key into the
client config; we never send keys to the client here.

The canonical connector URL is the BARE host (no /mcp path; the server also
aliases /mcp, but published copy uses the bare URL).

MCP host is per-env (CLAUDE.md: read the live value, don't hardcode). Override
with TW2_MCP_PUBLIC_HOST; otherwise derive from config.tw2_env
(dev -> mcp-dev, staging -> mcp-stage, prod -> mcp).
"""
import os

import config
from flask import render_template

from .blueprint import bp, require_login, get_current_user, api_tier_name_for, api_entitlements_for
from . import keystore

_MCP_HOST_BY_ENV = {
    "dev": "mcp-dev.trxstat.com",
    "staging": "mcp-stage.trxstat.com",
    "prod": "mcp.trxstat.com",
}


def _mcp_host():
    explicit = (os.environ.get("TW2_MCP_PUBLIC_HOST") or "").strip().rstrip("/")
    if explicit:
        return explicit
    return _MCP_HOST_BY_ENV.get(getattr(config, "tw2_env", "dev"), "mcp-dev.trxstat.com")


@bp.route("/mcp")
@require_login
def mcp_index():
    u = get_current_user()
    mcp_host = _mcp_host()
    mcp_url = "https://%s" % mcp_host

    # Does the user already have a live key? Drives the copy "your key" hint.
    has_key = keystore.count_active_keys(u.id) > 0

    return render_template(
        "api_mcp.html",
        user=u,
        mcp_host=mcp_host,
        mcp_url=mcp_url,
        has_key=has_key,
        tier_name=api_tier_name_for(u),
        tier_label=api_entitlements_for(u)["name"],
    )
