#!/bin/bash
# uptime_check.sh — TW2 dev box uptime probe
# Curls public endpoints, logs PASS/FAIL to /var/log/tradewave/uptime.log.
# Healthy: 200 (root) or 200/302 (/app/, redirect to WorkOS is OK).
# Failure: 5xx or connection error.

set -u

LOG=/var/log/tradewave/uptime.log
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EXIT=0

check() {
    local url="$1"
    local label="$2"
    local accept="$3"   # space-separated allowed codes
    local code
    code=$(curl -sS -o /dev/null -w "%{http_code}" \
                --max-time 10 --connect-timeout 5 \
                "$url" 2>/dev/null) || code="000"
    local ok=0
    for a in $accept; do
        if [ "$code" = "$a" ]; then ok=1; break; fi
    done
    if [ "$ok" = "1" ]; then
        echo "$TS PASS $label code=$code" >> "$LOG"
    else
        echo "$TS FAIL $label code=$code" >> "$LOG"
        EXIT=1
    fi
}

check "https://tw2.trxstat.com/"     "root" "200"
check "https://tw2.trxstat.com/app/" "app"  "200 302"

exit $EXIT
