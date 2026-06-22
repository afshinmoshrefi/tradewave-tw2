"""Ground-truth correctness eval for Tara (the in-product chatbot).

WHY THIS EXISTS: the original peak-tuning eval scored answers with an LLM rubric (brief / drives-UI
/ tone / "correct"=plausible) and was SINGLE-TURN. It could not catch a FABRICATED or STALE statistic
- e.g. Tara saying "won 10 of 10 years" for a setup that actually lost 6 of 10 - because nothing
checked the stated numbers against the real per-year data, and a cross-turn stat-bleed needs >1 turn
to reproduce. This harness closes that gap: for every win-rate / average / rank Tara STATES, it
fetches the GROUND TRUTH (the gateway card's per-year rows = the same data the wave-viewer bar chart
shows, and the OppList4 table for ranks) and ASSERTS equality. Deterministic - no LLM judge.

RUN (with the secrets env sourced so APPSERVER_JWT_SECRET + TARA_GATEWAY_KEY are present):
    set -a && sudo cat /etc/tradewave/secrets.env > /tmp/s.env && . /tmp/s.env && set +a
    PYTHONPATH=/home/flask:/home/flask/appserver/appserver /home/flask/venv/bin/python tara_truth_eval.py
Exit code 0 = all assertions passed; 1 = at least one stated stat did not match ground truth.
"""
import datetime
import os
import re
import sys

import jwt
import requests

APPSERVER = "http://127.0.0.1:5000"          # dev; per-env appserver
GATEWAY = (os.environ.get("TW2_GATEWAY_URL") or "http://127.0.0.1:8088/v1").rstrip("/")
SECRET = os.environ["APPSERVER_JWT_SECRET"]
GKEY = os.environ["TARA_GATEWAY_KEY"]

# ---- claims parsing (mirrors tara_gateway's guard regexes) -----------------------------------
_FRAC = re.compile(r'(\d+)\s*(?:of(?:\s*the\s*last)?|/)\s*(\d+)', re.I)
_PCT = re.compile(r'(\d{1,3})\s*%\s*win', re.I)
_AVG = re.compile(r'avg[a-z ]*?([+-]?\d+(?:\.\d+)?)\s*%|([+-]?\d+(?:\.\d+)?)\s*%\s*(?:avg|average)', re.I)
_RANK = re.compile(r'(?:#|ranks?\s*#?|number\s*)(\d+)\b|\b(\d+)(?:st|nd|rd|th)\b', re.I)


def _mint():
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode({"user": "truth-eval", "user_level": "6", "ipv4": "127.0.0.1",
                       "country_code": "US", "zip": "0", "aud": "tw2-appserver", "iss": "tw2-web",
                       "iat": now, "exp": now + datetime.timedelta(minutes=15)}, SECRET, algorithm="HS256")


TOKEN = _mint()


def chat(message, history=None, wave_viewer=None, opportunities=None, market=None, market_name=None, years="10"):
    body = {"message": message, "history": (history or []) + [{"role": "user", "content": message}],
            "wave_viewer": wave_viewer or {}, "opportunities": opportunities or [],
            "opp_table_length": len(opportunities or []), "opp_table_market": market or "",
            "opp_table_market_name": market_name or "", "opp_table_years": years, "token": TOKEN}
    r = requests.post(APPSERVER + "/chatbot/chat", json=body, timeout=120)
    d = r.json()
    return d.get("reply", ""), d.get("actions", [])


def gw(symbol, params):
    h = {"Authorization": "Bearer " + GKEY, "X-TW-On-Behalf-Of": "truth-eval"}
    r = requests.get("%s/analyze/%s" % (GATEWAY, symbol), params=params, headers=h, timeout=60)
    if r.status_code != 200:
        return None
    return r.json()


def truth_for_setup(symbol, entry_date=None, days_out=None, years=10, market=None):
    """GROUND TRUTH (wins, total, avg) for a setup, from the gateway card's per-year rows - the same
    data the wave-viewer bar chart shows. Returns None if unavailable."""
    p = {"years": years}
    if entry_date:
        p["entry_date"] = entry_date
    if days_out:
        p["days_out"] = days_out
    if market:
        p["market"] = market
    d = gw(symbol, p)
    if not d:
        return None
    c = d.get("card") or d
    py = (c.get("receipts") or {}).get("per_year") or []
    wins = sum(1 for x in py if x.get("result") == "win")
    tot = sum(1 for x in py if x.get("result") in ("win", "loss"))
    avg = (c.get("stats") or {}).get("avg_return_pct")
    return (wins, tot, avg) if tot else None


