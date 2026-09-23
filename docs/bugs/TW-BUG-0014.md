# TW-BUG-0014: SMN comparison disclosure assumes twenty observed years

- Status: verified on Dev
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

## Repair and handoff
2026-09-23T11:47:18.762086+00:00: SMN branch codex/smn-comparison-disclosure-20260923 contains clean pushed fix 7240b1a992d18340b312feea4d1735d8e2e111c4. Only the incorrect fixed sample-size disclosure changed; the table and engine values remain unchanged. Ten focused tests pass, including shorter available history. Five new articles passed independent review and actual desktop/mobile inspection using this source. SHOP original prose is byte-identical and its protected HTML disclosure is corrected, but its existing failed reviewer cannot be reused as approval. All12 allowed daily jobs are consumed. A request for one additional independent review is pending; no silent cap exception. No code or article deployment has occurred; verifiedSeptember22 Dev remains intact. Next action and private archive in [run evidence](../tasks/evidence/TW-TASK-0005-run-20260923.json).

## Verified Dev completion
2026-09-23T11:55:59.913746+00:00: Owner explicitly approved one extra reviewer call. All six exact production subjects SHOP, PAYX, WMT, HPQ, CTAS and NDX are live at https://smn-dev.trxstat.com/editions/2026-09-23/ . Source/main/live 7240b1a992d18340b312feea4d1735d8e2e111c4 corrects the protected sample disclosure without changing TradeWave values or SHOP prose. Total13 saved-ChatGPT Astra xhigh jobs (6 writers,7 reviewers), no paid API fallback. Ten focused tests,12 local and12 live layouts,156 public hashes,36 retained articles and older archive search passed. Required article and landing captures were actually inspected. Dev lock released. Previous web20260922-c2beec6778 and codec2beec6778c89592a8e12d3ac4266d8aea9e0ac0 retained for rollback. CanonicalSeptember23 live_verified receipt and recovery-resolution prevent regeneration while preserving failed evidence. Worker checkout smn-resilience-integrated-20260922 is clean and fast-forwarded; daily schedule/default12-job cap unchanged. This was a one-day approved exception. Production unchanged. [Completion evidence](../tasks/evidence/TW-TASK-0005-completion-20260923.json).
