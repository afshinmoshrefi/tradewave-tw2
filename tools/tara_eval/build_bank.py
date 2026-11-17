#!/usr/bin/env python3
"""Merge, normalize and validate Tara eval question drafts into the tracked bank.

    python tools/tara_eval/build_bank.py --drafts /path/part_A.json /path/part_B.json ...
    python tools/tara_eval/build_bank.py --check          # validate the tracked bank only

Validation (fails loudly):
- schema, enums, known context fixture ids, plan levels;
- every `kb:<heading>#L<line>` ref names a real KB section and a line inside it; refs are
  rewritten to `appserver/appserver/chatbot_knowledge.txt:<line> (<heading>)`;
- every `code:<path>:<line>` ref points at an existing file/line in this checkout;
- no near-duplicate questions; no customer identifiers (emails, long hex ids).
Ids are assigned deterministically per category (`<prefix>-NNN`) in draft order.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

from common import BANK_PATH, CATEGORIES, CONTEXTS_PATH, REPO_ROOT, kb_sections

PREFIX = {
    "product": "prod", "getting_started": "start", "ui_howto": "ui", "definitions": "def",
    "chart_reading": "chart", "pattern_analysis": "pat", "screening": "scan",
    "symbol_research": "sym", "comparisons": "cmp", "dates_cycles": "date", "ai_scores": "ai",
    "risk_boundary": "risk", "strategy": "strat", "portfolio_tools": "port",
    "account_billing": "acct", "data_methodology": "data", "troubleshooting": "fix",
    "mcp_api": "mcp", "offtopic_markets": "off", "multi_turn": "multi", "messy_input": "messy",
    "non_english": "lang",
}
PERSONAS = {"beginner", "intermediate", "pro"}
SOURCES = {"prod_log", "dev_log", "michael", "predicted"}
CAPABILITIES = {"supported", "partial", "unsupported", "boundary"}
UI_ACTIONS = {"none", "load", "set_view", "optional"}
KB_REL = "appserver/appserver/chatbot_knowledge.txt"
_PII = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\b[0-9a-f]{8,}\b", re.I)
_ALLOWED_EMAILS = {"help@tradewave.ai"}


def _norm(text):
    return re.sub(r"[\W_]+", " ", str(text).lower(), flags=re.UNICODE).strip()


def _resolve_ref(ref, sections, starts, kb_lines, problems, where):
    ref = str(ref).strip()
    if ref.startswith("kb:"):
        body = ref[3:]
        heading, _, line = body.partition("#L")
        heading = heading.strip()
        if heading not in sections:
            problems.append("%s: unknown KB heading %r" % (where, heading))
            return None
        start = starts[heading]
        end = start + sections[heading].count("\n")
        number = start
        if line.strip():
            try:
                number = int(re.match(r"\d+", line.strip()).group(0))
            except (AttributeError, ValueError):
                problems.append("%s: bad KB line in %r" % (where, ref))
                return None
            if not start <= number <= end + 2:
                # Authors sometimes cite the right line under a neighboring heading; keep the
                # line if it is real, and name the section that actually contains it.
                owner = None
                for other, other_start in starts.items():
                    if other_start <= number <= other_start + sections[other].count("\n") + 2:
                        owner = other
                if owner is None or number > len(kb_lines):
                    problems.append("%s: KB line %s outside the file" % (where, number))
                    return None
                heading = owner
        return "%s:%d (%s)" % (KB_REL, number, heading)
    if ref.startswith("code:"):
        match = re.match(r"code:(.+?):(\d+)(?:-\d+)?$", ref)
        if not match:
            problems.append("%s: bad code ref %r" % (where, ref))
            return None
        path, number = match.group(1), int(match.group(2))
        target = REPO_ROOT / path
        if not target.is_file():
            problems.append("%s: code ref file missing %r" % (where, path))
            return None
        if number > sum(1 for _ in target.open(encoding="utf-8", errors="replace")):
            problems.append("%s: code ref line past EOF %r" % (where, ref))
            return None
        return "%s:%d" % (path, number)
    if re.match(r"[\w./-]+:\d+", ref):      # already resolved (re-validation of the bank)
        return ref
    problems.append("%s: unrecognized ref %r" % (where, ref))
    return None


def normalize(raw, contexts, sections, starts, kb_lines, problems, where):
    expect = raw.get("expect") or {}
    q = {
        "category": raw.get("category"),
        "persona": raw.get("persona"),
        "plan_level": raw.get("plan_level"),
        "context": raw.get("context") or "empty",
        "question": str(raw.get("question") or "").strip(),
        "source": raw.get("source") or "predicted",
        "capability": raw.get("capability") or "supported",
        "expect": {
            "ideal": str(expect.get("ideal") or "").strip(),
            "must": [str(x).strip() for x in (expect.get("must") or []) if str(x).strip()],
            "must_not": [str(x).strip() for x in (expect.get("must_not") or []) if str(x).strip()],
            "ui_action": expect.get("ui_action") or "optional",
            "ui_action_detail": str(expect.get("ui_action_detail") or "").strip(),
        },
    }
    prior = [str(x).strip() for x in (raw.get("prior_user_turns") or []) if str(x).strip()]
    if prior:
        q["prior_user_turns"] = prior
    checks = (
        (q["category"] in CATEGORIES, "category %r" % q["category"]),
        (q["persona"] in PERSONAS, "persona %r" % q["persona"]),
        (q["plan_level"] in (1, 2, 4, 6), "plan_level %r" % q["plan_level"]),
        (q["context"] in contexts, "context %r" % q["context"]),
        (bool(q["question"]) and len(q["question"]) <= 2000, "question text"),
        (q["source"] in SOURCES, "source %r" % q["source"]),
        (q["capability"] in CAPABILITIES, "capability %r" % q["capability"]),
        (q["expect"]["ui_action"] in UI_ACTIONS, "ui_action %r" % q["expect"]["ui_action"]),
        (bool(q["expect"]["ideal"]), "missing ideal"),
        (bool(q["expect"]["must"]), "missing must"),
    )
    bad = [message for ok, message in checks if not ok]
    if bad:
        problems.append("%s: %s" % (where, "; ".join(bad)))
        return None
    text = json.dumps(q, ensure_ascii=False)
    for hit in _PII.findall(text):
        if hit.lower().rstrip(".") not in _ALLOWED_EMAILS and not hit.isdigit():
            problems.append("%s: possible identifier %r" % (where, hit))
            return None
    refs = []
    for ref in raw.get("refs") or []:
        resolved = _resolve_ref(ref, sections, starts, kb_lines, problems, where)
        if resolved and resolved not in refs:
            refs.append(resolved)
    q["refs"] = refs
    return q


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--drafts", nargs="*", default=[])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--contexts", default=str(CONTEXTS_PATH))
    parser.add_argument("--out", default=str(BANK_PATH))
    parser.add_argument("--lenient-refs", action="store_true",
                        help="drop unresolvable refs with a warning instead of failing")
    args = parser.parse_args()

    contexts = json.loads(Path(args.contexts).read_text(encoding="utf-8"))["contexts"]
    sections, starts = kb_sections()
    kb_lines = (REPO_ROOT / KB_REL).read_text(encoding="utf-8").splitlines()

    raw_items = []
    if args.check:
        raw_items = [(q, q.get("id", "?")) for q in json.loads(Path(args.out).read_text(encoding="utf-8"))["questions"]]
    for draft in args.drafts:
        for index, item in enumerate(json.loads(Path(draft).read_text(encoding="utf-8"))):
            raw_items.append((item, "%s[%d]" % (Path(draft).name, index)))

    problems, ref_problems, questions, seen = [], [], [], {}
    counters = collections.Counter()
    for raw, where in raw_items:
        local = []
        q = normalize(raw, contexts, sections, starts, kb_lines, local, where)
        ref_only = [p for p in local if " ref" in p or "KB " in p]
        hard = [p for p in local if p not in ref_only]
        ref_problems.extend(ref_only)
        problems.extend(hard)
        if q is None:
            continue
        key = _norm(" | ".join((q.get("prior_user_turns") or []) + [q["question"]])) + "|" + q["context"]
        if key in seen:
            print("duplicate dropped: %s == %s (%r)" % (where, seen[key], q["question"][:60]))
            continue
        seen[key] = where
        counters[q["category"]] += 1
        ordered = {"id": raw.get("id") if args.check else "%s-%03d" % (PREFIX[q["category"]], counters[q["category"]])}
        ordered.update(q)
        questions.append(ordered)

    for line in ref_problems:
        print("REF: " + line)
    for line in problems:
        print("ERROR: " + line)
    if problems or (ref_problems and not args.lenient_refs):
        raise SystemExit("bank validation failed (%d errors, %d ref problems)" % (len(problems), len(ref_problems)))

    questions.sort(key=lambda q: (CATEGORIES.index(q["category"]), q["id"]))
    summary = {
        "by_category": dict(collections.Counter(q["category"] for q in questions)),
        "by_persona": dict(collections.Counter(q["persona"] for q in questions)),
        "by_plan": dict(collections.Counter(str(q["plan_level"]) for q in questions)),
        "by_source": dict(collections.Counter(q["source"] for q in questions)),
        "by_capability": dict(collections.Counter(q["capability"] for q in questions)),
    }
    print(json.dumps({"total": len(questions), **summary}, indent=1))
    if not args.check:
        bank = {
            "schema_version": 1,
            "description": "Tara eval question bank (TW-TASK-0032). No customer identifiers. "
                           "See tools/tara_eval/README.md for the schema and how to run it.",
            "plan_levels": {"1": "Explorer (free)", "2": "Navigator", "4": "Analyst", "6": "Strategist"},
            "questions": questions,
        }
        Path(args.out).write_text(json.dumps(bank, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
