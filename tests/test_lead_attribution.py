import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lead_attribution import campaign_context, normalize_source, report_context, report_event, signup_context


def test_source_aliases_and_untrusted_values():
    assert normalize_source("hero") == "homepage_hero_report"
    assert normalize_source("homepage_sticky_report") == "homepage_sticky_report"
    assert normalize_source("private@example.com") == "other_report"
    assert normalize_source({}) == "home_free_report"


def test_campaign_context_drops_pii_and_unknown_fields():
    assert campaign_context({"utm_source": "youtube", "email": "x@example.com",
                             "utm_content": "x@example.com", "utm_campaign": "https://private/",
                             "utm_medium": ["email"], "tickers": ["AAPL"]}) == {"utm_source": "youtube"}
    assert campaign_context(None) == {}


def test_client_id_is_server_cookie_only():
    req = SimpleNamespace(cookies={"_ga": "GA1.1.123.456"})
    assert report_context(req, {"attribution": {"ga_client_id": "spoof"}}) == {"ga_client_id": "123.456"}
    assert report_context(SimpleNamespace(cookies={}), {}) == {}


def test_signup_context_has_stable_cta_ids():
    assert signup_context({"tw_cta": "homepage_hero_start_free"}) == {"cta_id": "homepage_hero_start_free"}
    assert signup_context({"tw_cta": "private@example.com"}) == {}
    assert signup_context({"utm_source": "lead_report", "utm_content": "hero"})["report_source"] == "homepage_hero_report"


def test_event_has_no_email_or_tickers_and_fails_open(monkeypatch):
    import ga4_mp
    send = MagicMock(return_value=True)
    monkeypatch.setattr(ga4_mp, "send_event", send)
    assert report_event("free_report_sent", "hero", {"ga_client_id": "123.456", "email": "x@y.com"}, 3)
    assert send.call_args.args == ("123.456", "free_report_sent", {"source": "homepage_hero_report", "ticker_count": 3})
    send.side_effect = RuntimeError("offline")
    assert report_event("free_report_sent", "hero", {}, 3) is False


@pytest.mark.parametrize("mode", ["signup", "open_app", "upgrade"])
def test_report_email_preserves_source_in_html_and_text(mode):
    import seasonal_report
    data = {"tickers": [], "not_covered": [], "as_of_label": "August 27, 2026"}
    for render in (seasonal_report.render_email_html, seasonal_report.render_email_text):
        output = render(data, cta_mode=mode, source="hero")
        assert "utm_content=homepage_hero_report" in output
        assert "utm_source=lead_report" in output


def test_home_card_and_csp_contract():
    root = Path(__file__).resolve().parents[1]
    template = (root / "site/templates/index-dark-blue.html").read_text()
    assert 'id="hero-report"' in template
    assert 'data-cta-id="homepage_hero_start_free"' in template
    assert "entry.intersectionRatio>=.5" in template
    assert template.count("gtag('event','free_report_open'") == 1
    for path in ("ops/nginx/snippets/security_headers.conf", "ops/staging/apply_audit_hardening.sh", "ops/staging/bootstrap_stage_web_services.sh"):
        source = (root / path).read_text()
        assert "https://www.googletagmanager.com" in source
        assert "https://*.google-analytics.com" in source
        assert "https://*.analytics.google.com" in source


@pytest.fixture
def report_db(db_session, _models_module, monkeypatch):
    mod = importlib.import_module("app")
    monkeypatch.setattr(mod, "DBSession", _models_module.Session)
    db_session.execute(_models_module.EmailLead.__table__.delete())
    db_session.commit()
    yield mod, db_session, _models_module
    db_session.execute(_models_module.EmailLead.__table__.delete())
    db_session.commit()


@pytest.mark.db
def test_update_preserves_attribution(report_db):
    app, session, m = report_db
    lead = m.EmailLead(email="report@example.com", source="hero", detail={"attribution": {"utm_source": "youtube"}})
    session.add(lead); session.commit()
    app._update_lead(lead.id, "sent", {"covered": ["AAPL"]}, sent=True)
    session.expire_all()
    saved = session.get(m.EmailLead, lead.id)
    assert saved.detail == {"attribution": {"utm_source": "youtube"}, "covered": ["AAPL"]}
    assert saved.sent_at is not None


@pytest.mark.db
def test_confirmed_leads_link_once_and_only_to_matching_account(report_db):
    from lead_attribution import link_confirmed_leads
    _, session, m = report_db
    now = datetime.now(timezone.utc)
    user = m.User(email="REPORT@example.com", roles=["user"], tier="explorer", email_verified=True)
    other = m.User(email="other@example.com", roles=["user"], tier="explorer")
    session.add_all([user, other]); session.commit()
    leads = [m.EmailLead(email="report@example.com", source="hero", status=status,
                        confirmed_at=now if confirmed else None, user_id=owner,
                        created_at=now-timedelta(days=1))
             for status, confirmed, owner in [("sent", True, None), ("pending_confirm", False, None),
                                               ("spam", True, None), ("sent", True, other.id)]]
    session.add_all(leads); session.commit()
    assert link_confirmed_leads(user.id, "wrong@example.com") == {}
    assert link_confirmed_leads(user.id, "") == {}
    assert link_confirmed_leads(user.id, "report@example.com") == {"report_source": "homepage_hero_report", "report_assisted": 1}
    session.expire_all()
    assert [session.get(m.EmailLead, lead.id).user_id for lead in leads] == [user.id, None, None, other.id]
    assert link_confirmed_leads(user.id, "report@example.com") == {}


