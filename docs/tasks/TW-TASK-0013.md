# TW-TASK-0013: Tara knowledge for recent Wave Viewer controls

- Status: verified on dev
- Confidence: reproduced and live-verified
- Priority: P3 - keep Tara's UI explanations accurate
- First observed / last updated: 2026-09-28 03:27 / 03:37 UTC
- Executor/session/claim time: Codex `/root/tara_feature_knowledge`, 2026-09-28 03:27 UTC
- Authorization: Afshin requested a knowledge-only Tara update for recently shipped UI features. Routine dev activation included; staging and production excluded.

## Goal, Scope and Acceptance

Tara explains the shipped Gain-Loss Bar Chart toolbar headings and the default-on, persistent Settings > General > Show toolbar titles switch, including the compact title-off benefit. Tara has no action for this setting and must not claim to have changed it. She also explains the two Avg Gain values and their short hover tips, and the current Wave Info rows without inventing calculations or offering obsolete Trend Long/Short rows. No UI control capability was added.

## Evidence and Investigation

At main `d1ef73c4d01da18776abc1acd1416930b53a3337`, `chatbot_knowledge.txt` omitted the new headings and short Avg Gain tips and described obsolete separate Trend Long/Trend Short Wave Info rows. The current source and dev-verified records `TW-TASK-0012`, `TW-TASK-0010`, and `TW-BUG-0018` establish the actual behavior. `tara_prompt_context.py` also lacked topic routes for these questions; `chatbot.py` had a stale hardcoded Wave Info summary. The correction updates product knowledge and its prompt routing only. TradeWave remains the sole source of all metric values.

## Acceptance and Regression Checks

- On the clean integration candidate, `/home/flask/venv/bin/python -m pytest -q tests/test_tara_prompt_context.py`: 22 passed. `py_compile` for `chatbot.py` and `tara_prompt_context.py` passed; `git diff --check` passed. Candidate frontend preflight `python -m web.react_build` passed against the unchanged active React artifact.
- The Tara activation script passed its deterministic live gate (6/6 markers, no action) and model-bound Luna gate (HTTP 200, no action, no fallback).
- Authenticated live dev `/chatbot/chat` questions with an empty viewer and a level-6 test JWT:
  - "How do I hide the toolbar titles?" -> "Settings > General > Show toolbar titles" and explains that the choice is saved; `actions=[]`.
  - "What do the two Avg Gain values mean?" -> winning-years average and all-years average; `actions=[]`.
  - "What is in Wave Info?" -> Percent Profitable, Sharpe Ratio, conditional TradeWave Ratio, and direction-matched Trend Alignment with change arrow; `actions=[]`.
- No rendered browser check was run because this task changed Tara's answers, not UI rendering. The cited UI records contain prior browser verification. No lower-tier live account was used; TWR gating was read from current source and prior verification.

## Implementation and Handoff

Repository `afshinmoshrefi/tradewave-tw2`. Shared claim `236154b45ad6da634b479f193a1121017f994d7b`; pushed source branch `codex/tara-ui-knowledge-20260927` at `b71455319fc36d13c113a46adbc5900caaa5a79b`; pushed integration branch `codex/tara-ui-knowledge-integration-20260927` and main at `9b02f007d90a26b605e2217b80188109e6f48add`. Isolated dev worktrees: `/home/tradewave-worktrees/tara-ui-knowledge-20260927` and `/home/tradewave-worktrees/tara-ui-knowledge-integration-20260927`; clean at handoff. Immutable active backend source: `/home/flask/.tw2-releases/9b02f007d90a26b605e2217b80188109e6f48add`.

Changed `appserver/appserver/chatbot_knowledge.txt` for facts, `tara_prompt_context.py` for narrow selection, `chatbot.py` for its existing summary, and `tests/test_tara_prompt_context.py` for topic-routing regression. No schema, action, engine math, React, migration, dependency, or configuration change. `docs/TRADEWAVE_ECOSYSTEM.md` already describes the current toolbar and named Wave Info fields, so no duplicate architecture note was added. Backend restart was required because Tara loads the knowledge file at startup. Previous app pointer was `/home/tradewave-worktrees/scenario-polish-20260927`; rollback script: `/root/tradewave-snapshots/tara-parity-dev-20260928T033457Z/rollback.sh`. The dev activation lock was released. This record and the task index are the final documentation-only main advance; no further runtime activation is needed because the application tree is unchanged.

Next: owner review of Tara's wording on dev. Staging qualification requires a separate request.

## Environment Verification

Dev: verified 2026-09-28 03:35 UTC by Codex through authenticated live Tara requests on backend `9b02f007d90a26b605e2217b80188109e6f48add`. `/chatbot/runtime-fingerprint` returned the same release SHA and fingerprint `3710941033dbde1e7943bc4bb314537a4dcf220c6be6c7c811fb2f78f4054967`. Both appserver and apiserver were active; current main and active backend SHA matched. React pointer remained `/home/flask/web-react/releases/build-00e3af9266ac4b208f81b392979a105786e20354`. Staging: not checked. Production: not checked.

## History

- 2026-09-28 03:27 UTC, Codex: Claimed TW-TASK-0013 on shared main before editing.
- 2026-09-28 03:32 UTC, Codex: Pushed the focused source commit; prompt-context tests passed.
- 2026-09-28 03:35 UTC, Codex: Activated exact integration candidate on dev, passed live gates and three feature questions, advanced main, proved parity, and released lock.

