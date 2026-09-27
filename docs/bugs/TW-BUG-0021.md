# TW-BUG-0021: CSP blocks Cloudflare Web Analytics

- Status: verified on dev
- Confidence: reproduced
- Priority: P2 - intended analytics beacon is blocked and loses measurement
- First observed / last updated: 2026-09-27 UTC
- Executor/session/claim time: Codex `/root/wave_info_dev`, 2026-09-27 UTC
- Authorization: fix the Cloudflare Web Analytics CSP failure on dev; no staging or production.

## User Impact and Reproduction

On the public dev site at `https://tw2-dev.trxstat.com/`, the edge-served HTML includes a Cloudflare Web Analytics `static.cloudflareinsights.com/beacon` script while the response CSP omits that host from `script-src`. With no `script-src-elem`, the browser falls back to `script-src` and blocks the script. The collection endpoint also needs `connect-src` permission. Expected: the intended analytics script loads and sends its beacon without weakening other CSP directives.

## Evidence and Investigation

At current main `57a846f7099680bff851383b4a1325e207f98c55`, `ops/nginx/snippets/security_headers.conf` and live dev `/etc/nginx/snippets/security_headers.conf` share the restrictive header. Public dev HTTP 200 HTML contains the beacon reference; public response header omits both Cloudflare origins. Existing staging bootstrap/hardening scripts already allow the exact Cloudflare origins. Cloudflare's [CSP guidance](https://developers.cloudflare.com/fundamentals/reference/policies-compliances/content-security-policies/) specifies `https://static.cloudflareinsights.com` for `script-src` and `https://cloudflareinsights.com` for `connect-src`.

## Acceptance and Regression Checks

- Candidate diff adds only `https://static.cloudflareinsights.com` to `script-src` and `https://cloudflareinsights.com` to `connect-src`; all other CSP directives and origins remain unchanged. `nginx -t` passed before and after installation.
- On 2026-09-27, a real headless Chrome visit to public `https://tw2-dev.trxstat.com/` returned HTTP 200, found the injected beacon script, loaded it from `static.cloudflareinsights.com` with HTTP 200, and recorded zero Cloudflare CSP violations or failed analytics requests. The public response header contained both exact origins. A collection request was not observed, so analytics delivery remains unverified. Browser probe used the public page and no authenticated data.
- No React/backend build was needed for this nginx-only repair. Staging/production not checked.

## Implementation and Handoff

Repository `afshinmoshrefi/tradewave-tw2`; task branch `codex/cloudflare-csp-dev-20260927`, pushed source commit `da34d7c7749cad7895f09995bd94a5d9d9caa10e`; clean task worktree `/home/tradewave-worktrees/cloudflare-csp-20260927`. Clean integration source `3cc7413eb9a0ea2a099068dad1e7039f5946edde`. Only `ops/nginx/snippets/security_headers.conf` changed. No frontend/backend build, migration or app service restart. Nginx reloaded on dev. Rollback copy: `/var/lib/tradewave/release-state/csp-before-3cc7413e.conf`; restore it to `/etc/nginx/snippets/security_headers.conf`, run `nginx -t`, then reload nginx. Next: owner review on dev; staging needs a separate release request.

## Environment Verification

Dev: verified on 2026-09-27 at `3cc7413eb9a0ea2a099068dad1e7039f5946edde` with active nginx snippet byte-identical to committed source and public browser proof above. Staging: not checked. Production: not checked.

## History

- 2026-09-27 UTC, Codex `/root/wave_info_dev`: Claimed authorized dev CSP repair at `f6552ade3e313c429a8260b1bd4b89bb6af194cb`; root cause reproduced in public dev HTML and header.
- 2026-09-27 UTC, Codex `/root/wave_info_dev`: Integrated at `3cc7413eb9a0ea2a099068dad1e7039f5946edde`, reloaded and verified live dev; staging and production remain unchanged.