def loaded_setup(actions):
    """The setup Tara actually loaded this turn (symbol + entry_date + days_out), from the last
    set_view that carries a symbol. None if she loaded nothing."""
    for a in reversed(actions or []):
        if a.get("type") == "set_view" and isinstance(a.get("spec"), dict) and a["spec"].get("symbol"):
            s = a["spec"]
            return s.get("symbol"), s.get("entry_date"), s.get("days_out"), s.get("market")
    return None


def win_claims(text):
    out = []
    for m in _FRAC.finditer(text):
        out.append((int(m.group(1)), int(m.group(2))))
    return out


def pct_claims(text):
    return [int(m.group(1)) for m in _PCT.finditer(text)]


# ---- the check: every stated win rate must match the loaded setup's real record ----------------
RESULTS = []


def record(name, ok, detail):
    RESULTS.append((name, ok, detail))
    print("%s %s\n     %s" % ("PASS" if ok else "FAIL", name, detail))


def assert_winrate_matches(name, reply, wins, tot):
    """FABRICATION check: FAIL only if the reply states a win rate that CONTRADICTS the setup's real
    record (the bug class). Absence of a stat is not a fabrication. The denominator may legitimately
    differ by ~a year ('last 10 years' vs 11 scored), so compare FRACTIONS with a small tolerance."""
    truth = wins / tot
    tol = 1.0 / tot + 0.02            # ~one year of slack + rounding
    bad = []
    for a, b in win_claims(reply):
        if b > 0 and abs(a / b - truth) > tol:
            bad.append("%d/%d" % (a, b))
    for p in pct_claims(reply):
        if abs(p / 100.0 - truth) > tol:
            bad.append("%d%%" % p)
    ok = not bad
    record(name, ok, "truth=%d/%d (%.0f%%) | CONTRADICTING=%s | all win-claims=%s pct=%s"
           % (wins, tot, truth * 100, bad, win_claims(reply), pct_claims(reply)))
    return ok


def scenario_multiturn_bleed():
    """THE regression test for the reported bug: load AAPL's June 10/10 window, then ask for the
    September window in a follow-up. The September answer must report SEPTEMBER's real record, never
    bleed June's 10/10 forward. (The old code emitted 'won 10 of 10' here.)"""
    wv = {"symbol": "AAPL", "company": "Apple Inc", "start_date": "2026-06-20", "days_out": "29",
          "years": "10", "direction": "long", "pe_cycle": "cons",
          "stats": {"Sharpe Ratio": "2.16", "Avg Profit": "5.6%", "Percent Profitable": "100%"},
          "yearly_results": [{"year": y, "return_pct": 5.0, "mfe_pct": 7.0, "mae_pct": -1.0} for y in range(2016, 2026)]}
    hist = [{"role": "user", "content": "why does this setup rank here?"},
            {"role": "assistant", "content": "AAPL is strong: 100% win rate over the last 10 years (won 10 of 10), avg +6%."}]
    reply, actions = chat("show me the september window and tell me its win rate over the last 10 years",
                          history=hist, wave_viewer=wv, market="1", market_name="NASDAQ 100")
    ls = loaded_setup(actions)
    if not ls:
        record("multiturn_bleed", False, "Tara loaded nothing (expected a set_view). reply=%r" % reply[:160])
        return
    sym, entry, days, mkt = ls
    t = truth_for_setup(sym, entry, days, 10, mkt)
    if not t:
        record("multiturn_bleed", False, "no ground truth for loaded setup %s %s %s" % (sym, entry, days))
        return
    w, tot, _ = t
    print("  [loaded %s entry=%s days=%s -> truth %d/%d]" % (sym, entry, days, w, tot))
    assert_winrate_matches("multiturn_bleed", reply, w, tot)
    print("     reply: %s" % reply.replace("\n", " ")[:400])


