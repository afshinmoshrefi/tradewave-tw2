"""Hermetic freeze test for the public MCP inventory and input schema.

ChatGPT custom apps use a reviewed, frozen snapshot of tools/list.  This test keeps
the repository's server source, portal generator freeze, and release acceptance
matrix on the same exact 17-tool contract without importing FastMCP or making a
network request.  ops/verify_mcp_contract.py performs the complementary live check.
"""
import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "mcpserver" / "server.py"
GENERATOR = REPO / "site" / "api_docs" / "generate_api_extras.py"
DOCS_GENERATOR = REPO / "site" / "api_docs" / "generate_api_docs.py"
MARKETING_GENERATOR = REPO / "site" / "api_marketing" / "generate.py"

# Ordered fields: (argument name, accepted non-null JSON types, required).
EXPECTED = {
    "find_best_opportunities": (
        ("markets", {"array", "string"}, False), ("window", {"string"}, False),
        ("direction", {"string"}, False), ("min_win_rate", {"number"}, False),
        ("min_years", {"integer"}, False), ("min_days", {"integer"}, False),
        ("max_days", {"integer"}, False), ("min_avg_return", {"number"}, False),
        ("min_median_return", {"number"}, False), ("min_sharpe", {"number"}, False),
        ("pe_cycle", {"string"}, False), ("years", {"integer"}, False),
        ("min_winning_years", {"integer"}, False), ("rank_by", {"string"}, False),
        ("limit", {"integer"}, False), ("view", {"string"}, False),
    ),
    "analyze_symbol": (
        ("symbol", {"string"}, True), ("market", {"string"}, False),
        ("direction", {"string"}, False), ("days_out", {"integer"}, False),
        ("entry_date", {"string"}, False), ("pe_cycle", {"string"}, False),
        ("years", {"integer"}, False), ("period", {"string"}, False),
        ("reverse", {"boolean"}, False), ("view", {"string"}, False),
        ("include_chart", {"boolean"}, False),
    ),
    "explain_pick": (),
    "morning_briefing": (),
    "whats_seasonal_now": (
        ("markets", {"array", "string"}, False),
        ("min_win_rate", {"number"}, False), ("view", {"string"}, False),
    ),
    "compare_opportunities": (
        ("symbols", {"array"}, True), ("market", {"string"}, False),
        ("view", {"string"}, False),
    ),
    "list_markets": (),
    "whoami": (),
    "describe_tradewave": (),
    "list_symbols": (
        ("market", {"string"}, True), ("prefix", {"string"}, False),
        ("limit", {"integer"}, False),
    ),
    "get_seasonal_opportunities": (
        ("market", {"string"}, True), ("from_date", {"string"}, False),
        ("direction", {"string"}, False),
        ("min_win_rate", {"number"}, False), ("min_days", {"integer"}, False),
        ("max_days", {"integer"}, False), ("min_avg_return", {"number"}, False),
        ("min_median_return", {"number"}, False), ("min_sharpe", {"number"}, False),
        ("pe_cycle", {"string"}, False), ("years", {"integer"}, False),
        ("min_winning_years", {"integer"}, False), ("limit", {"integer"}, False),
    ),
    "get_symbol_patterns": (
        ("symbol", {"string"}, True), ("market", {"string"}, True),
        ("pe_cycle", {"string"}, False), ("years", {"integer"}, False),
        ("min_winning_years", {"integer"}, False), ("min_days", {"integer"}, False),
        ("max_days", {"integer"}, False), ("min_avg_return", {"number"}, False),
        ("min_sharpe", {"number"}, False),
    ),
    "get_seasonal_pattern": (
        ("market", {"string"}, True), ("symbol", {"string"}, True),
        ("pe_cycle", {"string"}, False), ("years", {"integer"}, False),
        ("period", {"string"}, False), ("reverse", {"boolean"}, False),
    ),
    "get_opportunity_chart": (
        ("market", {"string"}, True), ("symbol", {"string"}, True),
        ("entry_date", {"string"}, False), ("days_out", {"integer"}, False),
        ("direction", {"string"}, False), ("years", {"string"}, False),
        ("pe_cycle", {"string"}, False), ("period", {"string"}, False),
        ("reverse", {"boolean"}, False),
    ),
    "score_opportunities": (
        ("opportunities", {"array"}, True), ("market", {"string"}, False),
    ),
    "get_daily_pick": (),
    "get_pick_track_record": (),
}


