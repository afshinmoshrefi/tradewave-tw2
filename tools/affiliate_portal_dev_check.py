"""DEV-BOX integration test for the affiliate dashboard + SMN expert module.

Requires: the dev box (live Postgres + secrets.env + /var/www/smn), run as flask:
  sudo -u flask bash -c 'set -a; . /etc/tradewave/secrets.env; set +a; \
    cd /home/flask/web && ../venv/bin/python ../tools/affiliate_portal_dev_check.py'
NOT a unit test - it exercises the real stack (incl. live Resend notifications
to SUPPORT_EMAIL_TO and a Stripe TEST-key invoice list) and cleans up after itself.
Run as flask with secrets.env sourced, CWD /home/flask/web. Cleans up after
itself. Prints PASS/FAIL lines; exits non-zero on any failure."""
import io
import os
import sys
import json
import subprocess

sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (f"  [{detail}]" if detail and not cond else ""))


TEST_EMAIL = "dev-test-partner@example.com"
TEST_CODE = "DEVTESTPRTNR"
ART_SLUG = "test-expert-sync-article"
ART_PATH = f"/var/www/smn/articles/{ART_SLUG}.html"
STATE_PATH = "/var/www/smn/expert_takes_state.json"

import config
from app import app
from models import (Session as DBSession, User, Affiliate, AffiliateSmnProfile,
                    ExpertTake, AuditLog)
from affiliate_portal.blueprint import set_user_loader

app.config["WTF_CSRF_ENABLED"] = False


def cleanup():
    s = DBSession()
    try:
        u = s.query(User).filter(User.email == TEST_EMAIL).first()
        a = s.query(Affiliate).filter(Affiliate.code == TEST_CODE).first()
        if a is not None:
            s.query(ExpertTake).filter(ExpertTake.affiliate_id == a.id).delete()
            p = s.get(AffiliateSmnProfile, a.id)
            if p is not None:
                s.delete(p)
            s.delete(a)
        if u is not None:
            s.query(AuditLog).filter(AuditLog.actor_user_id == u.id).delete()
            s.delete(u)
        s.commit()
    finally:
        s.close()
    for f in (ART_PATH, "/var/www/smn/experts/dev-test-partner.html"):
        if os.path.exists(f):
            os.unlink(f)
    if os.path.exists(STATE_PATH):
        os.unlink(STATE_PATH)
    photo = os.path.join(config.web_root_dir.rstrip("/"), "assets", "affiliate-logos",
                         TEST_CODE.lower() + "-photo.webp")
    if os.path.exists(photo):
        os.unlink(photo)


cleanup()   # start clean in case of a prior aborted run

s = DBSession()
try:
    user = User(email=TEST_EMAIL, first_name="Dev", last_name="Partner",
                roles=["user"], tier="explorer", email_verified=True)
    s.add(user)
    s.flush()
    from datetime import datetime, timezone
    aff = Affiliate(code=TEST_CODE, name="Dev Test Partner", email=TEST_EMAIL,
                    discount_pct=20, commission_pct=30, commission_model="recurring",
                    status="active", agreement_signed_at=datetime.now(timezone.utc),
                    agreement_signed_name="Dev Test Partner", agreement_version="test")
    s.add(aff)
    s.commit()
    user_id, aff_id = user.id, aff.id
finally:
    s.close()

# a fake SMN article for the injection test
os.makedirs(os.path.dirname(ART_PATH), exist_ok=True)
with open(ART_PATH, "w") as f:
    f.write("<!doctype html><html><head><title>t</title></head>"
            "<body><article><h1>Test article</h1><p>body</p></article></body></html>")


class FakeUser:
    """Detached stand-in with the attrs the portal touches."""
    def __init__(self, uid, email):
        self.id, self.email = uid, email
        self.roles, self.tier = ["user"], "explorer"
        self.first_name = "Dev"


set_user_loader(lambda: FakeUser(user_id, TEST_EMAIL))
client = app.test_client()

# --- 1. auto-link on first visit + overview renders
r = client.get("/account/affiliate/")
check("overview 200", r.status_code == 200, str(r.status_code))
check("overview shows code", TEST_CODE.encode() in r.data)
s = DBSession()
linked = s.get(Affiliate, aff_id).user_id
audit = (s.query(AuditLog).filter(AuditLog.action == "affiliate_linked",
                                  AuditLog.actor_user_id == user_id).count())
s.close()
check("auto-link wrote user_id", str(linked) == str(user_id), str(linked))
check("auto-link audited", audit == 1, str(audit))

# --- 2. the other read tabs
for tab in ("performance", "payouts", "links", "profile"):
    r = client.get(f"/account/affiliate/{tab}")
    check(f"{tab} 200", r.status_code == 200, str(r.status_code))

# --- 3. profile edit + validators
r = client.post("/account/affiliate/profile", data={
    "page_display_name": "Dev T. Partner", "page_note": "I use TradeWave daily.",
    "page_signoff": "Dev, options coach"}, follow_redirects=True)
check("profile save", b"Profile updated." in r.data)
r = client.post("/account/affiliate/profile", data={
    "page_note": "visit http://spam.example now"}, follow_redirects=True)
check("profile rejects links", b"plain text" in r.data)

# --- 4. photo upload (PIL round-trip, EXIF strip, webp out)
from PIL import Image
buf = io.BytesIO()
Image.new("RGB", (900, 700), (30, 120, 200)).save(buf, "PNG")
buf.seek(0)
r = client.post("/account/affiliate/profile/photo",
                data={"photo": (buf, "me.png")},
                content_type="multipart/form-data", follow_redirects=True)
