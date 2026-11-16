"""Read-only affiliate self-service view for the gateway (GET /v1/affiliate/me), which
powers the MCP `my_affiliate_program` tool. An affiliate's own AI assistant can read
their referral links, anonymized funnel counts, payout ledger, tax-form status and
ready-made promo copy.

Scope: ONLY the authenticated caller's own affiliate row (affiliates.user_id = caller,
or, for a not-yet-linked row, the same exact case-insensitive email match the web portal
uses to auto-link - read-only here, the portal does the actual link). Never returns
customer identities: funnel numbers are counts, ledger rows are totals.
Service/demo/chatbot principals are refused (they are not a person)."""
import datetime as dt
import uuid
from decimal import Decimal

from . import db

GUIDE_PATH = "/account/affiliate/guide"
DASHBOARD_PATH = "/account/affiliate"

_MODEL_TEXT = {
    "recurring": "recurring - you earn on every paid invoice for as long as the customer stays subscribed",
    "first_payment": "first payment - you earn on the customer's first paid invoice only",
    "duration_12mo": "12 months - you earn on paid invoices during the customer's first 12 months",
}

_DISCLOSURE = "I earn a commission if you subscribe through my link."


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
                      "repeated across many years - before I place a trade. Try it with my code "
                      "%s%s: %s\n\n%s" % (code, disc, join_url, _DISCLOSURE))},
            {"channel": "email or newsletter",
             "text": ("Subject: The seasonal research tool I use\n\n"
                      "I have been using TradeWave to check whether a stock, ETF or market has a "
                      "repeatable seasonal tendency before I act. It shows how a pattern did in each "
                      "past year, with the drawdowns, not just the average. It is research, not "
                      "advice, and past patterns do not guarantee future results.\n\n"
                      "If you want to try it, use my link: %s (code %s%s).\n\n%s"
                      % (join_url, code, disc, _DISCLOSURE))},
            {"channel": "video or podcast mention",
             "text": ("Today's research came from TradeWave, which maps seasonal patterns across "
                      "years of data. Link and code %s are in the description%s. %s"
                      % (code, disc, _DISCLOSURE))},
        ],
        "links": {"join_page": join_url, "home_with_code": home_url},
    }


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
    payload = {
        "code": code,
        "name": aff["name"],
        "status": aff["status"],
        "links": {"join_page": join_url, "home_with_code": home_url,
                  "dashboard": base + DASHBOARD_PATH, "partner_guide": base + GUIDE_PATH,
                  "partner_guide_markdown": base + GUIDE_PATH + ".md"},
        "terms": {"commission_model": aff["commission_model"],
                  "commission_model_text": _MODEL_TEXT.get(aff["commission_model"], aff["commission_model"]),
                  **rates},
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


