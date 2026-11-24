"""Read models for the partner dashboard (program v2, TW-TASK-0038).

Everything here is READ-ONLY and scoped to ONE affiliate. No commission math
lives in this module: dollar figures come from affiliate_service
(preview_offer / preview_promo / preview_renewal / renewal_schedule /
activity_status / display_offers) or straight from the ledger
(affiliate_commission_lines). Customers are always anonymized: a stable
"Customer #N" per partner, never a name, an email or a Stripe id.
"""
import csv
import datetime as dt
import io
from decimal import Decimal, ROUND_HALF_UP

import affiliate_service as afs

UTC = dt.timezone.utc
_CENT = Decimal("0.01")

PAYOUT_MINIMUM_CENTS = 5000          # $50 small-balance hold (program rule)
TIER_ORDER = ("navigator", "analyst", "strategist")
TIER_LABELS = {"navigator": "Navigator", "analyst": "Analyst", "strategist": "Strategist"}
INTERVAL_LABELS = {"month": "Monthly", "year": "Annual"}
INTERVAL_WORDS = {"month": "monthly", "year": "annual"}

KIND_LABELS = {"first_year": "First year", "promo": "Promotion", "renewal": "Renewal",
               "refund": "Refund adjustment", "dispute": "Refund adjustment",
               "lapsed": "Lapsed", "payment": "First year"}
STATE_LABELS = {"estimated": "Estimated", "pending": "Pending", "paid": "Paid",
                "held": "Held", "lapsed": "Lapsed", "void": "Void"}
HELP_EMAIL = "help@tradewave.ai"
_HELD_REVIEW = "Held for review - we'll email you. Questions: %s" % HELP_EMAIL
HOLD_REASONS = {"paused": "Held while your account is paused - paid when it's reactivated.",
                "unsigned": "Held until you sign your agreement.",
                "agreement": "Held until you sign your agreement.",
                "review": _HELD_REVIEW, "terminated": _HELD_REVIEW,
                "terminated_for_cause": "Not payable - the account was closed for cause.",
                "tax_form": "Held until we have your tax form."}
# One friendly sentence for every failed discount save. Raw service / Stripe
# text never reaches the partner (it is logged instead).
DISCOUNT_SAVE_FAILED = ("We couldn't update your discount. Nothing changed - "
                        "try again in a few minutes.")
PAYOUT_SEND_RULE = "Usually sent by the 15th of the month after the statement"
TAX_FORM_HELP = ("Don't email your tax form. Reply to your welcome email or contact %s "
                 "and we'll send you a secure upload link." % HELP_EMAIL)
PAYOUT_METHOD_HELP = ("Contact %s to add your PayPal or Wise email. Don't email bank or card "
                      "details - if we need more, we'll send you a secure link." % HELP_EMAIL)
SOURCE_LABELS = {"checkout": "Your link", "promo_code": "Typed code",
                 "signup": "Signup link", "return": "Returning customer"}
STATUS_LABELS = {"trial": "Not paid yet", "paying": "Paying", "ended": "Ended"}
RANGES = (("7d", "7 days", 7), ("30d", "30 days", 30), ("90d", "90 days", 90),
          ("12m", "12 months", 365), ("all", "All time", None))


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------
def fmt_money(amount, currency="usd"):
    """Decimal dollars -> '$1,234.50' (USD) or '1,234.50 EUR'. Negative
    amounts read '-$12.00'."""
    if amount is None:
        return "-"
    d = Decimal(str(amount)).quantize(_CENT, rounding=ROUND_HALF_UP)
    body = "{:,.2f}".format(abs(d))
    sign = "-" if d < 0 else ""
    cur = (currency or "usd").lower()
    return "%s$%s" % (sign, body) if cur == "usd" else "%s%s %s" % (sign, body, cur.upper())


def fmt_cents(cents, currency="usd"):
    if cents is None:
        return "-"
    return fmt_money(Decimal(int(cents)) / 100, currency)


def fmt_price(cents, currency="usd"):
    """A list price: whole dollars drop the cents ('$399', '$49.50')."""
    if cents is None:
        return "-"
    s = fmt_cents(cents, currency)
    return s.replace(".00", "") if s.endswith(".00") or ".00 " in s else s


