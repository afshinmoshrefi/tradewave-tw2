# TW-BUG-0033: Watchlist CSV rejects valid US ADRs

- Status: verified on Dev
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
- Eleven focused tests passed; Python compilation and diff whitespace checks passed.
- Browser upload/save was not exercised because the browser was signed out. The actual
  authenticated public Dev detection endpoint was exercised; no customer watchlist was changed.

## Implementation and live verification
- Source commit: 719a07851feea6d938530c31c6552e8ca1cc07a3, pushed to main and task branch.
- Verified at 2026-10-15T13:18:10Z with normal service-account authentication.
- Active backend: /home/tradewave-worktrees/watchlist-csv-validation-20261015.
- Previous backend: /home/tradewave-worktrees/securities-menu-tip-dev-20261010.
- Unchanged frontend: /home/flask/web-react/releases/build-906bd7b6d578c63076d88b3fa9f5e62bac16185b.
- Tests: sudo -u flask /home/flask/venv/bin/python3 -B -m pytest tests/test_watchlist_csv_validation.py -q --disable-warnings.
- Live: BP accepted in the Wilshire-detected fixture; bogus ticker rejected; AAPL/MSFT
  retained prior result; BP-only retained London selection; manual BP returned BP PLC ADR.
  Public https://tw2-dev.trxstat.com/appserver route returned BP among valid_symbols.
- Full sanitized inputs/results: [Dev receipt](evidence/TW-BUG-0033/dev-verification.json).
- First catalog retrieval plus validation took 1.637 seconds; subsequent US validation
  using the cache took 0.093 seconds in this smoke (not a performance guarantee).
- Only appserver restarted. Frontend next-start readiness passed; pointer stayed unchanged.
- Rollback: under the Dev activation lock, atomically restore .tw2-app-current to the
  previous backend above and restart tradewave-appserver; verify previous behavior and
  frontend pointer. Do not use this old pointer over a later unrelated deployment.
- Staging and production: not deployed by this task.
- Follow-up: test the customer's full CSV when available. A BP-only or genuinely mixed-market
  file still follows existing market detection; this fix does not guess listing identity.
  Any staging promotion requires a separate request and release qualification.


## October 16 follow-up investigation
BP remains accepted in live production mixed-US input. New BFA/BATS inconsistency
is traced to fuzzy manual-name validation, recorded separately in [TW-BUG-0035](TW-BUG-0035.md).
The prior CSV exact-US-catalog repair does not validate a London listing as US.
