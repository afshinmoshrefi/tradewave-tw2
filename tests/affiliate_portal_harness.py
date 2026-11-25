"""Shared harness for the partner-dashboard tests (and for rendering the
dashboard locally): an in-memory SQLite copy of the affiliate tables, a tiny
Flask app with the real affiliate_portal blueprint, a fake Stripe, and seed
data for an ACTIVE, a PAUSED and a NO-DATA partner.

Not a test module. `patch(obj, name, value)` is pytest's monkeypatch.setattr
in tests; a plain setattr works for a one-off local render.
"""
import datetime as dt
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(_REPO_ROOT), str(_REPO_ROOT / "web")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

UTC = dt.timezone.utc
TABLES = ["affiliate_terms", "affiliates", "affiliate_referrals", "affiliate_payouts",
          "affiliate_commission_lines", "affiliate_discount_changes", "promo_campaigns",
          "audit_log", "users", "affiliate_clicks", "affiliate_smn_profiles", "expert_takes"]
# Every TW-TASK-0039 table (help assistant, comms, ops, owner tools, job
# queue). The 0039 suites build their DB from TABLES + PROGRAM_TABLES, because
# those features now reach across each other (a tax-form review writes a
# notification, an answered question queues a job, the admin home counts all).
PROGRAM_TABLES = ["affiliate_applications", "affiliate_messages", "affiliate_notifications",
                  "affiliate_email_prefs", "affiliate_help_escalations", "affiliate_help_messages",
                  "affiliate_help_kb", "affiliate_tax_forms", "affiliate_sublinks",
                  "affiliate_sublink_clicks", "affiliate_creatives", "affiliate_jobs",
                  "affiliate_program_settings"]


def all_tables():
    import affiliate_ops_models  # noqa: F401  (registers the ops tables on Base.metadata)
    return TABLES + [t for t in PROGRAM_TABLES if t not in TABLES]

# Stripe price catalog stand-in: (tier, interval) -> list price.
CATALOG = {
    ("navigator", "month"): {"price_id": "price_nm", "product_id": "prod_n", "list_price_cents": 2900},
    ("navigator", "year"): {"price_id": "price_ny", "product_id": "prod_n", "list_price_cents": 24900},
    ("analyst", "month"): {"price_id": "price_am", "product_id": "prod_a", "list_price_cents": 4900},
    ("analyst", "year"): {"price_id": "price_ay", "product_id": "prod_a", "list_price_cents": 39900},
    ("strategist", "month"): {"price_id": "price_sm", "product_id": "prod_s", "list_price_cents": 9900},
    ("strategist", "year"): {"price_id": "price_sy", "product_id": "prod_s", "list_price_cents": 79900},
}
SECRET_EMAILS = ["priya.buyer@secret.example", "omar.buyer@secret.example",
                 "lena.buyer@secret.example"]


def D(v):
    return Decimal(str(v))


def make_db():
    """(session, factory, engine): SQLite copy of the affiliate tables with
    the three seeded terms versions."""
    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker
    import models
    md = sa.MetaData()
    for name in TABLES:
        src = models.Base.metadata.tables[name]
        cols = []
        for c in src.columns:
            ctype = c.type
            tname = type(ctype).__name__
            if tname == "JSONB":
                ctype = sa.JSON()
            elif tname == "UUID":
                ctype = sa.Uuid()
            elif tname == "ARRAY":
                ctype = sa.JSON()
            elif c.primary_key and isinstance(ctype, sa.BigInteger):
                ctype = sa.Integer()
            default = None
            if c.server_default is not None:
                arg = str(getattr(c.server_default.arg, "text", c.server_default.arg))
                if "now" in arg:
                    default = sa.text("CURRENT_TIMESTAMP")
                elif "(" not in arg and "::" not in arg:
                    default = sa.text(arg)
            cols.append(sa.Column(c.name, ctype, primary_key=c.primary_key, nullable=c.nullable,
                                  server_default=default))
        sa.Table(name, md, *cols)
    engine = sa.create_engine("sqlite://", connect_args={"check_same_thread": False},
                              poolclass=sa.pool.StaticPool)
    md.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    session = factory()
    session.add_all([models.AffiliateTerms(id=1, version="v2-5y", renewal_years=5),
                     models.AffiliateTerms(id=2, version="v2-10y", renewal_years=10),
                     models.AffiliateTerms(id=3, version="v2-lifetime", renewal_years=None)])
    session.commit()
    return session, factory, engine


