# TW2 Production Cutover Runbook

The domain cutover of `tradewave.ai` from TW1 (live, ~30 paying users) to TW2.

**Scope of the cutover session = the flip ONLY (Phase 1 → 2 → 3).**
Phase 0 (build TW2 prod on the `tw2-prod.trxstat.com` placeholder) is NOT
done in the cutover session — it is executed ahead of time in a general
build session via the parameterized staging playbook (`ops/staging/*.sh`
with `prod_target.env`). By the time the cutover session runs, TW2 prod is
already fully built, validated and soaked on the placeholder; the only
remaining work is the irreversible domain flip and its rollback path.

Execute the cutover in a **fresh, focused session** with this file open.
TW1 stays fully running and untouched until TW2 is proven on the live domain.

Everything not domain-related (build, secrets, services, crons, hardening,
bulletproofing) is the staging playbook: run `ops/staging/*.sh` against the
prod boxes — see `project_tw2_staging_deployment.md` memory + `ops/OPERATIONS.md`.
This file is ONLY the domain cutover, because that's the only irreversible,
TW1-is-live part.

---

## STEP 0 — Determine how `tradewave.ai` is exposed for TW1 today (DO THIS FIRST)

The flip mechanics and rollback value depend entirely on this. From any box:

```
dig +short tradewave.ai
dig +short tradewave.ai CNAME
```

- **Cloudflare-proxied A record** (resolves to 104.x / 172.x Cloudflare IPs, no CNAME): TW1 origin is an A record behind Cloudflare. Flip = change that A record (or replace with the TW2 tunnel CNAME). **Save the exact A value(s) — that's the rollback target.**
- **cloudflared tunnel** (CNAME → `<uuid>.cfargotunnel.com`): TW1 is already on a tunnel. Flip = repoint the CNAME to TW2's tunnel UUID. **Save TW1's tunnel UUID.**
- **Direct/un-proxied A** (resolves to a real origin IP): least likely; flip = A→TW2-tunnel-CNAME, but you also lose Cloudflare edge TLS continuity — verify Cloudflare proxy is on for the record post-flip.

Record the finding + exact rollback value at the top of the cutover session before touching anything.

---

## PHASE 0 — Build TW2 prod on the placeholder (DONE in the build session, NOT the cutover session)

