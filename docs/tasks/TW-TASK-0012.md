# TW-TASK-0012: Chart Toolbar Control Titles

## Mobile title removal claim (2026-10-04)

- Status: verified on dev; earlier desktop/title styling verification remains historical below.
- Executor/session/claim time: Codex `/root/toolbar_titles`, 2026-10-04 UTC.
- Branch/worktree: `codex/toolbar-mobile-compact-20261004` at `/home/tradewave-worktrees/toolbar-mobile-compact-20261004`, based on `dc2942105f73d414cdfec2601c27d154f4811474`.
- Authorization: Afshin requested no toolbar titles on mobile while preserving desktop titles and its General switch. Routine dev activation authorized; staging and production excluded.
- Acceptance: Phone toolbar and expanded second row show zero titles, retain compact height and control behavior. Desktop titles and persisted switch remain as before.
- Implementation: `SeasonalBarChart.js` applies the persisted title preference only when `!rdd.isMobile`; mobile/tablet height, title classes, headings and portrait second row therefore use the existing compact mode. Desktop preference behavior is unchanged. `docs/TRADEWAVE_ECOSYSTEM.md` now states this rule.
- Code/main SHA: `6b57fc5ebf895c419011e0d8646d5cd38606054f`; clean task and integration worktrees. React build via `ops/build_react_release.sh` passed with existing lint notices. Live dev frontend `/home/flask/web-react/releases/build-6b57fc5ebf895c419011e0d8646d5cd38606054f`, served `main.9cccd289.js`; previous frontend pointer `/home/flask/web-react/releases/build-c9a865640aeacf6e7fd10dc925ad065e80c0d8ac` retained for rollback. Backend application tree matches current main; no backend restart, migration or configuration change.
- Dev verification (2026-10-04, Codex): documented dev capture-bot shell with real nginx assets/API in Chromium. Loaded AAPL 15-day pattern showed all 15 desktop accessible titles; General switch off removed titles and reduced height 60 to 33.5px, persisted across reload, and on restored titles. Pixel 5 emulation at 390x844 showed zero titles and no title-layout class, compact 38.5px toolbar, no body overflow, and a working More action exposing five second-row controls with zero titles. This is the requested mobile regression; no broad staging gates run. Staging/production not checked or changed. Next action: staging qualification only on explicit request.

## Title spacing refinement claim (2026-09-29)

Afshin requested a cleaner, professional toolbar for new users after reviewing the underlined titles on dev. Codex `/root` claims this dev-only follow-up in `codex/toolbar-title-spacing-20260929`, isolated worktree `C:/Users/afshin/.codex/worktrees/toolbar-title-polish/TradeWave Main Orchestrator`, from main `e9c83d82089b66f5e47daa794072b957abf51d48`. A UI design subagent inspected the screenshot and identified a visually detached title row. Preserve no gray fills, title underlines, responsive aliases, single-row fitting and the existing title-off mode. Next: render and refine title-to-control spacing, then build, activate and verify on dev.

## Underlined title styling follow-up (2026-09-29)

Afshin requested removing the gray title backgrounds and placing an underline beneath each toolbar title. Codex `/root` claimed this dev-only styling follow-up in `codex/toolbar-title-underline-20260929`, isolated worktree `C:/Users/afshin/Documents/TradeWave Main Orchestrator/toolbar-title-underline-20260929`, from main `8b4cad757c838b7a192dc6e863347b3bbf891935`. Preserve responsive abbreviations, control layout, settings and title-off behavior. The verified implementation and evidence appear at the end of this record.

- Status: toolbar title styling verified on dev
- Confidence: reproduced
- Priority: P3 - improves control discoverability
- First observed / last updated: 2026-09-27 22:45 UTC / 2026-09-30 UTC
- Executor/session: Codex `/root/toolbar_no_wrap_repair`; independent visual/native-Chrome reviewer `/root`. Original implementation and prior failed attempts are retained below.
- Authorization: User requested implementation and routine dev activation; staging and production excluded.

## Goal, Scope and Acceptance

