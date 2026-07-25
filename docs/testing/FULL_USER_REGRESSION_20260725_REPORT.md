# TradeWave Full User-Facing Regression Report — 2026-07-25

## Executive decision

**Dev result:** The repaired build is deployed and functioning on `192.168.1.176`.

**Release decision:** **Not ready for staging or production yet.** The user-facing regression found and repaired 14 product defects, and the resulting automated suites are green. Release is still blocked by:

1. The configured EODHD market-data credential returns HTTP 401, so routine price refreshes are not reliable.
2. The Wave Viewer is clipped or unusable at tested narrow/tablet/mobile-width desktop viewports, and one viewport transition left the opportunity pane in a stale loading state until the market was reselected.
3. `CI=true npm run build` promotes the repository's existing lint warnings to errors. The normal production build succeeds, but the CI release gate is not clean.

Before production qualification, also close the visible-browser evidence gaps for watchlist CSV upload, chart CSV download, and browser back/forward recovery described below.

## Scope and safety

- Targeted only `192.168.1.176` and `https://tw2-dev.trxstat.com`.
- Used the existing signed-in, visible Chrome session as the authoritative interaction surface.
- Exercised user-facing features only; no admin screens.
- Did not touch `.180`, staging, or production.
- Did not place broker orders or submit calendar events, email/SMS, payments, subscriptions, lead forms, social posts, or API-key changes.
- WorkOS/auth configuration was not disabled or changed. The signed-in session survived reloads and site/app navigation.
- All test records were prefixed `TW-QA-20260725`, tracked, removed, and checked for absence.

## Deployed `.176` state

| Item | Value |
|---|---|
| Branch | `codex/full-user-regression-20260725` |
| Application code head | `929f8180` — Guard portfolio deletion while count loads |
| Frontend target | `/home/flask/web-react/build-full-user-regression-20260725-929f8180` |
| Frontend symlink | `/home/flask/web-react/build` |
| Browser bundle | `/app/static/js/main.266c0d79.js` |
| Backend deployed through | `71653933` |
| App server | `tradewave-appserver.service` active |
| Web service | active |
| Final browser state | S&P 500, 447 opportunities, no filter, full dates, tooltips OFF, no dialogs |

The frontend deploy is immutable and symlink-switched. Prior immutable build targets and timestamped backend rollback files remain available on `.176`.

The branch is committed and clean on `.176`. A GitHub push was attempted but not completed because the host's SSH private key permissions are invalid (`id_rsa` mode `0664`, so OpenSSH refuses it). No SSH configuration or key permissions were changed as part of this application test.

## Defects found and fixed

| ID | Severity | Defect | Root cause | Repair | Verification |
|---|---|---|---|---|---|
| D-01 | High | Opportunity prices could render `NaN` (first observed on `BK`). | Non-finite realtime values were accepted as prices. | Added finite-number sanitation before quote use. | Contract test plus visible table retest; no `NaN` values. |
| D-02 | High | A symbol shared by an equity group and futures namespace could receive the wrong quote. | Namespace lookup could prefer the wrong resource. | Added resource-aware collision validation and preserved the selected US equity group. | Contract tests for overlapping symbols/resources. |
| D-03 | High | Browser login credentials were embedded in a URL path. | Legacy GET-style login construction. | Added `/login/session` POST and moved credentials to the request body. | Contract test and signed-in browser reload/round trip. |
| D-04 | High | Generated report links could point at the production hostname while testing dev. | Hard-coded public URL. | Generate report URLs from `tw2_public_url`. | Static contract and `.176` link inspection. |
| D-05 | Medium | Portfolio footer edits could update a non-selected row. | Footer state update was not constrained to the clicked row. | Gate updates on the selected row index and use current-state updates. | Contract test and two-row Portfolio Manager exercise. |
| D-06 | High | Switching markets could leave the previous symbol/charts displayed. | Market change did not clear all viewer identity and chart state. | Clear symbol, company, selection, and all dependent chart data on switch. | Contract test and visible multi-market cycle. |
| D-07 | Medium | Start-date nudge controls were inaccessible/non-semantic. | Clickable glyphs were not buttons. | Replaced them with labeled, accessible buttons. | Contract plus visible date-nudge exercise. |
| D-08 | Medium | Current-price chart mode could disagree with the range actually fetched. | Mode inferred from stale percentage metadata. | Derive mode from the current request range. | Contract plus visible range/mode retest. |
| D-09 | High | Watchlist “Add Symbol” could receive the click event as a symbol. | Handler was passed directly to `onClick`. | Call the handler with no event argument. | Contract plus add/remove of disposable `AMZN`. |
| D-10 | Medium | Watchlist names could exceed a safe length, and duplicate rename validation was incomplete. | Client/server validation paths differed. | Added a 64-character bound and server duplicate/edit validation across add/edit/import responses. | Contract plus visible over-length/duplicate checks. |
| D-11 | Medium | Tooltips and short-date preferences did not reliably survive reload per user. | Mixed direct/global local-storage handling. | Use the user-scoped storage helpers for initialization and writes. | Visible OFF/ON and false/true reload tests; both restored to baseline. |
| D-12 | High | Tara produced an off-by-one calendar-day result and allowed unknown HTML tags through rendering. | Exclusive end-date math and incomplete tag allowlisting. | Use an inclusive end date and strip all tags outside the explicit allowlist. | Visible UTL date answer and inert script/image payload; contract test. |
| D-13 | High | A just-selected non-empty portfolio could be deleted without the required explicit confirmation. | The Delete handler interpreted the initial/stale opportunity count as empty before the async count returned. | Reset the count on selection, bind it to the selected portfolio, and refuse deletion until the matching count is loaded. | Immediate-select/delete visible retest showed “Delete Forever / Cancel” and the correct one-opportunity warning; new contract test. |
| D-14 | High | Delisted `CTRA` remained in cached S&P 500/Russell opportunity responses. | Disabled-symbol filtering was not applied after every cache-hit/miss path. | Apply market-specific retired-symbol filtering after cache resolution. | Default S&P count 448 → 447; `CTRA` filter returns no rows; contract test. |

