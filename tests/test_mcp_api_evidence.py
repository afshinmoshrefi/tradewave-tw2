"""Regression evidence for the September 2026 MCP/API consistency incident."""
import json
import math
import statistics

import pytest

from apiserver import appserver_client as client, cards
from apiserver.seasonal_evidence import completed_entries, coherent_stats, number

pytestmark = pytest.mark.unit

AAPL_SEP = [5.92, -6.24, -0.48, 8.88, -13.69, -7.22, -12.51, -8.29, 4.59, 10.84, -1.59]


def september_rows():
    return [{"year": 2016 + i, "pct": f"{value},15,-16", "price": "private"}
            for i, value in enumerate(AAPL_SEP)]


@pytest.mark.parametrize("direction,sign,wins", [("long", 1, 4), ("short", -1, 6)])
def test_september_card_summary_receipts_and_chart_have_one_direction_and_cohort(direction, sign, wins):
    opp = {"symbol": "AAPL", "market": "2", "entry_date": "2026-09-01", "days_out": 30,
           "years": "10", "direction": direction, "win_rate": .99,
           "avg_profit_pct": 99, "median_profit_pct": 99, "sharpe_ratio": 99}
    # The discovered engine result was automatically SHORT even on a LONG card.
    raw = {"Trade Dir": "short", "Avg Profit - All": "2%", "Median Profit": "3.36%",
           "Sharpe Ratio": ".17", "Risk Free Rate": 4, "last_trade_date": "2026-09-04"}
    card = cards.build_pattern_card(opp, raw, september_rows(), market_name="S&P 500",
                                    as_of="2026-09-07", include_chart=True)
    values = [sign * value for value in AAPL_SEP[:-1]]
    stats = card["stats"]
    assert card["receipts"]["years_tested"] == stats["years_tested"] == 10
    assert card["receipts"]["wins"] == wins
    assert stats["historical_win_rate"] == wins / 10
    assert stats["avg_return_pct"] == round(statistics.mean(values), 2)
    assert stats["median_return_pct"] == round(statistics.median(values), 2)
    assert stats["cumulative_return_pct"] == round((math.prod(1 + x / 100 for x in values) - 1) * 100, 2)
    expected_sharpe = round((statistics.mean(values) - 4 * 29 / 365) / statistics.stdev(values), 2)
    assert stats["sharpe_ratio"] == expected_sharpe
    assert [row["return_pct"] for row in card["receipts"]["per_year"]] == values
    assert [bar["net_pct"] for bar in card["chart"]["per_year_bars"]] == values
    assert "private" not in json.dumps(card)
    assert card["wave_viewer"]["url"].endswith("direction=" + direction)


def test_completed_current_year_remains_in_consecutive_lookback():
    rows = completed_entries(september_rows(), entry_date="2026-06-01", days_out=30,
                             as_of="2026-09-04", lookback=10)
    assert len(rows) == 11
    assert rows[-1]["year"] == 2026


def test_completion_metadata_preserves_flat_year_and_excludes_active_gain():
    rows = completed_entries([
        {"year": 2024, "pct": "0,0,0", "completed": True},
        {"year": 2025, "pct": "2,3,-1", "completed": False},
        {"year": 2026, "pct": "0,0,0", "completed": False},
    ])
    assert [row["year"] for row in rows] == [2024]
    for side in ("long", "short"):
        stats = coherent_stats({"Risk Free Rate": 4}, rows, side, 30)
        assert stats["Num Winners"] == 0
        assert stats["Num Losers"] == 1
        assert stats["Avg Profit - All"] == 0


def test_cross_year_open_trade_uses_data_date_not_server_clock():
    rows = [{"year": year, "pct": "5,6,-2"} for year in (2024, 2025)]
    selected = completed_entries(rows, entry_date="2026-12-01", days_out=90, as_of="2026-01-12")
    assert [row["year"] for row in selected] == [2024]


