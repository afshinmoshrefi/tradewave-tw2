# TradeWave Wave Viewer — Windows 11 Regression Report

**Test date:** 2026-07-24  
**Target:** `https://tw2-dev.trxstat.com/app/`  
**Disposition:** **FAIL — not release-ready for filter-dependent workflows**

## 1. Executive summary

The authenticated development site loaded and remained usable through extended table, Wave Viewer, chart, chatbot, navigation, and real-pointer resize testing. Baseline data was restored before the browser session was closed.

The run found four high-risk state/correctness problems:

1. AI filters are order- and timing-dependent. The same `PredR` intersection can return 0 or 56 rows depending on token order and rapid prior edits.
2. Sorting Win% after filtering silently replaces the active filter and expands the result set.
3. Selecting an opportunity leaves the Wave Viewer statistics showing the previous row for roughly 2.8–3.5 seconds with no loading indicator.
4. PE+2 can silently change the table requirement from 8-of-10 to 10-of-10; switching it off then returns 58 rows rather than restoring the 419-row baseline.

The filter field also turns temporarily incomplete or invalid expressions into an unlabeled zero-row table, making syntax errors visually indistinguishable from legitimate empty results.

No browser-console warnings or errors were recorded. Resource-failure inspection was not exposed by the selected browser-control surface.

## 2. Environment tested

| Item | Observed value |
|---|---|
| Operating system | Windows 11, x64; OS API version `10.0.26200.0`, build 26200 |
| Browser | Google Chrome `150.0.7871.186` |
| Authentication | Existing signed-in test account; no credential access |
| Screen | 1920×1080 |
| Effective browser viewport | 1920×911 |
| Device pixel ratio / effective scaling | DPR 1.0; effective 100% |
| Browser zoom | 100% baseline |
| Hostname | `tw2-dev.trxstat.com` |
| Application title | `TradeWave - AI Scored Patterns` |
| Visible app/build version | Not exposed |
| Initial landing-page DOM ready | 17.88 s |
| Initial `/app/` DOM ready | 0.56 s |
| Initial `/app/` usable with data | 13.48 s |
| Console errors/warnings | None captured |
| Failed-resource evidence | BLOCKED: resource/network log API was unavailable |

The viewport override reported success but did not change the effective 1920×911 viewport. Browser zoom shortcuts similarly did not change CSS viewport or DPR. Exact 1366×768, 1280×720, 80%, and 125% results are therefore marked BLOCKED rather than inferred.

## 3. Baseline

- Universe: S&P 500 STOCKS
- Date: 2026-07-24
- Lookback: 10 years
- Recurrence: 8 of 10 years
- Returned: **419 opportunities**
- Direction split: **351 long / 68 short**
- AI data: 152 populated rows; 267 rows displayed `---` in AI columns

[Baseline screenshot](./01-baseline-1920x911.png)

## 4. PASS / FAIL / BLOCKED matrix

| # | Case | Result | Evidence / observation |
|---:|---|:---:|---|
| 1 | Existing authentication and app access | PASS | Logged-in Wave Viewer opened without credential access |
| 2 | Baseline S&P 500, 10 years, 8-of-10, today | PASS | 419 rows; 351 long, 68 short |
| 3 | Browser console inspection | PASS | No warning/error entries captured |
| 4 | Exact filter steps 1–5 | PASS | `10-90`, `avgp>10`, combined, trailing `;`, appended AvgP all completed |
| 5 | Delete AvgP token one character at a time | FAIL | Temporary valid/incomplete states produced 0 unlabeled rows |
| 6 | Clear, re-enter, and whitespace variants | PASS | Restored expected rows; spaced syntax worked |
| 7 | Invalid-token distinction and correction | FAIL | Correction works, but invalid state is indistinguishable from real empty results |
| 8 | Rapid type/erase/replace | FAIL | Intermittent stale/race results, especially with AI tokens |
| 9 | Empty-result case followed by valid filter | PASS | `avgp>9999` → valid filter recovered |
| 10 | Switch universe with active filter | PASS | NASDAQ and S&P subsets updated |
| 11 | Change Years with active filter | FAIL | 8-of-10 silently became 10-of-10 on return |
| 12 | Refresh with active filter | PASS | App recovered with 419 rows; active filter was cleared |
| 13 | AI filter syntax discoverability | FAIL | Help/UI did not document syntax; literal headers had to be tested |
| 14 | Win% filter alone (`win>70`) | PASS | 95 rows |
| 15 | PredR filter alone (`predr>3`) | FAIL | 31 rows initially, then 0 after rapid prior edits |
| 16 | Win% and PredR together | PASS | 31 rows in stable sequence |
| 17 | Range combined with AI filters | FAIL | `10-90;predr>3` returned 0 while reversed token order returned 56 |
| 18 | AvgP combined with each AI filter | PASS | AvgP+Win 3; AvgP+PredR 1 |
| 19 | Range + AvgP + Win% + PredR | PASS | 2 rows in stable sequence |
| 20 | Delete AI tokens one character at a time | FAIL | Incomplete `win>` / `predr>` produced unlabeled empty state |
| 21 | Recover from invalid AI syntax | PASS | Correcting `win>>70` to `win>70` restored 95 |
| 22 | Sort AI column after filtering | FAIL | Win sort replaced the filter and expanded results |
| 23 | Important columns sorted both directions | PASS | Ticker, Days, DIR, SR, AvgP, Price, Win%, PredR |
| 24 | Large-result scrolling | PASS | Real wheel scrolling moved 0→1416→0 |
| 25 | Select beginning, middle, end, and post-sort rows | PASS | All selections accepted |
| 26 | Selected row immediately matches Wave Viewer | FAIL | Statistics lagged one selection behind |
| 27 | Rapidly select several rows | PASS | Final row eventually matched; stale intermediate states remained |
| 28 | DOW, NASDAQ, ETFs, S&P universes | PASS | 29, 84, 166, and 419 rows respectively |
| 29 | Different lookback settings | PASS | Values changed and data reloaded |
| 30 | Opportunity-table PE+2 toggle | FAIL | Mutated 8-of-10 to 10-of-10; failed to restore baseline |
| 31 | Long and short opportunities | PASS | Both loaded in viewer |
| 32 | Empty state and recovery | PASS | App remained recoverable |
| 33 | Symbol/date/days manual controls | PASS | MSFT and 30/60-day changes loaded |
| 34 | Viewer Years/lookback | PASS | 5/15/10-year changes worked |
| 35 | Consecutive and PE/PE+1/PE+2/PE+3 cycle controls | FAIL | Controls worked but changed date/recurrence and did not restore prior state |
| 36 | Reverse Date Range and Buy & Hold | PASS | Each updated the date/window |
| 37 | MFE and MAE | PASS | Both toggled on/off |