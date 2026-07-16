#!/usr/bin/env python3
"""
TradeWave Home Opportunities CSV Generator (TW2 port from TW1 prod).

Queries the TW2 appserver's /OppList4/ endpoint for current opportunities
in US large-cap markets (S&P 500), filters for the two day_range buckets
displayed on the homepage (7-30 day and 31-60 day patterns), looks up
company names, derives the pattern_param for the wave-viewer link, and
writes /home/flask/site/data/home_opportunities.csv.

This is consumed by site/generate_home_page.py.

TW1 lineage: /home/flask/blog/home_opportunities.py on TW1 prod, scheduled
in /etc/crontab at `4 0 * * *` (daily, 00:04 UTC).

Schema (matches the file site/generate_home_page.py:load_opportunities_from_csv expects):
  start_date, symbol, company_name, days, direction, SR, AvgP, median,
  TWA, TWR, day_range, mode, pattern_param

Usage:
    python home_opportunities.py [--dry-run] [--resource-id N]
"""

import argparse
import base64
import csv
import datetime
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

sys.path.insert(0, '/home/flask')
sys.path.insert(0, str(Path(__file__).resolve().parent / 'lib'))
import config
from log_safety import scrub_secret_text

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

APPSERVER_URL = config.appserver_url.rstrip('/')
OUTPUT_CSV = "/home/flask/site/data/home_opportunities.csv"

# Resource IDs whose opportunities feed the homepage. S&P 500 (id=2) is the
# primary source — the existing CSV evidence (EFX, GWW, DE, NUE, LLY, ...)
# all come from the S&P 500 universe. TW1_SPEC: confirm whether DJ30 (0),
# NASDAQ 100 (1), or Russell 1000 (3) were also queried.
DEFAULT_RESOURCE_IDS = [2]  # S&P 500

# OppList4 lookback / forward window — matches the comment block in
# site/generate_home_page.py:225 (FEATURED_YEARS / FEATURED_MIN_PYEARS).
YEARS_LOOKBACK = 10
PYEARS = 10  # PE cycle pyears parameter

# Two day_range buckets the homepage renders. Anything outside these is
# dropped before the CSV is written.
DAY_RANGES = ["7-30", "31-60"]

# Mode codes — TW1 home_opportunities.py queried both PE-cycle and
# consolidated modes. The existing CSV shows rows tagged with mode='pe'
# and mode='cons', and pattern_param encodes "PE2-10" vs "10".
# (mode_id_for_pattern is what gets base64'd into pattern_param.)
MODES = [
    {"name": "pe",   "url_mode": "pe",   "pattern_mode_id": "PE2-10"},
    {"name": "cons", "url_mode": "cons", "pattern_mode_id": "10"},
]

# Filter: only forward-looking opportunities — patterns starting within
# the next N days. TW1 typically showed the rolling upcoming window.
# TW1_SPEC: confirm exact window. 90 days is safely wide.
FORWARD_WINDOW_DAYS = 90

# Sharpe-ratio floor — drop noise.  TW1_SPEC: confirm. CSV evidence shows
# rows with SR as low as 0.87 (LLY), so the floor is low or absent.
MIN_SHARPE = 0.5

# Direction filter — CSV evidence is 100% Long. TW1_SPEC: confirm.
DIRECTIONS = ["Long"]

# How many opportunities to keep per (day_range, mode) bucket before
# concatenating. Caps the CSV at ~4× this number after dedup.
PER_BUCKET_CAP = 50

# Inter-request delay to be polite to the appserver.
REQUEST_DELAY_S = 0.2

# Request timeout per call.
REQUEST_TIMEOUT = 30


# ---------------------------------------------------------------------------
# APPSERVER LOGIN
# ---------------------------------------------------------------------------

def appserver_login() -> Optional[str]:
    """Login via a credential-safe service header."""
    if not getattr(config, "SERVICE_API_KEY", None):
        print("ERROR: config.SERVICE_API_KEY is not set in secrets.env")
        return None
    try:
        url = APPSERVER_URL + "/login/api"
        resp = requests.post(
            url,
            headers={"X-Service-Key": config.SERVICE_API_KEY},
            timeout=REQUEST_TIMEOUT,
        ).json()
        token = resp.get("token")
        if not token:
            print("ERROR: appserver login failed: %s" % resp.get("message", "no token"))
            return None
        return token
    except Exception as e:
        print("ERROR: appserver login exception: %s" % scrub_secret_text(e, config.SERVICE_API_KEY))
        return None


# ---------------------------------------------------------------------------
# OPPLIST4 FETCH
# ---------------------------------------------------------------------------