Add visible titles above every control in the bar-chart toolbar, from Add (+) through Help (?). Settings > General has a persisted Show toolbar titles switch, enabled by default. The date and duration controls read exactly "Start date" and "Days hold". Other titles accurately describe their controls. Enabled layout fits the title row; disabled layout is compact. Existing interactions and responsive use remain functional.

## Evidence and Investigation

The toolbar renders in `SeasonalBarChart.js`; Settings > General is in `DesktopLayout.js`. The phone portrait toolbar exposes five additional controls in an expandable second row. `App.js` holds user-scoped local settings through `lsGet`/`lsSet`. Source baseline: origin/main `5aaff50f6caef3597c3f65cfb202831e0d8ed914`.

## Acceptance and Regression Checks

React production build passed on the integrated candidate (existing project lint warnings). On live dev, a capture-bot browser loaded AAPL's 15-day pattern and found all 15 visible desktop toolbar titles from Save wave to Help. Settings > General showed the switch enabled by default; turning it off removed titles, reduced toolbar height from 58.7 to 33.5 px, and persisted `false` across reload. Turning it on restored titles. Pixel 5 emulation at 390px rendered the top row and the expanded second row with Start date, Ticker, Days hold, Years and Cycle filter; document width stayed 390px. Browser used the documented dev-only internal capture shell and real nginx/API routes. Staging and production not tested.

## Implementation and Handoff

Repository: tradewave-tw2. Task branch `codex/toolbar-control-titles-20260927`, commit `12d9a861`; integration branch `codex/toolbar-titles-integration-20260927`, commit `c2045a082ede9595fceb3783ccef53b228edaf6a`. Worktrees: `/home/tradewave-worktrees/toolbar-control-titles-20260927` and `/home/tradewave-worktrees/toolbar-titles-integration-20260927`, both clean. Changed `App.js`, `DesktopLayout.js`, `SeasonalBarChart.js`, its CSS, and this implementation map/record. No migration or configuration change. Frontend artifact: `/home/flask/web-react/releases/build-c2045a082ede9595fceb3783ccef53b228edaf6a`; previous pointer `/home/flask/web-react/releases/build-55bdbdc2fc61d020d0066382faf6f22a52d28129` for rollback. Backend unchanged. Next: staging qualification only after explicit request.

## Environment Verification

Dev: verified 2026-09-27 22:44 UTC by Codex on `c2045a082ede9595fceb3783ccef53b228edaf6a` / `main.10ca5482.js` using desktop Chromium 1440x900 and Pixel 5 emulation 390x844, with the documented dev capture-bot shell, real assets/API, and Settings interaction. The assertions and measurements above are the recorded evidence; repeat with a Puppeteer navigation to `/app/?o=` for `2|AAPL|2026-01-15|15|10` using `docs/UI_CAPTURE_PIPELINE.md`'s shell interception. Staging: not checked. Production: not checked.

## Visual quality follow-up

User reviewed the dev result and reported that the title layout looks terrible. Authenticated screenshots show overlapping labels and a Best Waves selector squeezed to 5.9px at a 1440px viewport, despite the earlier functional checks passing. Improve visual grouping, alignment and readable spacing while preserving the default-on switch, exact Start date/Days hold titles and compact-off mode. This follow-up is authorized for dev only; no staging or production. Owner: Codex `/root/wave_info_dev`, 2026-09-27 23:10 UTC; branch `codex/toolbar-title-polish-20260927`, worktree `/home/tradewave-worktrees/toolbar-title-polish-20260927`. Visual follow-up commit `a5470c706a9fb016c4c5db817c31c79da6939bf1` built as `main.e5cfbd82.js` and activated on dev from `/home/flask/web-react/releases/build-a5470c70`; rollback pointer is `build-c2045a082ede9595fceb3783ccef53b228edaf6a`. The toolbar now uses aligned two-row desktop controls at ordinary widths, adds a narrow three-row layout when the right panel is under 780px, keeps Best Waves readable, and shows Long/Short beside its color square only with titles on. Actual dev Chromium screenshots verified default ON at 1440, 1309, and 1280 CSS pixels, title OFF at 1440 (0 visible titles, 40.7px bar), and a 1280 viewport with 40% left panel / 763px right panel: every visible input and select stayed inside the 150px bar. The 1309px run approximates the responsive CSS width of 1440px at 110% browser zoom; native browser zoom was not tested. Screenshot evidence: `toolbar-final-on-1440.png`, `toolbar-final-off-1440.png`, and `toolbar-final-narrow-1280.png` in the orchestrator task workspace. Existing production-build lint warnings only. Staging and production not tested.

