"""TW-TASK-0014 item 5: one shared chart system (SMN chartkit) drives MCP images."""
import io

import pytest

pytest.importorskip("matplotlib")

from twcharts import chartkit  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n"


def test_shared_module_never_draws_prices():
    assert not hasattr(chartkit, "price_projection")


def test_record_bars_renders_to_a_buffer_with_its_own_claim():
    buf = io.BytesIO()
    sem = chartkit.record_bars([2014, 2018, 2022], [9.2, -4.4, 26.5],
                               {"symbol": "SPY", "direction": "long", "window_start": "2026-09-27",
                                "window_end": "2027-07-18", "days": 295,
                                "lookback_label": "3 midterm election years"},
                               buf, mfe=[9.5, 5.2, 26.7], mae=[-7.9, -19.1, -4.2])
    assert buf.getvalue().startswith(PNG)
    assert sem["title"].startswith("SPY has closed higher in 2 of 3 midterm election years")
    assert "worst drawdown to best gain" in sem["spec"]


def _card(direction="long"):
    trend = [{"date": "2026-09-%02d" % d, "index": 20.0 + d % 4} for d in range(27, 31)]
    trend += [{"date": "2026-%02d-%02d" % (m, d), "index": float(m * 3 + d % 5)}
              for m in range(10, 13) for d in range(1, 29)]
    trend += [{"date": "2027-%02d-%02d" % (m, d), "index": float(40 + m * 4 + d % 3)}
              for m in range(1, 9) for d in range(1, 29)]
    return {"symbol": "SPY", "direction": direction,
            "setup": {"entry_date": "2026-09-27", "exit_date": "2027-07-18", "hold_days": 295},
            "stats": {"years": "pe2-3"},
            "chart": {"per_year_bars": [
                {"year": "2014", "net_pct": 9.22, "mfe_pct": 9.53, "mae_pct": -7.91},
                {"year": "2018", "net_pct": 4.36, "mfe_pct": 5.16, "mae_pct": -19.11},
                {"year": "2022", "net_pct": 26.51, "mfe_pct": 26.7, "mae_pct": -4.2}],
                "trend_chart": trend}}


def test_mcp_card_charts_use_the_shared_system():
    from mcpserver.chart_renderer import render_card_charts

    charts = render_card_charts(_card())
    assert len(charts) == 2
    (bars_alt, bars_png), (trend_alt, trend_png) = charts
    assert bars_png.startswith(PNG) and trend_png.startswith(PNG)
    assert "closed higher in 3 of 3 midterm election years" in bars_alt
    assert "Where Sep 27 – Jul 18 sits in SPY's average year" in trend_alt
    assert "from Sep 27" in trend_alt          # the MCP curve starts at entry, and says so
    assert "average of the 3 midterm election years (2014–2022)" in trend_alt


def test_short_card_is_drawn_in_price_convention():
    from mcpserver.chart_renderer import render_card_charts

    card = _card("short")          # trade-relative bars: +9.22 means the price FELL 9.22%
    bars_alt, _ = render_card_charts(card)[0]
    assert "closed lower in 3 of 3" in bars_alt
