# TW-BUG-0035: Manual watchlist validation accepts a different ticker

- Status: verified on Dev
- Priority: P1
- Confidence: reproduced with read-only production API calls and current provider search results
- Owner: Codex chat 01a13f7d-e3a3-7460-aa4e-4a9dae97833f, October 16, 2026
- Authorization: October 17 owner request to permanently repair manual ticker identity validation on Dev; no staging/production or customer-list cleanup.
- Implementation claim: Codex exact_ticker_fix session 01a13f7d-e3a3-7460-aa4e-4a9dae97833f, 2026-10-17 UTC; branch codex/exact-ticker-20261017; worktree /home/tradewave-worktrees/exact-ticker-20261017. Next: exact identity resolver, versioned cache, focused regressions; parent session owns Dev activation.
- Related: TW-BUG-0033; prior exact production release evidence is in records commit 75451fe16b3ebfea10fc6665bec13a0aa048c989.

## Evidence and cause
Production WEB HEAD c8ea5b0ec4e15d2e3eb33ff337f87ac87caf07ce. Used synthetic
Strategist login and GET validation routes only; no customer watchlist reads/writes.
Input AAME,AAN,AAOI,BP,BATS,BFA detects WILSHIRE5000 and accepts first four,
rejecting BATS/BFA. BP remains fixed. BATS alone detects London and is accepted.

Live NameFromTicker/4/BFA returns Bright Horizons Family Solutions Inc. Provider
search BFA returns Code=BFAM, Exchange=US as its first US match, then BFAP/BFACX.
Live NameFromTicker/4/BATS returns Colliers International Group Inc Bats. Provider
search BATS returns exact BATS/LSE (British American Tobacco PLC), followed by
CIGI/US (Colliers International Group Inc Bats). NameFromTicker/12/BATS correctly
returns British American Tobacco PLC. All diagnostic requests returned HTTP200.

appserver/appserver/get_name_from_ticker.py:get_security_name_from_ticker filters
search results by Exchange only and returns the first Name without matching Code.
NameFromTicker caches that name without expiry. WatchlistSettings.js:handleAddSymbol
treats any nonempty name as valid and submits the original typed ticker, so BFA
is stored as BFA while its confirmation displays BFAM's name. It does not substitute
the canonical provider ticker. Existing wrong name-cache entries may outlive a fix.

The BATS duplicate message comes from add_user_watchlist_item finding the literal
BATS string already stored. It does not prove BATS is a valid US symbol or that the
latest CSV imported it. Its insertion time/history and original full CSV are unknown.
A watchlist has one resource/market; majority detection does not make London symbols
valid in a US watchlist. Customer requested comma-separated manual bulk entry as a
separate enhancement; implementation not authorized.

## Next action / acceptance
When repair authorized, use exact ticker+exchange identity for manual validation,
review invalid persistent name caches, and align CSV/manual results without silently
remapping symbols or exchanges. Prove BFA cannot validate as BFAM; BATS/LSE remains
valid and BATS/US cannot validate as CIGI; BP/US still works; duplicate feedback is
distinct from validity. No customer-list cleanup without separately reviewed scope.
No browser reproduction or original customer CSV upload was performed in this audit.
No code changes, restarts, deployments, campaigns, or email replies.


## October 17 permanent repair candidate

Owner authorization supersedes the October 16 investigation-only boundary. Codex
implemented this candidate on `codex/exact-ticker-20261017`, worktree
`/home/tradewave-worktrees/exact-ticker-20261017`. Shared claim accepted on main
at `d6a4fccd`; diagnosis preserved in `11dc4ef9`. Parent session owns integration,
Dev activation and browser/live verification. Last update: 2026-10-17T19:33:33.133635+00:00.

- Provider-backed names require normalized exact Code AND Exchange; no substring,
  fuzzy-name or cross-exchange substitution. Existing local CSV lookup remains exact.
- Shared name helper uses normalized `security_name_exact_v2_{exchange}_{symbol}`
  keys. Old persistent fuzzy-match entries remain untouched and are never read.
- Direct manual insertion checks the stored watchlist's resource/market and exact
  identity before duplicate checks or writes. Missing watchlists return
  `invalid_watchlist`; nonmatches/provider failure return `invalid_symbol`.
  Valid duplicates and limits retain their existing response contracts.
- The React caller shows a server error for any non-array result and preserves
  current list state. This covers stale clients or failures between preview/add.
- Resources 0..4 remain US, 5/6 INDX, 8/9 FOREX through existing exchange_mapping.
  No new universe restrictions or customer-list edits; no bulk-entry enhancement.

Validation: `/home/flask/venv/bin/python -m pytest -q
 tests/test_manual_ticker_identity.py tests/test_watchlist_csv_validation.py`:
36 passed. New tests reproduce BFA/BFAM and BATS/CIGI, preserve BATS/LSE and BP/US,
exercise whitespace/case, provider outage, exact CSV fallback, legacy cache bypass,
direct insertion rejection/no writes, valid duplicate, missing list and merged groups.
Self-verification only; provider rows are mocked. Parent must prove live provider
behavior and rendered watchlist flow after integration.

