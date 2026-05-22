#!/usr/bin/env bash
# Capture dev DB schema (DDL + alembic_version row) and ship to staging-app.
# Run on .176 as root. Replaces step 5 of bootstrap_stage_app_db.sh
# (which fails because alembic baseline is stamp-only — dev DB was hand-rolled).
#
# Steps:
#   1. pg_dump --schema-only on .176 → /tmp/tw2_schema.sql
#   2. append --data-only --table=alembic_version (so staging knows it's at head)
#   3. scp to staging-app
#   4. on staging-app: drop + recreate tradewave DB (clears the partial state),
#      restore from /tmp/tw2_schema.sql
#   5. clean up /tmp files on both ends

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

if [[ "$EUID" -ne 0 ]]; then
    echo "Run on .176 as root (needs sudo -u postgres pg_dump)." >&2
    exit 1
fi

LOCAL=/tmp/tw2_schema.sql
STAGE_IP="$TGT_APP_PUB"
SSH_PORT="$TGT_SSH_PORT"

hdr "1. pg_dump schema (DDL only)"
sudo -u postgres pg_dump --schema-only --no-owner --no-privileges tradewave > "$LOCAL"
echo "wrote $LOCAL: $(wc -l < "$LOCAL") lines"

hdr "2. append alembic_version row (so staging knows it's at head)"
sudo -u postgres pg_dump --data-only --no-owner --table=alembic_version tradewave >> "$LOCAL"
echo "appended; total $(wc -l < "$LOCAL") lines"
echo "Tables in dump:"
grep -E "^CREATE TABLE" "$LOCAL" | awk '{print "  ", $3}'
echo "Alembic head in dump:"
grep -A1 "COPY public.alembic_version" "$LOCAL" | tail -1 | head -c 60; echo

hdr "3. scp to staging-app"
scp -P "$SSH_PORT" "$LOCAL" "root@${STAGE_IP}:/tmp/tw2_schema.sql"

hdr "4. restore on staging-app (drop + recreate DB)"
ssh "root@${STAGE_IP}" -p "$SSH_PORT" 'bash -s' <<'REMOTE'
set -euo pipefail
echo "current state on staging:"
sudo -u postgres psql -tAc "\l" | grep -E '^tradewave' || echo "  (no tradewave DB)"

# Terminate any connections (there shouldn't be any, but be safe)
sudo -u postgres psql -tAc \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='tradewave' AND pid<>pg_backend_pid()" >/dev/null

sudo -u postgres dropdb --if-exists tradewave
sudo -u postgres createdb -O tradewave tradewave
echo "DB recreated empty."

# Restore as tradewave (matches dev ownership). PG_PW comes from secrets.env.
set -a
. /etc/tradewave/secrets.env
set +a
PG_PW=$(printf '%s' "$POSTGRES_DSN" | sed -E 's|^postgresql://[^:]+:([^@]+)@.*$|\1|')
PGPASSWORD="$PG_PW" psql -h 127.0.0.1 -U tradewave -d tradewave -f /tmp/tw2_schema.sql > /dev/null

echo "Tables created:"
PGPASSWORD="$PG_PW" psql -h 127.0.0.1 -U tradewave -d tradewave -tAc \
  "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename" | sed 's/^/  /'
echo "Alembic head on staging:"
PGPASSWORD="$PG_PW" psql -h 127.0.0.1 -U tradewave -d tradewave -tAc \
  "SELECT version_num FROM alembic_version"

shred -u /tmp/tw2_schema.sql
echo "remote /tmp/tw2_schema.sql wiped"
REMOTE

hdr "5. cleanup local"
shred -u "$LOCAL"
echo "local $LOCAL wiped"

echo
echo "=== schema seed complete ==="
