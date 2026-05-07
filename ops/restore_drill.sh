#!/bin/bash
# restore_drill.sh — verify latest backup is restorable
# Picks newest /var/backups/tradewave/db_*.sql.gz, restores into a temp DB,
# checks user count, drops temp DB. Outputs single PASS/FAIL line.

set -uo pipefail

BACKUP_DIR=/var/backups/tradewave
TMP_DB=tradewave_restore_test
LOG=/var/log/tradewave/restore_drill.log
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

fail() {
    local msg="$1"
    echo "RESTORE_DRILL: FAIL: $msg"
    echo "$NOW $msg" >> "$LOG" 2>/dev/null || true
    # best effort cleanup
    sudo -u postgres psql -d postgres -tAc \
        "DROP DATABASE IF EXISTS $TMP_DB;" >/dev/null 2>&1 || true
    exit 1
}

LATEST=$(ls -1t "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | head -1)
[ -n "$LATEST" ] || fail "no backup files in $BACKUP_DIR"
[ -s "$LATEST" ] || fail "latest backup is empty: $LATEST"

# Drop temp DB if leftover, then create.
sudo -u postgres psql -d postgres -tAc \
    "DROP DATABASE IF EXISTS $TMP_DB;" >/dev/null \
    || fail "DROP IF EXISTS failed"
sudo -u postgres psql -d postgres -tAc \
    "CREATE DATABASE $TMP_DB;" >/dev/null \
    || fail "CREATE DATABASE failed"

# Restore into temp DB.
if ! gunzip -c "$LATEST" | sudo -u postgres psql -v ON_ERROR_STOP=1 -d "$TMP_DB" \
        > /tmp/restore_drill.psql.out 2>&1; then
    sudo -u postgres psql -d postgres -tAc \
        "DROP DATABASE IF EXISTS $TMP_DB;" >/dev/null 2>&1 || true
    fail "psql restore failed (see /tmp/restore_drill.psql.out)"
fi

# Count users.
N=$(sudo -u postgres psql -d "$TMP_DB" -tAc \
        "SELECT count(*) FROM users;" 2>/dev/null) \
    || { sudo -u postgres psql -d postgres -tAc \
            "DROP DATABASE IF EXISTS $TMP_DB;" >/dev/null 2>&1 || true
         fail "SELECT count(*) FROM users failed (table missing?)"; }

N=$(echo "$N" | tr -d '[:space:]')
case "$N" in
    ''|*[!0-9]*) sudo -u postgres psql -d postgres -tAc \
                    "DROP DATABASE IF EXISTS $TMP_DB;" >/dev/null 2>&1 || true
                 fail "non-numeric user count: '$N'";;
esac

if [ "$N" -le 0 ]; then
    sudo -u postgres psql -d postgres -tAc \
        "DROP DATABASE IF EXISTS $TMP_DB;" >/dev/null 2>&1 || true
    fail "user count is $N (expected > 0)"
fi

# Clean up.
sudo -u postgres psql -d postgres -tAc \
    "DROP DATABASE IF EXISTS $TMP_DB;" >/dev/null 2>&1 || true

echo "RESTORE_DRILL: PASS ($N users restored)"
echo "$NOW PASS users=$N source=$LATEST" >> "$LOG" 2>/dev/null || true
exit 0
