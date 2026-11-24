"""Read-only affiliate self-service view for the gateway (GET /v1/affiliate/me), which
powers the MCP `my_affiliate_program` tool. An affiliate's own AI assistant can read
their referral links, anonymized funnel counts, payout ledger, tax-form status,
ready-made promo copy and - program v2 - their terms, current offer per plan, activity
status, renewal schedule and any live TradeWave promotion.

Scope: ONLY the authenticated caller's own affiliate row (affiliates.user_id = caller,
or, for a not-yet-linked row, the same exact case-insensitive email match the web portal
uses to auto-link - read-only here, the portal does the actual link). Never returns
customer identities: funnel numbers are counts, ledger rows are totals.
Service/demo/chatbot principals are refused (they are not a person)."""
import calendar
import datetime as dt
import json
import logging
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal, ROUND_HALF_UP

from . import db

log = logging.getLogger(__name__)

GUIDE_PATH = "/account/affiliate/guide"
DASHBOARD_PATH = "/account/affiliate"

_MODEL_TEXT = {
    "recurring": "recurring - you earn on every paid invoice for as long as the customer stays subscribed",
    "first_payment": "first payment - you earn on the customer's first paid invoice only",
    "duration_12mo": "12 months - you earn on paid invoices during the customer's first 12 months",
}

_DISCLOSURE = "I earn a commission if you subscribe through my link."

# --- program v2 (TW-TASK-0038) -------------------------------------------------------------
# The gateway cannot import web/affiliate_service.py, so the few display rules below mirror
# it: affiliate_service.DEFAULT_TERMS, ACTIVITY_GRACE_DAYS, preview_offer / preview_promo /
# preview_renewal and activity_status. The NUMBERS come from the affiliate_terms row; only
# the three one-line formulas are repeated here. Keep them in step with that module.
_DEFAULT_TERMS = {"terms_version": "v2-5y", "pool_pct": Decimal("50"),
                  "max_discount_pct": Decimal("25"), "promo_commission_pct": Decimal("50"),
                  "renewal_pct": Decimal("25"), "renewal_years": 5, "activity_rule_months": 12}
ACTIVITY_GRACE_DAYS = 30
DISCOUNT_CHANGE_COOLDOWN = dt.timedelta(hours=24)
_PLAN_NAMES = {"navigator": "Navigator", "analyst": "Analyst", "strategist": "Strategist"}
_TIER_ORDER = ("navigator", "analyst", "strategist")
_OFFERS_TIMEOUT = 2.5


def caller_user_id(cust):
    """The caller's users.id (UUID string) when the principal is a real person, else None.
    Service tiers (chatbot/mcp service key without a resolved WorkOS user), the public demo
    token and chatbot 'cb:' principals have no affiliate identity."""
    ent = cust.get("entitlements") or {}
    if ent.get("service"):
        return None
    uid = str(cust.get("user_id") or "")
    try:
        return str(uuid.UUID(uid))
    except ValueError:
        return None


