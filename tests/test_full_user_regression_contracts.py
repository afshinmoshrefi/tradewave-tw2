"""Regression contracts for defects found in the 2026-07-25 user-flow exercise."""

import ast
import math
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APPSERVER = ROOT / "appserver" / "appserver" / "appserver.py"
APP_JS = ROOT / "web-react" / "src" / "components" / "App.js"
REPORTS_JS = ROOT / "web-react" / "src" / "components" / "ReportsDashboard.js"
TEXT_BOX_INC_JS = ROOT / "web-react" / "src" / "components" / "TextBoxInc.js"
STOCK_LINE_CHART_JS = ROOT / "web-react" / "src" / "components" / "StockLineChart.js"
DESKTOP_LAYOUT_JS = ROOT / "web-react" / "src" / "components" / "DesktopLayout.js"
WATCHLIST_SETTINGS_JS = ROOT / "web-react" / "src" / "components" / "WatchlistSettings.js"
CHATBOT_JS = ROOT / "web-react" / "src" / "components" / "Chatbot.js"
CHATBOT_PY = ROOT / "appserver" / "appserver" / "chatbot.py"
CONFIG_PY = ROOT / "config.py"


def _functions(*names):
    module = ast.parse(APPSERVER.read_text(encoding="utf-8"))
    selected = [
        node for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    namespace = {"math": math}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(APPSERVER), "exec"), namespace)
    return namespace


def test_browser_login_uses_post_body_instead_of_credential_url():
    server = APPSERVER.read_text(encoding="utf-8")
    client = APP_JS.read_text(encoding="utf-8")
    assert "@app.route('/login/session', methods=['POST'])" in server
    assert "url: `${appserverURL()}/login/session`" in client
    assert "let url = `${appserverURL()}/login/session`" in client
    assert "/login/${userid}/" not in client


def test_realtime_quote_sanitizer_rejects_non_finite_prices():
    ns = _functions("_finite_number", "_sanitize_realtime_prices")
    sanitize = ns["_sanitize_realtime_prices"]
    assert sanitize({
        "GOOD": ["12.5", "-0.2"],
        "NA": ["NA", "NA"],
        "NAN": [float("nan"), 1],
        "ZERO": [0, 1],
    }) == {"GOOD": [12.5, -0.2]}


def test_equity_quote_guard_rejects_a_futures_namespace_collision():
    ns = _functions(
        "_finite_number",
        "_sanitize_realtime_prices",
        "validate_realtime_quote_for_resource",
    )
    ns["_load_commodity_symbols"] = lambda: {"ES"}
    ns["_latest_equity_close"] = lambda symbol: 74.62
    validate = ns["validate_realtime_quote_for_resource"]
    assert validate("2", "ES", [7442.5, 0.1]) is None
    assert validate("7", "ES", [7442.5, 0.1]) == [7442.5, 0.1]


def test_selected_equity_resource_is_preserved_for_overlapping_ticker():
    ns = _functions("resolve_resource_id")
    ns["_us_stock_groups"] = [("0", "dow"), ("2", "sp")]
    contents = {"dow": {"AAPL"}, "sp": {"AAPL", "LUV"}}
    ns["_load_us_stock_set"] = lambda resource_id, path: contents[path]
    assert ns["resolve_resource_id"]("AAPL", "2") == "2"
    assert ns["resolve_resource_id"]("AAPL", "0") == "0"


def test_report_urls_come_from_environment_public_root():
    source = APPSERVER.read_text(encoding="utf-8")
    assert source.count("config.tw2_public_url.rstrip('/')") >= 2
    assert 'report_url = f"https://tw2.trxstat.com/' not in source


def test_portfolio_footer_updates_only_for_the_selected_row():
    source = REPORTS_JS.read_text(encoding="utf-8")
    assert "if (parseInt(idx) === clickedRowIndex)" in source
    assert "SetSecurityData((current) => ({" in source


