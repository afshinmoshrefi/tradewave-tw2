"""Cross-surface drift guards. These fail loudly if the code and the agent/dev-facing
artifacts (the MCP discovery manifest, the describe_tradewave guide, the OpenAPI spec) ever
fall out of sync - the failure mode that bit us before (a phantom tool, a stale floor, a
re-added portfolio tool). Hermetic: pure file reads, no DB/redis/appserver/fastmcp.
"""
import ast
import importlib.util
import json
from pathlib import Path

import pytest

from apiserver import market_bands as mb
from apiserver import tiers

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
SERVER_PY = (REPO / "mcpserver" / "server.py").read_text()
OPENAPI = (REPO / "api" / "openapi.yaml").read_text()
PRICING_SPEC = (REPO / "docs" / "PRICING_QUOTA_SPEC.md").read_text()


def _generated_manifest():
    """Build the manifest from source without relying on ignored build output."""
    generator_path = REPO / "site" / "api_docs" / "generate_api_extras.py"
    spec = importlib.util.spec_from_file_location(
        "_tradewave_generate_api_extras", generator_path
    )
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    return json.loads(generator.build_well_known_mcp())


MANIFEST = _generated_manifest()

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


# --- the tool surface is exactly the 17, everywhere ------------------------------

def test_server_defines_exactly_the_17_tools_flagship_first():
    assert _server_tool_names() == _EXPECTED_TOOLS


def test_manifest_matches_the_live_tool_surface():
    manifest_names = [t["name"] for t in MANIFEST["tools"]]
    assert manifest_names == _EXPECTED_TOOLS          # 17, flagship-first, derived from server.py


def test_no_phantom_tool_anywhere():
    for name in ("get_opportunity_for_symbol",):
        assert name not in [t["name"] for t in MANIFEST["tools"]]
        assert name not in SERVER_PY


# --- educational-only: portfolio tools must stay eliminated (compliance guard) ----

def test_portfolio_tools_are_absent_from_code_and_manifest():
    for banned in ("scan_my_portfolio", "analyze_my_book"):
        assert banned not in _server_tool_names()
        assert banned not in [t["name"] for t in MANIFEST["tools"]]
        assert banned not in OPENAPI


# --- the describe_tradewave guide floors must match the live band manifest ---------

def test_describe_tradewave_example_floors_match_the_manifest():
    # the guide hardcodes example bands; if the data rebuild moves a floor, this fails so the
    # guide gets updated rather than silently lying to agents.
    for mid in ("2", "4", "9"):
        floor = mb.min_year2(mid, 20, "scan")
        assert ("%d-20" % floor) in SERVER_PY, (
            "describe_tradewave guide missing the %d-20 band for market %s" % (floor, mid))


def test_manifest_descriptions_reflect_current_capabilities():
    blob = " ".join(t["description"] for t in MANIFEST["tools"]).lower()
    for kw in ("view", "decision", "band", "min_winning", "extend_research", "chart"):
        assert kw in blob, "manifest descriptions never mention %r (stale?)" % kw


# --- the live market map underneath the band manifest ----------------------------

def test_symbol_path_markets_are_the_five_everywhere():
    # market_bands manifest + the doc string agree on the 5 per-symbol markets.
    assert mb.SYMBOL_MARKETS == ["0", "1", "2", "7", "9"]
    for mid in mb.SYMBOL_MARKETS:
        assert mid in SERVER_PY  # get_symbol_patterns lists the ids 0,1,2,7,9


# --- commercial contract: runtime, console, and current spec must move together ---

