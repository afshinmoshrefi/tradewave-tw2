"""PatternCard builder + projection + charting math (apiserver/cards.py).

Hermetic: synthetic appserver-shaped inputs, no DB/redis/appserver. Covers the A-D
additions (extend_research, setup.timing, alignment, extended stats, per_year_bars,
view projection) plus the invariants: derived-data only (no price), the edge_score blend,
neutral, direction-aware receipts, and the short-direction MFE/MAE sign.
"""
import base64

import pytest

from apiserver import cards

pytestmark = pytest.mark.unit

AS_OF = "2026-06-08"

# 9 winning years + 1 losing + a zero-stub current year (must be excluded).
_LONG_ENTRIES = (
    [{"year": y, "pct": "%.2f,%.2f,-1.00" % (4.0, 6.0)} for y in range(2015, 2024)]
    + [{"year": 2024, "pct": "-3.00,2.00,-5.00"}]            # the one losing year
    + [{"year": 2025, "pct": "0,0,0"}]                         # zero stub -> excluded
)

_STATS = {
    "Percent Profitable": "90%", "Sharpe Ratio": "1.5", "Avg Profit - All": "5%",
    "Median Profit": "3%", "Std Dev": "3.40%", "Annualized Return": "4%",
    "Cumulative Return": "50%", "Sharpe Ratio2": "1.80",
}


def _opp(direction="long", win_rate=0.9):
    return {"symbol": "TEST", "market": "2", "direction": direction,
            "entry_date": "2026-07-01", "days_out": 21, "years": "10",
            "win_rate": win_rate, "avg_profit_pct": 5.0, "sharpe_ratio": 1.5}


def _build(direction="long", win_rate=0.9, **kw):
    entries = list(_LONG_ENTRIES)
    if win_rate != 0.9:
        wins = round(win_rate * 10)
        entries = [
            {"year": 2015 + i, "pct": "2.00,3.00,-1.00" if i < wins else "-2.00,1.00,-3.00"}
            for i in range(10)
        ]
    return cards.build_pattern_card(_opp(direction, win_rate), _STATS, entries,
                                   market_name="S&P 500 STOCKS", as_of=AS_OF, rank=1,
                                   ml_state="market", **kw)


# --- card shape + the new A-D fields --------------------------------------------

def test_card_has_all_expected_blocks():
    c = _build()
    for k in ("rank", "symbol", "market", "direction", "bias", "setup", "edge_score",
              "stats", "alignment", "receipts", "extend_research", "next_step",
              "headline", "verdict", "disclaimer", "tier_notes", "wave_viewer"):
        assert k in c, "missing %s" % k
    assert c["disclaimer"] == cards.DISCLAIMER
    assert c["bias"] == "bullish"


def test_wave_viewer_link_opens_exact_pattern(monkeypatch):
    monkeypatch.setenv("TW2_PUBLIC_HOST", "tradewave.example")
    link = _build()["wave_viewer"]
    assert link["url"].startswith("https://tradewave.example/app/?o=")
    encoded = link["url"].split("?o=", 1)[1].split("&", 1)[0]
    encoded += "=" * (-len(encoded) % 4)
    assert base64.b64decode(encoded).decode() == "2|TEST|2026-07-01|21|10"
    assert link["url"].endswith("&view=evidence")


def test_setup_timing_is_computed():
    c = _build()
    assert c["setup"]["timing"] == {"days_to_entry": 23, "status": "window opens in 23 days"}


def test_extended_stats_present_and_parsed():
    s = _build()["stats"]
    assert s["sharpe_ratio_mfe"] == 1.8
    assert s["std_dev_pct"] == 3.4
    assert s["annualized_return_pct"] == 4.0
    assert s["cumulative_return_pct"] == 50.0


def test_extend_research_block():
    er = _build()["extend_research"]
    assert set(er) == {"tradewave_provides", "blind_to", "suggested_checks", "loop_back", "synthesis_rule"}
    assert "upcoming earnings" in er["blind_to"]
    assert any("earnings" in chk.lower() for chk in er["suggested_checks"])


def test_alignment_seasonal_only_without_ml():
    assert _build()["alignment"]["verdict"] == "seasonal_only"


def test_alignment_divergent_when_ml_disagrees():
    c = cards.build_pattern_card(_opp(), _STATS, list(_LONG_ENTRIES), market_name="S&P 500",
                                ml={"win_prob": 0.40, "ml_score": 30}, ml_available=True,
                                as_of=AS_OF, ml_state="shown")
    assert c["alignment"]["verdict"] == "divergent"          # seasonal strong (0.9), ml weak (0.4)


def test_no_em_dashes_in_composed_text():
    c = _build()
    assert "—" not in c["headline"] and "—" not in c["verdict"]


# --- neutral --------------------------------------------------------------------

def test_no_signal_when_win_rate_below_floor():
    c = _build(win_rate=0.30)
    assert c["bias"] == "neutral"
    assert "order_ticket" not in c["next_step"]               # omitted on neutral


