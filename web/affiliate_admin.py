"""Admin screens for affiliate program v2 (TW-TASK-0038, Phase 2).

Two layers:

  1. Pure helpers (no Flask, no Stripe): form validation, the dollar preview
     tables and the payout rules. Every dollar figure comes from
     affiliate_service (preview_offer / preview_promo / preview_renewal /
     campaign_first_period_cents) - nothing here re-implements the math.
  2. make_views(): the Flask-Admin BaseViews (Terms, Campaigns, Change terms)
     built on those helpers. web/app.py registers them; the ModelViews
     (Affiliates, Payout Ledger, Commission lines) stay in web/app.py and call
     the helpers.

All times are stored in UTC. The campaign form accepts and shows the claim
window in a named timezone (config.ADMIN_DISPLAY_TIMEZONE by default).
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import uuid
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

import affiliate_nav
import affiliate_service as afs
import config

log = logging.getLogger(__name__)

PLANS = (("navigator", "Navigator"), ("analyst", "Analyst"), ("strategist", "Strategist"))
INTERVALS = (("month", "Monthly"), ("year", "Annual"))
PLAN_LABEL = dict(PLANS)
INTERVAL_LABEL = dict(INTERVALS)
RENEWAL_LENGTHS = (("5", "5 years (renewals paid in years 2-5)"),
                   ("10", "10 years (renewals paid in years 2-10)"),
                   ("lifetime", "Lifetime (renewals paid every year)"))
TIMEZONES = ("America/New_York", "America/Chicago", "America/Denver",
             "America/Los_Angeles", "Europe/London", "UTC")
_LOCAL_FMT = "%Y-%m-%dT%H:%M"

LINE_KIND_LABELS = {
    "first_year": "First year", "promo": "Promotion sale", "renewal": "Renewal",
    "lapsed": "Renewal - not earned (partner inactive)", "refund": "Refund",
    "dispute": "Chargeback",
}
# A POSITIVE refund / dispute line gives an earlier clawback back (detail
# outcome 'failed' / 'won').
LINE_OUTCOME_LABELS = {
    ("dispute", "won"): "Chargeback won - commission restored",
    ("refund", "failed"): "Refund failed - commission restored",
}


def line_kind_label(line) -> str:
    """Label of a ledger line (ORM row), aware of give-back lines."""
    outcome = (getattr(line, "detail", None) or {}).get("outcome")
    return (LINE_OUTCOME_LABELS.get((line.kind, outcome))
            or LINE_KIND_LABELS.get(line.kind, line.kind))


LINE_STATE_LABELS = {
    "pending": "Payable", "paid": "Paid", "held": "Held",
    "lapsed": "Not earned", "void": "Forfeited / void",
}
HOLD_REASON_LABELS = {
    "paused": "Partner paused - becomes payable when the partner is active again",
    "terminated": "Partner terminated (not for cause) - released at the next commit",
    "terminated_for_cause": "Terminated for cause - forfeited",
}


class FormError(afs.AffiliateError):
    """One or more problems with an admin form. `errors` lists them all."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def money(cents) -> str:
    """Cents -> '$1,234.50' ('-$15.00' when negative, '-' for None)."""
    if cents is None:
        return "-"
    c = int(cents)
    return "%s$%s" % ("-" if c < 0 else "", format(Decimal(abs(c)) / 100, ",.2f"))


def money_amount(amount) -> str:
    """Decimal currency units -> '$30.00'."""
    if amount is None:
        return "-"
    return money(int((Decimal(str(amount)) * 100).quantize(Decimal("1"))))


def pct(v) -> str:
    """Decimal percent -> '20' / '12.5' (no trailing zeros)."""
    if v is None or v == "":
        return ""
    d = Decimal(str(v)).quantize(Decimal("0.01"))
    s = format(d, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def renewal_length_label(terms) -> str:
    years = getattr(terms, "renewal_years", None)
    if years is None:
        return "Lifetime"
    return "%d years (renewals in years 2-%d)" % (int(years), int(years))


def terms_summary(terms) -> str:
    """One plain-English line describing a terms version."""
    t = terms if terms is not None else afs.DEFAULT_TERMS
    return ("%s: %s%% pool, customer discount up to %s%%, promotions pay %s%% of what the "
            "customer paid, renewals pay %s%% - %s" % (
                t.version, pct(t.pool_pct), pct(t.max_discount_pct),
                pct(t.promo_commission_pct), pct(t.renewal_pct),
                renewal_length_label(t).lower()))


# ---------------------------------------------------------------------------
# Partner discount: validation + the dollar preview table
# ---------------------------------------------------------------------------

def parse_discount(raw, terms=None, label="Customer discount") -> Decimal:
    """A partner's customer discount from form input. Allowed range is 0 to
    terms.max_discount_pct (25 on the standard terms); the range itself is
    enforced by affiliate_service.preview_offer."""
    cap = pct(afs._terms_of(terms).max_discount_pct)
    try:
        value = Decimal(str(raw).strip())
        if not value.is_finite():
            raise ValueError(raw)
        value = value.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, AttributeError):
        raise afs.AffiliateError("%s must be a number from 0 to %s." % (label, cap))
    try:
        afs.preview_offer(10000, value, terms)
    except afs.AffiliateError:
        raise afs.AffiliateError("%s must be from 0%% to %s%% (you entered %s%%)."
                                 % (label, cap, pct(value)))
    return value


def _offer_row(plan, interval, list_cents, discount, terms):
    offer = afs.preview_offer(list_cents, discount, terms)
    renewal = afs.preview_renewal(list_cents, terms)
    return {
        "plan": plan, "interval": interval,
        "discount_pct": pct(discount),
        "commission_rate_pct": pct(offer["commission_rate_pct"]),
        "list_price_cents": offer["list_price_cents"],
        "customer_pays_cents": offer["customer_pays_cents"],
        "partner_first_year_cents": offer["partner_earns_cents"],
        "partner_renewal_cents": renewal["partner_earns_cents"],
        "retained_cents": offer["retained_cents"],
        "list_price": money(offer["list_price_cents"]),
        "customer_pays": money(offer["customer_pays_cents"]),
        "partner_first_year": money(offer["partner_earns_cents"]),
        "partner_renewal": money(renewal["partner_earns_cents"]),
        "retained": money(offer["retained_cents"]),
    }


def offer_preview(catalog, discount_year, discount_month=None, terms=None, example=True) -> list:
    """Rows of the partner dollar preview: one per plan and billing interval
    in the catalog (app._campaign_catalog()), plus a round $100 example row.

    Columns: list price, customer pays, partner earns in the first year,
    partner earns per renewal, TradeWave retains. Amounts are per PAYMENT
    (monthly rows = one monthly payment). A renewal is paid at the list
    price, because the partner discount lasts 12 months. Raises
    AffiliateError when a discount is outside the terms' range."""
    d_year = parse_discount(discount_year, terms, "Annual customer discount")
    d_month = d_year
    if discount_month is not None and str(discount_month).strip() != "":
        d_month = parse_discount(discount_month, terms, "Monthly customer discount")
    rows = []
    if example:
        rows.append(_offer_row("Example plan", "$100 list price", 10000, d_year, terms))
    for tier, tier_label in PLANS:
        for iv, iv_label in INTERVALS:
            plan = (catalog or {}).get((tier, iv))
            if not plan or not plan.get("list_price_cents"):
                continue
            rows.append(_offer_row(tier_label, iv_label, int(plan["list_price_cents"]),
                                   d_month if iv == "month" else d_year, terms))
    return rows


# ---------------------------------------------------------------------------
# Terms form
# ---------------------------------------------------------------------------

def parse_terms_form(form) -> dict:
    """create_terms() keyword arguments from the 'New terms version' form."""
    errors = []

    def number(field, label, lo, hi):
        raw = (form.get(field) or "").strip()
        try:
            v = Decimal(raw)
            if not v.is_finite():
                raise ValueError(raw)
        except (InvalidOperation, ValueError):
            errors.append("%s must be a number." % label)
            return None
        if not (lo <= v <= hi):
            errors.append("%s must be from %s to %s." % (label, lo, hi))
            return None
        return v

    version = (form.get("version") or "").strip()
    if not re.match(r"^[A-Za-z0-9._-]{2,40}$", version):
        errors.append("Version name must be 2-40 letters, digits, dots, dashes or underscores "
                      "(for example v2-10y).")
    pool = number("pool_pct", "Pool %", 0, 100)
    max_d = number("max_discount_pct", "Maximum customer discount %", 0, 100)
    promo = number("promo_commission_pct", "Promotion commission %", 0, 100)
    renewal = number("renewal_pct", "Renewal commission %", 0, 100)
    if pool is not None and max_d is not None and max_d > pool:
        errors.append("Maximum customer discount cannot be more than the pool.")
    length = (form.get("renewal_length") or "").strip().lower()
    if length not in dict(RENEWAL_LENGTHS):
        errors.append("Renewal length must be 5 years, 10 years or lifetime.")
    try:
        months = int((form.get("activity_rule_months") or "").strip())
        if months < 0 or months > 120:
            raise ValueError
    except ValueError:
        months = None
        errors.append("Activity months must be a whole number from 0 to 120 (0 turns the rule off).")
    if errors:
        raise FormError(errors)
    return {"version": version, "pool_pct": pool, "max_discount_pct": max_d,
            "promo_commission_pct": promo, "renewal_pct": renewal,
            "renewal_years": None if length == "lifetime" else int(length),
            "activity_rule_months": months,
            "notes": (form.get("notes") or "").strip() or None}


