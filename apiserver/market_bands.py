"""Per-market pattern-detection win-rate band: loader + validation.

TradeWave's seasonal detectors only surface patterns inside a per-market win-rate band:
year1 = lookback years, year2 = min winning years, so year2/year1 is the win-rate floor, and
the engine precomputes only the in-band (year1, year2) combos. The floor is MARKET-SPECIFIC
(e.g. S&P 500 ~80-85%, Wilshire ~90%, FOREX Liquid ~70% at a 20-year lookback) and is encoded
by which files exist on disk. apiserver/market_bands.json (built by ops/generate_market_bands.py)
captures it as floor[path][market_id] = {year1: min_year2}.

This module lets the gateway PRE-VALIDATE (year1, year2) and return a clear error + the valid
range, instead of forwarding an out-of-band combo (e.g. 20-9) that the appserver has no file
for and which silently returns an empty list. The band only governs the pattern-DETECTION path
(OppList4 / OppBySymbol); the symbol-analysis path (ChartData4 'years', continuous) is unaffected.
"""
import json
import logging
import os

log = logging.getLogger("apiserver.market_bands")

_PATH = os.path.join(os.path.dirname(__file__), "market_bands.json")
try:
    with open(_PATH) as _fh:
        _BANDS = json.load(_fh)
except Exception as e:  # noqa: BLE001 - never let a missing/bad manifest break the gateway
    log.warning("market_bands.json unavailable (%s); per-market band validation disabled", e)
    _BANDS = {"scan": {}, "symbol": {}}

# The markets that carry the per-SYMBOL pattern grid (opp_by_symbol). The scan path (Monthly_Opp)
# covers all markets; the symbol path is precomputed for only these.
SYMBOL_MARKETS = sorted((m for m, v in (_BANDS.get("symbol") or {}).items() if v), key=int)
_SYMBOL_MARKET_NAMES = "DOW 30, NASDAQ 100, S&P 500, Futures & Commodities, and FOREX Liquid"


def _floor_map(market_id, path):
    return (_BANDS.get(path) or {}).get(str(market_id))


def path_supported(market_id, path):
    """Is (market, path) precomputed at all? The symbol path exists for 5 markets only."""
    return _floor_map(market_id, path) is not None


def min_year2(market_id, year1, path):
    """The win-rate floor (minimum min_winning_years) for this market + lookback, or None if
    the lookback is not precomputed / the band is unknown."""
    fmap = _floor_map(market_id, path)
    if not fmap:
        return None
    return fmap.get(str(int(year1)))


def available_year1(market_id, path):
    fmap = _floor_map(market_id, path)
    return sorted((int(k) for k in fmap), key=int) if fmap else []


def default_year2(year1, market_id=None, path="scan"):
    """Default min_winning_years when the caller omits it: ~90% of year1 (the historical 10/9
    default, generalized), clamped into the market band when known. Always in [1, year1].
    Fixes the old fixed-9 default, which was out of band for any year1 > ~11 and silently
    returned nothing."""
    year1 = int(year1)
    y2 = max(1, min(year1, round(0.9 * year1)))
    if market_id is not None:
        fl = min_year2(market_id, year1, path)
        if fl is not None:
            y2 = min(year1, max(y2, fl))  # never below the market floor
    return y2


def validate(market_id, year1, year2, path, display_name=None):
    """Strict per-market band check for the single-market endpoints. Returns None if OK, else a
    clear, actionable error string. Lenient (None) when the band is unknown for a SCAN-path
    market/lookback (incomplete manifest) so we never hard-block on missing data - the appserver
    stays the backstop. The symbol path DOES hard-block unsupported markets (only 5 have it)."""
    year1, year2 = int(year1), int(year2)
    name = display_name or ("market %s" % market_id)
    if not path_supported(market_id, path):
        if path == "symbol":
            return ("Per-symbol seasonal pattern detection is not available for %s. It covers %s "
                    "(market ids %s). Use find_best_opportunities to scan %s instead."
                    % (name, _SYMBOL_MARKET_NAMES, ", ".join(SYMBOL_MARKETS), name))
        return None  # scan path band unknown -> lenient
    fl = min_year2(market_id, year1, path)
    if fl is None:
        avail = available_year1(market_id, path)
        avail_txt = (": " + ", ".join(str(y) for y in avail)) if avail else ""
        return ("A %d-year lookback is not available for %s. Available lookback years%s."
                % (year1, name, avail_txt))
    if not (fl <= year2 <= year1):
        floor_pct = round(100.0 * fl / year1)
        return ("For a %d-year lookback in %s, min_winning_years must be between %d and %d "
                "(TradeWave only detects patterns that won ~%d%%+ of those years in this market). "
                "You asked for %d; try %d for the ~%d%% floor, or up to %d for 100%%."
                % (year1, name, fl, year1, floor_pct, year2, fl, floor_pct, year1))
    return None


def market_summary(market_id):
    """Compact per-market pattern-detection summary for list_markets, so an agent can answer
    coverage/band questions ('does Wilshire support per-symbol patterns? what win-rate floor?')
    from data instead of a trial-and-error call."""
    scan = _floor_map(market_id, "scan")
    out = {
        "scan_detection": bool(scan),                                # find_best_opportunities/get_seasonal_opportunities
        "by_symbol_detection": path_supported(market_id, "symbol"),  # get_symbol_patterns (5 markets only)
    }
    if scan:
        y1s = sorted(int(k) for k in scan)
        out["lookback_years_range"] = [y1s[0], y1s[-1]]
        ref = 20 if 20 in y1s else y1s[-1]   # an illustrative band so the win-rate floor is visible
        fl = scan.get(str(ref))
        if fl is not None:
            out["example_band"] = ("%d-year lookback: min_winning_years %d-%d (~%d%%+ winners)"
                                   % (ref, fl, ref, round(100.0 * fl / ref)))
    return out


def out_of_band_markets(market_ids, year1, year2, path):
    """For the MULTI-market scan: which of these markets is the (year1, year2) combo out of band
    for (so they contributed nothing)? Returns a list of market ids. The scan stays lenient (it
    spans markets with different bands) but the route surfaces this so it is never silent."""
    year1, year2 = int(year1), int(year2)
    bad = []
    for mid in market_ids:
        if not path_supported(mid, path):
            continue  # scan path is supported for all markets; skip if somehow unknown
        fl = min_year2(mid, year1, path)
        if fl is None:
            bad.append(str(mid))            # this lookback not precomputed for this market
        elif not (fl <= year2 <= year1):
            bad.append(str(mid))            # out of the market's win-rate band
    return bad
