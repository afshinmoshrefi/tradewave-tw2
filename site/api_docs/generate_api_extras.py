#!/usr/bin/env python3
"""Generate the downloadable developer artifacts that make the API feel like a mature
platform, all derived from the single source of truth (api/openapi.yaml):

  - openapi.yaml            : the raw spec (copied verbatim, for import into any tool)
  - openapi.json            : the same spec as JSON (for tools that prefer JSON)
  - tradewave.postman_collection.json : a ready-to-run Postman v2.1 collection with
                              every endpoint, {{base_url}} + {{api_key}} variables, and
                              collection-level Bearer auth
  - .well-known/mcp.json    : an MCP discovery manifest for the hosted MCP server

Output goes next to the rendered HTML docs (this dir, site/api_docs/) so the docs can link
to them; the deploy step publishes them under developers.tradewave.ai/docs/. Run:

  ./venv/bin/python site/api_docs/generate_api_extras.py

Signals-only safety note: these artifacts only describe the public /v1 surface (which is
signals-only); they expose no raw-price endpoints.
"""
import ast
import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent                       # /home/flask
OPENAPI_YAML = REPO / "api" / "openapi.yaml"
MCP_SERVER_PY = REPO / "mcpserver" / "server.py"
sys.path.insert(0, str(REPO / "site" / "lib"))
import portal_urls  # noqa: E402

# Public hosts (env-resolved; dev defaults otherwise).
API_BASE = portal_urls.API_BASE                 # https://api.tradewave.ai/v1
MCP_URL = portal_urls.MCP_URL                   # https://mcp.tradewave.ai
DOCS_URL = portal_urls.DOCS_URL
CONSOLE_URL = portal_urls.CONSOLE_URL

# Sensible, immediately-runnable example values for the known query params, so an imported
# Postman request works on the first send (the user just fills in {{api_key}}).
_PARAM_EXAMPLES = {
    "markets": "2,11", "window": "now", "direction": "long", "min_win_rate": "0.6",
    "min_years": "5", "rank_by": "sharpe", "limit": "10", "market": "2", "market_id": "2",
    "symbol": "DOV", "from": "", "to": "", "days_out": "30", "entry_date": "",
}
# Path-param example values (substituted into the URL path).
_PATH_EXAMPLES = {"symbol": "DOV", "market_id": "2"}

# The /score POST body example (signals-only inputs; the response carries the ML block).
_SCORE_BODY = {
    "opportunities": [
        {"symbol": "DOV", "date": "2026-06-02", "days_out": 30, "direction": "long", "market": "2"}
    ]
}

# The MCP tool surface is NOT hand-maintained here: it is DERIVED, at generation time, by
# statically parsing the one source of truth (mcpserver/server.py) with Python's ast module.
# We never import server.py (it pulls in fastmcp + the full server runtime); we read it as text
# and walk the AST, so this generator stays a pure, dependency-light build step. For every
# @mcp.tool-decorated function we take the def name and its description= kwarg (an implicitly
# concatenated string literal). Source order is preserved (server.py defines the 5 flagships
# first, then the 11 primitives), so the manifest cannot drift from the live tool surface.

# Sentence terminators followed by whitespace + the start of a new sentence. We require the next
# char to be an uppercase letter / quote / digit so we do not break on the decimal point in
# "0-100", "5%", "v2.1", a mid-sentence "i.e."/"e.g.", or a '?'/'!' that sits inside a quoted
# phrase like 'show me SYMBOL's patterns' (there the terminator is followed by a closing quote,
# not a new sentence).
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'‘“])")
# Phrases that mark a sentence as carrying a current capability we want the discovery manifest to
# reflect even if it falls past the lead sentences (progressive-disclosure view, the per-market
# detection band, the extend_research hand-off, one-call charting, per-symbol coverage).
_CAPABILITY_HINTS = (
    "view=", "decision view", "view='", "extend_research", "include_chart", "trend chart",
    "detection band", "win-rate band", "per-symbol", "per-year", "ids 0,1,2,7,9",
)


def _str_from_kwarg(node: ast.AST) -> str | None:
    """Evaluate a description= value that is a (possibly implicitly concatenated) string literal.
    Returns the joined string, or None if the value is not a pure constant string expression."""
    try:
        value = ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None
    return value if isinstance(value, str) else None


def _split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_RE.split(text) if s.strip()]


def _trim_description(desc: str, head_max: int = 300, total_max: int = 480) -> str:
    """Trim a long tool description to a discovery-manifest length while keeping it CURRENT.

    Strategy: keep the first 1-2 sentences as the lead (up to head_max chars), then, if a later
    sentence advertises a current capability (progressive-disclosure view, the detection band, the
    extend_research hand-off, one-call charting, per-symbol coverage) that the lead omits, append
    that single capability sentence so the manifest still reflects it - capped at total_max chars.
    """
    desc = " ".join(desc.split())
    sentences = _split_sentences(desc)
    if not sentences:
        return desc[:total_max].rstrip()

    def _pack(items: list[str], budget: int) -> tuple[str, int]:
        """Join WHOLE sentences (never a partial) until adding the next would exceed budget;
        always take at least the first. Returns (text, number_of_sentences_consumed)."""
        out = items[0]
        used = 1
        for s in items[1:]:
            if len(out) + 1 + len(s) > budget:
                break
            out += " " + s
            used += 1
        return out, used

    # Lead: the first 1-2 whole sentences (up to head_max).
    head, consumed = _pack(sentences, head_max)

    head_lower = head.lower()
    # If the lead already advertises a current capability, the trimmed lead is enough.
    if not any(h in head_lower for h in _CAPABILITY_HINTS):
        for s in sentences[consumed:]:
            if any(h in s.lower() for h in _CAPABILITY_HINTS):
                if len(head) + 1 + len(s) <= total_max:
                    head = head + " " + s
                else:
                    # The capability sentence is the priority: keep it whole and shrink the lead
                    # to whole sentences only (never a dangling partial), within the remaining room.
                    room = total_max - len(s) - 1
                    if room >= len(sentences[0]):
                        lead, _ = _pack(sentences[:consumed], room)
                        head = lead + " " + s
                    else:
                        head = s  # lead won't fit cleanly; lead with the capability sentence
                break
    return head.strip()