def fmt_pct(value):
    if value is None:
        return ""
    d = Decimal(str(value)).normalize()
    s = format(d, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def fmt_date(value):
    """'30 Nov 2026' (no leading zero, plain English)."""
    v = _as_date(value)
    return "%d %s" % (v.day, v.strftime("%b %Y")) if v else "-"


def fmt_day(value):
    """'30 Nov' - for deadlines inside the current year."""
    v = _as_date(value)
    return "%d %s" % (v.day, v.strftime("%b")) if v else "-"


def fmt_sale_end(value, tz_name="America/New_York"):
    """A sale deadline with its time and zone: '30 Nov, 11:59 pm ET'. The
    campaign's ends_at is stored in UTC; shoppers read US Eastern time."""
    v = afs._utc(_parse_iso(value))
    if v is None:
        return ""
    try:
        from zoneinfo import ZoneInfo
        local = v.astimezone(ZoneInfo(tz_name))
        zone = "ET"
    except Exception:   # noqa: BLE001 - no tz database: say UTC rather than guess
        local, zone = v, "UTC"
    hour = local.hour % 12 or 12
    return "%d %s, %d:%02d %s %s" % (local.day, local.strftime("%b"), hour, local.minute,
                                     "am" if local.hour < 12 else "pm", zone)


def fmt_sale_day(value):
    """The calendar day of a sale deadline on the same clock as fmt_sale_end
    ('30 Nov'), so the dashboard and the join page never disagree by a day."""
    return fmt_sale_end(value).split(",")[0] or fmt_day(value)


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return afs._utc(value).date()
    if isinstance(value, dt.date):
        return value
    v = afs._utc(_parse_iso(value))
    return v.date() if v else None


def _parse_iso(value):
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value


def plan_label(tier, interval):
    t = TIER_LABELS.get((tier or "").lower())
    i = INTERVAL_WORDS.get(interval or "")
    if t and i:
        return "%s %s" % (t, i)
    return t or (INTERVAL_LABELS.get(interval or "") or "Plan")


def _now(now=None):
    return afs._utc(now) or dt.datetime.now(UTC)


def _catalog_rows(catalog):
    """[(tier, interval, plan)] in display order (Navigator..Strategist,
    monthly before annual)."""
    rows = []
    for (tier, interval), plan in (catalog or {}).items():
        iv = afs._norm_interval(interval)
        lp = int((plan or {}).get("list_price_cents") or 0)
        if iv is None or lp <= 0:
            continue
        rows.append((tier, iv, lp))
    order = {t: i for i, t in enumerate(TIER_ORDER)}
    rows.sort(key=lambda r: (order.get(r[0], 99), 0 if r[1] == "month" else 1))
    return rows


# ---------------------------------------------------------------------------
# offer (pool rule) - tables for Home, Settings and the live chooser
# ---------------------------------------------------------------------------
def offer_summary(aff, terms):
    """The partner's current offer in plain numbers (percentages only)."""
    sched = afs.renewal_schedule(terms)
    pool = afs._dec(terms.pool_pct)
    disc_year = afs.clamp_discount(afs.effective_discount_pct(aff, "year"), terms)
    disc_month = afs.clamp_discount(afs.effective_discount_pct(aff, "month"), terms)
    return {
        "pool_pct": fmt_pct(pool),
        "max_discount_pct": fmt_pct(terms.max_discount_pct),
        "max_discount_int": int(afs._dec(terms.max_discount_pct)),
        "discount_year": fmt_pct(disc_year), "discount_month": fmt_pct(disc_month),
        "split": disc_year != disc_month,
        "rate_year": fmt_pct(max(Decimal("0"), pool - disc_year)),
        "rate_month": fmt_pct(max(Decimal("0"), pool - disc_month)),
        "promo_pct": fmt_pct(terms.promo_commission_pct),
        "renewal_pct": fmt_pct(sched["renewal_pct"]),
        "renewal_label": sched["label"],
        "lifetime": sched["lifetime"],
        "last_year": sched["last_year"],
        "annual_renewals_paid": sched["annual_renewals_paid"],
        "monthly_last_month": sched["monthly_last_month"],
        "activity_rule_months": sched["activity_rule_months"],
        "terms_version": getattr(terms, "version", None),
    }


def plan_table(catalog, aff, terms, promos=None):
    """Per plan + interval at the partner's CURRENT discount: list price,
    customer pays, partner earns on a first-year payment, partner earns per
    renewal payment (renewal at today's list price).

    `promos` (the cards from promotions()) marks the plans a live sale wins:
    those rows carry sale=True with the SALE price and the promo commission
    in sale_customer_cents / sale_first_cents, so the offer table and the
    promotion card show the same numbers."""
    sales = {}
    for card in (promos or []):
        for pl in card["plans"]:
            if pl["sale_wins"]:
                sales[pl["key"]] = (card, pl)
    out = []
    for tier, iv, lp in _catalog_rows(catalog):
        disc = afs.clamp_discount(afs.effective_discount_pct(aff, iv), terms)
        o = afs.preview_offer(lp, disc, terms)
        r = afs.preview_renewal(lp, terms)
        out.append({"key": afs.offer_key(tier, iv), "tier": tier, "interval": iv,
                    "plan": plan_label(tier, iv), "per": "month" if iv == "month" else "year",
                    "list_cents": lp, "discount_pct": fmt_pct(disc),
                    "customer_cents": o["customer_pays_cents"],
                    "first_cents": o["partner_earns_cents"],
                    "renewal_cents": r["partner_earns_cents"], "sale": False})
        hit = sales.get(out[-1]["key"])
        if hit:
            card, pl = hit
            out[-1].update(sale=True, sale_name=card["name"], sale_ends=card["ends"],
                           sale_customer_cents=pl["pays_cents"], sale_first_cents=pl["earn_cents"])
    return out


def discount_grid(catalog, terms):
    """{discount%: {plan key: [customer_cents, first_year_cents]}} for every
    whole-percent discount the partner may pick. The Settings chooser reads
    this table, so the browser never does commission math of its own."""
    cap = int(afs._dec(terms.max_discount_pct))
    rows = _catalog_rows(catalog)
    grid = {}
    for pct in range(0, cap + 1):
        grid[str(pct)] = {}
        for tier, iv, lp in rows:
            o = afs.preview_offer(lp, pct, terms)
            grid[str(pct)][afs.offer_key(tier, iv)] = [o["customer_pays_cents"],
                                                      o["partner_earns_cents"]]
    example = {str(p): [afs.preview_offer(10000, p, terms)["customer_pays_cents"],
                        afs.preview_offer(10000, p, terms)["partner_earns_cents"]]
               for p in range(0, cap + 1)}
    return {"plans": grid, "example": example}


def discount_history_rows(session, aff, limit=20):
    rows = []
    for c in afs.discount_history(session, aff, limit=limit):
        rows.append({
            "date": fmt_date(c.changed_at),
            "plans": "Monthly plans" if c.billing_interval == "month" else "All plans",
            "old": fmt_pct(c.old_pct) if c.old_pct is not None else None,
            "new": fmt_pct(c.new_pct),
            "by": "TradeWave" if (c.actor or "").startswith("admin") else "You",
        })
    return rows


# ---------------------------------------------------------------------------
# promotions (company campaigns)
# ---------------------------------------------------------------------------
def promotions(session, aff, catalog, terms, now=None):
    """Live campaigns as partner-facing cards. One card per campaign, one row
    per plan it covers. `wins` says which price a referred NEW customer gets
    (the lower of the sale and the partner discount - display_offers decides)."""
    now = _now(now)
    if not catalog:
        return []
    try:
        offers = afs.display_offers(session, aff, catalog, now=now)
    except Exception:   # noqa: BLE001 - a promo card must never break the page
        return []
    live = {c.code: c for c in afs.list_campaigns(session, include_archived=False)
            if afs.campaign_is_live(c, now)}
    cards = {}
    order = {t: i for i, t in enumerate(TIER_ORDER)}
    for key, row in sorted(offers.items(),
                           key=lambda kv: (order.get(kv[1]["tier"], 99), kv[1]["interval"] != "year")):
        price = row.get("campaign_price_cents")
        if price is None:
            continue
        camp = None
        if row.get("campaign"):
            camp = live.get(row["campaign"]["code"])
        if camp is None:
            # the partner discount won: find the campaign that priced this plan
            camp, _p = afs.active_campaign_for(session, row["tier"], row["interval"],
                                               row["list_price_cents"], now)
        if camp is None:
            continue
        card = cards.setdefault(camp.code, {
            "code": camp.code, "name": camp.name, "ends_at": afs._utc(camp.ends_at),
            "ends": fmt_sale_day(camp.ends_at), "ends_full": fmt_date(camp.ends_at),
            "ends_time": fmt_sale_end(camp.ends_at),
            "days_left": max(0, (afs._utc(camp.ends_at) - now).days), "plans": []})
        iv = row["interval"]
        lp = row["list_price_cents"]
        sale_wins = row.get("offer") == "campaign"
        disc = afs.clamp_discount(afs.effective_discount_pct(aff, iv), terms)
        regular = afs.preview_offer(lp, disc, terms)
        if sale_wins:
            earn = afs.preview_promo(price, lp, terms)["partner_earns_cents"]
            pays = price
        else:
            earn, pays = regular["partner_earns_cents"], regular["customer_pays_cents"]
        intro_months = int(camp.intro_months or 12)
        card["plans"].append({
            "plan": plan_label(row["tier"], iv), "interval": iv,
            "key": afs.offer_key(row["tier"], iv),
            # what the same sale would look like at the partner's own discount
            "regular_earn_cents": regular["partner_earns_cents"],
            "regular_pays_cents": regular["customer_pays_cents"],
            "extra_saving_cents": max(0, regular["customer_pays_cents"] - pays),
            "sale_cents": price, "list_cents": lp, "pays_cents": pays, "earn_cents": earn,
            "sale_wins": sale_wins,
            "term": ("first year" if iv == "year" else
                     "a month for %d month%s" % (intro_months, "" if intro_months == 1 else "s")),
            "pays_term": ("for year one" if iv == "year" else
                          "a month for the first %d month%s" % (intro_months, "" if intro_months == 1 else "s")),
            "earn_term": "" if iv == "year" else " a month",
            "renews_term": "" if iv == "year" else " a month",
        })
    plan_count = len(offers)
    for card in cards.values():
        won = [pl for pl in card["plans"] if pl["sale_wins"]]
        card["compare"] = [_promo_compare(card["name"], pl) for pl in won]
        card["other_plans"] = bool(won) and plan_count > len(won)
    return sorted(cards.values(), key=lambda c: c["ends_at"])


def _promo_compare(name, pl):
    """'During Black Friday, Analyst annual through your link pays you $49.50
    instead of $119.70 - your customer saves $220.20 more.' All computed."""
    per = "" if pl["interval"] == "year" else " a month"
    text = "During %s, %s through your link pays you %s%s" % (
        name, pl["plan"], fmt_cents(pl["earn_cents"]), per)
    if pl["earn_cents"] != pl["regular_earn_cents"]:
        text += " instead of %s" % fmt_cents(pl["regular_earn_cents"])
    if pl["extra_saving_cents"] > 0:
        text += " - your customer saves %s more%s" % (fmt_cents(pl["extra_saving_cents"]), per)
    return text + "."


# ---------------------------------------------------------------------------
# customers (anonymized)
# ---------------------------------------------------------------------------
def _referrals(session, aff):
    from models import AffiliateReferral as R
    return (session.query(R).filter(R.affiliate_id == aff.id)
            .order_by(R.attributed_at, R.created_at, R.id).all())


def customer_numbers(referrals):
    """Stable anonymous numbering: customers are numbered in the order they
    were first credited to this partner. Keys are Stripe customer ids (or the
    subscription id when a referral carries no customer). Internal only -
    the ids never reach a template."""
    numbers = {}
    for r in referrals:
        key = r.stripe_customer_id or r.stripe_subscription_id
        if key not in numbers:
            numbers[key] = len(numbers) + 1
    return numbers


def _terms_for_ref(ref, terms_by_id, fallback):
    t = getattr(ref, "terms", None)
    if t is None and getattr(ref, "terms_id", None) is not None:
        t = terms_by_id.get(ref.terms_id)
    return t or fallback


def _today_price(ref, catalog):
    """Today's list price for the referral's plan (renewals are previewed 'at
    today's price'); the price stamped at checkout when the catalog is out."""
    plan = (catalog or {}).get((ref.tier, ref.billing_interval)) if ref.tier else None
    lp = int((plan or {}).get("list_price_cents") or 0)
    return lp or int(ref.list_price_cents or 0)


def _upcoming(ref, terms, campaigns, catalog, now, horizon):
    """Expected payments of ONE paying referral between now and horizon:
    [(when, year_number, cents, kind)]. Assumes the customer keeps renewing
    at today's price; year 1 follows the referral's stamped offer."""
    anchor = afs._utc(ref.year_anchor_at or ref.first_paid_at)
    iv = ref.billing_interval
    if anchor is None or iv not in ("month", "year") or ref.ended_at is not None:
        return []
    step = 12 if iv == "year" else 1
    k = afs.months_since_anchor(anchor, now)
    k = (k // step + 1) * step
    out = []
    last = terms.renewal_years
    today_price = _today_price(ref, catalog)
    stamped = int(ref.list_price_cents or 0) or today_price
    while True:
        when = afs._add_months(anchor, k)
        if when > horizon:
            break
        if when > now:
            year = k // 12 + 1
            if year == 1:
                if ref.offer_type == "promo":
                    camp = campaigns.get(ref.campaign_id)
                    paid = stamped
                    if camp is not None and k < int(camp.intro_months or 12):
                        paid = afs.campaign_first_period_cents(camp, ref.tier, iv, stamped) or stamped
                    cents = afs.preview_promo(paid, stamped, terms)["partner_earns_cents"]
                    kind = "promo"
                else:
                    disc = afs.clamp_discount(ref.discount_pct or 0, terms)
                    cents = afs.preview_offer(stamped, disc, terms)["partner_earns_cents"] if stamped else 0
                    kind = "first_year"
            elif last is None or year <= int(last):
                cents = afs.preview_renewal(today_price, terms)["partner_earns_cents"]
                kind = "renewal"
            else:
                cents, kind = 0, "ended"
            out.append((when, year, cents, kind))
        k += step
        if k > 12 * 200:
            break
    return out


def _load_side_tables(session):
    from models import AffiliateTerms, PromoCampaign
    terms_by_id = {t.id: t for t in session.query(AffiliateTerms).all()}
    campaigns = {c.id: c for c in session.query(PromoCampaign).all()}
    return terms_by_id, campaigns


def _earned_by_referral(lines):
    """{referral key: Decimal} from ledger line dicts (void / lapsed earn $0)."""
    out = {}
    for ln in lines:
        if ln["state_key"] in ("void", "lapsed"):
            continue
        out[ln["_ref_key"]] = out.get(ln["_ref_key"], Decimal("0")) + ln["amount"]
    return out


def customers(session, aff, catalog, terms, lines, activity, now=None):
    """One row per referred subscription, newest first. Never names/emails."""
    now = _now(now)
    refs = _referrals(session, aff)
    numbers = customer_numbers(refs)
    terms_by_id, campaigns = _load_side_tables(session)
    earned = _earned_by_referral(lines)
    horizon = afs._add_months(now, 13)
    active_until = activity.get("active_until")
    rule_on = int(activity.get("activity_rule_months") or 0) > 0
    rows = []
    for r in refs:
        t = _terms_for_ref(r, terms_by_id, terms)
        sched = afs.renewal_schedule(t)
        if r.ended_at is not None:
            status = "ended"
        elif r.first_paid_at is not None:
            status = "paying"
        else:
            status = "trial"
        anchor = afs._utc(r.year_anchor_at or r.first_paid_at)
        year_label, year_now = "-", None
        if anchor is not None:
            year_now = afs.year_number(anchor, min(now, afs._utc(r.ended_at) or now))
            if sched["lifetime"]:
                year_label = "Year %d (lifetime)" % year_now
            elif year_now > int(sched["last_year"]):
                year_label = "Year %d (past year %d)" % (year_now, sched["last_year"])
            else:
                year_label = "Year %d of %d" % (year_now, sched["last_year"])
        nxt = _upcoming(r, t, campaigns, catalog, now, horizon) if status == "paying" else []
        next_date = next_cents = None
        next_note = None
        if nxt:
            when, year, cents, kind = nxt[0]
            next_date, next_cents = when, cents
            if kind == "ended":
                next_note = "Past the commission window"
            elif kind == "renewal" and rule_on and (
                    active_until is None or when.date() > active_until):
                next_note = "Needs a new paying customer first"
        key = r.stripe_customer_id or r.stripe_subscription_id
        rows.append({
            "number": numbers[key], "label": "Customer #%d" % numbers[key],
            "signed_up": fmt_date(r.attributed_at), "signed_up_at": afs._utc(r.attributed_at),
            "tier": r.tier, "interval": r.billing_interval,
            "plan": plan_label(r.tier, r.billing_interval),
            "status": status, "status_label": STATUS_LABELS[status],
            "year": year_label,
            "next_renewal": fmt_date(next_date) if next_date else "-",
            "next_commission": next_cents,
            "next_note": next_note,
            "earned": earned.get(str(r.id), Decimal("0")).quantize(_CENT, rounding=ROUND_HALF_UP),
            "source": SOURCE_LABELS.get(r.source, "Your link"),
            "source_key": r.source,
            "promo": r.offer_type == "promo",
        })
    rows.sort(key=lambda x: (x["signed_up_at"] or dt.datetime.min.replace(tzinfo=UTC), x["number"]),
              reverse=True)
    return rows


def filter_customers(rows, status=None, interval=None, source=None):
    out = rows
    if status in STATUS_LABELS:
        out = [r for r in out if r["status"] == status]
    if interval in INTERVAL_LABELS:
        out = [r for r in out if r["interval"] == interval]
    if source in SOURCE_LABELS:
        out = [r for r in out if r["source_key"] == source]
    return out


def customers_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Customer", "Signed up", "Plan", "Status", "Commission year", "Next renewal",
                "Next commission (est.)", "Next commission note", "Earned to date", "Source"])
    for r in rows:
        w.writerow([r["label"], r["signed_up"], r["plan"], r["status_label"], r["year"],
                    r["next_renewal"],
                    "" if r["next_commission"] is None else "%.2f" % (r["next_commission"] / 100.0),
                    r["next_note"] or "", "%.2f" % r["earned"], r["source"]])
    return buf.getvalue()


