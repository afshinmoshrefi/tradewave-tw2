#!/usr/bin/env python3
"""EVAL-ONLY experiment overlays for TW-TASK-0034 (never committed to a product branch).

    patch.py <tree> [shapes] [repair] [detrewrite]

Each flag bakes one lever into a private copy of the round-3 tree:
  shapes      question-type answer shapes + multi-turn / language rules in the cached prefix
  repair      one extra Haiku self-check call after the tool loop ("OK" or a corrected answer)
  detrewrite  a deterministic route's reply becomes an ENGINE DRAFT that Haiku rewrites
              (numbers and actions stay the route's; the advice floor still runs afterwards)
"""
import sys
from pathlib import Path

tree = Path(sys.argv[1])
flags = set(sys.argv[2:])
app = tree / "appserver" / "appserver"


def rep(path, old, new, count=1):
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit("anchor not found in %s: %r" % (path.name, old[:70]))
    path.write_text(text.replace(old, new, count), encoding="utf-8")


SHAPES = r'''
    "\n=== ANSWER SHAPES (find the shape that matches the question and fill EVERY slot that "
    "applies, one short line per slot; a missing slot is an incomplete answer) ===\n"
    "DEFINITION / 'what is X' / 'what does X mean': (1) what it measures, in plain words; "
    "(2) where it is on screen; (3) the loaded pattern's own value when one is loaded; (4) the "
    "caveat the knowledge base attaches to it - it is historical / in-sample and not a forecast, "
    "probability or guarantee, what it must not be confused with, and what it is read alongside; "
    "(5) when the term is one of a set (PE cycle phases, bands, the lower windows), name the "
    "whole set in one line.\n"
    "HOW-TO / WHERE IS: (1) the control's exact name and location; (2) the steps; (3) how to "
    "undo it or get back; (4) every limit the knowledge base states for it (plan, desktop only, "
    "hidden or empty when nothing qualifies); (5) if you can do the equivalent yourself, do it "
    "or offer it in one clause.\n"
    "WHY / TROUBLESHOOTING: (1) the cause, and say 'by design' when it is; (2) every documented "
    "cause, not only the first; (3) where to confirm it on screen (which panel or setting); "
    "(4) the fix or restore step - do it yourself when you can, otherwise offer it.\n"
    "NOT POSSIBLE / NOT AVAILABLE: (1) one sentence saying no; (2) the closest supported thing, "
    "DONE in this reply (same goal, an in-plan instrument such as the ETF or US listing, the "
    "same window); (3) the manual route in the product when one exists (filter-row syntax such "
    "as 40-100;predr>5, Sort by, a menu path); (4) the CHEAPEST plan that includes it.\n"
    "PLAN / ACCOUNT / PRICE: the fact as it applies to THIS user's plan; the cheapest plan that "
    "unlocks the ask; tradewave.ai/account to confirm the current plan; help@tradewave.ai when "
    "what they see does not match what they paid for.\n"
    "ONE PATTERN / STATISTIC: start date AND end date plus days; record as W of N; average AND "
    "median; for a risk or quality question the worst year and deepest adverse move; the current "
    "year's in-progress result named separately when the window is active; if the engine used "
    "a different n than the lookback the user named, say so in one clause.\n"
    "LIST / SCAN: name the market, lookback, ranking and filters actually used; each row has "
    "symbol, direction, entry date, end date or days, record W of N and average; the number of "
    "rows you show equals the number you say (or say 'top K of N'); label leveraged or inverse "
    "ETFs; if a requested filter could not be applied, say so and give the filter-row or Sort by "
    "route; then load the top row or offer it once.\n"
    "SHOULD-I / RISK / ENTRY-EXIT / STOP: evidence, never an instruction: record W of N, worst "
    "year, deepest adverse move; the historical entry is the start-date close and the exit is the "
    "end-date close; MFE and MAE describe historical paths and are not targets or stops; no "
    "single number makes a pattern a recommendation; end with the research disclaimer.\n"
    "METHODOLOGY / DATA: say the basis that applies - end-of-day closes, split and dividend "
    "adjusted, gross of costs, one observation per completed year, fixed calendar dates that are "
    "not aligned to moving events, and no fundamentals or news.\n"
    "ONBOARDING / VAGUE / 'ok do that': act - put one real setup on the chart, say what is now "
    "on screen in one line with its record, and give one next step.\n"
    "EARLIER TURNS: your earlier replies in this conversation were built from real tool results "
    "that are no longer attached. Their figures stand. Never retract, disown, correct or "
    "apologise for an earlier reply, never call earlier figures unverified, and never mention "
    "tool runs; when you need a figure again, read it again silently.\n"
    "LANGUAGE: reply entirely in the language of the user's latest message, first line included.\n"
'''

if "shapes" in flags:
    path = app / "chatbot.py"
    rep(path,
        '    "user asked for a change or the answer is a pattern you are putting on screen."\n)',
        '    "user asked for a change or the answer is a pattern you are putting on screen.\\n"'
        + SHAPES + ")")
    rep(path,
        '    "own reading of the yearly rows."\n)',
        '    "own reading of the yearly rows.\\n"\n'
        '    "7) The reply fills every slot of its ANSWER SHAPE that applies, and nothing else: no "\n'
        '    "extra sections, no buy-and-hold aside unless asked, no retraction of an earlier reply."\n)')