def _tool_nodes(source):
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "tool"):
                yield node, decorator
                break


def _alias_nodes(source):
    aliases = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id.startswith("_"):
                aliases[target.id] = node.value
    return aliases


def _json_types(annotation, aliases):
    if isinstance(annotation, ast.Subscript):
        name = annotation.value.id if isinstance(annotation.value, ast.Name) else None
        value = annotation.slice.value if isinstance(annotation.slice, ast.Index) else annotation.slice
        if name == "Annotated":
            value = value.elts[0]
            return _json_types(value, aliases)
        if name == "Optional":
            return _json_types(value, aliases)
        if name == "list":
            return {"array"}
        if name == "dict":
            return {"object"}
        if name == "Literal":
            values = value.elts if isinstance(value, ast.Tuple) else [value]
            result = set()
            for item in values:
                literal = ast.literal_eval(item)
                result.add({str: "string", int: "integer", float: "number",
                            bool: "boolean"}[type(literal)])
            return result
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _json_types(annotation.left, aliases) | _json_types(annotation.right, aliases)
    if isinstance(annotation, ast.Name):
        built_in = {
            "str": {"string"}, "int": {"integer"}, "float": {"number"},
            "bool": {"boolean"}, "None": set(),
        }.get(annotation.id)
        if built_in is not None:
            return built_in
        if annotation.id in aliases:
            return _json_types(aliases[annotation.id], aliases)
    return set()


def _source_contract(node, aliases):
    positional = [*node.args.posonlyargs, *node.args.args]
    defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
    fields = []
    for arg, default in zip(positional, defaults):
        if arg.arg != "ctx":
            fields.append((arg.arg, _json_types(arg.annotation, aliases), default is None))
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        if arg.arg != "ctx":
            fields.append((arg.arg, _json_types(arg.annotation, aliases), default is None))
    return tuple(fields)


def _literal_assignment(source, name):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError("missing assignment %s" % name)


def test_server_source_is_exact_frozen_17_tool_schema():
    source = SERVER.read_text(encoding="utf-8")
    aliases = _alias_nodes(source)
    tools = list(_tool_nodes(source))
    assert [node.name for node, _ in tools] == list(EXPECTED)
    for node, _ in tools:
        assert _source_contract(node, aliases) == EXPECTED[node.name]
        assert isinstance(node, ast.AsyncFunctionDef), "%s must remain async" % node.name


def test_tool_descriptions_have_current_public_language_only():
    source = SERVER.read_text(encoding="utf-8")
    descriptions = {}
    for node, decorator in _tool_nodes(source):
        kw = next(item for item in decorator.keywords if item.arg == "description")
        descriptions[node.name] = ast.literal_eval(kw.value)
    blob = " ".join(descriptions.values())
    for stale in ("SignalCard", "NO_SIGNAL", "get_opportunity_for_symbol"):
        assert stale not in blob
    for current in ("Pattern Card", "neutral", "view='full'", "include_chart=true"):
        assert current in blob


def test_portal_generator_freeze_matches_server_acceptance_matrix():
    source = GENERATOR.read_text(encoding="utf-8")
    frozen_inputs = _literal_assignment(source, "_EXPECTED_MCP_INPUTS")
    frozen_required = _literal_assignment(source, "_EXPECTED_MCP_REQUIRED")
    assert list(frozen_inputs) == list(EXPECTED)
    for name, fields in EXPECTED.items():
        assert tuple(field[0] for field in fields) == frozen_inputs[name]
        assert tuple(field[0] for field in fields if field[2]) == frozen_required.get(name, ())