def forecast(session, aff, catalog, terms, now=None, months=12):
    """Expected commission from CURRENT paying customers over the next 12
    months, per calendar month - "if every customer renews at today's price".
    Renewals count only inside the commission window of each referral's
    terms. Does not apply the activity rule (the page says so)."""
    now = _now(now)
    horizon = afs._add_months(now, months)
    terms_by_id, campaigns = _load_side_tables(session)
    buckets = []
    first = dt.date(now.year, now.month, 1)
    for i in range(months + 1):
        idx = first.year * 12 + first.month - 1 + i
        buckets.append({"month": dt.date(idx // 12, idx % 12 + 1, 1), "cents": 0,
                        "renewal_cents": 0, "payments": 0})
    by_month = {b["month"]: b for b in buckets}
    total = renewals = 0
    for r in _referrals(session, aff):
        if r.first_paid_at is None or r.ended_at is not None:
            continue
        t = _terms_for_ref(r, terms_by_id, terms)
        for when, year, cents, kind in _upcoming(r, t, campaigns, catalog, now, horizon):
            b = by_month.get(dt.date(when.year, when.month, 1))
            if b is None or cents <= 0:
                continue
            b["cents"] += cents
            b["payments"] += 1
            total += cents
            if kind == "renewal":
                b["renewal_cents"] += cents
                renewals += cents
    if buckets and buckets[-1]["cents"] == 0:
        buckets = buckets[:-1]
    peak = max([b["cents"] for b in buckets] or [0])
    for b in buckets:
        b["label"] = b["month"].strftime("%b '%y" if (b["month"].month == 1 or b is buckets[0]) else "%b")
        b["full_label"] = b["month"].strftime("%b %Y")
        b["pct"] = int(round(100.0 * b["cents"] / peak)) if peak else 0
    return {"months": buckets, "total_cents": total, "renewal_cents": renewals,
            "has_data": total > 0}


# ---------------------------------------------------------------------------
# earnings ledger
# ---------------------------------------------------------------------------
def _how(kind, rate, basis_cents, net_cents, currency, list_cents=0, reverses=None):
    """'30% of $29.00 list' / '50% of $99.00 paid' / 'Reverses 30% of $29.00
    list': the sum a partner can check on a calculator. First-year commission
    is a share of the LIST price; promotions and renewals are a share of what
    the customer paid."""
    pct = fmt_pct(rate) or "0"
    if kind == "lapsed":
        return "No commission - renewals were off"
    if kind in ("refund", "dispute"):
        on_list = (reverses in ("first_year", "payment") if reverses
                   else abs(int(basis_cents or 0)) != abs(int(net_cents or 0)))
        base = abs(int(basis_cents or 0)) or abs(int(net_cents or 0))
        return "Reverses %s%% of %s %s" % (pct, fmt_cents(base, currency),
                                           "list" if on_list else "paid")
    if kind in ("first_year", "payment"):
        base = int(basis_cents or 0) or int(list_cents or 0) or int(net_cents or 0)
        return "%s%% of %s list" % (pct, fmt_cents(base, currency))
    base = int(basis_cents or 0) or int(net_cents or 0)
    return "%s%% of %s paid" % (pct, fmt_cents(base, currency))


def _lapsed_reason(when, first_paid_dates, rule_months=12):
    """'Renewals were off: no new paying customer since <date>' - the date is
    the last NEW paying customer before this renewal. The date is only named
    when it explains the lapse (it is outside the activity window)."""
    before = [d for d in first_paid_dates if when is None or d <= when]
    if before and when is not None:
        last = max(before)
        window_end = (afs._add_months(last, int(rule_months or 12))
                      + dt.timedelta(days=int(getattr(afs, "ACTIVITY_GRACE_DAYS", 30))))
        if window_end <= when:
            return "Renewals were off: no new paying customer since %s" % fmt_date(last)
    return ("Renewals were off: no new paying customer in the %d months before this renewal"
            % int(rule_months or 12))


def _line_view(d, numbers, ref_by_id, ref_by_sub, tax_ok, first_paid_dates=(), signed=True,
               rule_months=12):
    """A ledger line (engine/detail dict) as a display row."""
    ref = ref_by_id.get(d.get("referral_id")) or ref_by_sub.get(d.get("subscription"))
    key = d.get("customer") or d.get("subscription")
    if ref is not None:
        key = ref.stripe_customer_id or ref.stripe_subscription_id
    number = numbers.get(key)
    kind = d.get("kind") or "payment"
    state = d.get("state") or "pending"
    reason = HOLD_REASONS.get(d.get("hold_reason") or "", None)
    amount = afs._dec(d.get("amount")).quantize(_CENT, rounding=ROUND_HALF_UP)
    if state == "pending" and not tax_ok and amount > 0:
        state, reason = "held", HOLD_REASONS["tax_form"]
    if state == "held" and reason is None:
        # never an unexplained hold
        reason = HOLD_REASONS["review" if signed else "unsigned"]
    when = afs._utc(_parse_iso(d.get("event_at")))
    if state == "lapsed" or kind == "lapsed":
        reason = _lapsed_reason(when, first_paid_dates, rule_months)
    interval = d.get("interval") or getattr(ref, "billing_interval", None)
    tier = getattr(ref, "tier", None)
    year = d.get("year_number")
    return {
        "when": when, "date": fmt_date(when),
        "customer": ("Customer #%d" % number) if number else "Customer",
        "customer_number": number,
        "plan": plan_label(tier, interval),
        "interval": interval,
        "kind": kind, "type": KIND_LABELS.get(kind, kind.replace("_", " ").capitalize()),
        "is_dispute": kind == "dispute",
        "year": year,
        "paid": (Decimal(int(d.get("net_paid_cents") or 0)) / 100).quantize(_CENT),
        "rate": fmt_pct(d.get("rate_pct")),
        "how": _how(kind, d.get("rate_pct"), d.get("basis_cents"), d.get("net_paid_cents"),
                    (d.get("currency") or "usd").lower(),
                    list_cents=getattr(ref, "list_price_cents", 0) or 0,
                    reverses=d.get("reverses_kind")),
        "amount": amount,
        "currency": (d.get("currency") or "usd").lower(),
        "state_key": state, "state": STATE_LABELS.get(state, state.capitalize()),
        "reason": reason,
        "_ref_key": str(ref.id) if ref is not None else None,
    }


def ledger(session, aff, estimate_lines=None):
    """Every commission line of the partner, newest first: the persisted
    ledger plus this month's not-yet-booked ESTIMATED lines."""
    from models import AffiliateCommissionLine as L
    refs = _referrals(session, aff)
    numbers = customer_numbers(refs)
    ref_by_id = {str(r.id): r for r in refs}
    ref_by_sub = {r.stripe_subscription_id: r for r in refs}
    tax_ok = aff.tax_form_received_at is not None
    signed = aff.agreement_signed_at is not None
    new_paid = [afs._utc(r.first_paid_at) for r in refs
                if r.first_paid_at is not None and r.source != "return"]
    rule = int(getattr(afs.terms_for(session, aff), "activity_rule_months", 12) or 12)
    out, seen = [], set()
    for row in (session.query(L).filter(L.affiliate_id == aff.id).all()):
        d = afs._line_dict_from_row(row)
        seen.add(d["source_id"])
        out.append(_line_view(d, numbers, ref_by_id, ref_by_sub, tax_ok, new_paid, signed, rule))
    for d in (estimate_lines or []):
        if d.get("persisted") or d.get("source_id") in seen:
            continue
        seen.add(d.get("source_id"))
        out.append(_line_view(d, numbers, ref_by_id, ref_by_sub, tax_ok, new_paid, signed, rule))
    floor = dt.datetime.min.replace(tzinfo=UTC)
    out.sort(key=lambda x: x["when"] or floor, reverse=True)
    return out


def filter_ledger(lines, state=None, kind=None, days=None, now=None):
    out = lines
    if state in STATE_LABELS:
        out = [ln for ln in out if ln["state_key"] == state]
    if kind == "refund":
        out = [ln for ln in out if ln["kind"] in ("refund", "dispute")]
    elif kind in KIND_LABELS:
        out = [ln for ln in out if ln["kind"] == kind]
    if days:
        floor = _now(now) - dt.timedelta(days=int(days))
        out = [ln for ln in out if ln["when"] is not None and ln["when"] >= floor]
    return out


def ledger_totals(lines):
    """{currency: {state_key: Decimal, 'total': Decimal}} - never summed
    across currencies. Void and lapsed lines add nothing."""
    totals = {}
    for ln in lines:
        t = totals.setdefault(ln["currency"], {"estimated": Decimal("0"), "pending": Decimal("0"),
                                               "paid": Decimal("0"), "held": Decimal("0"),
                                               "total": Decimal("0")})
        if ln["state_key"] in ("void", "lapsed"):
            continue
        t[ln["state_key"]] = t.get(ln["state_key"], Decimal("0")) + ln["amount"]
        t["total"] += ln["amount"]
    return totals


def ledger_by_month(lines):
    """Lines (already newest first) grouped per calendar month for the phone
    layout: [{label, count, totals [(currency, Decimal)], lines}]. A month
    total counts what the ledger total counts (void and lapsed add nothing)."""
    groups = []
    for ln in lines:
        key = (ln["when"].year, ln["when"].month) if ln["when"] else None
        if not groups or groups[-1]["key"] != key:
            groups.append({"key": key, "lines": [], "_totals": {},
                           "label": ln["when"].strftime("%B %Y") if ln["when"] else "Undated"})
        g = groups[-1]
        g["lines"].append(ln)
        if ln["state_key"] not in ("void", "lapsed"):
            g["_totals"][ln["currency"]] = g["_totals"].get(ln["currency"], Decimal("0")) + ln["amount"]
    for g in groups:
        g["count"] = len(g["lines"])
        g["totals"] = sorted(g.pop("_totals").items()) or [("usd", Decimal("0"))]
    return groups


def ledger_csv(lines):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Customer", "Plan", "Type", "Commission year", "Customer paid",
                "How it's worked out", "Amount", "Currency", "State", "Reason"])
    for ln in lines:
        w.writerow([ln["when"].strftime("%Y-%m-%d") if ln["when"] else "", ln["customer"],
                    ln["plan"], ln["type"], ln["year"] or "", "%.2f" % ln["paid"], ln["how"],
                    "%.2f" % ln["amount"], ln["currency"].upper(), ln["state"], ln["reason"] or ""])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# funnel
