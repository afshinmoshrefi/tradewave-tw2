# AGENTS.md — read this before touching TradeWave / SMN code

This file exists for **any** AI coding agent (Codex, Cursor, Claude, Copilot, or
otherwise). Claude Code also reads `CLAUDE.md`; the rules below are identical.

---

## The single most-violated rule: how a TradeWave "day" is counted

**A TradeWave "day" is a CALENDAR day.** Never a trading day. Never a business day.

**The entry day counts as day 1.** The analytics engine does not count it, so all
original math uses `daysOut = days - 1`. The displayed count was later bumped by
+1 purely so that month windows read naturally — `Jul 1 → Jul 31` should read
**"31 days"**, not 30.

That +1 is **cosmetic and applies to the label only. It must never be added to
the end date.**

```
end_date = start + (days - 1)          # correct, everywhere
end_date = start + days                # WRONG — this is the recurring bug
```

Worked examples:

| Start | days | End date | Reads as |
|---|---|---|---|
| 2026-07-21 | 30 | **2026-08-19** | "30 days" |
| 2026-07-01 | 31 | **2026-07-31** | "31 days" (all of July) |

**Do not re-derive this rule.** It has repeatedly confused both the owner and AI
models. If you find code doing `start + days`, it is wrong — fix it to `days - 1`.

### If you are writing a prompt, a gate, or an LLM reviewer

State the ground truth **positively, before** naming the violation:

> ✅ "TradeWave windows are measured in CALENDAR days. Flag it only if the article
>    calls them trading days."
> ❌ "Hard issue: TradeWave days called trading days."

On 2026-07-21 the bare-negative form was read **backwards** by an LLM reviewer,
which asserted "TradeWave patterns are defined over trading days" and **held a
correct article**. A rule a model can invert is a rule it will invert.

---

## Where the canonical facts live

- **TW2** (`192.168.1.176`, repo root `/home/flask`): `docs/TRADEWAVE_ECOSYSTEM.md`
  is implementation truth and **wins over any memory note**. Day counting is
  invariant **0A** in §11. Update that doc in the SAME commit as any change to
  architecture, a data flow, an invariant, or a path.
- **SMN** (`192.168.1.180` dev / `209.182.216.112:4369` prod, repo `/home/flask/blog`):
  see `CLAUDE.md` and `.claude/skills/tradewave-domain/SKILL.md`.

## Other facts that bite

- `years` is **always a string** — it may be a plain lookback (`"20"`) or a PE-cycle
  slice (`"pe2-10"`). Never coerce it to int.
- `ChartData4` returns the **current year as a zeroed row** (the window has not
  completed). Drop it before computing records, or a "10 for 10" pattern reports
  as "10 of 11".
- On arbitrary (non-detected) windows `ChartData4` returns `Trade Dir='long'`
  regardless of the true direction — **derive direction from per-year net returns**.
- Returns are percentages; raw prices are not exposed in TradeWave-facing output.
- Always state the sample size (`n` years) alongside any record or win-rate claim.
