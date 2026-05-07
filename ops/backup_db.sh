#!/bin/bash
# backup_db.sh — nightly Postgres dump for TW2
# Reads POSTGRES_DSN from /home/flask/config.py, dumps tradewave DB,
# gzips to /var/backups/tradewave/db_YYYYMMDD_HHMM.sql.gz, prunes >14 days.

set -euo pipefail

# Run from a dir flask can stat — caller cwd may be unreadable (e.g. /home/afshin).
cd /tmp

BACKUP_DIR=/var/backups/tradewave
LOG=/var/log/tradewave/backup.log
TS=$(date -u +"%Y%m%d_%H%M")
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
OUT="$BACKUP_DIR/db_${TS}.sql.gz"

mkdir -p "$BACKUP_DIR"

# Pull DSN from config.py without sourcing the file (it's Python).
DSN=$(/home/flask/venv/bin/python -c \
    "import sys; sys.path.insert(0,'/home/flask'); import config; print(config.POSTGRES_DSN)")

if [ -z "$DSN" ]; then
    echo "$NOW backup_db FAIL: empty POSTGRES_DSN" >> "$LOG"
    exit 2
fi

# pg_dump can take the DSN as a single arg.
if pg_dump --no-owner --no-privileges "$DSN" | gzip -c > "$OUT.tmp"; then
    mv "$OUT.tmp" "$OUT"
    SIZE=$(stat -c %s "$OUT")
    echo "$NOW backup_db PASS file=$OUT size=$SIZE" >> "$LOG"
else
    rm -f "$OUT.tmp"
    echo "$NOW backup_db FAIL: pg_dump failed" >> "$LOG"
    exit 3
fi

# Prune >14 days
find "$BACKUP_DIR" -maxdepth 1 -name 'db_*.sql.gz' -mtime +14 -delete

exit 0
