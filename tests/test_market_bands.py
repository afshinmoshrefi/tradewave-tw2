"""Per-market pattern-detection win-rate band (apiserver/market_bands.py).

Hermetic: exercises the band logic against the committed apiserver/market_bands.json
manifest. No DB, redis, or appserver needed. Asserts the rules the product owner stated:
the band is market-specific, min_winning_years defaults to ~90% of years, out-of-band
combos (e.g. 20-9) are rejected with the valid range, and per-symbol detection is limited
to 5 markets.
"""
import pytest

from apiserver import market_bands as mb

pytestmark = pytest.mark.unit


# --- coverage / the 5-market symbol gate ---------------------------------------

def test_symbol_markets_are_exactly_the_five():
    assert mb.SYMBOL_MARKETS == ["0", "1", "2", "7", "9"]


def test_scan_path_supported_everywhere_symbol_only_for_five():
    for mid in ("0", "1", "2", "3", "4", "9", "11", "16"):
        assert mb.path_supported(mid, "scan") is True
    assert mb.path_supported("2", "symbol") is True       # S&P 500 has per-symbol
    assert mb.path_supported("9", "symbol") is True        # FOREX Liquid has per-symbol
    assert mb.path_supported("4", "symbol") is False       # Wilshire does NOT
    assert mb.path_supported("11", "symbol") is False      # ETFs do NOT


# --- the per-market floors (verified from disk) --------------------------------

@pytest.mark.parametrize("mid,year1,expected_floor", [
    ("2", 20, 17),   # S&P 500   -> 85%
    ("4", 20, 18),   # Wilshire  -> 90% (the owner's spec)
    ("9", 20, 14),   # FOREX Liq -> 70%
    ("0", 20, 16),   # DOW 30    -> 80%
    ("2", 10, 8),    # S&P 500 @10y
    ("4", 10, 9),    # Wilshire @10y -> 90%
])
def test_min_year2_floor_matches_grid(mid, year1, expected_floor):
    assert mb.min_year2(mid, year1, "scan") == expected_floor


# --- default min_winning_years scales to ~90% (the fixed-9 bug fix) ------------

@pytest.mark.parametrize("year1,expected", [(10, 9), (20, 18), (23, 21), (17, 15)])
def test_default_year2_is_about_ninety_percent(year1, expected):
    assert mb.default_year2(year1) == expected


def test_default_year2_clamped_into_market_floor():
    # Wilshire @20y floor is 18; ~90% rounds to 18 -> in band.
    assert mb.default_year2(20, market_id="4", path="scan") == 18
    # Never below the floor, never above year1.
    d = mb.default_year2(20, market_id="2", path="scan")
    assert mb.min_year2("2", 20, "scan") <= d <= 20


# --- validate: the heart of the fix --------------------------------------------

def test_validate_in_band_ok():
    assert mb.validate("2", 20, 18, "scan", "S&P 500") is None
    assert mb.validate("2", 10, 9, "scan", "S&P 500") is None      # backward-compatible default
    assert mb.validate("4", 20, 18, "scan", "Wilshire") is None    # 90% ok for Wilshire


def test_validate_rejects_the_classic_out_of_band_combo():
    err = mb.validate("2", 20, 9, "scan", "S&P 500")               # "20-9 is just not possible"
    assert err is not None
    assert "17" in err and "20" in err                            # states the valid range
    assert "9" in err


def test_validate_rejects_below_floor_even_if_close():
    # S&P @20y floor is 17 (85%), so 16 (80%) is out of band.
    assert mb.validate("2", 20, 16, "scan", "S&P 500") is not None
    # Wilshire is stricter (90%): 16 and 17 are both out of band; 18 is the floor.
    assert mb.validate("4", 20, 16, "scan", "Wilshire") is not None
    assert mb.validate("4", 20, 17, "scan", "Wilshire") is not None
    assert mb.validate("4", 20, 18, "scan", "Wilshire") is None


def test_validate_rejects_year2_above_year1():
    assert mb.validate("2", 20, 21, "scan", "S&P 500") is not None


def test_validate_symbol_path_blocks_unsupported_market():
    err = mb.validate("11", 20, 18, "symbol", "ETFs")             # ETFs have no per-symbol grid
    assert err is not None
    assert "find_best_opportunities" in err                       # tells the agent the alternative
    for mid in ("0", "1", "2", "7", "9"):
        assert mid in err                                         # lists the supported ids


def test_validate_lenient_when_band_unknown_on_scan():
    # An unknown/blank market on the scan path degrades to lenient (None), never a hard block.
    assert mb.validate("999", 20, 9, "scan", "Nowhere") is None


# --- out_of_band_markets: the multi-market scan annotation ----------------------

def test_out_of_band_markets_flags_only_the_strict_ones():
    # year1=20, year2=16: in band for DOW(16) + FOREX(14); OUT for S&P(17) + Wilshire(18).
    oob = mb.out_of_band_markets(["0", "2", "4", "9"], 20, 16, "scan")
    assert set(oob) == {"2", "4"}


def test_out_of_band_markets_empty_when_default_used():
    # The ~90% default is in band for every market at year1=20.
    assert mb.out_of_band_markets(["0", "1", "2", "4", "9", "11"], 20, 18, "scan") == []


# --- market_summary (powers list_markets) --------------------------------------

def test_market_summary_shape_and_coverage():
    s = mb.market_summary("4")                                    # Wilshire
    assert s["scan_detection"] is True
    assert s["by_symbol_detection"] is False
    assert "18-20" in s["example_band"] and "90%" in s["example_band"]
    assert s["lookback_years_range"][0] == 5

    s2 = mb.market_summary("2")                                   # S&P 500 has both paths
    assert s2["by_symbol_detection"] is True
    assert "17-20" in s2["example_band"]
