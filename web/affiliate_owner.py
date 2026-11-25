"""Owner-side tools of the partner program (TW-TASK-0039, fix-0039). Service
layer, no Flask. Screens: web/affiliate_owner_admin.py.

1. program_counts  - the live numbers on the "Partner program" admin home.
2. send_digest     - ONE owner email a day, only when an application, a
                     partner question or a tax form has waited more than 48
                     hours. Called by the daily comms job.
3. auto-approve    - owner-set rules applied when an application is
                     submitted (off by default). An auto-approved partner is
                     created PAUSED and still has to sign the agreement.
4. fraud_signals   - flags with a plain reason on the payout screens. They
                     are information for the owner: nothing here blocks,
                     holds or changes a payout.
5. tax_year_report - per partner, what was PAID in a calendar year, with the
                     tax form type and a "1099-NEC likely" flag.

No em-dashes in any copy (use " - ").
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from decimal import Decimal

import config
import affiliate_service as afs

log = logging.getLogger("tw2.affiliate_owner")

UTC = dt.timezone.utc
WAIT_HOURS = 48
DIGEST_ACTION = "affiliate_owner_digest_sent"


def _now(now=None):
    return afs._utc(now) or dt.datetime.now(UTC)


def age_text(since, now) -> str:
    """'3 days' / '5 hours' / 'under an hour' since a timestamp."""
    since = afs._utc(since)
    if since is None:
        return ""
    secs = max(0, int((now - since).total_seconds()))
    if secs >= 2 * 86400:
        return "%d days" % (secs // 86400)
    if secs >= 86400:
        return "1 day"
    if secs >= 7200:
        return "%d hours" % (secs // 3600)
    if secs >= 3600:
        return "1 hour"
    return "under an hour"


def _oldest(values):
    values = [afs._utc(v) for v in values if v is not None]
    return min(values) if values else None


# ===========================================================================
# 1. Waiting work + the admin home counts
# ===========================================================================
def waiting(session, now=None) -> dict:
    """What is waiting for the owner, as {key: {count, oldest, over}} where
    `over` is how many have waited more than WAIT_HOURS. Keys: applications,
    questions, tax_forms."""
    from models import AffiliateApplication as A
    from affiliate_help_models import AffiliateHelpEscalation as E
    import affiliate_ops_models as om
    now = _now(now)
    cutoff = now - dt.timedelta(hours=WAIT_HOURS)
    sources = {
        "applications": [r[0] for r in session.query(A.created_at).filter(A.status == "new").all()],
        "questions": [r[0] for r in session.query(E.created_at).filter(E.status == "open").all()],
        "tax_forms": [r[0] for r in session.query(om.AffiliateTaxForm.uploaded_at)
                      .filter(om.AffiliateTaxForm.status == "received").all()],
    }
    out = {}
    for key, stamps in sources.items():
        stamps = [afs._utc(v) for v in stamps if v is not None]
        out[key] = {"count": len(stamps), "oldest": min(stamps) if stamps else None,
                    "over": sum(1 for v in stamps if v < cutoff)}
    return out


def activity_watch(session, now=None, warn_days=None) -> list:
    """Partners with customers whose renewal commissions stop within
    `warn_days` (state 'closing'), or lapsed in the last 31 days ('lapsed'):
    [{code, name, state, date, days}]. Used by the admin home and the monthly
    operations summary."""
    from models import Affiliate, AffiliateReferral
    now = _now(now)
    if warn_days is None:
        warn_days = int(getattr(config, "AFFILIATE_OPS_ACTIVITY_WARN_DAYS", 30))
    out = []
    with_customers = {r[0] for r in session.query(AffiliateReferral.affiliate_id)
                      .filter(AffiliateReferral.first_paid_at.isnot(None)).distinct().all()}
    for aff in (session.query(Affiliate).filter(Affiliate.status.in_(("active", "paused")))
                .order_by(Affiliate.code).all()):
        if aff.id not in with_customers:
            continue
        st = afs.activity_status(aff, now, session=session, terms=afs.terms_for(session, aff))
        if st["active_until"] is not None:
            left = (st["active_until"] - now.date()).days
            if left <= warn_days:
                out.append({"code": aff.code, "name": aff.name, "state": "closing",
                            "date": st["active_until"], "days": left})
        elif st["lapsed_since"] is not None and (now.date() - st["lapsed_since"]).days <= 31:
            out.append({"code": aff.code, "name": aff.name, "state": "lapsed",
                        "date": st["lapsed_since"], "days": 0})
    return out


def program_counts(session, now=None) -> dict:
    """Everything the "Partner program" admin home shows. Each card:
    {key, title, count, detail, url, urgent}. Read-only."""
    import affiliate_jobs as jobs
    import affiliate_ops as ops
    from models import Affiliate
    now = _now(now)
    w = waiting(session, now)

    def waited(item):
        if not item["count"]:
            return "Nothing waiting"
        text = "Oldest has waited %s" % age_text(item["oldest"], now)
        if item["over"]:
            text += " - %d over 48 hours" % item["over"]
        return text

    rows = ops.pending_payout_rows(session)
    payable = [r for r in rows if r["payable"]]
    totals = {}
    for r in payable:
        totals[r["currency"]] = totals.get(r["currency"], Decimal("0")) + r["amount"]
    pay_detail = (", ".join("%s %s" % ("{:,.2f}".format(a), c.upper()) for c, a in sorted(totals.items()))
                  if payable else "Nothing payable right now")
    drift = sum(1 for r in rows if r["changed"])
    if drift:
        pay_detail += " - %d exported row%s changed amount" % (drift, "" if drift == 1 else "s")

    unsigned = (session.query(Affiliate.created_at)
                .filter(Affiliate.status == "paused", Affiliate.agreement_signed_at.is_(None)).all())
    oldest_unsigned = _oldest(r[0] for r in unsigned)
    watch = activity_watch(session, now)
    closing = [a for a in watch if a["state"] == "closing"]
    soonest = min((a["days"] for a in closing), default=None)
    flags = fraud_signals(session, now)
    flagged_payable = sum(1 for r in payable if flags.get(r["affiliate"].id))
    job_counts = jobs.counts(session)

    cards = [
        {"key": "applications", "title": "New applications", "count": w["applications"]["count"],
         "detail": waited(w["applications"]),
         "url": "/admin/affiliate_applications/", "urgent": bool(w["applications"]["over"])},
        {"key": "questions", "title": "Open partner questions", "count": w["questions"]["count"],
         "detail": waited(w["questions"]),
         "url": "/admin/affiliate_help/", "urgent": bool(w["questions"]["over"])},
        {"key": "tax_forms", "title": "Tax forms awaiting review", "count": w["tax_forms"]["count"],
         "detail": waited(w["tax_forms"]),
         "url": "/admin/affiliate_tax_forms/", "urgent": bool(w["tax_forms"]["over"])},
        {"key": "payable", "title": "Payout rows payable now", "count": len(payable),
         "detail": pay_detail, "url": "/admin/affiliate_bulk_payouts/", "urgent": bool(drift)},
        {"key": "unsigned", "title": "Partners who have not signed", "count": len(unsigned),
         "detail": ("Oldest was approved %s ago" % age_text(oldest_unsigned, now)) if unsigned
         else "Everyone has signed",
         "url": "/admin/affiliate/?flt1_status_equals=paused", "urgent": False},
        {"key": "activity", "title": "Partners near the activity deadline", "count": len(closing),
         "detail": ("Renewal commissions stop soonest in %d day%s" % (soonest, "" if soonest == 1 else "s"))
         if closing else "Nobody within %d days" % int(getattr(config, "AFFILIATE_OPS_ACTIVITY_WARN_DAYS", 30)),
         "url": "/admin/affiliate_home/#activity", "urgent": soonest is not None and soonest <= 7},
        {"key": "fraud", "title": "Partners with a fraud signal", "count": len(flags),
         "detail": ("%d of them on a payable row - check before paying" % flagged_payable)
         if flagged_payable else ("Flags are shown on Bulk payouts and the Payout ledger"
                                  if flags else "No signals"),
         "url": "/admin/affiliate_bulk_payouts/#flags", "urgent": bool(flagged_payable)},
    ]
    return {"cards": cards, "activity": watch, "jobs": job_counts, "generated_at": now,
            "owner_email": afs.owner_email(), "auto_approve": auto_approve_text(auto_approve_rules(session))}


# ===========================================================================
# 2. Owner digest (daily, only when something waited more than 48 hours)
# ===========================================================================
_DIGEST_ROWS = (
    ("applications", "partner application", "affiliate_applications/"),
    ("questions", "partner question", "affiliate_help/"),
    ("tax_forms", "tax form", "affiliate_tax_forms/"),
)


def digest_already_sent(session, day) -> bool:
    from models import AuditLog
    key = day.isoformat()
    for (details,) in (session.query(AuditLog.details).filter(AuditLog.action == DIGEST_ACTION)
                       .order_by(AuditLog.id.desc()).limit(10).all()):
        if isinstance(details, dict) and details.get("day") == key:
            return True
    return False


def build_digest(session, now=None):
    """(subject, text) or None when nothing has waited more than 48 hours."""
    now = _now(now)
    w = waiting(session, now)
    lines, total = [], 0
    for key, noun, path in _DIGEST_ROWS:
        item = w[key]
        if not item["over"]:
            continue
        total += item["over"]
        lines += ["%d %s%s waiting more than 48 hours (oldest: %s; %d waiting in all)."
                  % (item["over"], noun, "" if item["over"] == 1 else "s",
                     age_text(item["oldest"], now), item["count"]),
                  "Open: %s" % afs.admin_url(path), ""]
    if not total:
        return None
    subject = "Partner program: %d item%s waiting more than 48 hours" % (total, "" if total == 1 else "s")
    text = "\n".join(["These have waited more than 48 hours for you:", ""] + lines + [
        "Everything in one place: %s" % afs.admin_url("affiliate_home/"), "",
        "You get this email at most once a day, and only when something has waited this long."])
    return subject, text


def send_digest(session, now=None) -> str:
    """'sent' | 'nothing' | 'already' | 'not_sent'. One email per UTC day."""
    from models import AuditLog
    now = _now(now)
    built = build_digest(session, now)
    if built is None:
        return "nothing"
    if digest_already_sent(session, now.date()):
        return "already"
    to = afs.owner_email()
    try:
        from email_utils import resend_send_email
        ok = bool(to) and bool(resend_send_email(to=to, subject=built[0], body_text=built[1]))
    except Exception as e:   # noqa: BLE001
        log.warning("owner digest email failed: %s", type(e).__name__)
        ok = False
    if not ok:
        return "not_sent"
    session.add(AuditLog(actor_label="affiliate_comms", action=DIGEST_ACTION,
                         details={"day": now.date().isoformat(), "to": to}))
    session.commit()
    return "sent"


# ===========================================================================
# 3. Auto-approve rules
# ===========================================================================
AUTO_APPROVE_KEY = "auto_approve"
AUTO_MODES = (("off", "Off - I review every application"),
              ("all", "Approve every application"),
              ("rules", "Approve only applications that match the rules below"))
_COUNTRY_ALIASES = {
    "us": "united states", "usa": "united states", "u.s.": "united states", "u.s.a.": "united states",
    "united states of america": "united states", "america": "united states",
    "uk": "united kingdom", "u.k.": "united kingdom", "great britain": "united kingdom",
    "england": "united kingdom", "uae": "united arab emirates",
}


def norm_country(value) -> str:
    v = " ".join(str(value or "").strip().lower().split())
    return _COUNTRY_ALIASES.get(v, v)


def _size_rank(size_id) -> int:
    import affiliate_comms as comms
    ids = [s[0] for s in comms.AUDIENCE_SIZES]
    return ids.index(size_id) if size_id in ids else -1


def auto_approve_rules(session) -> dict:
    """{'mode': off|all|rules, 'countries': [..], 'min_audience': size id|''}.
    Off when nothing is stored or the stored value is unusable."""
    from models import AffiliateProgramSetting
    out = {"mode": "off", "countries": [], "min_audience": ""}
    try:
        row = session.get(AffiliateProgramSetting, AUTO_APPROVE_KEY)
    except Exception:   # noqa: BLE001  (table missing on a box that has not migrated yet)
        session.rollback()
        return out
    value = row.value if row is not None and isinstance(row.value, dict) else {}
    if value.get("mode") in dict(AUTO_MODES):
        out["mode"] = value["mode"]
    out["countries"] = [c for c in (norm_country(c) for c in value.get("countries") or []) if c]
    if _size_rank(value.get("min_audience")) >= 0:
        out["min_audience"] = value["min_audience"]
    return out


def auto_approve_text(rules) -> str:
    import affiliate_comms as comms
    if rules["mode"] == "off":
        return "Off"
    if rules["mode"] == "all":
        return "On - every application"
    parts = []
    if rules["countries"]:
        parts.append("country is one of: %s" % ", ".join(c.title() for c in rules["countries"]))
    if rules["min_audience"]:
        parts.append("audience is at least %s" % comms.AUDIENCE_SIZE_LABEL[rules["min_audience"]])
    return "On - when " + " and ".join(parts)


def save_auto_approve(session, form, actor, now=None) -> dict:
    """Validate and store the rules from the admin form. Commits. Raises
    afs.AffiliateError with a message for the admin."""
    from models import AffiliateProgramSetting
    mode = (form.get("mode") or "off").strip()
    if mode not in dict(AUTO_MODES):
        raise afs.AffiliateError("Choose one of the three options.")
    countries = []
    for part in re.split(r"[,\n;]+", str(form.get("countries") or "")):
        c = norm_country(part)
        if c and c not in countries:
            if len(c) > 80 or re.search(r"[<>]", c):
                raise afs.AffiliateError("Country names must be plain text.")
            countries.append(c)
    min_audience = (form.get("min_audience") or "").strip()
    if min_audience and _size_rank(min_audience) < 0:
        raise afs.AffiliateError("Choose an audience size from the list.")
    if mode == "rules" and not countries and not min_audience:
        raise afs.AffiliateError("Add at least one rule (countries or a minimum audience size), "
                                 "or choose another option.")
    value = {"mode": mode, "countries": countries[:100], "min_audience": min_audience}
    row = session.get(AffiliateProgramSetting, AUTO_APPROVE_KEY)
    if row is None:
        row = AffiliateProgramSetting(key=AUTO_APPROVE_KEY, value=value)
        session.add(row)
    else:
        row.value = value
    row.updated_by, row.updated_at = actor, _now(now)
    session.commit()
    return value


def auto_approve_match(app_row, rules) -> bool:
    if rules["mode"] == "all":
        return True
    if rules["mode"] != "rules":
        return False
    if rules["countries"] and norm_country(app_row.country) not in rules["countries"]:
        return False
    if rules["min_audience"] and _size_rank(app_row.audience_size) < _size_rank(rules["min_audience"]):
        return False
    return bool(rules["countries"] or rules["min_audience"])


def try_auto_approve(session, app_row, now=None):
    """Apply the owner's rules to a just-submitted application. Returns
    {'code', 'emailed'} when it was approved, else None (it stays 'new' for
    the owner). Never approves an email that is already a partner or that
    applied before. The partner is created PAUSED: they must still sign."""
    import affiliate_comms as comms
    from models import AuditLog
    rules = auto_approve_rules(session)
    if rules["mode"] == "off" or not auto_approve_match(app_row, rules):
        return None
    flags = comms.application_flags(session, app_row)
    if flags["affiliate"] is not None or flags["earlier"] or comms.has_link(app_row.name):
        return None
    terms = afs.get_terms(session)
    try:
        aff, emailed = comms.approve_application(
            session, app_row, code=comms.suggest_code(session, app_row.name),
            discount_pct=comms.default_discount(terms), actor="auto-approve",
            note=None, send_email=True, now=now)
    except comms.CommsError as e:
        session.rollback()
        log.info("auto-approve skipped for %s: %s", app_row.id, e)
        return None
    session.add(AuditLog(actor_label="auto-approve", action="affiliate_application_auto_approved",
                         details={"application": str(app_row.id), "code": aff.code,
                                  "rules": rules, "emailed": bool(emailed)}))
    session.commit()
    return {"code": aff.code, "emailed": bool(emailed)}


# ===========================================================================
# 4. Fraud signals (information only - never blocks anything)
# ===========================================================================
FREE_MAIL = frozenset((
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "ymail.com", "outlook.com",
    "hotmail.com", "hotmail.co.uk", "live.com", "msn.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "proton.me", "protonmail.com", "pm.me", "gmx.com", "gmx.net", "gmx.de", "mail.com",
    "yandex.com", "yandex.ru", "zoho.com", "fastmail.com", "hey.com", "web.de", "qq.com", "163.com",
))
RATIO_MIN_SIGNUPS = 5          # ignore the ratio until there is something to measure
RATIO_SUSPECT = 0.5            # more than 1 signup per 2 clicks is not organic traffic
SHARED_IP_MIN = 3              # this many referred signups from one network
FRAUD_LABELS = {"self_referral": "Self-referral", "self_referral_domain": "Same email domain",
                "self_referral_ip": "Same network as the partner", "click_ratio": "Unusual signup rate",
                "shared_ip": "Signups share a network"}


def _email(v) -> str:
    return str(v or "").strip().lower()


def _domain(v) -> str:
    return _email(v).rpartition("@")[2]


def _n(count, one, many=None) -> str:
    return "%d %s" % (count, one if count == 1 else (many or one + "s"))


def fraud_signals(session, now=None) -> dict:
    """{affiliate_id: [{"kind", "label", "reason"}]} for every partner with at
    least one signal. Counts only: no customer identity is put in a reason.

    self_referral        a referred signup or paying customer uses the
                         partner's own contact or payout email
    self_referral_domain ... or shares the partner's own (non-free-mail) domain
    self_referral_ip     a referred signup came from the network the partner
                         signed the agreement from
    click_ratio          many signups for the clicks counted (or signups with
                         no clicks at all)
    shared_ip            several referred signups from one network

    These are prompts to look, not verdicts: a couple sharing a home network
    or a partner testing their own link will trip them. Nothing is blocked."""
    from sqlalchemy import func
    from models import Affiliate, AffiliateClick, AffiliateReferral, User
    affs = {a.id: a for a in session.query(Affiliate).all()}
    if not affs:
        return {}
    people = {}        # affiliate_id -> {user_id: (email, ip_hash)}
    for uid, email, aid, iph in (session.query(User.id, User.email, User.referred_by_affiliate_id,
                                               User.referred_ip_hash)
                                 .filter(User.referred_by_affiliate_id.isnot(None)).all()):
        people.setdefault(aid, {})[uid] = (_email(email), iph)
    signup_counts = {aid: len(users) for aid, users in people.items()}
    cust = {}
    for aid, cid in (session.query(AffiliateReferral.affiliate_id, AffiliateReferral.stripe_customer_id)
                     .filter(AffiliateReferral.stripe_customer_id.isnot(None)).all()):
        cust.setdefault(cid, set()).add(aid)
    if cust:
        for uid, email, cid, iph in (session.query(User.id, User.email, User.stripe_customer_id,
                                                   User.referred_ip_hash)
                                     .filter(User.stripe_customer_id.in_(list(cust))).all()):
            for aid in cust.get(cid, ()):
                people.setdefault(aid, {}).setdefault(uid, (_email(email), iph))
    clicks = dict(session.query(AffiliateClick.affiliate_id, func.coalesce(func.sum(AffiliateClick.clicks), 0))
                  .group_by(AffiliateClick.affiliate_id).all())

    out = {}
    for aid, aff in affs.items():
        flags = []
        own = {e for e in (_email(aff.email), _email(aff.payout_email)) if e}
        own_domains = {_domain(e) for e in own} - FREE_MAIL - {""}
        own_ip = afs.hash_ip(aff.agreement_signed_ip) if aff.agreement_signed_ip else None
        users = list(people.get(aid, {}).values())
        same_email = sum(1 for e, _ip in users if e in own)
        same_domain = sum(1 for e, _ip in users if e not in own and _domain(e) in own_domains)
        same_ip = sum(1 for _e, ip in users if ip and own_ip and ip == own_ip)
        if same_email:
            flags.append(("self_referral", "%s the partner's own contact or payout email address"
                          % _n(same_email, "referred customer uses", "referred customers use")))
        if same_domain:
            flags.append(("self_referral_domain",
                          "%s the partner's own email domain (%s)"
                          % (_n(same_domain, "referred customer shares", "referred customers share"),
                             ", ".join(sorted(own_domains)))))
        if same_ip:
            flags.append(("self_referral_ip",
                          "%s from the network the partner signed the agreement from"
                          % _n(same_ip, "referred signup came", "referred signups came")))
        signups, n_clicks = int(signup_counts.get(aid, 0)), int(clicks.get(aid, 0) or 0)
        if signups >= RATIO_MIN_SIGNUPS and (n_clicks == 0 or signups / n_clicks > RATIO_SUSPECT):
            flags.append(("click_ratio",
                          "%d signups from %s (a normal link sees far more clicks than signups)"
                          % (signups, _n(n_clicks, "click"))))
        per_ip = {}
        for _e, ip in users:
            if ip:
                per_ip[ip] = per_ip.get(ip, 0) + 1
        crowded = sorted((n for n in per_ip.values() if n >= SHARED_IP_MIN), reverse=True)
        if crowded:
            flags.append(("shared_ip", "%d referred signups came from one network%s"
                          % (crowded[0], (" (and %s more)" % _n(len(crowded) - 1, "network"))
                             if len(crowded) > 1 else "")))
        if flags:
            out[aid] = [{"kind": k, "label": FRAUD_LABELS[k], "reason": r} for k, r in flags]
    return out


def fraud_text(flags) -> str:
    return "; ".join("%s: %s" % (f["label"], f["reason"]) for f in flags or [])


# ===========================================================================
# 5. Year-end tax report
# ===========================================================================
NEC_THRESHOLD = Decimal("600")          # IRS 1099-NEC reporting threshold (USD)
TAX_CSV_HEADER = ("partner_code", "name", "email", "country", "tax_form", "tax_form_received",
                  "currency", "total_paid", "payouts", "1099_nec_likely", "note")


def tax_years(session, now=None) -> list:
    """Calendar years that have at least one paid payout, newest first (the
    current year is always offered)."""
    from models import AffiliatePayout
    years = {_now(now).year}
    for (paid_at,) in session.query(AffiliatePayout.paid_at).filter(
            AffiliatePayout.status == "paid", AffiliatePayout.paid_at.isnot(None)).all():
        years.add(afs._utc(paid_at).year)
    return sorted(years, reverse=True)


def tax_year_report(session, year: int) -> dict:
    """What was PAID to each partner in the calendar year (by the date the
    payout was marked paid, UTC), per currency. One row per (partner,
    currency): {code, name, email, country, form, form_label, form_received,
    currency, total, payouts, nec, note}. A row marked paid at its exported
    amount counts what was actually sent (paid_amount). Bookkeeping rows
    (carried / forfeited) are not payments and are left out."""
    import affiliate_ops as ops
    from models import Affiliate, AffiliateApplication, AffiliatePayout
    year = int(year)
    start = dt.datetime(year, 1, 1, tzinfo=UTC)
    end = dt.datetime(year + 1, 1, 1, tzinfo=UTC)
    paid = (session.query(AffiliatePayout)
            .filter(AffiliatePayout.status == "paid", AffiliatePayout.paid_at.isnot(None)).all())
    sums = {}
    for p in paid:
        when = afs._utc(p.paid_at)
        if when is None or not (start <= when < end):
            continue
        if (p.external_ref or "").strip().startswith(("carried:", "forfeited:")):
            continue
        amount = Decimal(str(p.paid_amount if p.paid_amount is not None else p.commission_amount or 0))
        if amount <= 0:
            continue
        key = (p.affiliate_id, (p.currency or "usd").lower())
        row = sums.setdefault(key, [Decimal("0"), 0])
        row[0] += amount
        row[1] += 1
    affs = {a.id: a for a in session.query(Affiliate).filter(
        Affiliate.id.in_({k[0] for k in sums} or {None})).all()} if sums else {}
    countries = {}
    for aid, country in (session.query(AffiliateApplication.affiliate_id, AffiliateApplication.country)
                         .filter(AffiliateApplication.affiliate_id.isnot(None))
                         .order_by(AffiliateApplication.created_at).all()):
        if country:
            countries[aid] = country
    rows = []
    for (aid, currency), (total, n) in sums.items():
        a = affs.get(aid)
        if a is None:
            continue
        form = a.tax_form_type if a.tax_form_received_at is not None else None
        nec = form == "w9" and currency == "usd" and total >= NEC_THRESHOLD
        note = ""
        if form is None:
            note = "No tax form on file - get one before filing"
        elif form == "w9" and currency != "usd":
            note = "W-9 partner paid in %s - convert to USD for the %s test" % (
                currency.upper(), "{:,.0f}".format(NEC_THRESHOLD))
        elif form == "w9" and not nec:
            note = "Under $%s" % "{:,.0f}".format(NEC_THRESHOLD)
        elif form in ("w8ben", "w8bene"):
            note = "Foreign partner (W-8): no 1099-NEC"
        rows.append({"code": a.code, "name": a.name, "email": a.email,
                     "country": countries.get(aid, ""), "form": form,
                     "form_label": ops.TAX_FORM_LABELS.get(form, "None on file"),
                     "form_received": afs._utc(a.tax_form_received_at),
                     "currency": currency, "total": total.quantize(Decimal("0.01")),
                     "payouts": n, "nec": bool(nec), "note": note})
    rows.sort(key=lambda r: (r["code"], r["currency"]))
    totals = {}
    for r in rows:
        totals[r["currency"]] = totals.get(r["currency"], Decimal("0")) + r["total"]
    return {"year": year, "rows": rows, "totals": sorted(totals.items()),
            "nec_count": sum(1 for r in rows if r["nec"]),
            "partners": len({r["code"] for r in rows})}


def tax_year_csv(report) -> str:
    import affiliate_ops as ops
    out = []
    for r in report["rows"]:
        out.append([r["code"], r["name"], r["email"], r["country"], r["form_label"],
                    r["form_received"].date().isoformat() if r["form_received"] else "",
                    r["currency"].upper(), "%.2f" % r["total"], str(r["payouts"]),
                    "yes" if r["nec"] else "no", r["note"]])
    return ops._csv_text(out, header=TAX_CSV_HEADER)


def tax_report_filename(year) -> str:
    return "tradewave-partner-payments-%d.csv" % int(year)


__all__ = ["program_counts", "waiting", "send_digest", "build_digest", "auto_approve_rules",
           "save_auto_approve", "try_auto_approve", "fraud_signals", "tax_year_report",
           "tax_year_csv", "activity_watch"]
