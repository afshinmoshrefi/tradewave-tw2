"""Provision the internal 'chatbot' service key Tara uses to call the v1 gateway
(docs/TARA_GATEWAY_INTEGRATION.md, metering option A). Idempotent + repeatable per env.

  cd /home/flask && venv-api/bin/python -m apiserver.provision_chatbot_key

It (1) upserts a dedicated service user with api_tier='chatbot', (2) mints ONE live
api_keys row for it (revokes any prior tara-chatbot-service keys), (3) writes
TARA_GATEWAY_KEY + TW2_GATEWAY_URL into /etc/tradewave/secrets.env if absent.

SECURITY: the raw key is NEVER printed - it is written only to the DB (as an HMAC hash)
and to secrets.env (root-owned). Output is classification only. Restart the appserver
afterwards so config.py picks the new env up. The gateway base is PER-ENV; override
TW2_GATEWAY_URL in secrets.env for staging/prod (gateway is :80 there, not :8088)."""
import os
import secrets as _secrets

from apiserver import auth, db, settings

SERVICE_EMAIL = "tara-service@internal.tradewave"
KEY_NAME = "tara-chatbot-service"
SECRETS_PATH = "/etc/tradewave/secrets.env"
DEFAULT_DEV_GATEWAY = "http://127.0.0.1:8088/v1"


def _classify(s):
    return "set(%d chars)" % len(s) if s else "MISSING"


def main():
    if not settings.API_KEY_HMAC_SECRET:
        raise SystemExit("API_KEY_HMAC_SECRET unset; cannot hash a key. Fix secrets.env first.")
    if not settings.POSTGRES_DSN:
        raise SystemExit("POSTGRES_DSN unset; cannot reach the users DB.")

    raw_key = "tw_svc_" + _secrets.token_urlsafe(32)
    key_hash = auth.hash_key(raw_key)
    prefix = raw_key[:12]

    with db.cursor(commit=True) as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (SERVICE_EMAIL,))
        row = cur.fetchone()
        if row:
            user_id = row["id"]
            cur.execute("UPDATE users SET api_tier = 'chatbot' WHERE id = %s", (user_id,))
        else:
            cur.execute(
                "INSERT INTO users (email, api_tier, first_name) VALUES (%s, 'chatbot', %s) RETURNING id",
                (SERVICE_EMAIL, "Tara Service"),
            )
            user_id = cur.fetchone()["id"]
        # one live key only: revoke prior tara-chatbot-service keys, then insert the new one.
        cur.execute(
            "UPDATE api_keys SET revoked_at = now() WHERE user_id = %s AND name = %s AND revoked_at IS NULL",
            (user_id, KEY_NAME),
        )
        cur.execute(
            "INSERT INTO api_keys (user_id, name, key_hash, prefix) VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, KEY_NAME, key_hash, prefix),
        )
        key_id = cur.fetchone()["id"]

    # write secrets.env (only if the vars are absent - never clobber an operator-set value).
    wrote = []
    existing = ""
    if os.path.exists(SECRETS_PATH):
        with open(SECRETS_PATH) as f:
            existing = f.read()
    to_add = []
    if "TARA_GATEWAY_KEY=" not in existing:
        to_add.append('TARA_GATEWAY_KEY="%s"' % raw_key)
        wrote.append("TARA_GATEWAY_KEY")
    if "TW2_GATEWAY_URL=" not in existing:
        to_add.append('TW2_GATEWAY_URL="%s"' % (os.environ.get("TW2_GATEWAY_URL") or DEFAULT_DEV_GATEWAY))
        wrote.append("TW2_GATEWAY_URL")
    if to_add:
        with open(SECRETS_PATH, "a") as f:
            f.write("\n# Tara -> v1 gateway (provision_chatbot_key.py)\n" + "\n".join(to_add) + "\n")

    print("provisioned chatbot service key")
    print("  service user_id : %s" % user_id)
    print("  api_key id      : %s  (name=%s, prefix=%s)" % (key_id, KEY_NAME, prefix))
    print("  key_hash[:8]    : %s" % key_hash[:8])
    print("  secrets written : %s" % (", ".join(wrote) if wrote else "none (already present)"))
    print("  HMAC secret     : %s" % _classify(settings.API_KEY_HMAC_SECRET))
    print("NEXT: restart the appserver so config.py picks up the new env.")


if __name__ == "__main__":
    main()