def _num(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        v = float(v)
    return round(float(v), 2)


def _pct(v):
    n = _num(v)
    if n is None:
        return None
    return int(n) if n == int(n) else n


def _iso(v):
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _rates(aff):
    annual = {"discount_pct": _pct(aff["discount_pct"]), "commission_pct": _pct(aff["commission_pct"])}
    monthly = {
        "discount_pct": _pct(aff["discount_pct_monthly"]) if aff.get("discount_pct_monthly") is not None
        else annual["discount_pct"],
        "commission_pct": _pct(aff["commission_pct_monthly"]) if aff.get("commission_pct_monthly") is not None
        else annual["commission_pct"],
    }
    return {"annual_plans": annual, "monthly_plans": monthly}


def _ledger(rows):
    """Per-currency totals + the recent statement rows. 'pending' sums only positive
    pending rows (a negative pending row is a clawback carried into a later month)."""
    totals = {}
    recent = []
    for r in rows:
        cur = (r["currency"] or "usd").lower()
        t = totals.setdefault(cur, {"pending": 0.0, "paid": 0.0, "carried_negative": 0.0})
        amt = _num(r["commission_amount"]) or 0.0
        if r["status"] == "paid":
            t["paid"] += amt
        elif r["status"] == "pending":
            if amt >= 0:
                t["pending"] += amt
            else:
                t["carried_negative"] += amt
        ref = r.get("external_ref") or ""
        recent.append({
            "month": r["period_start"].strftime("%Y-%m") if r.get("period_start") else None,
            "currency": cur,
            "commission": amt,
            "status": r["status"],
            "carried_forward_to": ref[len("carried:"):] if ref.startswith("carried:") else None,
            "paid_at": _iso(r.get("paid_at")),
        })
    for t in totals.values():
        for k in t:
            t[k] = round(t[k], 2)
    return totals, recent[:12]


def _promo(code, join_url, home_url, discount_annual, discount_monthly):
    disc = ""
    if discount_annual:
        disc = " (%s%% off annual plans" % discount_annual
        disc += (", %s%% off monthly)" % discount_monthly) if discount_monthly and discount_monthly != discount_annual else ")"
    # At 0% off there is no checkout code to type (no Stripe coupon): link-only copy.
    has_code = bool(discount_annual)
    try_it = ("Try it with my code %s%s: %s" % (code, disc, join_url)) if has_code \
        else ("Try it with my link: %s" % join_url)
    use_link = ("%s (code %s%s)" % (join_url, code, disc)) if has_code else join_url
    in_desc = ("Link and code %s are in the description%s." % (code, disc)) if has_code \
        else "The link is in the description."
    return {
        "rules": [
            "Disclose the commission every time, clearly and near the link.",
            "No performance or income claims: never say subscribers will make money, that "
            "TradeWave predicts the market, or that a pattern will repeat.",
            "Not investment advice: do not call it signals, picks or recommendations.",
            "Only true, checkable facts; never invent statistics or testimonials.",
            "No spam, no bidding on 'TradeWave' in paid search, no posing as TradeWave staff.",
            "No self-referrals or fake signups.",
        ],
        "disclosure": _DISCLOSURE,
        "templates": [
            {"channel": "short post",
             "text": ("I use TradeWave to research seasonal patterns - calendar windows that have "
                      "repeated across many years - before I place a trade. "
                      "%s\n\n%s" % (try_it, _DISCLOSURE))},
            {"channel": "email or newsletter",
             "text": ("Subject: The seasonal research tool I use\n\n"
                      "I have been using TradeWave to check whether a stock, ETF or market has a "
                      "repeatable seasonal tendency before I act. It shows how a pattern did in each "
                      "past year, with the drawdowns, not just the average. It is research, not "
                      "advice, and past patterns do not guarantee future results.\n\n"
                      "If you want to try it, use my link: %s.\n\n%s"
                      % (use_link, _DISCLOSURE))},
            {"channel": "video or podcast mention",
             "text": ("Today's research came from TradeWave, which maps seasonal patterns across "
                      "years of data. %s %s" % (in_desc, _DISCLOSURE))},
        ],
        "links": {"join_page": join_url, "home_with_code": home_url},
    }


def _safe(fn, default, what):
    """The v2 sections are additive: a missing table (gateway deployed before the
    migration) or a slow web tier must never break the whole affiliate view."""
    try:
        return fn()
    except Exception as e:   # noqa: BLE001
        log.warning("affiliate view: %s unavailable: %s", what, e)
        return default


def _dec(v, default="0"):
    if v is None or v == "":
        return Decimal(default)
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _cents(amount):
    return int(Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _usd(cents):
    return None if cents is None else round(int(cents) / 100.0, 2)


def _add_months(d, months):
    idx = d.year * 12 + (d.month - 1) + months
    year, month = divmod(idx, 12)
    day = min(d.day, calendar.monthrange(year, month + 1)[1])
    return d.replace(year=year, month=month + 1, day=day)


def _utc(v):
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.replace(tzinfo=dt.timezone.utc) if v.tzinfo is None else v.astimezone(dt.timezone.utc)
    return dt.datetime(v.year, v.month, v.day, tzinfo=dt.timezone.utc)


def _terms(row):
    t = dict(_DEFAULT_TERMS)
    for k in t:
        if row and row.get(k) is not None:
            t[k] = row[k]
    if row and row.get("terms_version") and row.get("renewal_years") is None:
        t["renewal_years"] = None          # a real row with NULL = lifetime
    return t


def _fetch_offers(base, code):
    """The web tier's own effective-offer table (GET /api/offers?code=): list price and
    the price a new customer pays per plan, campaign vs partner discount already decided
    there. Best-effort; None on any failure."""
    url = "%s/api/offers?code=%s" % (base, urllib.parse.quote(code))
    with urllib.request.urlopen(url, timeout=_OFFERS_TIMEOUT) as r:   # noqa: S310 - our own host
        return json.loads(r.read().decode("utf-8"))


def _program(terms):
    pool, cap = _dec(terms["pool_pct"]), _dec(terms["max_discount_pct"])
    last = terms["renewal_years"]
    months = int(terms["activity_rule_months"] or 0)
    ex_disc = min(Decimal("20"), cap)
    rules = [
        "You have %s%% of the list price to split: give your audience up to %s%% off and keep "
        "the rest. Example: $100 plan at %s%% off - they pay $%s, you earn $%s."
        % (_pct(pool), _pct(cap), _pct(ex_disc), _pct(100 - ex_disc), _pct(pool - ex_disc)),
        "A new discount applies to customers who sign up after you save it. Nothing changes "
        "for customers you already have. You can change it once every 24 hours on the "
        "Settings page of your dashboard.",
        "During a TradeWave sale your customer gets whichever price is lower - the sale or "
        "your discount. If the sale wins, you earn %s%% of what they paid. You always keep "
        "the referral." % _pct(terms["promo_commission_pct"]),
        ("From year 2 you earn %s%% of what the customer pays at each renewal, for as long as "
         "they stay subscribed." % _pct(terms["renewal_pct"])) if last is None else
        ("From year 2 you earn %s%% of what the customer pays at each renewal, through year %d."
         % (_pct(terms["renewal_pct"]), int(last))),
        "Commission is worked out before tax. A refund takes back the same share of the "
        "commission it paid.",
    ]
    if months:
        rules.append("Renewal commissions are paid while you bring in at least 1 new paying "
                     "customer every %d months, with a %d-day grace. Free trials don't count "
                     "until they pay. Renewals during a gap are not paid back."
                     % (months, ACTIVITY_GRACE_DAYS))
    return {
        "terms_version": terms["terms_version"],
        "pool_pct": _pct(pool), "max_discount_pct": _pct(cap),
        "promo_commission_pct": _pct(terms["promo_commission_pct"]),
        "renewal_pct": _pct(terms["renewal_pct"]),
        "rules": rules,
    }


def _renewals(terms):
    last = terms["renewal_years"]
    lifetime = last is None
    return {
        "renewal_pct": _pct(terms["renewal_pct"]),
        "lifetime": lifetime,
        "first_year": 2, "last_year": None if lifetime else int(last),
        "annual_renewals_paid": None if lifetime else max(0, int(last) - 1),
        "monthly_first_month": 13, "monthly_last_month": None if lifetime else int(last) * 12,
        "label": "Lifetime renewals" if lifetime else "Renewals in years 2-%d" % int(last),
        "basis": "what the customer actually pays at renewal, before tax",
    }


def _activity(terms, row, now):
    months = int(terms["activity_rule_months"] or 0)
    last = _utc((row or {}).get("last_new_customer_at"))
    out = {"activity_rule_months": months, "grace_days": ACTIVITY_GRACE_DAYS, "active": True,
           "last_new_customer_at": _iso(last), "active_until": None, "lapsed_since": None,
           "days_left": None}
    if months <= 0:
        out["text"] = "No activity rule applies to your terms."
        return out
    if last is None:
        out["active"] = False
        out["text"] = ("Your first paying customer starts the clock. To earn on renewals you "
                       "need at least 1 new paying customer every %d months, with a %d-day grace."
                       % (months, ACTIVITY_GRACE_DAYS))
        return out
    until = _add_months(last, months) + dt.timedelta(days=ACTIVITY_GRACE_DAYS)
    if now < until:
        out["active_until"] = until.date().isoformat()
        out["days_left"] = (until.date() - now.date()).days
        out["text"] = ("You're active until %s. Refer 1 new paying customer before then to keep "
                       "your renewal commissions. Free trials don't count until they pay."
                       % until.date().isoformat())
    else:
        out["active"] = False
        out["lapsed_since"] = until.date().isoformat()
        out["text"] = ("Renewal commissions are stopped. They start again with your next new "
                       "paying customer. Renewals during the gap are not paid back.")
    return out


def _offer(aff, rates, terms, row, offers_payload, now):
    pool = _dec(terms["pool_pct"])
    cap = _dec(terms["max_discount_pct"])
    disc = {"year": min(_dec(rates["annual_plans"]["discount_pct"]), cap),
            "month": min(_dec(rates["monthly_plans"]["discount_pct"]), cap)}
    changed = _utc((row or {}).get("discount_changed_at"))
    next_change = None
    if changed is not None and now < changed + DISCOUNT_CHANGE_COOLDOWN:
        next_change = (changed + DISCOUNT_CHANGE_COOLDOWN).isoformat()
    out = {
        "discount_pct": {"annual_plans": _pct(disc["year"]), "monthly_plans": _pct(disc["month"])},
        "first_year_commission_pct": {"annual_plans": _pct(max(Decimal("0"), pool - disc["year"])),
                                      "monthly_plans": _pct(max(Decimal("0"), pool - disc["month"]))},
        "discount_range_pct": [0, _pct(cap)],
        "next_discount_change_at": next_change,
        "checkout_code_active": aff["status"] == "active" and disc["year"] > 0,
        "change_it": "Dashboard > Settings > Your offer (0%% to %s%%, once every 24 hours)." % _pct(cap),
        "per_plan": None,
    }
    if disc["year"] <= 0:
        out["checkout_code_note"] = ("At 0% off there is no checkout code to type. Share your "
                                     "link - links still track.")
    offers = (offers_payload or {}).get("offers") or {}
    if not offers:
        out["per_plan_note"] = "Plan prices are not available right now; see the dashboard."
        return out
    partner_live = bool((offers_payload or {}).get("code"))
    plans = []
    order = {t: i for i, t in enumerate(_TIER_ORDER)}
    for key, o in sorted(offers.items(), key=lambda kv: (order.get(kv[1].get("tier"), 99),
                                                         kv[1].get("interval") != "month")):
        iv = o.get("interval")
        lp = int(o.get("list_price_cents") or 0)
        if iv not in ("month", "year") or lp <= 0:
            continue
        sale_wins = o.get("offer") == "campaign"
        if partner_live or sale_wins:
            pays = int(o.get("price_cents") or lp)
        else:           # code not active yet: what the offer WILL be once it is
            pays = _cents(Decimal(lp) * (100 - disc[iv]) / 100)
        if sale_wins:
            earns = _cents(Decimal(pays) * _dec(terms["promo_commission_pct"]) / 100)
        else:
            earns = _cents(Decimal(lp) * max(Decimal("0"), pool - disc[iv]) / 100)
        plans.append({
            "plan": "%s %s" % (_PLAN_NAMES.get(o.get("tier"), o.get("tier")),
                               "annual" if iv == "year" else "monthly"),
            "tier": o.get("tier"), "interval": iv,
            "list_price": _usd(lp),
            "customer_pays": _usd(pays),
            "you_earn_first_year_payment": _usd(earns),
            "you_earn_per_renewal": _usd(_cents(Decimal(lp) * _dec(terms["renewal_pct"]) / 100)),
            "price_from": "promotion" if sale_wins else "your discount",
            "promotion": (o.get("campaign") or {}).get("name") if sale_wins else None,
        })
    out["per_plan"] = plans
    out["per_plan_note"] = ("USD, before tax. Monthly plans: per monthly payment in the first 12 "
                            "months. Renewal amounts assume today's list price.")
    return out


def _promotions(rows, terms):
    out = []
    for c in rows or []:
        coupons = c.get("stripe_coupon_ids") or {}
        plans = []
        for tier in (c.get("tiers") or []):
            for iv in (c.get("billing_intervals") or []):
                key = "%s:%s" % (tier, iv)
                if key not in coupons:
                    continue               # not provisioned for this plan -> not claimable
                item = {"plan": "%s %s" % (_PLAN_NAMES.get(tier, tier),
                                           "annual" if iv == "year" else "monthly"),
                        "tier": tier, "interval": iv}
                if c.get("offer_type") == "price":
                    price = (c.get("intro_prices") or {}).get(key)
                    if price is None:
                        continue
                    item["intro_price"] = _usd(price)
                    item["you_earn_if_sale_wins"] = _usd(
                        _cents(Decimal(int(price)) * _dec(terms["promo_commission_pct"]) / 100))
                else:
                    item["percent_off"] = _pct(c.get("percent_off"))
                item["intro_lasts"] = ("first year" if iv == "year"
                                       else "%d months" % int(c.get("intro_months") or 12))
                plans.append(item)
        if not plans:
            continue
        out.append({"name": c.get("name"), "code": c.get("code"),
                    "starts_at": _iso(c.get("starts_at")), "ends_at": _iso(c.get("ends_at")),
                    "new_customers_only": True, "plans": plans,
                    "rule": ("Your customer gets whichever price is lower - the sale or your "
                             "discount. If the sale wins, you earn %s%% of what they paid. "
                             "Renewal is at the regular price. You always keep the referral."
                             % _pct(terms["promo_commission_pct"]))})
    return out


def build(cust, host, today=None):
    """Return (payload, status). Status 404 = the caller is not an affiliate."""
    uid = caller_user_id(cust)
    if uid is None:
        return ({"error": {"code": "not_affiliate",
                           "message": "Affiliate data needs a signed-in TradeWave account."}}, 403)
    aff = db.get_affiliate_for_user(uid, cust.get("email"))
    base = "https://%s" % host
    if not aff:
        return ({"error": {"code": "not_affiliate",
                           "message": ("This TradeWave account is not an affiliate. Partners can "
                                       "apply via help@tradewave.ai."),
                           "dashboard_url": base + DASHBOARD_PATH}}, 404)
    code = aff["code"]
    join_url = "%s/join/%s" % (base, code)
    home_url = "%s/?code=%s" % (base, code)
    rates = _rates(aff)
    today = today or dt.datetime.now(dt.timezone.utc).date()
    funnel = db.affiliate_funnel(aff["id"], days=30)
    totals, recent = _ledger(db.affiliate_payout_rows(aff["id"]))
    tax_ok = aff.get("tax_form_received_at") is not None
    next_statement = (today.replace(day=2) if today.day < 2
                      else (today.replace(day=1) + dt.timedelta(days=32)).replace(day=2))
    now = dt.datetime.now(dt.timezone.utc)
    if today != now.date():      # tests pin `today`
        now = dt.datetime(today.year, today.month, today.day, 12, tzinfo=dt.timezone.utc)
    v2_row = _safe(lambda: db.affiliate_program_v2(aff["id"]), None, "program v2 terms")
    terms = _terms(v2_row)
    promo_rows = _safe(db.active_promotions, [], "promotions")
    offers_payload = _safe(lambda: _fetch_offers(base, code), None, "plan offers")
    payload = {
        "code": code,
        "name": aff["name"],
        "status": aff["status"],
        "links": {"join_page": join_url, "home_with_code": home_url,
                  "dashboard": base + DASHBOARD_PATH, "partner_guide": base + GUIDE_PATH,
                  "partner_guide_markdown": base + GUIDE_PATH + ".md"},
        # Legacy v1 block (kept for older clients). Program v2 pays by the `program`,
        # `offer`, `renewals` and `activity` sections below, not by commission_pct.
        "terms": {"commission_model": aff["commission_model"],
                  "commission_model_text": _MODEL_TEXT.get(aff["commission_model"], aff["commission_model"]),
                  **rates},
        "program": _program(terms),
        "offer": _offer(aff, rates, terms, v2_row, offers_payload, now),
        "renewals": _renewals(terms),
        "activity": _activity(terms, v2_row, now),
        "active_promotions": _promotions(promo_rows, terms),
        "funnel": funnel,
        "earnings": {
            "totals_by_currency": totals,
            "recent_statements": recent,
            "note": ("Statements are computed monthly; the current month's live estimate is on the "
                     "dashboard. Refunds and lost disputes are netted in the month they happen and "
                     "a negative month carries forward."),
        },
        "payout": {
            "method": aff.get("payout_method"),
            "payout_email_on_file": bool(aff.get("payout_email")),
            "next_statement_date": next_statement.isoformat(),
            "tax_form": {"on_file": tax_ok, "type": aff.get("tax_form_type"),
                         "received_at": _iso(aff.get("tax_form_received_at")),
                         "action": None if tax_ok else
                         "Send a W-9 (US) or W-8BEN / W-8BEN-E (non-US) to help@tradewave.ai - payouts are held until it is on file."},
            "small_balance_note": "Balances under about $50 in a currency may be held and added to a later payout.",
        },
        "promo": _promo(code, join_url, home_url,
                        rates["annual_plans"]["discount_pct"], rates["monthly_plans"]["discount_pct"]),
    }
    if aff["status"] != "active":
        payload["status_note"] = ("Your code is not active yet (sign the affiliate agreement from the "
                                  "email link) - links will not apply the discount until it is.")
    return payload, 200


