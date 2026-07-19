# API / MCP Deployment - Action Items & Handoff

A pick-up-able checklist to take the API/MCP product (incl. Tara + the consumer OAuth connect) from
"working on dev" to live on staging + prod. Authored for the operator (Afshin) - per the hard rules,
NEVER touch staging/prod directly; the operator runs the commands. Last updated 2026-06-06.

Control docs (the detail): `docs/MCP_OAUTH_INTEGRATION.md`, `docs/TARA_GATEWAY_INTEGRATION.md`,
`ops/OPERATIONS.md`, `ops/PROD_CUTOVER.md`, `ops/bootstrap_api_services.sh`,
`ops/assemble_developer_portal.sh`, `ops/SPLIT_GATEWAY_TO_OWN_BOX.md`, `api/BUILD_STATE.md`.
Memory: `reference_mcp_api_knowhow`, `project_mcp_consumer_oauth_goal`, `project_tara_gateway_client`.

## Status snapshot
- BUILT + verified on DEV, and the MCP consumer OAuth connect is CONNECTED end-to-end from ChatGPT/Claude
  (via the WorkOS STAGING env). Nothing is on staging/prod yet.
- Scope built this session: gateway tier-resolution for WorkOS users, the MCP resource-server (WorkOS JWT
  verifier, streamable-http, root-mount), Tara gateway client (Phase 1 + 2), the e2e-review fixes,
  ML-score table filter, slim dev-portal nav, Liquid name-drop removal.

## GIT STATE - read this first (it's non-obvious)
- Current branch: **`feature/affiliate-admin`** (NOT `feature/api-mcp`; the name drifted). HEAD is **17 commits
  ahead of `main`**, and the branch is **NOT pushed** (no remote tracking) and **NOT merged**.
- The branch has a **parallel affiliate session's work interleaved** (commit `cb0e5fa` + UNCOMMITTED:
  `web/affiliate_service.py`, `web/app.py`, `tests/test_affiliate.py`, `docs/AFFILIATE_AGREEMENT.md`,
  `site/generate_text_pages.py`, `site/templates/index-dark-blue.html`, `docs/TRADEWAVE_ECOSYSTEM.md`).
  **Do NOT commit or disturb those** when doing the API/MCP deploy - they belong to that session.
- Key API/MCP commits (all on this branch): `bf1f014` (api+mcp feature expansion + Tara P1), `62d3c13`
  (Tara P2), `0f63b5c` (relocatable deploy), `2a3be5e` (review fixes), `63f3830` (ML filter), `9fe79f5`
  (slim nav), `4b42335` (Liquid removal), `53a5a1d`/`45e7748`/`c231fa3`/`0f43333` (MCP OAuth).
- DECISION NEEDED: how to land this on main (clean up the branch name / cherry-pick API-MCP vs affiliate, or
  merge the whole branch once affiliate is done). Coordinate with the affiliate session via conversation.md.

## Pre-deploy DECISIONS (from the e2e review - `/home/afshin/TRADEWAVE_APP_REVIEW_2026-06-02.md`)
- [ ] Checkout CSRF (`web/app.py` `/api/stripe/create-checkout` is `@csrf.exempt`) - low blast radius; needs the
      live billing form tested before changing. Decide: fix now or note as accepted.
- [x] `SERVICE_API_KEY` is sent only in the `X-Service-Key` header to `POST /login/api`; tracked callers do not place it in a request path.
- [ ] ML-endpoint rate-limit decorators (`appserver.py` MLScoreBatch/Pending) - pick a per-tier limit.
- [ ] SEO: `ENABLE_SEO` now prod-only (env-driven) - confirm prod build flips it; the assemble guard rejects
      stale dev URLs.

## DEPLOY - run for STAGING first, verify, THEN prod (never skip staging)
For EACH env (staging, then prod):

1. **Code out.** Get this branch's code on the box (per `ops/deploy.sh {staging|prod}` once landed on main, or
   the branch). `pip install -r requirements.txt` + `-r requirements-api.txt`. React (Tara Phase 2 frontend) =
   symlink-swap deploy (`ops/deploy.sh` / the react release step). Reassemble the dev portal:
   `sudo bash ops/assemble_developer_portal.sh` (TW2_ENV set so the URL guard + SEO flip apply).
2. **API/MCP services.** If the box has no gateway/MCP yet: `sudo bash ops/bootstrap_api_services.sh`. Install the
   updated `tradewave-mcpserver.service` (now defaults `TW2_MCP_TRANSPORT=streamable-http`): `daemon-reload`.
3. **secrets.env (per env) - add/confirm:**
   - Tara: `TARA_GATEWAY_KEY` (run `venv-api/bin/python -m apiserver.provision_chatbot_key`), `TW2_GATEWAY_URL`
     (the gateway base, `http://127.0.0.1:8088/v1` while co-located), optionally `APPSERVER_CORS_ORIGINS`.
   - MCP-OAuth: `MCP_GATEWAY_KEY` (run `venv-api/bin/python -m apiserver.provision_mcp_key`),
     `WORKOS_AUTHKIT_DOMAIN` (already set for web login - reuse), `TW2_MCP_PUBLIC_URL` (the env's MCP host:
     `https://mcp-stage.trxstat.com` / `https://mcp.tradewave.ai`), `TW2_MCP_TRANSPORT=streamable-http`.
4. **WorkOS dashboard (per WorkOS env).** WorkOS has only STAGING + PROD. The dev + staging BOXES both ride WorkOS
   STAGING; the prod box rides WorkOS PROD.
   - WorkOS STAGING: Connect -> Configuration -> MCP enabled + DCR (+CIMD) + scopes; Resource Indicators MUST
     include BOTH `https://mcp-dev.trxstat.com` AND `https://mcp-stage.trxstat.com`.
   - WorkOS PROD: same Connect config; Resource Indicator = `https://mcp.tradewave.ai`.
5. **Restart** appserver (Tara), apiserver (gateway), mcpserver. **Edge:** cloudflared routes for
   `api-*` / `mcp-*` / `developers-*` (+ prod `api.`/`mcp.`/`developers.tradewave.ai`).
6. **Stripe:** create the 3 paid API products with their monthly prices (monthly only - no annual)
   (Dev/Pro/Business) so paid API signups resolve (the gateway reads prices from product metadata).
   See `web/api_portal/create_api_products.py`.
7. **VERIFY (per env):**
   - BYOK: a `tw_live_` key -> `GET /v1/markets` 200; MCP lists 17 tools (6 flagship + 11 primitives).
   - Discovery: `POST https://<mcp-host>/` -> 401 + WWW-Authenticate(resource_metadata); `/.well-known/
     oauth-protected-resource` 200; the AuthKit `/.well-known/oauth-authorization-server` advertises
     `registration_endpoint`; `POST <authkit>/oauth2/register` returns a client_id (DCR on).
   - OAuth end-to-end: add the connector in ChatGPT/Claude at the BARE host URL -> WorkOS login -> a tool call
     returns TIER-CORRECT data (the user's `workos_sub` must map to a `users.workos_user_id` row, else 401).
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
