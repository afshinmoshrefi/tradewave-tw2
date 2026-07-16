"""Provision the internal 'mcp' service key the MCP server uses to call the v1 gateway on behalf
of a WorkOS-authenticated researcher (docs/MCP_OAUTH_INTEGRATION.md). Idempotent + repeatable per env.

  cd /home/flask && venv-api/bin/python -m apiserver.provision_mcp_key

It (1) upserts a dedicated service_account user with api_tier='mcp', (2) ensures the
MCP_GATEWAY_KEY already in the environment has exactly ONE live api_keys row (or mints
and stores one on first provision), and (3) writes MCP_GATEWAY_KEY into
/etc/tradewave/secrets.env if absent. The raw key is NEVER printed - only its HMAC is
stored in the DB and the raw value in secrets.env (root-owned). Re-running is idempotent:
it never rotates the DB key away from the value the service still has configured.

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

    configured_raw = (os.environ.get("MCP_GATEWAY_KEY") or "").strip()
    raw_key = configured_raw or ("tw_svc_" + _secrets.token_urlsafe(32))
    key_hash = auth.hash_key(raw_key)
    prefix = raw_key[:12]

    with db.cursor(commit=True) as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (SERVICE_EMAIL,))
        row = cur.fetchone()
        if row:
            user_id = row["id"]
            cur.execute(
                "UPDATE users SET api_tier = 'mcp', "
                "roles = '[\"service_account\"]'::jsonb WHERE id = %s",
                (user_id,),
            )
        else:
            cur.execute(
                "INSERT INTO users (email, api_tier, first_name, roles) "
                "VALUES (%s, 'mcp', %s, '[\"service_account\"]'::jsonb) "
                "RETURNING id",
                (SERVICE_EMAIL, "MCP Service"),
            )
            user_id = cur.fetchone()["id"]
        cur.execute(
            "SELECT id, user_id FROM api_keys WHERE key_hash = %s",
            (key_hash,),
        )
        key_row = cur.fetchone()
        if key_row and key_row["user_id"] != user_id:
            raise RuntimeError("configured MCP_GATEWAY_KEY belongs to another user")
        cur.execute(
            "UPDATE api_keys SET revoked_at = now() WHERE user_id = %s "
            "AND name = %s AND key_hash <> %s AND revoked_at IS NULL",
            (user_id, KEY_NAME, key_hash),
        )
        if key_row:
            key_id = key_row["id"]
            cur.execute(
                "UPDATE api_keys SET name = %s, prefix = %s, revoked_at = NULL "
                "WHERE id = %s",
                (KEY_NAME, prefix, key_id),
            )
        else:
            cur.execute(
                "INSERT INTO api_keys (user_id, name, key_hash, prefix) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (user_id, KEY_NAME, key_hash, prefix),
            )
            key_id = cur.fetchone()["id"]

    existing = ""
    if os.path.exists(SECRETS_PATH):
        with open(SECRETS_PATH) as f:
            existing = f.read()
    wrote = []
    if not configured_raw and "MCP_GATEWAY_KEY=" not in existing:
        with open(SECRETS_PATH, "a") as f:
            f.write('\n# MCP -> v1 gateway service key (provision_mcp_key.py)\nMCP_GATEWAY_KEY="%s"\n' % raw_key)
        wrote.append("MCP_GATEWAY_KEY")

    print("provisioned mcp service key")
    print("  service user_id : %s" % user_id)
    print("  api_key id      : %s  (name=%s, prefix=%s)" % (key_id, KEY_NAME, prefix))
    print("  key_hash[:8]    : %s" % key_hash[:8])
    print("  secrets written : %s" % (", ".join(wrote) if wrote else "none (already present)"))
    print("  HMAC secret     : %s" % _classify(settings.API_KEY_HMAC_SECRET))
    print("NEXT: restart the API gateway + MCP so auth/key caches reload.")


if __name__ == "__main__":
    main()
