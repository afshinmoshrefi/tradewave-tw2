# TW-BUG-0023: Homepage 100-Year Pattern countdown stuck at zero after the window opened

- Status: duplicate - of the homepage 100-Year Pattern card work in main commit 469d600 ("Show the live 100-Year Pattern cycle on the homepage", session "100 year pattern home page update"), which covers this acceptance (day N of 295 by Eastern date, window-open copy, no zero countdown); this record was never added to main
- Confidence: reproduced
- Priority: P2 - the public homepage states the window "begins September 27, 2026" and shows 0 days 00 hours 00 minutes after it opened
- First observed / last updated: 2026-09-29 00:25 UTC (Afshin screenshot) / 2026-09-29 00:40 UTC
- Executor/session/claim time: Claude Code (Opus 5.5), session `c7bd49c6-d749-4f1e-8339-9085bf677acd`, 2026-09-29 00:30 UTC; branch `claude/home-100yp-open-20260929`
- Authorization: Afshin reported the stale homepage; fix with verified dev completion. Staging and production need a separate request; production writes are human-executed.

## Goal, Scope and Acceptance

After 2026-09-27 00:00 ET the homepage card must say the window is open and count days (Day N of 295, days left) through 2027-07-18, then say the window closed and hide the counter. Before the open time the countdown is unchanged. Day counts follow the Eastern calendar date, including across the November DST change.

## Evidence and Investigation

Production https://tradewave.ai/ on 2026-09-29 served "next recorded window begins September 27, 2026"; the script clamps the remaining time at 0 (`Math.max(0,target-Date.now())`) and has no open state. The /100-year-pattern page already switches to "The nominal window is now open." (`site/100-year-pattern/100-year-pattern.html`). The homepage block is in `site/templates/index-dark-blue.html` (TW100 HOME COUNTDOWN), enabled by `TW2_HOME_100_YEAR_PATTERN_ENABLED`.

## Acceptance and Regression Checks

Pending.

## Implementation and Handoff

Pending.

## Environment Verification

Dev: pending. Staging: not checked. Production: not checked (still shows the stale countdown).

## History

- 2026-09-29 00:40 UTC, Claude session `c7bd49c6`: reproduced on production; fix in progress.
- 2026-09-29 00:45 UTC, Claude session `c7bd49c6`: Afshin clarified the report belonged to another session already working on it (its release 469d600c took the dev lock at 00:34:32 and contains all TW-TASK-0014 work). Withdrawn; no rollback run (it would overwrite that release). The other session was told that dev home.html at 00:34:14 came from this branch's template and needs regenerating from its candidate.