## User-rejected redesign rollback

Afshin reported the visual redesign made the toolbar completely broken and asked for the prior version. On dev, the frontend pointer was restored to `/home/flask/web-react/releases/build-c2045a082ede9595fceb3783ccef53b228edaf6a` (source `c2045a082ede9595fceb3783ccef53b228edaf6a`); React asset preflight and the web service passed, and an authenticated AAPL Wave Viewer loaded the previous toolbar. Revert commit `288f8ec8823bb9b5d9540325b7f4dae3786929d1` reverses only the four visual-redesign commits `8f61ed25`, `2bdf2e8d`, `fd0940bd`, and `a5470c70`; `SeasonalBarChart.js` and its CSS now exactly match `c2045a08`. The visual follow-up screenshots above document a rejected, no-longer-active candidate. No staging or production change.

## Focused heading follow-up (2026-09-28)

Afshin requested coherent Opportunity-table-style toolbar headings, specifically correcting the Save wave title alignment. This is a new dev-only follow-up after the rejected redesign rollback. Claimed by Codex `/root/wave_info_dev` at 2026-09-28 00:43 UTC, branch `codex/toolbar-title-headings-20260927`, isolated worktree `/home/tradewave-worktrees/toolbar-title-polish-20260927`. Keep the restored control behavior and compact title-off mode. Validate actual desktop and narrowed-panel renders before activation; no staging or production authorization.

## Focused heading follow-up result (2026-09-28)

Commit `00e3af9266ac4b208f81b392979a105786e20354` is on current main and active on dev as `/home/flask/web-react/releases/build-00e3af9266ac4b208f81b392979a105786e20354` (`main.771a8bc4.js`). The title-on desktop toolbar uses the Opportunity table header theme colors and borders, aligns each heading with its existing control, gives Best Waves/Years/Cycle enough width to show their selected values, and wraps whole title/control pairs when the chart panel narrows. Title-off and mobile paths retain their prior layout. Backend, math, settings persistence, staging and production were unchanged.

React build passed with existing lint warnings. Authenticated dev browser checks used the built artifact and then the live served asset: 1440px and 1280px desktop, 1280px with the left panel widened to 40%, and title-off at 1440px. In the narrow view, all 15 visible control pairs were inside the 763px toolbar, the chart began exactly at the toolbar bottom (179px), and hidden Chart/More controls remained hidden. Title-off had zero headings and a compact 40.7px bar. On live dev, the Years selector changed to 9; `/healthz` reported DB/frontend OK. Browser screenshots are in `docs/tasks/evidence/TW-TASK-0012-heading-20260928/`. A 1280px viewport exercises a narrower CSS layout than a 1440px viewport at approximate 110% scaling; native browser zoom itself was not tested. Rollback pointer: `build-c2045a082ede9595fceb3783ccef53b228edaf6a`.

## Adaptive-width heading follow-up (2026-09-28)

Afshin reported that modest narrowing of the chart panel makes the full headings
wrap awkwardly. Authorized scope: use the actual toolbar width to shorten visible
headings progressively, keep the normal desktop row where controls fit, retain
full hover/accessibility names and selected values, and preserve title-off/mobile.
Staging and production are excluded.

Codex `/root/toolbar_responsive_labels` claimed this follow-up on main
`8539914749ee29450bea6afcc992147a6f24a600`, then pushed the claim as
`2181e7f08a92569cf61ca44d10487914e55f811f`. Task branch
`codex/toolbar-adaptive-titles-20260928` and worktree
`/home/tradewave-worktrees/toolbar-adaptive-titles-20260928` contain pushed
source commit `9259378c190472b0d0c8516cce3851d11c93915f`. The clean
integration worktree is `/home/tradewave-worktrees/toolbar-adaptive-integration-20260928`.