def fetch_opp_list(
    resource_id: int,
    month: int,
    day: int,
    years: int,
    pyears: int,
    day_range: str,
    mode: str,
    token: str,
) -> List[List[Any]]:
    """Call /OppList4/ for one (resource, mode, day_range) combination."""
    url = (
        "%s/OppList4/%s/%s/%s/%s/%s/%s/0/0?token=%s&mode=%s"
        % (APPSERVER_URL, resource_id, month, day, years, pyears, day_range, token, mode)
    )
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print("   WARN OppList4 %s/%s mode=%s dr=%s returned %s"
                  % (resource_id, day, mode, day_range, resp.status_code))
            return []
        data = resp.json()
        return data.get("OppList", []) or []
    except Exception as e:
        print("   WARN OppList4 exception: %s" % scrub_secret_text(e))
        return []


# ---------------------------------------------------------------------------
# NAME LOOKUP (cached)
# ---------------------------------------------------------------------------

_name_cache: Dict[str, str] = {}


def lookup_company_name(symbol: str, token: str) -> str:
    if symbol in _name_cache:
        return _name_cache[symbol]
    try:
        url = "%s/NameFromTicker/%s?token=%s" % (APPSERVER_URL, symbol, token)
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            name = resp.json().get("name") or resp.json().get("NameFromTicker") or symbol
        else:
            name = symbol
    except Exception:
        name = symbol
    _name_cache[symbol] = name
    return name


# ---------------------------------------------------------------------------
# PATTERN_PARAM (matches existing CSV)
# ---------------------------------------------------------------------------

def make_pattern_param(resource_id: int, symbol: str, start_date: str,
                        days: int, pattern_mode_id: str) -> str:
    """Base64-encode the wave-viewer pattern parameter.

    Existing CSV evidence: "MnxFRlh8MjAyNi0wMi0yMXwyM3xQRTItMTA=" decodes to
    "2|EFX|2026-02-21|23|PE2-10". And "MnxORU18MjAyNi0wMi0yN3w0NXwxMA==" to
    "2|NEM|2026-02-27|45|10".
    """
    raw = "%d|%s|%s|%d|%s" % (resource_id, symbol, start_date, days, pattern_mode_id)
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


# ---------------------------------------------------------------------------
# OPP NORMALISATION
# ---------------------------------------------------------------------------

# OppList4 row shape from /home/flask/smn/get_top10_data.py:108:
# ['Date','Symbol','DaysOut','Direction','Sharpe Ratio','avg_profit',
#  'median_profit','cumulative_return','stddev']
_OPP_COLS = ["Date", "Symbol", "DaysOut", "Direction", "SR", "AvgP",
             "median", "CumRet", "StdDev"]


def normalize_opp(row: List[Any]) -> Optional[Dict[str, Any]]:
    """Turn a raw OppList4 row into a dict; defensively skip malformed rows."""
    if not isinstance(row, list) or len(row) < 9:
        return None
    try:
        return {
            "Date": str(row[0]),
            "Symbol": str(row[1]),
            "DaysOut": int(row[2]),
            "Direction": str(row[3]),
            "SR": float(row[4]),
            "AvgP": float(row[5]),
            "median": float(row[6]),
            "CumRet": float(row[7]),
            "StdDev": float(row[8]),
        }
    except Exception:
        return None


def day_range_for(days: int) -> Optional[str]:
    if 7 <= days <= 30:
        return "7-30"
    if 31 <= days <= 60:
        return "31-60"
    return None


# ---------------------------------------------------------------------------
# TWA / TWR
# ---------------------------------------------------------------------------
# The TW1 CSV has TWA + TWR columns; appserver.py:512 notes that TWR (also
# called sr2 / TradeWave_Ratio) is off by default. Without TW1 source we
# cannot match TW1's exact formula. Best-effort approximations below — these
# are conservative and never NaN/inf; site/generate_home_page.py reads them
# with float() and renders as-is. TW1_SPEC: replace with the real formulas
# once we have TW1's home_opportunities.py.

def compute_twa(opp: Dict[str, Any]) -> float:
    """TradeWave Adjusted return — placeholder.
    The existing CSV has TWA > median > AvgP roughly, so we approximate
    as the upper-of (mean + half-stddev, median + half-stddev)."""
    return round(max(opp["AvgP"], opp["median"]) + 0.5 * opp["StdDev"], 2)


