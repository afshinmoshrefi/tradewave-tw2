# TradeWave Full User-Facing Regression Matrix — 2026-07-25

## Scope and authority

- Target: `192.168.1.176` / `https://tw2-dev.trxstat.com` only.
- Authoritative interaction surface: the current signed-in visible desktop Chrome session.
- Included: every discoverable user-facing feature in the published web site and Wave Viewer, including Portfolio Manager, watchlists, Tara/chat, charts, preferences, navigation, account read-only flows, responsive behavior, history, refresh, and recovery.
- Excluded: all admin screens; real broker orders; Google Calendar insertion; email/SMS/contact/webinar/lead submissions; checkout/payment/subscription changes; social/news publishing; API-key creation or disclosure; WorkOS/auth configuration changes.
- Disposable records must use the `TW-QA-20260725` prefix, be recorded in the ledger, and be removed with absence verified before completion.
- No access or deployment to `.180`, staging, or production.

## Evidence states

- `P`: passed in visible Chrome.
- `A`: passed by automated test or read-only server verification.
- `F`: failed and requires repair.
- `R`: repaired and passed.
- `X`: deliberately excluded external/admin side effect; internal gating or read-only UI may still be checked.
- `—`: not yet executed.

## Public site, authentication shell, and account

| ID | Capability | Expected result | Pass 1 | Pass 2 | Evidence |
|---|---|---|---|---|---|
| PUB-01 | Home and global navigation | Published home and global header/footer links render without console errors | — | — | |
| PUB-02 | Wave Viewer navigation | Signed-in navigation opens `/app/` without auth loop | — | — | |
| PUB-03 | Learn index and articles | Learn index and user guides load and links resolve | — | — | |
| PUB-04 | News/insights/research | Published editorial surfaces load with stable layout | — | — | |
| PUB-05 | Pricing | Pricing renders; checkout mutation is not submitted | — | — | |
| PUB-06 | About/methodology/scorecard | Explanatory surfaces and internal links render | — | — | |
| PUB-07 | Markets/pattern catalog | Market and pattern pages render; representative detail links resolve | — | — | |
| PUB-08 | Terms/privacy/contact | Legal and contact pages render; contact submission excluded | — | — | |
| PUB-09 | Webinar/affiliate surfaces | Pages render; registration/signing mutation excluded | — | — | |
| PUB-10 | Account page | Current user/tier/subscription state renders without exposing secrets | — | — | |
| PUB-11 | Auth shell persistence | Refresh and app/site round trip preserve signed-in state | — | — | |
| PUB-12 | Logout safety | Logout control is visible but is not invoked during the signed-in suite | X | X | Auth preservation requirement |

## Opportunity table and Wave Viewer controls

| ID | Capability | Expected result | Pass 1 | Pass 2 | Evidence |
|---|---|---|---|---|---|
| WV-01 | Default opportunity load | Table loads current opportunities with finite, formatted values | — | — | |
| WV-02 | Security group switch | Representative equity, ETF, index, future, forex, bond, crypto, and watchlist groups load | — | — | |
| WV-03 | Date controls | Month/day changes update opportunities and viewer state | — | — | |
| WV-04 | Lookback years | Supported year values update results without stale charts | — | — | |
| WV-05 | Partial/consecutive years | Partial-year selection updates results and labels consistently | — | — | |
| WV-06 | PE cycle | Consecutive and PE year modes update all dependent views | — | — | |
| WV-07 | Opportunity filter syntax | Ticker, range, numeric, combined, empty, and invalid filters behave safely | — | — | |
| WV-08 | Filter preset | MFE/MAE threshold presets update rows and can be cleared | — | — | |
| WV-09 | Sort columns | Date/ticker/days/direction/SR/AvgP/price/win/prediction sorts are stable | — | — | |
| WV-10 | Active toggle | Active-only state updates rows and remains internally consistent | — | — | |
| WV-11 | Row selection | Selected row drives all right-side charts and metadata | — | — | |
| WV-12 | Manual ticker | Valid ticker resolves and loads; invalid ticker yields a clear recoverable message | — | — | |
| WV-13 | Cross-market ticker | Symbols resolve to their correct security group without ambiguous state | — | — | |
| WV-14 | Start date nudge | Back/forward controls update the start date and all charts | — | — | |
| WV-15 | Days-out | Boundary and representative durations update wave statistics correctly | — | — | |
| WV-16 | Direction | Long/short toggle reverses calculation/labels consistently | — | — | |
| WV-17 | Months and quarters | Representative month, quarter, and reset choices update the window | — | — | |
| WV-18 | Reverse date range | Reversal updates dates/direction semantics without corrupting state | — | — | |
| WV-19 | Buy-and-hold comparison | Comparison series toggles and remains aligned with wave statistics | — | — | |
| WV-20 | MFE/MAE overlays | Overlays toggle independently and together without stale series | — | — | |
| WV-21 | Best Waves | Best-wave selection loads a valid pattern and remains navigable | — | — | |
| WV-22 | Deep link | Viewer state serializes/restores across copied URL and reload | — | — | |
| WV-23 | Browser history | Back/forward restores prior viewer selections without auth loss | — | — | |
| WV-24 | Rapid changes | Fast successive selections settle on the last requested state | — | — | |
| WV-25 | Empty/error state | No-data and rejected inputs show usable messages, not blank/NaN UI | — | — | |

