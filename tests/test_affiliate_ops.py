"""Affiliate operations + growth tools (TW-TASK-0039 package C).

Hermetic like the other affiliate suites: SQLite copy of the tables, fake
Stripe, temp folders for files, Resend never called.

Covered: secure tax-form upload (validation, encryption at rest, storage
outside the web root, admin-only download with an audit entry, accept
satisfies the payout gate, reject shows the reason), named sub-links (stored
with click / signup / referral, never change who earns, per-link and
per-campaign numbers), bulk payouts (PayPal + Wise CSV formats, per currency,
bulk mark-paid through the same gate, nothing is paid by an export), the
creative library, and the monthly operations summary (read-only, one email).
"""
import csv
import datetime as dt
import importlib
import io
import os
import stat
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import affiliate_portal_harness as h  # noqa: E402

import affiliate_ops as ops  # noqa: E402
import affiliate_ops_models as om  # noqa: E402
import affiliate_ops_summary as summ  # noqa: E402
import affiliate_service as afs  # noqa: E402

pytestmark = pytest.mark.unit

UTC = dt.timezone.utc
BASE = "/account/affiliate"
EM_DASH = "—"
OPS_TABLES = ["affiliate_tax_forms", "affiliate_sublinks", "affiliate_sublink_clicks",
              "affiliate_creatives"]
PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
PNG = None


def png_bytes(size=(728, 90)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, (40, 30, 90)).save(buf, "PNG")
    return buf.getvalue()


