# TW-TASK-0021: Adaptive historical years headings

- Status: verified on dev
- Executor/session/claim time: Codex /root/toolbar_titles; 2026-10-08
- Authorization: rename historical Years headings, verify and activate on Dev only; staging/production excluded

## Goal, Scope and Acceptance

Display "Years analyzed" for the Wave Viewer and Opportunity table historical-year controls when desktop space allows, and "Years" in narrower desktop layouts. Keep mobile headings hidden. Preserve probability-year title, all options/calculations, title/tooltip settings and control behavior.

## Evidence and Investigation

Claimed from origin/main `37a0f7670b4fbb56a20d82e00fa4accd2f7e97fe`. Fresh task worktree `/home/tradewave-worktrees/years-analyzed-headings-20261008`, branch `codex/years-analyzed-headings-20261008`. Rendered baseline measurement: at a 1745px viewport the Opportunity pane was 523.5px wide and the full heading measured 71.7px; a 1440px viewport provided a 432px pane where the heading also fit. The responsive rule uses the Opportunity pane as its container, so manual split-panel resizing changes the heading without relying on viewport width.

## Implementation and Handoff

Code commit `15464c2bb7d2064f32fa51b679e9a3f4bb0fd867` is pushed on the task branch and main. One React release build passed with the exact SHA stamp. Live Dev at 1920px showed `Years analyzed` for both chart and Opportunity table; 1440px/432px Opportunity pane showed the full heading, and a manually narrowed 350px pane plus a 1280px/384px pane showed `Years`. The chart uses its existing ResizeObserver width modes, showing full at 1339px toolbar width and compact at 1003px and 891px. Probability title stayed `Prob. years`; title-off and Pixel 5 mobile showed no headings. Hover on historical-years headings showed the existing tooltips, while the corresponding select did not. Screenshots: [wide Dev](evidence/TW-TASK-0021/years-analyzed-wide.png) and [narrow pane Dev](evidence/TW-TASK-0021/years-analyzed-narrow.png). Active frontend build pointer/stamp and copied artifact matched the tested code; dev lock released. The pre-existing backend webinar/config drift was not touched. Staging and production excluded.

## History

- 2026-10-08: Task claimed before source edits. Focused build and rendered Dev verification passed; code integrated to main, active frontend parity proven, lock released.