# ---------------------------------------------------------------------------
# Campaign form + preview
# ---------------------------------------------------------------------------

def display_timezone() -> str:
    return getattr(config, "ADMIN_DISPLAY_TIMEZONE", "UTC") or "UTC"


def timezone_choices() -> list:
    first = display_timezone()
    return [first] + [z for z in TIMEZONES if z != first]


def _zone(name):
    if not name or name == "UTC":
        return dt.timezone.utc
    from zoneinfo import ZoneInfo
    return ZoneInfo(name)


def local_to_utc(raw, tzname):
    """'2026-11-27T00:00' entered in `tzname` -> aware UTC datetime. Raises
    ValueError on a bad value or an unknown timezone."""
    raw = (raw or "").strip().replace(" ", "T")
    naive = dt.datetime.strptime(raw[:16], _LOCAL_FMT)
    try:
        zone = _zone(tzname)
    except Exception as e:
        raise ValueError("unknown timezone %r" % tzname) from e
    return naive.replace(tzinfo=zone).astimezone(dt.timezone.utc)


def utc_to_local(value, tzname) -> str:
    """Stored UTC datetime -> the 'YYYY-MM-DDTHH:MM' form value in `tzname`."""
    value = afs._utc(value)
    if value is None:
        return ""
    return value.astimezone(_zone(tzname)).strftime(_LOCAL_FMT)


def window_text(value, tzname) -> str:
    """'2026-11-27 00:00 America/New_York (05:00 UTC)' for display."""
    value = afs._utc(value)
    if value is None:
        return "-"
    local = value.astimezone(_zone(tzname))
    return "%s %s (%s UTC)" % (local.strftime("%Y-%m-%d %H:%M"), tzname,
                               value.strftime("%Y-%m-%d %H:%M"))


def _dollars_to_cents(raw):
    """'99' / '99.00' / '$1,299.50' -> cents. None when blank; raises
    ValueError when it is not a dollar amount with at most 2 decimals."""
    s = (raw or "").strip().replace("$", "").replace(",", "")
    if not s:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(raw)
    if not d.is_finite() or d != d.quantize(Decimal("0.01")):
        raise ValueError(raw)
    return int(d * 100)


def price_field(tier, interval) -> str:
    return "price_%s_%s" % (tier, interval)


def _getlist(form, name):
    if hasattr(form, "getlist"):
        return [v for v in form.getlist(name) if v]
    v = form.get(name) or []
    return [v] if isinstance(v, str) else list(v)


def parse_campaign_form(form, catalog) -> dict:
    """Validate the campaign form and return the keyword arguments shared by
    affiliate_service.create_campaign / update_campaign (plus 'code' and
    'tz'). Raises FormError listing every problem in plain English.

    Rules checked here: a name; at least one plan and one billing interval;
    a claim window whose end is after its start; a positive intro price below
    the list price for every eligible plan (fixed-price offers) or a percent
    off above 0 and below 100; an intro length of 1-36 months for monthly
    plans. affiliate_service re-validates on activation."""
    errors = []
    name = (form.get("name") or "").strip()
    if not name:
        errors.append("Give the campaign a name.")
    code = (form.get("code") or "").strip()
    if code:
        code = afs.normalize_code(code)
        try:
            afs.validate_code(code)
        except afs.AffiliateError:
            errors.append("Code may only use A-Z, 0-9, dash or underscore (2-64 characters).")

    tiers = [t for t, _ in PLANS if t in _getlist(form, "tiers")]
    intervals = [i for i, _ in INTERVALS if i in _getlist(form, "intervals")]
    if not tiers:
        errors.append("Pick at least one plan.")
    if not intervals:
        errors.append("Pick at least one billing interval (monthly or annual).")

    tz = (form.get("tz") or display_timezone()).strip()
    starts = ends = None
    try:
        starts = local_to_utc(form.get("starts_local"), tz)
    except ValueError:
        errors.append("Enter the date and time customers can claim FROM.")
    try:
        ends = local_to_utc(form.get("ends_local"), tz)
    except ValueError:
        errors.append("Enter the date and time customers can claim UNTIL.")
    if starts is not None and ends is not None and ends <= starts:
        errors.append("The claim window must end after it starts.")

    offer_type = (form.get("offer_type") or "").strip()
    intro_prices, percent_off = None, None
    if offer_type == "price":
        intro_prices = {}
        for tier in tiers:
            for iv in intervals:
                label = "%s %s" % (PLAN_LABEL[tier], INTERVAL_LABEL[iv].lower())
                plan = (catalog or {}).get((tier, iv))
                if not plan or not plan.get("list_price_cents"):
                    errors.append("No Stripe price is set up for %s." % label)
                    continue
                try:
                    cents = _dollars_to_cents(form.get(price_field(tier, iv)))
                except ValueError:
                    errors.append("Intro price for %s must be a dollar amount, for example 99 or 99.00."
                                  % label)
                    continue
                if cents is None:
                    errors.append("Enter an intro price for %s." % label)
                elif cents <= 0:
                    errors.append("Intro price for %s must be more than $0." % label)
                elif cents >= int(plan["list_price_cents"]):
                    errors.append("Intro price for %s must be below the regular price of %s."
                                  % (label, money(plan["list_price_cents"])))
                else:
                    intro_prices[afs.offer_key(tier, iv)] = cents
    elif offer_type == "percent":
        try:
            percent_off = Decimal((form.get("percent_off") or "").strip())
            if not percent_off.is_finite() or not (0 < percent_off < 100):
                raise InvalidOperation
        except InvalidOperation:
            percent_off = None
            errors.append("Percent off must be more than 0 and less than 100.")
        for tier in tiers:
            for iv in intervals:
                plan = (catalog or {}).get((tier, iv))
                if not plan or not plan.get("list_price_cents"):
                    errors.append("No Stripe price is set up for %s %s."
                                  % (PLAN_LABEL[tier], INTERVAL_LABEL[iv].lower()))
    else:
        errors.append("Choose the offer type: a fixed intro price or a percent off.")

    intro_months = 12
    if "month" in intervals:
        try:
            intro_months = int((form.get("intro_months") or "12").strip())
            if not (1 <= intro_months <= 36):
                raise ValueError
        except ValueError:
            errors.append("Intro length for monthly plans must be 1 to 36 months.")
    if errors:
        raise FormError(errors)
    return {"name": name, "code": code or None, "tiers": tiers, "intervals": intervals,
            "starts_at": starts, "ends_at": ends, "offer_type": offer_type,
            "intro_prices": intro_prices, "percent_off": percent_off,
            "intro_months": intro_months, "new_customers_only": True,
            "notes": (form.get("notes") or "").strip() or None, "tz": tz}


def campaign_form_values(campaign=None, form=None, tzname=None) -> dict:
    """What the campaign form shows: the submitted values when re-rendering
    after a POST, else the stored campaign, else the blank defaults."""
    tz = tzname or display_timezone()
    if form is not None:
        return {
            "name": form.get("name") or "", "code": form.get("code") or "",
            "tiers": _getlist(form, "tiers"), "intervals": _getlist(form, "intervals"),
            "tz": form.get("tz") or tz,
            "starts_local": form.get("starts_local") or "",
            "ends_local": form.get("ends_local") or "",
            "offer_type": form.get("offer_type") or "price",
            "prices": {afs.offer_key(t, i): (form.get(price_field(t, i)) or "")
                       for t, _ in PLANS for i, _ in INTERVALS},
            "percent_off": form.get("percent_off") or "",
            "intro_months": form.get("intro_months") or "12",
            "notes": form.get("notes") or "",
        }
    if campaign is None:
        return {"name": "", "code": "", "tiers": [], "intervals": ["year"], "tz": tz,
                "starts_local": "", "ends_local": "", "offer_type": "price", "prices": {},
                "percent_off": "", "intro_months": "12", "notes": ""}
    return {
        "name": campaign.name or "", "code": campaign.code or "",
        "tiers": list(campaign.tiers or []), "intervals": list(campaign.billing_intervals or []),
        "tz": tz,
        "starts_local": utc_to_local(campaign.starts_at, tz),
        "ends_local": utc_to_local(campaign.ends_at, tz),
        "offer_type": campaign.offer_type or "price",
        "prices": {k: format(Decimal(int(v)) / 100, ".2f")
                   for k, v in (campaign.intro_prices or {}).items()},
        "percent_off": pct(campaign.percent_off),
        "intro_months": str(campaign.intro_months or 12),
        "notes": campaign.notes or "",
    }


def intro_length_label(interval, intro_months) -> str:
    """How long the intro price lasts - separate from the claim window."""
    if interval == "year":
        return "First year (1 annual payment)"
    n = int(intro_months or 12)
    return "First %d monthly payment%s" % (n, "" if n == 1 else "s")


