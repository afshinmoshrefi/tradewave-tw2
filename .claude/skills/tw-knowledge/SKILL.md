---
name: tw-knowledge
description: Capture AND improve the TradeWave/SMN knowledge base so facts are written ONCE, in the right home, and never re-derived. Use at the END of any substantive TradeWave task (a change or clarification to architecture, a data flow, an invariant, a tier/feature, a deploy step, a price, a decision + its rationale, or a hard-won gotcha) - and whenever you catch yourself re-deriving something that should already have been written. Also use for a periodic consolidation pass when the knowledge base is fragmented. This is the self-maintaining-memory protocol; CLAUDE.md enforces running it unprompted.
---

# TradeWave knowledge maintenance (self-improving memory)

The goal: the owner should never have to re-explain how TradeWave works or what was
decided. Every non-obvious fact gets written ONCE, in its canonical home, and is improved
in place over time. **Re-deriving a fact you could have recalled is a defect** - the fix is
to write it down now so the next session recalls it.

Run this at the end of substantive TradeWave work, without being asked.

## The core principle: write once, improve in place, never fragment
The #1 failure mode is fragmentation - the same fact scattered across many half-overlapping
notes, so it gets re-derived. Prevent it: SEARCH first, UPDATE the canonical file in place,
and DELETE/merge anything that now duplicates or contradicts it.

## Two homes for knowledge (decide which, every time)

1. **Implementation truth -> `docs/TRADEWAVE_ECOSYSTEM.md`** (in the repo, code-verified, committed).
   HOW TradeWave is built: architecture, components, data flows, the tier/entitlement +
   ENFORCEMENT model, invariants/landmines, deploy/ops, the TW1<->TW2 mapping. Per CLAUDE.md
   this doc is updated in the SAME commit as any architecture/flow/invariant/path change, and
   it WINS over any memory note that disagrees. If a durable implementation fact is currently
   only in a memory note, PROMOTE it into this doc and leave the memory note as a pointer.

2. **Working knowledge -> memory files** (`/root/.claude/projects/-home-flask/memory/`,
   indexed by `MEMORY.md`). Cross-session context that is NOT derivable from code or git:
   project status/goals/deadlines, decisions + WHY, owner preferences, in-flight gotchas,
   external pointers. Memory POINTS to the ecosystem doc for implementation detail; it does
   not duplicate it.

   Canonical memory categories (one obvious destination per kind of fact):
   - `user_*` - who the owner is (role, expertise, preferences).
   - `feedback_*` - how to work: a correction or a confirmed approach, WITH the why and how-to-apply.
   - `project_*` - ongoing work: goal, state, decisions, rationale (convert relative dates to absolute).
   - `reference_*` - reusable playbooks + pointers to external resources (URLs, dashboards, tickets).

## Procedure (every time)
1. **Search before writing.** grep the memory dir AND `docs/TRADEWAVE_ECOSYSTEM.md` for the
   topic/keywords. Find the file that already owns it.
2. **Update in place, or create.** If a file owns the topic, edit THAT file (correct, extend,
   re-date). Create a new file only if the topic genuinely has no home. One topic = one file.
3. **Promote implementation facts.** If the fact is "how it works" (architecture/flow/invariant/
   enforcement/deploy/path), put it in the ecosystem doc (the right section), not a memory note.
4. **De-fragment as you go.** If the topic is spread across 2+ memory files, MERGE into the
   canonical one and reduce the others to a one-line `[[pointer]]` or delete them.
5. **Delete what is wrong or stale.** Remove superseded/contradicted content - never leave two
   files disagreeing. The ecosystem doc and the newest verified note win.
6. **Index discipline.** Keep `MEMORY.md` to exactly one line per memory file (`- [Title](file.md) - hook`).
   Add a line for a new file; remove the line for a deleted one. Never put content in MEMORY.md.
7. **Link.** Cross-reference related entries with `[[name]]` (the other file's `name:` slug).

## Quality bar - capture the non-obvious, skip the obvious
Write the WHY, the decision + rationale, the gotcha, the invariant, the file:line pointer, the
owner preference. Do NOT write what the code, CLAUDE.md, or git history already states (code
structure, a routine fix, things re-readable in seconds). For `feedback_*`/`project_*` include
**Why:** and **How to apply:**. Verify a claimed file/function/flag still exists before recording
it as current. Follow house style in any user-facing text you touch (no em-dashes, AP Title Case
headings, no third-party competitor names).

## The self-improving loop (the part that compounds)
At the end of the task, ask yourself:
- **Did I re-derive anything** (trace a data flow, recompute a tier mapping, rediscover a gotcha)
  that should already have been recorded? -> write/fix it now; that re-derivation was the KB
  telling you it has a gap.
- **Did a memory note turn out wrong or incomplete** while I worked? -> correct it now.
- **Is a fact now scattered?** -> consolidate it into one home.

## Periodic consolidation pass
When the index is large or you notice the same thing in several places, do a consolidation:
cluster overlapping files and merge each cluster into one canonical file; retire DONE/obsolete
notes into a single historical note (or delete); promote durable implementation facts into the
ecosystem doc; reconcile any memory that disagrees with the doc; trim MEMORY.md to match.

## Done-check
- [ ] Every non-obvious fact/decision/gotcha from this task is written in its canonical home.
- [ ] Implementation truth landed in `docs/TRADEWAVE_ECOSYSTEM.md` (not just a memory note).
- [ ] No new duplicate file; existing owners updated in place; stale content deleted.
- [ ] `MEMORY.md` index matches the files on disk (one line each).
- [ ] Anything I re-derived this session is now recorded so it won't be next time.
