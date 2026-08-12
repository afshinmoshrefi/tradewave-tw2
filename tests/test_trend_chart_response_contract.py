import ast
from pathlib import Path


SOURCE_PATH = Path(__file__).parents[1] / "appserver" / "appserver" / "appserver.py"


def _trend_chart_function():
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "get_consolidated_seasonal_chart2"
    )


def _jsonify_payload(return_node):
    value = return_node.value
    if isinstance(value, ast.Tuple):
        value = value.elts[0]
    if not (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "jsonify"
        and value.args
        and isinstance(value.args[0], ast.Dict)
    ):
        return None
    return {
        key.value
        for key in value.args[0].keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def test_trend_chart_response_echoes_every_valid_request_identity():
    function = _trend_chart_function()
    source = ast.get_source_segment(SOURCE_PATH.read_text(encoding="utf-8"), function)

    assert "strptime(opp_start_date" in source
    assert "_{opp_start_date}" in source

    valid_chart_returns = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Return):
            continue
        payload = _jsonify_payload(node)
        if payload and "cons_seas_chart" in payload and "error" not in payload:
            valid_chart_returns.append(payload)

    assert valid_chart_returns
    assert all("request" in payload for payload in valid_chart_returns)

