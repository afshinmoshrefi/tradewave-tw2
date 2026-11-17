#!/usr/bin/env python3
"""Summarize one judged Tara eval run, or compare several runs on their common questions.

    python tools/tara_eval/report.py --run baseline-dev                 # markdown to stdout
    python tools/tara_eval/report.py --run baseline-dev --examples 6    # more examples per cluster
    python tools/tara_eval/report.py --compare luna-low luna-med haiku55 sonnet55 luna-fullkb

Headline = share of questions whose judge verdict is `helpful`.
Root-cause buckets combine the judge's diagnosis with mechanical evidence recorded by the
runner (provider, protocol trace):
  shortcut_hijack      a deterministic/canned route produced the unhelpful reply
  retrieval_miss       legacy only: verdicts graded by judge v2 for code that still routed
                       three KB sections (before TW-TASK-0033). Judge v3 never emits it,
                       because the whole knowledge base is in Tara's prompt (TW-TASK-0036)
  missing_kb           the fact is not in the KB
  missing_tool_or_data needs data/actions Tara has no tool for, or the tool gave the wrong thing
  model_reasoning      model had the facts/context and still answered poorly
  wrong_fact           asserted something false although the truth was available
  (+ over_refusal, ui_action_error, verbosity_or_tone, error_or_empty, other)
"""

from __future__ import annotations

import argparse
import collections
import statistics
import sys
from pathlib import Path

from common import load_bank, read_jsonl

# USD per 1M tokens: (input, cached input read, cache write, output)
PRICES = {
    "gpt-5.6-luna": (0.20, 0.02, 0.20, 1.20),          # published list price (not invoice-verified)
    "claude-haiku-5-5": (0.10, 0.01, 0.125, 0.50),      # prompts <= 100K tokens
    "claude-sonnet-5-5": (2.00, 0.10, 2.50, 10.00),
    "claude-haiku-4-5": (1.00, 0.10, 1.25, 5.00),
}


def price_for(model):
    for name, price in PRICES.items():
        if str(model).startswith(name):
            return price
    return None


def usage_cost(usage):
    """Cost of one Tara turn from the private instance's `_eval_usage` call list."""

    if not usage:
        return 0.0 if usage == [] else None
    total = 0.0
    for call in usage:
        price = price_for(call.get("model"))
        if price is None:
            return None
        cache_read = call.get("cache_read", 0)
        cache_write = call.get("cache_write", 0)
        if call.get("provider") == "openai":
            # OpenAI reports input_tokens INCLUDING cached tokens.
            fresh = max(0, call.get("input", 0) - cache_read)
            total += (fresh * price[0] + cache_read * price[1] + call.get("output", 0) * price[3]) / 1e6
        else:
            total += (call.get("input", 0) * price[0] + cache_read * price[1]
                      + cache_write * price[2] + call.get("output", 0) * price[3]) / 1e6
    return total


def load_run(out_root, run, bank):
    run_dir = Path(out_root) / run
    results = {}
    for row in read_jsonl(run_dir / "results.jsonl"):
        if row.get("id") in bank:
            results[row["id"]] = row
    judged = {}
    for row in read_jsonl(run_dir / "judged.jsonl"):
        verdict = row["judge"]
        # The judge sometimes echoes the markdown marker with the heading; normalize it.
        verdict["kb_sections_needed"] = [
            str(h).lstrip("# ").strip() for h in (verdict.get("kb_sections_needed") or [])]
        judged[row["id"]] = verdict
    rows = []
    for qid, result in results.items():
        if qid in judged:
            rows.append({"q": bank[qid], "r": result, "j": judged[qid], "cause": root_cause(result, judged[qid])})
    return rows


def root_cause(result, judge):
    if judge["verdict"] == "helpful":
        return "none"
    cause = judge.get("failure_type") or "other"
    provider = result.get("provider")
    if cause == "none":
        cause = "other"
    if provider == "deterministic" and cause in ("model_reasoning", "other", "verbosity_or_tone", "over_refusal", "retrieval_miss"):
        return "shortcut_hijack"
    return cause


def pct(part, whole):
    return "%.0f%%" % (100.0 * part / whole) if whole else "-"


def headline(rows):
    counts = collections.Counter(row["j"]["verdict"] for row in rows)
    return counts["helpful"], counts["partial"], counts["unhelpful"], len(rows)


