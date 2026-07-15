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
try:
    _SECRET_LINES = (
        _SECRETS.read_text().splitlines() if os.access(_SECRETS, os.R_OK) else ()
    )
except OSError:
    # Network-isolated release tests deliberately make /etc/tradewave
    # inaccessible. Treat that boundary exactly like an absent optional file.
    _SECRET_LINES = ()
for line in _SECRET_LINES:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    v = v.strip().strip("'").strip('"')
    os.environ.setdefault(k.strip(), v)

# 2. Force POSTGRES_DSN to point at tradewave_test BEFORE models.py is
# imported. config.POSTGRES_DSN is read at module-load time (`engine =
# create_engine(config.POSTGRES_DSN, ...)` in models.py), so we MUST
# override before any `import models` anywhere in the suite.
_PROD_DSN = os.environ.get("POSTGRES_DSN", "")
if "/tradewave_test" not in _PROD_DSN:
    if _PROD_DSN.endswith("/tradewave"):
        os.environ["POSTGRES_DSN"] = _PROD_DSN[:-len("/tradewave")] + "/tradewave_test"
    elif _PROD_DSN:
        # DSN with query string or different path — best-effort swap
        os.environ["POSTGRES_DSN"] = _PROD_DSN.replace("/tradewave", "/tradewave_test")
    else:
        os.environ["POSTGRES_DSN"] = (
            "postgresql://tradewave@127.0.0.1:5432/tradewave_test"
        )

TEST_DSN = os.environ["POSTGRES_DSN"]
assert "/tradewave_test" in TEST_DSN, (
    f"REFUSING to run tests: POSTGRES_DSN does not target tradewave_test "
    f"(got {TEST_DSN!r}). Set TW2_TEST_POSTGRES_DSN explicitly."
)

# 3. Make the web/ tree importable so `from models import ...` works the
# same way the running web tier sees it.
sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")


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