`SeasonalBarChart.js` uses `ResizeObserver` on `.barchart-controls` and changes
only visible title text at measured widths; `CheckBox.js` allows MFE/MAE's
redundant inline words to disappear in tight title mode while preserving their
input values, full accessible names and callbacks. The CSS keeps fixed selected
values readable and removes empty spacing only in tight title mode. The phone
and title-off paths retain their previous display rules. No backend, calculation,
configuration or migration changes. React build from the clean task commit passed
with existing lint warnings; browser candidate checks used its built bundle and
real dev API through the documented authenticated capture shell without activating
it. AAPL `2|AAPL|2026-01-15|15|10`, desktop Chromium, 20% left panel:

| Viewport CSS px | Toolbar px | Heading row | Control/input overflow | Right slack |
|---:|---:|---:|---:|---:|
| 1745 | 1391 | full, one row | none | 22px |
| 1600 | 1275 | short, one row | none | 65px |
| 1400 | 1115 | short, one row | none | 50px |
| 1350 | 1075 | short, one row | none | 20px before final spacing reduction |
| 1300 | 1035 | short, one row | none | 29px |
| 1280 | 1019 | short, one row | none | 17px |
| 1250 | 995 | short, one row | none | 1px |

At 1035px with titles off, the toolbar stayed 34px high with no headings and all
controls inside its bounds. A 1600px CSS viewport is close to the effective
width of 1745px at 110% zoom (about 1586px); the 1280px check probes further
narrowing. Native zoom and other browsers were not tested.
Unobscured screenshots: `docs/tasks/evidence/TW-TASK-0012-adaptive-20260928/`.
At 995px the row has minimal slack; the CSS wraps whole controls when needed
below that width rather than clipping values. Integration commit
`eb3975d50232c57c921d965f60d21345d4ec18d5` passed the production React
build and was activated on dev as
`/home/flask/web-react/releases/build-eb3975d50232c57c921d965f60d21345d4ec18d5`.
Rollback pointer: `/home/flask/web-react/releases/build-00e3af9266ac4b208f81b392979a105786e20354`.
The backend pointer remained `/home/flask/.tw2-releases/9b02f007d90a26b605e2217b80188109e6f48add`.

Live dev verification at 2026-09-28 04:35 UTC used the same authenticated
Chromium capture shell through nginx with the active served bundle, not the
pre-activation candidate intercept. AAPL chart canvas rendered. At 1391px the
15 full headings fit one row with 22px right slack; at 1019px the short headings
fit one row with 17px slack. Every visible control and input stayed within the
toolbar, and toggling MFE changed checkbox state. Title-off at 1019px had zero
headings, 34px height and no overflow. The active bundle provenance file names
`eb3975d5`; `/healthz` reported DB/frontend OK. Current origin/main at activation
was advanced non-force to `eb3975d5`; its application tree matches the live
frontend source. This is self-verification by the implementing Codex session.
Staging and production were not checked. Next: qualify and promote only after an
explicit staging request; no configuration or migration is required.

## History

- 2026-09-28 04:36 UTC, Codex `/root/toolbar_responsive_labels`: Activated integration `eb3975d5` on dev, live browser checks passed, pushed main non-force and proved app tree/artifact parity; released dev lock. Next: documentation receipt and staging only on later request.

- 2026-09-28, Codex `/root/toolbar_responsive_labels`: Claimed the user-requested responsive heading follow-up on current main `8539914749ee29450bea6afcc992147a6f24a600`. Branch `codex/toolbar-adaptive-titles-20260928`, clean worktree `/home/tradewave-worktrees/toolbar-adaptive-titles-20260928`. Scope: keep a desktop row while shortening only visible headings according to the chart container width; preserve full names, controls, title-off and mobile behavior. Dev only. Next: implement, build, inspect narrowed rendered widths, activate and verify.

- 2026-09-27 22:25 UTC, Codex: Claimed authorized feature. Next: inspect toolbar and settings, implement and verify.
- 2026-09-27 22:35 UTC, Codex: Implemented source and passed React build; another session currently owns the dev activation lock.
- 2026-09-27 22:44 UTC, Codex: Integrated latest main and activated candidate under dev lock; desktop and phone browser checks passed; non-forced main advance to `c2045a08` succeeded.

