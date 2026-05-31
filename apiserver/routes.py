"""v1 blueprint. /markets is implemented as the reference pattern (auth -> entitlement
-> appserver call -> contract-shaped JSON). The gateway agent implements the rest to
match api/openapi.yaml. Every data route uses @require_api_key; ML + market scope come
from g.customer['entitlements'] / tiers.py.

Safety posture (enforced here + in appserver_client): signals only - no raw OHLCV /
last price / price-by-date is ever returned; all returns are percentages. ML fields are
Pro-tier only and ML-eligible-market only (ids 0-4, 11). Fail-fast: real errors surface
as the contract Error JSON via the app error handlers; only genuine data gaps fail soft.
"""
import datetime

from flask import Blueprint, g, jsonify, request

from . import appserver_client, cards, tiers
from .auth import require_api_key

v1 = Blueprint("v1", __name__)

_UPGRADE_URL = "https://tw2-dev.trxstat.com/account/api"

# how many ranked rows we enrich (win_rate + receipts + ml) AFTER ranking/slicing, so the
# scan never fans out ChartData4 50xN. Bounded by the appserver_client per-row cap.
_SCAN_ENRICH_CAP = appserver_client.MAX_WIN_RATE_ENRICH

# trading-day approximations for window resolution. "now" = entry within ~10 trading days.
_WINDOW_TRADING_DAYS = {"now": 10, "next_2_weeks": 14, "next_month": 31}


def _err(code, message, status):
    return jsonify({"error": {"code": code, "message": message}}), status


def _require_scope(market_id):
    """Return an (error_response, status) tuple if the market is out of the caller's
    tier scope, else None. The permanent resource keys '0'..'16' are the scope unit."""
    scope = set(g.customer["entitlements"]["markets"])
    if str(market_id) not in scope:
        return _err(
            "forbidden",
            "market '%s' is not in your plan's scope - upgrade for full market access"
            % market_id,
            403,
        )
    return None


def _today():
    return datetime.date.today().isoformat()


def _ml_eligible(market_id):
    return str(market_id) in tiers.ML_MARKETS


def _ml_enabled_for_caller(market_id):
    """The caller gets real ML only when their tier has ml_access AND the market is
    ML-eligible. (The underlying service account always has appserver ML access.)"""
    return bool(g.customer["entitlements"]["ml_access"]) and _ml_eligible(market_id)


def _in_scope_markets():
    """The caller's in-scope market ids (intersection of tier scope and the real catalog)."""
    return list(g.customer["entitlements"]["markets"])


def _parse_markets_param(raw, name_map):
    """Resolve the `markets` csv (ids like '2,11' OR names like 'gold,energy') to a list of
    in-scope ids. Unknown/out-of-scope tokens are dropped. Default = ALL in-scope."""
    scope = set(_in_scope_markets())
    if not raw:
        return [m for m in _in_scope_markets()]
    name_to_id = {str(v).strip().lower(): str(k) for k, v in name_map.items()}
    out = []
    for tok in raw.split(","):
        t = tok.strip()
        if not t:
            continue
        if t in scope:
            out.append(t)
        elif t.lower() in name_to_id and name_to_id[t.lower()] in scope:
            out.append(name_to_id[t.lower()])
    # dedupe, preserve order
    seen = set()
    return [m for m in out if not (m in seen or seen.add(m))]


