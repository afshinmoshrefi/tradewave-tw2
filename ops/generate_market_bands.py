#!/usr/bin/env python3
"""Generate apiserver/market_bands.json - the per-market pattern-detection win-rate band.

TradeWave's seasonal pattern DETECTORS only surface patterns whose historical win rate is
inside a per-market band (the engine precomputes only certain (year1, year2) combos, where
year1 = lookback years and year2 = min winning years, so year2/year1 is the win-rate floor).
The band is MARKET-SPECIFIC (e.g. S&P 500 ~80%, FOREX Liquid ~67%, Wilshire ~90% at a 20y
lookback) and is encoded purely by which precomputed files exist on disk:

  scan path   (OppList4  -> /v1/scan, /v1/opportunities): /data/<mkt>/opportunities/Monthly_Opp_<month>_<y1>_<y2>[_PE#].*
  symbol path (OppBySymbol -> /v1/opportunities/<symbol>): /data/<mkt>/opp_by_symbol/...<y1>_<y2>.csv.gz

This scans both grids (CONSECUTIVE combos only; _PE variants use a different lookback meaning
and are validated leniently) and emits, per market id, per path, the floor: {year1: min_year2}.
The gateway loads this to pre-validate (year1, year2) and return a clear error + valid range
instead of silently forwarding an out-of-band combo that the appserver has no file for.

Run on a box co-located with /home/flask/data (the dev/app box), then commit the JSON.
Re-run whenever the precomputed opportunity data is rebuilt.
"""
import json
import os
import re
import sys

DATA = "/home/flask/data"
OUT = os.path.join(os.path.dirname(__file__), "..", "apiserver", "market_bands.json")

# market id -> data folder (mirrors config.available_resources_path stems)
ID2FOLDER = {
    "0": "dj30", "1": "nasdaq100", "2": "sp500", "3": "rus1000", "4": "wilshire5000",
    "5": "INDX_COMMON", "6": "INDX_USA", "7": "COMM", "8": "FOREX", "9": "FOREX_LQ",
    "10": "GBOND", "11": "ETF", "12": "LSE", "13": "TO", "16": "CC",
}

_COMBO_FILE = re.compile(r"^(\d{1,2})_(\d{1,2})(_PE\d)?\.csv(\.gz)?$")
_COMBO_DIR = re.compile(r"^(\d{1,2})_(\d{1,2})(_PE\d)?$")
_MONTHLY = re.compile(r"Monthly_Opp_[A-Za-z]+_(\d{1,2})_(\d{1,2})(_PE\d)?(?:\.|$)")


def _floor_map(combos):
    """combos: set of (year1, year2). Returns {year1(str): min_year2} + a contiguity flag."""
    by_y1 = {}
    for y1, y2 in combos:
        by_y1.setdefault(y1, set()).add(y2)
    floor = {}
    contiguous = True
    for y1, y2set in by_y1.items():
        lo, hi = min(y2set), max(y2set)
        # valid year2 should be the contiguous range [lo, year1]; note any gap.
        if y2set != set(range(lo, hi + 1)) or hi > y1:
            contiguous = False
        floor[str(y1)] = lo
    return floor, contiguous


def scan_grid(folder):
    """Monthly_Opp consecutive combos for a market (union across months)."""
    d = os.path.join(DATA, folder, "opportunities")
    combos = set()
    if not os.path.isdir(d):
        return combos
    for f in os.listdir(d):
        m = _MONTHLY.search(f)
        if m and not m.group(3):  # skip _PE variants
            combos.add((int(m.group(1)), int(m.group(2))))
    return combos


def symbol_grid(folder):
    """opp_by_symbol consecutive combos for a market. Two layouts:
       FOREX-style: opp_by_symbol/<y1>_<y2>/<symbol>.csv.gz   (combo is a dir)
       stock-style: opp_by_symbol/<symbol>/<y1>_<y2>.csv.gz   (combo is a file in a symbol dir)
    Sample up to 40 symbol dirs and union the floors (per-symbol history length varies, but the
    win-rate FLOOR per year1 is uniform)."""
    base = os.path.join(DATA, folder, "opp_by_symbol")
    combos = set()
    if not os.path.isdir(base):
        return combos
    entries = os.listdir(base)
    forex_style = any(_COMBO_DIR.match(e) for e in entries)
    if forex_style:
        for e in entries:
            m = _COMBO_DIR.match(e)
            if m and not m.group(3):
                combos.add((int(m.group(1)), int(m.group(2))))
    else:
        for sym in entries[:40]:
            sd = os.path.join(base, sym)
            if not os.path.isdir(sd):
                continue
            for f in os.listdir(sd):
                m = _COMBO_FILE.match(f)
                if m and not m.group(3):
                    combos.add((int(m.group(1)), int(m.group(2))))
    return combos


def main():
    out = {"scan": {}, "symbol": {}, "_meta": {
        "doc": "Per-market pattern-detection win-rate band. floor[path][market_id] = {year1: min_year2}. "
               "Valid combo: min_year2 <= year2 <= year1. scan=Monthly_Opp (all markets); "
               "symbol=opp_by_symbol (5 markets only). CONSECUTIVE grid only; PE mode validated leniently.",
        "id2folder": ID2FOLDER,
    }}
    warnings = []
    for mid, folder in ID2FOLDER.items():
        sg = scan_grid(folder)
        yg = symbol_grid(folder)
        if sg:
            fmap, contig = _floor_map(sg)
            out["scan"][mid] = fmap
            if not contig:
                warnings.append("scan %s (%s): non-contiguous year2 set" % (mid, folder))
        else:
            out["scan"][mid] = None
        if yg:
            fmap, contig = _floor_map(yg)
            out["symbol"][mid] = fmap
            if not contig:
                warnings.append("symbol %s (%s): non-contiguous year2 set" % (mid, folder))
        else:
            out["symbol"][mid] = None
    out["_meta"]["warnings"] = warnings
    with open(os.path.abspath(OUT), "w") as fh:
        json.dump(out, fh, separators=(",", ":"), sort_keys=True)
    sym_markets = [m for m, v in out["symbol"].items() if v]
    scan_markets = [m for m, v in out["scan"].items() if v]
    print("wrote", os.path.abspath(OUT))
    print("scan-path markets:", scan_markets)
    print("symbol-path markets:", sym_markets)
    if warnings:
        print("WARNINGS:", *warnings, sep="\n  ")


if __name__ == "__main__":
    sys.exit(main())