class FakeList:
    def __init__(self, items):
        self._items = list(items)

    def auto_paging_iter(self):
        return iter(self._items)


def fake_stripe(patch):
    """Monkeypatch the Stripe calls the commission engine and
    set_partner_discount make. Returns the mutable world."""
    import stripe
    world = SimpleNamespace(invoices=[], refunds=[], disputes=[], calls=[])

    def invoice_list(**kw):
        items = world.invoices
        if "customer" in kw:
            items = [i for i in items if i["customer"] == kw["customer"]]
        return FakeList(items)

    patch(stripe.Invoice, "list", invoice_list)
    patch(stripe.Refund, "list", lambda **kw: FakeList(world.refunds))
    patch(stripe.Dispute, "list", lambda **kw: FakeList(world.disputes))
    patch(stripe.InvoicePayment, "list", lambda **kw: FakeList([]))
    patch(stripe.Invoice, "retrieve", lambda iid, **kw: {i["id"]: i for i in world.invoices}[iid])
    return world


def invoice(iid, *, paid, list_cents, sub, customer, paid_at, period_start=None, interval="month"):
    t = int(paid_at.timestamp())
    return {
        "id": iid, "status": "paid", "currency": "usd", "amount_paid": paid, "subtotal": list_cents,
        "total_taxes": [], "customer": customer, "customer_email": SECRET_EMAILS[0],
        "subscription": sub, "created": t, "status_transitions": {"paid_at": t},
        "lines": {"data": [{"period": {"start": int((period_start or paid_at).timestamp())},
                            "price": {"recurring": {"interval": interval}}}]},
        "discounts": [],
    }


def make_app(patch, factory, state, csrf=False):
    """A Flask app with the real blueprint at /account/affiliate. state.user
    is the logged-in user (None = logged out)."""
    from flask import Flask
    from flask_wtf.csrf import CSRFProtect
    import models
    import affiliate_portal
    from affiliate_portal import blueprint as bpmod, routes
    app = Flask("aff_portal_test_app")
    app.config.update(SECRET_KEY="test", TESTING=True, WTF_CSRF_ENABLED=csrf)
    CSRFProtect(app)
    app.register_blueprint(affiliate_portal.bp, url_prefix="/account/affiliate")
    patch(bpmod, "_USER_LOADER", lambda: state.user)
    patch(bpmod, "_CATALOG_LOADER", lambda: state.catalog)
    patch(models, "Session", factory)
    patch(routes, "_db", lambda: factory())
    patch(routes, "_est_redis", lambda: None)
    patch(routes, "_estimate_cache", {})
    patch(routes, "_catalog_cache", [0.0, None])
    patch(routes, "_resend_at", {})
    patch(routes, "_notify_operator", lambda *a, **k: None)
    return app


def _user(db, email):
    import models
    u = models.User(id=uuid.uuid4(), email=email, tier="explorer")
    db.add(u)
    db.commit()
    return u


def make_partner(db, code="ANNE", **kw):
    import models
    user = _user(db, code.lower() + "@partner.example")
    base = dict(id=uuid.uuid4(), code=code, name=code.title() + " Lee",
                email=code.lower() + "@partner.example", user_id=user.id,
                discount_pct=D(20), commission_pct=D(30), status="active", terms_id=1,
                stripe_coupon_id="cpn_" + code.lower(), stripe_promotion_code_id="promo_" + code.lower(),
                commission_model="recurring", agreement_token_version=0, terminated_for_cause=False,
                agreement_signed_at=dt.datetime(2026, 1, 5, tzinfo=UTC), agreement_version="v2",
                payout_method="paypal", payout_email="pay-" + code.lower() + "@partner.example",
                tax_form_type="w9", tax_form_received_at=dt.datetime(2026, 1, 6, tzinfo=UTC))
    base.update(kw)
    aff = models.Affiliate(**base)
    db.add(aff)
    db.commit()
    return aff, user


