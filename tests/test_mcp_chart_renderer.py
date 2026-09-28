"""Native MCP chart image rendering from PatternCard-derived data."""

import pytest

pytest.importorskip("matplotlib")

from mcpserver.chart_renderer import render_card_charts

pytestmark = pytest.mark.unit


def test_renderer_returns_two_valid_pngs():
    card = {
        "symbol": "TEST",
        "direction": "long",
        "setup": {"entry_date": "2026-07-01", "exit_date": "2026-07-22", "hold_days": 21},
        "chart": {
            "trend_chart": [
                {"date": "2026-07-01", "index": 40.0},
                {"date": "2026-07-02", "index": 41.5},
                {"date": "2026-07-03", "index": 43.0},
            ],
            "per_year_bars": [
                {"year": "2024", "net_pct": 5.0, "mfe_pct": 8.0, "mae_pct": -2.0},
                {"year": "2025", "net_pct": -1.0, "mfe_pct": 3.0, "mae_pct": -4.0},
            ],
        },
    }
    rendered = render_card_charts(card)
    # TW-TASK-0014 item 5: each image is labeled with the chart's own claim (the shared
    # chart system's alt text), in evidence order: year-by-year bars, then the seasonal path.
    labels = [name for name, _ in rendered]
    assert labels[0].startswith("TEST has closed higher in 1 of the past 2 years (Jul 1 – Jul 22)")
    assert labels[1].startswith("Where Jul 1 – Jul 22 sits in TEST's average year")
    assert all(blob.startswith(b"\x89PNG\r\n\x1a\n") for _, blob in rendered)
