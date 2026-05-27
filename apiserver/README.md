# TradeWave API gateway + MCP - build notes (dev)

Isolated, additive service. Public product = derived signals only (no raw prices).

## Layout
- `apiserver/` - the Flask gateway (this dir). Foundation files are done; `routes.py`
  + the `appserver_client` accessors are filled in by the gateway agent.
- `mcpserver/` - the MCP server (Python `mcp` SDK). Built by the MCP agent.
- `web/api_portal/` - the customer console blueprint. Built by the console agent.
- Docs + marketing - static, match tradewave.ai brand. Built by their agents.
- Contract (frozen): `../api/openapi.yaml` + `../api/MCP_TOOLS.md`.

## Foundation (shared, do not duplicate)
- `settings.py` - env/secrets (POSTGRES_DSN, API_KEY_HMAC_SECRET, APPSERVER_URL, SERVICE_API_KEY, Stripe).
- `tiers.py` - tier entitlements (scope, ML, rate limits). Single source of truth.
- `db.py` - api_keys + usage + user lookups.
- `auth.py` - `require_api_key` decorator, key hashing, rate limit, usage. Use these; don't reinvent.
- `appserver_client.py` - service-account bridge to the appserver (drops raw prices).
- `schema.sql` - api_keys + api_usage_daily (additive; run at integration).

## Run on dev
```
cd /home/flask
./venv-api/bin/python -m apiserver.app                      # dev server on 127.0.0.1:8088
./venv-api/bin/gunicorn -b 127.0.0.1:8088 apiserver.app:app # prod-style
curl 127.0.0.1:8088/healthz
```

## Hard rules for agents
- ADD files only. Do NOT edit `config.py`, `web/app.py`, the React build, or existing services.
- Do NOT run DB migrations, restart services, or touch cloudflared - integration is the parent's job.
- Do NOT `pip install` into the shared `/home/flask/venv`; deps live in `/home/flask/venv-api` (already set up).
- Loopback only; the appserver port is per-env (dev :5000) - read it from settings, never hardcode.
- No raw OHLCV / last price / price-by-date in any public response; returns are percentages.
- No em-dashes in any user-facing copy (use ' - '); `years` stays a string.
