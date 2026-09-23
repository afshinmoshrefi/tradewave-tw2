# TW-BUG-0014: SMN comparison disclosure assumes twenty observed years

- Status: in-progress
- Priority: P2
- Confidence: reproduced
- Executor/session: Codex smn-daily-run-20260923
- Claim: 2026-09-23T11:14:27.659898+00:00
- Authorization: scheduled Dev-only bounded recovery; production read-only.
- SMN branch/worktree: codex/smn-comparison-disclosure-20260923, Windows orchestrator/smn-comparison-disclosure-20260923, base277ba7ddb45d2148186d52d4d5f3761b8ca9c3e3.

## Reproduction and cause
September23 SHOP's correct original8-year study contains2018-2025; the engine response to a20-year request contains only2016-2025. blog/engine_seasonal.py comparison_html hardcodes "The ten-year sample is included in the twenty-year sample." The actual table and article are correct, but the protected explanatory sentence misstates observed history. The independent Astra reviewer held finalization. No engine calculation defect or article-writer defect is established.

## Acceptance and next step
Replace the fixed-size claim with accurate observed-history/overlap guidance while preserving engine values, studies and table. Focused regression and same-data re-render verification; preserve original writer and failed reviewer receipts. Actual independent re-review is required before publication. Only2 of12 authorized new jobs have been used, but completing6 articles plus the necessary replacement review would require13; do not silently exceed the daily cap. Continue recovery and collect the concrete remaining decision if necessary.

## Evidence and state
Local immutable root smn-review-20260921/production-style/2026-09-23; SHOP review output states the exact protected-text failure and approves otherwise strong article. Daily state failed_needs_review at finalize. Dev remains the verifiedSeptember22 archive. Production and TradeWave engine unchanged. No peer overlap found in TW-TASK-0006; Codex owns this newly discovered runtime defect, not Claude's unspecified efficiency assignment.