def table(rows, key, title, min_n=1):
    groups = collections.defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    lines = ["| %s | n | helpful | partial | unhelpful |" % title, "|---|---:|---:|---:|---:|"]
    for name, group in sorted(groups.items(), key=lambda kv: headline(kv[1])[0] / max(1, len(kv[1]))):
        if len(group) < min_n:
            continue
        helpful, partial, unhelpful, total = headline(group)
        lines.append("| %s | %d | %s | %s | %s |" % (name, total, pct(helpful, total), pct(partial, total), pct(unhelpful, total)))
    return "\n".join(lines)


def latency_stats(rows):
    values = sorted(row["r"].get("latency_s") or 0 for row in rows)
    if not values:
        return "-"
    p90 = values[int(0.9 * (len(values) - 1))]
    return "p50 %.1fs / p90 %.1fs / max %.1fs" % (statistics.median(values), p90, values[-1])


def trace_label(result):
    events = [event.get("event") for event in (result.get("protocol_trace") or []) if event.get("event")]
    tools = [event.get("tool") for event in (result.get("protocol_trace") or []) if event.get("tool")]
    if result.get("provider") == "deterministic":
        return "deterministic:" + (events[0] if events else "planner")
    if "protocol_violation" in events:
        return "model+guard:protocol_violation"
    return "model" + (":tools" if tools else ":no-tools")


def single(args, bank):
    rows = load_run(args.out_root, args.run, bank)
    if not rows:
        raise SystemExit("no judged rows for run %s" % args.run)
    helpful, partial, unhelpful, total = headline(rows)
    out = ["# Tara eval - run `%s`" % args.run, ""]
    out.append("**Helpful: %s** (%d/%d) | partial %s | unhelpful %s | latency %s" % (
        pct(helpful, total), helpful, total, pct(partial, total), pct(unhelpful, total), latency_stats(rows)))
    dims = ["correct", "answered", "helpful", "ui_action", "concise_tone", "boundary"]
    out += ["", "| dimension | pass | partial | fail | n (excl. n/a) |", "|---|---:|---:|---:|---:|"]
    for dim in dims:
        counts = collections.Counter(row["j"][dim] for row in rows if row["j"][dim] != "na")
        n = sum(counts.values())
        out.append("| %s | %s | %s | %s | %d |" % (dim, pct(counts["pass"], n), pct(counts["partial"], n), pct(counts["fail"], n), n))
    out += ["", "## By category", table(rows, lambda r: r["q"]["category"], "category")]
    out += ["", "## By persona", table(rows, lambda r: r["q"]["persona"], "persona")]
    out += ["", "## By plan level", table(rows, lambda r: str(r["q"]["plan_level"]), "plan")]
    out += ["", "## By capability class", table(rows, lambda r: r["q"]["capability"], "capability")]
    out += ["", "## By question source", table(rows, lambda r: r["q"]["source"], "source")]
    out += ["", "## By on-screen context", table(rows, lambda r: r["q"]["context"], "context")]
    out += ["", "## By answer path (provider / route)", table(rows, lambda r: trace_label(r["r"]), "path", min_n=3)]

    failures = [row for row in rows if row["j"]["verdict"] != "helpful"]
    out += ["", "## Root causes of the %d non-helpful answers" % len(failures),
            "| root cause | n | share of failures | unhelpful | partial |", "|---|---:|---:|---:|---:|"]
    causes = collections.Counter(row["cause"] for row in failures)
    for cause, count in causes.most_common():
        group = [row for row in failures if row["cause"] == cause]
        bad = sum(1 for row in group if row["j"]["verdict"] == "unhelpful")
        out.append("| %s | %d | %s | %d | %d |" % (cause, count, pct(count, len(failures)), bad, count - bad))

    out += ["", "## Failure clusters (root cause x answer path), largest first"]
    clusters = collections.defaultdict(list)
    for row in failures:
        clusters[(row["cause"], trace_label(row["r"]))].append(row)
    for (cause, path), group in sorted(clusters.items(), key=lambda kv: -len(kv[1]))[: args.clusters]:
        cats = collections.Counter(row["q"]["category"] for row in group).most_common(4)
        out.append("")
        out.append("### %s via %s - %d questions (%s)" % (cause, path, len(group), ", ".join("%s %d" % c for c in cats)))
        needed = collections.Counter(h for row in group for h in (row["j"].get("kb_sections_needed") or []))
        if needed and cause in ("retrieval_miss", "missing_kb", "wrong_fact"):
            out.append("KB sections needed most: " + "; ".join("%s (%d)" % kv for kv in needed.most_common(5)))
        group.sort(key=lambda row: (row["j"]["verdict"] != "unhelpful", row["q"]["id"]))
        for row in group[: args.examples]:
            out.append("- `%s` [%s] Q: %s" % (row["q"]["id"], row["j"]["verdict"], row["q"]["question"][:140]))
            out.append("  - Tara: %s" % (row["r"].get("reply") or "")[:260].replace("\n", " "))
            out.append("  - Judge: %s" % row["j"]["rationale"][:330])
            if cause == "retrieval_miss":
                out.append("  - routed: %s | needed: %s" % (row["r"].get("routed_kb") or [], row["j"].get("kb_sections_needed")))
    print("\n".join(out))