def D(v):
    return Decimal(str(v))


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Portal app + DB with the ops tables, a tax-form key, and temp folders:
    web root, tax-form folder (outside it) and the creative folder."""
    import config
    from cryptography.fernet import Fernet
    monkeypatch.setattr(h, "TABLES", h.all_tables())
    web_root = tmp_path / "www"
    web_root.mkdir()
    monkeypatch.setattr(config, "web_root_dir", str(web_root) + "/")
    monkeypatch.setattr(config, "TAX_FORM_KEY", Fernet.generate_key().decode(), raising=False)
    monkeypatch.setattr(config, "TAX_FORM_DIR", str(tmp_path / "private" / "tax"), raising=False)
    monkeypatch.setattr(config, "AFFILIATE_CREATIVE_DIR", str(web_root / "assets" / "affiliate-creatives"),
                        raising=False)
    db, factory, engine = h.make_db()
    state = SimpleNamespace(user=None, catalog=h.CATALOG)
    world = h.fake_stripe(monkeypatch.setattr)
    app = h.make_app(monkeypatch.setattr, factory, state)
    notes = []
    from affiliate_portal import routes
    monkeypatch.setattr(routes, "_notify_operator", lambda subject, body: notes.append((subject, body)))
    yield SimpleNamespace(db=db, factory=factory, state=state, world=world, app=app, notes=notes,
                          client=app.test_client(), patch=monkeypatch, tmp=tmp_path, web_root=web_root)
    db.close()
    engine.dispose()


def login(env, user):
    env.state.user = user


def page(env, path):
    r = env.client.get(BASE + path)
    assert r.status_code == 200, (path, r.status_code)
    return r.get_data(as_text=True)


def flashes(env):
    with env.client.session_transaction() as sess:
        return [m for _c, m in sess.pop("_flashes", [])]


def upload(env, blob=PDF, name="w9.pdf", mime="application/pdf", form_type="w9"):
    return env.client.post(BASE + "/tax-form", data={
        "form_type": form_type, "tax_form": (io.BytesIO(blob), name, mime)},
        content_type="multipart/form-data")


def partner(env, code="ANNE", **kw):
    kw.setdefault("tax_form_type", None)
    kw.setdefault("tax_form_received_at", None)
    return h.make_partner(env.db, code, **kw)


def forms(env):
    env.db.expire_all()
    return env.db.query(om.AffiliateTaxForm).order_by(om.AffiliateTaxForm.id).all()


# ---------------------------------------------------------------------------
# admin app (the real web/app.py views on the SQLite copy)
# ---------------------------------------------------------------------------
@pytest.fixture
def admin(env, monkeypatch):
    import models
    mod = importlib.import_module("app")
    audits = []

    def audit(**kw):
        audits.append(kw)
        s = env.factory()
        s.add(models.AuditLog(actor_label=kw.get("actor_label"), action=kw.get("action"),
                              details=kw.get("details")))
        s.commit()
        s.close()
    who = SimpleNamespace(user=SimpleNamespace(id=None, email="afshin@example.com", roles=["super_admin"]))
    monkeypatch.setattr(mod, "get_current_user", lambda: who.user)
    monkeypatch.setattr(mod, "write_audit", audit)
    monkeypatch.setattr(models, "Session", env.factory)
    monkeypatch.setitem(mod.app.config, "WTF_CSRF_ENABLED", False)
    sent = []
    import email_utils
    monkeypatch.setattr(email_utils, "resend_send_email",
                        lambda **kw: sent.append(kw) or True)
    return SimpleNamespace(client=mod.app.test_client(), audits=audits, mod=mod, who=who, sent=sent)


# ===========================================================================
# 1. Tax forms
# ===========================================================================
class TestTaxFormUpload:
    def test_refused_when_the_key_is_unset(self, env):
        import config
        aff, user = partner(env)
        login(env, user)
        env.patch.setattr(config, "TAX_FORM_KEY", "")
        assert ops.tax_upload_enabled() is False
        assert upload(env).status_code == 302
        assert "Secure upload is not available right now" in flashes(env)[0]
        assert forms(env) == [] and not (env.tmp / "private").exists()
        html = page(env, "/payouts")
        assert "Secure upload is not available right now" in html and 'name="tax_form"' not in html
        # the existing guidance stays while upload is off
        assert "secure upload link" in html

    def test_a_malformed_key_counts_as_unset(self, env):
        import config
        env.patch.setattr(config, "TAX_FORM_KEY", "not-a-fernet-key")
        assert ops.tax_upload_enabled() is False
        aff, _user = partner(env)
        with pytest.raises(ops.OpsError):
            ops.store_tax_form(env.db, aff, "w9", "w9.pdf", "application/pdf", PDF)

    def test_storage_folder_inside_the_web_root_switches_upload_off(self, env):
        import config
        env.patch.setattr(config, "TAX_FORM_DIR", str(env.web_root / "assets" / "tax"))
        assert ops.tax_upload_enabled() is False

    @pytest.mark.parametrize("blob,name,mime,needle", [
        (b"", "w9.pdf", "application/pdf", "empty"),
        (b"GIF89a not a pdf %%EOF", "w9.pdf", "application/pdf", "not a valid PDF"),
        (b"<html>%PDF-1.4 %%EOF</html>", "w9.pdf", "application/pdf", "not a valid PDF"),
        (b"%PDF-1.7 truncated, no end marker", "w9.pdf", "application/pdf", "not a valid PDF"),
        (PDF, "w9.exe", "application/pdf", "PDF file"),
        (PDF, "w9.pdf.html", "application/pdf", "PDF file"),
        (PDF, "w9.pdf", "text/html", "PDF file"),
        (PDF + b"x" * (5 * 1024 * 1024), "w9.pdf", "application/pdf", "too large"),
    ])
    def test_bad_files_are_refused_and_nothing_is_stored(self, env, blob, name, mime, needle):
        aff, user = partner(env)
        login(env, user)
        assert upload(env, blob, name, mime).status_code == 302
        assert needle in flashes(env)[0]
        assert forms(env) == []
        folder = env.tmp / "private" / "tax"
        assert not folder.exists() or list(folder.iterdir()) == []

    def test_form_type_is_required(self, env):
        aff, user = partner(env)
        login(env, user)
        upload(env, form_type="1099")
        assert "Choose which form" in flashes(env)[0] and forms(env) == []

    def test_upload_is_encrypted_at_rest_outside_the_web_root(self, env):
        import config
        from cryptography.fernet import Fernet
        aff, user = partner(env)
        login(env, user)
        assert upload(env, form_type="w8ben").status_code == 302
        assert "we have your W-8BEN" in flashes(env)[0]
        row = forms(env)[0]
        assert (row.status, row.form_type, row.size_bytes) == ("received", "w8ben", len(PDF))
        assert row.original_filename == "w9.pdf" and row.uploaded_by_user_id == user.id
        folder = Path(config.TAX_FORM_DIR)
        stored = folder / row.storage_name
        assert env.web_root not in stored.resolve().parents            # never under the web root
        raw = stored.read_bytes()
        assert b"%PDF" not in raw and PDF not in raw                    # ciphertext only
        assert Fernet(config.TAX_FORM_KEY.encode()).decrypt(raw) == PDF
        assert stat.S_IMODE(os.stat(stored).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700
        assert ops.read_tax_form(row) == PDF
        # the operator is told, without the file or any tax detail
        # (fix-0039: with a deep link to the exact admin page)
        ((subject, note),) = env.notes
        assert subject == "Affiliate tax form to review: ANNE"
        assert note.startswith("Affiliate ANNE uploaded a W-8BEN. Review it here:\n")
        assert note.endswith("/admin/affiliate_tax_forms/")
        # not yet accepted: the payout gate is still closed
        env.db.refresh(aff)
        assert aff.tax_form_received_at is None
        html = page(env, "/payouts")
        assert "Being reviewed" in html and "Received - being reviewed" in html
        assert "We have your form and are reviewing it." in html
        assert "Upload securely" in html and EM_DASH not in html

    def test_a_new_upload_replaces_the_one_waiting_and_deletes_its_file(self, env):
        import config
        aff, user = partner(env)
        login(env, user)
        upload(env)
        first = forms(env)[0].storage_name
        upload(env, form_type="w8bene")
        a, b = forms(env)
        assert (a.status, a.storage_name) == ("replaced", None)
        assert (b.status, b.form_type) == ("received", "w8bene")
        assert not (Path(config.TAX_FORM_DIR) / first).exists()

    def test_upload_rate_limit(self, env):
        aff, user = partner(env)
        login(env, user)
        for _ in range(ops.TAX_UPLOADS_PER_DAY):
            upload(env)
            flashes(env)
        upload(env)
        assert "several forms today" in flashes(env)[0]
        assert len(forms(env)) == ops.TAX_UPLOADS_PER_DAY

    def test_key_rotation_keeps_old_files_readable(self, env):
        import config
        from cryptography.fernet import Fernet
        aff, _user = partner(env)
        row = ops.store_tax_form(env.db, aff, "w9", "w9.pdf", "application/pdf", PDF)
        old = config.TAX_FORM_KEY
        env.patch.setattr(config, "TAX_FORM_KEY", Fernet.generate_key().decode() + "," + old)
        assert ops.read_tax_form(row) == PDF
        env.patch.setattr(config, "TAX_FORM_KEY", Fernet.generate_key().decode())
        with pytest.raises(ops.OpsError) as e:
            ops.read_tax_form(row)
        assert "could not be decrypted" in str(e.value)

    def test_logged_out_and_non_partners_cannot_upload(self, env):
        assert upload(env).status_code == 302                      # to /login
        login(env, h._user(env.db, "nobody@example.com"))
        r = upload(env)
        assert r.status_code == 200 and forms(env) == []


class TestTaxFormAdmin:
    def _uploaded(self, env, code="ANNE"):
        aff, user = partner(env, code)
        row = ops.store_tax_form(env.db, aff, "w9", "w9.pdf", "application/pdf", PDF, user_id=user.id)
        return aff, user, row

    def test_download_is_admin_only(self, env, admin):
        aff, user, row = self._uploaded(env)
        admin.who.user = SimpleNamespace(id=None, email="x@example.com", roles=["user"])
        for url in ("/admin/affiliate_tax_forms/", "/admin/affiliate_tax_forms/download/%d" % row.id,
                    "/admin/affiliate_bulk_payouts/", "/admin/affiliate_creatives/"):
            assert admin.client.get(url).status_code == 403, url
        assert admin.client.post("/admin/affiliate_tax_forms/accept/%d" % row.id).status_code == 403
        assert admin.audits == []
        # and there is no partner-side route that serves a stored form
        login(env, user)
        assert env.client.get(BASE + "/tax-form").status_code == 405

    def test_download_returns_the_pdf_and_writes_an_audit_entry(self, env, admin):
        import models
        aff, user, row = self._uploaded(env)
        r = admin.client.get("/admin/affiliate_tax_forms/download/%d" % row.id)
        assert r.status_code == 200 and r.data == PDF
        assert r.mimetype == "application/pdf" and "attachment" in r.headers["Content-Disposition"]
        assert "no-store" in r.headers["Cache-Control"]
        entry = env.db.query(models.AuditLog).filter_by(action="affiliate_tax_form_downloaded").one()
        assert entry.actor_label == "admin:afshin@example.com"
        assert entry.details["form_id"] == row.id and entry.details["affiliate"] == "ANNE"

    def test_no_audit_entry_no_download(self, env, admin, monkeypatch):
        aff, user, row = self._uploaded(env)

        def boom(**kw):
            raise RuntimeError("audit store down")
        monkeypatch.setattr(admin.mod, "write_audit", boom)
        monkeypatch.setitem(admin.mod.app.config, "PROPAGATE_EXCEPTIONS", False)
        r = admin.client.get("/admin/affiliate_tax_forms/download/%d" % row.id)
        assert r.status_code == 500 and PDF not in r.data

    def test_accept_satisfies_the_payout_gate(self, env, admin):
        import models
        import affiliate_admin as afa
        import config
        env.patch.setattr(config, "RESEND_API_KEY", "re_test_key", raising=False)
        aff, user, row = self._uploaded(env)
        payout = models.AffiliatePayout(affiliate_id=aff.id, period_start=dt.date(2026, 10, 1),
                                        period_end=dt.date(2026, 10, 31), currency="usd",
                                        gross_revenue=D(200), commission_amount=D(100), status="pending")
        env.db.add(payout)
        env.db.commit()
        assert "no tax form on file" in afa.payout_block_reason(payout, aff)
        html = admin.client.get("/admin/affiliate_tax_forms/").get_data(as_text=True)
        assert "Waiting for review (1)" in html and "ANNE" in html and EM_DASH not in html
        assert admin.client.post("/admin/affiliate_tax_forms/accept/%d" % row.id).status_code == 302
        env.db.expire_all()
        aff = env.db.get(models.Affiliate, aff.id)
        assert aff.tax_form_type == "w9" and aff.tax_form_received_at is not None
        assert afa.payout_block_reason(payout, aff) is None                # the existing gate opens
        row = forms(env)[0]
        assert (row.status, row.reviewed_by) == ("accepted", "admin:afshin@example.com")
        assert [a["action"] for a in admin.audits] == ["affiliate_tax_form_accepted"]
        assert admin.sent[0]["to"] == aff.email and EM_DASH not in admin.sent[0]["body_text"]
        login(env, user)
        html = page(env, "/payouts")
        assert "W-9 on file" in html and "Accepted" in html
        assert "Your form is on file. Upload a new one only if your details changed." in html

    def test_reject_needs_a_reason_shows_it_to_the_partner_and_deletes_the_file(self, env, admin):
        import config
        import models
        aff, user, row = self._uploaded(env)
        stored = Path(config.TAX_FORM_DIR) / row.storage_name
        admin.client.post("/admin/affiliate_tax_forms/reject/%d" % row.id, data={"reason": "no"})
        assert forms(env)[0].status == "received" and stored.exists()
        admin.client.post("/admin/affiliate_tax_forms/reject/%d" % row.id,
                          data={"reason": "The form is not signed. Please sign and date line 3."})
        row = forms(env)[0]
        assert row.status == "rejected" and row.storage_name is None and not stored.exists()
        assert env.db.get(models.Affiliate, aff.id).tax_form_received_at is None
        assert admin.audits[-1]["action"] == "affiliate_tax_form_rejected"
        login(env, user)
        html = page(env, "/payouts")
        assert "Needs a new upload" in html and "What to fix" in html
        assert "The form is not signed. Please sign and date line 3." in html
        # a reviewed form cannot be accepted afterwards
        admin.client.post("/admin/affiliate_tax_forms/accept/%d" % row.id)
        assert forms(env)[0].status == "rejected"

    def test_accepting_a_newer_form_replaces_the_one_on_file(self, env, admin):
        aff, user, row = self._uploaded(env)
        ops.accept_tax_form(env.db, row, "admin:x")
        newer = ops.store_tax_form(env.db, aff, "w8ben", "w8.pdf", "application/pdf", PDF)
        assert [f.status for f in forms(env)] == ["accepted", "received"]   # old stays on file meanwhile
        ops.accept_tax_form(env.db, newer, "admin:x")
        a, b = forms(env)
        assert (a.status, a.storage_name, b.status) == ("replaced", None, "accepted")
        env.db.refresh(aff)
        assert aff.tax_form_type == "w8ben"


# ===========================================================================
# 2. Sub-links
# ===========================================================================
class TestSubLinks:
    def test_slug_rules(self):
        assert afs.normalize_sub("YouTube") == "youtube"
        assert afs.normalize_sub("march-newsletter_2") == "march-newsletter_2"
        for bad in ("", None, "a b", "-lead", "x" * 41, "<script>", "you/tube", 7):
            assert afs.normalize_sub(bad) is None
        assert ops.slugify_sub("  My March Newsletter! ") == "my-march-newsletter"

    def test_create_archive_and_ownership(self, env):
        anne, user = partner(env)
        bob, bob_user = partner(env, "BOB")
        login(env, user)
        assert env.client.post(BASE + "/links/sub", data={"name": "YouTube"}).status_code == 302
        assert "Link youtube created" in flashes(env)[0]
        env.client.post(BASE + "/links/sub", data={"name": "youtube"})
        assert "already have a link named youtube" in flashes(env)[0]
        env.client.post(BASE + "/links/sub", data={"name": "!!!"})
        assert "short name" in flashes(env)[0]
        row = env.db.query(om.AffiliateSublink).one()
        assert (row.affiliate_id, row.sub) == (anne.id, "youtube")
        # another partner cannot archive it
        login(env, bob_user)
        env.client.post(BASE + "/links/sub/%d/archive" % row.id)
        assert "not found" in flashes(env)[0]
        env.db.expire_all()
        assert env.db.query(om.AffiliateSublink).one().archived_at is None
        login(env, user)
        env.client.post(BASE + "/links/sub/%d/archive" % row.id)
        env.db.expire_all()
        assert env.db.query(om.AffiliateSublink).one().archived_at is not None

    def test_link_limit(self, env):
        anne, _ = partner(env)
        env.patch.setattr(ops, "MAX_SUBLINKS", 2)
        ops.create_sublink(env.db, anne, "one")
        ops.create_sublink(env.db, anne, "two")
        with pytest.raises(ops.OpsError):
            ops.create_sublink(env.db, anne, "three")

    def test_clicks_count_only_registered_links_and_not_refreshes(self, env):
        anne, _ = partner(env)
        bob, _b = partner(env, "BOB")
        ops.create_sublink(env.db, anne, "youtube")
        assert ops.record_sub_click(env.db, anne, "YouTube") == "youtube"
        assert ops.record_sub_click(env.db, anne, "youtube") == "youtube"
        assert ops.record_sub_click(env.db, anne, "youtube", "ANNE:youtube") is None     # refresh
        assert ops.record_sub_click(env.db, anne, "youtube", "BOB:youtube") == "youtube"  # other partner's tag
        assert ops.record_sub_click(env.db, anne, "made-up") is None                      # not registered
        assert ops.record_sub_click(env.db, bob, "youtube") is None                       # not Bob's link
        assert ops.record_sub_click(env.db, anne, "<x>") is None
        rows = env.db.query(om.AffiliateSublinkClick).all()
        assert [(r.clicks) for r in rows] == [3]

    def test_the_cookie_tag_never_travels_to_another_partner(self):
        assert afs.sub_from_cookie("ANNE:youtube", "anne") == "youtube"
        assert afs.sub_from_cookie("ANNE:youtube", "BOB") is None
        for bad in ("youtube", "", None, ":youtube", "ANNE:", "ANNE:<b>"):
            assert afs.sub_from_cookie(bad, "ANNE") is None

    def test_checkout_tag_follows_the_resolved_partner_only(self):
        offer = {"affiliate_code": "ANNE", "affiliate_id": "id-anne"}
        buyer = SimpleNamespace(referred_by_affiliate_id="id-anne", referred_sub="bio")
        assert ops.checkout_sub(offer, buyer, "YouTube", "ANNE:podcast") == "youtube"   # link wins
        assert ops.checkout_sub(offer, buyer, None, "ANNE:podcast") == "podcast"        # then the cookie
        assert ops.checkout_sub(offer, buyer, None, "BOB:podcast") == "bio"             # then the signup stamp
        other = SimpleNamespace(referred_by_affiliate_id="id-bob", referred_sub="bio")
        assert ops.checkout_sub(offer, other, None, "BOB:podcast") is None
        # a direct sale is never tagged
        assert ops.checkout_sub({"affiliate_code": None, "affiliate_id": None}, buyer, "youtube",
                                "ANNE:youtube") is None
        assert ops.checkout_sub({}, buyer, "youtube", None) is None

    def test_signup_stamp_stores_the_sub_and_credit_is_unchanged(self, env):
        import models
        anne, _ = partner(env)
        bob, _b = partner(env, "BOB")
        u1 = h._user(env.db, "new1@example.com")
        assert afs.record_signup_referral(env.db, u1, "anne", "ANNE:youtube") is True
        assert (u1.referred_by_affiliate_id, u1.referred_sub) == (anne.id, "youtube")
        # a tag that belongs to another partner is dropped; Anne still gets the signup
        u2 = h._user(env.db, "new2@example.com")
        assert afs.record_signup_referral(env.db, u2, "ANNE", "BOB:youtube") is True
        assert (u2.referred_by_affiliate_id, u2.referred_sub) == (anne.id, None)
        # old two-argument call still works
        u3 = h._user(env.db, "new3@example.com")
        assert afs.record_signup_referral(env.db, u3, "BOB") is True
        assert (u3.referred_by_affiliate_id, u3.referred_sub) == (bob.id, None)
        assert models.User.referred_sub is not None

    def test_referral_row_stores_the_sub_and_the_same_partner(self, env):
        import models
        anne, _ = partner(env)

        def sub(sid, **md):
            base = {"tw2_affiliate_id": str(anne.id), "tw2_affiliate_code": "ANNE",
                    "tw2_affiliate_source": "checkout", "tw2_terms_id": "1",
                    "tw2_offer_type": "regular", "tw2_list_price_cents": "39900",
                    "tw2_discount_pct": "20.00", "tier": "analyst"}
            base.update(md)
            return {"id": sid, "customer": "cus_" + sid, "metadata": base,
                    "items": {"data": [{"price": {"unit_amount": 39900, "recurring": {"interval": "year"}}}]}}
        assert afs.record_referral_from_subscription(env.db, sub("sub_a", tw2_affiliate_sub="youtube"))
        assert afs.record_referral_from_subscription(env.db, sub("sub_b"))
        assert afs.record_referral_from_subscription(env.db, sub("sub_c", tw2_affiliate_sub="<bad>"))
        env.db.commit()
        rows = {r.stripe_subscription_id: r for r in env.db.query(models.AffiliateReferral).all()}
        assert rows["sub_a"].sub_link == "youtube" and rows["sub_b"].sub_link is None
        assert rows["sub_c"].sub_link is None
        # the tag changes nothing about who earns or on what terms
        for r in rows.values():
            assert (r.affiliate_id, r.terms_id, r.offer_type, r.discount_pct, r.list_price_cents) == (
                anne.id, 1, "regular", D(20), 39900)

    def test_engine_never_reads_the_sub(self):
        import inspect
        engine_src = inspect.getsource(afs._compute) + inspect.getsource(afs.classify_invoice) \
            + inspect.getsource(afs.resolve_checkout_offer)
        assert "sub_link" not in engine_src and "referred_sub" not in engine_src
        assert "tw2_affiliate_sub" not in engine_src

    def _seed_stats(self, env):
        import models
        now = dt.datetime.now(UTC)
        anne, user = h.seed_rich(env.db, env.world)
        camp = env.db.query(models.PromoCampaign).one()
        yt = ops.create_sublink(env.db, anne, "YouTube channel")
        bf = ops.create_sublink(env.db, anne, "bf-email", campaign_id=camp.id)
        ops.create_sublink(env.db, anne, "unused")
        for _ in range(5):
            ops.record_sub_click(env.db, anne, yt.sub)
        for _ in range(3):
            ops.record_sub_click(env.db, anne, bf.sub)
        refs = {r.stripe_subscription_id: r for r in env.db.query(models.AffiliateReferral).all()}
        refs["sub_ANNE_1"].sub_link = yt.sub        # annual, year 1 paid 119.70 + renewal 99.75
        refs["sub_ANNE_5"].sub_link = yt.sub        # 8.70 then refunded -8.70; a lapsed line
        refs["sub_ANNE_3"].sub_link = bf.sub        # the Black Friday customer, 49.50
        users = env.db.query(models.User).filter(models.User.referred_by_affiliate_id == anne.id).all()
        users[0].referred_sub = yt.sub
        users[1].referred_sub = yt.sub
        users[2].referred_sub = bf.sub
        env.db.commit()
        assert now is not None
        return anne, user, camp

    def test_numbers_per_link_and_per_campaign(self, env):
        anne, user, camp = self._seed_stats(env)
        st = ops.link_stats(env.db, anne)
        rows = {r["sub"]: r for r in st["sublinks"]}
        yt, bf = rows["youtube-channel"], rows["bf-email"]
        assert (yt["label"], yt["clicks"], yt["signups"], yt["paid"]) == ("YouTube channel", 5, 2, 2)
        assert yt["earned_cents"] == 11970 + 9975 + 870 - 870
        assert (bf["clicks"], bf["signups"], bf["paid"], bf["earned_cents"]) == (3, 1, 1, 4950)
        assert bf["campaign"] == "Black Friday"
        assert rows["unused"]["clicks"] == rows["unused"]["paid"] == rows["unused"]["earned_cents"] == 0
        assert yt["urls"]["join"].endswith("/join/ANNE?sub=youtube-channel")
        assert yt["urls"]["referral"].endswith("/?code=ANNE&sub=youtube-channel")
        # every column adds up to the partner's totals
        t, u = st["totals"], st["untagged"]
        assert t["clicks"] == 278 and t["signups"] == 9 and t["paid"] == 4
        for col in ("clicks", "signups", "paid", "earned_cents"):
            assert sum(r[col] for r in st["sublinks"]) + u[col] == t[col], col
        assert st["campaigns"] == [{"name": "Black Friday", "live": True, "starts_at": camp.starts_at,
                                    "clicks": 3, "signups": 1, "paid": 1, "earned_cents": 4950}]

    def test_links_page_shows_the_stats_without_customer_identities(self, env):
        anne, user, camp = self._seed_stats(env)
        login(env, user)
        html = page(env, "/links")
        assert "Tracked links" in html and "YouTube channel" in html and "bf-email" in html
        assert "/join/ANNE?sub=youtube-channel" in html
        assert "Your main link or typed code" in html and "All links" in html
        assert "$219.45" in html and "$49.50" in html
        assert '<h3>Promotions</h3>' in html and "Black Friday" in html
        assert 'id="lb-sub"' in html and '<option value="bf-email">' in html
        assert 'name="campaign_id"' in html            # a live promotion can be picked
        assert EM_DASH not in html
        for email in h.SECRET_EMAILS:
            assert email not in html
        assert "cus_ANNE" not in html and "sub_ANNE" not in html

    def test_links_page_without_any_sublink(self, env):
        anne, user = partner(env)
        login(env, user)
        html = page(env, "/links")
        assert "No tracked links yet" in html and 'id="lb-sub"' not in html
        assert '<h3>Promotions</h3>' not in html

    def test_the_qr_route_accepts_a_sub_link(self, env):
        import affiliate_agreement as agr
        anne, user = partner(env)
        login(env, user)
        r = env.client.get(BASE + "/qr.svg", query_string={"u": agr._base() + "/join/ANNE?sub=youtube"})
        assert r.status_code == 200 and r.mimetype == "image/svg+xml"


class TestSubLinkWiring:
    """web/app.py: ?sub= on /join/<code>, /pricing and the click beacon."""

    @pytest.fixture
    def site(self, env, monkeypatch):
        mod = importlib.import_module("app")
        monkeypatch.setattr(mod, "DBSession", env.factory)
        monkeypatch.setattr(mod, "_display_offers", lambda s, aff: {})
        anne, _ = partner(env)
        ops.create_sublink(env.db, anne, "youtube")
        return SimpleNamespace(client=mod.app.test_client(), mod=mod, anne=anne)

    def _clicks(self, env):
        import models
        env.db.expire_all()
        total = sum(r.clicks for r in env.db.query(models.AffiliateClick).all())
        sub = sum(r.clicks for r in env.db.query(om.AffiliateSublinkClick).all())
        return total, sub

    def test_join_page_sets_both_cookies_and_counts_both_clicks(self, env, site):
        r = site.client.get("/join/anne?sub=YouTube")
        assert r.status_code == 200
        cookies = r.headers.getlist("Set-Cookie")
        assert any(c.startswith("tw_ref=ANNE;") for c in cookies)
        assert any(c.startswith("tw_ref_sub=ANNE:youtube;") or c.startswith('tw_ref_sub="ANNE:youtube";')
                   for c in cookies)
        assert "/pricing?code=ANNE&amp;sub=youtube" in r.get_data(as_text=True)
        assert self._clicks(env) == (1, 1)
        # the same browser again: neither counter moves
        site.client.get("/join/ANNE?sub=youtube")
        assert self._clicks(env) == (1, 1)

    def test_plain_join_link_sets_no_sub_cookie(self, env, site):
        r = site.client.get("/join/ANNE")
        assert not any(c.startswith("tw_ref_sub=") for c in r.headers.getlist("Set-Cookie"))
        assert self._clicks(env) == (1, 0)
        r = site.client.get("/join/ANNE?sub=%3Cscript%3E")
        assert not any(c.startswith("tw_ref_sub=") for c in r.headers.getlist("Set-Cookie"))

    def test_pricing_link_carries_the_sub_through_the_redirect(self, env, site):
        r = site.client.get("/pricing?code=ANNE&sub=youtube")
        assert r.status_code == 302 and r.headers["Location"].endswith("/?code=ANNE&sub=youtube#pricing")
        assert any("tw_ref_sub=" in c for c in r.headers.getlist("Set-Cookie"))
        assert self._clicks(env) == (1, 1)

    def test_click_beacon_takes_a_sub(self, env, site):
        assert site.client.post("/api/aff/click", json={"code": "ANNE", "sub": "youtube"}).status_code == 204
        assert self._clicks(env) == (1, 1)
        assert site.client.post("/api/aff/click", json={"code": "ANNE", "sub": "nope"}).status_code == 204
        assert self._clicks(env) == (2, 1)

    def test_checkout_stamps_the_tag_after_the_partner_is_resolved(self):
        src = (h._REPO_ROOT / "web" / "app.py").read_text()
        resolve = src.index("offer = _resolve_checkout_offer(")
        stamp = src.index('sub_metadata["tw2_affiliate_sub"]')
        assert resolve < stamp
        home = (h._REPO_ROOT / "site" / "templates" / "index-dark-blue.html").read_text()
        assert "tw_ref_sub" in home and "sub: sub" in home


# ===========================================================================
# 3. Bulk payouts
# ===========================================================================
def payout(env, aff, amount, period=dt.date(2026, 10, 1), currency="usd", status="pending"):
    import models
    p = models.AffiliatePayout(affiliate_id=aff.id, period_start=period, period_end=period,
                               currency=currency, gross_revenue=D(amount) * 2,
                               commission_amount=D(amount), status=status)
    env.db.add(p)
    env.db.commit()
    return p


def paid_partner(env, code, **kw):
    kw.setdefault("tax_form_type", "w9")
    kw.setdefault("tax_form_received_at", dt.datetime(2026, 1, 6, tzinfo=UTC))
    return h.make_partner(env.db, code, **kw)[0]


class TestBulkPayouts:
    def _world(self, env):
        anne = paid_partner(env, "ANNE")
        bob = paid_partner(env, "BOB", payout_method="wise", name="Bob, Lee & Co")
        cara = paid_partner(env, "CARA")
        dan = paid_partner(env, "DAN", tax_form_type=None, tax_form_received_at=None)
        eve = paid_partner(env, "EVE", payout_method=None)
        rows = SimpleNamespace(
            anne=payout(env, anne, "108.45"), bob=payout(env, bob, "250.00"),
            cara_eur=payout(env, cara, "75.50", currency="eur"),
            cara_small=payout(env, cara, "12.00"), dan=payout(env, dan, "90.00"),
            eve=payout(env, eve, "60.00"), neg=payout(env, anne, "-20.00", period=dt.date(2026, 9, 1)))
        return rows

    def test_only_payable_rows_are_offered_grouped_by_method_and_currency(self, env):
        r = self._world(env)
        rows = ops.pending_payout_rows(env.db)
        why = {x["ref"]: x["short_reason"] for x in rows if not x["payable"]}
        assert why == {ops.payout_ref(r.cara_small): "Below minimum, carried",
                       ops.payout_ref(r.dan): "No tax form on file",
                       ops.payout_ref(r.eve): "No payout method",
                       ops.payout_ref(r.neg): "Negative, carried"}
        groups = ops.payout_groups(rows)
        assert [(g["method"], g["currency"], [x["code"] for x in g["rows"]], g["total"]) for g in groups] == [
            ("paypal", "eur", ["CARA"], D("75.50")), ("paypal", "usd", ["ANNE"], D("108.45")),
            ("wise", "usd", ["BOB"], D("250.00"))]

    def test_paypal_csv_format(self, env):
        r = self._world(env)
        rows, skipped = ops.select_for_export(env.db, [r.anne.id, r.cara_eur.id, r.dan.id, r.bob.id],
                                              "paypal", "usd")
        text = ops.paypal_csv(rows)
        # no header row; email, amount, currency, reference id, note, wallet
        assert text == "pay-anne@partner.example,108.45,USD,%s,TradeWave partner commission Oct 2026,PAYPAL\r\n" \
            % ops.payout_ref(r.anne)
        assert ops.payout_ref(r.anne).isalnum() and len(ops.payout_ref(r.anne)) <= 30
        assert dict(skipped) == {ops.payout_ref(r.cara_eur): "different method or currency",
                                 ops.payout_ref(r.dan): "No tax form on file",
                                 ops.payout_ref(r.bob): "different method or currency"}
        eur, _ = ops.select_for_export(env.db, [r.cara_eur.id], "paypal", "eur")
        assert ops.paypal_csv(eur).split(",")[1:3] == ["75.50", "EUR"]
        with pytest.raises(ops.OpsError):                    # one currency per PayPal file
            ops.paypal_csv(rows + eur)

    def test_wise_csv_format(self, env):
        r = self._world(env)
        rows, _ = ops.select_for_export(env.db, [r.bob.id], "wise", "usd")
        table = list(csv.reader(io.StringIO(ops.wise_csv(rows))))
        assert table[0] == ["name", "recipientEmail", "paymentReference", "receiverType",
                            "amountCurrency", "amount", "sourceCurrency", "targetCurrency"]
        assert table[1] == ["Bob, Lee & Co", "pay-bob@partner.example", ops.payout_ref(r.bob), "PERSON",
                            "target", "250.00", "USD", "USD"]
        assert len(table) == 2

    def test_nothing_payable_selected_is_an_error(self, env):
        r = self._world(env)
        for ids in ([], [r.dan.id], [r.neg.id], ["x"], [999999]):
            with pytest.raises(ops.OpsError):
                ops.select_for_export(env.db, ids, "paypal", "usd")

    def test_csv_cells_cannot_start_a_formula(self, env):
        mallory = paid_partner(env, "MAL", payout_method="wise", name="=HYPERLINK(1)")
        p = payout(env, mallory, "80.00")
        rows, _ = ops.select_for_export(env.db, [p.id], "wise", "usd")
        assert list(csv.reader(io.StringIO(ops.wise_csv(rows))))[1][0] == "'=HYPERLINK(1)"

    def test_export_view_downloads_a_file_and_pays_nothing(self, env, admin):
        import models
        r = self._world(env)
        html = admin.client.get("/admin/affiliate_bulk_payouts/").get_data(as_text=True)
        assert "This page never moves money" in html and EM_DASH not in html
        assert "Export PayPal CSV (USD)" in html and "Export PayPal CSV (EUR)" in html
        assert "Export Wise CSV (USD)" in html and "Not payable yet (4)" in html
        resp = admin.client.post("/admin/affiliate_bulk_payouts/export",
                                 data={"method": "paypal", "currency": "usd", "ids": [str(r.anne.id)]})
        assert resp.status_code == 200 and resp.mimetype == "text/csv"
        assert "tradewave-paypal-payouts-usd-" in resp.headers["Content-Disposition"]
        assert resp.get_data(as_text=True).startswith("pay-anne@partner.example,108.45,USD,")
        env.db.expire_all()
        assert {p.status for p in env.db.query(models.AffiliatePayout).all()} == {"pending"}
        assert admin.audits[-1]["action"] == "affiliate_payout_export"
        assert admin.audits[-1]["details"]["rows"] == [ops.payout_ref(r.anne)]
        # nothing ticked: back to the page, no file
        resp = admin.client.post("/admin/affiliate_bulk_payouts/export",
                                 data={"method": "wise", "currency": "usd"})
        assert resp.status_code == 302

    def test_parse_paste_and_files(self):
        got = ops.parse_paid_batch("TWP000012, 5AB12345\n twp13\tWISE-99 \n\nTWP000014\nhello world\n")
        assert [(e["payout_id"], e["reference"], bool(e["error"])) for e in got] == [
            (12, "5AB12345", False), (13, "WISE-99", False), (14, "", False), (None, "", True)]
        # our own PayPal export pasted back: the reference comes from the batch field
        got = ops.parse_paid_batch("pay@x.example,108.45,USD,TWP000012,TradeWave partner commission Oct 2026,PAYPAL")
        assert (got[0]["payout_id"], got[0]["reference"]) == (12, "")
        # a result file with a header and a status column
        text = ("Reference ID,Recipient,Transaction ID,Status\r\n"
                "TWP000012,a@x.example,9XY111,SUCCESS\r\nTWP000013,b@x.example,9XY222,FAILED\r\n")
        got = ops.parse_paid_batch(text)
        assert (got[0]["payout_id"], got[0]["reference"], got[0]["error"]) == (12, "9XY111", None)
        assert got[1]["payout_id"] == 13 and "Not paid according to the file" in got[1]["error"]
        wise = "paymentReference;id;status\nTWP000015;55123;outgoing_payment_sent\n"
        assert [(e["payout_id"], e["reference"]) for e in ops.parse_paid_batch(wise)] == [(15, "55123")]
        assert ops.parse_paid_batch("  ") == []

    def test_bulk_mark_paid_goes_through_the_same_gate(self, env):
        import models
        r = self._world(env)
        line = models.AffiliateCommissionLine(
            affiliate_id=r.anne.affiliate_id, kind="first_year", source_id="in_1", currency="usd",
            net_paid_cents=21690, basis_cents=21690, rate_pct=D(50), amount=D("108.45"),
            state="pending", period_month=dt.date(2026, 10, 1), payable_month=dt.date(2026, 10, 1),
            payout_id=r.anne.id)
        env.db.add(line)
        env.db.commit()
        text = "\n".join([
            "%s, PP-AAA" % ops.payout_ref(r.anne), "%s, WISE-BBB" % ops.payout_ref(r.bob),
            "%s, PP-CCC" % ops.payout_ref(r.dan),          # no tax form
            "%s, PP-DDD" % ops.payout_ref(r.cara_small),   # below minimum
            "%s, PP-EEE" % ops.payout_ref(r.neg),          # negative
            "%s" % ops.payout_ref(r.cara_eur),             # no reference at all
            "%s, PP-AAA2" % ops.payout_ref(r.anne),        # listed twice
            "TWP999999, PP-ZZZ"])
        entries = ops.check_paid_batch(env.db, ops.parse_paid_batch(text))
        assert [e["ok"] for e in entries] == [True, True, False, False, False, False, False, False]
        assert [e["message"] for e in entries[2:]] == [
            "No tax form on file", "Below minimum, carried", "Negative, carried",
            "No payment reference - add one on the line or a batch reference",
            "Listed twice - the first line is used", "No ledger row with this reference"]
        env.db.expire_all()
        assert {p.status for p in env.db.query(models.AffiliatePayout).all()} == {"pending"}   # preview only

        when = dt.datetime(2026, 11, 10, tzinfo=UTC)
        result = ops.apply_paid_batch(env.db, ops.parse_paid_batch(text), paid_at=when)
        assert result["paid"] == [ops.payout_ref(r.anne), ops.payout_ref(r.bob)]
        assert len(result["refused"]) == 6 and result["lines"] == 1
        env.db.expire_all()
        by_id = {p.id: p for p in env.db.query(models.AffiliatePayout).all()}
        assert (by_id[r.anne.id].status, by_id[r.anne.id].external_ref) == ("paid", "PP-AAA")
        assert (by_id[r.bob.id].status, by_id[r.bob.id].external_ref) == ("paid", "WISE-BBB")
        assert by_id[r.anne.id].paid_at is not None
        for other in (r.dan, r.cara_small, r.neg, r.cara_eur, r.eve):
            assert by_id[other.id].status == "pending" and by_id[other.id].external_ref is None
        assert env.db.query(models.AffiliateCommissionLine).one().state == "paid"
        # running the same file again changes nothing
        again = ops.apply_paid_batch(env.db, ops.parse_paid_batch(text), paid_at=when)
        assert again["paid"] == [] and (ops.payout_ref(r.anne), "Already marked paid (PP-AAA)") in again["refused"]

    def test_batch_reference_fills_lines_without_one(self, env):
        import models
        r = self._world(env)
        res = ops.apply_paid_batch(env.db, ops.parse_paid_batch(ops.payout_ref(r.cara_eur)), "BATCH-77")
        assert res["paid"] == [ops.payout_ref(r.cara_eur)]
        env.db.expire_all()
        assert env.db.get(models.AffiliatePayout, r.cara_eur.id).external_ref == "BATCH-77"

    def test_mark_paid_view_previews_first(self, env, admin):
        import models
        r = self._world(env)
        text = "%s, PP-AAA\n%s, PP-CCC" % (ops.payout_ref(r.anne), ops.payout_ref(r.dan))
        resp = admin.client.post("/admin/affiliate_bulk_payouts/mark-paid", data={"batch": text})
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200 and "Check before marking paid" in html
        assert "Will be marked paid" in html and "No tax form on file" in html and "Mark 1 row paid" in html
        env.db.expire_all()
        assert env.db.get(models.AffiliatePayout, r.anne.id).status == "pending"
        resp = admin.client.post("/admin/affiliate_bulk_payouts/mark-paid",
                                 data={"batch": text, "confirm": "yes"})
        assert resp.status_code == 302
        env.db.expire_all()
        assert env.db.get(models.AffiliatePayout, r.anne.id).status == "paid"
        assert env.db.get(models.AffiliatePayout, r.dan.id).status == "pending"
        assert admin.audits[-1]["action"] == "affiliate_payout_bulk_paid"
        assert admin.audits[-1]["details"]["paid"] == [ops.payout_ref(r.anne)]
        # a CSV upload works the same way
        csv_file = (io.BytesIO(("Reference ID,Transaction ID\n%s,WISE-1\n" % ops.payout_ref(r.bob)).encode()),
                    "result.csv")
        resp = admin.client.post("/admin/affiliate_bulk_payouts/mark-paid",
                                 data={"batch_file": csv_file}, content_type="multipart/form-data")
        assert "Mark 1 row paid" in resp.get_data(as_text=True)

    def test_module_has_no_payment_client(self):
        import inspect
        src = inspect.getsource(ops)
        for word in ("requests.", "stripe.", "paypalrestsdk", "api.paypal.com", "api.wise.com", "urllib"):
            assert word not in src, word


# ===========================================================================
# 4. Creative library
# ===========================================================================
class TestCreativeLibrary:
    def test_admin_adds_items_and_partner_sees_them_filled_in(self, env, admin):
        import config
        anne, user = partner(env)
        r = admin.client.post("/admin/affiliate_creatives/create", data={
            "kind": "banner", "title": "Leaderboard 728 x 90",
            "image": (io.BytesIO(png_bytes()), "leader.png", "image/png")},
            content_type="multipart/form-data")
        assert r.status_code == 302
        r = admin.client.post("/admin/affiliate_creatives/create", data={
            "kind": "email", "title": "Launch email",
            "body": "Hi — I use TradeWave. {discount}% off with code {code}: {join_link}\n"
                    "Home: {link} {name} {unknown}"})
        assert r.status_code == 302
        banner, email = sorted(env.db.query(om.AffiliateCreative).all(), key=lambda c: c.id)
        assert (banner.width, banner.height, banner.mime_type) == (728, 90, "image/png")
        assert (Path(config.AFFILIATE_CREATIVE_DIR) / banner.file_name).is_file()
        assert EM_DASH not in email.body and "Hi - I use" in email.body       # house style on save
        assert [a["action"] for a in admin.audits] == ["affiliate_creative_added"] * 2
        html = admin.client.get("/admin/affiliate_creatives/").get_data(as_text=True)
        assert "Leaderboard 728 x 90" in html and "Launch email" in html and EM_DASH not in html

        login(env, user)
        html = page(env, "/promote")
        assert "Creative library" in html and "Leaderboard 728 x 90" in html and "728 x 90" in html
        assert "Copy embed code" in html and "/creative/%d/file?download=1" % banner.id in html
        assert "20% off with code ANNE: https://" in html and "/join/ANNE" in html
        assert "{code}" not in html and "{join_link}" not in html and "{unknown}" in html
        assert EM_DASH not in html
        lib = ops.creatives_for_partner(env.db, anne, {"join": "https://t.example/join/ANNE",
                                                       "referral": "https://t.example/?code=ANNE"}, "20")
        assert lib["images"][0]["embed"] == (
            '<a href="https://t.example/join/ANNE"><img src="%s/assets/affiliate-creatives/%s" '
            'alt="Leaderboard 728 x 90" width="728" height="90"></a>'
            % (__import__("affiliate_agreement")._base(), banner.file_name))
        assert "Home: https://t.example/?code=ANNE Anne Lee {unknown}" in lib["texts"][0]["text"]

        r = env.client.get(BASE + "/creative/%d/file" % banner.id)
        assert r.status_code == 200 and r.mimetype == "image/png" and r.data == png_bytes()
        r = env.client.get(BASE + "/creative/%d/file?download=1" % banner.id)
        assert "attachment" in r.headers["Content-Disposition"]
        assert "tradewave-leaderboard-728-x-90.png" in r.headers["Content-Disposition"]
        assert env.client.get(BASE + "/creative/%d/file" % email.id).status_code == 404

    @pytest.mark.parametrize("kind,title,body,blob,needle", [
        ("banner", "B", None, None, "Choose an image"),
        ("banner", "B", None, b"<svg onload=alert(1)></svg>", "not a supported image"),
        ("logo", "L", None, PDF, "not a supported image"),
        ("email", "E", "", None, "Write the copy"),
        ("social", "", "text", None, "title"),
        ("video", "V", "text", None, "kind"),
    ])
    def test_bad_items_are_refused(self, env, kind, title, body, blob, needle):
        with pytest.raises(ops.OpsError) as e:
            ops.save_creative(env.db, kind=kind, title=title, body=body, blob=blob, filename="x.png")
        assert needle in str(e.value)
        assert env.db.query(om.AffiliateCreative).count() == 0

    def test_campaign_items_show_only_while_the_campaign_is_live(self, env):
        import models
        anne, user = h.seed_rich(env.db, env.world)
        camp = env.db.query(models.PromoCampaign).one()
        ops.save_creative(env.db, kind="social", title="Black Friday post", body="Sale: {join_link}",
                          campaign_id=camp.id)
        ops.save_creative(env.db, kind="social", title="Evergreen post", body="Try it: {join_link}")
        links = {"join": "J", "referral": "R"}
        titles = [c["title"] for c in ops.creatives_for_partner(env.db, anne, links)["texts"]]
        assert sorted(titles) == ["Black Friday post", "Evergreen post"]
        # a sale item says when it leaves; general copy that quotes the discount is flagged
        ops.save_creative(env.db, kind="social", title="Discount post", body="{discount}% off: {join_link}")
        ops.save_creative(env.db, kind="banner", title="Leaderboard", blob=png_bytes((728, 90)), filename="l.png")
        ops.save_creative(env.db, kind="banner", title="Square", blob=png_bytes((300, 250)), filename="s.png")
        lib = ops.creatives_for_partner(env.db, anne, links, "20")
        by = {c["title"]: c for c in lib["texts"] + lib["images"]}
        ends = camp.ends_at
        assert by["Black Friday post"]["ends"] == "%d %s" % (ends.day, ends.strftime("%b"))
        assert by["Evergreen post"]["ends"] is None
        assert by["Discount post"]["quotes_discount"] and not by["Black Friday post"]["quotes_discount"]
        assert by["Leaderboard"]["wide"] is True and by["Square"]["wide"] is False
        login(env, user)
        html = page(env, "/promote")
        assert '<div class="creative wide">' in html and "Until %d %s" % (ends.day, ends.strftime("%b")) in html
        assert "leave this page by themselves when the sale ends" in html
        # the live sale beats ANNE's 20%: the discount copy carries a warning, the sale copy does not
        assert html.count("This one quotes your regular 20% discount.") == 1
        assert "onerror=" in html and "Preview not available - use Download" in html
        for row in env.db.query(om.AffiliateCreative).filter(om.AffiliateCreative.title.in_(
                ["Discount post", "Leaderboard", "Square"])).all():
            ops.delete_creative(env.db, row)
        later = dt.datetime.now(UTC) + dt.timedelta(days=30)
        titles = [c["title"] for c in ops.creatives_for_partner(env.db, anne, links, now=later)["texts"]]
        assert titles == ["Evergreen post"]

    def test_archive_and_delete(self, env, admin):
        import config
        anne, user = partner(env)
        row = ops.save_creative(env.db, kind="logo", title="Logo", blob=png_bytes((200, 200)),
                                filename="logo.png")
        path = Path(config.AFFILIATE_CREATIVE_DIR) / row.file_name
        admin.client.post("/admin/affiliate_creatives/status/%d" % row.id, data={"status": "archived"})
        login(env, user)
        assert "Creative library" not in page(env, "/promote")
        assert env.client.get(BASE + "/creative/%d/file" % row.id).status_code == 404
        admin.client.post("/admin/affiliate_creatives/delete/%d" % row.id)
        env.db.expire_all()
        assert env.db.query(om.AffiliateCreative).count() == 0 and not path.exists()

    def test_partner_cannot_reach_the_admin_library(self, env):
        anne, user = partner(env)
        login(env, user)
        assert env.client.post(BASE + "/creative/1/file").status_code == 405


# ===========================================================================
# 5. Monthly operations summary
# ===========================================================================
class TestOpsSummary:
    NOW = dt.datetime(2026, 11, 3, 6, 30, tzinfo=UTC)

    def _world(self, env):
        import models
        anne = paid_partner(env, "ANNE")
        bob = paid_partner(env, "BOB", payout_method="wise")
        dan = paid_partner(env, "DAN", tax_form_type=None, tax_form_received_at=None)
        eve = paid_partner(env, "EVE", payout_method=None, payout_email=None)
        pat = paid_partner(env, "PAT", status="paused")
        oct1 = dt.date(2026, 10, 1)
        rows = SimpleNamespace(
            anne=payout(env, anne, "108.45"), bob=payout(env, bob, "250.00"),
            dan=payout(env, dan, "90.00"), eve=payout(env, eve, "60.00"),
            small=payout(env, bob, "12.00", period=dt.date(2026, 9, 1)))

        def line(aff, kind, source, paid, amount, state="pending", hold=None, day=12):
            when = dt.datetime(2026, 10, day, tzinfo=UTC)
            env.db.add(models.AffiliateCommissionLine(
                affiliate_id=aff.id, kind=kind, source_id=source, currency="usd", net_paid_cents=paid,
                basis_cents=paid, rate_pct=D(50), amount=D(amount), state=state, hold_reason=hold,
                event_at=when, period_month=oct1, payable_month=None if state == "held" else oct1))
        line(anne, "refund", "re_big", -39900, "-99.75")
        line(anne, "refund", "re_small", -2900, "-8.70")
        line(bob, "dispute", "dp_1", -4900, "-12.25")
        line(pat, "first_year", "in_held", 10000, "50.00", state="held", hold="paused")

        def ref(aff, n, first_paid):
            env.db.add(models.AffiliateReferral(
                id=uuid.uuid4(), affiliate_id=aff.id, stripe_subscription_id="sub_%s_%d" % (aff.code, n),
                source="checkout", terms_id=1, first_paid_at=first_paid, year_anchor_at=first_paid))
        ref(anne, 1, dt.datetime(2026, 9, 1, tzinfo=UTC))            # active for a long while
        ref(bob, 1, dt.datetime(2025, 10, 20, tzinfo=UTC))           # 12 months + 30 days -> ends 19 Nov 2026
        ref(dan, 1, dt.datetime(2025, 9, 20, tzinfo=UTC))            # lapsed 20 Oct 2026
        env.db.add(om.AffiliateTaxForm(affiliate_id=dan.id, form_type="w9", status="received",
                                       storage_name=None, size_bytes=10))
        env.db.commit()
        return rows

    def test_summary_numbers_and_flags(self, env):
        r = self._world(env)
        s = summ.build_summary(env.db, 2026, 10, now=self.NOW)
        assert s["period_label"] == "October 2026" and s["committed"] is True
        assert s["payable_totals"] == [("usd", D("358.45"))]
        assert sorted(x["code"] for x in s["payable"]) == ["ANNE", "BOB"]
        assert s["blocked_totals"] == [("usd", D("162.00"))]
        assert [(x["code"], x["kind"], x["customer_amount"]) for x in s["large_refunds"]] == [
            ("ANNE", "refund", D("399")), ("BOB", "dispute", D("49"))]      # every chargeback, big refunds only
        assert [(h_["code"], h_["amount"]) for h_ in s["held"]] == [("PAT", D("50.00"))]
        assert [x["code"] for x in s["no_tax"]] == ["DAN"] and s["forms_waiting"] == 1
        assert [x["code"] for x in s["no_details"]] == ["EVE"]
        assert [(x["code"], x["short_reason"]) for x in s["carries"]] == [("BOB", "Below minimum, carried")]
        assert [(a["code"], a["state"], a["date"], a["days"]) for a in s["activity"]] == [
            ("BOB", "closing", "19 Nov 2026", 16), ("DAN", "lapsed", "20 Oct 2026", 0)]
        assert s["flags"] == 2 + 1 + 1 + 1 + 1 + 2 + 1

        text = summ.render_text(s)
        subject = summ.subject_for(s)
        assert subject == "Affiliate operations Oct 2026 - $358.45 payable to 2 partners, 9 things to check"
        assert "Payable now: $358.45 across 2 rows." in text
        assert "ANNE refund of $399.00 on 12 Oct 2026 - commission taken back $99.75 (re_big)" in text
        assert "BOB chargeback of $49.00" in text and "re_small" not in text
        assert "PAT Pat Lee (paused) - $50.00 in 1 line" in text
        assert "DAN Dan Lee - $90.00 waiting (Oct 2026)" in text
        assert "1 uploaded form waiting for your review." in text
        assert "EVE Eve Lee - $60.00 - No payout method" in text
        assert "BOB Sep 2026 - $12.00 - Below minimum, carried" in text
        assert "renewal commissions stop after 19 Nov 2026 (16 days)" in text
        assert "DAN Dan Lee - renewal commissions lapsed on 20 Oct 2026" in text
        for path in ("/admin/affiliate_bulk_payouts/", "/admin/affiliate_tax_forms/",
                     "/admin/affiliatecommissionline/?flt1_state_equals=held", "/admin/affiliate_compute/"):
            assert path in text
        assert "never marks a row paid" in text
        html = summ.render_html(s)
        assert "<a href=" in html and "Open in admin" in html
        for out in (text, html, subject):
            assert EM_DASH not in out
        # no customer identity leaves in the summary
        assert "cus_" not in text and "@" not in text.replace("help@", "")

    def test_quiet_month(self, env):
        anne = paid_partner(env, "ANNE")
        s = summ.build_summary(env.db, 2026, 10, now=self.NOW)
        assert s["committed"] is False and s["flags"] == 0 and s["payable"] == []
        text = summ.render_text(s)
        assert "October 2026 is not in the ledger yet" in text and "Nothing flagged this month." in text
        assert summ.subject_for(s) == "Affiliate operations Oct 2026 - $0.00 payable to 0 partners, 0 things to check"
        assert anne is not None

    def test_one_email_per_month_and_nothing_is_marked_paid(self, env, monkeypatch):
        import config
        import email_utils
        import models
        import stripe
        self._world(env)
        sent = []
        monkeypatch.setattr(email_utils, "resend_send_email", lambda **kw: sent.append(kw) or True)
        monkeypatch.setattr(config, "AFFILIATE_OWNER_EMAIL", "owner@example.com", raising=False)

        def no_stripe(*a, **k):
            raise AssertionError("the summary must not call Stripe")
        for obj in (stripe.Invoice, stripe.Refund, stripe.Dispute):
            monkeypatch.setattr(obj, "list", no_stripe)

        def snapshot():
            env.db.expire_all()
            return ([(p.id, p.status, p.paid_at, p.external_ref, p.commission_amount)
                     for p in env.db.query(models.AffiliatePayout).order_by(models.AffiliatePayout.id)],
                    [(ln.id, ln.state, ln.payout_id, ln.amount)
                     for ln in env.db.query(models.AffiliateCommissionLine)
                     .order_by(models.AffiliateCommissionLine.id)])
        before = snapshot()
        assert summ.send_summary(env.db, 2026, 10, now=self.NOW) == "sent"
        assert len(sent) == 1 and sent[0]["to"] == "owner@example.com"
        assert sent[0]["subject"].startswith("Affiliate operations Oct 2026 - $358.45 payable")
        assert sent[0]["html"] and "Payable now" in sent[0]["body_text"]
        assert snapshot() == before                                  # ledger untouched
        assert summ.send_summary(env.db, 2026, 10, now=self.NOW) == "already_sent"
        assert len(sent) == 1
        assert summ.send_summary(env.db, 2026, 9, now=self.NOW) == "sent"      # another month is its own email
        assert summ.send_summary(env.db, 2026, 10, force=True, now=self.NOW) == "sent"
        assert len(sent) == 3
        log = env.db.query(models.AuditLog).filter_by(action=summ.SENT_ACTION).all()
        assert sorted(a.details["period"] for a in log) == ["2026-09", "2026-10", "2026-10"]

    def test_unsent_email_is_not_recorded(self, env, monkeypatch):
        import email_utils
        import models
        monkeypatch.setattr(email_utils, "resend_send_email", lambda **kw: False)
        assert summ.send_summary(env.db, 2026, 10, now=self.NOW) == "not_sent"
        assert env.db.query(models.AuditLog).filter_by(action=summ.SENT_ACTION).count() == 0

    def test_default_month_and_cron_entry(self):
        assert summ.prev_month(dt.date(2026, 11, 3)) == (2026, 10)
        assert summ.prev_month(dt.date(2027, 1, 3)) == (2026, 12)
        cron = (h._REPO_ROOT / "ops" / "install_affiliate_crons.sh").read_text()
        assert "30 6 3 * *" in cron and "affiliate_ops_summary.py --email" in cron
        src = Path(summ.__file__).read_text()
        for word in ("upsert_month", "compute_month(", "status = \"paid\"", "sync_line_states", "import stripe"):
            assert word not in src, word


# ===========================================================================
# house rules
# ===========================================================================
def test_no_em_dashes_in_the_new_code_and_templates():
    root = h._REPO_ROOT
    files = [root / "web" / n for n in ("affiliate_ops.py", "affiliate_ops_admin.py",
                                        "affiliate_ops_summary.py", "affiliate_ops_models.py")]
    files += [root / "web" / "affiliate_portal" / "ops_routes.py"]
    files += sorted((root / "web" / "affiliate_portal" / "templates").glob("*.html"))
    for f in files:
        text = f.read_text()
        assert EM_DASH not in text and "&mdash;" not in text, f.name


def test_migration_adds_the_ops_tables_on_the_v2_head():
    mig = (h._REPO_ROOT / "migrations" / "versions" / "c0a1b2d3e4f5_affiliate_ops_growth.py").read_text()
    assert "revision = 'c0a1b2d3e4f5'" in mig and "down_revision = 'b4d7e1f2a3c5'" in mig
    for name in OPS_TABLES + ["referred_sub", "sub_link"]:
        assert name in mig
    import models
    for name in OPS_TABLES:
        table = models.Base.metadata.tables[name]
        # the migration creates every column the model declares
        for col in table.columns:
            assert '"%s"' % col.name in mig, (name, col.name)
    reqs = (h._REPO_ROOT / "requirements.txt").read_text()
    assert "cryptography" in reqs


# ===========================================================================
# fix-0039: review fixes + owner-side tools
# ===========================================================================
def model_views(env, admin):
    """The Flask-Admin list pages (ModelView) hold the session they were
    registered with, so point the partner-program ones at the test database."""
    from sqlalchemy.orm import scoped_session
    scoped = scoped_session(env.factory)
    for view in admin.mod.admin._views:
        if getattr(view, "endpoint", "") in ("affiliate", "affiliatepayout", "affiliatecommissionline"):
            env.patch.setattr(view, "session", scoped)


def admin_flashes(admin):
    with admin.client.session_transaction() as sess:
        return [m for _c, m in sess.pop("_flashes", [])]


class TestSubCookieEncoding:
    def test_a_percent_encoded_cookie_is_decoded(self):
        # older page JS wrote encodeURIComponent("ANNE:youtube")
        assert afs.sub_from_cookie("ANNE%3Ayoutube", "ANNE") == "youtube"
        assert afs.sub_from_cookie("anne%3Ayoutube", "ANNE") == "youtube"
        assert afs.sub_from_cookie("ANNE%3Ayoutube", "BOB") is None
        assert afs.sub_from_cookie("ANNE%3A%3Cb%3E", "ANNE") is None       # still validated after decoding
        assert afs.sub_from_cookie("%", "ANNE") is None

    def test_signup_stamp_reads_the_encoded_cookie(self, env):
        anne, _ = partner(env)
        u = h._user(env.db, "enc@example.com")
        assert afs.record_signup_referral(env.db, u, "ANNE", "ANNE%3Ayoutube") is True
        assert (u.referred_by_affiliate_id, u.referred_sub) == (anne.id, "youtube")

    def test_the_page_js_writes_the_cookie_raw(self):
        js = (h._REPO_ROOT / "site" / "templates" / "index-dark-blue.html").read_text()
        (line,) = [ln for ln in js.splitlines() if "document.cookie = 'tw_ref_sub='" in ln]
        assert "encodeURIComponent" not in line and "'tw_ref_sub=' + subTag" in line


class TestAttributionWindow:
    def test_one_helper_for_the_cookie_and_the_copy(self, env):
        import config
        assert afs.attribution_window_days() == 60
        assert afs.attribution_cookie_max_age() == 60 * 24 * 60 * 60
        env.patch.setattr(config, "AFFILIATE_ATTRIBUTION_WINDOW_DAYS", 45, raising=False)
        assert afs.attribution_window_days() == 45
        assert afs.attribution_cookie_max_age() == 45 * 24 * 60 * 60
        env.patch.setattr(config, "AFFILIATE_ATTRIBUTION_WINDOW_DAYS", "junk", raising=False)
        assert afs.attribution_window_days() == 60
        cfg = (h._REPO_ROOT / "config.py").read_text()
        assert "AFFILIATE_ATTRIBUTION_WINDOW_DAYS" in cfg
        app_src = (h._REPO_ROOT / "web" / "app.py").read_text()
        assert app_src.count("attribution_cookie_max_age()") >= 3      # tw_ref + tw_ref_sub cookies
        assert "affiliate_attribution_days" in app_src                 # exposed to templates

    def test_portal_templates_get_the_number(self, env):
        anne, user = partner(env)
        login(env, user)
        seen = {}
        from flask import template_rendered

        def grab(sender, template, context, **extra):
            seen.update(days=context.get("aff_attribution_days"))
        with template_rendered.connected_to(grab, env.app):
            page(env, "/payouts")
        assert seen["days"] == 60


class TestOwnerEmail:
    def test_one_address_with_fallbacks(self, env):
        import config
        for name in ("AFFILIATE_OWNER_EMAIL", "AFFILIATE_SUPPORT_EMAIL", "SUPPORT_EMAIL_TO"):
            env.patch.setattr(config, name, "", raising=False)
        assert afs.owner_email() == ""
        env.patch.setattr(config, "SUPPORT_EMAIL_TO", "support@tw.test", raising=False)
        assert afs.owner_email() == "support@tw.test"
        env.patch.setattr(config, "AFFILIATE_SUPPORT_EMAIL", "partners@tw.test", raising=False)
        assert afs.owner_email() == "partners@tw.test"
        env.patch.setattr(config, "AFFILIATE_OWNER_EMAIL", " owner@tw.test ", raising=False)
        assert afs.owner_email() == "owner@tw.test"
        import affiliate_comms
        import affiliate_help
        assert affiliate_comms.owner_email() == affiliate_help.owner_email() == "owner@tw.test"
        assert not hasattr(config, "AFFILIATE_OPS_EMAIL")              # the old second address is gone

    def test_admin_links_are_absolute(self, env):
        import config
        env.patch.setattr(config, "tw2_public_url", "https://tw.test/", raising=False)
        assert afs.admin_url("affiliate_tax_forms/") == "https://tw.test/admin/affiliate_tax_forms/"
        assert afs.admin_url("/affiliate_home/") == "https://tw.test/admin/affiliate_home/"


class TestExportDrift:
    W = TestBulkPayouts._world

    def test_unclaimed_is_not_a_paid_status(self):
        assert "unclaimed" not in ops._PAID_WORDS
        text = ("Reference ID,Transaction ID,Status\r\nTWP000012,9XY111,UNCLAIMED\r\n"
                "TWP000013,9XY222,Completed\r\n")
        got = ops.parse_paid_batch(text)
        assert "Not paid according to the file" in got[0]["error"] and got[1]["error"] is None

    @pytest.mark.parametrize("name", ["=1+1", "+1", "-2+3", "@SUM(A1)", "\tcmd", "\r=1"])
    def test_csv_cells_cannot_start_a_formula_any_way(self, env, name):
        mallory = paid_partner(env, "MAL", payout_method="wise", name=name)
        p = payout(env, mallory, "80.00")
        rows, _ = ops.select_for_export(env.db, [p.id], "wise", "usd")
        cell = list(csv.reader(io.StringIO(ops.wise_csv(rows))))[1][0]
        assert cell == "'" + name
        assert ops._csv_text([[80, "ok", "-x"]]) == "80,ok,'-x\r\n"       # numbers are left alone

    def test_export_stamps_the_row_and_a_second_export_is_refused(self, env, admin):
        import models
        r = self.W(env)
        data = {"method": "paypal", "currency": "usd", "ids": [str(r.anne.id)]}
        assert admin.client.post("/admin/affiliate_bulk_payouts/export", data=data).status_code == 200
        env.db.expire_all()
        p = env.db.get(models.AffiliatePayout, r.anne.id)
        assert p.exported_at is not None and D(p.exported_amount) == D("108.45") and p.status == "pending"
        assert env.db.get(models.AffiliatePayout, r.bob.id).exported_at is None
        html = admin.client.get("/admin/affiliate_bulk_payouts/").get_data(as_text=True)
        assert "Exported" in html and "Include rows I already exported" in html and EM_DASH not in html
        # the same row again: no file, a plain reason
        resp = admin.client.post("/admin/affiliate_bulk_payouts/export", data=data)
        assert resp.status_code == 302
        (msg,) = admin_flashes(admin)
        assert "already in an earlier export file" in msg and "pays the partner twice" in msg
        with pytest.raises(ops.OpsError, match="already in an earlier export"):
            ops.select_for_export(env.db, [r.anne.id], "paypal", "usd")
        # the owner can still ask for it, and is warned
        resp = admin.client.post("/admin/affiliate_bulk_payouts/export", data=dict(data, reexport="yes"))
        assert resp.status_code == 200 and resp.get_data(as_text=True).startswith("pay-anne@partner.example")
        (msg,) = admin_flashes(admin)
        assert "ALREADY in an earlier export" in msg and ops.payout_ref(r.anne) in msg
        assert admin.audits[-1]["details"]["re_exported"] == [ops.payout_ref(r.anne)]

    def _drifted(self, env):
        import models
        r = self.W(env)
        rows, _ = ops.select_for_export(env.db, [r.anne.id, ], "paypal", "usd")
        assert ops.mark_exported(env.db, rows) == 1
        p = env.db.get(models.AffiliatePayout, r.anne.id)
        p.commission_amount = D("88.45")                    # a refund landed after the export
        env.db.commit()
        return r

    def test_import_refuses_a_row_whose_amount_moved_after_the_export(self, env):
        import models
        r = self._drifted(env)
        ref = ops.payout_ref(r.anne)
        (row,) = [x for x in ops.pending_payout_rows(env.db) if x["id"] == r.anne.id]
        assert row["changed"] is True and D(row["exported_amount"]) == D("108.45")
        (e,) = ops.check_paid_batch(env.db, ops.parse_paid_batch("%s, PP-1" % ref))
        assert (e["ok"], e["drift"]) == (False, True)
        assert e["message"] == ("Amount changed since the export: the file said 108.45 USD, "
                                "the ledger now says 88.45 USD. Not marked paid")
        res = ops.apply_paid_batch(env.db, ops.parse_paid_batch("%s, PP-1" % ref))
        assert res["paid"] == [] and res["drift"] == [] and res["refused"][0][0] == ref
        env.db.expire_all()
        assert env.db.get(models.AffiliatePayout, r.anne.id).status == "pending"

    def test_owner_can_record_the_exported_amount_that_was_really_sent(self, env):
        import models
        r = self._drifted(env)
        ref = ops.payout_ref(r.anne)
        (e,) = ops.check_paid_batch(env.db, ops.parse_paid_batch("%s, PP-1" % ref), accept_exported=True)
        assert e["ok"] is True and e["pay_amount"] == D("108.45")
        assert "EXPORTED amount 108.45 USD" in e["message"] and "-20.00 USD" in e["message"]
        res = ops.apply_paid_batch(env.db, ops.parse_paid_batch("%s, PP-1" % ref), accept_exported=True)
        assert res["paid"] == [ref] and res["drift"] == [ref]
        env.db.expire_all()
        p = env.db.get(models.AffiliatePayout, r.anne.id)
        assert (p.status, p.external_ref) == ("paid", "PP-1")
        assert D(p.paid_amount) == D("108.45") and D(p.commission_amount) == D("88.45")

    def test_an_unchanged_row_records_what_was_paid(self, env):
        import models
        r = self.W(env)
        res = ops.apply_paid_batch(env.db, ops.parse_paid_batch("%s, PP-1" % ops.payout_ref(r.anne)))
        assert res["paid"] == [ops.payout_ref(r.anne)] and res["drift"] == []
        env.db.expire_all()
        assert D(env.db.get(models.AffiliatePayout, r.anne.id).paid_amount) == D("108.45")

    def test_mark_paid_view_shows_the_drift_and_the_override(self, env, admin):
        import models
        r = self._drifted(env)
        text = "%s, PP-1\n%s, WISE-2" % (ops.payout_ref(r.anne), ops.payout_ref(r.bob))
        html = admin.client.post("/admin/affiliate_bulk_payouts/mark-paid",
                                 data={"batch": text}).get_data(as_text=True)
        assert "Amount changed since the export" in html and "Mark 1 row paid" in html
        assert 'name="accept_exported"' in html and EM_DASH not in html
        html = admin.client.post("/admin/affiliate_bulk_payouts/mark-paid",
                                 data={"batch": text, "accept_exported": "yes"}).get_data(as_text=True)
        assert "Mark 2 rows paid" in html and "EXPORTED amount" in html
        resp = admin.client.post("/admin/affiliate_bulk_payouts/mark-paid",
                                 data={"batch": text, "accept_exported": "yes", "confirm": "yes"})
        assert resp.status_code == 302
        msgs = admin_flashes(admin)
        assert any("marked paid at the EXPORTED amount" in m for m in msgs)
        env.db.expire_all()
        assert D(env.db.get(models.AffiliatePayout, r.anne.id).paid_amount) == D("108.45")
        assert admin.audits[-1]["details"]["paid_at_exported_amount"] == [ops.payout_ref(r.anne)]

    def test_apply_re_reads_each_row_under_the_lock(self, env):
        """A change committed by ANOTHER session between the check and the
        write is seen (populate_existing), and the row goes back through the
        payout gate instead of being marked paid from stale data."""
        import models
        r = self.W(env)
        env.db.get(models.AffiliatePayout, r.anne.id)        # loaded: the identity map holds old values
        env.db.get(models.Affiliate, r.anne.affiliate_id)
        real = ops.check_paid_batch

        def check_then_someone_else_changes_it(session, entries, *a, **k):
            out = real(session, entries, *a, **k)
            other = env.factory()
            aff = other.get(models.Affiliate, r.anne.affiliate_id)
            aff.tax_form_received_at = None                  # the gate now refuses this partner
            other.get(models.AffiliatePayout, r.bob.id).status = "void"
            other.commit()
            other.close()
            return out
        env.patch.setattr(ops, "check_paid_batch", check_then_someone_else_changes_it)
        text = "%s, PP-1\n%s, WISE-2\n%s, PP-3" % (ops.payout_ref(r.anne), ops.payout_ref(r.bob),
                                                   ops.payout_ref(r.cara_eur))
        res = ops.apply_paid_batch(env.db, ops.parse_paid_batch(text))
        assert res["paid"] == [ops.payout_ref(r.cara_eur)]
        assert res["refused"] == [(ops.payout_ref(r.anne), "Changed since the preview - not marked paid"),
                                  (ops.payout_ref(r.bob), "Changed since the preview - not marked paid")]
        env.db.expire_all()
        assert env.db.get(models.AffiliatePayout, r.anne.id).status == "pending"
        assert env.db.get(models.AffiliatePayout, r.bob.id).status == "void"


class TestTaxFormLifecycle:
    def test_deleting_a_partner_removes_the_encrypted_files(self, env):
        import config
        aff, user = partner(env)
        login(env, user)
        assert upload(env).status_code == 302
        row = forms(env)[0]
        stored = Path(config.TAX_FORM_DIR) / row.storage_name
        assert stored.exists()
        assert ops.purge_tax_forms(env.db, aff) == 1
        assert not stored.exists()
        assert ops.purge_tax_forms(env.db, aff) in (0, 1)     # a missing file is not an error

    def test_tax_form_rows_go_with_the_partner(self):
        (fk,) = om.AffiliateTaxForm.__table__.c.affiliate_id.foreign_keys
        assert fk.ondelete == "CASCADE"
        app_src = (h._REPO_ROOT / "web" / "app.py").read_text()
        assert "purge_tax_forms(self.session, model)" in app_src

    def test_accept_and_reject_reach_the_partner_by_email_and_inbox(self, env, admin):
        import config
        import models
        env.patch.setattr(config, "RESEND_API_KEY", "re_test_key", raising=False)
        aff, user = partner(env)
        login(env, user)
        upload(env)
        row = forms(env)[0]
        assert admin.client.post("/admin/affiliate_tax_forms/reject/%d" % row.id,
                                 data={"reason": "The signature line is empty."}).status_code == 302
        (mail,) = admin.sent
        assert mail["to"] == aff.email and mail["subject"] == "Your W-9 needs a fix"
        assert "The signature line is empty." in mail["body_text"] and EM_DASH not in mail["body_text"]
        N = models.AffiliateNotification
        (note,) = env.db.query(N).filter(N.affiliate_id == aff.id).all()
        assert (note.event_type, note.email_status) == ("tax_form_rejected", "sent")
        # a required notice: it is sent even when every optional email is off
        import affiliate_comms as comms
        assert comms.EVENT_PREF["tax_form_rejected"] is None and comms.EVENT_PREF["tax_form_accepted"] is None
        comms.set_disabled_prefs(env.db, aff.id, list(comms.PREF_IDS))
        upload(env)
        row2 = forms(env)[-1]
        assert admin.client.post("/admin/affiliate_tax_forms/accept/%d" % row2.id).status_code == 302
        assert [m["subject"] for m in admin.sent] == ["Your W-9 needs a fix", "Your W-9 is on file"]
        assert env.db.query(N).filter(N.event_type == "tax_form_accepted").count() == 1
        assert comms.notify_tax_form(env.db, forms(env)[-1]) is None      # already told
        assert len(admin.sent) == 2                              # once per form and result
        login(env, user)
        inbox = page(env, "/messages")
        assert "Your W-9 is on file" in inbox and "Your W-9 needs a fix" in inbox


def referred(env, aff, email, ip=None, customer=None):
    import models
    u = models.User(id=uuid.uuid4(), email=email, tier="explorer", referred_by_affiliate_id=aff.id,
                    referred_ip_hash=afs.hash_ip(ip) if ip else None, stripe_customer_id=customer)
    env.db.add(u)
    env.db.commit()
    return u


def clicks(env, aff, n):
    import models
    env.db.add(models.AffiliateClick(affiliate_id=aff.id, day=dt.date(2026, 10, 3), clicks=n))
    env.db.commit()


class TestFraudSignals:
    def _cast(self, env):
        import affiliate_owner as owner
        clean = paid_partner(env, "ANNE")
        selfy = paid_partner(env, "BOB", email="bob@bobtrades.example", payout_email="bobpay@gmail.com",
                             agreement_signed_ip="198.51.100.7")
        farm = paid_partner(env, "CARA")
        clicks(env, clean, 400)
        for i in range(6):
            referred(env, clean, "c%d@example.org" % i, ip="203.0.113.%d" % i)
        clicks(env, selfy, 300)
        referred(env, selfy, "bobpay@gmail.com")                         # his own payout email
        referred(env, selfy, "wife@bobtrades.example")                   # his own domain
        referred(env, selfy, "someone@gmail.com", ip="198.51.100.7")     # his own network (free mail: no domain flag)
        clicks(env, farm, 4)
        for i in range(6):
            referred(env, farm, "f%d@example.net" % i, ip="192.0.2.9" if i < 4 else None)
        return owner, clean, selfy, farm

    def test_each_signal_has_a_plain_reason_and_no_customer_identity(self, env):
        owner, clean, selfy, farm = self._cast(env)
        flags = owner.fraud_signals(env.db)
        assert clean.id not in flags
        assert {f["kind"]: f["reason"] for f in flags[selfy.id]} == {
            "self_referral": "1 referred customer uses the partner's own contact or payout email address",
            "self_referral_domain": "1 referred customer shares the partner's own email domain (bobtrades.example)",
            "self_referral_ip": "1 referred signup came from the network the partner signed the agreement from"}
        assert {f["kind"]: f["reason"] for f in flags[farm.id]} == {
            "click_ratio": "6 signups from 4 clicks (a normal link sees far more clicks than signups)",
            "shared_ip": "4 referred signups came from one network"}
        text = owner.fraud_text(flags[selfy.id]) + owner.fraud_text(flags[farm.id])
        assert "@gmail.com" not in text and "example.net" not in text and "192.0.2" not in text
        assert EM_DASH not in text
        assert owner.fraud_text([]) == "" and owner.fraud_signals(env.db)[farm.id][0]["label"]

    def test_a_paying_customer_on_the_partners_own_email_is_flagged(self, env):
        import affiliate_owner as owner
        import models
        anne = paid_partner(env, "ANNE")
        u = models.User(id=uuid.uuid4(), email="PAY-anne@partner.example", tier="analyst",
                        stripe_customer_id="cus_self")
        env.db.add(u)
        env.db.add(models.AffiliateReferral(
            id=uuid.uuid4(), affiliate_id=anne.id, stripe_subscription_id="sub_self",
            stripe_customer_id="cus_self", source="checkout", terms_id=1, offer_type="regular",
            discount_pct=D(20), referral_code="ANNE", tier="analyst", billing_interval="year",
            list_price_cents=39900, attributed_at=dt.datetime(2026, 10, 1, tzinfo=UTC)))
        env.db.commit()
        assert [f["kind"] for f in owner.fraud_signals(env.db)[anne.id]] == ["self_referral"]

    def test_the_ip_of_a_new_signup_is_stored_only_as_a_hash(self, env):
        anne, _ = partner(env)
        u = h._user(env.db, "fresh@example.com")
        assert afs.record_signup_referral(env.db, u, "ANNE", None, ip="203.0.113.77") is True
        assert u.referred_ip_hash == afs.hash_ip("203.0.113.77") and len(u.referred_ip_hash) == 64
        assert "203.0.113.77" not in u.referred_ip_hash
        assert afs.hash_ip("") is None and afs.hash_ip(None) is None

    def test_flags_show_on_the_payout_screens_and_never_block(self, env, admin):
        import models
        owner, clean, selfy, farm = self._cast(env)
        p = payout(env, selfy, "150.00")
        payout(env, clean, "99.00")
        html = admin.client.get("/admin/affiliate_bulk_payouts/").get_data(as_text=True)
        assert 'id="flags"' in html and "Fraud signals" in html and EM_DASH not in html
        assert "Self-referral" in html and "Signups share a network" in html
        assert "1 referred customer uses the partner&#39;s own contact or payout email address" in html
        assert "a flag never blocks, holds" in html
        # a flagged row is still payable, exportable and can be marked paid
        (row,) = [x for x in ops.pending_payout_rows(env.db) if x["id"] == p.id]
        assert row["payable"] is True
        rows, _ = ops.select_for_export(env.db, [p.id], "paypal", "usd")
        assert [x["code"] for x in rows] == ["BOB"]
        res = ops.apply_paid_batch(env.db, ops.parse_paid_batch("%s, PP-9" % ops.payout_ref(p)))
        assert res["paid"] == [ops.payout_ref(p)]
        model_views(env, admin)
        ledger = admin.client.get("/admin/affiliatepayout/").get_data(as_text=True)
        assert "Fraud signals" in ledger and "Self-referral" in ledger and "twp-nav" in ledger
        env.db.expire_all()
        assert env.db.get(models.AffiliatePayout, p.id).status == "paid"


class TestBulkPayoutsOnAPhone:
    def test_rows_become_cards_with_amount_currency_method_and_reason(self, env, admin):
        r = TestBulkPayouts._world(self, env)
        html = admin.client.get("/admin/affiliate_bulk_payouts/").get_data(as_text=True)
        assert "@media (max-width:700px)" in html and html.count('<table class="cards">') == 4
        assert "table.cards tr.head{display:none;}" in html
        assert 'content:attr(data-label) ": "' in html
        # a payable row: partner, amount, currency and method are all in the card
        card = html.split('value="%d"' % r.anne.id)[1].split("</tr>")[0]
        assert 'class="card-title"><strong>ANNE</strong> Anne Lee' in card
        assert '<strong>108.45</strong><span class="only-card"> USD by PayPal</span>' in card
        assert 'data-label="Pay to">pay-anne@partner.example' in card and 'data-label="Export"' in card
        # a blocked row: the reason is in the card, and a missing method is said plainly
        blocked = html.split("Not payable yet")[1]
        assert 'data-label="Not payable">No tax form on file' in blocked
        assert '60.00 USD<span class="only-card"> by no payout method yet</span>' in blocked
        assert '90.00 USD<span class="only-card"> by PayPal</span>' in blocked
        # the preview before marking paid uses the same cards
        text = "%s, PP-AAA\n%s, PP-CCC" % (ops.payout_ref(r.anne), ops.payout_ref(r.dan))
        prev = admin.client.post("/admin/affiliate_bulk_payouts/mark-paid", data={"batch": text}).get_data(as_text=True)
        assert 'data-label="Result">Will be marked paid' in prev and 'data-label="Amount">108.45 USD' in prev
        assert EM_DASH not in html + prev


class TestProgramHome:
    NOW = dt.datetime(2026, 11, 24, 15, 0, tzinfo=UTC)

    def _seed(self, env):
        import affiliate_help_models as hm
        import models
        anne = paid_partner(env, "ANNE")
        paul = h.make_partner(env.db, "PAUL", status="paused", agreement_signed_at=None,
                              created_at=self.NOW - dt.timedelta(days=4))[0]
        for i, hours in enumerate((1, 30, 72)):
            env.db.add(models.AffiliateApplication(
                id=uuid.uuid4(), name="App %d" % i, email="app%d@example.com" % i, website="x.example",
                channels="yt", audience_size="1k_10k", promo_plan="p", country="Canada", status="new",
                created_at=self.NOW - dt.timedelta(hours=hours)))
        env.db.add(hm.AffiliateHelpEscalation(affiliate_id=anne.id, question="q?", status="open",
                                              created_at=self.NOW - dt.timedelta(hours=3)))
        env.db.add(om.AffiliateTaxForm(affiliate_id=anne.id, form_type="w9", status="received",
                                       storage_name="x.bin", original_filename="w9.pdf", size_bytes=10,
                                       uploaded_at=self.NOW - dt.timedelta(days=5)))
        env.db.commit()
        payout(env, anne, "108.45")
        return anne, paul

    def test_counts(self, env):
        import affiliate_owner as owner
        self._seed(env)
        data = owner.program_counts(env.db, self.NOW)
        cards = {c["key"]: c for c in data["cards"]}
        assert [c["key"] for c in data["cards"]] == ["applications", "questions", "tax_forms", "payable",
                                                     "unsigned", "activity", "fraud"]
        assert (cards["applications"]["count"], cards["applications"]["urgent"]) == (3, True)
        assert cards["applications"]["detail"] == "Oldest has waited 3 days - 1 over 48 hours"
        assert (cards["questions"]["count"], cards["questions"]["urgent"]) == (1, False)
        assert cards["questions"]["detail"] == "Oldest has waited 3 hours"
        assert (cards["tax_forms"]["count"], cards["tax_forms"]["urgent"]) == (1, True)
        assert (cards["payable"]["count"], cards["payable"]["detail"]) == (1, "108.45 USD")
        assert (cards["unsigned"]["count"], cards["unsigned"]["detail"]) == (1, "Oldest was approved 4 days ago")
        assert (cards["fraud"]["count"], cards["fraud"]["detail"]) == (0, "No signals")
        assert data["auto_approve"] == "Off" and data["jobs"] == {"queued": 0, "running": 0, "failed": 0}
        for c in data["cards"]:
            assert c["url"].startswith("/admin/") and EM_DASH not in c["title"] + c["detail"]

    def test_empty_program(self, env):
        import affiliate_owner as owner
        data = owner.program_counts(env.db, self.NOW)
        assert [c["count"] for c in data["cards"]] == [0] * 7
        assert not any(c["urgent"] for c in data["cards"])

    def test_home_page_is_first_in_the_menu_and_shows_live_numbers(self, env, admin):
        import config
        env.patch.setattr(config, "AFFILIATE_OWNER_EMAIL", "owner@tw.test", raising=False)
        self._seed(env)
        resp = admin.client.get("/admin/affiliate_home/")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200 and EM_DASH not in html and '<meta name="viewport"' in html
        for needle in ("<h1>Partner program</h1>", 'id="card-applications"', 'id="card-fraud"',
                       "New applications", "Tax forms awaiting review", "Payout rows payable now",
                       "Partners who have not signed", "owner@tw.test", "Referral link is remembered for",
                       "60 days", "twp-nav", "Auto-approve applications"):
            assert needle in html, needle
        import re
        nums = re.findall(r'id="card-(\w+)">\s*<div class="n">(\d+)</div>', html)
        assert dict(nums)["applications"] == "3" and dict(nums)["payable"] == "1"
        # first item of the Affiliates menu
        (cat,) = [m for m in admin.mod.admin.menu() if m.name == "Affiliates"]
        names = [c.name for c in cat.get_children()]
        assert names[0] == "Partner program" and "Year-end tax report" in names

    def test_home_is_admin_only(self, env, admin):
        admin.who.user = SimpleNamespace(id=None, email="x@example.com", roles=[])
        assert admin.client.get("/admin/affiliate_home/").status_code in (302, 403)
        assert admin.client.get("/admin/affiliate_tax_report/").status_code in (302, 403)
        assert admin.client.get("/admin/affiliate_tax_report/csv").status_code in (302, 403)

    def test_every_link_of_the_shared_nav_resolves_and_every_page_carries_it(self, env, admin):
        import affiliate_nav
        model_views(env, admin)
        assert affiliate_nav.NAV_ITEMS[0][0] == "/admin/affiliate_home/"
        for path, label, _group in affiliate_nav.NAV_ITEMS:
            resp = admin.client.get(path)
            assert resp.status_code == 200, (path, resp.status_code)
            html = resp.get_data(as_text=True)
            assert 'class="twp-nav"' in html, path
            assert html.count('class="twp-nav"') == 1, path
            for other, _l, _g in affiliate_nav.NAV_ITEMS:
                assert 'href="%s"' % other in html, (path, other)
        assert EM_DASH not in affiliate_nav.NAV_HTML


class TestTaxYearReport:
    def _seed(self, env):
        import models
        anne = paid_partner(env, "ANNE")                                          # W-9
        bob = paid_partner(env, "BOB", tax_form_type="w8ben")
        cara = paid_partner(env, "CARA")                                          # W-9, small
        dan = paid_partner(env, "DAN", tax_form_type=None, tax_form_received_at=None)
        env.db.add(models.AffiliateApplication(
            id=uuid.uuid4(), name="Anne Lee", email=anne.email, website="x.example", channels="yt",
            audience_size="1k_10k", promo_plan="p", country="United States", status="approved",
            affiliate_id=anne.id, created_at=dt.datetime(2026, 1, 2, tzinfo=UTC)))
        env.db.commit()

        def paid(aff, amount, when, currency="usd", ref="PP-1", paid_amount=None, month=1):
            p = payout(env, aff, amount, period=dt.date(when.year, month, 1), currency=currency, status="paid")
            p.paid_at, p.external_ref, p.paid_amount = when, ref, paid_amount
            env.db.commit()
            return p
        y = lambda m, d=10, yr=2026: dt.datetime(yr, m, d, 12, tzinfo=UTC)      # noqa: E731
        paid(anne, "400.00", y(3), month=2)
        paid(anne, "250.00", y(6), month=5, paid_amount=D("260.00"))             # paid at the exported amount
        paid(anne, "999.00", y(2, yr=2025), month=1)                              # another year
        paid(anne, "50.00", y(7), currency="eur", month=6)
        paid(bob, "900.00", y(4), month=3)
        paid(cara, "599.99", y(5), month=4)
        paid(dan, "700.00", y(8), month=7)
        paid(cara, "30.00", y(9), ref="carried:TWP000001", month=8)               # bookkeeping, not a payment
        payout(env, cara, "500.00", period=dt.date(2026, 10, 1))                  # pending: not paid
        return anne, bob, cara, dan

    def test_totals_forms_and_the_1099_flag(self, env):
        import affiliate_owner as owner
        self._seed(env)
        rep = owner.tax_year_report(env.db, 2026)
        got = {(r["code"], r["currency"]): r for r in rep["rows"]}
        assert sorted(got) == [("ANNE", "eur"), ("ANNE", "usd"), ("BOB", "usd"), ("CARA", "usd"), ("DAN", "usd")]
        a = got[("ANNE", "usd")]
        assert (a["total"], a["payouts"], a["nec"], a["form_label"], a["country"]) == (
            D("660.00"), 2, True, "W-9", "United States")
        assert got[("ANNE", "eur")]["nec"] is False and "convert to USD" in got[("ANNE", "eur")]["note"]
        assert (got[("BOB", "usd")]["nec"], got[("BOB", "usd")]["note"]) == (
            False, "Foreign partner (W-8): no 1099-NEC")
        assert (got[("CARA", "usd")]["total"], got[("CARA", "usd")]["nec"],
                got[("CARA", "usd")]["note"]) == (D("599.99"), False, "Under $600")
        assert (got[("DAN", "usd")]["form"], got[("DAN", "usd")]["nec"]) == (None, False)
        assert got[("DAN", "usd")]["note"] == "No tax form on file - get one before filing"
        assert rep["totals"] == [("eur", D("50.00")), ("usd", D("2859.99"))]
        assert (rep["nec_count"], rep["partners"]) == (1, 4)
        assert owner.tax_year_report(env.db, 2025)["totals"] == [("usd", D("999.00"))]
        assert owner.tax_year_report(env.db, 2024)["rows"] == []
        assert owner.tax_years(env.db, dt.datetime(2026, 11, 24, tzinfo=UTC)) == [2026, 2025]

    def test_csv(self, env):
        import affiliate_owner as owner
        self._seed(env)
        table = list(csv.reader(io.StringIO(owner.tax_year_csv(owner.tax_year_report(env.db, 2026)))))
        assert tuple(table[0]) == owner.TAX_CSV_HEADER and len(table) == 6
        assert table[2] == ["ANNE", "Anne Lee", "anne@partner.example", "United States", "W-9", "2026-01-06",
                            "USD", "660.00", "2", "yes", ""]
        assert owner.tax_report_filename(2026) == "tradewave-partner-payments-2026.csv"

    def test_admin_page_and_download(self, env, admin):
        self._seed(env)
        html = admin.client.get("/admin/affiliate_tax_report/?year=2026").get_data(as_text=True)
        assert EM_DASH not in html
        for needle in ("Year-end tax report", "2026: 4 partners paid", "1 likely 1099-NEC", "660.00",
                       "None on file", "$600 or more", "Download CSV (2026)", "twp-nav",
                       '<option value="2025">2025</option>'):
            assert needle in html, needle
        resp = admin.client.get("/admin/affiliate_tax_report/csv?year=2026")
        assert resp.status_code == 200 and resp.mimetype == "text/csv"
        assert 'filename="tradewave-partner-payments-2026.csv"' in resp.headers["Content-Disposition"]
        assert resp.get_data(as_text=True).startswith("partner_code,name,email,country,tax_form,")
        assert admin.audits[-1]["action"] == "affiliate_tax_report_exported"
        assert admin.audits[-1]["details"] == {"year": 2026, "rows": 5}
        empty = admin.client.get("/admin/affiliate_tax_report/?year=2019").get_data(as_text=True)
        assert "No payouts were marked paid in 2019." in empty
        assert admin.client.get("/admin/affiliate_tax_report/?year=junk").status_code == 200


class TestCapacityAndCron:
    def test_web_unit_runs_threaded_workers_like_the_api(self):
        unit = (h._REPO_ROOT / "ops" / "systemd" / "tradewave-web.service").read_text()
        assert "--worker-class gthread" in unit and "--threads 8" in unit

    def test_cron_installer_strips_email_from_the_report_line_only(self):
        import subprocess
        script = h._REPO_ROOT / "ops" / "install_affiliate_comms_cron.sh"
        crontab = "\n".join([
            "30 3 2 * * /venv/bin/python /home/flask/web/affiliate_report.py --email >> /var/log/x.log 2>&1",
            "31 3 2 * * /venv/bin/python /home/flask/web/affiliate_report.py --month 2026-10 --email",
            "32 3 2 * * /venv/bin/python /home/flask/web/affiliate_report.py --email-digest x",
            "0 5 * * * /venv/bin/python /home/flask/web/other_job.py --email >> /var/log/y.log",
        ]) + "\n"
        out = subprocess.run(["bash", str(script), "--print-strip"], input=crontab, text=True,
                             capture_output=True, check=True).stdout.splitlines()
        assert out == [
            "30 3 2 * * /venv/bin/python /home/flask/web/affiliate_report.py >> /var/log/x.log 2>&1",
            "31 3 2 * * /venv/bin/python /home/flask/web/affiliate_report.py --month 2026-10",
            "32 3 2 * * /venv/bin/python /home/flask/web/affiliate_report.py --email-digest x",
            "0 5 * * * /venv/bin/python /home/flask/web/other_job.py --email >> /var/log/y.log"]
        text = script.read_text()
        assert "affiliate_jobs.py" in text and "*/2 * * * *" in text and "10 14 * * *" in text

    def test_the_report_script_ignores_email(self, env, monkeypatch, caplog):
        import affiliate_report as rep
        import models
        called = []
        monkeypatch.setattr(rep, "send_monthly_statements", lambda *a, **k: called.append(a) or 0)
        monkeypatch.setattr(models, "Session", env.factory)
        import inspect
        src = inspect.getsource(rep.main)
        assert "send_monthly_statements(" not in src and "--email is ignored" in src
        assert "IGNORED" in inspect.getsource(rep)
        cutover = (h._REPO_ROOT / "ops" / "PROD_CUTOVER.md").read_text()
        assert "affiliate_report.py" in cutover and "--email" in cutover and EM_DASH not in cutover.split(
            "One statement email")[-1][:600]


def test_fix_0039_migration_matches_the_models():
    versions = h._REPO_ROOT / "migrations" / "versions"
    mig = (versions / "e2f3a4b5c6d7_affiliate_review_fixes.py").read_text()
    assert "revision = 'e2f3a4b5c6d7'" in mig and "down_revision = 'd1e2f3a4b5c6'" in mig
    import models
    for name in ("affiliate_jobs", "affiliate_program_settings"):
        for col in models.Base.metadata.tables[name].columns:
            assert '"%s"' % col.name in mig, (name, col.name)
    for col in ("exported_at", "exported_amount", "paid_amount", "referred_ip_hash"):
        assert '"%s"' % col in mig
    assert "CASCADE" in mig and "affiliate_tax_forms" in mig and "def downgrade" in mig
    assert EM_DASH not in mig


def test_no_em_dashes_in_the_fix_0039_code():
    root = h._REPO_ROOT / "web"
    for n in ("affiliate_owner.py", "affiliate_owner_admin.py", "affiliate_jobs.py", "affiliate_nav.py",
              "affiliate_comms_admin.py", "affiliate_comms_views.py",
              "affiliate_help_admin.py", "affiliate_report.py",
              "templates/admin/affiliate_list.html", "templates/partner_apply.html"):
        text = (root / n).read_text()
        assert EM_DASH not in text and "&mdash;" not in text, n
