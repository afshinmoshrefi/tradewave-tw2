# TW-BUG-0037: Explorer row click leaves the chart blank when the pattern started before today

- Status: open
- Confidence: reproduced
- Priority: P1. Every free Explorer user who clicks an already-started pattern sees an empty Gain-Loss Bar Chart. On Monday 2026-11-23 all five DJ30 rows were dated 2026-11-21 or 2026-11-22, so every Explorer row click failed. It also blocks the mandatory level-1 Wave Viewer staging gate.
- First observed / last updated: 2026-11-23T19:15Z
- Executor/session/claim time: unassigned (found by Claude during staging qualification tw2-20261123-01)
- Authorization: documentation only. Repair needs an owner decision on intended behavior.

## User Impact and Reproduction

1. Sign in as an Explorer (level 1, DJ30) user on a day when the table lists patterns whose start date is before today (for example a Monday after a weekend).
2. Click any opportunity row.
3. Expected: the bar chart draws. Actual: the "Gain-Loss Bar Chart" placeholder stays and the statistics panel keeps "Loading statistics".

Strategist users are not affected (same flow passes). Rows dated today are not affected.

## Evidence and Investigation

- React requests `ChartData4/0/2026-11-21/UNH/13/10`. The appserver Explorer date-lock (`getChartData4`, `_is_date_locked` -> `date = todayDate`) answers for 2026-11-23 and echoes `request.entry_date = 2026-11-23`.
- `SeasonalBarChart.js` rejects any response whose echoed request differs from the requested view (`taraEffectiveResponseMatches`, reason `server_normalized_or_unverified_request`), clears the chart data and stops loading.
- Reproduced on dev with the release candidate frontend 9857c385 and with the current staging/production frontend 0c67bb84. Not introduced by release tw2-20261123-01. Production was not tested directly; it runs the same appserver and frontend code (0c67bb84).
- Evidence on dev: `/var/lib/tradewave/release-state/tw2-20261123-01/evidence/dev-browser-gate-explorer.json`, `dev-browser-strategist.json`.

## Acceptance and Regression Checks

Explorer row click on a past-dated row draws the chart (canvas in `.seasonal-barchart-parent`, `.barchart-background` gone) without weakening the response guard for other normalizations. Strategist flow unchanged.

## Implementation and Handoff

Pending owner decision: either the level-1 row click requests today's date (matching the date-lock the appserver enforces), or the guard accepts the documented Explorer date-lock normalization.

## Environment Verification

Dev: reproduced 2026-11-23. Staging: not checked. Production: not checked (same code).

## History

- 2026-11-23T19:20Z, Claude (staging release tw2-20261123-01): reproduced on dev with candidate and prior frontend; staging deploy paused on the mandatory level-1 gate.