def campaign_preview(spec, catalog, terms=None, partner_discounts=None) -> list:
    """The money preview of a campaign, one row per eligible plan + interval.

    spec: the dict from parse_campaign_form (or a PromoCampaign row). Each
    row carries:
      direct    customer pays the intro price, partner $0, TradeWave keeps it all
      referred  customer pays the intro price, the partner earns
                promo_commission_pct of what was paid (preview_promo)
      winners   for a partner offering each of `partner_discounts` (default
                0% and the terms' maximum): which single offer the customer
                gets. The lower first-period price wins, a tie goes to the
                partner discount, offers never stack - the same rule as
                affiliate_service.resolve_checkout_offer.
    """
    t = afs._terms_of(terms)
    get = spec.get if isinstance(spec, dict) else (lambda k, d=None: getattr(spec, k, d))
    intervals = get("intervals") or get("billing_intervals") or []
    camp = SimpleNamespace(
        tiers=list(get("tiers") or []), billing_intervals=list(intervals),
        offer_type=get("offer_type"), intro_prices=get("intro_prices") or {},
        percent_off=get("percent_off"))
    if partner_discounts is None:
        partner_discounts = (Decimal("0"), Decimal(str(t.max_discount_pct)))
    rows = []
    for tier, tier_label in PLANS:
        for iv, iv_label in INTERVALS:
            plan = (catalog or {}).get((tier, iv))
            if not plan or not plan.get("list_price_cents"):
                continue
            lp = int(plan["list_price_cents"])
            price = afs.campaign_first_period_cents(camp, tier, iv, lp)
            if price is None:
                continue
            promo = afs.preview_promo(price, lp, terms)
            winners = []
            for d in partner_discounts:
                regular = afs.preview_offer(lp, d, terms)
                campaign_wins = price < regular["customer_pays_cents"]
                chosen = promo if campaign_wins else regular
                winners.append({
                    "partner_discount_pct": pct(d),
                    "partner_price_cents": regular["customer_pays_cents"],
                    "partner_price": money(regular["customer_pays_cents"]),
                    "campaign_price": money(price),
                    "winner": "campaign" if campaign_wins else "partner",
                    "winner_label": ("Campaign price" if campaign_wins else "Partner discount"),
                    "rule": ("Promotion rule: %s%% of what the customer paid"
                             % pct(promo["commission_rate_pct"]) if campaign_wins else
                             "Pool rule: %s%% of the list price" % pct(regular["commission_rate_pct"])),
                    "customer_pays_cents": chosen["customer_pays_cents"],
                    "partner_earns_cents": chosen["partner_earns_cents"],
                    "retained_cents": chosen["retained_cents"],
                    "customer_pays": money(chosen["customer_pays_cents"]),
                    "partner_earns": money(chosen["partner_earns_cents"]),
                    "retained": money(chosen["retained_cents"]),
                })
            rows.append({
                "tier": tier, "interval": iv, "plan": tier_label, "interval_label": iv_label,
                "list_price_cents": lp, "list_price": money(lp),
                "intro_price_cents": price, "intro_price": money(price),
                "renewal_price_cents": lp, "renewal_price": money(lp),
                "intro_length": intro_length_label(iv, get("intro_months")),
                "direct": {"customer_pays_cents": price, "partner_earns_cents": 0,
                           "retained_cents": price, "customer_pays": money(price),
                           "partner_earns": money(0), "retained": money(price)},
                "referred": {"customer_pays_cents": promo["customer_pays_cents"],
                             "partner_earns_cents": promo["partner_earns_cents"],
                             "retained_cents": promo["retained_cents"],
                             "commission_rate_pct": pct(promo["commission_rate_pct"]),
                             "customer_pays": money(promo["customer_pays_cents"]),
                             "partner_earns": money(promo["partner_earns_cents"]),
                             "retained": money(promo["retained_cents"])},
                "winners": winners,
            })
    return rows


def campaign_phase(campaign, now=None) -> str:
    """Plain status of a campaign right now."""
    now = afs._utc(now) or dt.datetime.now(dt.timezone.utc)
    if campaign.status == "archived":
        return "Archived"
    if campaign.status == "draft":
        return "Draft - not live"
    if now < afs._utc(campaign.starts_at):
        return "Scheduled"
    if now >= afs._utc(campaign.ends_at):
        return "Ended"
    return "Live - customers can claim"


def campaign_offer_text(campaign) -> str:
    if campaign.offer_type == "percent":
        return "%s%% off" % pct(campaign.percent_off)
    parts = []
    for tier, tier_label in PLANS:
        for iv, iv_label in INTERVALS:
            v = (campaign.intro_prices or {}).get(afs.offer_key(tier, iv))
            if v is not None and tier in (campaign.tiers or []) \
                    and iv in (campaign.billing_intervals or []):
                parts.append("%s %s %s" % (tier_label, iv_label.lower(), money(v)))
    return ", ".join(parts) or "-"


# ---------------------------------------------------------------------------
# Payout rules: minimum, tax form, line sync
# ---------------------------------------------------------------------------

def payout_minimum_cents() -> int:
    return int(getattr(config, "AFFILIATE_PAYOUT_MINIMUM_CENTS", 5000) or 0)


def payout_below_minimum(payout) -> bool:
    """A pending month that is positive but under the payout minimum."""
    amount = Decimal(str(payout.commission_amount or 0))
    return 0 <= amount < afs.payout_minimum()


def payout_block_reason(payout, affiliate=None):
    """Why this payout row may NOT be marked paid, or None when it may.
    Order: tax form (a condition of payment), negative month, payout minimum.
    The minimum does not apply to a partner terminated WITHOUT cause: their
    final balance is paid whatever its size (agreement 5.3 / 11.3)."""
    aff = affiliate if affiliate is not None else getattr(payout, "affiliate", None)
    if aff is not None and not getattr(aff, "tax_form_received_at", None):
        return ("Can't mark paid: %s has no tax form on file (W-9 / W-8BEN / "
                "W-8BEN-E). Record it on the affiliate first (Affiliates -> edit -> "
                "Tax form + Tax form received)." % aff.code)
    amount = Decimal(str(payout.commission_amount or 0))
    if amount < 0:
        return ("This row is negative (refunds or chargebacks were more than sales). It is "
                "carried into the affiliate's next payable month automatically - leave it "
                "pending.")
    if amount > 0 and aff is not None and afs.final_balance_due(aff):
        return None
    if amount < afs.payout_minimum():
        return ("Can't mark paid: %s is below the %s payout minimum. Leave it pending - it "
                "is carried into the affiliate's next month automatically."
                % (money_amount(amount), money(payout_minimum_cents())))
    return None


def payout_note(payout) -> str:
    """Short status note for a payout row in the admin list."""
    status = getattr(payout, "status", None)
    ref = getattr(payout, "external_ref", None) or ""
    amount = Decimal(str(payout.commission_amount or 0))
    notes = []
    if status == "void" and ref.startswith("carried:"):
        notes.append("Carried into %s" % ref.split(":", 1)[1])
    elif status == "void" and ref == FORFEIT_REF:
        notes.append("Forfeited - terminated for cause")
    elif status == "pending":
        if amount < 0:
            notes.append("Negative, carried into the next payable month")
        elif amount < afs.payout_minimum():
            aff = getattr(payout, "affiliate", None)
            if amount > 0 and aff is not None and afs.final_balance_due(aff):
                notes.append("Final balance - payable below the minimum (partner terminated)")
            else:
                notes.append("Below minimum, carried")
    carry_in = (getattr(payout, "detail", None) or {}).get("carry_in") or []
    if carry_in:
        total = sum((Decimal(str(c.get("amount") or 0)) for c in carry_in), Decimal("0"))
        notes.append("Includes %s carried from %s" % (
            money_amount(total), ", ".join(str(c.get("period", ""))[:7] for c in carry_in)))
    return "; ".join(notes)


def payout_line_totals(session, payout_ids) -> dict:
    """{payout_id: {"count", "amount" (Decimal, rounded to cents), "paid",
    "pending"}} from the commission ledger, for the payout list."""
    from sqlalchemy import func
    from models import AffiliateCommissionLine as L
    ids = [i for i in payout_ids if i is not None]
    out = {}
    if not ids:
        return out
    for pid, state, count, amount in (
            session.query(L.payout_id, L.state, func.count(L.id), func.sum(L.amount))
            .filter(L.payout_id.in_(ids)).group_by(L.payout_id, L.state).all()):
        row = out.setdefault(pid, {"count": 0, "amount": Decimal("0"), "paid": 0, "pending": 0})
        row["count"] += int(count or 0)
        row["amount"] += Decimal(str(amount or 0))
        if state in ("paid", "pending"):
            row[state] += int(count or 0)
    for row in out.values():
        row["amount"] = row["amount"].quantize(Decimal("0.01"))
    return out


def payout_lines_text(totals) -> str:
    if not totals or not totals.get("count"):
        return "No ledger lines"
    text = "%d line%s, %s" % (totals["count"], "" if totals["count"] == 1 else "s",
                              money_amount(totals["amount"]))
    if totals.get("paid"):
        text += " (%d paid)" % totals["paid"]
    return text


def sync_paid_lines(session) -> int:
    """After a payout row is marked paid: flip its ledger lines (and the lines
    of rows carried into it) to 'paid'. Commits. Returns lines moved."""
    moved = afs.sync_line_states(session)
    session.commit()
    return moved


def held_summary(session) -> list:
    """Held commission per partner and currency: [{code, name, status,
    currency, count, amount, reason}] - visible so nothing held is forgotten."""
    from sqlalchemy import func
    from models import Affiliate, AffiliateCommissionLine as L
    rows = (session.query(Affiliate.code, Affiliate.name, Affiliate.status, L.currency,
                          L.hold_reason, func.count(L.id), func.sum(L.amount))
            .join(Affiliate, Affiliate.id == L.affiliate_id)
            .filter(L.state == "held")
            .group_by(Affiliate.code, Affiliate.name, Affiliate.status, L.currency, L.hold_reason)
            .order_by(Affiliate.code).all())
    return [{"code": code, "name": name, "status": status, "currency": currency,
             "count": int(count or 0),
             "amount": Decimal(str(amount or 0)).quantize(Decimal("0.01")),
             "reason": HOLD_REASON_LABELS.get(reason, reason or "-")}
            for code, name, status, currency, reason, count, amount in rows]


