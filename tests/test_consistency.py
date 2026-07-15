"""Cross-surface drift guards for tracked MCP and API sources.

The generated ``site/api_docs/.well-known/mcp.json`` is intentionally ignored, so these
tests validate the tracked fail-closed generator contract and the server source directly.
That keeps a clean release checkout hermetic while still catching phantom tools, stale
descriptions, stale floors, and re-added portfolio tools.
"""
import ast
from pathlib import Path

import pytest

from apiserver import market_bands as mb

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
SERVER_PY = (REPO / "mcpserver" / "server.py").read_text(encoding="utf-8")
GENERATOR_PY = (REPO / "site" / "api_docs" / "generate_api_extras.py").read_text(
    encoding="utf-8"
)
OPENAPI = (REPO / "api" / "openapi.yaml").read_text(encoding="utf-8")

_FLAGSHIP = ["find_best_opportunities", "analyze_symbol", "explain_pick",
             "morning_briefing", "whats_seasonal_now", "compare_opportunities"]
_PRIMITIVES = ["list_markets", "whoami", "describe_tradewave", "list_symbols",
               "get_seasonal_opportunities", "get_symbol_patterns", "get_seasonal_pattern",
               "get_opportunity_chart", "score_opportunities", "get_daily_pick",
               "get_pick_track_record"]
_EXPECTED_TOOLS = _FLAGSHIP + _PRIMITIVES


def _server_tool_names():
    """The @mcp.tool-decorated function names in source order (static AST, no import)."""
    tree = ast.parse(SERVER_PY)
    names = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            call = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(call, ast.Attribute) and call.attr == "tool":
                names.append(node.name)
    return names


def _server_tool_descriptions():
    """Literal descriptions that the tracked generator publishes into mcp.json."""
    descriptions = []
    for node in ast.parse(SERVER_PY).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "tool"
            ):
                continue
            for kwarg in dec.keywords:
                if kwarg.arg == "description":
                    descriptions.append(ast.literal_eval(kwarg.value))
                    break
    return descriptions


def _generator_expected_tool_names():
    """Ordered keys in the generator's frozen public MCP input contract."""
    for node in ast.parse(GENERATOR_PY).body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "_EXPECTED_MCP_INPUTS"
               for target in node.targets):
            return list(ast.literal_eval(node.value))
    raise AssertionError("generate_api_extras.py has no _EXPECTED_MCP_INPUTS contract")


# --- the tool surface is exactly the 17, everywhere ------------------------------

def test_server_defines_exactly_the_17_tools_flagship_first():
    assert _server_tool_names() == _EXPECTED_TOOLS


def test_generator_contract_matches_the_live_tool_surface():
    assert _generator_expected_tool_names() == _EXPECTED_TOOLS


def test_no_phantom_tool_anywhere():
    for name in ("get_opportunity_for_symbol",):
        assert name not in SERVER_PY
        assert name not in _generator_expected_tool_names()


# --- educational-only: portfolio tools must stay eliminated (compliance guard) ----

def test_portfolio_tools_are_absent_from_code_and_generator():
    for banned in ("scan_my_portfolio", "analyze_my_book"):
        assert banned not in _server_tool_names()
        assert banned not in _generator_expected_tool_names()
        assert banned not in OPENAPI


# --- the describe_tradewave guide floors must match the live band manifest ---------

def test_describe_tradewave_example_floors_match_the_manifest():
    # the guide hardcodes example bands; if the data rebuild moves a floor, this fails so the
    # guide gets updated rather than silently lying to agents.
    for mid in ("2", "4", "9"):
        floor = mb.min_year2(mid, 20, "scan")
        assert ("%d-20" % floor) in SERVER_PY, (
            "describe_tradewave guide missing the %d-20 band for market %s" % (floor, mid))


def test_discovery_descriptions_reflect_current_capabilities():
    blob = " ".join(_server_tool_descriptions()).lower()
    for kw in ("view", "decision", "band", "min_winning", "extend_research", "chart"):
        assert kw in blob, "published tool descriptions never mention %r (stale?)" % kw


# --- the live market map underneath the band manifest ----------------------------

def test_symbol_path_markets_are_the_five_everywhere():
    # market_bands manifest + the doc string agree on the 5 per-symbol markets.
    assert mb.SYMBOL_MARKETS == ["0", "1", "2", "7", "9"]
    for mid in mb.SYMBOL_MARKETS:
        assert mid in SERVER_PY  # get_symbol_patterns lists the ids 0,1,2,7,9
