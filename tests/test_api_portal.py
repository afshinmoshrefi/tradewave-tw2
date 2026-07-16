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