# ---------------------------------------------------------------------------
# Partner actions (Change terms page)
# ---------------------------------------------------------------------------

def apply_partner_discounts(session, affiliate, raw_year, raw_month, actor) -> list:
    """Admin change of a partner's customer discount. Discount-only, inside
    the terms' cap: calls set_partner_discount for each interval that
    changed - the partner is NOT paused and does NOT re-sign. `raw_month`
    blank means "same as annual". Returns the AffiliateDiscountChange rows.
    Raises AffiliateError (nothing is changed when validation fails)."""
    terms = afs.terms_for(session, affiliate)
    new_year = parse_discount(raw_year, terms, "Annual customer discount")
    blank_month = raw_month is None or str(raw_month).strip() == ""
    new_month = new_year if blank_month else parse_discount(
        raw_month, terms, "Monthly customer discount")
    changes = []
    if Decimal(str(affiliate.discount_pct)) != new_year:
        changes.append(afs.set_partner_discount(
            session, affiliate, new_year, interval="year", actor=actor, enforce_cooldown=False))
    current_month = afs.effective_discount_pct(affiliate, "month")
    if current_month is None or Decimal(str(current_month)) != new_month:
        changes.append(afs.set_partner_discount(
            session, affiliate, new_month, interval="month", actor=actor, enforce_cooldown=False))
    return changes


def terminate_partner_for_cause(session, affiliate, reason, actor):
    """Terminate for cause. A written reason is REQUIRED: it is recorded on
    the partner and in the audit log, and it forfeits unpaid commission."""
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise afs.AffiliateError(
            "Write the reason for the termination (at least 10 characters). It is recorded "
            "permanently and it forfeits the partner's unpaid commission.")
    if getattr(affiliate, "terminated_for_cause", False):
        raise afs.AffiliateError("%s is already terminated for cause." % affiliate.code)
    # Any signing link already issued must stop working.
    affiliate.agreement_token_version = (affiliate.agreement_token_version or 0) + 1
    # Forfeits pending payout rows and held / payable lines, and commits.
    return afs.terminate_for_cause(session, affiliate, reason, actor=actor)


FORFEIT_REF = afs.FORFEIT_REF
forfeit_unpaid = afs.forfeit_unpaid


def held_line_count(session, affiliate) -> int:
    from models import AffiliateCommissionLine as L
    return (session.query(L).filter(L.affiliate_id == affiliate.id, L.state == "held").count())


def require_resign(session, affiliate):
    """Agreement change: clear the signature so the partner must sign again.
    The partner is PAUSED until they do (their link and code stop applying to
    new customers; commission that accrues meanwhile is held, not lost)."""
    import affiliate_agreement as agr
    import promo_service as ps
    affiliate.agreement_signed_name = None
    affiliate.agreement_signed_at = None
    affiliate.agreement_signed_ip = None
    affiliate.agreement_signed_user_agent = None
    affiliate.agreement_snapshot = None
    affiliate.agreement_version = agr.AGREEMENT_VERSION
    affiliate.agreement_token_version = (affiliate.agreement_token_version or 0) + 1
    affiliate.status = "paused"
    try:
        ps.set_promo_active(affiliate, False)
    except Exception:
        session.rollback()
        raise
    session.commit()


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

_CSS = """
 body{font:14px/1.6 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2a44;background:#f4f5f9;margin:0;}
 .wrap{max-width:1040px;margin:0 auto;padding:24px 20px 60px;}
 nav a{margin-right:14px;} a{color:#5b4bdb;}
 h1{font-size:22px;margin:14px 0 4px;} h2{font-size:17px;margin:0 0 8px;color:#3a32a8;}
 h3{font-size:14px;margin:18px 0 6px;}
 .doc{background:#fff;border:1px solid #e3e6ee;border-radius:12px;padding:22px 26px;margin:16px 0;}
 .flash{border-radius:8px;padding:10px 14px;margin:12px 0;font-size:13px;border:1px solid #e3e6ee;}
 .flash-success{background:#e7f6ec;color:#0a7d28;border-color:#bfe6cb;}
 .flash-warning{background:#fffbe6;color:#8a6d00;border-color:#f0e6b0;}
 .flash-error,.flash-danger{background:#fdeaea;color:#b00020;border-color:#f3c6c6;}
 .flash-info{background:#eef2ff;color:#3a32a8;border-color:#cfd6f5;}
 table{border-collapse:collapse;width:100%;margin-top:8px;}
 th,td{border:1px solid #e1e4ec;padding:7px 10px;text-align:left;font-size:13px;vertical-align:top;}
 th{background:#f5f5f9;} td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;}
 label{display:block;margin:12px 0 0;font-size:13px;font-weight:600;color:#3a3a55;}
 label.inline{display:inline-block;margin:6px 16px 0 0;font-weight:500;}
 input[type=number],input[type=text],input[type=datetime-local],select,textarea{margin-top:4px;padding:7px 9px;border:1px solid #cfd3e0;border-radius:7px;font-size:14px;font-family:inherit;}
 input[type=number]{width:120px;} input[type=text]{width:320px;max-width:100%;} textarea{width:100%;box-sizing:border-box;}
 .note{font-size:13px;color:#555;background:#f7f7fb;border:1px solid #e6e6ef;border-radius:8px;padding:10px 14px;margin:12px 0;}
 .warn{font-size:13px;color:#8a6d00;background:#fffbe6;border:1px solid #f0e6b0;border-radius:8px;padding:10px 14px;margin:12px 0;}
 .muted{color:#666;font-size:13px;} .err{color:#b00020;font-size:13px;}
 button,.btn{display:inline-block;margin-top:14px;font-size:14px;font-weight:600;border:1px solid #4338ca;background:#4f46e5;color:#fff;border-radius:7px;padding:8px 16px;cursor:pointer;text-decoration:none;}
 button:hover,.btn:hover{background:#4338ca;}
 button.secondary{background:#fff;color:#4338ca;} button.danger{background:#b00020;border-color:#8f001a;}
 button.small{margin-top:0;padding:4px 10px;font-size:12px;}
 .grid{display:flex;gap:24px;flex-wrap:wrap;} .grid>div{flex:1;min-width:240px;}
 .pill{display:inline-block;font-size:12px;font-weight:700;padding:1px 8px;border-radius:20px;background:#eef2ff;color:#3a32a8;}
 fieldset{border:1px solid #e3e6ee;border-radius:10px;margin:16px 0 0;padding:10px 16px 14px;}
 legend{font-weight:700;font-size:13px;padding:0 6px;color:#3a32a8;}
"""

_HEAD = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{{ title }}</title><style>""" + _CSS + """</style></head><body><div class="wrap">
""" + affiliate_nav.NAV_HTML + """
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% if msgs %}{% for cat, m in msgs %}<div class="flash flash-{{ cat }}">{{ m }}</div>{% endfor %}{% endif %}
{% endwith %}
{% if errors %}<div class="flash flash-error"><strong>Please fix:</strong><ul style="margin:4px 0 0 18px;padding:0">
{% for e in errors %}<li>{{ e }}</li>{% endfor %}</ul></div>{% endif %}
"""
_FOOT = "</div></body></html>"

# The navigation at the top of every page is the ONE shared partner-program
# sub-nav (web/affiliate_nav.py).
# The live dollar-preview widget is templates/admin/_affiliate_offer_preview.html
# (shared with the Flask-Admin affiliate create form).
OFFER_PREVIEW_WIDGET = '{% include "admin/_affiliate_offer_preview.html" %}'

_TERMS_TMPL = _HEAD + """
<h1>Partner terms</h1>
<p class="muted">A terms version sets the commission rules of the partner agreement. Versions are never edited:
to change the rules, create a new version and assign it to a partner.</p>
<div class="note"><strong>Terms apply to future customers only.</strong> Every referred customer is stamped with the
terms version in force when their checkout started. Assigning a different version to a partner changes only customers
who check out after that. Customers they already referred, and commission already recorded, keep the version they started with.</div>

<div class="doc"><h2>Terms versions</h2>
<table>
 <tr><th>Version</th><th class="num">Pool %</th><th class="num">Max customer discount %</th>
   <th class="num">Promotion commission %</th><th class="num">Renewal commission %</th>
   <th>Renewal length</th><th class="num">Activity months</th><th class="num">Partners</th><th>Notes</th></tr>
 {% for t in terms %}
 <tr><td><strong>{{ t.version }}</strong>{% if t.version == default_version %} <span class="pill">default</span>{% endif %}</td>
   <td class="num">{{ pct(t.pool_pct) }}</td><td class="num">{{ pct(t.max_discount_pct) }}</td>
   <td class="num">{{ pct(t.promo_commission_pct) }}</td><td class="num">{{ pct(t.renewal_pct) }}</td>
   <td>{{ renewal_length_label(t) }}</td><td class="num">{{ t.activity_rule_months }}</td>
   <td class="num">{{ counts.get(t.id, 0) }}</td><td>{{ t.notes or '' }}</td></tr>
 {% else %}<tr><td colspan="9">No terms versions yet. Run the database migration, or create one below.</td></tr>
 {% endfor %}
