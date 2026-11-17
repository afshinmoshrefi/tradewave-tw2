# Tara eval harness (TW-TASK-0032)

The measuring stick for "can Tara helpfully answer nearly any question a beginner or a
professional trader/investor asks". It does not change Tara. It runs a question bank
against any running appserver, grades every reply with an LLM judge, and reports
helpful % by category/persona/plan plus root-cause clusters.

| Piece | File |
|---|---|
| Question bank (questions + expected-behavior rubrics) | `tests/fixtures/tara_eval_questions.json` |
| On-screen context fixtures (real engine statistics) | `tests/fixtures/tara_eval_contexts.json` |
| Runner (calls `/chatbot/chat`, records reply/actions/latency/provider) | `run_eval.py` |
| Judge (Claude Opus 5.5, structured verdict, cached, budget-capped) | `judge.py` |
| Report (summary, clusters, run comparison, cost per question) | `report.py` |
| Private instance launcher (own port/pid/logs, eval-only overlay) | `private_instance.py` |
| Bank merge + validation | `build_bank.py` |
| Context fixture builder | `build_contexts.py` |

## Quick start

```bash
# one-time: the judge needs the official SDK (not installed in /home/flask/venv)
python3 -m venv /root/tara-eval-runs/venv
/root/tara-eval-runs/venv/bin/pip install anthropic requests pyjwt
PY=/root/tara-eval-runs/venv/bin/python
cd tools/tara_eval

# 1. run the bank against live dev (max 3 concurrent; default 2). Resumable.
$PY run_eval.py --run baseline-dev --target http://127.0.0.1:5000

# 2. grade it. Prints a cost estimate first; --budget is a hard USD cap. Resumable + cached.
$PY judge.py --run baseline-dev --dry-run --budget 0
$PY judge.py --run baseline-dev --budget 25

# 3. report
$PY report.py --run baseline-dev > /root/tara-eval-runs/baseline-dev/report.md
```

Secrets come from the environment; the tools also read `/etc/tradewave/secrets.env` and
`/etc/tradewave/appserver.env` when run as root (`APPSERVER_JWT_SECRET` to mint the
synthetic eval JWT, `ANTHROPIC_TOKEN` or `ANTHROPIC_API_KEY` for the judge).

Raw outputs live outside the repo in `/root/tara-eval-runs/<run>/` (mode 700):
`results.jsonl`, `judged.jsonl`; shared `judge_cache/` and `spend_ledger.jsonl`.
Every request uses a synthetic identity `tara-eval-<run>-<question id>`; no customer
identity is ever used and no customer data is written to the repo.

## Comparing a branch, a model, or a prompt strategy

`private_instance.py` creates a detached git worktree of any ref, applies an eval-only
overlay to that private copy (never committed), and runs its own gunicorn on a localhost
port with `--no-control-socket`, its own pid file and its own question log. It never
touches the live service, `/home/flask/.gunicorn/gunicorn.ctl`, or systemd.

```bash
sudo python3 private_instance.py start --name fix-branch --port 5096 --ref origin/claude/tara-prod-failures-20261117
sudo python3 private_instance.py start --name sonnet55 --port 5094 --provider anthropic --claude-model claude-sonnet-5-5
sudo python3 private_instance.py start --name luna-med --port 5092 --openai-effort medium
sudo python3 private_instance.py start --name luna-fullkb --port 5095 --full-kb

$PY run_eval.py --run sonnet55 --target http://127.0.0.1:5094 --ids-file subset.txt \
    --question-log /home/tradewave-worktrees/tara-eval-private-sonnet55/.eval/tara_questions.log
$PY judge.py --run sonnet55 --budget 8
$PY report.py --compare luna-low luna-med haiku55 sonnet55 luna-fullkb

sudo python3 private_instance.py stop --name sonnet55 --remove
```

Overlay switches (environment of the private instance only):

| Flag | Effect in the private copy |
|---|---|
| `--provider anthropic --claude-model <id>` | every model-bound turn runs on that Claude model through the existing Anthropic tool loop. For `claude-haiku-5-5` / `claude-sonnet-5-5` the request uses the current API shape: adaptive thinking, `output_config.effort`, no `budget_tokens`, no sampling params, no forced `tool_choice` |
| `--claude-effort low\|medium\|high` | effort for those Claude models (default low) |
| `--openai-effort low\|medium\|high` | Luna reasoning effort (live = low) |
| `--full-kb` | the whole knowledge base goes into the cached stable prompt prefix instead of the 3-section regex routing |
| always | per-request token usage is returned as `_eval_usage`, which `report.py --compare` turns into measured $ per question |