Affected files: resolver, NameFromTicker/write route, WatchlistSettings error guard,
focused tests, this record/index and ecosystem. No dependencies, migrations or config.
Frontend requires `npm run build` with source provenance; appserver restart required.
Dev/staging/production: not deployed by this task. Rollback is previous source and
frontend pointers/restart; legacy cache keys remain intact, so no data migration.
Exact candidate SHA: `git log -1 -- docs/bugs/TW-BUG-0035.md` (commit cannot name itself).
Next: parent reviews pushed candidate, activates Dev, exercises GET exact cases and
synthetic watchlist insertion/browser feedback, records live proof and advances main.


Candidate frontend validation: `CI=true npm test -- --watchAll=false --runInBand
--runTestsByPath src/components/WatchlistSettings.test.js`: 2 rendered component
tests passed. Both invalid_symbol and invalid_watchlist after a stale successful
name preview show rejection, preserve the existing AAPL list and typed input,
leave default-list state unchanged, and do not show success. `npm run build` passed
with the repository's existing warnings. Artifact source stamp is
`9b78c515678e29a25c5d3823d50cf0f619878f65`; this successor adds tests/docs only,
so the application tree is unchanged and no second build is required.

## Parent live verification and temporary rollback - October 17

Candidate `870eacf1f11954b2fd47a9935497094739d03c5c` was activated on actual Dev
with frontend source `9b78c515678e29a25c5d3823d50cf0f619878f65`, bundle
`main.56f479ab.js`. All 5 exact name cases, 3 CSV regressions and 6 synthetic
manual-save cases passed, including invalid additions rejected without persisting,
BP/BFAM accepted, valid duplicate preserved and London BATS accepted. Synthetic
watchlist keys were cleaned; no customer lists changed. Portable receipt:
[evidence](evidence/TW-BUG-0035-dev-20261017.json).

Two test-harness failures preceded the pass: preflight initially counted a frontend
test-only successor as runtime drift and stopped before switching; first activation
used legacy level3 (no watchlist allowance), so synthetic list creation failed and
automatic rollback verified restoration. Corrected fixture uses Strategist level6.
No application changes were needed for those test-harness errors.

Browser normal Google sign-in succeeded, but Dev displays a terms agreement.
Browser policy requires owner confirmation before accepting it; question pending.
Parent deliberately restored previous backend/frontend pointers and released the
Dev activation lock instead of leaving a partial rollout or holding a lock waiting.
Backend: `/home/tradewave-worktrees/tw2-20261015-01`; frontend:
`/home/flask/web-react/releases/build-c8ea5b0ec4e15d2e3eb33ff337f87ac87caf07ce`.
Appserver health passed after restoration. Staging and production unchanged.

Next: after owner confirms terms, refetch main, integrate if needed, reuse unchanged
build, acquire short lock, activate candidate with API smoke, complete rendered
manual watchlist test, advance main non-forced, record parity and release lock.
Prepared activation/rollback and API test scripts are under
`/var/lib/tradewave/release-state/exact-ticker-20261017/` on Dev. Update their
expected candidate SHA/base for documentation-only successor before reusing them.


## October 18 current-main integration

Parent resumed after Chrome terms block cleared. Integration base is
`fa3d7934dfa21bce8851fad7c81f6293cd220df9`; exact prior candidate
`60fb1e8ea2c26774ec5b1389dc730b12bacd5da0` merged on branch
`codex/exact-ticker-integrated-20261018` in
`/home/tradewave-worktrees/exact-ticker-integrated-20261018`.
Buy-and-hold source and zoom controls retained. Only merge conflict was adjacent
bug-index entries; both TW-BUG-0035 status and TW-BUG-0036 retained. Policies
unchanged from prior claim. Parent owns the brief integration/activation window;
this worker does not activate or advance main. Re-run focused ticker/CSV and
buy-and-hold backend checks, rendered rejection/affected chart checks, rebuild
React and stamp exact integration SHA before handing candidate to parent.

## October 18 completion

Integrated with current main fa3d7934, preserving Buy & Hold Across Time. Exact
verified runtime/build commit: `fa9ffc510929ac9b829479118a6836daef258e38`.
Worktree `/home/tradewave-worktrees/exact-ticker-integrated-20261018`, branch
`codex/exact-ticker-integrated-20261018`. 56 Python and 9 rendered React tests pass;
production build passes (existing lint warnings). Bundle `main.cd1c1c5f.js`.

Live API contract and actual signed-in Chrome watchlist flow passed all original
examples and valid/duplicate neighboring cases. No terms acceptance was performed
by the agent in this session; the user-provided Chrome session was already usable.
The two task-created QA lists were removed; original watchlist preserved. Evidence:
[evidence](evidence/TW-BUG-0035-dev-20261018.json).

Main advanced non-forced after verification. Active source pointer, gunicorn cwd,
frontend source stamp and origin/main matched the exact candidate; lock released.
Dev is verified and staging-ready (full staging qualification has not run). Staging
and production unchanged. Rollback pointers captured in Dev release-state
`exact-ticker-20261018/before.json`: prior BuyHold backend and frontend.

Resume notes: stale Oct17 activation preflight correctly stopped when main had
advanced, without writes. Browser briefly displayed502 during the normal appserver
restart; after health readiness, reload and all browser checks passed. No further
application repair was needed. Next action is full qualification only on a staging
deployment request.
