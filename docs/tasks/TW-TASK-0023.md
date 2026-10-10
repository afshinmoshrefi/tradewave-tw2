# TW-TASK-0023: One-time securities menu customization tip

- Status: in-progress
- Executor/session/claim: Codex, securities-menu-tip-20261010, 2026-10-10T13:36:56.488697+00:00
- Authorization: Owner accepted the proposed first-click popover, per-account acknowledgment, Customize Lists and Got It buttons, and settings help replay. Routine Dev activation included; staging/production excluded.

## Goal and Acceptance

First intentional mouse/touch/keyboard opening of the market dropdown shows a brief anchored tip explaining market hiding and published-list visibility. Both buttons persist acknowledgment per account; Customize Lists opens existing securities settings. Settings help can replay the explanation. Existing menu selection works normally after acknowledgment. No tip on page load; wait for account preferences to load; no acknowledgment on failed save. Test desktop and narrow mobile, persistence across fresh browser contexts, help replay, and list opt-out via actual desktop settings.

## Investigation and Plan

App owns account/catalog/preferences; shared SelectBox renders each securities dropdown. Add a focused tip component and activation callback through UserContext. Store acknowledgment separately from resettable list preferences using the existing authenticated appserver token flow. Connect Customize Lists to desktop inline settings and existing mobile securities settings. Desktop inline published controls still use legacy enabled_published; align them with TW-BUG-0032 hidden_published so customization actually works.

## Evidence, Handoff and Release

Repository afshinmoshrefi/tradewave-tw2. Branch codex/securities-menu-tip-20261010; worktree /home/tradewave-worktrees/securities-menu-tip-20261010. Starting source 8097f90e. Tests/build/live verification pending. No dependencies or migration expected. Rollback pointers will be retained before activation. Next: implement, focused-test, build, push and live-verify Dev. Staging/production unchanged.