# ---------------------------------------------------------------------------
def funnel(session, aff, lines, range_key="30d", now=None):
    """Clicks > Signups > Paid for a date range, with step rates,
    click-to-paid and earnings per click. Counts only. Every signup starts
    the 7-day trial, so there is no separate trial step."""
    from sqlalchemy import func as safunc
    from models import AffiliateClick, AffiliateReferral, User
    now = _now(now)
    days = dict((k, d) for k, _l, d in RANGES).get(range_key, 30)
    if range_key not in dict((k, d) for k, _l, d in RANGES):
        range_key = "30d"
    since = (now - dt.timedelta(days=days)) if days else None

    q = (session.query(safunc.coalesce(safunc.sum(AffiliateClick.clicks), 0))
         .filter(AffiliateClick.affiliate_id == aff.id))
    if since is not None:
        q = q.filter(AffiliateClick.day >= since.date())
    clicks = int(q.scalar() or 0)

    uq = session.query(User).filter(User.referred_by_affiliate_id == aff.id)
    if since is not None:
        uq = uq.filter(User.referred_at >= since)
    signups = uq.count()
    trials = uq.filter(User.reverse_trial_ends_at.isnot(None)).count()
    in_trial = (session.query(User).filter(User.referred_by_affiliate_id == aff.id,
                                           User.reverse_trial_ends_at > now).count())

    pq = (session.query(AffiliateReferral)
          .filter(AffiliateReferral.affiliate_id == aff.id,
                  AffiliateReferral.first_paid_at.isnot(None),
                  AffiliateReferral.source != "return"))
    if since is not None:
        pq = pq.filter(AffiliateReferral.first_paid_at >= since)
    paid = pq.count()

    earned = {}
    for ln in lines:
        if ln["state_key"] in ("void", "lapsed"):
            continue
        if since is not None and (ln["when"] is None or ln["when"] < since):
            continue
        earned[ln["currency"]] = earned.get(ln["currency"], Decimal("0")) + ln["amount"]

    def rate(a, b):
        return ("%.1f%%" % (100.0 * a / b)) if b else None

    steps = [
        {"key": "clicks", "label": "Clicks", "value": clicks, "rate": None,
         "hint": "New visitors who opened your link or join page"},
        {"key": "signups", "label": "Signups", "value": signups, "rate": rate(signups, clicks),
         "hint": "(each starts a 7-day trial)", "keep_hint": True},
        {"key": "paid", "label": "Paid", "value": paid, "rate": rate(paid, signups),
         "hint": "New customers whose first payment went through"},
    ]
    peak = max([s["value"] for s in steps] or [0])
    for s in steps:
        s["pct"] = max(4, int(round(100.0 * s["value"] / peak))) if peak and s["value"] else 0
    usd = earned.get("usd", Decimal("0"))
    return {
        "range": range_key, "ranges": [(k, l) for k, l, _d in RANGES],
        "range_label": dict((k, l) for k, l, _d in RANGES)[range_key],
        "steps": steps, "clicks": clicks, "signups": signups, "trials": trials, "paid": paid,
        "in_trial": in_trial,
        "click_to_paid": rate(paid, clicks),
        "earned": sorted(earned.items()),
        "epc": fmt_money(usd / clicks) if clicks else None,
        "empty": not (clicks or signups or paid),
    }


