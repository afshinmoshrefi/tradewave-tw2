# TW-BUG-0025: SMN article editor loses migrated private images and charts

- Status: in-progress
- Confidence: reproduced by the coordinator in the user's actual Chrome editor; documentation agent has not independently rerun the browser reproduction.
- Priority: P2 - all five Microsoft article images/charts are broken in the edit window.
- First observed / last updated: 2026-10-03T10:39:44.243605+00:00
- Executor/session/claim time: Codex coordinator `/root` and Sol 6.1 implementation agent `/root/membership_builder`; session `01a0ff6b-e439-79a3-9aa3-9d70763f9e85`; claimed 2026-10-03T10:39:44.243605+00:00. `/root/preview_builder` owns this shared record only.
- Authorization: fix editor preview asset resolution after private-corpus migration and verify on Dev. Preserve the existing MSFT draft, protected-reader entitlement checks and private assets. No financial/math/provider changes, unrelated edits, public asset exposure or production writes.

## User Impact and Reproduction

SMN Dev source/main `2b00e6cbc8ae1ce363fb601cf91a9b0ea1ef6d5b`, active `/opt/smn-worktrees/smn-promotion-links-20261003` on .180. Genuine user Chrome tab `333161940` is editing MSFT draft `517ef29290284f369147fca49e99f50d`, version4, for `/editions/2026-10-02/MSFT/article.html`.

1. Open the Microsoft article edit window through the authenticated publishing dashboard.
2. Inspect its article preview and image loading.
3. Expected: all five retained images/charts load from an authorized private revision/draft asset resolver.
4. Actual: all five image elements have `naturalWidth=0`. Relative asset references resolve to `/editions/2026-10-02/MSFT/assets/...`, where migrated assets are no longer anonymously available.

Do not save, regenerate, replace, delete or otherwise mutate this user's draft during reproduction or testing.

## Evidence and Investigation

Coordinator observed the actual browser failure at the source above. The broken resolved URL and zero image dimensions are confirmed; the exact editor rendering/resolver defect is still under investigation. Private-corpus migration deliberately denies old raw asset routes; reopening those public routes is not an acceptable fix. Related feature: [TW-TASK-0018](../tasks/TW-TASK-0018.md).

Portable automated regression and sanitized live browser evidence are pending the implementation. No credentials, cookies, tokens or draft article content belong in this record.

## Acceptance and Regression Checks

- Original MSFT edit window: all five images/charts render with nonzero natural dimensions in the real browser.
- Existing draft ID/version/content/dirty state and source assets are preserved; no MSFT draft writes.
- Relevant authenticated saved/draft/revision preview paths resolve only retained allowlisted assets and preserve version binding.
- Unknown asset, traversal and stale/unavailable revision handling fail closed. Anonymous access does not acquire private full-body/assets; reader entitlement rules remain intact.
- Focused tests and actual Dev browser smoke bind exact pushed fix/main/live SHA. Tests have not run yet.

## Implementation and Handoff

Application repository: SMN. Coordinator prepares code worktree `C:/Users/afshin/Documents/TradeWave Main Orchestrator/smn-editor-assets-20261003`, branch `codex/smn-editor-assets-20261003`, from current SMN `origin/main` (`2b00e6c...`). Implementation ownership is limited to `blog/article_editor_routes.py`, `blog/article_editor.py` and directly related asset-resolver tests only when necessary. Code SHA: pending; activation/browser verification owned by coordinator.

Documentation repository: TW2. Fresh worktree `C:/Users/afshin/Documents/smn-editor-assets-bug-record-20261003`, branch `codex/smn-editor-assets-bug-20261003`, from current TW2 main `f9be13c633b94c2008774845cfd229d38ae36fc2`. Initial claim changes this record and bug index only. Claim commit is identified by `git log -1 -- docs/bugs/TW-BUG-0025.md`; acceptance requires nonforced shared-main push and refetch before code edits. No app activation is needed for this claim.

Next: after shared claim acceptance, implementation agent investigates existing private-store/editor resolver patterns and makes the smallest fix; coordinator activates the exact tested candidate on Dev and repeats original browser and private-access checks. Documentation agent then updates this bug/index and one appropriate ecosystem implementation fact from actual evidence. Preserve unrelated work and all user state.

## Environment Verification

Dev: original failure reproduced; fix/activation/verification pending. Staging: not deployed/checked by this task. Production: unchanged/not checked.

## History

- 2026-10-03T10:39:44.243605+00:00: reproduced editor-only image/chart failure; claimed narrow fix and explicitly preserved MSFT draft and private-reader authority. Shared claim publication/refetch is the immediate next action.
