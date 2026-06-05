"""Provision the internal 'mcp' service key the MCP server uses to call the v1 gateway on behalf
of a WorkOS-authenticated researcher (docs/MCP_OAUTH_INTEGRATION.md). Idempotent + repeatable per env.

  cd /home/flask && venv-api/bin/python -m apiserver.provision_mcp_key

It (1) upserts a dedicated service user with api_tier='mcp', (2) mints ONE live api_keys row for it
(revoking any prior mcp-oauth-service keys), (3) writes MCP_GATEWAY_KEY into /etc/tradewave/secrets.env
if absent. The raw key is NEVER printed - only to the DB (as an HMAC hash) and to secrets.env
(root-owned). Restart the MCP + appserver afterwards so config picks the new env up.

This key is POWERFUL (it can act as any user at their REAL tier via X-TW-Principal-WorkOS). Keep it
loopback-internal + secrets.env only, never logged. The gateway only honors that header for the
service:true + workos_principal 'mcp' tier (auth._apply_on_behalf)."""
import os
import secrets as _secrets

from apiserver import auth, db, settings

SERVICE_EMAIL = "mcp-service@internal.tradewave"
KEY_NAME = "mcp-oauth-service"
SECRETS_PATH = "/etc/tradewave/secrets.env"


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
            cur.execute("UPDATE users SET api_tier = 'mcp' WHERE id = %s", (user_id,))
        else:
            cur.execute(
                "INSERT INTO users (email, api_tier, first_name) VALUES (%s, 'mcp', %s) RETURNING id",
                (SERVICE_EMAIL, "MCP Service"),
            )
            user_id = cur.fetchone()["id"]
        cur.execute(
            "UPDATE api_keys SET revoked_at = now() WHERE user_id = %s AND name = %s AND revoked_at IS NULL",
            (user_id, KEY_NAME),
        )
        cur.execute(
            "INSERT INTO api_keys (user_id, name, key_hash, prefix) VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, KEY_NAME, key_hash, prefix),
        )
        key_id = cur.fetchone()["id"]

    existing = ""
    if os.path.exists(SECRETS_PATH):
        with open(SECRETS_PATH) as f:
            existing = f.read()
    wrote = []
    if "MCP_GATEWAY_KEY=" not in existing:
        with open(SECRETS_PATH, "a") as f:
            f.write('\n# MCP -> v1 gateway service key (provision_mcp_key.py)\nMCP_GATEWAY_KEY="%s"\n' % raw_key)
        wrote.append("MCP_GATEWAY_KEY")

    print("provisioned mcp service key")
    print("  service user_id : %s" % user_id)
    print("  api_key id      : %s  (name=%s, prefix=%s)" % (key_id, KEY_NAME, prefix))
    print("  key_hash[:8]    : %s" % key_hash[:8])
    print("  secrets written : %s" % (", ".join(wrote) if wrote else "none (already present)"))
    print("  HMAC secret     : %s" % _classify(settings.API_KEY_HMAC_SECRET))
    print("NEXT: restart the MCP + appserver so config picks up MCP_GATEWAY_KEY.")


if __name__ == "__main__":
    main()