def test_api_price_and_quota_contract_matches_current_spec():
    expected = {
        "free": (0, 0, 10, 100),
        "dev": (39, 390, 60, 5_000),
        "pro": (199, 1_990, 120, 50_000),
        "business": (599, 5_990, 300, 250_000),
    }
    for name, (monthly, annual, per_minute, per_day) in expected.items():
        entitlement = tiers.API_TIERS[name]
        assert entitlement["price_monthly"] == monthly
        assert entitlement["price_annual"] == annual
        assert entitlement["rate"] == {
            "per_minute": per_minute,
            "per_day": per_day,
        }

    assert tiers.WEB_TIER_TO_MCP["analyst"]["rate"]["per_day"] == 5_000
    assert tiers.WEB_TIER_TO_MCP["strategist"]["rate"]["per_day"] == 20_000
    assert "| Annual price | $0 | $390 | $1,990 | $5,990 |" in PRICING_SPEC
    assert "| Rate per minute / day | 10 / 100 | 60 / 5,000 | 120 / 50,000 | 300 / 250,000 |" in PRICING_SPEC


def test_explicit_and_bundled_api_tiers_resolve_by_max_rank(caplog):
    assert tiers.api_tier_from_user(
        {"tier": "strategist", "api_tier": "dev"}
    ) == "pro"
    assert tiers.api_tier_from_user(
        {"tier": "explorer", "api_tier": "dev"}
    ) == "dev"
    assert tiers.api_tier_from_user(
        {"tier": "explorer", "api_tier": "mcp"}
    ) == "free"
    assert "ignoring unrankable explicit api_tier='mcp'" in caplog.text


def test_service_key_provisioners_preserve_configured_keys_and_roles():
    for filename, env_name in (
        ("provision_mcp_key.py", "MCP_GATEWAY_KEY"),
        ("provision_chatbot_key.py", "TARA_GATEWAY_KEY"),
    ):
        source = (REPO / "apiserver" / filename).read_text()
        assert f'os.environ.get("{env_name}")' in source
        assert "service_account" in source
        assert "key_hash <> %s" in source
        assert "revoked_at = NULL" in source


def test_api_billing_sources_keep_both_intervals():
    paths = [
        REPO / "web" / "api_portal" / "create_api_products.py",
        REPO / "web" / "api_portal" / "routes_billing.py",
        REPO / "web" / "api_portal" / "templates" / "api_billing.html",
        REPO / "site" / "api_marketing" / "generate.py",
    ]
    sources = [path.read_text() for path in paths]
    assert all("price_annual" in source for source in sources)
    assert "_ensure_price(stripe, product, tier, \"year\"" in sources[0]
    assert "data-cycle=\"year\"" in sources[2]
    assert "id=\"btn-annual\"" in sources[3]


def test_web_imports_are_release_tree_relative():
    """An isolated candidate must not import modules from the live checkout."""
    app_source = (REPO / "web" / "app.py").read_text()
    models_source = (REPO / "web" / "models.py").read_text()

    assert "Path(__file__).resolve().parents[1]" in app_source
    assert "Path(__file__).resolve().parents[1]" in models_source
    guarded_paths = [
        *sorted((REPO / "web").rglob("*.py")),
        *sorted((REPO / "tests").rglob("*.py")),
        REPO / "migrations" / "env.py",
        REPO / "ops" / "audit_stripe_subscription_identity.py",
        REPO / "ops" / "backfill_active_reverse_trial_lifecycle.py",
    ]
    forbidden = (
        'sys.path.insert(0, "/home/flask',
        "sys.path.insert(0, '/home/flask",
        'Path("/home/flask")',
        "Path('/home/flask')",
        'str(ROOT / "web"), "/home/flask"',
    )
    for path in guarded_paths:
        if path.resolve() == Path(__file__).resolve():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{path.relative_to(REPO)} imports the live checkout"


def test_database_harness_requires_an_exact_local_test_database():
    source = (REPO / "tests" / "conftest.py").read_text(encoding="utf-8")

    assert 'os.environ.get("TW2_TEST_POSTGRES_DSN"' in source
    assert '_test_url.database != "tradewave_test"' in source
    assert '_query_host = _test_url.query.get("host")' in source
    assert "host not in _allowed_hosts" in source
    assert "TEST_DSN!r" not in source