# ---------------------------------------------------------------------------
# activity rule, payouts, action strip
# ---------------------------------------------------------------------------
def activity_card(aff, session, terms, now=None):
    """The activity-rule card: tone green | amber | red | none, with the
    exact partner-facing sentence."""
    now = _now(now)
    st = afs.activity_status(aff, now, session=session, terms=terms)
    months = int(st.get("activity_rule_months") or 0)
    grace = int(getattr(afs, "ACTIVITY_GRACE_DAYS", 30))
    # Dates always come from activity_status()["active_until"] (it applies the
    # grace); this sentence only explains the rule.
    card = {"status": st, "tone": "none", "title": None, "text": None, "days_left": None,
            "months": months,
            "rule": ("The rule: at least 1 new paying customer every %d months, with a "
                     "%d-day grace." % (months, grace))}
    if months <= 0:
        return card
    if st["active"] and st.get("active_until"):
        until = st["active_until"]
        days_left = (until - now.date()).days
        card["days_left"] = days_left
        card["tone"] = "amber" if days_left <= 60 else "green"
        card["title"] = "You're active until %s." % fmt_date(until)
        card["text"] = ("Refer 1 new paying customer before then to keep your renewal "
                        "commissions. Free trials don't count until they pay.")
        if days_left <= 60:
            card["badge"] = "%d day%s left" % (max(days_left, 0), "" if days_left == 1 else "s")
    elif st.get("lapsed_since"):
        card["tone"] = "red"
        card["title"] = "Renewal commissions are stopped."
        card["text"] = ("They start again with your next new paying customer. "
                        "Renewals during the gap are not paid back.")
        card["since"] = fmt_date(st["lapsed_since"])
    else:
        card["tone"] = "start"
        card["title"] = "Your first paying customer starts the clock."
        card["text"] = ("To earn on renewals you need at least 1 new paying customer every "
                        "%d months, with a %d-day grace. Free trials don't count until they pay."
                        % (months, grace))
    return card


