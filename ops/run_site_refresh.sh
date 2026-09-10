#!/usr/bin/env bash
# Resolve code through the invoking release, and share one publication lock with
# scorecard updates so the daily-pick ledger cannot be overwritten concurrently.
set -euo pipefail
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
set -a
. /etc/tradewave/secrets.env
set +a
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT/site/lib:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec 9>/var/lib/tradewave/site/refresh.lock
flock -n 9 || exit 0
PY=/home/flask/venv/bin/python
case "${1:-}" in
  home)
    rc=0
    "$PY" site/home_opportunities.py || rc=$?
    # A valid empty screen preserves the CSV. The renderer omits closed windows.
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then exit "$rc"; fi
    "$PY" site/generate_home_page.py
    ;;
  scorecard) "$PY" site/generate_scorecard.py ;;
  daily-pick) "$PY" site/generate_daily_ai_pick.py ;;
  *) echo 'Expected home, scorecard, or daily-pick' >&2; exit 2 ;;
esac
