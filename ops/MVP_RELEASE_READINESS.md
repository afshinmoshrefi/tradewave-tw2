# TradeWave MVP release readiness

Status: development code and deployment artifacts prepared. No staging or production
deployment was performed by this work.

## Minimal rollout order

1. **Land the development baseline.** Use the reviewed commit containing the existing
   tier enforcement, stability, subscriber UX, billing/portal work, plus the API, MCP,
   and appserver scalability changes. Do not replace it with the older MCP hardening
   branch wholesale.
2. **Verify development locally.** Run `python -m pytest -m unit -q`, regenerate the API
   docs and developer marketing output, and run `git diff --check`. Database-marked tests
   require the isolated `tradewave_test` Postgres database described in `tests/README.md`.
3. **Start the development services with the tracked units.** Appserver defaults to 4
   gthread workers x 4 threads for dev's 4 CPU / 16 GB. API remains 4 gthread workers x
   12 threads. MCP remains one asyncio process with 32 bounded gateway calls. Keep
   `TRADEWAVE_API_KEY` unset on hosted MCP.
4. **Apply only the additive development schema.** Confirm `users.api_tier`, API
   subscription identity fields, `api_keys`, and `api_usage_daily`. Use test-mode Stripe
   products and prices in development. Do not enable public paid pricing yet.
5. **Run the development release gate.** Execute `ops/verify_mvp_release.py` with an
   existing API key and WorkOS OAuth token. It must pass API BYOK, a non-null daily pick,
   MCP BYOK, MCP OAuth, concurrent scan load, and the storm-breaker canary.
6. **Review the commercial path in development.** Create/revoke a key in the customer
   console, verify usage display, test API checkout and portal return, and confirm API
   subscription webhooks change `api_tier` without changing the web subscription tier.
   Keep `TW2_API_PRICING_LIVE` off until the owner approves live prices.
7. **Prepare staging, then deploy in a separate authorized session.** Before any staging
   performance gate, free disk space and resize it; the current 1 CPU / roughly 1 GB box
   is not a meaningful proxy. Deployment itself is intentionally outside this work.
8. **Deploy production on the owner-approved low-traffic capacity.** As of 2026-08-03,
   the production appserver baseline is 2 CPU / 4 GB with 4 workers x 4 threads. Deploy
   off-hours away from the 02:00 UTC cron burst, rerun the same auth/load gate, and scale
   above the baseline when the documented sustained-load triggers are reached. Make the
   owner-approved Stripe pricing visibility flip only as a separate business decision.

## MVP acceptance criteria

- No async rewrite of the Flask appserver or API gateway.
- MCP is async only where it waits on gateway HTTP and uses bounded connection reuse.
- Daily pick returns a real card or an honest 503, never `200 card:null` due to topology.
- API-key revocation propagation is bounded by the positive-cache TTL of 30 seconds;
  negative lookups are not cached and the cache is capped at 4096 entries per worker.
- ML quota consumption is atomic under concurrency.
- Appserver cache fills are single-flight and file publication is atomic.
- Gunicorn and nginx access logs omit query strings.
- The release gate has at most 1% errors, scan p95 at most 15 seconds, and the appserver
  storm breaker remains inactive.
- WorkOS OAuth and BYOK both pass end to end before each environment is promoted.