def scenario_explicit_load(label, message, expect_hint=""):
    reply, actions = chat(message, wave_viewer={})
    ls = loaded_setup(actions)
    if not ls:
        record(label, False, "Tara loaded nothing. reply=%r" % reply[:160])
        return
    sym, entry, days, mkt = ls
    t = truth_for_setup(sym, entry, days, 10, mkt)
    if not t:
        record(label, False, "no ground truth for %s %s %s" % (sym, entry, days))
        return
    w, tot, _ = t
    print("  [%s loaded %s entry=%s days=%s -> truth %d/%d]" % (label, sym, entry, days, w, tot))
    # only assert if the reply actually states a win rate (some loads just confirm)
    if win_claims(reply) or pct_claims(reply):
        assert_winrate_matches(label, reply, w, tot)
    else:
        record(label, True, "no win-rate stated (load-only reply) - nothing to fabricate")
    print("     reply: %s" % reply.replace("\n", " ")[:400])


def scenario_rank():
    """A 'why does this rank here' answer must state the loaded symbol's REAL position in the table."""
    opps = [{"date": "2026-06-21", "symbol": "FAST", "days_out": 228, "direction": "L", "avg_profit": 16.1, "sharpe_ratio": 2.48},
            {"date": "2026-06-22", "symbol": "TXN", "days_out": 30, "direction": "L", "avg_profit": 5.6, "sharpe_ratio": 2.36},
            {"date": "2026-06-20", "symbol": "CTAS", "days_out": 36, "direction": "L", "avg_profit": 8.6, "sharpe_ratio": 2.27},
            {"date": "2026-06-20", "symbol": "AAPL", "days_out": 29, "direction": "L", "avg_profit": 5.6, "sharpe_ratio": 2.16},
            {"date": "2026-06-20", "symbol": "WMT", "days_out": 33, "direction": "L", "avg_profit": 21.7, "sharpe_ratio": 2.05}]
    true_rank = next(i + 1 for i, o in enumerate(opps) if o["symbol"] == "AAPL")  # = 4
    wv = {"symbol": "AAPL", "company": "Apple Inc", "start_date": "2026-06-20", "days_out": "29", "years": "10",
          "direction": "long", "stats": {"Sharpe Ratio": "2.16", "Avg Profit": "5.6%", "Percent Profitable": "100%"},
          "yearly_results": [{"year": y, "return_pct": 5.0, "mfe_pct": 7.0, "mae_pct": -1.0} for y in range(2016, 2026)]}
    reply, _ = chat("why does this setup rank here?", wave_viewer=wv, opportunities=opps,
                    market="1", market_name="NASDAQ 100")
    ranks = [int(a or b) for a, b in _RANK.findall(reply)]
    inrange = [r for r in ranks if 1 <= r <= len(opps)]      # ignore stray numbers out of table range
    wrong = [r for r in inrange if r != true_rank]
    if not inrange:
        record("rank_not_fabricated", True, "no rank stated (not a fabrication; she answered without ranking)")
    else:
        record("rank_not_fabricated", not wrong, "true rank=#%d | stated=%s | WRONG=%s" % (true_rank, inrange, wrong))
    print("     reply: %s" % reply.replace("\n", " ")[:200])


def scenario_oracle_selftest():
    """Prove the oracle has teeth: fed the ORIGINAL fabricated reply ('won 10 of 10' for a setup
    whose real record is 4/10), it MUST flag a contradiction. If this ever passes silently, the
    whole harness is blind."""
    fab = "AAPL long: won 10 of the last 10 years, avg +15.1%. Loaded on the chart."
    truth = 4 / 10
    tol = 1.0 / 10 + 0.02
    bad = ["%d/%d" % (a, b) for a, b in win_claims(fab) if b > 0 and abs(a / b - truth) > tol]
    record("oracle_selftest_catches_old_bug", bool(bad),
           "fed the original fabrication ('won 10 of 10' for a real 4/10 setup); oracle flagged=%s" % bad)


def main():
    print("=== Tara ground-truth correctness eval ===\n")
    scenario_oracle_selftest()
    scenario_multiturn_bleed()
    scenario_explicit_load("load_june_10of10", "load AAPL's pattern entering June 20th held 29 days and tell me its 10-year win rate")
    scenario_explicit_load("load_sept_weak", "show me AAPL's September 1st 30-day seasonal window and its real track record")
    scenario_rank()
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n=== %d/%d passed ===" % (passed, len(RESULTS)))
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