- 2026-09-27 23:10 UTC, Codex `/root/wave_info_dev`: Claimed user-requested visual follow-up; confirmed overlap on actual dev render.

- 2026-09-27 23:40 UTC, Codex `/root/wave_info_dev`: Completed visual follow-up on dev with browser screenshots and narrow-panel bounds check; no staging or production.

- 2026-09-27 23:50 UTC, Codex `/root/wave_info_dev`: User rejected visual redesign; restored original dev frontend and reverted redesign code on main.

## Desktop single-row repair claim (2026-09-28)

User rejected wrapping and explicitly escalated investigation to Astra. Codex
`/root/toolbar_no_wrap_repair` owns the follow-up in
`codex/toolbar-single-row-20260928`, isolated flask worktree
`/home/tradewave-worktrees/toolbar-single-row-20260928`, claimed 2026-09-28.
Exact user failure: Chrome at native 110%, CSS viewport 1046x545, toolbar
782.713px, HLT / 2026-09-28 / 141 days / 10 years, loaded main.de1a2983.js.
Heading mode wraps controls at 1040px while nonshrinking title/control pairs
retain fixed selected-control floors. OFF remains one line but clips controls
and collapses Best Waves to 1.8px. Splitter range is 20%-40% left panel.
Scope: one desktop heading row directly above one control row across that
range; compact labels retain full accessible/hover names and actual values.
Preserve OFF/mobile/settings/theme/Save alignment. Dev only. Next: prototype
and verify full allowed width sweep, root visual review, build and dev smoke.

### Single-row candidate implementation

Removed the deliberate desktop wrap rule. Compact title-mode controls use
container-scaled text, selected option labels without redundant units, and short
Waves/Presets closed captions; native dropdown options, actual values, and full
selected-label hover text remain intact. CSS removes title min-content floors
and prevents native selects' longest options from sizing the closed control.
Direction uses Dir; minimum title tracks prevent MFE/MAE overlap. Existing OFF
and phone styling remain unchanged. No backend, math, config or migration change.

First source build passed with existing lint warnings. An independent capture
browser with real HLT data tested the source-CSS correction against that bundle
at 22 actual splitter positions, 623-831px toolbar width including 782.6px: one
heading row, no control bounds overflow, no heading overlap, date/ticker values
fit. Root visually reviewed 623px and 783px screenshots and accepted this design.
Final clean-source artifact, transition, interaction and live checks pending.

### Single-row repair verified on dev

Source/integration SHA: `79fcba0be29af546cfd2ac01b1042b8405382b60`,
pushed on `codex/toolbar-single-row-20260928` and advanced to main without force.
Final clean integration worktree:
`/home/tradewave-worktrees/toolbar-single-row-integration-20260928`.
Production React build via `ops/build_react_release.sh` passed with existing
lint warnings; artifact provenance names that exact SHA. Dev runs
`/home/flask/web-react/releases/build-79fcba0be29af546cfd2ac01b1042b8405382b60`,
`main.7fb35429.js`. Backend pointer remains
`/home/flask/.tw2-releases/9b02f007d90a26b605e2217b80188109e6f48add`;
backend source paths match current main. Previous frontend for rollback:
`/home/flask/web-react/releases/build-eb3975d50232c57c921d965f60d21345d4ec18d5`.
Activation lock released after the non-forced main update and parity proof.
No staging or production change; this is fast-dev completion, not staging qualification.

Evidence: [screenshots, width receipts and repeatable browser check](evidence/TW-TASK-0012-nowrap-20260928/).
The final compiled bundle and then live served bundle each passed a single-page
22-position actual splitter sweep at viewport 1046x545: approximately 623-831px
actual toolbar widths, one heading row, all controls in bounds, no heading text
overlap, visible date/ticker values. HLT / 2026-09-28 / 141 calendar days / 10
years reproduced the original inputs. Additional final-artifact checks at
1440x900 and 1745x900 cover the 20%-40% splitter endpoints/intermediate positions
and both sides of the 1040px compact transition (1039.7/1041.9px).
Days selection changed to 140, showing compact `140` while the native option and
hover title retained `140 days`. MFE toggled. Best Waves retained the full native
choice `12/13-02/13 L SR:4.26`; choosing it resets the action selector to its
existing placeholder behavior. The overlay never rewrites option values/labels.
`/healthz` reported database/frontend OK; the live browser loaded main.7fb35429.js.