def _resolve_window(window):
    """Resolve the window param to (entry_lo_date, entry_hi_date, label).

    Supported: 'now' (~10 trading days), 'next_2_weeks', 'next_month', or 'YYYY-MM-DD..YYYY-MM-DD'.
    Returns dates as datetime.date. OppList4 is keyed to a SINGLE entry date, so the scan
    fetches at the window's start date and then keeps only setups whose entry_date falls in
    the window - giving a true window over a single-date primitive."""
    today = datetime.date.today()
    w = (window or "now").strip().lower()
    if ".." in w:
        lo_s, _, hi_s = w.partition("..")
        try:
            lo = datetime.datetime.strptime(lo_s.strip(), "%Y-%m-%d").date()
            hi = datetime.datetime.strptime(hi_s.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None
        if hi < lo:
            lo, hi = hi, lo
        return lo, hi, window
    days = _WINDOW_TRADING_DAYS.get(w)
    if days is None:
        return None
    # ~7 calendar days per 5 trading days
    cal = int(round(days * 7 / 5)) if w == "now" else days
    return today, today + datetime.timedelta(days=cal), w


@v1.get("/markets")
@require_api_key
def markets():
    scope = set(g.customer["entitlements"]["markets"])
    out = []
    for m in appserver_client.list_markets():
        out.append({
            "id": m["id"],
            "name": m["name"],
            "ml_eligible": m["id"] in tiers.ML_MARKETS,
            "in_scope": m["id"] in scope,
        })
    return jsonify({"markets": out})


@v1.get("/markets/<market_id>/symbols")
@require_api_key
def symbols(market_id):
    scope_err = _require_scope(market_id)
    if scope_err:
        return scope_err
    return jsonify({"symbols": appserver_client.list_symbols(market_id)})


@v1.get("/opportunities")
@require_api_key
def opportunities():
    market = request.args.get("market")
    if not market:
        return _err("invalid_request", "query param 'market' is required", 400)
    scope_err = _require_scope(market)
    if scope_err:
        return scope_err

    # OppList4 is keyed to a SINGLE entry date (month + day), so 'from' is the entry
    # date (default today). This endpoint is single-date by design; for a true date
    # WINDOW (now / next_2_weeks / next_month / from..to) use /v1/scan, which owns
    # windowed scanning. 'to' is accepted but NOT used to widen the query here; the
    # response sets window_supported=false so callers are never silently misled.
    entry_date = request.args.get("from") or _today()
    direction = request.args.get("direction")  # long|short, optional

    # min_win_rate filters on the REAL historical win rate (share of profitable years,
    # from ChartData4 'Percent Profitable') - NOT the ML win_prob. The OppList4 feed
    # has no per-row win rate, so we enrich each row's win_rate per symbol via
    # ChartData4. That is one (cached) ChartData4 call per row, so it is capped at
    # appserver_client.MAX_WIN_RATE_ENRICH rows; when min_win_rate is set we enrich up
    # to that cap and drop rows we could not enrich (an unknown rate must NOT pass a
    # minimum filter). Without min_win_rate we still enrich up to the cap so win_rate is
    # populated, but we never drop rows.
    min_win_rate = request.args.get("min_win_rate", type=float)
    enrich_n = appserver_client.MAX_WIN_RATE_ENRICH

    opps = appserver_client.opportunities(
        market, entry_date, direction=direction, enrich_win_rate=enrich_n)

    # P0: surface how many rows were actually win-rate-evaluated and whether the
    # enrichment cap was hit, so a min_win_rate filter is never silently misleading
    # (rows past the cap have win_rate=None and are dropped by the filter).
    total_rows = len(opps)
    evaluated_count = min(total_rows, enrich_n)
    enrichment_capped = total_rows > enrich_n

    if min_win_rate is not None:
        opps = [o for o in opps if o.get("win_rate") is not None and o["win_rate"] >= min_win_rate]

    # limit: tier-capped to the plan's opp_limit (free 3, dev 100, pro 1000, business
    # 5000). A caller-supplied limit can only narrow, never exceed, the tier cap.
    tier_cap = g.customer["entitlements"]["opp_limit"]
    req_limit = request.args.get("limit", default=25, type=int)
    if req_limit < 0:
        req_limit = 0
    effective_limit = min(req_limit, tier_cap)
    opps = opps[:effective_limit]

    # Attach ML only for Pro + ML-eligible markets.
    if opps and _ml_enabled_for_caller(market):
        items = [
            {"symbol": o["symbol"], "date": o["entry_date"],
             "days_out": o["days_out"], "direction": o["direction"]}
            for o in opps
        ]
        ml = appserver_client.ml_scores(market, items)
        for o, score in zip(opps, ml):
            o["ml"] = score

    return jsonify({
        "opportunities": opps,
        "entry_date": entry_date,
        "window_supported": False,  # single-date endpoint; use /v1/scan for windows
        "evaluated_count": evaluated_count,
        "enrichment_capped": enrichment_capped,
    })


@v1.get("/opportunities/<symbol>")
@require_api_key
def opportunities_by_symbol(symbol):
    market = request.args.get("market")
    if not market:
        return _err("invalid_request", "query param 'market' is required", 400)
    scope_err = _require_scope(market)
    if scope_err:
        return scope_err

    opps = appserver_client.opportunities_by_symbol(market, symbol)

    # tier cap applies here too (one symbol can still yield many start-date setups).
    tier_cap = g.customer["entitlements"]["opp_limit"]
    opps = opps[:tier_cap]

    if opps and _ml_enabled_for_caller(market):
        items = [
            {"symbol": o["symbol"], "date": o["entry_date"],
             "days_out": o["days_out"], "direction": o["direction"]}
            for o in opps
        ]
        ml = appserver_client.ml_scores(market, items)
        for o, score in zip(opps, ml):
            o["ml"] = score

    return jsonify({"opportunities": opps})


# --------------------------------------------------------------------------- #
# FLAGSHIP endpoints: build SignalCards via cards.py (one source of truth)     #
# --------------------------------------------------------------------------- #

def _enrich_and_card(opp, *, ml_available, seasonal_curve=None, as_of=None, rank=None,
                     tier_note_free=False, name_map=None):
    """Source receipts (ChartData4 stats + per-year entries) for ONE opp and build its
    card. A per-symbol data gap degrades that row to a card with whatever stats exist
    (logged inside appserver_client) - it never aborts the request."""
    stats, chart_entries = appserver_client.chart_stats_and_years(
        opp["market"], opp["symbol"], opp["entry_date"], opp.get("days_out"), opp.get("years"))
    # win_rate from the same stats (so historical_win_rate is consistent everywhere)
    if opp.get("win_rate") is None:
        opp["win_rate"] = appserver_client._win_rate_from_stats(stats)
    name_map = name_map or appserver_client.market_name_map()
    market_name = name_map.get(str(opp["market"]), str(opp["market"]))
    ml = opp.get("ml")
    return cards.build_signal_card(
        opp, stats, chart_entries, market_name=market_name, ml=ml,
        ml_available=ml_available, seasonal_curve=seasonal_curve, as_of=as_of,
        rank=rank, tier_note_free=tier_note_free)


_RANK_KEYS = {
    "edge": lambda o: o.get("_edge_score") or 0,
    "win_rate": lambda o: o.get("win_rate") or 0,
    "sharpe": lambda o: o.get("sharpe_ratio") or 0,
    "ml": lambda o: ((o.get("ml") or {}).get("win_prob")) or 0,
    "avg_return": lambda o: o.get("avg_profit_pct") or 0,
}


@v1.get("/scan")
@require_api_key
def scan():
    """find_best_opportunities: cross-market ranked seasonal scan -> SignalCard[].

    Fans out OppList4 over the caller's in-scope markets IN PARALLEL, resolves the window
    to entry dates, ranks (default by edge_score), tier-caps, then enriches ONLY the
    surviving rows (win_rate + receipts + Pro ML) so we never fan out ChartData4 NxM."""
    name_map = appserver_client.market_name_map()
    markets_param = request.args.get("markets")
    market_ids = _parse_markets_param(markets_param, name_map)
    if not market_ids:
        return _err("invalid_request",
                    "no in-scope markets resolved from 'markets' - check ids/names and your plan scope",
                    400)

    win = _resolve_window(request.args.get("window"))
    if win is None:
        return _err("invalid_request",
                    "invalid 'window' - use now | next_2_weeks | next_month | YYYY-MM-DD..YYYY-MM-DD",
                    400)
    entry_lo, entry_hi, window_label = win

    direction = request.args.get("direction")
    min_win_rate = request.args.get("min_win_rate", type=float)
    min_years = request.args.get("min_years", type=int)
    rank_by = (request.args.get("rank_by") or "edge").strip().lower()
    if rank_by not in _RANK_KEYS:
        rank_by = "edge"

    tier_cap = g.customer["entitlements"]["opp_limit"]
    req_limit = request.args.get("limit", default=10, type=int)
    if req_limit < 0:
        req_limit = 0
    effective_limit = min(req_limit, tier_cap)

    # 1) parallel fan-out at the window's start date (NO enrichment yet).
    raw = appserver_client.opportunities_multi(
        market_ids, entry_lo.isoformat(), direction=direction)

    # 2) keep only setups whose entry_date falls inside the window (true window over the
    #    single-date OppList4 primitive).
    in_window = []
    for o in raw:
        ed = cards._parse_date(o.get("entry_date"))
        if ed is None:
            continue
        if entry_lo <= ed <= entry_hi:
            in_window.append(o)
    evaluated_count = len(in_window)

    # 3) preliminary edge_score for ranking using the cheap OppList4 fields (sharpe +
    #    years; win_rate not yet sourced). This orders rows so we only enrich the top N.
    for o in in_window:
        prelim, _ = cards.compute_edge_score(
            o.get("win_rate"), o.get("sharpe_ratio"),
            int(o.get("years")) if str(o.get("years") or "").isdigit() else 0)
        o["_edge_score"] = prelim
    in_window.sort(key=_RANK_KEYS["edge"], reverse=True)

    # 4) take a generous head for enrichment (cap), then enrich win_rate + ml on those.
    head = in_window[: max(effective_limit, min(_SCAN_ENRICH_CAP, len(in_window)))]
    head = head[:_SCAN_ENRICH_CAP]
    enrichment_capped = len(in_window) > len(head)

    # enrich win_rate (+ receipts happen at card build) on the head rows.
    for o in head:
        if o.get("win_rate") is None:
            o["win_rate"] = appserver_client._win_rate_for_opp(o)

    # 5) trust filters (after win_rate is real).
    filtered = head
    if min_win_rate is not None:
        filtered = [o for o in filtered if o.get("win_rate") is not None and o["win_rate"] >= min_win_rate]
    # min_years filter applied via receipts in the card build below (years_tested); we
    # approximate here with the lookback label, then re-check on the built card.

    # 6) attach ML inline for Pro on eligible markets (grouped per market for batching).
    by_market = {}
    for o in filtered:
        if _ml_enabled_for_caller(o["market"]):
            by_market.setdefault(o["market"], []).append(o)
    for mid, rows in by_market.items():
        items = [{"symbol": r["symbol"], "date": r["entry_date"],
                  "days_out": r["days_out"], "direction": r["direction"]} for r in rows]
        try:
            ml = appserver_client.ml_scores(mid, items)
            for r, score in zip(rows, ml):
                r["ml"] = score
        except Exception:  # noqa: BLE001 - ML is best-effort enrichment, never fatal
            pass

    # 7) build cards, then re-rank by the requested key (edge uses the FULL edge_score now).
    built = []
    for o in filtered:
        ml_available = _ml_enabled_for_caller(o["market"])
        card = _enrich_and_card(
            o, ml_available=ml_available, as_of=_today(),
            tier_note_free=(_ml_eligible(o["market"]) and not ml_available),
            name_map=name_map)
        if min_years is not None and card["receipts"]["years_tested"] < min_years:
            continue
        card["_sortkey"] = _scan_sortkey(card, rank_by)
        built.append(card)

    built.sort(key=lambda c: c["_sortkey"], reverse=True)
    built = built[:effective_limit]
    for i, c in enumerate(built, 1):
        c["rank"] = i
        c.pop("_sortkey", None)

    return jsonify({
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "window": window_label,
        "rank_by": rank_by,
        "count": len(built),
        "evaluated_count": evaluated_count,
        "enrichment_capped": enrichment_capped,
        "opportunities": built,
    })


def _scan_sortkey(card, rank_by):
    if rank_by == "edge":
        return card.get("edge_score") or 0
    if rank_by == "win_rate":
        return card["stats"].get("historical_win_rate") or 0
    if rank_by == "sharpe":
        return card["stats"].get("sharpe_ratio") or 0
    if rank_by == "avg_return":
        return card["stats"].get("avg_return_pct") or 0
    if rank_by == "ml":
        ml = card.get("ml") or {}
        return ml.get("ml_win_prob") or 0
    return card.get("edge_score") or 0


@v1.get("/analyze/<symbol>")
@require_api_key
def analyze_symbol(symbol):
    """analyze_symbol: fuse OppBySymbol + ChartData4 + seasonal curve (+ Pro ML) into ONE
    rich SignalCard (the best setup) + compact other_setups[]."""
    name_map = appserver_client.market_name_map()
    market = request.args.get("market")

    if not market:
        # resolve the market if the symbol is unique across the caller's in-scope markets.
        candidates = appserver_client.resolve_market_for_symbol(symbol, _in_scope_markets())
        if not candidates:
            return _err("not_found",
                        "symbol '%s' not found in any of your in-scope markets - pass ?market=<id>"
                        % symbol, 404)
        if len(candidates) > 1:
            return _err("invalid_request",
                        "symbol '%s' exists in multiple markets %s - specify ?market=<id>"
                        % (symbol, ",".join(sorted(candidates))), 400)
        market = candidates[0]

    scope_err = _require_scope(market)
    if scope_err:
        return scope_err

    direction = request.args.get("direction")
    opps = appserver_client.opportunities_by_symbol(market, symbol)
    if direction:
        want = appserver_client._dir_to_public(direction)
        opps = [o for o in opps if o["direction"] == want]
    if not opps:
        return _err("not_found",
                    "no seasonal setups for '%s' in market '%s'%s"
                    % (symbol, market, (" (%s)" % direction) if direction else ""), 404)

    # pick the best setup by preliminary edge_score (win_rate already enriched by
    # opportunities_by_symbol), build the rich card with receipts + seasonal curve.
    for o in opps:
        prelim, _ = cards.compute_edge_score(
            o.get("win_rate"), o.get("sharpe_ratio"),
            int(o.get("years")) if str(o.get("years") or "").isdigit() else 0)
        o["_edge"] = prelim
    opps.sort(key=lambda o: o["_edge"], reverse=True)
    best = opps[0]

    ml_available = _ml_enabled_for_caller(market)
    if ml_available:
        try:
            ml = appserver_client.ml_scores(market, [{
                "symbol": best["symbol"], "date": best["entry_date"],
                "days_out": best["days_out"], "direction": best["direction"]}])
            best["ml"] = ml[0] if ml else None
        except Exception:  # noqa: BLE001
            best["ml"] = None

    seasonal_curve = None
    try:
        seasonal_curve = appserver_client._seasonal_curve(
            market, symbol, best["entry_date"], best.get("years") or "10")
    except Exception:  # noqa: BLE001 - curve_summary is optional, never fatal
        seasonal_curve = None

    card = _enrich_and_card(
        best, ml_available=ml_available, seasonal_curve=seasonal_curve, as_of=_today(),
        rank=1, tier_note_free=(_ml_eligible(market) and not ml_available),
        name_map=name_map)

    other = [cards.compact_setup(o) for o in opps[1:]]
    tier_cap = g.customer["entitlements"]["opp_limit"]
    other = other[: max(0, tier_cap - 1)]

    return jsonify({"card": card, "other_setups": other, "as_of": _today()})


@v1.get("/patterns/<market_id>/<symbol>")
@require_api_key
def pattern(market_id, symbol):
    scope_err = _require_scope(market_id)
    if scope_err:
        return scope_err
    entry_date = request.args.get("entry_date") or _today()
    days_out = request.args.get("days_out", default="30")
    years = request.args.get("years", default="10")  # stays a string
    return jsonify(appserver_client.pattern_stats(market_id, symbol, entry_date, days_out, years))


@v1.get("/seasonal-chart")
@require_api_key
def seasonal_chart():
    market = request.args.get("market")
    symbol = request.args.get("symbol")
    if not market or not symbol:
        return _err("invalid_request", "query params 'market' and 'symbol' are required", 400)
    scope_err = _require_scope(market)
    if scope_err:
        return scope_err
    entry_date = request.args.get("entry_date") or _today()
    days_out = request.args.get("days_out", default="30")
    years = request.args.get("years", default="10")  # stays a string
    direction = request.args.get("direction")
    return jsonify(appserver_client.seasonal_chart(
        market, symbol, entry_date, days_out, years, direction=direction))


@v1.post("/score")
@require_api_key
def score():
    if not g.customer["entitlements"]["ml_access"]:
        return jsonify({"requires": "pro", "message": "ML scores require the Pro tier",
                        "upgrade_url": _UPGRADE_URL}), 200

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _err("invalid_request", "JSON body with 'opportunities' is required", 400)
    items = body.get("opportunities")
    if not isinstance(items, list) or not items:
        return _err("invalid_request", "'opportunities' must be a non-empty array", 400)

    # ML-eligible markets only (0-4, 11). The score request items are not market-tagged
    # in the contract, so the market is taken from the 'market' query/body param and
    # must be ML-eligible. Default to S&P 500 ('2'), an ML-eligible market.
    market = request.args.get("market") or body.get("market") or "2"
    if not _ml_eligible(market):
        return _err("forbidden",
                    "market '%s' is not ML-eligible (ML markets: %s)"
                    % (market, ", ".join(sorted(tiers.ML_MARKETS))), 403)
    scope_err = _require_scope(market)
    if scope_err:
        return scope_err

    # Validate + normalize each requested opportunity to the contract's ScoreRequest.
    norm = []
    for it in items:
        if not isinstance(it, dict):
            return _err("invalid_request", "each opportunity must be an object", 400)
        missing = [k for k in ("symbol", "date", "days_out", "direction") if it.get(k) in (None, "")]
        if missing:
            return _err("invalid_request",
                        "opportunity missing required fields: %s" % ", ".join(missing), 400)
        norm.append({
            "symbol": it["symbol"],
            "date": it["date"],
            "days_out": int(it["days_out"]),
            "direction": it["direction"],
        })

    ml = appserver_client.ml_scores(market, norm)
    scores = []
    for it, score in zip(norm, ml):
        row = {
            "symbol": it["symbol"],
            "date": it["date"],
            "days_out": it["days_out"],
            "direction": appserver_client._dir_to_public(it["direction"]),
        }
        if score:
            row.update(score)
        else:
            # appserver could not score it (e.g. days_out outside the 10-90 range)
            row.update({"ml_score": None, "win_prob": None,
                        "pred_return": None, "pred_mfe": None})
        scores.append(row)
    return jsonify({"scores": scores})


@v1.get("/daily-pick")
@require_api_key
def daily_pick():
    """The daily AI pick as a full SignalCard + the LIVE forward-tested track record
    (the strongest receipt: made in advance, scored later). The pick's own seasonal
    receipts come from ChartData4; the live record comes from featured_history."""
    raw = appserver_client.daily_pick_raw()
    if not raw:
        return jsonify({"card": None, "track_record": None, "as_of": _today()})

    opp = raw["opp"]
    market = opp.get("market")
    # daily-pick is a published signal everyone can see; if the pick's market is out of
    # the caller's tier scope, ML still gates normally but the card itself is shown.
    ml_available = _ml_enabled_for_caller(market) if market else False

    seasonal_curve = None
    if market and opp.get("entry_date"):
        try:
            seasonal_curve = appserver_client._seasonal_curve(
                market, opp["symbol"], opp["entry_date"], opp.get("years") or "10")
        except Exception:  # noqa: BLE001
            seasonal_curve = None

    card = _enrich_and_card(
        opp, ml_available=ml_available, seasonal_curve=seasonal_curve, as_of=_today(),
        rank=1, tier_note_free=(market and _ml_eligible(market) and not ml_available))

    # fold the LIVE track record into the card receipts - the differentiating proof.
    tr = appserver_client.track_record()
    summary = tr.get("summary", {}) if isinstance(tr, dict) else {}
    live_record = {
        "count": summary.get("count"),
        "win_count": summary.get("win_count"),
        "win_rate": summary.get("win_rate"),
        "avg_return_pct": summary.get("avg_return_pct"),
        "note": "Live forward-tested record of past daily picks (made in advance, scored later).",
    }
    if isinstance(card, dict):
        card.setdefault("receipts", {})["live_track_record"] = live_record

    return jsonify({
        "card": card,
        "featured_date": raw.get("featured_date"),
        "track_record": live_record,
        "as_of": _today(),
    })


@v1.get("/daily-pick/track-record")
@require_api_key
def track_record():
    return jsonify(appserver_client.track_record())
