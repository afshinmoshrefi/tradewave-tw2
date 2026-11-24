"""
Shared test fixtures for the TW2 web tier.

Strategy:
  * Pure-Python tests (`tier_compat`, `_json_safe` shape) need nothing.
  * DB tests use a real Postgres `tradewave_test` database that mirrors
    the production schema (loaded by an operator before the run; see
    /home/flask/tests/README.md). Each test gets a fresh transaction
    that is rolled back at teardown so no test sees another test's
    rows.
  * `mock_workos` and `mock_stripe` are factory fixtures that return a
    MagicMock with sane defaults; individual tests override return
    values as needed via `.return_value = ...`.

We deliberately do NOT import `web.app` at conftest collection time —
that module talks to live config (WorkOS, Stripe SDK init). Tests that
need callables from app.py import them lazily after `mock_workos` and
`mock_stripe` are in place.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------
# Environment bootstrap — runs at import time, before any test or
# conftest fixture is collected. Order matters here: we must populate
# the secrets env BEFORE config.py / models.py get imported anywhere.
# ---------------------------------------------------------------------

# 1. Mirror systemd's EnvironmentFile=/etc/tradewave/secrets.env. The
# file is mode 0640 root:flask; only the flask user can read it (run
# the test suite via `sudo -u flask`).
_SECRETS = Path("/etc/tradewave/secrets.env")
if _SECRETS.exists() and os.access(_SECRETS, os.R_OK):
    for line in _SECRETS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip().strip("'").strip('"')
        os.environ.setdefault(k.strip(), v)

# The current WorkOS SDK validates configuration when the client is
# constructed. Unit tests never make WorkOS network calls, but they still
# import web.app, so provide unmistakably non-production placeholders when a
# developer checkout has no secrets file.
os.environ.setdefault("WORKOS_API_KEY", "sk_test_unit_only")
os.environ.setdefault("WORKOS_CLIENT_ID", "client_test_unit_only")
os.environ.setdefault("WORKOS_COOKIE_PASSWORD", "unit-only-cookie-password")
os.environ.setdefault("APPSERVER_JWT_SECRET", "unit-only-jwt-secret-at-least-32-bytes")
os.environ.setdefault("SERVICE_API_KEY", "unit-only-service-key")

# 2. Force POSTGRES_DSN to an exact, local tradewave_test database BEFORE
# models.py is imported. An explicit TW2_TEST_POSTGRES_DSN wins; otherwise we
# derive only the database name from the configured local production DSN.
# Never include the raw DSN in an error because it commonly embeds a password.
_explicit_test_dsn = os.environ.get("TW2_TEST_POSTGRES_DSN", "").strip()
_configured_dsn = _explicit_test_dsn or os.environ.get("POSTGRES_DSN", "").strip()
if not _configured_dsn:
    _configured_dsn = "postgresql://tradewave@127.0.0.1:5432/tradewave_test"

try:
    _test_url = urlsplit(_configured_dsn)
    _database = unquote(_test_url.path.removeprefix("/"))
    _url_host = _test_url.hostname
except (TypeError, ValueError) as exc:
    raise RuntimeError(
        "REFUSING to run tests: the configured test PostgreSQL DSN is invalid"
    ) from exc

if not (_test_url.scheme == "postgres" or _test_url.scheme.startswith("postgresql")):
    raise RuntimeError(
        "REFUSING to run tests: the configured test DSN is not PostgreSQL"
    )
if not _explicit_test_dsn:
    if _database not in {"tradewave", "tradewave_test"}:
        raise RuntimeError(
            "REFUSING to derive a test DSN from an unexpected database name; "
            "set TW2_TEST_POSTGRES_DSN explicitly"
        )
    _test_url = _test_url._replace(path="/tradewave_test")
    _database = "tradewave_test"

if _database != "tradewave_test":
    raise RuntimeError(
        "REFUSING to run tests: TW2_TEST_POSTGRES_DSN must name exactly "
        "tradewave_test"
    )
_allowed_hosts = {None, "localhost", "127.0.0.1", "::1"}
_hosts = [_url_host]
for _query_host in parse_qs(_test_url.query).get("host", []):
    _hosts.extend(part.strip() for part in _query_host.split(",") if part.strip())
if any(host not in _allowed_hosts and not str(host).startswith("/") for host in _hosts):
    raise RuntimeError(
        "REFUSING to run tests: tradewave_test must be on the local host"
    )

TEST_DSN = urlunsplit(_test_url)
os.environ["POSTGRES_DSN"] = TEST_DSN

# 3. Make this checkout's web/ tree importable so `from models import ...`
# works the same way the running web tier sees it.  This must be relative to
# conftest.py rather than hardcoded to /home/flask: integrity runs use an
# isolated release-candidate checkout on the dev box, and importing the live
# checkout there would test the wrong code while appearing to pass.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "web"))


# ---------------------------------------------------------------------
# Engine / session
# ---------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_engine():
    """One Postgres engine pointing at the tradewave_test DB for the whole run."""
    from sqlalchemy import create_engine
    eng = create_engine(TEST_DSN, pool_pre_ping=True, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def _models_module(test_engine):
    """Import models with engine/session swapped to the test DB.

    models.py reads config.POSTGRES_DSN at import time and binds an engine
    + scoped_session immediately. Because we already overrode POSTGRES_DSN
    above, the import lands on tradewave_test directly. We still re-bind
    Session to our pool_pre_ping engine for safety.
    """
    import models as m
    m.engine = test_engine
    m.Session.configure(bind=test_engine)
    return m


@pytest.fixture
def db_session(_models_module):
    """Per-test session that wraps every test in a transaction we always
    roll back at teardown — keeps the test DB pristine across runs."""
    Session = _models_module.Session
    s = Session()
    # Clear common tables at the START of each test (defensive — prior
    # crashed tests can leave debris if the rollback didn't run).
    s.execute(_models_module.AuditLog.__table__.delete())
    s.execute(_models_module.StripeEvent.__table__.delete())
    s.execute(_models_module.MailerLiteLifecycleEvent.__table__.delete())
    s.execute(_models_module.EmailOptout.__table__.delete())
    s.execute(_models_module.User.__table__.delete())
    s.commit()
    try:
        yield s
    finally:
        try:
            s.rollback()
        except Exception:
            pass
        # Hard cleanup so the next test starts empty even if assertions
        # left rows behind without rolling back.
        try:
            s.execute(_models_module.AuditLog.__table__.delete())
            s.execute(_models_module.StripeEvent.__table__.delete())
            s.execute(_models_module.MailerLiteLifecycleEvent.__table__.delete())
            s.execute(_models_module.EmailOptout.__table__.delete())
            s.execute(_models_module.User.__table__.delete())
            s.commit()
        except Exception:
            s.rollback()
        s.close()
        Session.remove()


# ---------------------------------------------------------------------
# WorkOS / Stripe mocks
# ---------------------------------------------------------------------

@pytest.fixture
def mock_workos_user():
    """Factory: a minimal WorkOS user object with email, id, etc.

    Mirrors the duck-typed access lazy_create_user does:
      workos_user.id, .email, .email_verified, .first_name, .last_name
    """
    def _make(
        id: str | None = None,
        email: str = "test@example.com",
        email_verified: bool = True,
        first_name: str = "Test",
        last_name: str = "User",
    ):
        u = MagicMock()
        u.id = id or f"user_{uuid.uuid4().hex[:16]}"
        u.email = email
        u.email_verified = email_verified
        u.first_name = first_name
        u.last_name = last_name
        return u
    return _make


@pytest.fixture
def mock_workos(monkeypatch):
    """Patch web.app.workos_client to a MagicMock + return the mock.

    Tests can reach into mock_workos.user_management.load_sealed_session.return_value
    to control what `_read_sealed_session()` sees.
    """
    fake = MagicMock(name="workos_client")
    return fake


@pytest.fixture
def mock_stripe(monkeypatch):
    """Patch the stripe SDK so no real network calls fire during tests.

    Stubs:
      stripe.Webhook.construct_event   → returns the parsed payload
      stripe.Customer.retrieve         → returns a MagicMock with email=None
    """
    import stripe
    fake_construct = MagicMock(name="construct_event")
    fake_construct.side_effect = lambda payload, sig, secret: __import__("json").loads(payload)
    monkeypatch.setattr(stripe.Webhook, "construct_event", fake_construct)

    fake_cust = MagicMock(name="Customer.retrieve")
    fake_cust.return_value = MagicMock(email=None)
    monkeypatch.setattr(stripe.Customer, "retrieve", fake_cust)

    return {"construct_event": fake_construct, "customer_retrieve": fake_cust}


# ---------------------------------------------------------------------
# Helpers tests can use
# ---------------------------------------------------------------------

@pytest.fixture
def make_user(db_session, _models_module):
    """Insert + return a User row. Common building block for DB tests."""
    User = _models_module.User
    created = []

    def _make(**kw):
        defaults = {
            "email": f"{uuid.uuid4().hex[:8]}@example.com",
            "tier": "explorer",
            "roles": ["user"],
        }
        defaults.update(kw)
        u = User(**defaults)
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)
        created.append(u)
        return u

    yield _make
    # Cleanup happens in db_session teardown.


# ---------------------------------------------------------------------
# Tara plan gate. tara_gateway._plan_scope reads the caller's plan ONLY from
# the claims the chat route verified (flask.g.chatbot_jwt) and grants nothing
# without them. Unit tests that call the gateway functions directly have no
# request, so they run as a Strategist-level caller unless they say otherwise;
# inside a real request the route's own verified claims are always used.
# ---------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _tara_unit_test_plan(monkeypatch):
    gateway = sys.modules.get("tara_gateway")
    if gateway is None or not hasattr(gateway, "_verified_claims"):
        yield
        return
    real = gateway._verified_claims

    def claims():
        verified = real()
        if verified is not None:
            return verified
        return {"user": "unit-test", "user_level": "6"}

    monkeypatch.setattr(gateway, "_verified_claims", claims)
    yield


# ---------------------------------------------------------------------
# Tara engine replies with a model lead (TW-TASK-0035 phase B). The engine
# reply is sent word for word and the model may only add a validated lead
# above it. Every Tara test runs with that path ON and a HOSTILE model: the
# lead it offers moves a figure, flips a direction, invents a count and
# gives advice. The route tests therefore prove that an engine reply reaches
# the user unchanged whatever the model says. A test that drives the lead
# itself asks for it with @pytest.mark.tara_draft_rewrite.
# ---------------------------------------------------------------------
HOSTILE_LEAD = ("Yes: it rose in 99 of 100 years with an average of +55.5%, so you should "
                "buy it now. I have loaded it on your chart.")


@pytest.fixture(autouse=True)
def _tara_engine_reply_with_hostile_lead(request, monkeypatch):
    gateway = sys.modules.get("tara_gateway")
    if gateway is not None and hasattr(gateway, "DRAFT_REWRITE_ENABLED"):
        # tara_rewrite_off pins the shipped default: no provider is reached at all.
        monkeypatch.setattr(
            gateway, "DRAFT_REWRITE_ENABLED",
            request.node.get_closest_marker("tara_rewrite_off") is None)
        if request.node.get_closest_marker("tara_draft_rewrite") is None:
            monkeypatch.setattr(gateway, "_request_lead", lambda *args, **kwargs: HOSTILE_LEAD)
    yield


# VIX pause annotation (appserver/appserver/vix_gate.py) reads TradeWave VIX history,
# which may download data. Tests never touch the network: by default the history is
# unavailable, so responses pass through unchanged. tests/test_vix_gate.py injects
# its own history.
@pytest.fixture(autouse=True)
def _no_live_vix_history(monkeypatch):
    try:
        import vix_gate
    except ImportError:
        yield
        return

    def _unavailable():
        raise OSError("VIX history disabled in tests")
    monkeypatch.setattr(vix_gate, "_default_loader", _unavailable)
    monkeypatch.setattr(vix_gate, "_default_live_loader", lambda: None)
    monkeypatch.setitem(vix_gate._CACHE, "rows", None)
    monkeypatch.setitem(vix_gate._CACHE, "live", None)
    monkeypatch.setitem(vix_gate._CACHE, "live_at", 0.0)
    yield
