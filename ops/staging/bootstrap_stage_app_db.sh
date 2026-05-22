#!/usr/bin/env bash
# TW2 staging APP-box DB bootstrap.
# Run after bootstrap_stage_app_code.sh and after /etc/tradewave/secrets.env is in place.
# Usage (via the env-driven runner, which prepends the target coordinates):
#   ops/staging/run.sh {staging|prod} bootstrap_stage_app_db.sh
#
# What this does:
#   1. Source /etc/tradewave/secrets.env (root reads it)
#   2. Extract password from POSTGRES_DSN
#   3. ALTER ROLE tradewave PASSWORD ... (so TCP auth works)
#   4. As flask: alembic upgrade head against the staging DB
#   5. Verify expected tables exist

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

SECRETS=/etc/tradewave/secrets.env
[[ -r "$SECRETS" ]] || { echo "Missing $SECRETS — upload it first." >&2; exit 1; }

hdr "1. source secrets (root)"
set -a
# shellcheck disable=SC1090
. "$SECRETS"
set +a
[[ -n "${POSTGRES_DSN:-}" ]] || { echo "POSTGRES_DSN not set in $SECRETS" >&2; exit 1; }

hdr "2. extract password from POSTGRES_DSN"
# postgresql://tradewave:<pw>@127.0.0.1:5432/tradewave
PG_PW=$(printf '%s' "$POSTGRES_DSN" | sed -E 's|^postgresql://[^:]+:([^@]+)@.*$|\1|')
if [[ -z "$PG_PW" || "$PG_PW" == "$POSTGRES_DSN" ]]; then
    echo "Could not parse password from POSTGRES_DSN; check the format." >&2
    exit 1
fi
echo "password parsed: ${#PG_PW} chars"

hdr "3. ALTER ROLE tradewave"
# Password is alphanumeric (no quotes) by construction, but escape defensively.
PG_PW_ESC=$(printf '%s' "$PG_PW" | sed "s/'/''/g")
sudo -u postgres psql <<SQL >/dev/null
ALTER ROLE tradewave WITH PASSWORD '${PG_PW_ESC}';
SQL
echo "role password set"

hdr "4. test TCP auth"
PGPASSWORD="$PG_PW" psql -h 127.0.0.1 -U tradewave -d tradewave -tAc 'SELECT current_user, current_database()' || {
    echo "TCP auth failed — check pg_hba.conf"
    exit 1
}

hdr "5. alembic upgrade head"
cd /home/flask/web
# alembic.ini uses env var POSTGRES_DSN via env.py (per dev convention)
sudo -u flask bash -c "
    set -a
    . $SECRETS
    set +a
    cd /home/flask/web
    /home/flask/venv/bin/alembic upgrade head
"

hdr "6. verify tables"
PGPASSWORD="$PG_PW" psql -h 127.0.0.1 -U tradewave -d tradewave -c '\dt'
PGPASSWORD="$PG_PW" psql -h 127.0.0.1 -U tradewave -d tradewave -tAc "SELECT version_num FROM alembic_version;"

echo
echo "=== DB bootstrap complete ==="
echo "Schema head: $(PGPASSWORD="$PG_PW" psql -h 127.0.0.1 -U tradewave -d tradewave -tAc 'SELECT version_num FROM alembic_version;')"
echo "Next: lift US-only data subset, then systemd services + nginx + cloudflared."