## Trend, statistics, and price charts

| ID | Capability | Expected result | Pass 1 | Pass 2 | Evidence |
|---|---|---|---|---|---|
| CH-01 | Seasonal bar chart | Bars, axes, legend, metadata, and current selection agree | — | — | |
| CH-02 | Trend chart | Trend series renders and follows the selected wave | — | — | |
| CH-03 | Trend window drag | Left/right boundaries drag and update dependent metrics | — | — | |
| CH-04 | Jan–Dec/reset | Full-year reset restores a valid range | — | — | |
| CH-05 | Trend navigation | Previous/next controls select valid neighboring patterns | — | — | |
| CH-06 | Stats tabs | Wave Detail, P/L, cumulative, Wave Stats, Wave Info, General render | — | — | |
| CH-07 | Stats consistency | Dates, years, direction, return, SR, and win metrics agree across views | — | — | |
| CH-08 | Price chart | Historical chart loads with current symbol/date context | — | — | |
| CH-09 | Price chart type | Line, candle, and OHLC modes render | — | — | |
| CH-10 | Price timeframe | Daily/weekly and 3m/6m/1y/2y ranges render | — | — | |
| CH-11 | Price overlays | Volume, moving averages, Bollinger, earnings, projection toggle cleanly | — | — | |
| CH-12 | Projection horizon | Maximum-year projection and normal projection recover cleanly | — | — | |
| CH-13 | Price levels | Create/edit/color/dash/delete/clear disposable price lines | — | — | |
| CH-14 | CSV export | Export produces a non-empty, correctly named data file | — | — | |
| CH-15 | JPG export | Seasonal/trend/stats/price exports produce valid non-empty images | — | — | |

## Portfolio Manager and reports

| ID | Capability | Expected result | Pass 1 | Pass 2 | Evidence |
|---|---|---|---|---|---|
| PM-01 | Open/select Portfolio Manager | Manager opens and existing user data is preserved | — | — | |
| PM-02 | Create portfolio | Create tracked `TW-QA-20260725-A` and record returned identity | — | — | |
| PM-03 | Duplicate/invalid portfolio | Duplicate, empty, and over-limit names are rejected clearly | — | — | |
| PM-04 | Rename portfolio | Rename disposable portfolio to `TW-QA-20260725-B` | — | — | |
| PM-05 | Main portfolio guard | Main/default portfolio cannot be renamed or deleted | — | — | |
| PM-06 | Save selected wave | Save a wave into the disposable portfolio once | — | — | |
| PM-07 | Idempotent/duplicate save | Repeated save does not create an unintended duplicate | — | — | |
| PM-08 | Save second wave | Save a distinct wave and verify independent state | — | — | |
| PM-09 | Recall wave | Recall each saved row into all Wave Viewer controls/charts | — | — | |
| PM-10 | Notes | Add/edit/clear a prefixed note and verify persistence across reload | — | — | |
| PM-11 | Shares | Enter, edit, clear representative share quantities | — | — | |
| PM-12 | Investment/P&L | Investment, gain/loss, total, and percentage recalculate correctly | — | — | |
| PM-13 | Status | Change status flags and verify filtering/aggregate behavior | — | — | |
| PM-14 | Sort/report table | Sort representative columns without row/action mismatch | — | — | |
| PM-15 | Generate static report | Generate/refresh internal report and open `/r/<slug>/` | — | — | |
| PM-16 | Report content | Report matches saved wave and renders without console errors | — | — | |
| PM-17 | Calendar dialog | Internal dialog and validation render; Google Calendar insert excluded | X | X | No external insertion |
| PM-18 | Delete saved rows | Delete only disposable rows and verify absence | — | — | |
| PM-19 | Non-empty portfolio guard | Non-empty deletion requires explicit confirmation | — | — | |
| PM-20 | Delete portfolio | Delete empty disposable portfolio and verify absence after reload | — | — | |

## Watchlists and securities preferences