</table>
<p class="muted">Pool: the share of the list price split between the customer discount and the partner
(partner earns pool minus discount, of the list price). Activity months: renewal commission is paid only while the partner
has brought at least one new paying customer in this many trailing months (0 turns the rule off).</p>
</div>

<div class="doc"><h2>New terms version</h2>
<form method="post" action="{{ url_for('affiliate_terms.create') }}">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <label>Version name <input type="text" name="version" value="{{ f.get('version', '') }}" placeholder="for example v2-10y-custom" required></label>
  <div class="grid">
   <div><label>Pool % <input type="number" step="0.01" min="0" max="100" name="pool_pct" value="{{ f.get('pool_pct', '50') }}" required></label></div>
   <div><label>Maximum customer discount % <input type="number" step="0.01" min="0" max="100" name="max_discount_pct" value="{{ f.get('max_discount_pct', '25') }}" required></label></div>
   <div><label>Promotion commission % <input type="number" step="0.01" min="0" max="100" name="promo_commission_pct" value="{{ f.get('promo_commission_pct', '50') }}" required></label></div>
   <div><label>Renewal commission % <input type="number" step="0.01" min="0" max="100" name="renewal_pct" value="{{ f.get('renewal_pct', '25') }}" required></label></div>
  </div>
  <div class="grid">
   <div><label>Renewal length
     <select name="renewal_length">{% for v, label in renewal_lengths %}
       <option value="{{ v }}"{% if f.get('renewal_length', '5') == v %} selected{% endif %}>{{ label }}</option>{% endfor %}
     </select></label></div>
   <div><label>Activity months <input type="number" step="1" min="0" max="120" name="activity_rule_months" value="{{ f.get('activity_rule_months', '12') }}" required></label></div>
  </div>
  <label>Notes (optional) <input type="text" name="notes" value="{{ f.get('notes', '') }}"></label>
  <button type="submit">Create terms version</button>
</form></div>

<div class="doc"><h2>Which version each partner is on</h2>
<table>
 <tr><th>Code</th><th>Partner</th><th>Status</th><th>Terms version</th><th class="num">Customer discount</th><th></th></tr>
 {% for a in affiliates %}
 <tr><td><strong>{{ a.code }}</strong></td><td>{{ a.name }}</td><td>{{ a.status }}</td>
   <td>{{ a.terms.version if a.terms else default_version ~ ' (default)' }}</td>
   <td class="num">{{ pct(a.discount_pct) }}%{% if a.discount_pct_monthly is not none %} / {{ pct(a.discount_pct_monthly) }}% monthly{% endif %}</td>
   <td><a href="{{ url_for('affiliate_change_terms.index', id=a.id) }}">Change terms</a></td></tr>
 {% else %}<tr><td colspan="6">No partners yet.</td></tr>
 {% endfor %}
</table></div>
""" + _FOOT

_CAMPAIGN_LIST_TMPL = _HEAD + """
<h1>Promotion campaigns</h1>
<p class="muted">A campaign is a company-wide intro offer for new customers. A direct sale pays no commission.
A sale referred by a partner pays the partner a share of what the customer actually paid. A customer never gets a campaign
and a partner discount together: the lower first-period price wins.</p>
<p><a class="btn" href="{{ url_for('promo_campaigns.edit') }}">New campaign</a></p>
<div class="doc">
<table>
 <tr><th>Campaign</th><th>Status</th><th>Plans</th><th>Customers can claim</th><th>Intro offer</th><th>Intro price lasts</th><th></th></tr>
 {% for c in campaigns %}
 <tr><td><strong>{{ c.name }}</strong><br><span class="muted">{{ c.code }}</span></td>
   <td>{{ phase(c) }}</td>
   <td>{% for t in c.tiers %}{{ plan_label.get(t, t) }}{% if not loop.last %}, {% endif %}{% endfor %}<br>
     <span class="muted">{% for i in c.billing_intervals %}{{ interval_label.get(i, i) }}{% if not loop.last %}, {% endif %}{% endfor %}</span></td>
   <td>From {{ window_text(c.starts_at, tz) }}<br>Until {{ window_text(c.ends_at, tz) }}</td>
   <td>{{ offer_text(c) }}</td>
   <td>{% for i in c.billing_intervals %}{{ interval_label.get(i, i) }}: {{ intro_length_label(i, c.intro_months) }}{% if not loop.last %}<br>{% endif %}{% endfor %}</td>
   <td><a href="{{ url_for('promo_campaigns.edit', id=c.id) }}">Edit / preview</a>
     {% if c.status != 'archived' %}
     <form method="post" action="{{ url_for('promo_campaigns.archive') }}" style="margin-top:6px"
           onsubmit="return confirm('Archive this campaign? New customers can no longer claim it. Customers who already claimed keep their intro price.');">
       <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ c.id }}">
       <button class="small secondary" type="submit">Archive</button></form>{% endif %}</td></tr>
 {% else %}<tr><td colspan="7">No campaigns yet.</td></tr>
 {% endfor %}
</table>
<p class="muted">Times are shown in {{ tz }} with the UTC time in brackets. They are stored in UTC.</p>
</div>
""" + _FOOT

_CAMPAIGN_FORM_TMPL = _HEAD + """
<h1>{% if campaign %}Edit campaign - {{ campaign.name }}{% else %}New campaign{% endif %}</h1>
{% if campaign %}<p class="muted">Code {{ campaign.code }} &middot; {{ phase(campaign) }}</p>{% endif %}
{% if catalog_error %}<div class="warn">Could not read the plan prices from Stripe ({{ catalog_error }}). Prices and the preview are unavailable until that works.</div>{% endif %}
{% if campaign and campaign.status == 'active' %}<div class="warn">This campaign is active. Changing the plans, the claim window or the offer creates new Stripe coupons for future customers. Customers who already claimed keep the intro price they got.</div>{% endif %}

<form method="post" action="{{ url_for('promo_campaigns.edit', id=campaign.id) if campaign else url_for('promo_campaigns.edit') }}" id="campaign-form">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<div class="doc">
  <h2>1. Campaign</h2>
  <label>Name <input type="text" name="name" value="{{ v.name }}" placeholder="for example Black Friday 2026" required></label>
  <label>Code {% if campaign %}<span class="muted">(cannot be changed)</span>{% else %}<span class="muted">(optional - made from the name if left blank)</span>{% endif %}
    <input type="text" name="code" value="{{ v.code }}" {% if campaign %}readonly{% endif %}></label>

  <fieldset><legend>Who can claim</legend>
    <div><strong>Plans</strong><br>
    {% for t, label in plans %}<label class="inline"><input type="checkbox" name="tiers" value="{{ t }}"{% if t in v.tiers %} checked{% endif %}> {{ label }}</label>{% endfor %}</div>
    <div style="margin-top:8px"><strong>Billing</strong><br>
    {% for i, label in intervals %}<label class="inline"><input type="checkbox" name="intervals" value="{{ i }}"{% if i in v.intervals %} checked{% endif %}> {{ label }}</label>{% endfor %}</div>
    <div style="margin-top:8px"><label class="inline"><input type="checkbox" checked disabled> New customers only</label>
      <span class="muted">Always on. Existing subscribers and founders cannot claim a campaign.</span></div>
  </fieldset>

  <fieldset><legend>Customers can claim from / until (the claim window)</legend>
    <p class="muted" style="margin:0">When a new customer may START a checkout at the intro price. This is not how long the intro price lasts.</p>
    <div class="grid">
      <div><label>Customers can claim from <input type="datetime-local" name="starts_local" value="{{ v.starts_local }}" required></label></div>
      <div><label>Customers can claim until <input type="datetime-local" name="ends_local" value="{{ v.ends_local }}" required></label></div>
      <div><label>Timezone of these times
        <select name="tz">{% for z in timezones %}<option value="{{ z }}"{% if z == v.tz %} selected{% endif %}>{{ z }}</option>{% endfor %}</select></label></div>
    </div>
    <p class="muted">Times are entered in the timezone picked here and stored in UTC.
      {% if window %}This window is <strong>{{ window.starts }}</strong> to <strong>{{ window.ends }}</strong>.{% endif %}</p>
  </fieldset>
</div>

<div class="doc">
  <h2>2. Intro offer</h2>
  <label class="inline"><input type="radio" name="offer_type" value="price"{% if v.offer_type != 'percent' %} checked{% endif %}> Fixed intro price per plan</label>
  <label class="inline"><input type="radio" name="offer_type" value="percent"{% if v.offer_type == 'percent' %} checked{% endif %}> Percent off the regular price</label>

  <h3>Fixed intro price (used when "Fixed intro price" is picked)</h3>
  <table>
    <tr><th>Plan</th><th>Billing</th><th>Intro price (USD, before tax)</th><th>Then renews at the regular price</th></tr>
    {% for t, tlabel in plans %}{% for i, ilabel in intervals %}
    <tr><td>{{ tlabel }}</td><td>{{ ilabel }}</td>
      <td>$ <input type="text" style="width:110px" name="{{ price_field(t, i) }}" value="{{ v.prices.get(t ~ ':' ~ i, '') }}" placeholder="for example 99">
        <span class="muted">{{ 'for the first year' if i == 'year' else 'per month during the intro' }}</span></td>
      <td>{% if catalog.get((t, i)) %}{{ money(catalog[(t, i)].list_price_cents) }} {{ 'per year' if i == 'year' else 'per month' }}{% else %}<span class="err">no Stripe price</span>{% endif %}</td></tr>
    {% endfor %}{% endfor %}
  </table>
  <p class="muted">Only the plans and billing intervals ticked above are used. Leave the others blank.</p>

  <h3>Percent off (used when "Percent off" is picked)</h3>
  <label>Percent off the regular price <input type="number" step="0.01" min="0" max="100" name="percent_off" value="{{ v.percent_off }}"> %</label>

  <fieldset><legend>Intro price lasts</legend>
    <p class="muted" style="margin:0">How long a customer who claimed keeps the intro price. After that they pay the regular price.</p>
    <p style="margin:8px 0 0"><strong>Annual plans:</strong> the first year (1 annual payment). The second year renews at the regular price.</p>
    <label><strong>Monthly plans:</strong> the first <input type="number" step="1" min="1" max="36" name="intro_months" value="{{ v.intro_months }}" style="width:80px"> monthly payments</label>
  </fieldset>
  <label>Notes (internal, optional) <textarea name="notes" rows="2">{{ v.notes }}</textarea></label>