def _line(aff, ref, kind, source, when, *, paid, rate, amount, state, year=1, hold=None,
          payout_id=None, interval=None, basis=None):
    """A ledger line. Like the engine, a first-year line (and its refund) is
    priced on the LIST price; promotions and renewals on what was paid."""
    import models
    if basis is None:
        basis = paid
        if kind == "first_year" and ref.list_price_cents:
            basis = int(ref.list_price_cents)
        elif kind in ("refund", "dispute") and ref.list_price_cents and ref.offer_type != "promo":
            basis = -int(ref.list_price_cents) if paid < 0 else int(ref.list_price_cents)
    return models.AffiliateCommissionLine(
        affiliate_id=aff.id, referral_id=ref.id, kind=kind, source_id=source,
        stripe_invoice_id=source if kind not in ("refund", "dispute") else "in_orig_" + source,
        stripe_reversal_id=source if kind in ("refund", "dispute") else None,
        stripe_customer_id=ref.stripe_customer_id, stripe_subscription_id=ref.stripe_subscription_id,
        currency="usd", billing_interval=interval or ref.billing_interval,
        service_period_start=when, event_at=when, year_number=year, net_paid_cents=paid,
        basis_cents=basis, rate_pct=D(rate), amount=D(amount), state=state, hold_reason=hold,
        period_month=dt.date(when.year, when.month, 1),
        payable_month=None if state == "held" else dt.date(when.year, when.month, 1),
        payout_id=payout_id, detail={})


