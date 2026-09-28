"""TW-TASK-0014 item 4: hypothetical basket scenarios (the app's Portfolio Scenarios math in %)."""
import datetime

from apiserver import scenarios as sc


def _entries(values):
    return [{"year": y, "pct": "%.2f,1.00,-1.00" % v, "price": "1,1"} for y, v in values.items()]


def test_horizon_windows_match_the_app():
    start = datetime.date(2026, 9, 28)
    assert sc.horizon_window(start, "30") == (datetime.date(2026, 10, 27), 30)
    assert sc.horizon_window(start, "eoy") == (datetime.date(2026, 12, 31), 95)
    assert sc.horizon_window(start, "custom", 294) == (datetime.date(2027, 7, 18), 294)


def test_short_flips_the_sign():
    assert sc.annual_returns(_entries({2020: 5.0}), "short") == {2020: -5.0}


def test_basket_result_is_the_weighted_sum_on_shared_years():
    basket = [{"symbol": "A", "direction": "long", "weight_pct": 60.0},
              {"symbol": "B", "direction": "long", "weight_pct": 40.0}]
    annual = {"A": {2019: 10.0, 2020: -5.0, 2021: 20.0}, "B": {2020: 5.0, 2021: -10.0}}
    start = datetime.date(2026, 9, 28)
    result = sc.horizon(basket, annual, start, datetime.date(2027, 7, 18), 294, "custom",
                        benchmark=("SPY", {2020: 1.0, 2021: 10.0}))

    assert result["coverage"]["common_years"] == [2020, 2021]
    assert result["coverage"]["excluded_years"] == [2019]
    assert [o["change_pct"] for o in result["annual_outcomes"]] == [-1.0, 8.0]
    assert result["mean_change_pct"] == 3.5
    assert result["worst_year"] == {"year": 2020, "change_pct": -1.0}
    assert result["positive"] == 1 and result["negative"] == 1
    assert result["benchmark"]["years_basket_beat_benchmark"] == 0
    text = " ".join(sc.summary(result))
    assert "B limits the shared history to 2 years." in text
    assert "not a forecast" in text


def test_output_contains_no_money_or_holding_fields():
    basket = [{"symbol": "A", "direction": "long", "weight_pct": 100.0}]
    result = sc.horizon(basket, {"A": {2020: 1.0}}, datetime.date(2026, 1, 1),
                        datetime.date(2026, 1, 30), 30, "30")
    flat = repr(result)
    for banned in ("amount", "value", "shares", "cost", "gain_loss", "holding"):
        assert banned not in flat
