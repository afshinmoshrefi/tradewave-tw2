# TW-TASK-0012: Chart Toolbar Control Titles

- Status: original title build restored on dev; visual redesign rejected and rolled back
- Confidence: reproduced
- Priority: P3 - improves control discoverability
- First observed / last updated: 2026-09-27 22:45 UTC
- Executor/session/claim time: Codex toolbar_titles / 2026-09-27 22:25 UTC
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

## History

- 2026-09-28, Codex `/root/toolbar_responsive_labels`: Claimed the user-requested responsive heading follow-up on current main `8539914749ee29450bea6afcc992147a6f24a600`. Branch `codex/toolbar-adaptive-titles-20260928`, clean worktree `/home/tradewave-worktrees/toolbar-adaptive-titles-20260928`. Scope: keep a desktop row while shortening only visible headings according to the chart container width; preserve full names, controls, title-off and mobile behavior. Dev only. Next: implement, build, inspect narrowed rendered widths, activate and verify.

- 2026-09-27 22:25 UTC, Codex: Claimed authorized feature. Next: inspect toolbar and settings, implement and verify.
- 2026-09-27 22:35 UTC, Codex: Implemented source and passed React build; another session currently owns the dev activation lock.
- 2026-09-27 22:44 UTC, Codex: Integrated latest main and activated candidate under dev lock; desktop and phone browser checks passed; non-forced main advance to `c2045a08` succeeded.

- 2026-09-27 23:10 UTC, Codex `/root/wave_info_dev`: Claimed user-requested visual follow-up; confirmed overlap on actual dev render.

- 2026-09-27 23:40 UTC, Codex `/root/wave_info_dev`: Completed visual follow-up on dev with browser screenshots and narrow-panel bounds check; no staging or production.

- 2026-09-27 23:50 UTC, Codex `/root/wave_info_dev`: User rejected visual redesign; restored original dev frontend and reverted redesign code on main.