Bring prod-web + prod-app up on **`tw2-prod.trxstat.com`** (off-brand, no
SEO/leak risk, tunnel is hostname-agnostic so this doesn't constrain the flip).
Run the staging playbook against the prod boxes with prod deltas:

- 2 CPU / 2 GB per box; **full ~39 GB `/home/flask/data/` on BOTH tiers** (web runs ticker/scorecard/home-opportunities generators that read local CSVs) + `data_updater` cron.
- Stripe **live** keys; **prod WorkOS environment** (separate from staging).
- DB seed: real TW1-prod migration (lazy dual-hash phpass→argon2 for payers, hard-cut + reset email for free users — final spec per `project_tw2_auth_architecture` memory).
- Validate end-to-end on `tw2-prod.trxstat.com`: sign-in, /app, opp data, Stripe live checkout (use a real card you refund), SMN, ticker pages, the bulletproof pass (`make_bulletproof.sh`).

Do not proceed to Phase 1 until `tw2-prod.trxstat.com` is fully green and has soaked.

---

## PHASE 1 — Pre-cutover (days ahead; TW1 untouched and serving)

Each of these is safe while TW1 still owns `tradewave.ai`:

1. **Lower `tradewave.ai` DNS TTL to 60s.** Single most important step. Must be done DAYS early — the TTL reduction itself propagates at the *old* TTL. Without this, a broken flip = up to old-TTL of broken prod and slow rollback.
2. **Add `tradewave.ai` to the TW2 prod tunnel ingress** (`/etc/cloudflared/config.yml` on prod-web, `hostname: tradewave.ai → http://localhost:80`) and `systemctl restart cloudflared`. **Do NOT route DNS yet.** Tunnel is now ready to serve the domain the instant DNS points at it.
3. **WorkOS prod env:** add `https://tradewave.ai/auth/callback` to AuthKit redirect URIs (alongside the placeholder's). Harmless to TW1; sign-in is dead in the gap if skipped.
4. **Stripe:** create the TW2 prod webhook endpoint pointed at the TW2 prod hostname; subscribe to `checkout.session.completed` + `customer.subscription.*`; verify with test events. It now receives before AND after the flip — no gap; `StripeEvent` ledger dedupes any overlap with TW1's webhook.
5. **Pre-seed the TW2 `users` table from a fresh TW1-prod DB dump.** At the flip every active TW1 session dies (different auth system) and re-auths through WorkOS simultaneously. Matched-by-email in `lazy_create_user` is cheap; a mass create-storm is not. Pre-seeding makes first sign-in a match, not a create.
6. Optional: a maintenance/notice banner ready to surface, given the simultaneous re-auth.

---

## PHASE 2 — Cutover (minutes)

1. **Final delta user sync** from TW1 prod (catch signups since the Phase-1 pre-seed).
2. **Flip the one `tradewave.ai` DNS record** to the TW2 tunnel CNAME (`<tw2-prod-tunnel-uuid>.cfargotunnel.com`, proxied). This is the atomic switch — a record can't be both TW1's value and TW2's CNAME at once.
3. **Purge the Cloudflare cache for the zone immediately** — or the edge serves stale TW1 HTML/JS over the new origin.
4. **Re-point the ~4 box config values** on prod-web (these are placeholder-scoped, not just DNS): `TW2_DOMAIN_ROOT`, `TW2_PUBLIC_HOST`, `TW2_AUTH_CALLBACK_URL` in `/etc/tradewave/secrets.env`; nginx `server_name`. Restart `tradewave-web`, reload nginx. (App box: **no changes** — appserver is on `.trxstat.com` and uses JWT aud/iss, not the web host.)
5. **Regenerate static content** so canonical/og:url/sitemaps carry `tradewave.ai`: re-run the home/scorecard/ticker/insights generators (or trigger the crons). **Also regenerate SMN pages** — neither is on cron: `/home/flask/smn/generate_security_pages.py` (rewrites `/var/www/smn/markets/*.html` with the new TradeWave link) and `build_home()` from `rebuild_news_home.py` (rewrites `/var/www/smn/index.html`). The SMN "TradeWave" link is now driven by `config.tw2_public_url` which derives from `TW2_PUBLIC_HOST` (repointed in Step 4) — so this is just a re-stamp, no env edit needed. Already-published SMN articles in `/var/www/smn/articles/.../` still carry the old chrome URL; bulk re-chrome with `_inject_site_wrapper(html, ..., force=True)` if a full content sweep is wanted. The React build is env-agnostic — **no rebuild**.
6. **Smoke on `https://tradewave.ai`:** sign-in → WorkOS → super_admin for afshin; /app loads + opp data; live Stripe checkout + webhook receipt; SMN; ticker pages; `tail -f /var/log/tradewave/*.log` clean.

---

## PHASE 3 — Rollback (instant, if Phase 2 smoke fails)

Works ONLY because TTL is already 60s and TW1 was never decommissioned:

1. Restore the saved `tradewave.ai` DNS record value (from STEP 0).
2. Purge Cloudflare cache for the zone.
3. TW1 resumes serving within ~60s. Investigate TW2 on the placeholder, never on the live domain.

There is no partial rollback — it's the one DNS record + cache purge, same as the flip.

---

## PHASE 4 — Decommission TW1 (only after soak)

Keep TW1 fully running, untouched, as the rollback target for the agreed soak
(days, not hours — at least one full Stripe billing-event cycle + a weekend).
Only after TW2 is proven on the live domain: stop TW1 services, snapshot, then
release. Remove the placeholder (`tw2-prod.trxstat.com`) WorkOS callback +
tunnel ingress + DNS after decommission.

---

## API/MCP go-live (SEPARATE, post-cutover - not part of the domain flip)

The v2 public product (gateway + MCP + developer portal) ships AFTER the domain cutover
has soaked and the billing/auth freeze is lifted - it is additive to the appserver and does
NOT touch the `tradewave.ai` flip. Full deploy/restart detail: `ops/OPERATIONS.md` "API/MCP
deploy + restart"; map: `docs/TRADEWAVE_ECOSYSTEM.md` §7A/§7B; contract: `api/SIGNALCARD_SPEC.md`.
**SIGNALS-ONLY** (no raw prices). Build prod against `tw2-prod.trxstat.com` first, soak, then add
the public hostnames. Checklist:

1. **Schema** - apply the additive `apiserver/schema.sql` migration to prod Postgres
   (`api_keys`, `api_usage_daily`, `users.api_tier`). Verify all three exist; back up first.
2. **Secrets** - set `TW2_API_PUBLIC_HOST=api.tradewave.ai`,
   `TW2_MCP_PUBLIC_HOST=mcp.tradewave.ai`, `TW2_DEVELOPERS_PUBLIC_HOST=developers.tradewave.ai`
   in `/etc/tradewave/secrets.env` on the relevant box(es).
3. **venv-api + units** - run `ops/bootstrap_api_services.sh` on the app box (builds
   `/home/flask/venv-api`, installs `tradewave-apiserver` :8088 + `tradewave-mcpserver` :9090,
   nginx `api`/`mcp`/`developers` server blocks). Confirm `TRADEWAVE_API_KEY` is UNSET on the
   MCP unit (BYOK). `systemctl enable --now tradewave-apiserver tradewave-mcpserver`.
4. **Tunnels** - add the `api.` / `mcp.` / `developers.tradewave.ai` ingress entries (BEFORE
   the 404 catch-all), add the three Cloudflare DNS tunnel records, `systemctl restart
   cloudflared`, then `nginx -t && systemctl reload nginx`.
5. **Stripe products** - run `web/api_portal/create_api_products.py` in **LIVE** mode (prod
   uses live Stripe keys; do NOT seed live with test keys or vice versa). Create the prod API
   webhook if the API tier write needs its own endpoint; verify with a test event.
6. **Assemble the portal** - run `ops/assemble_developer_portal.sh` (generators + rsync to
   `/var/www/developers/`); the pages bake the prod hostnames, so this must run AFTER step 2.
7. **Smoke** (use a real key you create + revoke): `https://api.tradewave.ai/v1/markets`,
   `https://mcp.tradewave.ai/sse` opens, `https://developers.tradewave.ai/` + `/docs` +
   `/.well-known/mcp.json` serve; confirm responses are **signals-only (no raw price fields)**;
   one paid API checkout end-to-end; `tail -f /var/log/tradewave/*.log` clean.

Rollback is non-destructive: stop the two units + remove the three ingress/DNS records; the
appserver and web tier are untouched.

---

## What is scripted vs manual

`ops/cutover_repoint.sh` does the **box-side** mechanics only (Phase 2 steps
4-6: re-point secrets, nginx server_name, cloudflared ingress, restart,
regenerate content, smoke). It deliberately does NOT touch DNS, Cloudflare
cache, WorkOS, or Stripe — those are dashboard/API actions an operator does
deliberately, with the runbook open, because they're the irreversible ones.
The DNS flip + cache purge are single, conscious manual actions by design.