@pytest.mark.parametrize("value", ["NaN", "inf", "-Infinity", None, "broken"])
def test_invalid_numeric_data_cannot_enter_json_or_rankings(value):
    assert number(value) is None
    assert client._num(value) is None
    assert cards._num(value) is None


def test_gateway_requests_exact_direction_before_publishing_statistics(monkeypatch):
    calls = []
    def get(path, params=None):
        calls.append((path, params))
        return {"ChartData4": september_rows(), "stats": {
            "Trade Dir": "long", "last_trade_date": "2026-09-04", "Risk Free Rate": 4}}
    monkeypatch.setattr(client, "get", get)
    stats, rows = client.chart_stats_and_years("2", "AAPL", "2026-09-01", 30, "10", direction="long")
    assert calls == [("/ChartData4/2/2026-09-01/AAPL/29/10", {"comparison_direction": "long", "exact_window": "1"})]
    assert len(rows) == 10
    assert stats["Percent Profitable"] == 40
    assert stats["Avg Profit - All"] < 0


def test_unknown_or_opposite_engine_sharpe_is_not_relabelled():
    rows = [{"year": 2025, "pct": "-2,3,-4", "completed": True}]
    for raw in ({"Sharpe Ratio": 3}, {"Trade Dir": "short", "Sharpe Ratio": 3}):
        assert coherent_stats(raw, rows, "long")["Sharpe Ratio"] is None


def test_missing_evidence_does_not_reuse_confident_scan_statistics():
    opp = {"symbol": "AAPL", "market": "2", "entry_date": "2026-09-01", "days_out": 30,
           "years": "10", "direction": "long", "win_rate": 1, "avg_profit_pct": 10, "sharpe_ratio": 5}
    card = cards.build_pattern_card(opp, {}, [], market_name="S&P 500", as_of="2026-09-07")
    assert card["stats"]["avg_return_pct"] is None
    assert card["stats"]["historical_win_rate"] is None
    assert card["stats"]["sharpe_ratio"] is None
    assert card["bias"] == "neutral"


def test_engine_window_rewrite_is_an_outage_not_false_evidence(monkeypatch):
    monkeypatch.setattr(client, "get", lambda *a, **k: {
        "ChartData4": september_rows(), "stats": {"Trade Dir": "long"},
        "request": {"market":"2", "symbol":"AAPL", "entry_date":"2026-01-02",
                    "days_out":31, "years":10, "pe_cycle":"cons", "comparison_direction":"long"},
    })
    assert client.chart_stats_and_years("2", "AAPL", "2026-01-01", 31, "10", direction="long") == (None, None)


def test_primitive_percentage_fields_keep_their_string_units():
    published = client._publishable_stats({"Percent Profitable":40, "Avg Profit - All":-1.82,
                                          "Num Winners":4, "Sharpe Ratio":-.24})
    assert published == {"percent_profitable":"40.0%", "avg_profit_all":"-1.82%",
                         "num_winners":"4", "sharpe_ratio":"-0.24"}


def test_opposite_sides_cannot_share_a_cached_win_rate(monkeypatch):
    from types import SimpleNamespace
    cache, calls = {}, []
    monkeypatch.setattr(client, "_win_rate_cache", SimpleNamespace(
        get=cache.get, setex=lambda key, ttl, value: cache.update({key:value})))
    def chart(*args, direction=None):
        calls.append(direction)
        return [], {"Percent Profitable":40 if direction == "long" else 60}
    monkeypatch.setattr(client, "_chart_data", chart)
    opp = {"market":"2", "symbol":"AAPL", "entry_date":"2026-09-01", "days_out":30, "years":"10"}
    assert client._win_rate_for_opp({**opp, "direction":"long"}) == .4
    assert client._win_rate_for_opp({**opp, "direction":"short"}) == .6
    assert client._win_rate_for_opp({**opp, "direction":"long"}) == .4
    assert calls == ["long", "short"]
