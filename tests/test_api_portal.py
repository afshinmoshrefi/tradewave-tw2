"""
Regression net for the API customer console (/account/api).

The gateway publishes https://<host>/account/api as `upgrade_url` in every
customer-visible quota/scope nudge (apiserver/routes.py _UPGRADE_URL), so the
console is the API funnel's landing strip. These tests keep it from ever
shipping dark silently again. They cover the 2026-06-12 repairs:

  1. routes_usage.py was missing `from flask import render_template`
     (NameError = 500 for every logged-in Usage view).
  2. The blueprint had no index route - the published upgrade_url
     (/account/api, no tab) 404'd even with the console enabled. It now
     redirects to the billing tab (the plans + upgrade page the nudges sell).
  3. Flag-off: without TW2_API_CONSOLE_ENABLED the console must NOT register
     (404 everywhere) - the ships-dark-on-prod invariant.

Auth mock: the console resolves its user through an injected loader
(api_portal.blueprint.set_user_loader - the exact hook web/app.py wires at
boot). Logged-in tests inject a loader returning a real User row in
tradewave_test; anonymous tests rely on the app's own cookie-less loader
returning None (no network involved without a session cookie).
"""
from __future__ import annotations

import os

# MUST happen at import (= pytest collection) time, before any test runs and
# therefore before config.py is first imported anywhere in this process:
# config.API_CONSOLE_ENABLED is computed from this env var at config import,
# and web/app.py registers the blueprint at ITS import based on that value.
os.environ["TW2_API_CONSOLE_ENABLED"] = "1"

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_SQL = _REPO_ROOT / "apiserver" / "schema.sql"

# Every console tab the blueprint serves (path -> substring expected in the
# rendered page). The index ("" and "/") is asserted separately as a redirect.
_TABS = {
    "/account/api/keys": b"API Keys",
    "/account/api/usage": b"Usage",
    "/account/api/billing": b"Billing",
    "/account/api/mcp": b"MCP",
}


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def app_module():
    """Lazy import (same pattern as test_web_funnel_fixes) + a loud guard:
    if config was somehow imported before this module set the flag, the
    blueprint never registered and every test below would 404 mysteriously."""
    import config
    if not config.API_CONSOLE_ENABLED:
        pytest.fail(
            "config.API_CONSOLE_ENABLED is False - config.py was imported "
            "before tests/test_api_portal.py set TW2_API_CONSOLE_ENABLED "
            "(collection-order regression; fix the import order)."
        )
    m = importlib.import_module("app")
    assert "api_portal" in m.app.blueprints, (
        "API console blueprint not registered despite TW2_API_CONSOLE_ENABLED=1"
    )
    return m


@pytest.fixture
def client(app_module, _models_module):
    app_module.DBSession = _models_module.Session
    app_module.app.config["TESTING"] = True  # exceptions propagate, not 500
    return app_module.app.test_client()


@pytest.fixture
def _ensure_api_tables(test_engine):
    """The operator-loaded tradewave_test snapshot can predate the API product;
    apply apiserver/schema.sql (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT
    EXISTS - additive + idempotent, test DB only) so the keys/usage tabs have
    their tables. apiserver.db reads POSTGRES_DSN, which conftest already
    points at tradewave_test before anything imports apiserver.settings."""
    with test_engine.begin() as conn:
        conn.exec_driver_sql(_SCHEMA_SQL.read_text())


@pytest.fixture
def as_user(app_module, make_user, _ensure_api_tables):
    """Log the test client in: inject a console user-loader returning a real
    tradewave_test User row, restoring the app's own loader afterwards."""
    from api_portal import blueprint as bp_mod

    user = make_user(tier="explorer")
    prev_loader = bp_mod._USER_LOADER
    bp_mod.set_user_loader(lambda: user)
    yield user
    bp_mod._USER_LOADER = prev_loader


@pytest.fixture
def login_as(app_module, make_user, _ensure_api_tables):
    """Factory version of as_user: `login_as(tier=..., api_tier=..., ...)`
    creates + logs in an arbitrary persona (§3's table), restoring the
    app's own loader afterwards. Returns the created User row."""
    from api_portal import blueprint as bp_mod

    prev_loader = bp_mod._USER_LOADER

    def _login(**kw):
        user = make_user(**kw)
        bp_mod.set_user_loader(lambda: user)
        return user

    yield _login
    bp_mod._USER_LOADER = prev_loader