def test_market_switch_clears_all_prior_viewer_identity_and_chart_state():
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("const switchMarket = (marketDisplayName) =>")
    end = source.index("const selectboxChanged = (event) =>", start)
    switch_market = source[start:end]
    for reset in (
        "SetSymbol('')",
        "SetCompany('')",
        "SetSeasonalBarChartData([])",
        "SetTradeDetailData([])",
        "SetConsolidatedSeasonalData([])",
        "SetMaxYearsConsolidatedSeasonalData([])",
        "SetCompareSecurityBarChartData([])",
        "SetRowIndexClicked(-1)",
    ):
        assert reset in switch_market


def test_start_date_nudges_are_real_accessible_buttons():
    source = TEXT_BOX_INC_JS.read_text(encoding="utf-8")
    assert 'aria-label="Move start date one day earlier"' in source
    assert 'aria-label="Move start date one day later"' in source
    assert source.count('<button type="button"') == 2


def test_price_chart_mode_follows_the_range_actually_requested():
    source = STOCK_LINE_CHART_JS.read_text(encoding="utf-8")
    assert "const currentChartRequest = d1 > td" in source
    assert "if (currentChartRequest) {" in source
    assert "tmp2['pct'] === '0,0,0'" not in source


def test_watchlist_names_are_bounded_and_symbol_button_passes_no_event():
    client = WATCHLIST_SETTINGS_JS.read_text(encoding="utf-8")
    server = APPSERVER.read_text(encoding="utf-8")
    assert "const WATCHLIST_NAME_MAX_LENGTH = 64" in client
    assert "WATCHLIST_NAME_MAX_LENGTH = 64" in server
    assert client.count("watchlist_names_list'] === 'invalid_name'") >= 3
    assert "onClick={() => handleAddSymbol()}" in client
    assert "onClick={handleAddSymbol}" not in client
    assert "if not name or len(name) > WATCHLIST_NAME_MAX_LENGTH:" in server
    assert "if not new_name or len(new_name) > WATCHLIST_NAME_MAX_LENGTH:" in server
    assert "return jsonify({'watchlist_names_list': 'duplicate'})" in server


def test_user_scoped_preferences_survive_reload():
    app = APP_JS.read_text(encoding="utf-8")
    desktop = DESKTOP_LAYOUT_JS.read_text(encoding="utf-8")
    assert "const persisted = lsGet('tw_tooltips');" in app
    assert "const persisted = lsGet('tw_short_dates');" in app
    assert "lsSet('tw_tooltips', next);" in desktop
    assert "lsSet('tw_short_dates', next);" in desktop
    assert "localStorage.setItem('tw_short_dates'" not in desktop


def test_tara_uses_inclusive_dates_and_strips_unknown_html_tags():
    server = CHATBOT_PY.read_text(encoding="utf-8")
    client = CHATBOT_JS.read_text(encoding="utf-8")
    assert "timedelta(days=max(num_days - 1, 0))" in server
    assert "inclusive end date" in server
    assert "s.replace(/<(?!\\/?(?:b|br|i|a|span)\\b)[^>]*>/gi, '');" in client


def test_retired_symbols_are_filtered_after_cache_loading():
    ns = _functions("_drop_disabled_market_symbols")
    ns["config"] = SimpleNamespace(drop_symbols_by_market={"2": ["CTRA"]})
    drop = ns["_drop_disabled_market_symbols"]
    source = APPSERVER.read_text(encoding="utf-8")
    config = CONFIG_PY.read_text(encoding="utf-8")

    original = pd.DataFrame({"sym": ["AAPL", "CTRA"], "sharpe_ratio": [1.0, 2.0]})
    filtered = drop(original, "2")

    assert filtered["sym"].tolist() == ["AAPL"]
    assert original["sym"].tolist() == ["AAPL", "CTRA"]
    assert source.count("_drop_disabled_market_symbols(") == 3
    assert "'2':  ['CTRA']" in config
    assert "'3':  ['CTRA']" in config