def compute_twr(opp: Dict[str, Any]) -> float:
    """TradeWave Ratio — placeholder. Sharpe-like but less volatile."""
    sr = opp["SR"]
    if opp["StdDev"] <= 0:
        return round(sr, 2)
    return round(sr * (opp["CumRet"] / max(opp["StdDev"], 1.0)) / max(sr, 1.0), 2)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print summary, do not write CSV")
    parser.add_argument("--resource-id", type=int, action="append",
                        help="Override DEFAULT_RESOURCE_IDS (repeatable)")
    parser.add_argument("--output", default=OUTPUT_CSV,
                        help="Output CSV path (default: %s)" % OUTPUT_CSV)
    args = parser.parse_args()

    resource_ids = args.resource_id or DEFAULT_RESOURCE_IDS

    print("=== home_opportunities.py — TW2 port ===")
    print("Started at %s UTC" % datetime.datetime.utcnow().isoformat())
    print("Appserver: %s" % APPSERVER_URL)
    print("Resource IDs: %s" % resource_ids)

    token = appserver_login()
    if not token:
        return 1

    today = datetime.date.today()
    cutoff_future = today + datetime.timedelta(days=FORWARD_WINDOW_DAYS)

    all_opps: List[Dict[str, Any]] = []

    for resource_id in resource_ids:
        for mode in MODES:
            for day_range in DAY_RANGES:
                time.sleep(REQUEST_DELAY_S)
                rows = fetch_opp_list(
                    resource_id=resource_id,
                    month=today.strftime("%B"),
                    day=today.day,
                    years=YEARS_LOOKBACK,
                    pyears=PYEARS,
                    day_range=day_range,
                    mode=mode["url_mode"],
                    token=token,
                )
                kept = 0
                for raw in rows[:PER_BUCKET_CAP * 4]:  # over-fetch then filter
                    opp = normalize_opp(raw)
                    if opp is None:
                        continue
                    if opp["Direction"] not in DIRECTIONS:
                        continue
                    if opp["SR"] < MIN_SHARPE:
                        continue
                    try:
                        start = datetime.datetime.strptime(opp["Date"], "%Y-%m-%d").date()
                    except Exception:
                        continue
                    if start < today or start > cutoff_future:
                        continue
                    dr = day_range_for(opp["DaysOut"])
                    if dr is None or dr != day_range:
                        continue
                    opp["resource_id"] = resource_id
                    opp["mode_name"] = mode["name"]
                    opp["pattern_mode_id"] = mode["pattern_mode_id"]
                    opp["day_range"] = dr
                    all_opps.append(opp)
                    kept += 1
                    if kept >= PER_BUCKET_CAP:
                        break
                print("   resource=%s mode=%s dr=%s — %d raw -> %d kept"
                      % (resource_id, mode["name"], day_range, len(rows), kept))

    if not all_opps:
        print("ERROR: no opportunities collected — leaving CSV unchanged")
        return 2

    # Dedup by (symbol, start_date); keep highest SR.
    by_key: Dict[tuple, Dict[str, Any]] = {}
    for opp in all_opps:
        k = (opp["Symbol"], opp["Date"])
        if k not in by_key or opp["SR"] > by_key[k]["SR"]:
            by_key[k] = opp

    dedup = sorted(by_key.values(), key=lambda o: (o["Date"], -o["SR"]))
    print("Total kept after dedup: %d" % len(dedup))

    # Look up company names for all unique symbols.
    unique_symbols = sorted({o["Symbol"] for o in dedup})
    print("Looking up %d company names..." % len(unique_symbols))
    for s in unique_symbols:
        lookup_company_name(s, token)
        time.sleep(0.05)

    # Compose CSV rows.
    rows_out: List[Dict[str, Any]] = []
    for o in dedup:
        rows_out.append({
            "start_date":    o["Date"],
            "symbol":        o["Symbol"],
            "company_name":  _name_cache.get(o["Symbol"], o["Symbol"]),
            "days":          o["DaysOut"],
            "direction":     o["Direction"],
            "SR":            round(o["SR"], 2),
            "AvgP":          round(o["AvgP"], 2),
            "median":        round(o["median"], 2),
            "TWA":           compute_twa(o),
            "TWR":           compute_twr(o),
            "day_range":     o["day_range"],
            "mode":          o["mode_name"],
            "pattern_param": make_pattern_param(
                o["resource_id"], o["Symbol"], o["Date"],
                o["DaysOut"], o["pattern_mode_id"]),
        })

    if args.dry_run:
        print("\n=== DRY-RUN — first 5 rows ===")
        for r in rows_out[:5]:
            print(r)
        return 0

    # Write CSV atomically.
    import os, tempfile
    out_dir = os.path.dirname(args.output)
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".home_opp.", dir=out_dir)
    os.close(fd)
    cols = ["start_date", "symbol", "company_name", "days", "direction",
            "SR", "AvgP", "median", "TWA", "TWR", "day_range", "mode",
            "pattern_param"]
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows_out)
    os.replace(tmp, args.output)
    os.chmod(args.output, 0o644)
    print("Wrote %s (%d rows)" % (args.output, len(rows_out)))
    print("Finished at %s UTC" % datetime.datetime.utcnow().isoformat())
    return 0


if __name__ == "__main__":
    sys.exit(main())
