# TW-TASK-0013: Tara knowledge for recent Wave Viewer controls

- Status: in-progress
- Confidence: reproduced from current main source and completed dev records
- Priority: P3 - keep Tara's UI explanations accurate
- First observed / last updated: 2026-09-28 03:27 UTC
- Executor/session/claim time: Codex `/root/tara_feature_knowledge`, 2026-09-28 03:27 UTC
- Authorization: Owner requested a knowledge-only Tara update for recently shipped UI features. Routine dev activation included; staging and production excluded.

## Goal, Scope and Acceptance

Update Tara's runtime product knowledge for the shipped Wave Viewer toolbar title switch, the two Avg Gain hover tips, and the corrected Wave Info rows. Tara should accurately explain locations, labels, and behavior without claiming she can toggle toolbar titles or adding a UI control action. Preserve TradeWave's engine metrics and existing Tara actions.

## Evidence and Investigation

Current main `d1ef73c4d01da18776abc1acd1416930b53a3337`; `docs/tasks/TW-TASK-0012.md`, `TW-TASK-0010.md`, and `docs/bugs/TW-BUG-0018.md` record dev-verified behavior. `chatbot_knowledge.txt` lacks toolbar title and short Avg Gain tip facts and describes obsolete separate Trend Long/Trend Short Wave Info rows. Source: `SeasonalBarChart.js`, `DesktopLayout.js`, `TradeDetail.js`, `VisualTable.js`. Further exact source check pending.

## Acceptance and Regression Checks

Review the KB diff against shipped source and records. Run a focused Tara knowledge test or direct prompt check and verify live dev after appserver activation. No new `set_view` or settings action. Tests and live verification pending.

## Implementation and Handoff

Repository `afshinmoshrefi/tradewave-tw2`; branch `codex/tara-ui-knowledge-20260927`; worktree `/home/tradewave-worktrees/tara-ui-knowledge-20260927`. Claim published on main; source and integration SHAs pending. No migration, configuration, or React build expected. Appserver restart required because Tara's KB loads at startup. Rollback pointer and exact test evidence pending. Next: implement source update and focused validation.

## Environment Verification

Dev: pending. Staging: not checked. Production: not checked.

## History

- 2026-09-28 03:27 UTC, Codex `/root/tara_feature_knowledge`: Claimed knowledge-only UI update. Next: edit runtime KB, test, activate on dev.