`CTRA` was delisted after its Devon merger. Supporting filings: [SEC merger 8-K](https://www.sec.gov/Archives/edgar/data/858470/000110465926057278/tm2613882d1_8k.htm) and [Devon closing release](https://www.sec.gov/Archives/edgar/data/1090012/000119312526211971/d799973dex991.htm).

## Capability coverage

### Wave Viewer

Passed in visible Chrome: authenticated load, opportunity population, representative security-group changes, active/filter/sort behavior, ticker selection, empty/no-match recovery, date controls, years/partial years/PE modes, long/short/date-range behavior, MFE/MAE controls, row-to-chart propagation, stale-state clearing, deep-link reload, rapid selection settling, and retired-symbol exclusion.

### Charts and statistics

Passed: seasonal bar chart, trend chart, stats sections, current-price chart, representative ranges and chart modes, overlays, projection behavior, chart navigation, and non-empty JPEG export. The JPEG evidence is retained under `qa-artifacts`.

Not closed: the Trade Detail CSV anchor had the correct blob URL and filename (`AXP TradeWave Opportunity csv report.csv`), but controlled Chrome emitted no download event and produced no local file. There were no console errors. Retest manually and, if reproducible outside browser control, treat it as a product defect.

### Portfolio Manager

Passed: open/select, create, rename, invalid/duplicate guards, save distinct waves, row selection, share/investment edits, calculated footer behavior, sorting, report/calendar affordances, calendar-dialog cancel with no external insertion, saved-row deletion, empty-portfolio deletion, and cleanup.

The non-empty deletion race was reproduced, repaired, deployed, and retested. The corrected UI now requires the explicit “Delete Forever” step.

### Watchlists

Passed: settings load, invalid/long/duplicate name behavior, add valid symbol, remove symbol, and preference persistence. `AMZN` was added to and removed from the pre-existing favorites list; the original six symbols were restored.

Not closed: CSV upload could not be selected because the ChatGPT Chrome extension's **Allow access to file URLs** permission is disabled. The synthetic import file remains at `qa-artifacts/TW-QA-WL-20260725-import.csv`. Enable that permission, rerun valid/duplicate/invalid mixed-row import, and then remove any imported test symbols/list.

### Tara, preferences, navigation, and auth

Passed: Tara open/use/clear flows, selected-wave context, viewer update action, inclusive-date answer, unsafe-markup sanitization, tooltip persistence, short-date persistence, reload recovery, multi-tab/deep-link behavior, global navigation, account visibility, and signed-in session continuity. Logout was deliberately not invoked.

Browser back/forward could not be completed reliably because the visible-browser control channel timed out twice during history navigation. This is a qualification gap, not a claimed application failure.

### Responsive behavior

Failed release qualification:

- `1024×768`: controls clipped; one transition left stale loading until market reselect.
- `768×1024`: desktop-UA layout unusable/clipped.
- `390×844`: desktop-UA layout unusable/clipped.

A true mobile-UA pass was not available in the preserved signed-in Chrome session. Either fix these widths or explicitly document the supported-device/viewport contract and validate with the intended mobile UA.

## Automated and operational verification

| Gate | Result |
|---|---|
| Focused regression contracts | 14 passed |
| Full Python suite | 682 passed, 3 skipped |
| React suites | 7/7 suites; 61/61 tests passed |
| Normal production frontend build | Passed; emitted `main.266c0d79.js` |
| CI-strict frontend build | Failed because existing lint warnings are treated as errors |
| Visible Chrome post-deploy | Passed core retest; no console warnings/errors |
| App/web services | Active on `.176` |
| EODHD credential | HTTP 401; release-blocking refresh risk |

The three Python skips were environmental/document-generation skips: missing optional `mcp` package and two quickstart checks whose generated HTML was absent.

## Cleanup proof

Removed and absence-verified:

- Portfolios `TW-QA-20260725-A`, renamed `TW-QA-20260725-B`, and final retest portfolio `TW-QA-20260725-C`.
- Saved rows for AAPL, LUV, and AXP.
- Prefixed portfolio note.
- Disposable `AMZN` favorites entry.
- Long/invalid watchlist-name attempts (never persisted).
- Tooltip and short-date changes restored to OFF and full dates.

Final Portfolio Manager portfolio list: `main`, `Notifications`.

Pre-existing user data was not deleted or renamed. Local JPG/CSV files under `qa-artifacts` are retained only as regression evidence; they are not application records.

## Required work before release

1. Replace/repair the EODHD credential on `.176`, prove successful refreshes for every configured market, and audit stale/delisted constituents.
2. Fix or explicitly constrain responsive support, then repeat desktop/tablet/mobile-UA passes.
3. Eliminate or baseline the lint warnings so `CI=true npm run build` passes.
4. Enable file-URL access for the Chrome test extension and finish watchlist CSV import/cleanup.
5. Manually retest Trade Detail CSV download and repair if it fails outside browser control.
6. Repeat browser back/forward recovery with a stable visible Chrome control session.
7. After those items pass on `.176`, run the same release candidate in staging. Do not promote the present build directly to production.
