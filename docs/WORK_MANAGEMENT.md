# Shared Work Management

## Purpose and Scope

Afshin uses ChatGPT/Codex, Claude Code, and potentially Grok or other agents interchangeably. No provider is the default owner of a project. The project must retain enough context for another capable agent or human to continue without the previous conversation, account, private memory, or local machine.

This protocol is reusable for every project adopting it. Keep one canonical copy per project, link it from that project's agent entry points, and fill in its project map. Adoption here covers TradeWave and its local orchestrator; it does not silently configure unrelated repositories or external AI accounts.

## The Big Picture

The owner sets goals, priorities, and authorization. A coordinating session selects authorized work and tracks dependencies. An implementer investigates and changes the code. A verifier checks the recorded acceptance criteria. These are responsibilities, not permanent people or AI brands; one session can perform several roles, but must identify self-verification honestly. Separate review is useful for risky changes when authorized and available.

The shared records are the handoff between those roles. Choosing an AI by demonstrated suitability or randomly does not change the evidence required. An automated manager follows the same rules and authorization limits. A backlog entry alone is never permission to fix, deploy, purchase, or send messages. This protocol creates no background scheduler or automatic assignment service.

## Where Information Lives

| Information | Canonical home |
|---|---|
| Operating protocol and project map | This document |
| Open and resolved bugs | `docs/bugs/README.md` and one record per bug |
| Features and other substantive work | `docs/tasks/README.md` and one record per task |
| Architecture, contracts, invariants | Existing project architecture documentation |
| Release authorization, gates, locks | Existing release policy and release records |
| Repro evidence | Repository-relative files or durable shared artifact links with access instructions |
| Private agent memory | Short discovery pointers to the above; never the sole task state |

Bug records own defect status, reproduction, investigation, fix and verification history. Architecture documentation owns implementation facts and links to bug IDs for current status. Do not keep competing status lists in private memories, chats, or architecture prose. A historical observation retains its date and source version; never reinterpret it as a current environment check.

## Start or Resume

1. Read the project's agent instructions, this protocol, the bug/task indexes, and relevant architecture and release policies. Fetch the current shared Git state before relying on local records.
2. Search for an existing bug or task before creating one. Use the same bug ID for recurrence of the same failure, with a new dated event. Link related symptoms; split them if they need independent fixes or verification.
3. Read the whole relevant record and its evidence. Confirm environment, source revision, authorization and current runtime. If evidence is inaccessible, say exactly what is missing and reproduce what is possible; do not silently mark it verified.
4. Claim authorized implementation work before editing code. Record executor/provider, unique session ID, UTC claim/update time, branch, worktree and next step. Push the claim to the shared repository using a non-forced update, then refetch it. Separate branches alone do not establish exclusive ownership. Resolve a simultaneous claim before overlapping edits; the first accepted shared claim owns the work until transferred.
5. A coordinator can serialize claims on the default branch or explicitly designate a shared coordination branch. Without a designated branch, use the default branch. Honor release freezes: preserve a proposed claim on a task branch and coordinate before proceeding when shared state is frozen. Follow existing Git/worktree policy for all updates.
6. Work within the owner's authorization. Recording a newly discovered bug is allowed during an authorized investigation; expanding implementation scope requires matching authorization. Record decisions and their reasons as they arise.

## Ownership and Continuity

Update the record at meaningful milestones and before stopping or handing off, including unfinished work. Do not produce a commit for every minute of activity. A long-running session should checkpoint its claim at least hourly when practical. A stale timestamp is a signal to check the owning session and pushed work, not permission to overwrite it. After confirming the owner stopped, record an explicit takeover with reason and preserve its commits. If ownership cannot be established, work on an independent authorized item or ask for coordination.

IDs are stable: TradeWave uses `TW-BUG-NNNN` and `TW-TASK-NNNN`. Allocate from the fetched index and resolve collisions before pushing. Never renumber an already shared ID; duplicates retain a link to the canonical record.

## Status and Completion

| Status | Meaning |
|---|---|
| open | Recorded; may be confirmed or still suspected, as stated separately |
| in-progress | An identified session owns authorized work |
| blocked | Exact blocker and next action recorded; ownership remains explicit |
| fixed | Exact pushed code commit exists; required live verification still pending |
| verified | Recorded acceptance criteria passed in the explicitly named environment and revision |
| deferred | Intentionally postponed, with reason and any revisit trigger |
| duplicate / not-a-bug | Evidence-based disposition and canonical link or rationale |

Keep resolved records. Reopen a regression with its failing revision, environment and evidence; retain the earlier successful fix history. Use priority P1 for severe user disruption or silent change of user intent, P2 for other confirmed user-visible failures, P3 for minor impact, and P0 for an urgent widespread outage or similarly critical incident. Priority is an assessment, not scheduling authorization.