With no flags a private instance behaves exactly like its ref, which is how two branches
are compared with the same bank.

## Question bank schema

```json
{
  "id": "acct-012", "category": "account_billing", "persona": "intermediate",
  "plan_level": 2, "context": "default_table",
  "question": "why does the years dropdown stop at 15",
  "prior_user_turns": ["optional earlier user messages; replayed for real first"],
  "source": "prod_log | dev_log | michael | predicted",
  "capability": "supported | partial | unsupported | boundary",
  "expect": {
    "ideal": "what the ideal helpful answer says/does",
    "must": ["checkable things the answer must contain or do"],
    "must_not": ["things that make it wrong or harmful"],
    "ui_action": "none | load | set_view | optional", "ui_action_detail": "..."
  },
  "refs": ["appserver/appserver/chatbot_knowledge.txt:767 (Subscription Tiers)", "config.py:402"]
}
```

- `plan_level`: 1 Explorer (free), 2 Navigator, 4 Analyst, 6 Strategist (JWT `user_level`).
- `capability`: `unsupported` = TradeWave genuinely cannot do it and `ideal` describes the
  graceful answer; `boundary` = personal advice / sizing / guarantees, where the ideal is
  "no personal instruction, but still useful evidence".
- `refs` prove the rubric's facts (KB line with its section, or code line). `build_bank.py
  --check` re-validates them against the current checkout, so a KB edit that moves or
  deletes a cited fact is caught.
- `source`: real production/dev phrasings are kept verbatim or lightly varied; user ids
  are never stored.

Add questions by appending drafts in the same shape (with `kb:<heading>#L<line>` /
`code:<path>:<line>` refs) and running `build_bank.py --drafts <existing bank parts> <new>`,
or edit the JSON and run `build_bank.py --check`.

## Context fixtures

`context` names what is on the user's screen. The fixtures mirror the exact payload the
React app sends (`Chatbot.js buildWaveViewerContext`, `chatbotScreenContext.js`), filled
from the live engine so loaded-pattern questions are graded against real statistics:
`empty`, `default_table`, `stock_long_strong`, `stock_short`, `stock_mixed_custom` (AAPL),
`stock_long_ai`, `etf_long` (XLK), `futures_gold` (GC), `crypto_btc` (BTC-USD),
`stock_pe2` (MSFT, PE+2 cohort), `stock_long_window` (~200+ days), `stock_active`
(window already in progress, price chart with projection).

Scanner fixtures are dated near the build day. Rebuild when they go stale:
`$PY build_contexts.py --target http://127.0.0.1:5000` (then re-run; old runs stay valid
because results are only compared within the same fixture snapshot).

Known simplifications: the screen context is static during a multi-turn question (the
harness does not apply Tara's view actions between turns), and plan level 1 questions
reuse S&P 500 fixtures although Explorer is Dow 30 only outside the reverse trial.

## Judge

One Opus 5.5 call per question (adaptive thinking, low effort, JSON-schema output). The
judge sees the full knowledge base (cached system prefix), the rubric, the exact on-screen
context, the transcript, Tara's reply and actions, and diagnostic metadata (provider,
protocol trace, which KB sections Tara's router attached). It does not see the model name.

Dimensions (pass / partial / fail / na): `correct`, `answered`, `helpful`, `ui_action`,
`concise_tone`, `boundary`. Headline `verdict`: helpful / partial / unhelpful.
Diagnosis: `false_facts`, `missing`, `kb_has_answer`, `kb_sections_needed`, `failure_type`.

`report.py` turns that into root causes: `shortcut_hijack` (a deterministic route gave the
bad answer), `retrieval_miss` (KB has it, router attached none of the needed sections),
`missing_kb`, `missing_tool_or_data`, `model_reasoning`, `wrong_fact`, and others.

Cost: about $0.03 per uncached judgment (measured; the knowledge base is ~55K tokens, read
from cache at $0.20/M), plus about $0.45 once per hour to write the cache. Verdicts are
cached by hash of (judge version, rubric, context, transcript, reply, actions), so
deterministic replies and reruns are free. `--budget` stops the run before the cap; rerun
to resume.

Limits to keep in mind: the judge cannot verify numbers that come from Tara's research
tools for other symbols/windows (it only flags contradictions), prices and plan facts are
graded against the knowledge base (if the KB is stale the grade is too), and a single
judge pass has noise of a few points - compare runs on the same question ids and look at
paired wins/losses, not one-point differences.