</div>

{% if preview %}
<div class="doc" id="preview-panel">
  <h2>3. Preview - check the money before you save</h2>
  <p>Customers can claim from <strong>{{ window.starts }}</strong> until <strong>{{ window.ends }}</strong>.</p>

  <h3>Direct sale (no partner)</h3>
  <table>
    <tr><th>Plan</th><th>Billing</th><th class="num">Regular price</th><th class="num">Customer pays (intro)</th>
      <th>Intro price lasts</th><th class="num">Then renews at</th><th class="num">Partner earns</th><th class="num">TradeWave retains</th></tr>
    {% for r in preview %}<tr><td>{{ r.plan }}</td><td>{{ r.interval_label }}</td><td class="num">{{ r.list_price }}</td>
      <td class="num">{{ r.direct.customer_pays }}</td><td>{{ r.intro_length }}</td><td class="num">{{ r.renewal_price }}</td>
      <td class="num">{{ r.direct.partner_earns }}</td><td class="num">{{ r.direct.retained }}</td></tr>{% endfor %}
  </table>

  <h3>Referred sale (the customer came from a partner)</h3>
  <table>
    <tr><th>Plan</th><th>Billing</th><th class="num">Customer pays (intro)</th>
      <th class="num">Partner earns</th><th class="num">TradeWave retains</th></tr>
    {% for r in preview %}<tr><td>{{ r.plan }}</td><td>{{ r.interval_label }}</td>
      <td class="num">{{ r.referred.customer_pays }}</td>
      <td class="num">{{ r.referred.partner_earns }} <span class="muted">({{ r.referred.commission_rate_pct }}% of what the customer paid)</span></td>
      <td class="num">{{ r.referred.retained }}</td></tr>{% endfor %}
  </table>
  <p class="muted">Amounts are per payment during the intro, before tax. Renewals at the regular price follow the partner's renewal terms.</p>

  <h3>Which offer wins with a partner code</h3>
  <p class="muted">The customer gets one offer only: whichever first-period price is lower. A tie goes to the partner discount. Offers never stack.</p>
  <table>
    <tr><th>Plan</th><th>Billing</th><th>Partner's customer discount</th><th class="num">Partner price</th><th class="num">Campaign price</th>
      <th>Winner</th><th class="num">Customer pays</th><th class="num">Partner earns</th><th class="num">TradeWave retains</th></tr>
    {% for r in preview %}{% for w in r.winners %}
    <tr><td>{{ r.plan }}</td><td>{{ r.interval_label }}</td><td>{{ w.partner_discount_pct }}% partner</td>
      <td class="num">{{ w.partner_price }}</td><td class="num">{{ w.campaign_price }}</td>
      <td><strong>{{ w.winner_label }}</strong><br><span class="muted">{{ w.rule }}</span></td>
      <td class="num">{{ w.customer_pays }}</td><td class="num">{{ w.partner_earns }}</td><td class="num">{{ w.retained }}</td></tr>
    {% endfor %}{% endfor %}
  </table>

  <div id="save-buttons">
    <button type="submit" name="action" value="save_draft" class="secondary">Save as draft (not live)</button>
    <button type="submit" name="action" value="activate">Save and activate</button>
    <p class="muted">"Save and activate" creates the Stripe coupons. The campaign goes live when the claim window starts.</p>
  </div>
  <p id="stale-note" class="warn" style="display:none">You changed the form. Preview again before saving.</p>
</div>
{% endif %}
<button type="submit" name="action" value="preview"{% if preview %} class="secondary"{% endif %}>{{ 'Preview again' if preview else 'Preview' }}</button>
<a href="{{ url_for('promo_campaigns.index') }}" style="margin-left:14px">Cancel</a>
</form>
<script>
(function(){
  var form = document.getElementById('campaign-form'), save = document.getElementById('save-buttons');
  if(!form || !save) return;
  function stale(){ save.style.display = 'none'; document.getElementById('stale-note').style.display = 'block'; }
  form.addEventListener('input', stale); form.addEventListener('change', stale);
})();
</script>
""" + _FOOT

_CHANGE_TERMS_TMPL = _HEAD + """
{% if not found %}
  <div class="doc">Affiliate not found. <a href="/admin/affiliate/">Back to affiliates</a></div>
{% else %}
<h1>Change terms - {{ aff.code }}</h1>
<p class="muted">{{ aff.name }} &middot; status <strong>{{ aff.status }}</strong>
  &middot; {{ 'signed ' ~ aff.agreement_signed_at.strftime('%Y-%m-%d') if aff.agreement_signed_at else 'agreement not signed' }}
  &middot; {{ ref_count }} referred customer(s)</p>
<div class="note"><strong>Changes apply to future customers only.</strong> A customer keeps the discount and the terms that
were in force when their checkout started. Nothing on this page changes commission that is already recorded.</div>

{% if aff.status == 'terminated' %}
  <div class="doc"><h2>This partner is terminated</h2>
  {% if aff.terminated_for_cause %}<p>Terminated for cause{% if aff.terminated_at %} on {{ aff.terminated_at.strftime('%Y-%m-%d') }}{% endif %}.
    Unpaid commission is forfeited.</p><p><strong>Recorded reason:</strong> {{ aff.termination_cause }}</p>
  {% else %}<p>Terminated (not for cause). Commission on payments already made stays payable, and the final
    balance is paid even when it is below the payout minimum. Nothing is forfeited.</p>{% endif %}</div>
{% else %}
<div class="doc"><h2>1. Customer discount</h2>
  <p>Terms version <strong>{{ terms.version }}</strong>: the partner has a pool of {{ pct(terms.pool_pct) }}% of the list price.
    The customer discount comes out of that pool and the partner earns the rest. The discount can be 0% to {{ cap }}%.</p>
  <p><strong>Partner earns = {{ pct(terms.pool_pct) }}% minus the customer discount, of the list price.</strong>
    TradeWave always retains the other {{ 100 - terms.pool_pct|int }}% of the list price.</p>
  <form method="post" action="{{ url_for('affiliate_change_terms.apply') }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ aff.id }}">
    <div class="grid">
      <div><label>Annual plans - customer discount %
        <input type="number" step="0.01" min="0" max="{{ cap }}" name="discount_pct" id="discount_pct" value="{{ cur_year }}" required></label>
        <span class="muted">Also the discount behind the typed code {{ aff.code }}.</span></div>
      <div><label>Monthly plans - customer discount %
        <input type="number" step="0.01" min="0" max="{{ cap }}" name="discount_pct_monthly" id="discount_pct_monthly" value="{{ cur_month }}"></label>
        <span class="muted">Leave blank to use the annual discount.</span></div>
    </div>
    <h3>What this means in dollars</h3>
    """ + OFFER_PREVIEW_WIDGET + """
    <div class="note">Saving a discount inside the 0% to {{ cap }}% range takes effect right away for new checkouts.
      The partner is <strong>not paused</strong> and does <strong>not sign again</strong>. Existing customers keep the discount they have.
      The partner can also change this on their own dashboard (once every 24 hours; that limit does not apply here).</div>
    <button type="submit">Save customer discount</button>
  </form>
  {% if history %}<h3>Discount history</h3>
  <table><tr><th>When (UTC)</th><th>Billing</th><th class="num">From</th><th class="num">To</th><th>Changed by</th></tr>
  {% for h in history %}<tr><td>{{ h.changed_at.strftime('%Y-%m-%d %H:%M') if h.changed_at else '' }}</td>
    <td>{{ 'Annual' if h.billing_interval == 'year' else 'Monthly' }}</td>
    <td class="num">{{ pct(h.old_pct) if h.old_pct is not none else '-' }}%</td><td class="num">{{ pct(h.new_pct) }}%</td>
    <td>{{ h.actor or '-' }}</td></tr>{% endfor %}</table>{% endif %}
</div>

<div class="doc"><h2>2. Terms version</h2>
  <p>Current: <strong>{{ terms_summary(terms) }}</strong></p>
  <form method="post" action="{{ url_for('affiliate_change_terms.assign') }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ aff.id }}">
    <label>Assign terms version
      <select name="terms_id">{% for t in all_terms %}
        <option value="{{ t.id }}"{% if t.id == terms.id %} selected{% endif %}>{{ terms_summary(t) }}</option>{% endfor %}
      </select></label>
    <label class="inline" style="margin-top:10px"><input type="checkbox" name="resign" value="1" checked>
      Require the partner to sign the agreement again (recommended: the commission rules are part of the agreement)</label>
    <div class="note">The new version applies only to customers whose checkout starts after you save.
      Customers already referred keep the version they started with, for first-year and renewal commission.
      If you require a new signature, the partner is paused until they sign: their link stops applying to new customers
      and commission that accrues meanwhile is held, then released when they sign.</div>
    <button type="submit">Assign terms version</button>
  </form>
  <p class="muted">Need different rules? <a href="{{ url_for('affiliate_terms.index') }}">Create a new terms version</a> first.</p>
