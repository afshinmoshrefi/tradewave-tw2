# TW-BUG-0033: Watchlist CSV rejects valid US ADRs

- Status: in-progress
- Priority: P2
- Confidence: reproduced on Dev using active detector and symbol provider
- Owner: Codex, chat 01a13f7d-e3a3-7460-aa4e-4a9dae97833f, 2026-10-15
- Authorization: fix safely on Dev; staging and production excluded.
- Branch: codex/watchlist-csv-validation-20261015
- Worktree: /home/tradewave-worktrees/watchlist-csv-validation-20261015

## Reproduction and cause
At baseline dc38f14bcbb3083396da9ca01698ac0b935b9701, input AAME,AAN,AAOI,BP detects
WILSHIRE 5000, accepts the first three, and rejects BP. Manual US name lookup returns
BP PLC ADR. BP is absent from all five local US constituent CSVs, so this is not
merely a stale group cache. CSV detection checks index membership whereas manual
addition queries the broader exchange. No customer watchlist was changed during diagnosis.

## Executable plan
1. Preserve the existing winning-group selection and resource identity. Supplement only
   unmatched symbols when that selected resource maps to US.
2. Add a bounded, cached full-US provider catalog lookup with exact Code membership.
   Never add ADRs to index constituent CSVs, guess another exchange, accept fuzzy search
   matches, alter NameFromTicker, or touch calculation code.
3. Preserve detection response fields and symbol order. Provider validation failure must
   return an explicit error, blocking partial import rather than mislabeling symbols.
4. Add focused unit coverage for ADR recovery, invalid symbols, exchange boundaries,
   unchanged existing/non-US imports, cache reuse, ordering and provider failures.
5. Commit/push candidate; acquire the short Dev activation lock only after tests.
   Preserve current backend/frontend pointers, check frontend next-start path, activate
   backend only, and verify authenticated live detection plus manual BP lookup.
6. Non-forced main update and application-tree proof after live checks. On any failed
   activation/smoke/main push, restore previous backend pointer and restart affected
   appserver. Retain unchanged frontend; no React build or database migration.

## Acceptance and limits
- US sample above accepts BP and a bogus ticker remains invalid.
- Existing imports and non-US market selection retain their prior semantics.
- Authentication, watchlist limits/storage, and index/chart math remain unchanged.
- Original customer CSV was not attached; use a minimal representative fixture.
- Browser end-to-end import requires signed-in session; backend live contract is required.
- Current tests, final SHA, deployment evidence and rollback pointers: pending.
