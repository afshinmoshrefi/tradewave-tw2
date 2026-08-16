"""Guard the /OppList4 response contract against the React wave-viewer.

Regression: `ml_market_eligible` was added to OppTable.js on 2026-08-06 and read as
`opps['ml_market_eligible'] || false`, but the appserver never emitted the key. The
client therefore fell back to `false` for every market and hid the AI Score columns -
and told the user "AI Scores are not available for this market" - even on the US
stock and ETF resources that are in fact ML-eligible.

Reading a key the server never sends fails silently and closed, so assert the two
sides agree instead of waiting for a browser to reveal it.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
APPSERVER_PATH = REPO_ROOT / "appserver" / "appserver" / "appserver.py"
OPP_TABLE_PATH = REPO_ROOT / "web-react" / "src" / "components" / "OppTable.js"

# Keys the client reads defensively but the server deliberately omits on some paths.
# Keep this empty unless a divergence is an intentional, documented decision.
CLIENT_ONLY_KEYS: set = set()


def _opplist4_payload_keys() -> set:
    source = APPSERVER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "OppList4"
    )

    keys = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Return):
            continue
        value = node.value
        if isinstance(value, ast.Tuple) and value.elts:
            value = value.elts[0]
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "jsonify"
            and value.args
            and isinstance(value.args[0], ast.Dict)
        ):
            continue
        keys.update(
            key.value
            for key in value.args[0].keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        )
    return keys


def _opptable_response_keys() -> set:
    source = OPP_TABLE_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"opps\['([A-Za-z0-9_]+)'\]", source))


def test_opplist4_emits_every_key_the_wave_viewer_reads():
    payload_keys = _opplist4_payload_keys()
    assert payload_keys, "no jsonify payload found in OppList4"

    missing = _opptable_response_keys() - payload_keys - CLIENT_ONLY_KEYS
    assert not missing, (
        "OppTable.js reads OppList4 keys the appserver never returns: "
        f"{sorted(missing)}. The client fails closed on a missing key, so add the "
        "field to the OppList4 jsonify payload."
    )


def test_opplist4_reports_market_ml_eligibility_separately_from_tier_access():
    payload_keys = _opplist4_payload_keys()

    # ml_enabled is market AND tier; the viewer needs the market half on its own to
    # tell "this market is not scored" apart from "your plan does not include AI".
    assert "ml_enabled" in payload_keys
    assert "ml_market_eligible" in payload_keys

    source = APPSERVER_PATH.read_text(encoding="utf-8")
    assert "ml_market_eligible = resourceID in config.ml_score_resource_ids" in source
