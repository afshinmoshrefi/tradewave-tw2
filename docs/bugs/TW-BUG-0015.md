# TW-BUG-0015: Median labels overlap seasonal bars

- Status: verified on Dev
- Priority: P2
- Confidence: reproduced in owner screenshots (GC, QQQ, SPY)
- Executor/session: Codex smn-chart-labels-20260923
- Claimed: 2026-09-23T15:10:26.538058+00:00
- Authorization: owner requests unreadable chart labels fixed with professional appearance; Dev only.
- SMN branch/worktree: codex/smn-chart-labels-20260923; Windows orchestrator/smn-chart-labels-20260923, from7240b1a.

## Cause and acceptance
chartkit.record_bars right-aligns the median annotation near the final bar, causing its text to extend left into the bar. Fix presentation only: a tidy reserved right-hand gutter inside the frame, aligned with the median line, with rendered text extents proving no collision or clipping. Preserve every engine value, study, bar and financial calculation. Verify supplied GC/QQQ/SPY cases and mobile behavior; repair affected Dev assets with retained article prose/heroes/data. Production unchanged.

## Coordination
Claude lean daily candidate changes reviewer/effort/orchestration/layout checks but does not edit chartkit. Do not merge or override that experimental branch. This task does not remove daily visual checks or change model settings. User questions their value; broader workflow decision remains separate.

## Next
Focused renderer correction and examples, regression verification, exact-source Dev asset repair and shared completion evidence. Prior visual approval missed this defect; do not treat past approvals as proof of absence.

## Verified repair - 2026-09-23T16:19:22.748186+00:00

SMN main/live source `c7e56157acf097b8a47bc47abcf6b3cfb8dbcea4` fixes `blog/chartkit.py` and adds focused geometry regressions in `blog/tests/test_chartkit.py`. The 11-point median label is measured with the actual renderer, placed in a reserved right gutter and checked against the last bar. If that space would crowd observations, a dashed-line key below the subtitle is used. Native chart URLs now include their image hash so browsers and the CDN load repaired images. The first activation was rolled back after actual screenshots exposed cached old charts despite cache-busted hash probes. The second candidate versions the actual reader URLs; original prose is verified unchanged by stripping only those query strings. The original failed receipt/screenshots remain preserved. No financial calculation, model setting or daily review gate changed. All 25 chartkit tests and10 engine fidelity/cache-version tests pass, including 6/7 bars, positive/negative medians, caps and a long-label fallback.

Presentation-only replay of the twelve September22/23 articles changed 48 desktop bar/range PNGs. Retained engine cards, values, observations, price overlays, mobile charts, article prose and heroes are unchanged. Original daily receipts/results are preserved; no new writer/reviewer jobs or paid API calls.24 desktop/mobile article layouts passed, all229 scoped public files matched expected hashes, and all36 archive articles remain. Actual repaired chart images and live GC/QQQ/SPY captures were inspected.653 other existing public files were byte-verified unchanged during candidate preparation.

Exact Dev web pointer: `/var/www/smn-dev-recovery/chart-labels-20260923-c7e56157ac`; code pointer: `/var/lib/tradewave/smn-editorial/releases/c7e56157acf097b8a47bc47abcf6b3cfb8dbcea4`. State/proof and rollback: `/var/lib/tradewave/release-state/smn-chart-labels-20260923-c7e56157ac`; previous web `/var/www/smn-dev-recovery/20260923-7240b1a992`, previous code `/var/lib/tradewave/smn-editorial/releases/7240b1a992d18340b312feea4d1735d8e2e111c4`. The existing guarded installer activate/rollback/finalize functions handled the short Dev lock. A scoped maintenance package overlays only the48 named images onto an immutable copy of the current site; `chart-repair-provenance.json` binds the new renderer and old/new asset hashes without relabeling original article-writing provenance. Production and .180 unchanged.

Private reproducible replay, source, manifests, scripts, screenshots and visual proofs are archived on .176 at `/var/lib/tradewave/smn-editorial/audits/20260923/chart-label-repair-v2-audit.tar.gz`; corresponding local directory is `smn-review-20260923/chart-label-repair-v2` under the Windows orchestrator. Source branch `codex/smn-chart-labels-20260923` is pushed and clean. Next: normal daily workflow fetches this renderer; model/effort optimization remains a separate pending peer review.
