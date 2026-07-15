# API / MCP Deployment - Action Items & Handoff

A pick-up-able checklist to take the API/MCP product (incl. Tara + the consumer OAuth connect) from
"working on dev" to live on staging + prod. Authored for the operator (Afshin) - per the hard rules,
NEVER touch staging/prod directly; the operator runs the commands. Last updated 2026-07-15.

Control docs (the detail): `docs/MCP_OAUTH_INTEGRATION.md`, `docs/TARA_GATEWAY_INTEGRATION.md`,
`ops/OPERATIONS.md`, `ops/PROD_CUTOVER.md`, `ops/bootstrap_api_services.sh`,
`ops/assemble_developer_portal.sh`, `ops/SPLIT_GATEWAY_TO_OWN_BOX.md`, `api/BUILD_STATE.md`.
Memory: `reference_mcp_api_knowhow`, `project_mcp_consumer_oauth_goal`, `project_tara_gateway_client`.

## Status snapshot
- MCP is a release candidate. Promotion is blocked unless the authenticated public release verifier proves
  OAuth discovery, the exact 17-tool schema/annotation contract, a real `whoami` gateway call, and 20
  independent concurrent ChatGPT-style sessions. Nothing is on staging/prod yet.
- Scope built this session: gateway tier-resolution for WorkOS users, the MCP resource-server (WorkOS JWT
  verifier, streamable-http, root-mount), Tara gateway client (Phase 1 + 2), the e2e-review fixes,
  ML-score table filter, slim dev-portal nav, Liquid name-drop removal.

## RELEASE SOURCE - read this first
- Deploy MCP only from an exact lowercase 40-character commit SHA through the fixed installed launcher.
  Branches, refs, mixed-case SHAs, caller-supplied refspecs, and ambiguous `HEAD` are rejected before
  the root controller starts. The SHA must be fetchable from the fixed canonical HTTPS origin.
- The app checkout may contain unrelated operator work. `ops/deploy_mcp_release.sh` leaves the gateway in
  `/home/flask` untouched and creates a root-owned, non-writable MCP code + venv + config bundle under
  `/home/tradewave-mcp/releases/`. Do not clean, reset, or repoint the live gateway checkout for this release.
- RC command on dev: `sudo /usr/local/sbin/tradewave-mcp-release <reviewed-lowercase-40-sha>`.
  A failure in unit, nginx, process, contract, gateway-call, or 20-session verification restores the prior
  code/runtime/config automatically. Manual rollback uses the same launcher with `--rollback`.

## Pre-deploy DECISIONS (from the e2e review - `/home/afshin/TRADEWAVE_APP_REVIEW_2026-06-02.md`)
- [ ] Checkout CSRF (`web/app.py` `/api/stripe/create-checkout` is `@csrf.exempt`) - low blast radius; needs the
      live billing form tested before changing. Decide: fix now or note as accepted.
- [ ] `SERVICE_API_KEY` in the `/login/api/{key}` URL path (`apiserver/appserver_client.py`) - move to header.
- [ ] ML-endpoint rate-limit decorators (`appserver.py` MLScoreBatch/Pending) - pick a per-tier limit.
- [ ] SEO: `ENABLE_SEO` now prod-only (env-driven) - confirm prod build flips it; the assemble guard rejects
      stale dev URLs.

## DEPLOY - run for STAGING first, verify, THEN prod (never skip staging)
For EACH env (staging, then prod):

1. **Code out.** Get the reviewed code on the box. MCP itself is promoted with
   `sudo /usr/local/sbin/tradewave-mcp-release <reviewed-lowercase-40-sha>`; it uses the tracked fully
   pinned SHA-256-hashed `requirements-mcp.lock` (MCP 1.28.1) and offline, binary-wheel-only installs
   under the exact isolated system CPython 3.13. It never mutates `/home/flask/venv-api`.
   The seal binds source, selected wheels, and installed bytes; the host-managed interpreter, standard
   library, CA store, and OS remain external trust boundaries. React =
   symlink-swap deploy (`ops/deploy.sh` / the react release step). Reassemble the dev portal:
   `sudo bash ops/assemble_developer_portal.sh` (TW2_ENV set so the URL guard + SEO flip apply).
2. **API/MCP services.** If the box has no gateway/MCP yet, bootstrap the loopback gateway/service once. Then use
   the immutable MCP release command above; it installs the versioned unit/drop-in/nginx configuration itself.
