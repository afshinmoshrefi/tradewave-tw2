# TW-BUG-0031: SMN chart images omit the security identity and use unreadably small text

- Status: in-progress
- Confidence: reproduced
- Priority: P2. Every SMN daily article ships charts that do not say which security they show and whose text renders at roughly 7-11 CSS px in the article column. Images shared, saved or viewed out of context lose their meaning.
- First observed / last updated: 2026-10-09 23:10 UTC (reported by Afshin)
- Executor/session/claim time: Claude Code (Opus 5.5), session 6dd54b04-ad02-49d6-9209-84d5b2326727, claimed 2026-10-09 23:15 UTC
- Authorization: Afshin, 2026-10-09: "fix the smn dev". Scope: SMN chart presentation only (`blog/engine_seasonal.py::render_price`, `blog/visual_charts.py`, `blog/chartkit.py` text sizing) plus Dev activation. Production is read-only. Exclusions: no TradeWave engine math, projection normalization, statistics, or published-revision rewrites.

## User Impact and Reproduction

Environment: SMN main/Dev runtime `185af5cbec060a41958650c1bc709cfc68f0946d` (`/opt/smn-daily/current`). Evidence edition: `/var/tmp/smn-production-native-d69c46e/run-32bd869/web/editions/2026-10-05/{SPY,NVDA,...}/assets` on 192.168.1.180.

1. Open any native seasonal article (for example SPY, October 5).
2. `tradewave-price_projection.png` / `-mobile.png`: no title, symbol, security name, window or source inside the image; plain DejaVu 11 pt at 160 dpi on a 1600 px canvas (legend 8-9 pt), about 9-11 CSS px in the 740 px column.
3. `business-context-{desktop,mobile}.png` (visual_charts): no title, subject, security or source inside the image.
4. `tradewave-bars*.png` desktop: symbol and name present, but tick/year/source text is about 8-9 CSS px; the mobile variant omits the security name and its source line is about 7 CSS px.

Expected: every chart image identifies symbol and security name, states what it shows and its source, and keeps text at or above about 12 CSS px at article width on desktop and phone.

## Evidence and Investigation

- `render_price` has been plain matplotlib since `354c7d2` (2026-09-10); `visual_charts.render_chart` puts the title only in HTML.
- chartkit frame sizes are tuned for a 1280 px canvas at DPI 100 and the article column displays it at about 0.58x.
- The projection overlay's normalized scaling is the owner-approved design (`docs/TRADEWAVE_ECOSYSTEM.md`, owner clarification 2026-09-12). It is not part of this bug and will not be changed. Only labels change.

## Acceptance and Regression Checks

Pending: focused chartkit/engine_seasonal/visual tests, rendered desktop/mobile images for real engine inputs, Dev activation, and a live check.

## Implementation and Handoff

SMN repo branch `claude/smn-chart-identity-20261009`, worktree `/opt/smn-worktrees/smn-chart-identity-20261009` on 192.168.1.180. Commits pending.

## Environment Verification

Dev: pending. Staging: not applicable to SMN. Production: not checked; read-only.

## History

- 2026-10-09 23:15 UTC, Claude Code session 6dd54b04: claimed and reproduced on Oct 5 edition assets. Next: implement branded/readable renderers, test, activate on Dev.