def test_compare_schema_has_release_safety_bounds():
    source = SERVER.read_text(encoding="utf-8")
    node = next(node for node, _ in _tool_nodes(source) if node.name == "compare_opportunities")
    annotation = next(arg.annotation for arg in node.args.args if arg.arg == "symbols")
    text = ast.get_source_segment(source, annotation)
    assert "min_length=2" in text
    assert "max_length=_COMPARE_MAX_SYMBOLS" in text
    assert _literal_assignment(source, "_COMPARE_MAX_SYMBOLS") == 10


def test_score_schema_is_typed_and_capped_at_100_items():
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    score_batch = _alias_nodes(source)["_ScoreBatch"]
    batch_text = ast.get_source_segment(source, score_batch)
    assert "min_length=1" in batch_text
    assert "max_length=100" in batch_text

    item = next(node for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == "_ScoreOpportunity")
    aliases = _alias_nodes(source)
    fields = [(node.target.id, _json_types(node.annotation, aliases)) for node in item.body
              if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)]
    assert fields == [
        ("symbol", {"string"}), ("date", {"string"}),
        ("days_out", {"integer"}), ("direction", {"string"}),
    ]


def _argument_source(source, tool_name, field_name):
    node = next(node for node, _ in _tool_nodes(source) if node.name == tool_name)
    args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    annotation = next(arg.annotation for arg in args if arg.arg == field_name)
    return ast.get_source_segment(source, annotation)


def test_canonical_enum_aliases_and_numeric_bounds_are_frozen_in_source():
    source = SERVER.read_text(encoding="utf-8")
    aliases = _alias_nodes(source)
    expected_aliases = {
        "_Direction": ("long", "short"),
        "_View": ("decision", "table", "full"),
        "_RankBy": ("edge", "win_rate", "sharpe", "ml", "avg_return"),
        "_ListPeCycle": ("consecutive", "pe"),
        "_ChartPeCycle": ("consecutive", "pe", "pe0", "pe1", "pe2", "pe3"),
        "_Period": (
            "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
            "nov", "dec", "q1", "q2", "q3", "q4", "spring", "summer", "fall",
            "winter", "ytd", "year_end", "buy_hold",
        ),
        "_MlMarketToken": ("0", "1", "2", "3", "4", "11"),
    }
    for alias, expected in expected_aliases.items():
        literal = next(node for node in ast.walk(aliases[alias])
                       if isinstance(node, ast.Subscript)
                       and isinstance(node.value, ast.Name) and node.value.id == "Literal")
        value = literal.slice.value if isinstance(literal.slice, ast.Index) else literal.slice
        assert ast.literal_eval(value) == expected

    enum_fields = {
        ("find_best_opportunities", "direction"): "_Direction",
        ("find_best_opportunities", "rank_by"): "_RankBy",
        ("analyze_symbol", "period"): "_Period",
        ("get_seasonal_pattern", "pe_cycle"): "_ChartPeCycle",
        ("score_opportunities", "market"): "_MlMarketToken",
    }
    for (tool, field), alias in enum_fields.items():
        assert alias in _argument_source(source, tool, field)

    bounded_fields = {
        ("find_best_opportunities", "min_win_rate"): ("ge=0", "le=1"),
        ("find_best_opportunities", "min_years"): ("ge=1", "le=99"),
        ("find_best_opportunities", "min_days"): ("ge=1", "le=366"),
        ("find_best_opportunities", "limit"): ("ge=1", "le=100"),
        ("list_symbols", "limit"): ("ge=1", "le=1000"),
        ("get_seasonal_opportunities", "min_winning_years"): ("ge=0", "le=99"),
        ("get_seasonal_opportunities", "limit"): ("ge=1", "le=100"),
        ("get_opportunity_chart", "days_out"): ("ge=1", "le=366"),
    }
    for (tool, field), bounds in bounded_fields.items():
        text = _argument_source(source, tool, field)
        assert all(bound in text for bound in bounds), (tool, field, text)

    assert r"^(?:[1-9]|[1-9]\d)$" in ast.get_source_segment(source, aliases["_ChartYears"])