Always record confidence separately from status: reported, suspected, or reproduced. Keep observations, inferred mechanisms and confirmed causes distinct. A green build, a test script exiting zero, or HTTP 200 is not proof that a user-visible bug is fixed. Verification must exercise the original failure and relevant neighboring cases. Record failed checks and tests not run, including browser/device limits. Never invent results.

Record deployment per environment: not checked, not deployed by this task, deployed/unverified, or verified, with SHA/artifact, time and evidence. `verified on dev` does not imply verified on staging or production, or full environment parity. Documentation-only completion requires reviewed, linked, committed shared records, not a runtime deployment.

## Required Handoff Before Stopping

Every substantive bug fix or feature task must leave:

- Goal, user-visible outcome and scope; exact authorization and explicit exclusions.
- ID/status/priority, executor/session, update time and ownership transfer if any.
- Reproduction or feature acceptance criteria, expected versus actual behavior, preconditions and recovery.
- Evidence, source/runtime versions, environment, browser/device, data inputs and test limits.
- Confirmed facts, hypotheses, decisions with reasons, attempted approaches and their results.
- Repository, branch, worktree, full pushed commit SHAs and clean/WIP state. A commit cannot contain its own hash; identify itself by `git log -1 -- <record>` and publish the resulting SHA in the completion receipt or next handoff.
- Changed files and why; tests/commands, results, evidence, pending checks and regression risks.
- Dependencies, configuration/migration/build needs, release state, rollback and preserved unrelated changes.
- A concrete next action that another agent can execute without asking the owner to retell the history.

Use the bug and task templates. Unknown fields must say unknown or pending, not remain misleadingly blank. Store sanitized evidence without credentials, cookies, tokens or personal customer data. Include enough inputs and commands to repeat the check; private host paths can supplement but cannot replace portable evidence. If an artifact cannot be shared, document access requirements and a safe recreation procedure.

## Managing the Backlog

At the start/end of relevant work, update the index and affected records together. A review summarizes open priorities, blocked dependencies, recent verified fixes and the next authorized action. Do not claim a periodic review is running unless a scheduler was explicitly set up. Respect an intentional deferral. Record recurring patterns so later changes exercise known regressions.

Features use task records with acceptance criteria and the same handoff fields. Bugs discovered during a feature get their own linked IDs. Completion updates code, record, index and canonical architecture facts together where possible; later deployment evidence can be a follow-up documentation commit.

## TradeWave Project Map

- Repository: https://github.com/afshinmoshrefi/tradewave-tw2 ; shared default branch `main`.
- Entry points: `AGENTS.md` and `CLAUDE.md`. Configure any other agent to read AGENTS.md; do not assume an agent automatically discovers it.
- Architecture: `docs/TRADEWAVE_ECOSYSTEM.md`; methodology: `docs/TRADEWAVE_METHODOLOGY_AND_FEATURES_KB.md`.
- Git: `.claude/skills/tw-git-release-workflow/SKILL.md`; releases: `docs/RELEASE_PROCESS.md`; knowledge: `.claude/skills/tw-knowledge/SKILL.md`. Directory names do not limit their applicability to one provider.
- Dev host: SSH alias `tradewave-vm`, TW2 `192.168.1.176`. Git and repository edits run as `flask`. Task worktrees live under `/home/tradewave-worktrees/`. Preserve the dirty shared `/home/flask` checkout.
- Read existing release policy for authorization. Application fixes normally include verified dev completion; documentation does not activate runtime. Staging and production have separate gates. This protocol does not weaken those gates.
- TradeWave owns financial values: preserve exact engine results. Do not calculate a replacement or interpolate missing leap-day values in clients. Suspected engine math changes require agreement with Afshin. Opportunity days are inclusive calendar days: `end = start + (days - 1)`; `years` is a string.
- Historic audit baseline: September 15, 2026, frontend `fce41885ec8fbdc70fabc1fb56bde38c98339396`, bundle `main.0ee1de72.js`. Recheck runtime before a new investigation.
- Known separate release dependency at that baseline: active backend `/home/tradewave-worktrees/restore-overlay-integrated-20260912` retained an uncommitted OppList4 sparse-day/empty-response repair (19 insertions, 4 deletions in `appserver/appserver/appserver.py`) and a separate OppTable guard in that worktree. Preserve and investigate separately. These chart records do not establish full main/dev parity or authorize integrating those changes.

## Adopting This in Another Project

Copy this protocol and the two templates, replace the TradeWave project map and ID prefix, and connect the project's actual instruction entry points to its canonical copy. Identify the repository/default branch, architecture, build/test commands, environment access, deployment boundaries, record locations and ownership mechanism. Preserve that project's existing policies. Do not copy TradeWave paths or assume its deployment permissions apply elsewhere. The next agent must confirm it has read the shared instructions; a provider-specific memory may store only the entry point and owner preference.