def test_buy_signal_carries_order_ticket_without_price():
    nx = _build()["next_step"]
    assert "order_ticket" in nx
    ot = nx["order_ticket"]
    assert ot["type"] == "MARKET"
    assert "price" not in ot and "limit" not in ot and "limit_price" not in ot


# --- derived-data only invariant -------------------------------------------------------

def test_no_raw_price_anywhere_on_the_card():
    import json
    blob = json.dumps(_build(include_chart=True,
                             seasonal_curve=[{"date": "2026-07-01", "index": 40.0},
                                             {"date": "2026-07-02", "index": 41.0}]))
    # the card never emits a price/ohlcv/last-price field
    for banned in ('"price"', '"open"', '"high"', '"low"', '"close"', '"last_price"', '"limit_price"'):
        assert banned not in blob


# --- edge_score blend -------------------------------------------------------------

def test_edge_score_blend_is_deterministic():
    score, basis = cards.compute_edge_score(0.9, 1.5, 10, ml_win_prob=None, ml_available=False)
    # 0.40*0.9 + 0.30*0.5 + 0.20*0.9 + 0.10*(10/15) = 0.7567 -> 76
    assert score == 76
    assert "win_rate 0.90" in basis and "10y history" in basis


# --- direction-aware per-year bars (charting) ------------------------------------

def test_per_year_bars_long():
    bars = cards.per_year_bars([{"year": 2016, "pct": "11.86,12.71,-1.80"},
                                {"year": 2025, "pct": "0,0,0"}], "long")
    assert len(bars) == 1                                     # zero-stub excluded
    assert bars[0] == {"year": "2016", "net_pct": 11.86, "mfe_pct": 12.71,
                       "mae_pct": -1.8, "result": "win"}


def test_per_year_bars_short_flips_net_and_swaps_excursions():
    bars = cards.per_year_bars([{"year": 2016, "pct": "11.86,12.71,-1.80"}], "short")
    b = bars[0]
    assert b["net_pct"] == -11.86                             # short loses when the stock rose
    assert b["mfe_pct"] == 1.8                                # favorable = -mae_long
    assert b["mae_pct"] == -12.71                             # adverse  = -mfe_long
    assert b["result"] == "loss"


def test_short_aggregate_stats_are_not_double_flipped():
    # the appserver's aggregate stats arrive already trade-relative; cards must NOT re-flip.
    s = _build(direction="short")["stats"]
    assert s["annualized_return_pct"] == 4.0
    assert s["cumulative_return_pct"] == 50.0


def test_excursions_parsing():
    assert cards._excursions("-1.09,5.03,-5.83") == (-1.09, 5.03, -5.83)
    assert cards._excursions("5.0") == (5.0, None, None)
    assert cards._excursions(None) == (None, None, None)


def test_include_chart_attaches_curve_and_bars():
    c = _build(include_chart=True,
               seasonal_curve=[{"date": "2026-07-01", "index": 40.0},
                               {"date": "2026-07-02", "index": 41.0}])
    assert "chart" in c
    assert len(c["chart"]["trend_chart"]) == 2
    assert c["chart"]["trend_chart"][0] == {"date": "2026-07-01", "index": 40.0}
    assert len(c["chart"]["per_year_bars"]) == 10            # 10 completed years, stub excluded
    assert c["chart"]["presentation_order"] == ["year_by_year_evidence", "seasonal_trend"]
    assert [spec["id"] for spec in c["chart"]["recommended_charts"]] == [
        "year_by_year_evidence", "seasonal_trend"]


# --- progressive disclosure / view projection ------------------------------------

def test_project_full_is_identical_passthrough():
    c = _build()
    assert cards.project_card(c, "full") == c


def test_project_evidence_keeps_winner_full_and_trims_runner():
    winner = _build(include_chart=True)
    runner = _build(include_chart=True)
    runner["rank"] = 2
    assert "per_year" in cards.project_card(winner, "evidence")["receipts"]
    projected_runner = cards.project_card(runner, "evidence")
    assert "per_year" not in projected_runner["receipts"]
    assert "chart" in projected_runner  # explicit chart data is never silently discarded


def test_project_decision_trims_but_keeps_decision_essentials():
    c = _build()
    d = cards.project_card(c, "decision")
    assert "per_year" not in d["receipts"]                    # heavy array dropped
    assert set(d["stats"]) == {"historical_win_rate", "sharpe_ratio", "avg_return_pct", "years"}
    assert "edge_basis" not in d                              # detail dropped
    # token trim (2026-06-12 review): extend_research is per-card fixed-cost text; the MCP
    # envelope hand-off carries the same methodology once, so 'decision' drops it.
    assert "extend_research" not in d
    assert "extend_research" in cards.project_card(c, "full")  # full keeps it
    assert d["disclaimer"] == cards.DISCLAIMER                # compliance kept
    assert "alignment" in d                                   # decision-relevant kept
    assert d["setup"]["timing"] is not None