photo_path = os.path.join(config.web_root_dir.rstrip("/"), "assets", "affiliate-logos",
                          TEST_CODE.lower() + "-photo.webp")
check("photo upload", b"Photo updated." in r.data and os.path.exists(photo_path))
if os.path.exists(photo_path):
    im = Image.open(photo_path)
    check("photo resized+webp", im.format == "WEBP" and max(im.size) <= 512, str(im.size))

# --- 5. SMN tab: hidden -> invited -> accept terms
r = client.get("/account/affiliate/smn")
check("smn hidden without invite", r.status_code == 404, str(r.status_code))
s = DBSession()
s.add(AffiliateSmnProfile(affiliate_id=aff_id, status="invited"))
s.commit()
s.close()
r = client.get("/account/affiliate/smn")
check("smn invited shows terms", r.status_code == 200 and b"Contributor Terms" in r.data)
r = client.post("/account/affiliate/smn/accept", data={"agree": "yes"}, follow_redirects=True)
check("terms accept", b"Welcome to the SMN expert program" in r.data)
s = DBSession()
prof = s.get(AffiliateSmnProfile, aff_id)
check("terms audit fields", prof.status == "active" and prof.terms_accepted_at is not None
      and prof.terms_snapshot and prof.terms_version == "2026-07-07", prof.status)
check("slug auto-generated", prof.slug == "dev-t-partner", str(prof.slug))
EXPERT_SLUG = prof.slug
s.close()

# --- 6. take lifecycle: draft+submit -> approve(publish) via service
r = client.post("/account/affiliate/smn/takes/new", data={
    "article_slug": ART_SLUG, "title": "My read on this setup",
    "body_md": "The window is real. **I would sell the put spread** below support.\n\n"
               "Risk is defined; see <script>alert(1)</script> nothing here.",
    "execution_note": "Sold the Aug 210/220 call spread at 3.10",
    "scored_call": "yes", "call_symbol": "aapl", "call_direction": "long",
    "call_entry": "2026-07-15", "call_exit": "2026-08-30",
    "action": "submit"}, follow_redirects=True)
check("take submitted", b"Take submitted for review." in r.data)
s = DBSession()
take = s.query(ExpertTake).filter(ExpertTake.affiliate_id == aff_id).one()
check("take status submitted", take.status == "submitted", take.status)
check("call normalized", take.declared_call == {"symbol": "AAPL", "direction": "long",
      "entry_date": "2026-07-15", "exit_date": "2026-08-30"}, str(take.declared_call))
import expert_takes_service as ets
ets.approve_and_publish(s, take, s.get(User, user_id))
s.commit()
rendered = take.rendered_html
take_id = str(take.id)
s.close()
check("publish rendered+sanitized",
      "<strong>" in rendered and "<script" not in rendered and "alert(1)" in rendered)

# --- 7. internal feed serves it
import config as _cfg
r = client.get("/internal/expert_takes", headers={"X-Service-Key": _cfg.SERVICE_API_KEY})
feed = r.get_json()
check("feed has take", len(feed["takes"]) == 1 and feed["takes"][0]["id"] == take_id)
check("feed expert block", feed["takes"][0]["expert"]["slug"] == EXPERT_SLUG
      and feed["takes"][0]["expert"]["code"] == TEST_CODE)
check("feed cursor set", bool(feed["cursor"]))

# --- 8. SMN-side sync: inject + hub page
rc = subprocess.run(["/home/flask/venv/bin/python3", "/home/flask/smn/expert_sync.py"],
                    capture_output=True, text=True)
art = open(ART_PATH).read()
hub = f"/var/www/smn/experts/{EXPERT_SLUG}.html"
check("expert_sync exit 0", rc.returncode == 0, rc.stderr[-300:])
check("article injected", "TW-EXPERT-DESK:START" in art and "expert-" + EXPERT_SLUG in art
      and "Scored call:" in art and f"?code={TEST_CODE}" in art)
check("hub page built", os.path.exists(hub) and ART_SLUG in open(hub).read())

# idempotency: run again, article must be unchanged
before = open(ART_PATH).read()
subprocess.run(["/home/flask/venv/bin/python3", "/home/flask/smn/expert_sync.py"],
               capture_output=True, text=True)
check("sync idempotent", open(ART_PATH).read() == before)

# heal: simulate article regeneration wiping the section
with open(ART_PATH, "w") as f:
    f.write("<!doctype html><html><body><article><h1>Regenerated</h1></article></body></html>")
subprocess.run(["/home/flask/venv/bin/python3", "/home/flask/smn/expert_sync.py"],
               capture_output=True, text=True)
check("sync heals regenerated article", "TW-EXPERT-DESK:START" in open(ART_PATH).read())

# --- 9. retract via portal -> sync removes block
r = client.post(f"/account/affiliate/smn/takes/{take_id}/retract", follow_redirects=True)
check("retract", b"Take retracted" in r.data)
rc = subprocess.run(["/home/flask/venv/bin/python3", "/home/flask/smn/expert_sync.py"],
                    capture_output=True, text=True)
check("sync removes retracted", "TW-EXPERT-DESK:START" not in open(ART_PATH).read(),
      rc.stderr[-200:])

# --- 10. non-affiliate user sees the invite-only page (no probing)
set_user_loader(lambda: FakeUser("00000000-0000-0000-0000-000000000000", "nobody@example.com"))
r = client.get("/account/affiliate/")
check("non-affiliate clean page", r.status_code == 200 and b"invite-only" in r.data)

cleanup()
print("\n%d/%d passed" % (sum(1 for _, ok in RESULTS if ok), len(RESULTS)))
sys.exit(0 if all(ok for _, ok in RESULTS) else 1)
