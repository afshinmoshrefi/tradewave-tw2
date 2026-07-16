# TW2 web-tier test suite

Initial pytest coverage for the four highest-leverage paths in
`/home/flask/web/`. Created 2026-05-06 (BUILD AGENT F8, Round 2).

## How to run

```bash
cd /home/flask && sudo -u flask /home/flask/venv/bin/python -m pytest -ra --tb=short
```

Or, if you only want fast unit tests (no Postgres):

```bash
cd /home/flask && sudo -u flask /home/flask/venv/bin/python -m pytest -ra --tb=short -m unit
```

Make targets are also wired up:

```bash
cd /home/flask && make test          # full suite
cd /home/flask && make test-unit     # unit-only
cd /home/flask && make test-db       # DB-only
```

The fixtures resolve the repository root from `tests/conftest.py`; they do not
hardcode `/home/flask` for imports. This is intentional: an integrity run from
an isolated release-candidate checkout must test that checkout rather than
silently importing modules from the currently deployed dev tree.

## API + MCP gateway tests (no DB)

The public API gateway (`apiserver/`) and the MCP server (`mcpserver/`) are covered by
hermetic tests (auth, redis, and the appserver are all mocked - no Postgres needed):

- `test_market_bands.py` - the per-market pattern-detection win-rate band.
- `test_cards.py` - the PatternCard builder, charting math, view projection, neutral.
- `test_apiserver_endpoints.py` - route wiring (band 400, disclaimer coverage, view, include=chart).
- `test_consistency.py` - cross-surface drift guards (manifest/guide/spec vs the live tools).

These import `apiserver`, so run them under the gateway venv (`venv`, which has flask+pytest):

```bash
cd /home/flask && /home/flask/venv/bin/python -m pytest tests/ -m unit
```

`test_mcpserver.py` needs `fastmcp`, which lives in `venv-api` (not `venv`). It self-skips
under `venv` (via `importorskip`); run it explicitly under `venv-api`:

```bash
cd /home/flask && /home/flask/venv-api/bin/python -m pytest tests/test_mcpserver.py
```

## Test DB setup (one-time)

The DB-backed tests connect to `tradewave_test` on the same Postgres
instance the running tier uses, with the same role. Create / refresh it:

```bash
sudo -u postgres psql -c "DROP DATABASE IF EXISTS tradewave_test;"
sudo -u postgres psql -c "CREATE DATABASE tradewave_test OWNER tradewave;"
sudo PGPASSWORD=<tradewave-password> pg_dump -h 127.0.0.1 -U tradewave \
     -d tradewave --schema-only --no-owner > /tmp/tradewave_schema.sql
sudo PGPASSWORD=<tradewave-password> psql -h 127.0.0.1 -U tradewave \
     -d tradewave_test -f /tmp/tradewave_schema.sql
```

Each test wraps its work in a transaction we roll back at teardown, so
the DB stays clean across runs. `conftest.py` also clears `users`,
`audit_log`, and `stripe_events` at the start and end of each test as a
safety net.

## What is covered

| File | Path under test | Branches |
|---|---|---|
| `test_tier_compat.py` | `web/tier_compat.py` | All public functions. **Anti-inversion guards** that explicitly forbid the analyst='6'/strategist='4' bug from re-appearing. |
| `test_webhook_idempotency.py` | `web/app.py::webhook_stripe` (parts) | StripeEvent unique constraint, SELECT-then-INSERT idempotency pattern, `_json_safe` Decimal handling — the bug that used to drop entire StripeEvent rows. |
| `test_sealed_session.py` | `web/app.py::_read_sealed_session` | All 5 branches: no cookie, malformed cookie, valid auth, refresh-success (with cookie staging on `g`), refresh-failure (both False return AND exception). |
| `test_lazy_create_user.py` | `web/app.py::lazy_create_user` | Happy-path create, idempotent re-call, email-collision backfill, IntegrityError signup race, WorkOS email-change sync + audit. |

## What is NOT covered yet (deferred for future work)

Full integration coverage of the Flask routes is out of scope for this
first pass. The following need follow-up tests:

- **`/auth/callback` route** — the full sign-in HTTP path that calls
  `lazy_create_user` and sets the sealed cookie. Needs Flask test client
  + a stubbed `authenticate_with_code`. Today we cover only the helper.
- **`/webhooks/stripe` end-to-end** — POSTing a synthesised event with a
  signature, asserting tier change + audit row + 200 response. Today we
  cover only the dedup primitives (StripeEvent uniqueness + `_json_safe`).
  The full handler also has the `with_for_update()` lock path, the
  `stripe_customer_id` rebind-conflict guard, the `user_not_found` 500,
  and the `tier_changed` audit — none currently hit.
- **`/stripe/success` short-circuit** — F2.11 idempotency between webhook
  and success-redirect race. Untested.
- **Flask-Admin authorization** — `_AdminAuth.is_accessible` and the
  super_admin role gating need a route-level test.
- **Appserver `/login/...` LTK flow** — the auth bypass fix from today
  (Fix 2 in the session state doc) deserves dedicated regression tests
  but lives in `appserver/`, a different service. Track separately.
- **Email + Mailerlite paths** — `email_utils.mailerlite_subscribe` is
  stubbed in our tests; no test verifies the real HTTP call shape.
- **Migrations** — alembic upgrade/downgrade is exercised manually only.

## Conventions

- DB tests are tagged `@pytest.mark.db`; pure-Python tests `@pytest.mark.unit`.
- No test makes a real network call. WorkOS, Stripe SDK, and Mailerlite
  are mocked via `monkeypatch`/`unittest.mock`.
- No test mutates the production `tradewave` database. DB tests use
  `tradewave_test` only — confirmed by the `TW2_TEST_POSTGRES_DSN` env
  var defaulting to `.../tradewave_test`.
