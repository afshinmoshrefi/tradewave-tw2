"""Render the REAL console routes/templates via the Flask test client, injecting
the authenticated DB user WorkOS would supply (token issuance is disabled on this
shared staging env, so we bypass ONLY the token check - all route logic, tier
resolution, and Jinja templates are the real production ones). Persona switching
is a DB UPDATE; the loader re-queries per request so the switch is reflected.
"""
import os, sys, re
sys.path.insert(0, "/home/flask"); sys.path.insert(0, "/home/flask/web")

DB_USER_ID = os.environ["AUDIT_DB_USER_ID"]

import app as webapp
from models import Session as DBSession, User
import api_portal.blueprint as bp

def _load_user():
    s = DBSession()
    try:
        return s.query(User).filter_by(id=DB_USER_ID).first()
    finally:
        s.close()

# Override BOTH the console loader and the web get_current_user path used by /account.
bp.set_user_loader(_load_user)
webapp.get_current_user = _load_user  # so /account (web route) also resolves

app = webapp.app
app.config["WTF_CSRF_ENABLED"] = True  # keep CSRF real; we round-trip the token

client = app.test_client()

def get(path):
    return client.get(path, base_url="https://tw2-dev.trxstat.com")

def extract_csrf(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    return m.group(1) if m else None

def post(path, data, referer="https://tw2-dev.trxstat.com/account/api/keys"):
    # WTF_CSRF_SSL_STRICT requires a same-origin Referer for HTTPS form posts.
    return client.post(path, data=data, base_url="https://tw2-dev.trxstat.com",
                       headers={"Referer": referer})

def render_to(path, out_html):
    r = get(path)
    body = r.get_data(as_text=True)
    with open(out_html, "w") as f:
        f.write(body)
    return r.status_code, len(body)