# ---------------------------------------------------------------------
# §7 items 3-6: persona x card-state matrix, C1/C4/C5 banners, ?subscribe=
# highlight, R8 account hub link, no em-dashes anywhere rendered.
# ---------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

# (web_tier, explicit_api_tier, in_trial) -> expected effective tier + banner
# source, per docs/API_CONSOLE_USER_FLOWS.md §3's persona table.
_PERSONA_MATRIX = [
    ("explorer_trial", dict(tier="explorer",
                             reverse_trial_ends_at=lambda: datetime.now(timezone.utc) + timedelta(days=3)),
     "free", "bundled", True),
    ("explorer", dict(tier="explorer"), "free", "bundled", False),
    ("navigator", dict(tier="navigator"), "navigator", "bundled", False),
    ("analyst", dict(tier="analyst"), "dev", "bundled", False),
    ("strategist", dict(tier="strategist"), "pro", "bundled", False),
    ("strategist_explicit_dev", dict(tier="strategist", api_tier="dev"), "pro", "bundled", False),
]


@pytest.mark.db
class TestPersonaMatrix:
    """§3's table, replayed against the real routes/templates."""

    @pytest.mark.parametrize("name,kw,eff,src,in_trial", _PERSONA_MATRIX, ids=[p[0] for p in _PERSONA_MATRIX])
    def test_keys_and_billing_show_effective_tier(self, client, login_as, name, kw, eff, src, in_trial):
        kw = dict(kw)
        if "reverse_trial_ends_at" in kw:
            kw["reverse_trial_ends_at"] = kw["reverse_trial_ends_at"]()
        login_as(**kw)

        from apiserver import tiers as api_tiers
        eff_label = api_tiers.tier_for(eff)["name"]

        r_keys = client.get("/account/api/keys")
        assert r_keys.status_code == 200
        assert eff_label.encode() in r_keys.data, "%s: Keys tab must show effective tier %r" % (name, eff_label)

        r_bill = client.get("/account/api/billing")
        assert r_bill.status_code == 200
        assert eff_label.encode() in r_bill.data, "%s: Billing tab must show effective tier %r" % (name, eff_label)

    def test_strategist_with_lower_explicit_sub_stays_pro_not_downgraded(self, client, login_as):
        """The exact §7.1 defect: a bundled-pro Strategist holding an explicit
        LOWER dev sub must resolve pro (not be demoted), and Billing must show
        the redundant-sub advice (C5) rather than silently doing nothing."""
        login_as(tier="strategist", api_tier="dev")
        r = client.get("/account/api/billing")
        assert r.status_code == 200
        assert b"Pro" in r.data
        assert b"no longer needed" in r.data, "C5 redundant-sub advice must render"

    def test_churned_explicit_subscriber_can_resubscribe(self, client, login_as):
        """KNOWN DEFECT this task fixes: stripe_customer_id surviving a
        cancelled sub must NOT drive card state. A user with a stale
        stripe_customer_id but NO explicit api_tier (webhook nulled it on
        cancel) must see a real Subscribe button on Dev, not 'Switch in
        portal'."""
        user = login_as(tier="explorer", stripe_customer_id="cus_stale_churned_test")
        r = client.get("/account/api/billing")
        assert r.status_code == 200
        assert b"Subscribe" in r.data

    def test_bundled_user_never_shown_switch_in_portal_for_a_downgrade(self, client, login_as):
        """A Strategist (bundled pro) must never see a live Subscribe/'Switch
        in portal' offer for Dev - it is strictly below what the plan already
        grants for free."""
        login_as(tier="strategist")
        r = client.get("/account/api/billing")
        assert r.status_code == 200
        assert b"Included at a higher tier with your Strategist plan" in r.data