def test_project_table_is_a_compact_row():
    row = cards.project_card(_build(), "table")
    assert set(row) == {"rank", "symbol", "market", "direction", "bias", "entry_date",
                        "hold_days", "edge_score", "historical_win_rate", "ml_win_prob",
                        "sharpe_ratio", "headline", "wave_viewer"}
    assert row["symbol"] == "TEST" and row["market"] == "S&P 500 STOCKS"


def test_project_decision_keeps_explicit_chart():
    c = _build(include_chart=True,
               seasonal_curve=[{"date": "2026-07-01", "index": 40.0}])
    d = cards.project_card(c, "decision")
    assert "chart" in d                                       # explicit include survives the trim


# --- neutral: each of the three trip conditions ---------------------------------

def _build_custom(win_rate, sharpe, n_entries):
    """Build a card with a controllable win_rate, sharpe, and number of completed years."""
    wins = round(win_rate * n_entries)
    entries = [
        {"year": 2000 + i, "pct": "2.00,3.00,-1.00" if i < wins else "-2.00,1.00,-3.00"}
        for i in range(n_entries)
    ]
    opp = {"symbol": "TST", "market": "2", "direction": "long", "entry_date": "2026-07-01",
           "days_out": 21, "years": str(max(n_entries, 1)), "win_rate": win_rate,
           "avg_profit_pct": 2.0, "sharpe_ratio": sharpe}
    return cards.build_pattern_card(opp, dict(_STATS), entries, market_name="S&P 500",
                                   as_of=AS_OF, ml_state="market")


def test_no_signal_via_low_edge_score():
    # win_rate 0.55 (not below the win-rate floor) + years 5 (not below) but a weak blend -> edge < 40.
    c = _build_custom(win_rate=0.55, sharpe=0.0, n_entries=5)
    assert c["edge_score"] < cards.MIN_EDGE_SCORE
    assert c["bias"] == "neutral"


def test_no_signal_via_too_few_years():
    # strong win_rate + sharpe, but only 4 completed years (< MIN_YEARS_TESTED) -> neutral.
    c = _build_custom(win_rate=0.95, sharpe=2.5, n_entries=4)
    assert c["receipts"]["years_tested"] == 4
    assert c["bias"] == "neutral"


def test_strong_inputs_do_signal():
    c = _build_custom(win_rate=0.9, sharpe=1.5, n_entries=10)
    assert c["bias"] == "bullish"


# --- receipts_unavailable: an outage is NEVER evidence of absence ------------------
# (2026-06-12 prod-429 review: under upstream starvation the gateway used to render a
# confident neutral / "under 5 years of history" from receipts that simply failed to load.)

def _build_unavailable(win_rate):
    return cards.build_pattern_card(_opp(win_rate=win_rate), {}, [],
                                   market_name="S&P 500 STOCKS", as_of=AS_OF,
                                   ml_state="market", receipts_unavailable=True)


def test_receipts_unavailable_keeps_opplist_signal_and_says_unavailable():
    c = _build_unavailable(win_rate=0.9)
    assert c["receipts"]["receipts_unavailable"] is True
    assert c["receipts"]["note"]
    assert c["receipts"]["years_tested"] is None              # unknown, not zero
    assert c["bias"] == "bullish"                               # OppList stats stand
    assert "unavailable" in c["verdict"].lower()
    blob = c["headline"] + " " + c["verdict"]
    assert "under 5 years" not in blob                        # never the absence lie
    assert "Won 0/0" not in blob


def test_receipts_unavailable_unknown_win_rate_is_not_weak():
    c = _build_unavailable(win_rate=None)
    assert c["bias"] == "bullish"                               # unknown != weak on an outage
    assert "unavailable" in c["verdict"].lower()


def test_receipts_unavailable_loaded_weak_win_rate_still_no_signal():
    # a win rate that DID load and is weak stays an honest neutral (true reason only).
    c = _build_unavailable(win_rate=0.30)
    assert c["bias"] == "neutral"
    assert "win rate below 55%" in c["verdict"]
    assert "under 5 years" not in c["verdict"]


def test_receipts_unavailable_survives_decision_and_table_projection():
    c = _build_unavailable(win_rate=0.9)
    d = cards.project_card(c, "decision")
    assert d["receipts"]["receipts_unavailable"] is True and d["receipts"]["note"]
    row = cards.project_card(c, "table")
    assert row["receipts_unavailable"] is True


# --- ml_state -> tier_notes mapping ----------------------------------------------

@pytest.mark.parametrize("state", list(cards._ML_NOTES))
def test_ml_state_sets_tier_notes(state):
    opp = {"symbol": "TST", "market": "2", "direction": "long", "entry_date": "2026-07-01",
           "days_out": 21, "years": "10", "win_rate": 0.9, "avg_profit_pct": 5.0, "sharpe_ratio": 1.5}
    c = cards.build_pattern_card(opp, dict(_STATS), list(_LONG_ENTRIES), market_name="S&P 500",
                                as_of=AS_OF, ml_state=state)
    assert c["tier_notes"] == cards._ML_NOTES[state]