REPAIR_FN = r'''

_H80_REPAIR_PROMPT = (
    "[TradeWave quality check - this message is not from the user] Re-read the user's last "
    "message and your draft reply above against the ANSWER SHAPES and the BEFORE YOU SEND "
    "checks. If the draft already answers every part, fills every slot that applies, agrees "
    "with the tool results and the live context, and is in the user's language, reply with "
    "exactly: OK. Otherwise reply with the complete corrected final answer for the user: the "
    "full reply, not a diff; keep everything that was right; add only facts from the knowledge "
    "base, the live context or this turn's tool results; do not call tools; do not mention "
    "this check or the draft."
)


def _h80_repair(convo, blocks, candidate, model, system, cache_ttl, trace):
    try:
        resp = send_claude_messages(
            list(convo) + [{"role": "assistant", "content": blocks},
                           {"role": "user", "content": _H80_REPAIR_PROMPT}],
            model=model, system=system, cache_system=True, cache_ttl=cache_ttl,
            tools=TOOLS, return_raw=True, effort=CLAUDE_EFFORT)
        if resp.get("stop_reason") == "tool_use":
            trace("h80_repair", outcome="tool_call_ignored")
            return candidate
        text = (_text_of(resp.get("content", []) or []) or "").strip()
        if not text or text.upper().rstrip(".!") == "OK" or len(text) < 25:
            trace("h80_repair", outcome="ok")
            return candidate
        trace("h80_repair", outcome="rewritten")
        return text
    except Exception:
        trace("h80_repair", outcome="error")
        return candidate

'''

if "repair" in flags:
    path = app / "tara_gateway.py"
    rep(path, "\ndef run_chat_with_tools(", REPAIR_FN + "\ndef run_chat_with_tools(")
    rep(path,
        "                continue\n            final_text = candidate\n            break\n        tool_ids = [block.get(\"id\") for block in native_tool_blocks]",
        "                continue\n            candidate = _h80_repair(convo, blocks, candidate, model, system, cache_ttl, trace)\n"
        "            final_text = candidate\n            break\n        tool_ids = [block.get(\"id\") for block in native_tool_blocks]")

DET_FN = r'''
        def _h80_rewrite(draft, response_actions):
            draft_actions = json.dumps(response_actions or [])[:1500]
            sys_blocks = build_system_prompt(wave_viewer, opportunities, opp_table_length,
                                             opp_table_market, opp_table_market_name,
                                             screen_context, user_message=user_message)
            msgs = []
            for h in history[:-1]:
                role = "assistant" if h.get("role") == "assistant" else "user"
                msgs.append({"role": role, "content": h.get("content", "")})
            msgs.append({"role": "user", "content": (
                user_message + "\n\n[ENGINE DRAFT - produced by TradeWave's deterministic engine "
                "route for this message; not written by the user]\n" + str(draft) +
                "\n[VIEW ACTIONS ALREADY QUEUED BY THE ENGINE: " + draft_actions + "]\n"
                "[INSTRUCTION] Write the final reply to the user's message above. The draft's "
                "numbers, dates, symbols, plan facts and its statements about what is being loaded "
                "are verified engine output: reuse them exactly and never add, change, round or "
                "compute a figure; any other fact must come from the knowledge base or the live "
                "context. Answer the question that was actually asked, first, in one or two "
                "sentences; then keep only the draft lines that support that answer and drop "
                "sections the user did not ask about. Add what the draft lacks: the other part of "
                "a multi-part question, the end date of the window, the record as W of N, the "
                "nearest in-plan alternative, the next step. If the draft answers a different "
                "question than the user asked, answer the user's question from the knowledge base "
                "and the live context and use the draft only as evidence. You cannot call tools "
                "in this step: only say something is being loaded or switched if it is in the "
                "queued actions. Keep the draft's research disclaimer sentence if it has one, keep "
                "any guide-popup markup exactly, use <br> for line breaks, and do not mention the "
                "draft, the engine route or this instruction."
            )})
            text = send_claude_messages(msgs, model=CHATBOT_MODEL, system=sys_blocks,
                                        cache_system=True, cache_ttl=CACHE_TTL,
                                        effort=_H80_EFFORT)
            text = (text or "").strip()
            return text or draft

'''

if "detrewrite" in flags:
    path = app / "chatbot.py"
    rep(path, "    try:\n        def finish(reply, response_actions=None, provider='deterministic',\n",
        "    try:\n" + DET_FN +
        "        def finish(reply, response_actions=None, provider='deterministic',\n")
    rep(path,
        "                   messages_or_text=None):\n            return _finalize_chat_response(\n                user_id,\n                turn_id,\n                user_message,\n                reply,\n",
        "                   messages_or_text=None):\n"
        "            if provider == 'deterministic':\n"
        "                try:\n"
        "                    reply = _h80_rewrite(reply, response_actions)\n"
        "                    protocol_trace.append({'event': 'h80_det_rewrite'})\n"
        "                except Exception:\n"
        "                    logging.exception('h80 rewrite failed')\n"
        "            return _finalize_chat_response(\n                user_id,\n                turn_id,\n                user_message,\n                reply,\n")
    rep(path, "CACHE_TTL     = '5m'", "from tara_runtime_policy import CLAUDE_EFFORT as _H80_EFFORT\nCACHE_TTL     = '5m'")

print("patched", tree, sorted(flags))