def compare(args, bank):
    runs = {name: {row["q"]["id"]: row for row in load_run(args.out_root, name, bank)} for name in args.compare}
    common = set.intersection(*(set(rows) for rows in runs.values())) if runs else set()
    print("# Tara eval comparison on %d common questions\n" % len(common))
    print("| run | helpful | partial | unhelpful | correct-fail | model-bound helpful | latency p50/p90 | $/question (all) | $/model-bound question |")
    print("|---|---:|---:|---:|---:|---:|---|---:|---:|")
    for name, rows in runs.items():
        subset = [rows[qid] for qid in sorted(common)]
        helpful, partial, unhelpful, total = headline(subset)
        wrong = sum(1 for row in subset if row["j"]["correct"] == "fail")
        model_rows = [row for row in subset if row["r"].get("provider") not in ("deterministic", None)]
        mh = headline(model_rows)
        lat = sorted(row["r"].get("latency_s") or 0 for row in model_rows) or [0]
        costs = [usage_cost(row["r"].get("usage")) for row in subset]
        known = [c for c in costs if c is not None]
        model_costs = [c for c in (usage_cost(row["r"].get("usage")) for row in model_rows) if c]
        print("| %s | %s | %s | %s | %s | %s (n=%d) | %.1fs / %.1fs | %s | %s |" % (
            name, pct(helpful, total), pct(partial, total), pct(unhelpful, total), pct(wrong, total),
            pct(mh[0], mh[3]), mh[3], statistics.median(lat), lat[int(0.9 * (len(lat) - 1))],
            ("$%.5f" % (sum(known) / len(known))) if known and any(known) else "n/a",
            ("$%.5f" % (sum(model_costs) / len(model_costs))) if model_costs else "n/a"))
    names = list(runs)
    if len(names) >= 2:
        base = names[0]
        print("\nPaired changes vs `%s` (helpful -> not / not -> helpful):" % base)
        for name in names[1:]:
            lost = [qid for qid in common if runs[base][qid]["j"]["verdict"] == "helpful" and runs[name][qid]["j"]["verdict"] != "helpful"]
            won = [qid for qid in common if runs[base][qid]["j"]["verdict"] != "helpful" and runs[name][qid]["j"]["verdict"] == "helpful"]
            print("- %s: +%d won, -%d lost (net %+d)" % (name, len(won), len(lost), len(won) - len(lost)))
    print("\n## Helpful %% by category\n")
    cats = sorted({runs[names[0]][qid]["q"]["category"] for qid in common})
    print("| category | n | " + " | ".join(names) + " |")
    print("|---|---:|" + "---:|" * len(names))
    for cat in cats:
        ids = [qid for qid in common if runs[names[0]][qid]["q"]["category"] == cat]
        cells = [pct(sum(1 for qid in ids if runs[name][qid]["j"]["verdict"] == "helpful"), len(ids)) for name in names]
        print("| %s | %d | %s |" % (cat, len(ids), " | ".join(cells)))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run")
    parser.add_argument("--compare", nargs="+")
    parser.add_argument("--out-root", default="/root/tara-eval-runs")
    parser.add_argument("--bank", default=None)
    parser.add_argument("--examples", type=int, default=3)
    parser.add_argument("--clusters", type=int, default=14)
    args = parser.parse_args()
    bank = {q["id"]: q for q in load_bank(args.bank)}
    if args.compare:
        compare(args, bank)
    elif args.run:
        single(args, bank)
    else:
        parser.error("give --run or --compare")
    return 0


if __name__ == "__main__":
    sys.exit(main())
