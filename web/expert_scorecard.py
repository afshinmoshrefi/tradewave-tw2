"""Expert scorecard, Layer 1 (house-scored) - AFFILIATE_DASHBOARD_SPEC decision 5.

Every published take may declare a directional call on an UNDERLYING:
{symbol, direction long|short, entry_date, exit_date}. Once the window has
closed, this job scores it from underlying closes - the same win/loss rule as
the engine's per-year pattern record:

    return = close(exit) / close(entry) - 1      (closes snapped FORWARD to the
                                                 next trading day by the
                                                 appserver, like ChartData4)
    win    = return > 0 for long, return < 0 for short

Objective and ungameable: the expert can't pick the dates after the fact (the
call is frozen at submit), and a take retracted AFTER its entry date still
counts (no quietly deleting losers). Expert-reported execution (Layer 2,
execution_note/result) is never part of this record.

Prices come from the appserver (getStockPriceByDate, service-token auth, the
same path web/seasonal_report.py uses). Run daily as a cron on the web box:

  15 2 * * * set -a; . /etc/tradewave/secrets.env; set +a; \\
    /home/flask/venv/bin/python /home/flask/web/expert_scorecard.py \\
    >> /var/log/tradewave/expert_scorecard.log 2>&1

Scoring a take bumps its updated_at (and the expert profile's) so the SMN
expert_sync pull re-renders the Expert Desk block and the expert hub page.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from decimal import Decimal
from pathlib import Path

_WEB_ROOT = Path(__file__).resolve().parent
for candidate in (str(_WEB_ROOT.parent), str(_WEB_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

log = logging.getLogger("tw2.expert_scorecard")

# A call whose prices are still missing this many days after exit is voided
# (delisted / unsupported symbol) instead of retried forever.
VOID_AFTER_DAYS = 10
SCORE_RESULTS = ("win", "loss", "void")   # storage IDs - never rename


def score_call(call: dict, entry_close, exit_close) -> tuple[str, Decimal | None]:
    """Pure rule: (result, return_pct). Prices <= 0 / None -> ('void', None)."""
    try:
        e = Decimal(str(entry_close))
        x = Decimal(str(exit_close))
    except Exception:
        return "void", None
    if e <= 0 or x <= 0:
        return "void", None
    ret = (x / e - 1) * 100
    ret = ret.quantize(Decimal("0.0001"))
    if call.get("direction") == "short":
        return ("win" if ret < 0 else "loss"), ret
    return ("win" if ret > 0 else "loss"), ret


def _counts_in_record(take, today: dt.date) -> bool:
    """Published takes always count; a retracted take counts only if it was
    retracted on/after its entry date (losers can't be deleted mid-window)."""
    call = take.declared_call or {}
    if take.status == "published":
        return True
    if take.status == "retracted" and take.retracted_at and call.get("entry_date"):
        return take.retracted_at.date().isoformat() >= call["entry_date"]
    return False


class AppserverPrices:
    """close-on-or-after-date lookups via the appserver (service token)."""

    def __init__(self):
        import seasonal_report as sr
        self._sr = sr
        self._token = sr.mint_token()
        self._markets: dict = {}

    def close(self, symbol: str, date: str):
        import requests
        sym = symbol.upper()
        if sym not in self._markets:
            self._markets[sym] = self._sr._resolve_market(sym, self._token)
        market = self._markets[sym]
        if market is None:
            return None, None
        url = "%s/getStockPriceByDate/%s/%s/%s" % (
            self._sr._appserver_url(), market, sym, date)
        try:
            r = requests.get(url, params={"token": self._token}, timeout=30)
            if r.status_code != 200:
                return None, None
            j = r.json()
        except Exception:
            log.warning("price lookup failed symbol=%s date=%s", sym, date)
            return None, None
        price = j.get("price") or 0
        return (price if price and float(price) > 0 else None), j.get("date")


def evaluate_due(session, today: dt.date | None = None, prices=None) -> dict:
    """Score every unscored call whose window has closed (exit_date < today).
    Commits. Returns counts {scored, voided, pending}."""
    from models import ExpertTake, AffiliateSmnProfile
    today = today or dt.datetime.now(dt.timezone.utc).date()
    now = dt.datetime.now(dt.timezone.utc)
    q = (session.query(ExpertTake)
         .filter(ExpertTake.declared_call.isnot(None),
                 ExpertTake.score_result.is_(None),
                 ExpertTake.status.in_(("published", "retracted"))))
    counts = {"scored": 0, "voided": 0, "pending": 0}
    for t in q.all():
        call = t.declared_call or {}
        exit_s = call.get("exit_date")
        if not exit_s or exit_s >= today.isoformat():
            continue                      # window still open
        if not _counts_in_record(t, today):
            continue                      # retracted before entry: not a call
        if prices is None:
            prices = AppserverPrices()
        e_px, e_dt = prices.close(call["symbol"], call["entry_date"])
        x_px, x_dt = prices.close(call["symbol"], exit_s)
        if e_px is None or x_px is None:
            age = (today - dt.date.fromisoformat(exit_s)).days
            if age < VOID_AFTER_DAYS:
                counts["pending"] += 1
                continue
            result, ret = "void", None
        else:
            result, ret = score_call(call, e_px, x_px)
        t.score_result = result
        t.score_return_pct = ret
        t.score_entry_date = dt.date.fromisoformat(e_dt) if e_dt and e_px else None
        t.score_exit_date = dt.date.fromisoformat(x_dt) if x_dt and x_px else None
        t.scored_at = now
        prof = session.get(AffiliateSmnProfile, t.affiliate_id)
        if prof is not None:
            prof.updated_at = now      # hub page re-renders with the new record
        counts["voided" if result == "void" else "scored"] += 1
        log.info("scored take %s %s %s -> %s %s", t.id, call.get("direction"),
                 call.get("symbol"), result, ret)
    session.commit()
    return counts


def scorecard_for(session, affiliate_id) -> dict:
    """Verified (Layer 1) record for one expert: wins/losses/void, win rate,
    average directional return (sign-adjusted so a good short is positive)."""
    from models import ExpertTake
    rows = (session.query(ExpertTake)
            .filter(ExpertTake.affiliate_id == affiliate_id,
                    ExpertTake.score_result.isnot(None)).all())
    wins = sum(1 for r in rows if r.score_result == "win")
    losses = sum(1 for r in rows if r.score_result == "loss")
    voids = sum(1 for r in rows if r.score_result == "void")
    edge = []
    for r in rows:
        if r.score_result in ("win", "loss") and r.score_return_pct is not None:
            sign = -1 if (r.declared_call or {}).get("direction") == "short" else 1
            edge.append(Decimal(r.score_return_pct) * sign)
    n = wins + losses
    return {
        "calls": n, "wins": wins, "losses": losses, "void": voids,
        "win_rate": (round(wins * 100.0 / n, 1) if n else None),
        "avg_return_pct": (round(float(sum(edge) / len(edge)), 2) if edge else None),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s expert_scorecard: %(message)s")
    ap = argparse.ArgumentParser(description="Score closed expert calls (Layer 1).")
    ap.add_argument("--today", help="YYYY-MM-DD (default: UTC today)")
    args = ap.parse_args()
    import config
    if not config.POSTGRES_DSN:
        log.error("POSTGRES_DSN not set")
        return 1
    today = dt.date.fromisoformat(args.today) if args.today else None
    from models import Session
    s = Session()
    try:
        c = evaluate_due(s, today)
        log.info("done: %s", c)
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
