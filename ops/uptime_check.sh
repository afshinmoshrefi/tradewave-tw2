#!/bin/bash
# uptime_check.sh — TW2 uptime probe (env-aware)
# Curls the env's own public root + /app/, logs PASS/FAIL to
# /var/log/tradewave/uptime.log. Base URL comes from config.domain_root
# (TW2_DOMAIN_ROOT) so dev/staging/prod each probe themselves — was
# previously hardcoded to tw2.trxstat.com (dev) and silently "passed"
# on staging by probing the wrong box.
# Healthy: 200 (root) or 200/302 (/app/). Failure: 5xx / connection error.

set -u

LOG=/var/log/tradewave/uptime.log
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EXIT=0

BASE=$(/home/flask/venv/bin/python -c \
    "import sys; sys.path.insert(0,'/home/flask'); import config; print((config.domain_root or 'https://tw2.trxstat.com').rstrip('/'))" 2>/dev/null) \
    || BASE="https://tw2.trxstat.com"

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

check "${BASE}/"     "root" "200"
check "${BASE}/app/" "app"  "200 302"

exit $EXIT
