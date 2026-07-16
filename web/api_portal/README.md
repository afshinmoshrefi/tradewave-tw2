# API Customer Console (`web/api_portal/`)

Self-contained Flask **Blueprint** for the logged-in customer self-serve API
console on tradewave.ai. Runs **inside the existing web tier** (`/home/flask/web`,
the `/home/flask/venv` web venv). Additive only - it does not edit `web/app.py`,
`web/models.py`, or `config.py`.

Scope: customer self-serve ONLY (API keys, usage, billing, MCP connect). No
internal/admin views.

## Integration (parent does this in `web/app.py`)

Add, near the other blueprint/admin registrations:

```python
import api_portal
api_portal.bp.set_user_loader(get_current_user)   # share the web app's WorkOS resolver (recommended)
app.register_blueprint(api_portal.bp, url_prefix="/account/api")
```

- `set_user_loader(get_current_user)` makes the console reuse the web app's exact
  WorkOS sealed-session auth. **If you skip it**, the blueprint falls back to
  reading the same sealed cookie itself (same `tw2_session` cookie +
  `config.WORKOS_COOKIE_PASSWORD`) and resolving the Postgres `User` via
  `web/models.py` - so it still works, just with its own (non-refreshing) session
  read.
- `url_prefix="/account/api"` is the canonical mount (matches the
  `https://<host>/account/api` upgrade URL already referenced in
  `apiserver/routes.py`). The blueprint's static is namespaced to
  `/account/api/static`, so it never collides with the web app's `/static`.

### Routes (all under `/account/api`)

| Method | Path                         | Page / action                          |
|--------|------------------------------|----------------------------------------|
| GET    | `/keys`                      | List keys + create form (one-time reveal) |
| POST   | `/keys/create`               | Create a key (enforces tier `max_keys`)|
| POST   | `/keys/<id>/rotate`          | Rotate (new key + revoke old)          |
| POST   | `/keys/<id>/revoke`          | Revoke a key                           |
| GET    | `/usage`                     | Usage vs quota (Redis today + rollup)  |
| GET    | `/billing`                   | 4 tiers + checkout / portal            |
| POST   | `/billing/checkout`          | Stripe Checkout (mode=subscription)    |
| GET    | `/billing/success`           | Post-checkout return (no tier write)   |
| GET    | `/billing/manage`            | Stripe Billing Portal redirect         |
| GET    | `/mcp`                       | MCP URL + hosted OAuth setup; optional Claude Desktop/Cursor BYOK setup |

POST routes carry `{{ csrf_token() }}` (the web app's global Flask-WTF
`CSRFProtect` validates them; nothing here is csrf-exempt).

## Keys: generation + storage
- Format `tw_live_<32 hex>` via `secrets.token_hex(16)` (128 bits).
- Stored: **only** `apiserver.auth.hash_key(raw)` (HMAC-SHA256) in `api_keys.key_hash`,
  plus `name` and a non-secret display `prefix` (`tw_live_` + first 8 hex). The
  raw key is shown to the user exactly once (Flask-session one-time reveal) and
  is never recoverable.
- Reuses the `apiserver` package end-to-end: `apiserver.db.cursor` (same
  `POSTGRES_DSN`), `apiserver.auth.hash_key`, `apiserver.tiers` (entitlements +
  `max_keys`). Tables come from `apiserver/schema.sql` (`api_keys`,
  `api_usage_daily`) - run at integration; **not** run here.

## Usage
- "Today" reads the gateway's per-day Redis counters in **db4** (same
  `apiserver.settings.REDIS_DB`): `usage:{uid}:{YYYY-MM-DD}` (per-endpoint hash)
  and `rl:day:{uid}:{epoch_day}` (daily total). Redis is best-effort (a Redis
  outage degrades the page, never 500s it).
- History reads the `api_usage_daily` rollup table.

## Billing - Stripe (NOT called during build)
- Mirrors `web/app.py`: `_stripe_configured()` guard, **metadata-only** price
  resolution (`product_line=api` + `tier`), `stripe.checkout.Session.create`
  with `client_reference_id=<user uuid>` and subscription metadata
  `{tw2_user_id, product_line=api, tier}`, and the `billing_portal` redirect for
  upgrade/downgrade/cancel.
- **No Stripe API call happens at import or build time** - only at request time
  when a logged-in user clicks a button. Confirmed: nothing in this package
  calls Stripe on import.
- `create_api_products.py` idempotently creates the 4 **TEST-mode**
  products/prices. It is **NOT run** by this build and **refuses to run** unless
  `STRIPE_SECRET_KEY` starts with `sk_test_`. Parent runs it once at integration:
  ```
  cd /home/flask
  STRIPE_SECRET_KEY=sk_test_... ./venv/bin/python web/api_portal/create_api_products.py
  ```

### API tier writes on payment
The active `users.api_tier` column keeps standalone API subscriptions separate
from the web subscription tier. The existing `/webhooks/stripe` handler routes
subscriptions with `product_line=api` to `users.api_tier`; it never writes the
web `users.tier` for that product line. `apiserver.tiers.api_tier_from_user`
prefers this explicit API tier. When it is null, the bundled web entitlement is
inherited: Explorer -> Free, Navigator -> internal Navigator, Analyst -> Dev,
and Strategist -> Pro.

## MCP connect
- MCP host is per-env: override with `TW2_MCP_PUBLIC_HOST`, else derived from
  `config.tw2_env` (dev->`mcp-dev.trxstat.com`, staging->`mcp-stage.trxstat.com`,
  prod->`mcp.tradewave.ai`). Dev default = `mcp-dev.trxstat.com`.
- The published connector URL is the BARE host (no `/mcp` path; the server also
  aliases `/mcp`).
- Page shows the MCP URL + per-client setup. ChatGPT, Claude.ai, and Claude
  Desktop connect to the hosted connector through OAuth (paste the URL, connect,
  and sign in with the TradeWave account - no API key). Claude Desktop also has
  an optional BYOK bridge, while Cursor uses the BYOK configuration. OAuth mirrors
  the user's web plan and active teaser; BYOK uses the API entitlement ladder.

## Validate (web venv)
```
cd /home/flask && ./venv/bin/python -m py_compile web/api_portal/*.py
```
