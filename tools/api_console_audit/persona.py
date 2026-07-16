"""Switch the single test user row to a persona state, then render console pages.
Usage: persona.py <label> <tier> <api_tier|NULL> <trial:active|past|none>
Renders keys+billing to html/<label>_{keys,billing}.html and prints signals.
"""
import os, sys
sys.path.insert(0, "/home/flask"); sys.path.insert(0, "/home/flask/web")
sys.path.insert(0, "/tmp/claude-0/-home-flask/0a525026-2010-4572-a505-12cf6e7a1966/scratchpad")
import psycopg2, psycopg2.extras, json

STATE = "/tmp/claude-0/-home-flask/0a525026-2010-4572-a505-12cf6e7a1966/scratchpad/audit_state.json"
HTMLDIR = "/tmp/claude-0/-home-flask/0a525026-2010-4572-a505-12cf6e7a1966/scratchpad/html"
st = json.load(open(STATE))
UID = st["db_user_id"]
os.environ["AUDIT_DB_USER_ID"] = UID

label, tier, api_tier, trial = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
trial_sql = {"active": "now()+interval '5 days'", "past": "now()-interval '2 days'", "none": "NULL"}[trial]
api_val = None if api_tier.upper() == "NULL" else api_tier

con = psycopg2.connect(os.environ["POSTGRES_DSN"]); con.autocommit = True
cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute(f"UPDATE users SET tier=%s, api_tier=%s, reverse_trial_ends_at={trial_sql} WHERE id=%s RETURNING tier, api_tier, reverse_trial_ends_at",
            (tier, api_val, UID))
row = cur.fetchone()
con.close()
print(f"[{label}] DB set -> tier={row['tier']} api_tier={row['api_tier']} trial_ends={row['reverse_trial_ends_at']}")

import driver as D
for tab in ("keys", "billing"):
    out = f"{HTMLDIR}/{label}_{tab}.html"
    code, n = D.render_to(f"/account/api/{tab}", out)
    print(f"  render /{tab}: {code} ({n}b) -> {out}")