| ID | Capability | Expected result | Pass 1 | Pass 2 | Evidence |
|---|---|---|---|---|---|
| WL-01 | Open watchlist settings | Settings show current lists without mutation | — | — | |
| WL-02 | Create watchlist | Create tracked `TW-QA-WL-20260725` | — | — | |
| WL-03 | Duplicate/invalid watchlist | Duplicate, empty, and over-limit names are rejected | — | — | |
| WL-04 | Rename watchlist | Rename disposable watchlist and retain items/default state | — | — | |
| WL-05 | Add valid ticker | Add representative valid symbols | — | — | |
| WL-06 | Invalid/duplicate ticker | Invalid and duplicate additions yield clear feedback | — | — | |
| WL-07 | Remove ticker | Remove only disposable entries and verify absence | — | — | |
| WL-08 | CSV import | Import tracked CSV with valid, duplicate, invalid, and mixed-group rows | — | — | |
| WL-09 | Group detection | Imported symbols resolve to correct groups with actionable failures | — | — | |
| WL-10 | Add to securities | Disposable watchlist appears as a Wave Viewer group and loads | — | — | |
| WL-11 | Default watchlist | Set disposable default, verify toolbar suggestions, then restore original | — | — | |
| WL-12 | Rename persistence | Renamed list remains selected and functional after reload | — | — | |
| WL-13 | Delete watchlist | Delete disposable list and verify absence after reload | — | — | |
| WL-14 | Published list preferences | User-visible published lists can be hidden/shown without admin mutation | — | — | |

## Tara/chat, help, and preferences

| ID | Capability | Expected result | Pass 1 | Pass 2 | Evidence |
|---|---|---|---|---|---|
| AI-01 | Open/close/resize Tara | Chat opens, closes, and resizes without covering critical controls | — | — | |
| AI-02 | Greeting and entitlement | Initial message and access state match the signed-in account | — | — | |
| AI-03 | Current-wave context | Answer references the selected pattern accurately | — | — | |
| AI-04 | Opportunity context | Scan/filter question uses current opportunity context safely | — | — | |
| AI-05 | Viewer update action | Tara can update ticker/date/days/years/market/PE and UI confirms it | — | — | |
| AI-06 | Concepts | Representative help topics open accurate concept content | — | — | |
| AI-07 | Clear | `clear` resets conversation without affecting viewer state | — | — | |
| AI-08 | Sanitization | HTML/script-like input is rendered inert and does not execute | — | — | |
| UX-01 | Tooltips | Global tooltip toggle changes help affordances and persists | — | — | |
| UX-02 | Lesson/help | Contextual lesson bulb opens/closes relevant guidance | — | — | |
| UX-03 | Theme | Light/dark theme updates all panels and remains readable | — | — | |
| UX-04 | Column visibility/order | Table columns hide/show/reorder and table remains usable | — | — | |
| UX-05 | Short dates | Date-format preference updates visible dates consistently | — | — | |
| UX-06 | Group visibility | User can hide/show securities groups and recover defaults | — | — | |
| UX-07 | Pane resizing | Left/right, chart, table, and chat resizers remain bounded | — | — | |
| UX-08 | Preference persistence | Settings survive reload and are restored to baseline afterward | — | — | |

## Responsive, resilience, compatibility, and quality gates

| ID | Capability | Expected result | Pass 1 | Pass 2 | Evidence |
|---|---|---|---|---|---|
| QA-01 | Desktop baseline | Current desktop viewport has no overlap/clipping/blocking modal | — | — | |
| QA-02 | Narrow desktop/tablet | Representative narrow viewport remains operable | — | — | |
| QA-03 | Mobile width | Published site and supported app controls remain accessible | — | — | |
| QA-04 | Zoom | 80%, 125%, and 150% retain essential controls/readability | — | — | |
| QA-05 | Multi-tab | Second visible tab does not corrupt first-tab viewer state | — | — | |
| QA-06 | Refresh recovery | Reload restores a valid signed-in state and current/deep-linked context | — | — | |
| QA-07 | Back/forward recovery | Navigation history does not leave stale or blank charts | — | — | |
| QA-08 | Error recovery | Invalid/no-data actions recover with the next valid selection | — | — | |
| QA-09 | Console quality | No unexplained error/warning introduced during suite | — | — | |
| QA-10 | Network/API quality | No unexplained 4xx/5xx or failed required resource during suite | — | — | |
| QA-11 | Interaction performance | Core table load, row-to-chart, manual ticker, portfolio open are responsive | — | — | |
| QA-12 | Automated frontend tests | Relevant React unit/integration suites pass | — | — | |
| QA-13 | Automated backend tests | Selected side-effect-free app/API unit suites pass | — | — | |
| QA-14 | Production build | Clean immutable frontend build succeeds | — | — | |
| QA-15 | Dev deploy/rollback | `.176` deploy is atomic, health-checked, and rollback target recorded | — | — | |
| QA-16 | Boundary audit | No `.180`, staging, production, admin, or external side effect touched | — | — | |
| QA-17 | Cleanup audit | Every disposable record/file is removed and absence verified | — | — | |

