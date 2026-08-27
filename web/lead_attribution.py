"""Small, privacy-bounded attribution helpers for the free-report funnel.

Postgres is authoritative for confirmation, delivery and account linkage. GA4
is a best-effort mirror, never a prerequisite for those operations.
"""
import re
from datetime import datetime, timezone


REPORT_SOURCES = {
    "homepage_hero_report", "homepage_pricing_report", "homepage_sticky_report",
    "homepage_direct_report", "home_free_report", "webinar_report",
    "youtube_report", "creator_report", "podcast_report", "other_report",
}
SOURCE_ALIASES = {
    "hero": "homepage_hero_report", "pricing": "homepage_pricing_report",
    "sticky": "homepage_sticky_report", "webinar": "webinar_report",
    "youtube": "youtube_report", "creator": "creator_report", "podcast": "podcast_report",
}
SIGNUP_CTAS = {"homepage_hero_start_free", "homepage_header_start_free",
               "homepage_other_cta", "report_email_start_free"}


def signup_context(args):
    context = campaign_context(dict(args))
    cta = args.get("tw_cta")
    if cta in SIGNUP_CTAS:
        context["cta_id"] = cta
    if context.get("utm_source") == "lead_report":
        context["cta_id"] = "report_email_start_free"
        context["report_source"] = normalize_source(context.get("utm_content"))
    return context


def normalize_source(value):
    if not isinstance(value, str):
        return "home_free_report"
    value = value.strip().lower()
    value = SOURCE_ALIASES.get(value, value)
    return value if value in REPORT_SOURCES else "other_report"


def campaign_context(value):
    """Only campaign labels: never email, ticker text, URLs or arbitrary fields."""
    if not isinstance(value, dict):
        return {}
    return {k: v for k in ("utm_source", "utm_medium", "utm_campaign", "utm_content")
            if isinstance((v := value.get(k)), str)
            and re.fullmatch(r"[a-zA-Z0-9 _.-]{1,100}", v)}


def report_context(request, data):
    from ga4_mp import parse_ga_client_id
    context = campaign_context(data.get("attribution"))
    client_id = parse_ga_client_id(request)
    if client_id and re.fullmatch(r"\d{1,20}\.\d{1,20}", client_id):
        context["ga_client_id"] = client_id
    return context


def report_event(name, source, context, count):
    """Analytics cannot interrupt report delivery, even if the adapter raises."""
    try:
        from ga4_mp import send_event
        return send_event((context or {}).get("ga_client_id"), name, {
            "source": normalize_source(source), "ticker_count": count,
        })
    except Exception:
        return False


def link_confirmed_leads(user_id, verified_email):
    """Call only after identity-provider email verification. Never reassign a lead.

Use an independent session so a failure cannot roll back authentication or billing.
The link is report-assisted attribution, not proof that a report caused signup.
"""
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session
    from models import EmailLead, User, engine

    if not verified_email:
        return {}
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user or user.email.strip().lower() != verified_email.strip().lower():
            return {}
        leads = session.scalars(select(EmailLead).where(
            func.lower(EmailLead.email) == verified_email.strip().lower(),
            EmailLead.confirmed_at.is_not(None),
            EmailLead.status.in_(("pending_confirm", "sent", "failed")),
            EmailLead.user_id.is_(None),
        ).order_by(EmailLead.created_at).with_for_update()).all()
        source = None
        for lead in leads:
            lead.user_id = user.id
            lead.detail = {**(lead.detail or {}), "account_linked_at": datetime.now(timezone.utc).isoformat()}
            if source is None and lead.created_at <= user.created_at:
                source = normalize_source(lead.source)
        session.commit()
        return {"report_source": source, "report_assisted": 1} if source else {}