def payout_totals(session, aff):
    """({currency: Decimal} pending, {currency: Decimal} paid) from the
    payout ledger. Pending includes negative carry rows (net)."""
    from sqlalchemy import func as safunc
    from models import AffiliatePayout as P
    out = {"pending": {}, "paid": {}}
    q = (session.query(P.status, P.currency, safunc.coalesce(safunc.sum(P.commission_amount), 0))
         .filter(P.affiliate_id == aff.id, P.status.in_(("pending", "paid")))
         .group_by(P.status, P.currency))
    for status, cur, amt in q.all():
        out[status][(cur or "usd").lower()] = Decimal(str(amt))
    return out["pending"], out["paid"]


def next_payout_date(now=None):
    """Statements are computed on the 2nd for the month before; payouts are
    sent after that review. Returns the next statement date."""
    today = _now(now).date()
    if today.day < 2:
        return today.replace(day=2)
    return (today.replace(day=1) + dt.timedelta(days=32)).replace(day=2)


def payout_checklist(aff, pending, held_cents=0, now=None):
    """Checklist + progress toward the $50 minimum (USD)."""
    usd = pending.get("usd", Decimal("0"))
    cents = int((usd * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    tax_ok = aff.tax_form_received_at is not None
    method_ok = bool(aff.payout_method and aff.payout_email)
    min_ok = cents >= PAYOUT_MINIMUM_CENTS
    return {
        "items": [
            {"key": "tax", "ok": tax_ok, "label": "Tax form on file",
             "help": None if tax_ok else
             "W-9 (U.S.) or W-8BEN / W-8BEN-E (non-U.S.). " + TAX_FORM_HELP},
            {"key": "method", "ok": method_ok, "label": "Payout method set",
             "help": None if method_ok else PAYOUT_METHOD_HELP},
            {"key": "minimum", "ok": min_ok,
             "label": "%s minimum reached" % fmt_price(PAYOUT_MINIMUM_CENTS),
             "help": None if min_ok else
             "%s to go. Smaller balances roll into your next payout."
             % fmt_cents(max(0, PAYOUT_MINIMUM_CENTS - cents))},
        ],
        "ready": tax_ok and method_ok and min_ok and aff.status == "active",
        "pending_cents": cents,
        "minimum_cents": PAYOUT_MINIMUM_CENTS,
        "progress_pct": max(0, min(100, int(round(100.0 * cents / PAYOUT_MINIMUM_CENTS)))),
        "next_date": fmt_date(next_payout_date(now)),
        "send_by": fmt_date(next_payout_date(now).replace(day=15)),
        "send_rule": PAYOUT_SEND_RULE,
        "held_cents": held_cents,
    }


def _month_span(months):
    """[date] -> 'Sep 2026' / 'Sep and Oct 2026' / 'Sep to Nov 2026' (a run of
    consecutive months) / 'Jul, Sep and Oct 2026'."""
    ms = sorted(set(months))
    if not ms:
        return ""
    same_year = ms[0].year == ms[-1].year
    names = [m.strftime("%b" if same_year else "%b %Y") for m in ms]
    tail = (" %d" % ms[0].year) if same_year else ""
    idx = [m.year * 12 + m.month for m in ms]
    if len(ms) >= 3 and idx[-1] - idx[0] == len(ms) - 1:
        return "%s to %s%s" % (names[0], names[-1], tail)
    if len(ms) == 1:
        return names[0] + tail
    return "%s and %s%s" % (", ".join(names[:-1]), names[-1], tail)


def payout_history(session, aff, now=None, limit=60):
    """Payout rows as statements: which months each one includes (its own
    month plus any small or negative months carried into it), and when a
    pending one is expected. Read from affiliate_payouts (detail.carry_in,
    the carried:<month> reference) and the lines booked to each payout."""
    from models import AffiliateCommissionLine as L, AffiliatePayout as P
    today = _now(now).date()
    rows = (session.query(P).filter(P.affiliate_id == aff.id)
            .order_by(P.period_start.desc()).limit(limit).all())
    line_months = {}
    for pid, month in (session.query(L.payout_id, L.period_month)
                       .filter(L.affiliate_id == aff.id, L.payout_id.isnot(None)).distinct().all()):
        if month is not None:
            line_months.setdefault(pid, set()).add(dt.date(month.year, month.month, 1))
    out = []
    for p in rows:
        own = dt.date(p.period_start.year, p.period_start.month, 1)
        months = {own} | line_months.get(p.id, set())
        for c in ((p.detail or {}).get("carry_in") or []):
            m = _as_date(c.get("period"))
            if m:
                months.add(dt.date(m.year, m.month, 1))
        ref = p.external_ref or ""
        carried_to = None
        if ref.startswith("carried:"):
            try:
                carried_to = dt.datetime.strptime(ref[len("carried:"):], "%Y-%m").strftime("%b %Y")
            except ValueError:
                carried_to = ref[len("carried:"):]
        send_by = (own + dt.timedelta(days=32)).replace(day=15)
        out.append({
            "period": p.period_start.strftime("%B %Y"),
            "statement": "Statement for %s" % p.period_start.strftime("%b %Y"),
            "includes": ("includes %s lines" % _month_span(months)) if len(months) > 1 else None,
            "currency": p.currency, "commission": p.commission_amount, "status": p.status,
            "paid_at": fmt_date(p.paid_at) if p.paid_at else None,
            "expected": (fmt_date(send_by) if p.status == "pending" and not carried_to
                         and send_by >= today else None),
            "external_ref": p.external_ref, "carried_to": carried_to,
        })
    return out


def link_block(aff):
    """Why the partner's links and code do NOT credit them right now (shown
    on every disabled Copy button), or None when they work."""
    if aff.agreement_signed_at is None:
        return "Works after you sign your agreement"
    if aff.status == "paused":
        return "Paused - links don't credit you right now"
    if aff.status != "active":
        return "Not active - links don't credit you right now"
    return None


def getting_started(plans, offer, has_paying):
    """The 3-step card for a partner with no paying customer yet (None once
    they have one). The dollar range is the first-year commission over the
    annual plans at the partner's current discount."""
    if has_paying:
        return None
    earns = (sorted(p["first_cents"] for p in plans if p["interval"] == "year")
             or sorted(p["first_cents"] for p in plans))
    if earns and earns[0] != earns[-1]:
        earn = "%s to %s (first year, depending on plan)" % (fmt_cents(earns[0]), fmt_cents(earns[-1]))
    elif earns:
        earn = "%s (first year)" % fmt_cents(earns[0])
    else:
        earn = "%s%% of the list price (first year)" % offer["rate_year"]
    return ["Share your link.",
            "When someone pays, you earn %s." % earn,
            "We pay you monthly by PayPal or Wise once you're over %s."
            % fmt_price(PAYOUT_MINIMUM_CENTS)]


def welcome_back(aff, user, has_activity):
    """'Welcome back' only for a partner who has been here before: they have
    activity, or their login is from a later day than the day they joined."""
    if has_activity:
        return True
    last = afs._utc(getattr(user, "last_login_at", None))
    joined = afs._utc(getattr(aff, "agreement_signed_at", None) or getattr(aff, "created_at", None))
    return bool(last and joined and last - joined > dt.timedelta(days=1))


def action_items(aff, activity, urls):
    """The Home action strip: only what needs the partner's attention."""
    items = []
    if aff.agreement_signed_at is None:
        items.append({"key": "agreement", "tone": "red", "title": "Sign your partner agreement",
                      "text": "Your link and code switch on as soon as you sign. "
                              "The signing link is in your email.",
                      "post": urls.get("resend"), "cta": "Email me the link"})
    elif aff.status == "paused":
        items.append({"key": "paused", "tone": "amber", "title": "Your account is paused",
                      "text": "Commissions keep adding up and are paid when it is reactivated. "
                              "Your links don't credit you while paused.",
                      "href": "mailto:help@tradewave.ai", "cta": "Contact us"})
    if aff.tax_form_received_at is None:
        items.append({"key": "tax", "tone": "red", "title": "Send your tax form",
                      "text": "Payouts are held until we have a W-9 (U.S.) or "
                              "W-8BEN / W-8BEN-E (non-U.S.). Don't email it - "
                              "we'll send you a secure upload link.",
                      "href": urls.get("payouts"), "cta": "How to send it"})
    if not (aff.payout_method and aff.payout_email):
        items.append({"key": "payout", "tone": "amber", "title": "Add a payout method",
                      "text": "Tell us where to send your money: PayPal or Wise.",
                      "href": urls.get("payouts"), "cta": "Set it up"})
    if activity.get("tone") == "amber":
        items.append({"key": "activity", "tone": "amber",
                      "title": "Keep your renewals: %s" % activity.get("badge", ""),
                      "text": "Refer 1 new paying customer by %s to keep earning on renewals."
                              % fmt_date(activity["status"]["active_until"]),
                      "href": urls.get("links"), "cta": "Get your link"})
    return items


# ---------------------------------------------------------------------------
# promote: swipe copy
# ---------------------------------------------------------------------------
DISCLOSURE = "I earn a commission if you subscribe through my link."


def swipe_copy(aff, links, offer):
    """Ready-to-post copy per channel, prefilled with the partner's code and
    discount, always ending in the FTC disclosure line."""
    code = aff.code
    join = links["join"]
    d = offer["discount_year"]
    has_disc = d not in ("", "0")
    # At 0% there is no checkout code to type (no Stripe coupon): link only.
    deal = ("%s%% off your first year with my code %s" % (d, code)) if has_disc else "my link"
    return [
        {"key": "social", "channel": "Social post",
         "text": ("Before I place a trade I check whether the market has a seasonal habit. "
                  "TradeWave shows how a pattern did in every past year, drawdowns included. "
                  "Try it with %s: %s\n\n%s" % (deal, join, DISCLOSURE))},
        {"key": "email", "channel": "Email or newsletter",
         "text": ("Subject: The seasonal research tool I use\n\n"
                  "I use TradeWave to check whether a stock, ETF or market has a repeatable "
                  "seasonal tendency before I act. It shows each past year, not just the "
                  "average, so you can see the bad years too. It is research, not advice, and "
                  "past patterns do not guarantee future results.\n\n"
                  "If you want to try it, use my link: %s\n%s\n\n%s"
                  % (join, ("You get %s." % deal) if has_disc else "The link takes you straight there.",
                     DISCLOSURE))},
        {"key": "video", "channel": "Video or podcast",
         "text": ("Today's research came from TradeWave, which maps seasonal patterns across "
                  "decades of data. The link is in the description%s. %s"
                  % ((", and code %s gets you %s%% off your first year" % (code, d)) if has_disc
                     else "", DISCLOSURE))},
        {"key": "bio", "channel": "Link in bio",
         "text": ("Seasonal market research I use: %s%s. %s"
                  % (join, (" (%s%% off with %s)" % (d, code)) if has_disc else "", DISCLOSURE))},
    ]