</div>

<div class="doc"><h2>3. Agreement changed? Ask for a new signature</h2>
  <p>Use this when the agreement text or this partner's addendum (Exhibit B) changed. It clears the signature and pauses
    the partner until they sign again. A discount change on its own never needs this.</p>
  <form method="post" action="{{ url_for('affiliate_change_terms.resign') }}"
        onsubmit="return confirm('Pause {{ aff.code }} until they sign the agreement again?');">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ aff.id }}">
    <button type="submit" class="secondary">Require a new signature</button>
  </form>
</div>

<div class="doc"><h2>4. Terminate for cause</h2>
  <p>Ends the partnership for a breach of the agreement. This is the only action that <strong>forfeits</strong> commission:
    held and unpaid commission is voided at once, including pending payout rows. Commission already paid is not touched.
    The partner's code stops working. To wind a partner down without forfeiting, set their status to Paused or Terminated on the Affiliates page instead.</p>
  <form method="post" action="{{ url_for('affiliate_change_terms.terminate') }}"
        onsubmit="return confirm('Terminate {{ aff.code }} for cause and forfeit their unpaid commission? This cannot be undone here.');">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ aff.id }}">
    <label>Reason (required - recorded permanently)
      <textarea name="reason" rows="3" minlength="10" required placeholder="What the partner did and which part of the agreement it breached"></textarea></label>
    <button type="submit" class="danger">Terminate for cause</button>
  </form>
</div>
{% endif %}
{% if held_lines and not aff.terminated_for_cause %}
<div class="doc"><h2>Held commission</h2>
  <p>{{ aff.code }} has <strong>{{ held_lines }}</strong> held commission line(s). Lines held while a partner is paused
    are released automatically when the partner is active again, or is terminated without cause. Use this button to
    release them now. Released lines become payable and join the next month you commit.</p>
  <form method="post" action="{{ url_for('affiliate_change_terms.release') }}"
        onsubmit="return confirm('Release the held commission lines of {{ aff.code }}? They become payable.');">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ aff.id }}">
    <button type="submit" class="secondary">Release held lines</button>
  </form>
