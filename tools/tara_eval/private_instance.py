#!/usr/bin/env python3
"""Start/stop a PRIVATE Tara appserver for evals - never touches live services.

    sudo python tools/tara_eval/private_instance.py start --name sonnet55 --port 5091 \
        --ref origin/main --provider anthropic --claude-model claude-sonnet-5-5
    sudo python tools/tara_eval/private_instance.py start --name luna-med --port 5092 --openai-effort medium
    sudo python tools/tara_eval/private_instance.py start --name luna-fullkb --port 5093 --full-kb
    sudo python tools/tara_eval/private_instance.py stop --name sonnet55 [--remove]

What it does:
- `git worktree add --detach` of <ref> at /home/tradewave-worktrees/tara-eval-private-<name>
  (any branch/commit, so the same bank can compare branches).
- Applies an EVAL-ONLY overlay to that private working tree (never committed, never in the
  tracked source): env-selected model/effort, an optional "whole knowledge base in the cached
  prefix" mode, and per-request token usage returned as `_eval_usage` for cost measurement.
  With no overlay flags the instance behaves exactly like the ref.
- Runs its own gunicorn as user flask on 127.0.0.1:<port> with `--no-control-socket`, its
  own pid file, and its own question/action logs under <worktree>/.eval/. It does not
  touch /home/flask/.gunicorn/gunicorn.ctl, systemd units, or the live release.

Research tool calls still go to the shared dev gateway/engine (read-only GETs).
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

WORKTREE_ROOT = Path("/home/tradewave-worktrees")
MAIN_REPO = "/home/flask"
GUNICORN = "/home/flask/venv/bin/gunicorn"

USAGE_MODULE = '''"""Eval-only per-request token accounting (private overlay; not in tracked source)."""
import threading

_local = threading.local()


def reset():
    _local.calls = []


def add(provider, model, **tokens):
    calls = getattr(_local, "calls", None)
    if calls is None:
        calls = _local.calls = []
    entry = {"provider": provider, "model": model}
    entry.update({k: int(v or 0) for k, v in tokens.items()})
    calls.append(entry)


def snapshot():
    return list(getattr(_local, "calls", []) or [])
'''


def _replace(text, old, new, label, count=1):
    if text.count(old) < 1:
        raise SystemExit("overlay anchor not found (%s); the ref's source drifted - update private_instance.py" % label)
    return text.replace(old, new, count)


def apply_overlay_legacy(tree):
    """Overlay for refs before TW-TASK-0033 (no ACTIVE_POLICY switch, routed KB)."""
    app = tree / "appserver" / "appserver"
    (app / "tara_eval_usage.py").write_text(USAGE_MODULE, encoding="utf-8")

    # --- OpenAI adapter: env effort, larger output cap above low effort, usage capture
    path = app / "openai_tools_appserver.py"
    text = path.read_text(encoding="utf-8")
    text = _replace(text, 'import hashlib\n', 'import hashlib\nimport os\nimport tara_eval_usage\n', "openai imports")
    text = _replace(
        text, '"reasoning": {"effort": "low"},',
        '"reasoning": {"effort": os.environ.get("TARA_EVAL_OPENAI_EFFORT") or "low"},', "openai effort")
    text = _replace(
        text, '"max_output_tokens": max_output_tokens,',
        '"max_output_tokens": (max_output_tokens if (os.environ.get("TARA_EVAL_OPENAI_EFFORT") or "low") == "low"'
        ' else max(max_output_tokens, 6000)),', "openai output cap")
    text = _replace(
        text, '    output_details = usage.get("output_tokens_details") or {}\n',
        '    output_details = usage.get("output_tokens_details") or {}\n'
        '    tara_eval_usage.add("openai", model, input=usage.get("input_tokens", 0),\n'
        '        cache_read=input_details.get("cached_tokens", input_details.get("cache_read_tokens", 0)),\n'
        '        cache_write=input_details.get("cache_write_tokens", input_details.get("cache_write_input_tokens", 0)),\n'
        '        output=usage.get("output_tokens", 0), reasoning=output_details.get("reasoning_tokens", 0))\n',
        "openai usage")
    path.write_text(text, encoding="utf-8")

    # --- Anthropic adapter: current-generation request shape + usage capture
    path = app / "AI_tools_appserver.py"
    text = path.read_text(encoding="utf-8")
    text = _replace(text, 'import logging\n', 'import logging\nimport os\nimport tara_eval_usage\n', "anthropic imports")
    text = _replace(
        text, "    if cache_system:\n        headers['anthropic-beta'] = 'prompt-caching-2024-07-31'\n",
        "    _current_gen = str(model).startswith(('claude-haiku-5', 'claude-sonnet-5', 'claude-opus-5'))\n"
        "    if cache_system and not _current_gen:\n        headers['anthropic-beta'] = 'prompt-caching-2024-07-31'\n",
        "anthropic beta header")
    text = _replace(
        text, "    if tools:\n        payload['tools'] = tools\n",
        "    if tools:\n        payload['tools'] = tools\n"
        "    if _current_gen:\n"
        "        # Haiku 5.5 / Sonnet 5.5: adaptive thinking only (no budget_tokens), no sampling\n"
        "        # params, no forced tool_choice; depth is controlled with output_config.effort.\n"
        "        payload.pop('temperature', None)\n"
        "        payload['thinking'] = {'type': 'adaptive'}\n"
        "        payload['output_config'] = {'effort': os.environ.get('TARA_EVAL_CLAUDE_EFFORT') or 'low'}\n"
        "        payload['max_tokens'] = max(int(max_tokens), 8000)\n",
        "anthropic payload")
    text = _replace(
        text, "    if return_raw:\n        return data\n    return data['content'][0]['text']\n",
        "    if isinstance(usage, dict):\n"
        "        tara_eval_usage.add('anthropic', model, input=usage.get('input_tokens', 0),\n"
        "            cache_read=usage.get('cache_read_input_tokens', 0),\n"
        "            cache_write=usage.get('cache_creation_input_tokens', 0),\n"
        "            output=usage.get('output_tokens', 0))\n"
        "    if return_raw:\n        return data\n"
        "    return ''.join(b.get('text', '') for b in data.get('content', []) if b.get('type') == 'text')\n",
        "anthropic return")
    path.write_text(text, encoding="utf-8")

    # --- chatbot.py: env model/provider, whole-KB mode, usage in the response envelope
    path = app / "chatbot.py"
    text = path.read_text(encoding="utf-8")
    text = _replace(text, "from tara_model_router import select_tara_provider\n",
                    "from tara_model_router import select_tara_provider\nimport tara_eval_usage\n", "chatbot import")
    text = _replace(text, "CHATBOT_MODEL = CLAUDE_HAIKU_45\n",
                    "CHATBOT_MODEL = os.environ.get('TARA_EVAL_CLAUDE_MODEL') or CLAUDE_HAIKU_45\n", "chatbot model")
    text = _replace(
        text, "    turn_id = uuid.uuid4().hex\n    protocol_trace = []\n",
        "    turn_id = uuid.uuid4().hex\n    tara_eval_usage.reset()\n    protocol_trace = []\n", "usage reset")
    text = _replace(text, "        'turn_id': turn_id,\n    })\n\n",
                    "        'turn_id': turn_id,\n        '_eval_usage': tara_eval_usage.snapshot(),\n    })\n\n",
                    "usage envelope")
    text = _replace(
        text,
        "            if TARA_TOOLS_ENABLED:\n                bot_reply, actions = run_chat_with_openai_tools(\n",
        "            if os.environ.get('TARA_EVAL_PROVIDER') == 'anthropic':\n"
        "                raise RuntimeError('tara-eval: provider forced to anthropic')\n"
        "            if TARA_TOOLS_ENABLED:\n                bot_reply, actions = run_chat_with_openai_tools(\n",
        "force anthropic")
    text = _replace(
        text,
        "    knowledge = select_topic_knowledge(user_message, _KNOWLEDGE_SECTIONS)\n"
        "    blocks = segmented_system_blocks(\n        \"\\n\".join(static_parts),\n        knowledge.text,\n",
        "    knowledge = select_topic_knowledge(user_message, _KNOWLEDGE_SECTIONS)\n"
        "    _eval_stable = \"\\n\".join(static_parts)\n"
        "    _eval_topic = knowledge.text\n"
        "    if os.environ.get('TARA_EVAL_FULL_KB') == '1':\n"
        "        # Whole knowledge base inside the cached stable prefix; no per-question routing.\n"
        "        _eval_stable += (\"\\n\\n=== TRADEWAVE KNOWLEDGE BASE (COMPLETE) ===\\n\"\n"
        "            \"Use these product facts. Do not infer product details that are not stated here.\\n\" + _KNOWLEDGE)\n"
        "        _eval_topic = ''\n"
        "    blocks = segmented_system_blocks(\n        _eval_stable,\n        _eval_topic,\n",
        "full kb")
    path.write_text(text, encoding="utf-8")


POLICY_BY_MODEL = {"claude-haiku-5-5": "haiku55", "claude-sonnet-5-5": "sonnet55"}


def apply_overlay(tree, policy="luna", claude_effort="low"):
    """Eval-only overlay for refs that carry tara_runtime_policy.ACTIVE_POLICY.

    The model is selected the same way a release would select it: by rewriting the one
    ACTIVE_POLICY line in the private copy. The only other change is token accounting.
    """
    app = tree / "appserver" / "appserver"
    policy_path = app / "tara_runtime_policy.py"
    text = policy_path.read_text(encoding="utf-8")
    if "ACTIVE_POLICY" not in text:
        return apply_overlay_legacy(tree)
    text = _replace(text, 'ACTIVE_POLICY = "luna"\n', 'ACTIVE_POLICY = "%s"\n' % policy, "active policy")
    text = _replace(text, 'CLAUDE_EFFORT = "low"\n', 'CLAUDE_EFFORT = "%s"\n' % claude_effort, "claude effort")
    policy_path.write_text(text, encoding="utf-8")
    (app / "tara_eval_usage.py").write_text(USAGE_MODULE, encoding="utf-8")

    path = app / "openai_tools_appserver.py"
    text = path.read_text(encoding="utf-8")
    text = _replace(text, 'import hashlib\n', 'import hashlib\nimport os\nimport tara_eval_usage\n', "openai imports")
    text = _replace(
        text, '"reasoning": {"effort": "low"},',
        '"reasoning": {"effort": os.environ.get("TARA_EVAL_OPENAI_EFFORT") or "low"},', "openai effort")
    text = _replace(
        text, '"max_output_tokens": max_output_tokens,',
        '"max_output_tokens": (max_output_tokens if (os.environ.get("TARA_EVAL_OPENAI_EFFORT") or "low") == "low"'
        ' else max(max_output_tokens, 6000)),', "openai output cap")
    text = _replace(
        text, '    output_details = usage.get("output_tokens_details") or {}\n',
        '    output_details = usage.get("output_tokens_details") or {}\n'
        '    tara_eval_usage.add("openai", model, input=usage.get("input_tokens", 0),\n'
        '        cache_read=input_details.get("cached_tokens", input_details.get("cache_read_tokens", 0)),\n'
        '        cache_write=input_details.get("cache_write_tokens", input_details.get("cache_write_input_tokens", 0)),\n'
        '        output=usage.get("output_tokens", 0), reasoning=output_details.get("reasoning_tokens", 0))\n',
        "openai usage")
    path.write_text(text, encoding="utf-8")

    path = app / "AI_tools_appserver.py"
    text = path.read_text(encoding="utf-8")
    text = _replace(text, 'import logging\n', 'import logging\nimport tara_eval_usage\n', "anthropic imports")
    text = _replace(
        text, "    if return_raw:\n        return data\n    if current_gen:\n",
        "    if isinstance(usage, dict):\n"
        "        tara_eval_usage.add('anthropic', model, input=usage.get('input_tokens', 0),\n"
        "            cache_read=usage.get('cache_read_input_tokens', 0),\n"
        "            cache_write=usage.get('cache_creation_input_tokens', 0),\n"
        "            output=usage.get('output_tokens', 0))\n"
        "    if return_raw:\n        return data\n    if current_gen:\n",
        "anthropic usage")
    path.write_text(text, encoding="utf-8")

    path = app / "chatbot.py"
    text = path.read_text(encoding="utf-8")
    text = _replace(text, "from tara_model_router import select_tara_provider\n",
                    "from tara_model_router import select_tara_provider\nimport tara_eval_usage\n", "chatbot import")
    text = _replace(
        text, "    turn_id = uuid.uuid4().hex\n    protocol_trace = []\n",
        "    turn_id = uuid.uuid4().hex\n    tara_eval_usage.reset()\n    protocol_trace = []\n", "usage reset")
    text = _replace(text, "        'turn_id': turn_id,\n    })\n\n",
                    "        'turn_id': turn_id,\n        '_eval_usage': tara_eval_usage.snapshot(),\n    })\n\n",
                    "usage envelope")
    path.write_text(text, encoding="utf-8")


def _flask(cmd, **kw):
    return subprocess.run(["sudo", "-u", "flask"] + cmd, **kw)


def _env_from_files():
    env = {}
    for path in ("/etc/tradewave/secrets.env", "/etc/tradewave/appserver.env"):
        try:
            for line in Path(path).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env[key.replace("export ", "").strip()] = value.strip().strip('"').strip("'")
        except OSError:
            pass
    return env


def start(args):
    tree = WORKTREE_ROOT / ("tara-eval-private-" + args.name)
    if not tree.exists():
        if args.from_tree:
            # Private COPY of an uncommitted working tree (fast iteration; no git state).
            source = Path(args.from_tree).resolve()
            if not (source / "appserver" / "appserver" / "chatbot.py").exists():
                raise SystemExit("--from-tree is not a TradeWave checkout")
            tree.mkdir(parents=True)
            subprocess.run(
                ["rsync", "-a", "--exclude", ".git", "--exclude", "node_modules", "--exclude", ".eval",
                 "--exclude", "docs", "--exclude", "web-react", "--exclude", "__pycache__",
                 str(source) + "/", str(tree) + "/"], check=True)
            subprocess.run(["chown", "-R", "flask:flask", str(tree)], check=True)
        else:
            result = _flask(["git", "-C", MAIN_REPO, "worktree", "add", "--detach", str(tree), args.ref])
            if result.returncode:
                raise SystemExit("git worktree add failed")
        policy = args.policy or (
            POLICY_BY_MODEL.get(args.claude_model, "haiku55") if args.provider == "anthropic" else "luna")
        apply_overlay(tree, policy=policy, claude_effort=args.claude_effort)
        subprocess.run(["chown", "-R", "flask:flask", str(tree / "appserver" / "appserver")], check=True)
    eval_dir = tree / ".eval"
    eval_dir.mkdir(exist_ok=True)
    subprocess.run(["chown", "flask:flask", str(eval_dir)], check=True)
    pid_file = eval_dir / "gunicorn.pid"
    if pid_file.exists():
        raise SystemExit("instance %s already has a pid file (%s); stop it first" % (args.name, pid_file))

    env = _env_from_files()
    env.update({
        "PATH": "/home/flask/venv/bin:/usr/bin:/bin",
        "HOME": "/home/flask",
        "PYTHONPATH": "%s:%s" % (tree, tree / "appserver" / "appserver"),
        "TARA_QUESTION_LOG": str(eval_dir / "tara_questions.log"),
        "TARA_ACTION_AUDIT_LOG": str(eval_dir / "tara_actions.log"),
        "TARA_EVAL_OPENAI_EFFORT": args.openai_effort,
        "TARA_EVAL_CLAUDE_EFFORT": args.claude_effort,
    })
    if args.provider == "anthropic":
        env["TARA_EVAL_PROVIDER"] = "anthropic"
        env["TARA_EVAL_CLAUDE_MODEL"] = args.claude_model
    if args.full_kb:
        env["TARA_EVAL_FULL_KB"] = "1"
    # Secrets go through a 0600 flask-owned env file, never the process command line.
    import shlex
    env_file = eval_dir / "env"
    env_file.write_text("".join("export %s=%s\n" % (k, shlex.quote(v)) for k, v in env.items()), encoding="utf-8")
    os.chmod(env_file, 0o600)
    subprocess.run(["chown", "flask:flask", str(env_file)], check=True)
    gunicorn_cmd = [
        GUNICORN, "--workers", "1", "--worker-class", "gthread", "--threads", "4",
        "--timeout", "180", "--bind", "127.0.0.1:%d" % args.port,
        "--no-control-socket", "--pid", str(pid_file), "--daemon",
        "--chdir", str(tree / "appserver" / "appserver"),
        "--access-logfile", str(eval_dir / "access.log"),
        "--error-logfile", str(eval_dir / "error.log"), "--capture-output",
        "appserver:app",
    ]
    cmd = ["sudo", "-u", "flask", "env", "-i", "bash", "-c",
           ". %s && exec %s" % (shlex.quote(str(env_file)), " ".join(shlex.quote(c) for c in gunicorn_cmd))]
    subprocess.run(cmd, check=True)
    for _ in range(60):
        time.sleep(1)
        probe = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:%d/chatbot/runtime-fingerprint" % args.port],
            capture_output=True, text=True)
        if probe.stdout.strip() not in ("", "000"):
            print("private Tara '%s' is up: http://127.0.0.1:%d (http %s)" % (args.name, args.port, probe.stdout.strip()))
            print("question log: %s" % (eval_dir / "tara_questions.log"))
            return 0
    raise SystemExit("instance did not come up; see %s" % (eval_dir / "error.log"))


def stop(args):
    tree = WORKTREE_ROOT / ("tara-eval-private-" + args.name)
    pid_file = tree / ".eval" / "gunicorn.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                time.sleep(0.5)
                os.kill(pid, 0)
        except (ProcessLookupError, ValueError):
            pass
        pid_file.unlink(missing_ok=True)
        print("stopped %s" % args.name)
    else:
        print("no pid file for %s" % args.name)
    if args.remove and tree.exists():
        if (tree / ".git").exists():
            _flask(["git", "-C", MAIN_REPO, "worktree", "remove", "--force", str(tree)])
        elif tree.parent == WORKTREE_ROOT and tree.name.startswith("tara-eval-private-"):
            import shutil
            shutil.rmtree(tree)      # a --from-tree copy: no git state to unregister
        print("removed worktree %s" % tree)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_start = sub.add_parser("start")
    p_start.add_argument("--name", required=True)
    p_start.add_argument("--port", type=int, required=True)
    p_start.add_argument("--ref", default="origin/main")
    p_start.add_argument("--from-tree", default="",
                         help="copy this working tree instead of checking out --ref (uncommitted work)")
    p_start.add_argument("--provider", choices=["openai", "anthropic"], default="openai")
    p_start.add_argument("--claude-model", default="claude-haiku-5-5")
    p_start.add_argument("--claude-effort", default="low")
    p_start.add_argument("--openai-effort", default="low")
    p_start.add_argument("--full-kb", action="store_true",
                         help="legacy refs only; from TW-TASK-0033 the whole KB is always in the prefix")
    p_start.add_argument("--policy", choices=["luna", "haiku55", "sonnet55"], default=None,
                         help="tara_runtime_policy.ACTIVE_POLICY for the private copy")
    p_start.set_defaults(func=start)
    p_stop = sub.add_parser("stop")
    p_stop.add_argument("--name", required=True)
    p_stop.add_argument("--remove", action="store_true")
    p_stop.set_defaults(func=stop)
    args = parser.parse_args()
    if getattr(args, "port", 5091) in (5000, 5500, 8088):
        raise SystemExit("refusing a live service port")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