@pytest.mark.db
class TestBannerCopy:
    def test_c1_banner_present_keys_and_billing(self, client, as_user):
        for path in ("/account/api/keys", "/account/api/billing"):
            r = client.get(path)
            assert b"Your API access is included with your TradeWave plan" in r.data, path

    def test_c4_trial_note_when_in_reverse_trial(self, client, login_as):
        login_as(tier="explorer", reverse_trial_ends_at=datetime.now(timezone.utc) + timedelta(days=5))
        for path in ("/account/api/keys", "/account/api/billing"):
            r = client.get(path)
            assert b"REST API keys are separate and start on the Free tier" in r.data, path

    def test_c4_absent_when_no_trial(self, client, as_user):
        r = client.get("/account/api/keys")
        assert b"REST API keys are separate and start on the Free tier" not in r.data

    def test_c4_absent_when_trial_expired(self, client, login_as):
        login_as(tier="explorer", reverse_trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1))
        r = client.get("/account/api/keys")
        assert b"REST API keys are separate and start on the Free tier" not in r.data


@pytest.mark.db
class TestSubscribeDeepLink:
    def test_subscribe_pro_highlights_for_explorer(self, client, login_as):
        login_as(tier="explorer")
        r = client.get("/account/api/billing?subscribe=pro")
        assert r.status_code == 200
        assert b'id="plan-pro" class="card plan-highlight"' in r.data

    def test_subscribe_pro_no_highlight_for_strategist_already_covered(self, client, login_as):
        """R3: an already-covered tier degrades to the explanatory state,
        never an error, never a highlight that implies a purchase is live.
        (Note: the CSS rule for .plan-highlight is always present in the
        page's <style> block, so this checks the CARD ELEMENT'S class list,
        not a bare substring match against the whole page.)"""
        login_as(tier="strategist")
        r = client.get("/account/api/billing?subscribe=pro")
        assert r.status_code == 200
        assert b'id="plan-pro" class="card plan-highlight"' not in r.data
        assert b'id="plan-pro" class="card"' in r.data

    def test_subscribe_unknown_tier_degrades_silently(self, client, login_as):
        login_as(tier="explorer")
        r = client.get("/account/api/billing?subscribe=nonexistent")
        assert r.status_code == 200
        assert b' class="card plan-highlight"' not in r.data


@pytest.mark.db
class TestCheckoutServerSideGuard:
    @pytest.fixture(autouse=True)
    def _paid_checkout_enabled(self, app_module, monkeypatch):
        billing = importlib.import_module("api_portal.routes_billing")
        monkeypatch.setattr(billing.api_tiers, "API_PRICING_LIVE", True)

    def test_checkout_rejects_handcrafted_post_when_pricing_off(
        self, client, login_as, app_module, monkeypatch,
    ):
        login_as(tier="explorer")
        r_keys = client.get("/account/api/keys")
        import re
        token = re.search(
            rb'name="csrf_token"[^>]*value="([^"]+)"', r_keys.data,
        ).group(1).decode()
        billing = importlib.import_module("api_portal.routes_billing")
        monkeypatch.setattr(billing, "_stripe_configured", lambda: True)
        monkeypatch.setattr(billing.api_tiers, "API_PRICING_LIVE", False)
        price_lookup = []
        monkeypatch.setattr(
            billing,
            "_price_for_tier",
            lambda *args: price_lookup.append(args),
        )

        response = client.post(
            "/account/api/billing/checkout",
            data={"csrf_token": token, "tier": "dev"},
        )

        assert response.status_code == 403
        assert price_lookup == []

    def test_checkout_rejects_covered_tier(self, client, login_as):
        """Server-side re-check (spec: 4xx-with-flash, never 500) even if the
        UI never should have offered the button - a stale page or hand-built
        POST must not be able to buy something already held."""
        user = login_as(tier="strategist")
        r_keys = client.get("/account/api/keys")  # warm a CSRF token via the session
        import re
        m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r_keys.data)
        assert m, "no CSRF token found on keys page"
        token = m.group(1).decode()
        r = client.post(
            "/account/api/billing/checkout",
            data={"csrf_token": token, "tier": "pro"},
        )
        assert r.status_code == 400, "checkout of an already-covered tier must 4xx, got %s" % r.status_code

    def test_checkout_rejects_unknown_tier(self, client, login_as):
        login_as(tier="explorer")
        r_keys = client.get("/account/api/keys")
        import re
        m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r_keys.data)
        token = m.group(1).decode()
        r = client.post(
            "/account/api/billing/checkout",
            data={"csrf_token": token, "tier": "not_a_real_tier"},
        )
        assert r.status_code == 400

    def test_price_resolution_is_monthly_only(
        self, app_module, monkeypatch,
    ):
        """Billing is MONTHLY ONLY (owner decision 2026-07-05, reaffirmed
        2026-07-17). There is no interval parameter to fall back across - the
        cache is keyed by tier alone, and only ever holds a monthly price."""
        billing = importlib.import_module("api_portal.routes_billing")
        monthly = object()
        monkeypatch.setattr(billing, "_price_cache", {"pro": monthly})
        assert billing._price_for_tier("pro") is monthly
        assert billing._price_for_tier("business") is None

    def test_annual_checkout_is_rejected_before_any_price_lookup(
        self, client, login_as, monkeypatch,
    ):
        """An explicit annual ask must be rejected loudly (flash + redirect),
        never silently resolved to a different interval - and it must never
        even reach price resolution, since none is offered."""
        login_as(tier="explorer")
        r_keys = client.get("/account/api/keys")
        import re
        token = re.search(
            rb'name="csrf_token"[^>]*value="([^"]+)"', r_keys.data,
        ).group(1).decode()

        billing = importlib.import_module("api_portal.routes_billing")
        requested = []
        monkeypatch.setattr(billing, "_stripe_configured", lambda: True)
        monkeypatch.setattr(
            billing,
            "_price_for_tier",
            lambda tier: requested.append(tier) or None,
        )
        response = client.post(
            "/account/api/billing/checkout",
            data={
                "csrf_token": token,
                "tier": "dev",
                "interval": "annual",
            },
        )
        assert response.status_code == 400
        assert response.headers["Location"].endswith("/account/api/billing")
        assert requested == []


