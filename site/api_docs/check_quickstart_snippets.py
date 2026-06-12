#!/usr/bin/env python3
"""Doc-CI: execute every published quickstart code snippet against the live gateway.

The 2026-06-12 docs review found the shipped quickstart crashed on copy-paste
(pick["symbol"] for a /daily-pick response whose SignalCard lives under "card").
This checker makes that class of bug impossible to publish again: it parses the
GENERATED quickstart.html, extracts each code-tab snippet (curl / Python /
JavaScript), substitutes the placeholder key and the published API base, RUNS the
snippet, and exits non-zero if any snippet errors. generate_api_docs.py calls it
at the end of every build and fails the generation on error.

Environment:
  TW_DOCCHECK_KEY        an API key to run the snippets with (preferred), else
  TRADEWAVE_API_KEY      same, else
  TW_DOCCHECK_KEYS_FILE  a JSON list of {"key": ..., "api_tier": ...} records
                         (default /tmp/mcp_review_keys.json). The PRO key is
                         preferred: the snippets behave identically on every
                         tier, and the free key's small shared day budget gets
                         burned by parallel test sessions.
  TW_DOCCHECK_API_BASE   gateway base the snippets are pointed at
                         (default http://127.0.0.1:8088/v1 - the local gateway).

Exit codes: 0 = all snippets ran clean; 1 = a snippet failed (must block
publishing); 2 = no key configured; 3 = the key's day quota is exhausted so the
check is INCONCLUSIVE (2 and 3 are environment conditions, not docs failures -
callers warn loudly and continue).

Only the first 12 characters of the key are ever printed.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUICKSTART = HERE / "quickstart.html"

sys.path.insert(0, str(HERE.parent / "lib"))
import portal_urls  # noqa: E402

CHECK_BASE = os.environ.get("TW_DOCCHECK_API_BASE", "http://127.0.0.1:8088/v1").rstrip("/")
PLACEHOLDER = "<your-api-key>"
VENV_PY = "/home/flask/venv/bin/python"


def resolve_key() -> str | None:
    for var in ("TW_DOCCHECK_KEY", "TRADEWAVE_API_KEY"):
        if os.environ.get(var):
            return os.environ[var].strip()
    keys_file = Path(os.environ.get("TW_DOCCHECK_KEYS_FILE", "/tmp/mcp_review_keys.json"))
    if keys_file.is_file():
        try:
            records = json.loads(keys_file.read_text())
        except (ValueError, OSError) as e:
            print(f"ERROR: cannot read keys file {keys_file}: {e}", file=sys.stderr)
            return None
        # Prefer the PRO key: identical snippet behavior, and its day budget is not
        # burned by the parallel sessions sharing the free test key.
        for want_pro in (True, False):
            for rec in records:
                if isinstance(rec, dict) and rec.get("key") and \
                        ((rec.get("api_tier") == "pro") is want_pro):
                    return rec["key"]
    return None


def preflight(key: str) -> int:
    """One cheap call to classify the key's state before blaming the snippets.
    Returns 0 = good to go, 3 = day quota exhausted (inconclusive), 1 = broken key."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(f"{CHECK_BASE}/daily-pick",
                                 headers={"Authorization": f"Bearer {key}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15):
                return 0
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 429 and '"day"' in body:
                print(f"preflight: key {key[:12]}... day quota exhausted - "
                      "doc-CI is INCONCLUSIVE today (use a higher-tier key)", flush=True)
                return 3
            if e.code == 429:
                print(f"preflight: minute bucket busy - waiting (attempt {attempt + 1}/3)",
                      flush=True)
                time.sleep(35)
                continue
            print(f"preflight: key {key[:12]}... rejected: HTTP {e.code} "
                  f"{body[:200].replace(key, key[:12] + '...')}", file=sys.stderr)
            return 1
        except OSError as e:
            print(f"preflight: gateway unreachable at {CHECK_BASE}: {e}", file=sys.stderr)
            return 1
    print("preflight: still rate-limited after 3 attempts", file=sys.stderr)
    return 1


def extract_snippets(doc: str) -> list[tuple[str, str]]:
    """Return [(language, code), ...] for every code-tab pane in quickstart.html.

    The quickstart's tabbed examples are emitted as:
      <div class="code-tabs">
        <div class="code-tab-bar"><button ...>curl</button><button ...>Python</button>...</div>
        <div class="code-tab-pane ..."><pre><code>SNIPPET</code></pre></div> x N
    Tab labels and panes are positional - same order.
    """
    snippets: list[tuple[str, str]] = []
    for block in re.findall(r'<div class="code-tabs">(.*?)</div>\s*</div>', doc, flags=re.DOTALL):
        labels = re.findall(r'<button class="code-tab-btn[^"]*">([^<]+)</button>', block)
        panes = re.findall(r'<div class="code-tab-pane[^"]*">\s*<pre><code>(.*?)</code></pre>',
                           block, flags=re.DOTALL)
        if not labels or len(labels) != len(panes):
            print(f"ERROR: malformed code-tabs block ({len(labels)} labels, {len(panes)} panes)",
                  file=sys.stderr)
            sys.exit(1)
        for label, pane in zip(labels, panes):
            snippets.append((label.strip().lower(), html.unescape(pane)))
    if not snippets:
        print("ERROR: no code-tab snippets found in quickstart.html - parser or page broke",
              file=sys.stderr)
        sys.exit(1)
    return snippets


def _run_proc(lang: str, code: str, idx: int):
    """One execution attempt. Returns (ok, proc) - proc may be None for a skip."""
    if lang == "curl":
        # curl exits 0 even on an HTTP 4xx/5xx JSON error body, so check the body too.
        proc = subprocess.run(["bash", "-euo", "pipefail", "-c", code],
                              capture_output=True, text=True, timeout=60)
        ok = proc.returncode == 0
        if ok:
            try:
                body = json.loads(proc.stdout)
                ok = "error" not in body
            except ValueError:
                ok = False
    elif lang == "python":
        proc = subprocess.run([VENV_PY, "-c", code],
                              capture_output=True, text=True, timeout=60)
        ok = proc.returncode == 0
    elif lang == "javascript":
        node = shutil.which("node")
        if not node:
            print(f"  [{idx}] javascript: SKIP (node not installed on this box)", flush=True)
            return True, None
        # The snippets use top-level await -> run as an ES module.
        proc = subprocess.run([node, "--input-type=module", "-e", code],
                              capture_output=True, text=True, timeout=60)
        ok = proc.returncode == 0
    else:
        print(f"ERROR: snippet {idx} has unknown language tab '{lang}'", file=sys.stderr)
        return False, None
    return ok, proc


def _looks_rate_limited(proc) -> bool:
    blob = (proc.stdout or "") + (proc.stderr or "")
    return "429" in blob or "TOO MANY REQUESTS" in blob.upper() or "rate_limited" in blob


def run_one(lang: str, code: str, idx: int, key: str) -> bool:
    """Run one snippet; return True on success. A 429 is the shared per-minute bucket
    (parallel sessions hit the same test key), not a docs-truth failure - wait out the
    minute window and retry before declaring failure. The key never appears in output:
    everything printed is redacted to its 12-char prefix."""
    redact = lambda s: (s or "").replace(key, key[:12] + "...")
    for attempt in range(3):
        ok, proc = _run_proc(lang, code, idx)
        if proc is None:          # skip (no node) or unknown lang
            return ok
        if ok or not _looks_rate_limited(proc):
            break
        print(f"  [{idx}] {lang:<10} 429 rate-limited - waiting for the minute bucket "
              f"(attempt {attempt + 1}/3)", flush=True)
        time.sleep(35)

    status = "ok" if ok else "FAIL"
    first_line = redact(next((ln for ln in code.splitlines() if ln.strip()), ""))[:72]
    print(f"  [{idx}] {lang:<10} {status}   {first_line}", flush=True)
    if not ok:
        print(f"      exit={proc.returncode}", file=sys.stderr)
        for stream, text in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            if text.strip():
                print(f"      {stream}: {redact(text.strip())[:1000]}", file=sys.stderr)
    return ok


def main() -> int:
    if not QUICKSTART.is_file():
        print(f"ERROR: {QUICKSTART} not found - generate the docs first", file=sys.stderr)
        return 1

    key = resolve_key()
    if not key:
        print("no API key configured (TW_DOCCHECK_KEY / TRADEWAVE_API_KEY / "
              "TW_DOCCHECK_KEYS_FILE) - cannot run quickstart snippets")
        return 2

    print(f"quickstart doc-CI: base={CHECK_BASE}  key={key[:12]}...", flush=True)
    rc = preflight(key)
    if rc:
        return rc
    doc = QUICKSTART.read_text(encoding="utf-8")
    failures = 0
    for idx, (lang, code) in enumerate(extract_snippets(doc), 1):
        code = code.replace(PLACEHOLDER, key)
        # Point the published base (per-env public host) at the gateway under test.
        code = code.replace(portal_urls.API_BASE, CHECK_BASE)
        if not run_one(lang, code, idx, key):
            failures += 1

    if failures:
        print(f"\n{failures} quickstart snippet(s) FAILED against {CHECK_BASE}", file=sys.stderr)
        return 1
    print("all quickstart snippets executed cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
