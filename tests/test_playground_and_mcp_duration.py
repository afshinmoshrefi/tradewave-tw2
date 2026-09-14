"""Release defect TW-R14-02: the API playground shipped an unrunnable example, and the
MCP tool described duration behaviour the API does not implement."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLAYGROUND_SRC = REPO / "site" / "api_playground" / "generate_playground.py"
PLAYGROUND_OUT = REPO / "site" / "api_playground" / "out" / "index.html"
MCP_SERVER = REPO / "mcpserver" / "server.py"


def test_score_example_body_never_ships_an_empty_date():
    """/score treats "" as a MISSING required field (routes.py), so a blank date made the
    prefilled POST example fail on the first Send."""
    src = PLAYGROUND_SRC.read_text(encoding="utf-8")
    assert 'date:""' not in src
    assert "PG_TODAY" in src, "the example date must be built at page load, not hardcoded"


def test_generated_playground_matches_the_source():
    if not PLAYGROUND_OUT.exists():
        return  # page not generated in this checkout
    html = PLAYGROUND_OUT.read_text(encoding="utf-8")
    assert 'date:""' not in html
    assert "PG_TODAY" in html


def test_analyze_exposes_entry_date_beside_days_out():
    """/analyze REJECTS days_out on its own ("days_out requires entry_date or period for
    an exact-window analysis", 400), so the playground must offer entry_date or the
    duration field can only ever produce an error."""
    src = PLAYGROUND_SRC.read_text(encoding="utf-8")
    analyze = src[src.index('"analyze":'):src.index('"markets":')]
    assert 'name:"entry_date"' in analyze
    assert "REQUIRES entry_date or period" in analyze


def test_mcp_describes_the_real_days_out_rule():
    """Two wrong descriptions have shipped here. "biases setup selection" promised
    behaviour that never existed; "IGNORED" was also wrong - the request is REJECTED.
    Assert the live rule from routes.py."""
    src = MCP_SERVER.read_text(encoding="utf-8")
    assert "biases setup selection" not in src
    assert "On its own it is IGNORED" not in src
    assert "REQUIRES a companion entry_date or period" in src
    assert "days_out requires entry_date or period" in src


def test_the_playground_surfaces_a_rejected_request():
    """A 400 rendered as "No cards returned" hid the API's own message, so a bad request
    was indistinguishable from a genuinely empty scan."""
    src = PLAYGROUND_SRC.read_text(encoding="utf-8")
    assert "Request rejected." in src