@pytest.mark.db
def test_no_em_dashes_in_rendered_console_pages(client, login_as):
    """House style (CLAUDE.md): no em-dashes anywhere in user-facing copy.
    Exercise the personas most likely to render every conditional banner
    (C1/C4/C5) in one pass."""
    login_as(tier="strategist", api_tier="dev",
             reverse_trial_ends_at=None)
    for path in ("/account/api/keys", "/account/api/billing"):
        r = client.get(path)
        assert r.status_code == 200
        assert "—".encode() not in r.data, "%s contains an em-dash" % path


@pytest.mark.db
def test_account_hub_has_api_mcp_action_when_console_enabled(client, app_module, as_user):
    """/account is a WEB APP route (not the api_portal blueprint), so it
    resolves the logged-in user through app_module.get_current_user (a
    WorkOS sealed-session read), not the console's injectable _USER_LOADER -
    same distinction the audit driver (tools/api_console_audit/driver.py)
    makes by overriding both independently. Monkeypatch it directly here."""
    app_module.get_current_user = lambda: as_user
    r = client.get("/account")
    assert r.status_code == 200
    assert b"API &amp; MCP" in r.data or b"API & MCP" in r.data
    assert b'/account/api/keys' in r.data


# ---------------------------------------------------------------------
# Index: the published upgrade_url must land
# ---------------------------------------------------------------------

@pytest.mark.db
class TestConsoleIndex:
    def test_bare_index_redirects_to_billing_tab(self, client):
        r = client.get("/account/api")
        assert r.status_code == 302, (
            "/account/api (the gateway's published upgrade_url) must redirect, "
            "got %s" % r.status_code
        )
        assert r.headers["Location"].endswith("/account/api/billing")

    def test_slash_index_redirects_to_billing_tab(self, client):
        r = client.get("/account/api/")
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/account/api/billing")

    def test_index_chain_never_404s_or_500s_anonymous(self, client):
        """Anonymous click on a published upgrade_url: index -> billing ->
        login bounce. Every hop is a redirect; none may 404/500."""
        r = client.get("/account/api")
        hops = 0
        while r.status_code in (301, 302, 303, 307, 308) and hops < 5:
            loc = r.headers["Location"]
            if not loc.startswith("/"):
                break  # off-app (e.g. WorkOS hosted login) - out of scope
            r = client.get(loc)
            hops += 1
        assert r.status_code not in (404, 500), (
            "upgrade_url redirect chain died with %s" % r.status_code
        )


