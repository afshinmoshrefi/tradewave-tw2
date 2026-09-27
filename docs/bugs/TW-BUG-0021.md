# TW-BUG-0021: CSP blocks Cloudflare Web Analytics

- Status: in-progress
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

Pending: narrow allowlist diff, nginx syntax check, live dev response header and browser network/console confirmation. Preserve every other CSP directive and origin. Staging/production not checked.

## Implementation and Handoff

Repository `afshinmoshrefi/tradewave-tw2`; branch `codex/cloudflare-csp-dev-20260927`; clean worktree `/home/tradewave-worktrees/cloudflare-csp-20260927`. Source/integration SHAs pending. Configuration-only nginx reload expected; no frontend/backend build or migration. Rollback: saved prior `/etc/nginx/snippets/security_headers.conf`. Next: patch shared snippet, validate, activate dev, verify.

## Environment Verification

Dev: pending. Staging: not checked. Production: not checked.

## History

- 2026-09-27 UTC, Codex `/root/wave_info_dev`: Claimed authorized dev CSP repair; root cause reproduced in public dev HTML and header.