</div>
{% endif %}
{% endif %}
""" + _FOOT


def make_views(auth_cls, *, catalog_fn, audit_fn, current_user_fn):
    """Build the BaseViews. auth_cls is app._AdminAuth (super_admin gate);
    catalog_fn is app._campaign_catalog; audit_fn is app.write_audit;
    current_user_fn is app.get_current_user. Returns a dict of classes."""
    from flask import flash, jsonify, redirect, render_template_string, request, url_for
    from flask_admin import BaseView, expose
    from models import Affiliate, AffiliateReferral, PromoCampaign

    def _S():
        # resolved per request (not captured at import) so tests can swap it
        import models
        return models.Session()

    def actor():
        u = current_user_fn()
        return "admin:%s" % (getattr(u, "email", None) or "unknown")

    def catalog():
        """(catalog, error text or None) - a Stripe hiccup must not 500 a page."""
        try:
            return catalog_fn(), None
        except Exception as e:   # noqa: BLE001
            log.warning("campaign catalog unavailable: %s", e)
            return {}, str(e)

    def load_affiliate(session, aid, lock=False):
        try:
            aid = uuid.UUID(str(aid))
        except (ValueError, TypeError, AttributeError):
            return None
        q = session.query(Affiliate).filter(Affiliate.id == aid)
        if lock:
            q = q.with_for_update()
        return q.first()

    helpers = dict(pct=pct, money=money, renewal_length_label=renewal_length_label,
                   terms_summary=terms_summary, plan_label=PLAN_LABEL,
                   interval_label=INTERVAL_LABEL, window_text=window_text,
                   intro_length_label=intro_length_label, phase=campaign_phase,
                   offer_text=campaign_offer_text, price_field=price_field,
                   plans=PLANS, intervals=INTERVALS)

    # ----------------------------------------------------------------- Terms
    class AffiliateTermsView(auth_cls, BaseView):
        """List / create terms versions and show which one each partner is on."""

        def _page(self, s, form=None, errors=None):
            from sqlalchemy import func
            counts = dict(s.query(Affiliate.terms_id, func.count(Affiliate.id))
                          .group_by(Affiliate.terms_id).all())
            default = afs.get_terms(s)
            if default is not None and None in counts:
                # partners without an explicit version are on the default
                counts[default.id] = counts.get(default.id, 0) + counts[None]
            return render_template_string(
                _TERMS_TMPL, title="Partner terms", terms=afs.list_terms(s), counts=counts,
                default_version=afs.DEFAULT_TERMS_VERSION, renewal_lengths=RENEWAL_LENGTHS,
                affiliates=s.query(Affiliate).order_by(Affiliate.code).all(),
                f=form or {}, errors=errors, **helpers)

        @expose("/")
        def index(self):
            s = _S()
            try:
                return self._page(s)
            finally:
                s.close()

        @expose("/create", methods=["POST"])
        def create(self):
            s = _S()
            try:
                try:
                    kwargs = parse_terms_form(request.form)
                    row = afs.create_terms(s, kwargs.pop("version"), **kwargs)
                except FormError as e:
                    s.rollback()
                    return self._page(s, form=request.form, errors=e.errors)
                except afs.AffiliateError as e:
                    s.rollback()
                    return self._page(s, form=request.form, errors=[str(e)])
                version = row.version
                audit_fn(actor_label=actor(), action="affiliate_terms_created",
                         details={"version": version})
                flash("Terms version %s created. Assign it to a partner from their "
                      "Change terms page." % version, "success")
                return redirect(url_for("affiliate_terms.index"))
            finally:
                s.close()

    # ------------------------------------------------------------- Campaigns
    class PromoCampaignView(auth_cls, BaseView):
        """Create / edit / archive company-wide promotion campaigns."""

        @expose("/")
        def index(self):
            s = _S()
            try:
                return render_template_string(
                    _CAMPAIGN_LIST_TMPL, title="Promotion campaigns", errors=None,
                    campaigns=afs.list_campaigns(s), tz=display_timezone(), **helpers)
            finally:
                s.close()

        def _load(self, s, cid):
            if not cid:
                return None
            try:
                cid = uuid.UUID(str(cid))
            except (ValueError, TypeError, AttributeError):
                return None
            return s.query(PromoCampaign).filter(PromoCampaign.id == cid).first()

        def _form(self, s, campaign, cat, cat_error, *, form=None, errors=None, spec=None):
            values = campaign_form_values(campaign, form)
            preview = window = None
            if spec is None and campaign is not None and form is None and cat:
                # opening a stored campaign shows its preview straight away
                spec = {"tiers": campaign.tiers, "intervals": campaign.billing_intervals,
                        "offer_type": campaign.offer_type, "intro_prices": campaign.intro_prices,
                        "percent_off": campaign.percent_off, "intro_months": campaign.intro_months,
                        "starts_at": campaign.starts_at, "ends_at": campaign.ends_at}
            if spec is not None:
                preview = campaign_preview(spec, cat, afs.get_terms(s))
                window = {"starts": window_text(spec["starts_at"], values["tz"]),
                          "ends": window_text(spec["ends_at"], values["tz"])}
            return render_template_string(
                _CAMPAIGN_FORM_TMPL, title="Campaign", campaign=campaign, v=values,
                catalog=cat, catalog_error=cat_error, errors=errors, preview=preview,
                window=window, timezones=timezone_choices(), **helpers)

        @expose("/edit", methods=["GET", "POST"])
        def edit(self):
            s = _S()
            try:
                cid = request.args.get("id", "")
                campaign = self._load(s, cid)
                if cid and campaign is None:
                    flash("Campaign not found.", "error")
                    return redirect(url_for("promo_campaigns.index"))
                cat, cat_error = catalog()
                if request.method == "GET":
                    return self._form(s, campaign, cat, cat_error)
                try:
                    spec = parse_campaign_form(request.form, cat)
                except FormError as e:
                    return self._form(s, campaign, cat, cat_error, form=request.form,
                                      errors=e.errors)
                action = request.form.get("action") or "preview"
                if action not in ("save_draft", "activate"):
                    return self._form(s, campaign, cat, cat_error, form=request.form, spec=spec)
                status = "active" if action == "activate" else "draft"
                fields = {k: spec[k] for k in ("name", "tiers", "intervals", "starts_at",
                                               "ends_at", "offer_type", "intro_prices",
                                               "percent_off", "intro_months", "notes")}
                try:
                    if campaign is None:
                        campaign = afs.create_campaign(
                            s, catalog=cat, status=status, code=spec["code"],
                            new_customers_only=True, **fields)
                        verb = "created"
                    else:
                        campaign = afs.update_campaign(s, campaign, catalog=cat, status=status,
                                                       **fields)
                        verb = "updated"
                except afs.AffiliateError as e:
                    s.rollback()
                    campaign = self._load(s, cid)
                    return self._form(s, campaign, cat, cat_error, form=request.form,
                                      errors=[str(e)], spec=spec)
                code, name = campaign.code, campaign.name
                audit_fn(actor_label=actor(), action="promo_campaign_%s" % verb,
                         details={"code": code, "status": status})
                flash("Campaign %s %s as %s." % (
                    name, verb, "ACTIVE - customers can claim it during the claim window"
                    if status == "active" else "a draft (not live)"), "success")
                return redirect(url_for("promo_campaigns.index"))
            finally:
                s.close()

        @expose("/archive", methods=["POST"])
        def archive(self):
            s = _S()
            try:
                campaign = self._load(s, request.form.get("id", ""))
                if campaign is None:
                    flash("Campaign not found.", "error")
                    return redirect(url_for("promo_campaigns.index"))
                try:
                    afs.update_campaign(s, campaign, status="archived")
                except afs.AffiliateError as e:
                    s.rollback()
                    flash("Could not archive: %s" % e, "error")
                    return redirect(url_for("promo_campaigns.index"))
                code = campaign.code
                audit_fn(actor_label=actor(), action="promo_campaign_archived",
                         details={"code": code})
                flash("Campaign %s archived. New customers can no longer claim it." % code,
                      "success")
                return redirect(url_for("promo_campaigns.index"))
            finally:
                s.close()

    # ---------------------------------------------------------- Change terms
    class AffiliateChangeTermsView(auth_cls, BaseView):
        """Per-partner page: customer discount (no pause, no re-sign), terms
        version (prospective), new signature for agreement changes, and
        terminate for cause. Reached from the row icon on the Affiliates list."""

        def is_visible(self):
            return False

        def _back(self, aid):
            return redirect(url_for("affiliate_change_terms.index", id=aid))

        @expose("/")
        def index(self):
            s = _S()
            try:
                aff = load_affiliate(s, request.args.get("id", ""))
                if aff is None:
                    return render_template_string(_CHANGE_TERMS_TMPL, title="Change terms",
                                                  found=False, errors=None, **helpers)
                held_lines = held_line_count(s, aff)
                terms = afs.terms_for(s, aff)
                cat, cat_error = catalog()
                month = aff.discount_pct_monthly
                try:
                    rows = offer_preview(cat, aff.discount_pct, month, terms)
                except afs.AffiliateError:
                    rows = []       # legacy discount above the cap: the live preview explains
                if cat_error:
                    flash("Plan prices could not be read from Stripe, so the preview shows "
                          "the $100 example only.", "warning")
                return render_template_string(
                    _CHANGE_TERMS_TMPL, title="Change terms - %s" % aff.code, found=True,
                    aff=aff, terms=terms, cap=pct(terms.max_discount_pct), errors=None,
                    held_lines=held_lines,
                    cur_year=pct(aff.discount_pct),
                    cur_month=pct(month) if month is not None else "",
                    preview_rows=rows, preview_terms_id=getattr(terms, "id", None) or "",
                    all_terms=afs.list_terms(s), history=afs.discount_history(s, aff, limit=20),
                    ref_count=s.query(AffiliateReferral)
                    .filter(AffiliateReferral.affiliate_id == aff.id).count(),
                    **helpers)
            finally:
                s.close()

        @expose("/preview")
        def preview(self):
            """JSON for the live dollar table (also used by the create form)."""
            s = _S()
            try:
                terms = None
                raw_terms = (request.args.get("terms_id") or "").strip()
                if raw_terms.isdigit():
                    terms = afs.get_terms(s, int(raw_terms))
                terms = terms or afs.get_terms(s) or afs.DEFAULT_TERMS
                cat, cat_error = catalog()
                try:
                    rows = offer_preview(cat, request.args.get("discount_year", ""),
                                         request.args.get("discount_month", ""), terms)
                except afs.AffiliateError as e:
                    return jsonify({"ok": False, "error": str(e)})
                return jsonify({"ok": True, "rows": rows, "terms": terms.version,
                                "warning": ("Plan prices could not be read from Stripe - "
                                            "showing the $100 example only." if cat_error else "")})
            finally:
                s.close()

        @expose("/apply", methods=["POST"])
        def apply(self):
            aid = request.form.get("id", "")
            s = _S()
            try:
                aff = load_affiliate(s, aid, lock=True)
                if aff is None:
                    flash("Affiliate not found.", "error")
                    return redirect("/admin/affiliate/")
                code = aff.code
                try:
                    changes = apply_partner_discounts(
                        s, aff, request.form.get("discount_pct"),
                        request.form.get("discount_pct_monthly"), actor())
                except afs.AffiliateError as e:
                    s.rollback()
                    flash(str(e), "error")
                    return self._back(aid)
                if not changes:
                    flash("No change - the customer discount is the same as before.", "info")
                    return self._back(aid)
                summary = ", ".join("%s %s%%" % (
                    "annual" if c.billing_interval == "year" else "monthly", pct(c.new_pct))
                    for c in changes)
                audit_fn(actor_label=actor(), action="affiliate_discount_changed",
                         details={"code": code, "changes": summary})
                flash("Customer discount for %s is now %s. It applies to new checkouts from "
                      "now on. The partner was not paused and does not need to sign again."
                      % (code, summary), "success")
                return self._back(aid)
            except Exception as e:   # noqa: BLE001
                s.rollback()
                log.exception("admin discount change failed")
                flash("Could not change the discount: %s" % e, "error")
                return self._back(aid)
            finally:
                s.close()

        @expose("/assign", methods=["POST"])
        def assign(self):
            aid = request.form.get("id", "")
            s = _S()
            try:
                aff = load_affiliate(s, aid, lock=True)
                if aff is None:
                    flash("Affiliate not found.", "error")
                    return redirect("/admin/affiliate/")
                if aff.status == "terminated":
                    flash("A terminated partner cannot be given new terms.", "error")
                    return self._back(aid)
                code = aff.code
                current = afs.terms_for(s, aff)
                raw = (request.form.get("terms_id") or "").strip()
                if not raw.isdigit():
                    flash("Pick a terms version.", "error")
                    return self._back(aid)
                if getattr(current, "id", None) == int(raw) and aff.terms_id == int(raw):
                    flash("No change - %s is already on that terms version." % code, "info")
                    return self._back(aid)
                try:
                    terms = afs.assign_terms(s, aff, int(raw), actor=actor())
                except afs.AffiliateError as e:
                    s.rollback()
                    flash(str(e)[:1].upper() + str(e)[1:], "error")
                    return self._back(aid)
                version = terms.version
                msg = ("%s is now on terms %s for customers who check out from now on. "
                       "Existing customers keep their terms." % (code, version))
                if request.form.get("resign") and aff.agreement_signed_at is not None:
                    try:
                        require_resign(s, aff)
                    except Exception as e:   # noqa: BLE001
                        flash(msg + " But the new-signature step failed (%s) - use "
                              "'Require a new signature' below." % e, "warning")
                        return self._back(aid)
                    flash(msg + " The partner is PAUSED until they sign the agreement again - "
                          "send them the signing link below.", "success")
                    return redirect(url_for("affiliate_signed.index", id=aid))
                flash(msg, "success")
                return self._back(aid)
            finally:
                s.close()

        @expose("/resign", methods=["POST"])
        def resign(self):
            aid = request.form.get("id", "")
            s = _S()
            try:
                aff = load_affiliate(s, aid, lock=True)
                if aff is None:
                    flash("Affiliate not found.", "error")
                    return redirect("/admin/affiliate/")
                if aff.status == "terminated":
                    flash("A terminated partner cannot sign again.", "error")
                    return self._back(aid)
                code = aff.code
                try:
                    require_resign(s, aff)
                except Exception as e:   # noqa: BLE001
                    flash("Could not require a new signature: %s" % e, "error")
                    return self._back(aid)
                audit_fn(actor_label=actor(), action="affiliate_resign_required",
                         details={"code": code})
                flash("%s is PAUSED until they sign the agreement again. Send them the "
                      "signing link below." % code, "success")
                return redirect(url_for("affiliate_signed.index", id=aid))
            finally:
                s.close()

        @expose("/terminate", methods=["POST"])
        def terminate(self):
            aid = request.form.get("id", "")
            s = _S()
            try:
                aff = load_affiliate(s, aid, lock=True)
                if aff is None:
                    flash("Affiliate not found.", "error")
                    return redirect("/admin/affiliate/")
                code = aff.code
                try:
                    terminate_partner_for_cause(s, aff, request.form.get("reason"), actor())
                except afs.AffiliateError as e:
                    s.rollback()
                    flash(str(e), "error")
                    return self._back(aid)
                flash("%s was terminated for cause. Their code is off and their unpaid "
                      "commission is forfeited." % code, "success")
                return self._back(aid)
            finally:
                s.close()

        @expose("/release", methods=["POST"])
        def release(self):
            """Release held lines: held -> payable, for the next committed month."""
            aid = request.form.get("id", "")
            s = _S()
            try:
                aff = load_affiliate(s, aid, lock=True)
                if aff is None:
                    flash("Affiliate not found.", "error")
                    return redirect("/admin/affiliate/")
                code = aff.code
                try:
                    moved = afs.release_held_lines(s, aff, actor=actor())
                except afs.AffiliateError as e:
                    s.rollback()
                    flash(str(e), "error")
                    return self._back(aid)
                if moved:
                    flash("%d held line(s) of %s released. They are payable and join the next "
                          "month you commit." % (moved, code), "success")
                else:
                    flash("%s has no held commission lines." % code, "info")
                return self._back(aid)
            finally:
                s.close()

    return {"terms": AffiliateTermsView, "campaigns": PromoCampaignView,
            "change_terms": AffiliateChangeTermsView}
