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

from . import appserver_client, tiers
from .auth import require_api_key

v1 = Blueprint("v1", __name__)

_UPGRADE_URL = "https://tw2-dev.trxstat.com/account/api"


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

    # OppList4 is keyed to a single entry date (month + day), so 'from' is the entry
    # date (default today). 'to' has no native OppList4 equivalent (see report); it is
    # accepted but not used to widen the query.
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

    return jsonify({"opportunities": opps})


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
    return jsonify(appserver_client.daily_pick())


@v1.get("/daily-pick/track-record")
@require_api_key
def track_record():
    return jsonify(appserver_client.track_record())