3. **Secrets and MCP identity (per env) - add/confirm:**
   - Tara: `TARA_GATEWAY_KEY` (run `venv-api/bin/python -m apiserver.provision_chatbot_key`), `TW2_GATEWAY_URL`
     (the gateway base, e.g. `http://127.0.0.1:80/v1` on stg/prod), optionally `APPSERVER_CORS_ORIGINS`.
   - MCP-OAuth metadata in the broad platform source: `WORKOS_AUTHKIT_DOMAIN` (already set for web
     login - reuse), `TW2_MCP_PUBLIC_URL` (the env's MCP host:
     `https://mcp-stage.trxstat.com` / `https://mcp.tradewave.ai`), plus a dedicated safe smoke account:
     `TW_MCP_SMOKE_WORKOS_SUB` and its lowercase `TW_MCP_SMOKE_EXPECT_TIER`. Deploy strictly parses these
     values.
   - Do **not** manually add or rotate `MCP_GATEWAY_KEY` in the broad platform file. On a legacy first
     migration the fixed root controller may discover the old K0 there, but it transactionally creates
     K1, writes it only to `/etc/tradewave/mcpserver.env` (root:root 0600), removes every broad-file
     assignment, proves the replacement PID and exact database identity, then revokes K0. Its root-only
     rotation state binds the new and superseded key IDs/hashes without storing either raw key. PID 1
     reads the MCP-only file before dropping to `tradewave-mcp`; the worker cannot browse
     `/etc/tradewave` or `/home/flask`, never receives `secrets.env`, and `TRADEWAVE_API_KEY` remains absent.
4. **WorkOS dashboard (per WorkOS env).** WorkOS has only STAGING + PROD. The dev + staging BOXES both ride WorkOS
   STAGING; the prod box rides WorkOS PROD.
   - WorkOS STAGING: Connect -> Configuration -> MCP enabled + DCR (+CIMD) + scopes; Resource Indicators MUST
     include BOTH `https://mcp-dev.trxstat.com` AND `https://mcp-stage.trxstat.com`.
   - WorkOS PROD: same Connect config; Resource Indicator = `https://mcp.tradewave.ai`.
5. **Restart** appserver/Tara and the gateway in place if their own code changed. The immutable release script
   restarts MCP only after its candidate is staged. **Edge:** cloudflared routes for
   `api-*` / `mcp-*` / `developers-*` (+ prod `api.`/`mcp.`/`developers.tradewave.ai`).
6. **Stripe:** create the 4 API products/prices (Dev/Pro/Business) so paid API signups resolve (the gateway reads
   prices from product metadata). See `web/api_portal/create_api_products.py`.
7. **VERIFY (per env):**
   - BYOK: a `tw_live_` key -> `GET /v1/markets` 200.
   - The immutable deploy provisions a permanent dedicated Pro release verifier in
     `/etc/tradewave/mcp-verifier.env` (root:root `0600`, never loaded by systemd), validates its exact
     reserved DB binding with `provision-mcp-key.py --check-verifier`, and injects it only into the
     verifier child through `mcp-service-env.py exec-with-verifier`. Never copy the raw key into a
     command, shell variable, or the broad platform `secrets.env`. The contract gate must report the
     exact authenticated 17-tool contract, current `2025-11-25` plus compatible `2025-06-18` protocol,
     protected-resource discovery, WorkOS authorization-server metadata (DCR/CIMD, offline access, refresh,
     PKCE S256), and live `whoami`.
     The deploy also runs `verify_mcp_load.py --clients 20`; 20/20 independent sessions must pass.
     Confirm `systemctl show tradewave-mcpserver -p MemoryHigh -p MemoryMax` reports the reviewed
     768 MiB soft-pressure threshold and 1 GiB hard ceiling. MCP opportunity schemas/runtime must
     remain capped at 100 compact results (25 for `view=full`) with defaults of 10/25.
   - OAuth end-to-end: remove/re-add (or create a fresh) connector in ChatGPT/Claude at the BARE host URL after
     contract changes; connector tool catalogs are cached. WorkOS login -> a tool call
     returns TIER-CORRECT data. Leave it connected through an access-token expiry and prove refresh succeeds,
     then call `whoami` again (the user's `workos_sub` must map to `users.workos_user_id`, else 401).
   - Tara: in-app chat narrates a real card + drives the wave-viewer.

## MARKETING (Afshin asked; ship at deploy, not before)
- [ ] Write the consumer story: "Add TradeWave to ChatGPT or Claude, log in with your TradeWave account, ask for
      the edge." Files: `site/api_marketing/generate.py` (mcp page) + `site/content/learn_api/
      connect-an-ai-agent-mcp.md`. The connector URL is the BARE host (no /mcp). Deploy to prod only once live.

## CLEANUP / DEFERRED
- [ ] Remove dev test users: `mcp-test-pro@example.com`, `mcp-test-free@example.com` (DELETE FROM users ...).
- [ ] $99 WorkOS Custom Domain (branded `tradewave.ai` login) - AFTER it's proven useful (also fixes the deferred
      consent-screen branding).
- [ ] Enhancement (separate): "my portfolio" in chat - memory `enh_mcp_portfolio_tools`.

## Hard rules (do not violate)
dev -> staging -> verify -> prod (staging is the gate; never dev->prod). Author commands; the operator runs them
on the box. Run box git as `sudo -u flask`. `config.py` env-agnostic. No secrets in chat (box-to-box).
