#!/usr/bin/env python3
"""Run the Tara question bank against any running appserver and record raw replies.

    set -a; . /etc/tradewave/secrets.env; set +a
    python tools/tara_eval/run_eval.py --run baseline-dev --target http://127.0.0.1:5000

The target can be live dev or a private instance on another port (see
tools/tara_eval/private_instance.sh), so branches and model policies can be compared
with the same bank. Output goes OUTSIDE the repo (default /root/tara-eval-runs/<run>/):
    results.jsonl   one row per question (reply, actions, latency, provider, trace, usage)

The run is resumable: questions already present in results.jsonl are skipped.
Load is deliberately gentle: at most 3 concurrent requests.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import threading
import time
from pathlib import Path

import requests

from common import (
    append_jsonl, load_bank, load_contexts, load_env_files, mint_token, read_jsonl,
    routed_kb_headings, strip_html,
)

MAX_CONCURRENCY = 3
_write_lock = threading.Lock()


def _payload(message, history, token, ctx):
    body = {
        "message": message,
        "history": history,
        "token": token,
        "wave_viewer": ctx.get("wave_viewer") or {},
        "screen_context": ctx.get("screen_context") or {},
        "opportunities": ctx.get("opportunities") or [],
    }
    for key in ("opp_table_length", "opp_table_market", "opp_table_market_name",
                "opp_table_years", "opp_table_pe_cycle"):
        if ctx.get(key) is not None:
            body[key] = ctx[key]
    return body


def _post(target, body, timeout):
    started = time.monotonic()
    try:
        response = requests.post(target.rstrip("/") + "/chatbot/chat", json=body, timeout=timeout)
        elapsed = time.monotonic() - started
        try:
            data = response.json()
        except ValueError:
            data = {}
        return response.status_code, data if isinstance(data, dict) else {}, elapsed, None
    except requests.RequestException as exc:
        return 0, {}, time.monotonic() - started, type(exc).__name__


def _log_entries(question_log, user_id):
    """Provider + protocol trace are not in the HTTP response; read them from the
    target instance's TARA_QUESTION_LOG by the (unique, synthetic) eval user id."""

    if not question_log:
        return []
    entries = []
    try:
        with open(question_log, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 4_000_000))
            tail = handle.read().decode("utf-8", "replace")
    except OSError:
        return entries
    needle = '"user_id": "%s"' % user_id
    for line in tail.splitlines():
        if needle in line:
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    return entries


def run_question(question, contexts, args):
    qid = question["id"]
    user_id = "tara-eval-%s-%s" % (args.run, qid)
    token = mint_token(user_id, question.get("plan_level", 6))
    ctx = contexts.get(question.get("context") or "empty")
    if ctx is None:
        raise SystemExit("question %s references unknown context %r" % (qid, question.get("context")))

    history, transcript = [], []
    turns = list(question.get("prior_user_turns") or []) + [question["question"]]
    final = None
    total_latency = 0.0
    for index, message in enumerate(turns):
        history.append({"role": "user", "content": message})
        status, data, elapsed, error = _post(args.target, _payload(message, list(history), token, ctx), args.timeout)
        if status in (0, 502, 503, 504) and not error == "ReadTimeout":
            time.sleep(3)
            status, data, elapsed, error = _post(args.target, _payload(message, list(history), token, ctx), args.timeout)
        total_latency += elapsed
        reply = str(data.get("reply") or "")
        transcript.append({"user": message, "tara": strip_html(reply)})
        history.append({"role": "assistant", "content": reply})
        final = {
            "http_status": status, "error": error, "latency_s": round(elapsed, 2),
            "reply_html": reply, "reply": strip_html(reply),
            "actions": [
                {k: a.get(k) for k in ("type", "spec", "rank") if a.get(k) is not None}
                for a in (data.get("actions") or []) if isinstance(a, dict)
            ],
            "suggestions": data.get("suggestions") or [],
            "usage": data.get("_eval_usage"),
        }
        if index < len(turns) - 1 and args.turn_pause:
            time.sleep(args.turn_pause)

    time.sleep(0.2)   # let the appserver flush its audit line
    entries = _log_entries(args.question_log, user_id)
    last = entries[-1] if entries else {}
    row = {
        "id": qid, "run": args.run, "target": args.target,
        "category": question["category"], "persona": question["persona"],
        "plan_level": question["plan_level"], "context": question.get("context"),
        "question": question["question"],
        "transcript": transcript[:-1],
        "provider": last.get("provider"),
        "protocol_trace": [
            {k: v for k, v in event.items() if k in ("event", "reason", "tool", "intent", "name", "status")}
            for event in (last.get("protocol_trace") or []) if isinstance(event, dict)
        ][:12],
        "routed_kb": routed_kb_headings(question["question"]),
        "total_latency_s": round(total_latency, 2),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    row.update(final or {})
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help="run name; also the synthetic user-id prefix tara-eval-<run>-")
    parser.add_argument("--target", default="http://127.0.0.1:5000", help="appserver base URL")
    parser.add_argument("--out-root", default="/root/tara-eval-runs")
    parser.add_argument("--bank", default=None)
    parser.add_argument("--contexts", default=None)
    parser.add_argument("--question-log", default="/var/log/tradewave/tara_questions.log",
                        help="the TARGET instance's TARA_QUESTION_LOG (for provider/trace); '' to skip")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=150)
    parser.add_argument("--turn-pause", type=float, default=0.3)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ids-file", default="", help="file with one question id per line (subset run)")
    parser.add_argument("--category", action="append", default=[])
    args = parser.parse_args()
    if not 1 <= args.concurrency <= MAX_CONCURRENCY:
        raise SystemExit("--concurrency must be 1..%d (keep load on dev gentle)" % MAX_CONCURRENCY)

    load_env_files()
    bank = load_bank(args.bank)
    contexts = load_contexts(args.contexts)
    if args.ids_file:
        wanted = {line.strip() for line in Path(args.ids_file).read_text().splitlines() if line.strip()}
        bank = [q for q in bank if q["id"] in wanted]
    if args.category:
        bank = [q for q in bank if q["category"] in set(args.category)]
    if args.limit:
        bank = bank[: args.limit]

    out_dir = Path(args.out_root) / args.run
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)
    results_path = out_dir / "results.jsonl"
    done = {row["id"] for row in read_jsonl(results_path) if row.get("http_status") == 200}
    todo = [q for q in bank if q["id"] not in done]
    print("run=%s target=%s questions=%d already_done=%d todo=%d concurrency=%d" % (
        args.run, args.target, len(bank), len(done), len(todo), args.concurrency), flush=True)

    started = time.monotonic()
    counts = {"ok": 0, "bad": 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(run_question, q, contexts, args): q for q in todo}
        for number, future in enumerate(concurrent.futures.as_completed(futures), 1):
            question = futures[future]
            try:
                row = future.result()
            except Exception as exc:   # keep the run alive; record the failure
                row = {"id": question["id"], "run": args.run, "http_status": -1,
                       "error": "%s: %s" % (type(exc).__name__, exc)}
            with _write_lock:
                append_jsonl(results_path, row)
            counts["ok" if row.get("http_status") == 200 else "bad"] += 1
            if number % 20 == 0 or number == len(todo):
                rate = number / max(1e-6, time.monotonic() - started)
                print("  %d/%d ok=%d bad=%d  %.1f q/min" % (
                    number, len(todo), counts["ok"], counts["bad"], rate * 60), flush=True)
    print("wrote %s" % results_path)
    return 0 if not counts["bad"] else 1


if __name__ == "__main__":
    sys.exit(main())
