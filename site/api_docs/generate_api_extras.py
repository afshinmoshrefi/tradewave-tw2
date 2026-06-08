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
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent                       # /home/flask
OPENAPI_YAML = REPO / "api" / "openapi.yaml"
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

# The MCP tool surface (kept in lockstep with api/MCP_TOOLS.md + mcpserver/server.py):
# 16 tools = 5 flagship + 11 primitives. Flagship are listed first.
_MCP_TOOLS = [
    # Flagship (5)
    ("find_best_opportunities", "Scan the markets in your scope and return the best seasonal setups as ranked SignalCards."),
    ("analyze_symbol", "Deep-dive one symbol into a rich SignalCard (best setup, receipts, order ticket) plus its other setups; pin a specific opportunity by entry_date or a date-range preset."),
    ("explain_pick", "Today's daily pick as a SignalCard, with its live forward-tested track record as proof."),
    ("whats_seasonal_now", "Setups entering their seasonal window in the next ~10 trading days (a weekly digest)."),
    ("compare_opportunities", "Deep-dive several symbols and return them side by side for a head-to-head."),
    # Primitives (11)
    ("list_markets", "The markets in your scope and which support ML."),
    ("whoami", "The caller's identity and entitlements from the API key - tier, in-scope markets, ML allowance, remaining quota."),
    ("describe_tradewave", "Self-documents the method: the seasonal + 62-feature-ML edge, what TradeWave is blind to (fundamentals, news, macro, live price), and how to pair it with the assistant's own research."),
    ("list_symbols", "The symbols in a market."),
    ("get_seasonal_opportunities", "Raw single-market ranked seasonal setups."),
    ("get_symbol_patterns", "Every raw seasonal setup for one symbol."),
    ("get_seasonal_pattern", "Bare aggregate seasonal pattern stats for a symbol (no price series)."),
    ("get_opportunity_chart", "The Trend Chart data: a single year-averaged, normalized 0-100 seasonal index curve (the typical within-year shape, never a price)."),
    ("score_opportunities", "ML score a list of setups (ml_score, win_prob, predicted return)."),
    ("get_daily_pick", "The bare daily-pick payload."),
    ("get_pick_track_record", "The realized win/loss record of past daily picks."),
]


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
