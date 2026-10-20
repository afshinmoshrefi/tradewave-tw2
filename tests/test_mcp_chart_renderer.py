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
    assert labels[0].startswith("TEST: yearly price moves (Jul 1 – Jul 22)")
    assert labels[1].startswith("Where Jul 1 – Jul 22 sits in TEST's average year")
    assert all(blob.startswith(b"\x89PNG\r\n\x1a\n") for _, blob in rendered)


@pytest.mark.parametrize("style", ["publication", "wave_viewer"])
@pytest.mark.parametrize("direction", ["long", "short"])
def test_renderer_preserves_completed_rows_and_engine_index(monkeypatch, style, direction):
    import copy
    import matplotlib.pyplot as plt
    from mcpserver import chart_renderer as renderer
    card = {"symbol": "TEST", "direction": direction,
            "setup": {"entry_date": "2026-12-30", "exit_date": "2027-01-02", "hold_days": 4},
            "stats": {"years": "pe2-2"},
            "chart": {"per_year_bars": [
                {"year": "2018", "net_pct": 5.125, "mfe_pct": 8.25, "mae_pct": -2.5},
                {"year": "2022", "net_pct": 0, "mfe_pct": 0, "mae_pct": 0}],
                "trend_chart": [{"date": d, "index": v} for d, v in
                    [("2026-12-30", 40.125), ("2026-12-31", 43.25), ("2027-01-02", 41.5)]]}}
    before = copy.deepcopy(card)
    captured = []
    def save(fig, path):
        ax = fig.axes[0]
        captured.append({"bars": [p.get_height() for p in ax.patches if hasattr(p, "get_height")],
                         "lines": [list(line.get_ydata()) for line in ax.lines],
                         "ticks": [t.get_text() for t in ax.get_xticklabels()]})
        path.write(b"png")
        plt.close(fig)
    monkeypatch.setattr(renderer.chartkit, "_save", save)
    def no_recalculation(*args, **kwargs):
        raise AssertionError("Completed engine evidence must not be recomputed or filtered")
    monkeypatch.setattr(renderer.chartkit, "_median", no_recalculation)
    monkeypatch.setattr(renderer.chartkit, "_drop_zeroed", no_recalculation)
    images = renderer.render_chart_images(card, style)
    assert [i["kind"] for i in images] == ["year_bars", "seasonal_path"]
    assert captured[0]["bars"][:2] == ([5.125, 0] if direction == "long" else [-5.125, 0])
    assert captured[0]["ticks"] == ["2018", "2022"]
    assert [40.125, 43.25, 41.5] in captured[1]["lines"]
    assert card == before


def test_partial_render_preserves_kind_and_style(monkeypatch):
    from mcpserver import chart_renderer as renderer
    def fail(*args):
        raise ValueError("missing year chart")
    monkeypatch.setattr(renderer, "render_year_evidence_chart", fail)
    monkeypatch.setattr(renderer, "render_trend_chart", lambda *args: (b"png", {"alt": "path"}))
    images = renderer.render_chart_images({}, "wave_viewer")
    assert images == [{"kind": "seasonal_path", "style": "wave_viewer", "alt": "path", "png": b"png"}]