def _derive_mcp_tools() -> list[tuple[str, str]]:
    """Statically parse mcpserver/server.py and return [(tool_name, trimmed_description), ...] in
    source order, one entry per @mcp.tool(...)-decorated function. Raises if server.py is missing
    so the build fails loudly rather than silently emitting a stale/empty manifest."""
    source = MCP_SERVER_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MCP_SERVER_PY))
    tools: list[tuple[str, str]] = []
    # Iterate top-level statements to guarantee source order (the tools are module-level defs).
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            # Match @mcp.tool(...) -> a Call whose func is an attribute access ending in '.tool'.
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "tool"):
                continue
            desc = None
            for kw in dec.keywords:
                if kw.arg == "description":
                    desc = _str_from_kwarg(kw.value)
                    break
            if desc:
                tools.append((node.name, _trim_description(desc)))
            break  # one @mcp.tool per function
    return tools


# Derived once at import; 16 tools = 5 flagship + 11 primitives, in server.py source order.
_MCP_TOOLS = _derive_mcp_tools()


def _load_spec():
    with open(OPENAPI_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"  {len(text):>8,} bytes -> {path}")


def _postman_url(path: str, params: list):
    """Build a Postman url object for a path, substituting {var} path params and adding query
    params with example values (disabled if we have no example, so they are visible but inert)."""
    raw_path = path
    segs = []
    for seg in path.strip("/").split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            name = seg[1:-1]
            val = _PATH_EXAMPLES.get(name, ":" + name)
            raw_path = raw_path.replace(seg, val)
            segs.append(val)
        else:
            segs.append(seg)
    query = []
    for p in params:
        if p.get("in") != "query":
            continue
        name = p.get("name")
        ex = _PARAM_EXAMPLES.get(name, "")
        query.append({"key": name, "value": ex, "disabled": ex == "",
                      "description": (p.get("description") or "").strip()[:160]})
    url = {
        "raw": "{{base_url}}" + raw_path + ("?" + "&".join(f"{q['key']}={q['value']}" for q in query if not q["disabled"]) if any(not q["disabled"] for q in query) else ""),
        "host": ["{{base_url}}"],
        "path": [s for s in raw_path.strip("/").split("/") if s],
    }
    if query:
        url["query"] = query
    return url


def build_postman(spec: dict) -> str:
    items = []
    for path, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            params = op.get("parameters", []) or []
            req = {
                "method": method.upper(),
                "header": [{"key": "Accept", "value": "application/json"}],
                "url": _postman_url(path, params),
                "description": (op.get("summary") or op.get("description") or "").strip(),
            }
            if method == "post" and path == "/score":
                req["header"].append({"key": "Content-Type", "value": "application/json"})
                req["body"] = {"mode": "raw", "raw": json.dumps(_SCORE_BODY, indent=2),
                               "options": {"raw": {"language": "json"}}}
            items.append({"name": f"{method.upper()} {path}", "request": req})

    collection = {
        "info": {
            "name": "TradeWave Data API (v1)",
            "description": ("Seasonal-edge + ML trading signals. Signals only - no raw prices. "
                            f"Set the collection variable api_key to your tw_live_ key (get one at {CONSOLE_URL}). "
                            f"Docs: {DOCS_URL}"),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{api_key}}", "type": "string"}]},
        "variable": [
            {"key": "base_url", "value": API_BASE, "type": "string"},
            {"key": "api_key", "value": "tw_live_REPLACE_ME", "type": "string"},
        ],
        "item": items,
    }
    return json.dumps(collection, indent=2)


def build_well_known_mcp() -> str:
    manifest = {
        "name": "TradeWave",
        "description": ("Seasonal-edge and ML trading signals for AI agents. Signals only "
                        "(percentages and a normalized 0-100 seasonal index, never raw prices); "
                        "broker-agnostic. Includes a public, forward-tested daily-pick track record."),
        "version": "1.0.0",
        "documentation": DOCS_URL,
        "mcp": {
            "url": MCP_URL,
            "transport": ["streamable-http", "sse"],
            "authentication": {
                "type": "bearer",
                "description": "Send your TradeWave API key (tw_live_...) as Authorization: Bearer <key>.",
                "instructions_url": f"{DOCS_URL}/mcp-reference.html",
                "token_url": CONSOLE_URL,
            },
        },
        "tools": [{"name": n, "description": d} for n, d in _MCP_TOOLS],
        "contact": {"homepage": portal_urls.MAIN_URL},
    }
    return json.dumps(manifest, indent=2)


def main():
    spec = _load_spec()
    print("TradeWave API extras generator")
    print(f"  spec: {OPENAPI_YAML}\n")
    # 1) raw spec (yaml verbatim + json)
    _write(HERE / "openapi.yaml", OPENAPI_YAML.read_text(encoding="utf-8"))
    _write(HERE / "openapi.json", json.dumps(spec, indent=2))
    # 2) Postman collection
    _write(HERE / "tradewave.postman_collection.json", build_postman(spec))
    # 3) MCP discovery manifest
    _write(HERE / ".well-known" / "mcp.json", build_well_known_mcp())
    print("\nDone.")


if __name__ == "__main__":
    main()