def seed_rich(db, world, now=None, code="ANNE", status="active", **partner_kw):
    """A partner with history: five customers (annual in year 2, monthly,
    promotion, not paid yet, ended), ledger lines in every state, payouts,
    clicks, signups, a discount change and a live Black Friday campaign.
    status='paused' makes this month's Stripe invoice come back HELD."""
    import models
    import affiliate_service as afs
    now = now or dt.datetime.now(UTC)
    aff, user = make_partner(db, code, status=status, **partner_kw)

    camp = models.PromoCampaign(
        id=uuid.uuid4(), code="BLACK-FRIDAY", name="Black Friday", tiers=["analyst"],
        billing_intervals=["year"], new_customers_only=True,
        starts_at=now - dt.timedelta(days=4), ends_at=now + dt.timedelta(days=6),
        offer_type="price", intro_prices={"analyst:year": 9900}, intro_months=12,
        stripe_coupon_ids={"analyst:year": "cpn_bf_analyst_year"}, status="active")
    db.add(camp)

    def ref(n, **kw):
        base = dict(id=uuid.uuid4(), affiliate_id=aff.id, stripe_subscription_id="sub_%s_%d" % (code, n),
                    stripe_customer_id="cus_%s_%d" % (code, n), source="checkout", terms_id=1,
                    offer_type="regular", discount_pct=D(20), referral_code=code)
        base.update(kw)
        r = models.AffiliateReferral(**base)
        db.add(r)
        return r

    m14 = afs._add_months(now, -14) + dt.timedelta(days=9)
    r1 = ref(1, tier="analyst", billing_interval="year", list_price_cents=39900,
             attributed_at=m14, first_paid_at=m14, year_anchor_at=m14)
    m3 = afs._add_months(now, -3) - dt.timedelta(days=2)
    r2 = ref(2, tier="navigator", billing_interval="month", list_price_cents=2900,
             attributed_at=m3, first_paid_at=m3, year_anchor_at=m3, source="promo_code")
    d20 = now - dt.timedelta(days=3)
    r3 = ref(3, tier="analyst", billing_interval="year", list_price_cents=39900, offer_type="promo",
             campaign_id=camp.id, discount_pct=None, attributed_at=d20, first_paid_at=d20,
             year_anchor_at=d20)
    r4 = ref(4, tier="strategist", billing_interval="year", list_price_cents=79900,
             attributed_at=now - dt.timedelta(days=1), source="signup")
    m8 = afs._add_months(now, -8)
    r5 = ref(5, tier="navigator", billing_interval="month", list_price_cents=2900,
             attributed_at=m8, first_paid_at=m8, year_anchor_at=m8,
             ended_at=afs._add_months(now, -5))
    db.flush()

    def month_start(d):
        return dt.date(d.year, d.month, 1)

    paid_month = month_start(m14)
    p_paid = models.AffiliatePayout(
        affiliate_id=aff.id, period_start=paid_month, period_end=paid_month, currency="usd",
        gross_revenue=D("319.20"), commission_amount=D("119.70"), status="paid", locked=True,
        paid_at=afs._add_months(m14, 1), external_ref="PP-7H2K91")
    last_month = month_start(afs._add_months(now, -1))
    p_pending = models.AffiliatePayout(
        affiliate_id=aff.id, period_start=last_month, period_end=last_month, currency="usd",
        gross_revenue=D("428.00"), commission_amount=D("108.45"), status="pending")
    db.add_all([p_paid, p_pending])
    db.flush()

    lm = afs._add_months(now, -1)
    lines = [
        _line(aff, r1, "first_year", "in_r1_y1", m14, paid=31920, rate=30, amount="119.70",
              state="paid", payout_id=p_paid.id),
        _line(aff, r1, "renewal", "in_r1_y2", afs._add_months(m14, 12), paid=39900, rate=25,
              amount="99.75", state="pending", year=2, payout_id=p_pending.id),
        _line(aff, r2, "first_year", "in_r2_m1", m3, paid=2320, rate=30, amount="8.70", state="paid"),
        _line(aff, r2, "first_year", "in_r2_m2", afs._add_months(m3, 1), paid=2320, rate=30,
              amount="8.70", state="pending", payout_id=p_pending.id),
        _line(aff, r5, "first_year", "in_r5_m1", m8, paid=2320, rate=30, amount="8.70", state="paid"),
        _line(aff, r5, "refund", "re_r5_1", m8 + dt.timedelta(days=6), paid=-2320, rate=30,
              amount="-8.70", state="paid"),
        _line(aff, r3, "promo", "in_r3_y1", d20, paid=9900, rate=50, amount="49.50",
              state="held" if status == "paused" else "pending",
              hold="paused" if status == "paused" else None),
        _line(aff, r5, "lapsed", "in_r5_lapsed", lm, paid=2900, rate=0, amount="0", state="lapsed", year=2),
    ]
    db.add_all(lines)

    for back, n in ((0, 9), (1, 14), (2, 6), (5, 22), (9, 11), (20, 30), (45, 41), (100, 60), (300, 85)):
        db.add(models.AffiliateClick(affiliate_id=aff.id, day=(now - dt.timedelta(days=back)).date(), clicks=n))
    for i, back in enumerate((1, 2, 4, 8, 15, 28, 50, 120, 400)):
        email = SECRET_EMAILS[i] if i < len(SECRET_EMAILS) else "buyer%d@secret.example" % i
        when = now - dt.timedelta(days=back)
        db.add(models.User(id=uuid.uuid4(), email=email, tier="explorer",
                           referred_by_affiliate_id=aff.id, referred_at=when,
                           reverse_trial_ends_at=when + dt.timedelta(days=7)))
    db.add(models.AffiliateDiscountChange(
        affiliate_id=aff.id, billing_interval="year", old_pct=D(15), new_pct=D(20),
        actor="partner:%s" % user.id, changed_at=now - dt.timedelta(days=40)))
    db.commit()

    # This month's monthly payment of customer 2: not booked yet -> Estimated
    # (or Held when the partner is paused).
    paid_at = now - dt.timedelta(hours=6)
    if paid_at.month != now.month:
        paid_at = now
    world.invoices.append(invoice("in_%s_this_month" % code, paid=2320, list_cents=2900,
                                  sub=r2.stripe_subscription_id, customer=r2.stripe_customer_id,
                                  paid_at=paid_at, period_start=afs._add_months(m3, 3)))
    return aff, user


def seed_empty(db, code="NEWBIE", **kw):
    """A brand-new partner: nothing but the row (tax form and payout method
    still missing)."""
    base = dict(tax_form_type=None, tax_form_received_at=None, payout_method=None,
                payout_email=None, discount_pct=D(10))
    base.update(kw)
    return make_partner(db, code, **base)