@pytest.mark.db
def test_report_request_and_confirmation_lifecycle(report_db, monkeypatch):
    app, session, m = report_db
    import seasonal_report, ga4_mp, email_utils, threading
    events = MagicMock(return_value=True)
    monkeypatch.setattr(ga4_mp, "send_event", events)
    monkeypatch.setattr(app, "get_current_user", lambda: None)
    monkeypatch.setattr(app, "_is_suppressed", lambda email: False)
    monkeypatch.setattr(app, "account_cta_mode", lambda email: "signup")
    monkeypatch.setattr(seasonal_report, "resolve_coverage", lambda tickers: {"covered": tickers, "not_covered": []})
    monkeypatch.setattr(app.config, "LEAD_EMAIL_FROM", "unit@example.com", raising=False)
    sender = MagicMock(return_value=True)
    monkeypatch.setattr(email_utils, "resend_send_email", sender)
    monkeypatch.setattr(email_utils, "mailerlite_subscribe", lambda email: None)
    class ImmediateThread:
        def __init__(self, target, args, **kwargs): self.target, self.args = target, args
        def start(self): self.target(*self.args)
    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    rep = {"tickers": [{"symbol": "AAPL"}], "not_covered": [], "as_of": datetime.now(timezone.utc)}
    monkeypatch.setattr(seasonal_report, "build_report_data", lambda tickers: rep)
    html = MagicMock(return_value="report")
    monkeypatch.setattr(seasonal_report, "render_email_html", html)
    monkeypatch.setattr(seasonal_report, "render_email_text", lambda *args, **kwargs: "report")
    with app.app.test_client() as client:
        client.set_cookie("_ga", "GA1.1.123.456")
        response = client.post("/api/lead-report", json={"email": "report@example.com", "tickers": ["aapl"],
                             "source": "hero", "attribution": {"utm_source": "youtube"}})
        assert response.status_code == 200
        lead = session.query(m.EmailLead).one()
        assert lead.source == "homepage_hero_report"
        assert lead.detail["attribution"]["utm_source"] == "youtube"
        token = lead.confirm_token
        assert client.get("/api/lead-report/confirm", query_string={"token": token}).status_code == 200
        assert client.get("/api/lead-report/confirm", query_string={"token": token}).status_code == 200
    assert [call.args[1] for call in events.call_args_list] == ["free_report_submitted", "free_report_confirmed", "free_report_sent"]
    assert sender.call_count == 2
    assert html.call_args.kwargs["source"] == "homepage_hero_report"
    session.expire_all()
    assert session.query(m.EmailLead).one().detail["attribution"]["utm_source"] == "youtube"


@pytest.mark.parametrize("verified", [False, True])
@pytest.mark.parametrize("new_signup", [False, True])
def test_auth_attribution_is_verified_fail_open_and_consumed(monkeypatch, verified, new_signup):
    app = importlib.import_module("app")
    import lead_attribution
    identity = SimpleNamespace(email="report@example.com", email_verified=verified,
                               to_dict=lambda: {"email": "report@example.com"})
    provider = MagicMock()
    provider.user_management.authenticate_with_code.return_value = SimpleNamespace(
        user=identity, impersonator=None, access_token="test", refresh_token="test")
    monkeypatch.setattr(app, "workos_client", provider)
    monkeypatch.setattr(app, "seal_session_from_auth_response", lambda **kwargs: "test-sealed-session")
    monkeypatch.setattr(app, "lazy_create_user", lambda identity: SimpleNamespace(id="test-id", _tw_new_signup=new_signup))
    monkeypatch.setattr(app, "DBSession", MagicMock())
    link = MagicMock(side_effect=RuntimeError("attribution unavailable"))
    monkeypatch.setattr(lead_attribution, "link_confirmed_leads", link)
    analytics = MagicMock(side_effect=RuntimeError("analytics unavailable"))
    monkeypatch.setattr(app, "send_event", analytics)
    monkeypatch.setattr(app, "write_audit", MagicMock(side_effect=RuntimeError("audit unavailable")))
    monkeypatch.setitem(app.app.config, "SECRET_KEY", "unit-test-only")
    with app.app.test_client() as client:
        with client.session_transaction() as session:
            session["signup_attribution"] = {"cta_id": "homepage_hero_start_free"}
        response = client.get("/auth/callback?code=test&state=/account")
        assert response.status_code == 302
        assert response.location == "/account"
        with client.session_transaction() as session:
            assert "signup_attribution" not in session
    assert link.call_count == int(verified)
    assert analytics.call_count == int(new_signup)


def test_signup_entry_retains_source_even_when_analytics_fails(monkeypatch):
    app = importlib.import_module("app")
    monkeypatch.setattr(app, "_get_authorization_url", lambda **kwargs: "https://auth.example.test/signup")
    monkeypatch.setattr(app, "send_event", MagicMock(side_effect=RuntimeError("analytics unavailable")))
    monkeypatch.setitem(app.app.config, "SECRET_KEY", "unit-test-only")
    with app.app.test_client() as client:
        response = client.get("/signup?utm_source=lead_report&utm_content=homepage_hero_report")
        assert response.status_code == 302
        with client.session_transaction() as session:
            assert session["signup_attribution"]["report_source"] == "homepage_hero_report"