Independent root verification used the original user Chrome session with native
110% zoom (devicePixelRatio 1.1): original 1046x545 CSS viewport, 782.713px
toolbar, all 15 headings at y=71, toolbar height 59.97px. An actual pointer drag
to 40% left panel produced 622.827px: all 15 headings remained one row, with no
select/input/button/title bounds overflow and visibly readable controls. The
user had fullscreened the window during implementation, so the reviewer used
a supported temporary 1151x600 viewport override to reproduce the original CSS
viewport while preserving native zoom. A real drag near 20% also passed at
831.378px with all 15 headings on one row (y=72, height 59.97px). The reviewer
opened the native Days selector at 623px and escaped without changing the value.
The temporary viewport override was cleared. Exact divider restoration was not
completed before the user resumed testing, so no restored divider state is
claimed. Afshin subsequently confirmed that all fixes worked.

Light-theme title-on at 623px passed with visible values/carets. Title-off at
623px remained 19px high with zero headings; its pre-existing clipping was not
changed or presented as a successful fit. Pixel 5 emulation at 390x844 retained
identical control geometry against the prior eb3975d5 artifact (64px toolbar,
same nine top-row headings and same existing mobile bounds limitation). Mobile
layout/persistence paths were not redesigned. Verification is limited to the
recorded browsers/viewports, not an exhaustive device audit.

Next action: none for this dev fix. Staging qualification only after explicit
request. No migrations, environment configuration, or backend restart required.

## Underline styling verified on dev (2026-09-30 UTC)

Source commit `f4d8127a1a6395a3c3c8a0271453b0d95e5762bd` advanced main without force. It changes only `web-react/src/components/styles/SeasonalBarChart.css`: title text gains an underline and offset, while the desktop title fill and border are removed. Existing theme text colors, headings, responsive abbreviations, single-row sizing, controls, and settings logic remain as before. Tara knowledge did not describe title backgrounds, so it required no update. No engine math, backend code, configuration, or migration changed.

The clean source built with `ops/build_react_release.sh` (existing Browserslist/lint notices only). The candidate was rendered with real dev HLT data at a 1046px CSS viewport and actual toolbar widths 623, 782.5 and 831.7px: all 15 titles remained on one row, with transparent backgrounds, zero border width, underlined text, and no control overflow or clipped values. At a 1745px viewport, the 1385px toolbar also kept one row and no overflow. The candidate wide check's optional compact-select interaction assertion did not apply because that wide layout uses a normal select; its layout and styling assertions passed. The narrow candidate interaction check passed Days 140, Best Waves and MFE. With titles off at 1280/1300px, no title row appeared and the toolbar retained its compact height. Screenshots: [live 623px](evidence/TW-TASK-0012-underline-20260929/dev-623.png), [live 783px](evidence/TW-TASK-0012-underline-20260929/dev-783.png), [candidate wide](evidence/TW-TASK-0012-underline-20260929/candidate-wide.png).

Dev frontend pointer is `/home/flask/web-react/releases/build-f4d8127a1a6395a3c3c8a0271453b0d95e5762bd`; previous pointer `/home/flask/web-react/releases/build-79fcba0be29af546cfd2ac01b1042b8405382b60` is retained for rollback. A live nginx/capture-bot browser loaded the served build and repeated the 623/783/820px narrow checks, including title style, one-row geometry and working Days/Best Waves/MFE interactions. `/healthz` reported database/frontend OK; the served CSS hash matched the active artifact. Current main has no `appserver` or `web` source difference from the active backend at `9b02f007d90a26b605e2217b80188109e6f48add`. Dev activation lock was released. Staging and production were not changed or verified. Next action: qualify staging when Afshin requests its deployment.