# ---------------------------------------------------------------------
# Anonymous: every tab bounces to login, never 404/500
# ---------------------------------------------------------------------

@pytest.mark.db
class TestConsoleAnonymous:
    @pytest.mark.parametrize("path", sorted(_TABS))
    def test_tab_redirects_to_login(self, client, path):
        r = client.get(path)
        assert r.status_code == 302, "%s anon -> %s (want 302)" % (path, r.status_code)
        assert r.headers["Location"].startswith("/login?next="), (
            "%s anon must bounce to /login, got %r" % (path, r.headers["Location"])
        )


# ---------------------------------------------------------------------
# Logged in: every tab renders 200 (TESTING=True turns any handler
# exception - e.g. a missing flask import - into a test failure)
# ---------------------------------------------------------------------

@pytest.mark.db
class TestConsoleLoggedIn:
    @pytest.mark.parametrize("path", sorted(_TABS))
    def test_tab_renders(self, client, as_user, path):
        r = client.get(path)
        assert r.status_code == 200, "%s logged in -> %s (want 200)" % (path, r.status_code)
        assert _TABS[path] in r.data

    def test_usage_tab_regression_missing_flask_import(self, client, as_user):
        """The 2026-06-12 bug: routes_usage.py called render_template without
        importing it - NameError = 500 for every logged-in Usage view. A plain
        200 here proves the import exists AND the template renders."""
        r = client.get("/account/api/usage")
        assert r.status_code == 200

    def test_key_reveal_page_is_never_cacheable(self, client, as_user):
        from api_portal import routes_keys

        raw = "tw_live_" + ("a" * 32)
        with client.session_transaction() as browser_session:
            browser_session[routes_keys._ONCE_KEY_SESSION] = raw
        response = client.get("/account/api/keys")

        assert response.status_code == 200
        assert raw.encode() in response.data
        assert response.headers["Cache-Control"] == "private, no-store"
        assert response.headers["Pragma"] == "no-cache"

    def test_index_lands_logged_in_user_on_billing(self, client, as_user):
        r = client.get("/account/api", follow_redirects=True)
        assert r.status_code == 200
        assert b"Billing" in r.data


# ---------------------------------------------------------------------
# Flag off: the console ships dark (404), the prod invariant
# ---------------------------------------------------------------------

@pytest.mark.db
def test_console_dark_without_flag():
    """Blueprint registration is import-time and irreversible in-process, so
    the flag-off world needs its own interpreter: import the app WITHOUT
    TW2_API_CONSOLE_ENABLED and prove /account/api* is 404 everywhere."""
    env = dict(os.environ)
    env.pop("TW2_API_CONSOLE_ENABLED", None)
    # POSTGRES_DSN already points at tradewave_test (conftest overrode it in
    # this process; the child inherits). config.py reads only os.environ, so
    # popping the var above is sufficient - nothing re-loads it before the
    # `if config.API_CONSOLE_ENABLED` gate in web/app.py runs.
    assert "/tradewave_test" in env.get("POSTGRES_DSN", ""), "refusing: child would hit a non-test DB"
    code = "\n".join([
        "import sys",
        f"sys.path.insert(0, {str(_REPO_ROOT)!r})",
        f"sys.path.insert(0, {str(_REPO_ROOT / 'web')!r})",
        "import config",
        "assert not config.API_CONSOLE_ENABLED, 'flag leaked into the child env'",
        "import app",
        "assert 'api_portal' not in app.app.blueprints, 'console registered with flag OFF'",
        "c = app.app.test_client()",
        "paths = ['/account/api', '/account/api/', '/account/api/keys',",
        "         '/account/api/usage', '/account/api/billing', '/account/api/mcp']",
        "for p in paths:",
        "    r = c.get(p)",
        "    assert r.status_code == 404, '%s -> %s (want 404 when dark)' % (p, r.status_code)",
        "print('console-dark-ok')",
    ])
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, "flag-off child failed:\n%s" % proc.stderr[-3000:]
    assert "console-dark-ok" in proc.stdout
