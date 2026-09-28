"""TW-TASK-0014 item 3: same-window symbol comparison (mirrors the app's Symbol Comparison)."""
from apiserver import compare as cmp


def _entries(values):
    return [{"year": year, "pct": "%.2f,%.2f,%.2f" % (net, high, low), "price": "1,1"}
            for year, (net, high, low) in values.items()]


def test_short_direction_flips_return_and_swaps_excursions_like_the_app():
    rows = cmp.yearly_results(_entries({2020: (5.0, 8.0, -2.0)}), direction="short")
    assert rows == [{"year": 2020, "return_pct": -5.0, "mfe_pct": 2.0, "mae_pct": -8.0}]


def test_every_symbol_is_measured_on_the_shared_years_only():
    young = cmp.yearly_results(_entries({y: (30.0, 40.0, -20.0) for y in range(2019, 2025)}))
    old = cmp.yearly_results(_entries({y: (5.0, 7.0, -3.0) for y in range(2010, 2025)}))

    result = cmp.compare({"NVDA": young, "PG": old}, days_out=90, max_years=10)

    assert result["common_years"] == list(range(2019, 2025))
    assert result["years_used"] == 6 and result["can_compare"] is True
    pg = next(r for r in result["rows"] if r["symbol"] == "PG")
    assert pg["years_available"] == 15 and pg["metrics"]["sample_years"] == 6
    text = " ".join(result["findings"])
    assert "NVDA had the highest average return" in text
    assert "NVDA has only 6 years" in text and "PG alone has 15" in text
    assert "NVDA had the deepest drop" in text


def test_metrics_match_the_app_definitions():
    rows = cmp.yearly_results(_entries({2020: (10.0, 12.0, -1.0), 2021: (0.0, 3.0, -4.0),
                                        2022: (-5.0, 1.0, -9.0)}))
    m = cmp.metrics(rows, days_out=365)
    assert m["profitable_pct"] == 66.67          # a flat year counts as profitable (>= 0)
    assert m["winners"] == 2 and m["losers"] == 1
    assert m["cumulative_return_pct"] == 4.5      # 1.10 * 1.00 * 0.95 - 1
    assert m["worst_mae_pct"] == -9.0
    assert m["sharpe_ratio"] == -0.31             # (mean 1.67 - 4% risk-free) / stdev 7.64


def test_too_few_shared_years_is_flagged():
    a = cmp.yearly_results(_entries({2023: (1.0, 2.0, -1.0), 2024: (1.0, 2.0, -1.0)}))
    result = cmp.compare({"A": a, "B": a}, days_out=30)
    assert result["can_compare"] is False
    assert "fewer than the 5 needed" in result["findings"][-1]


def test_buy_hold_benchmark_uses_the_same_shared_years():
    a = cmp.yearly_results(_entries({y: (10.0, 12.0, -1.0) for y in range(2015, 2025)}))
    bh = _entries({y: (2.0, 5.0, -5.0) for y in range(2010, 2025)})
    result = cmp.compare({"A": a, "B": a}, days_out=90, buy_hold={"A": bh})
    row = next(r for r in result["rows"] if r["symbol"] == "A")
    assert row["benchmark"]["years_compared"] == 10
    assert row["metrics"]["beats_buy_hold"] is True
    assert "benchmark" not in next(r for r in result["rows"] if r["symbol"] == "B")


def test_tied_leaders_are_all_named():
    a = cmp.yearly_results(_entries({y: (5.0, 6.0, -1.0) for y in range(2015, 2021)}))
    b = cmp.yearly_results(_entries({y: (3.0, 4.0, -2.0) for y in range(2015, 2021)}))
    result = cmp.compare({"NVDA": a, "PG": b}, days_out=30)
    assert "NVDA and PG were profitable most often, in 6 of 6 years." in result["findings"]