def test_tool_safety_annotations_are_explicit_and_correct():
    source = SERVER.read_text(encoding="utf-8")
    metered = {
        "find_best_opportunities", "analyze_symbol", "morning_briefing",
        "whats_seasonal_now", "compare_opportunities", "get_seasonal_opportunities",
        "score_opportunities",
    }
    for node, decorator in _tool_nodes(source):
        annotation = next(kw.value for kw in decorator.keywords if kw.arg == "annotations")
        assert isinstance(annotation, ast.Name)
        assert annotation.id == ("_METERED_TOOL" if node.name in metered else "_READ_ONLY_TOOL")

    assignments = _alias_nodes(source)
    for name, expected in {
        "_READ_ONLY_TOOL": {
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        "_METERED_TOOL": {
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": False,
        },
    }.items():
        call = assignments[name]
        assert isinstance(call, ast.Call)
        actual = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
        assert actual == expected


def _manual_tool_card(source, name):
    marker = f'<span class="tool-name">{name}</span>'
    assert marker in source
    tail = source.split(marker, 1)[1]
    return tail.split('<div class="tool-card">', 1)[0]


def test_demo_facing_manual_reference_does_not_invite_invalid_tool_calls():
    source = DOCS_GENERATOR.read_text(encoding="utf-8")
    find = _manual_tool_card(source, "find_best_opportunities")
    assert '<code class="inline-code">markets</code>' in find
    assert '<code class="inline-code">market</code>' not in find

    explain = _manual_tool_card(source, "explain_pick")
    assert '<strong>Inputs:</strong> none' in explain
    assert 'GET /v1/daily-pick' in explain and '/v1/analyze/' not in explain

    compare = _manual_tool_card(source, "compare_opportunities")
    assert '<code class="inline-code">symbols</code>' in compare
    assert 'entry_date' not in compare

    whoami = _manual_tool_card(source, "whoami")
    assert 'GET /v1/me' in whoami and 'GET /v1/markets' not in whoami

    symbol_patterns = _manual_tool_card(source, "get_symbol_patterns")
    assert 'GET /v1/securities/{{symbol}}/patterns' in symbol_patterns

    chart = _manual_tool_card(source, "get_opportunity_chart")
    for field in ("pe_cycle", "period", "reverse"):
        assert f'<code class="inline-code">{field}</code>' in chart

    chatgpt = source.split("<h3>ChatGPT</h3>", 1)[1].split("<h3>Claude.ai</h3>", 1)[0]
    assert "Settings &rarr; Apps &rarr; Create" in chatgpt
    assert "Settings &rarr; Connectors" not in chatgpt


def test_public_copy_keeps_default_market_and_progressive_disclosure_honest():
    paths = [
        REPO / "api" / "MCP_TOOLS.md",
        REPO / "api" / "openapi.yaml",
        REPO / "api" / "sdks" / "python" / "README.md",
        REPO / "api" / "sdks" / "python" / "tradewave" / "client.py",
        REPO / "api" / "sdks" / "typescript" / "README.md",
        REPO / "api" / "sdks" / "typescript" / "src" / "client.ts",
        REPO / "site" / "content" / "learn_api" / "connect-an-ai-agent-mcp.md",
        REPO / "site" / "content" / "learn_api" / "cross-market-screener.md",
        REPO / "site" / "content" / "learn_api" / "build-dont-rebuild.md",
        REPO / "site" / "lib" / "llms_agent_append.md",
        REPO / "site" / "api_playground" / "generate_playground.py",
        REPO / "site" / "api_marketing" / "for_agents_copy.json",
        MARKETING_GENERATOR,
    ]
    blob = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for stale in (
        "default = ALL in-scope",
        "blank = all in scope",
        "Every flagship tool takes a `view`",
        "daily, universe-wide scan",
        "All seasonal patterns for one specific symbol",
        "Omit to use your full scope",
        "ranked PatternCards across in-scope markets",
    ):
        assert stale not in blob
    assert "liquid-equities core" in blob
