#!/usr/bin/env bash
# regen_site.sh - regenerate ALL rendered MAIN-SITE output on THIS box, with the
# correct public host. Run ON a web box (where /var/www/tradewave lives), as part
# of deploy.sh or standalone. This closes the deploy gap: stock deploy.sh only runs
# generate_text_pages.py, so home/scorecard/insights/learn/research/about/daily-pick/
# ticker/markets only refreshed on the next cron tick - a code/content change never
# reached the served site on deploy. This regenerates them all, immediately, with
# TW2_PUBLIC_HOST sourced so every page bakes the correct env host (never tw2-dev).
#
# Portal (developers.*) is regenerated separately by ops/assemble_developer_portal.sh
# on the APP box (where the portal vhost + docroot live).
#
# Usage (on the target web box):  sudo -u flask bash /home/flask/ops/regen_site.sh
set -uo pipefail   # NOT -e: attempt every generator, report failures, never half-abort.

PY=/home/flask/venv/bin/python
SITE=/home/flask/site
SECRETS=/etc/tradewave/secrets.env

# --- env: bake with the correct public host or refuse -------------------------
[ -r "$SECRETS" ] || { echo "FATAL: $SECRETS not readable"; exit 2; }
set -a; . "$SECRETS"; set +a
[ -n "${TW2_PUBLIC_HOST:-}" ] || { echo "FATAL: TW2_PUBLIC_HOST is unset -> pages would bake the tw2-dev fallback. Refusing."; exit 2; }
[ -x "$PY" ] || { echo "FATAL: $PY missing"; exit 2; }

echo "== regen_site on $(hostname) | TW2_PUBLIC_HOST=$TW2_PUBLIC_HOST =="
fails=0
run() {  # run <label> <workdir> <cmd...>
  local label="$1" dir="$2"; shift 2
  if ( cd "$dir" && "$@" ) >"/tmp/regen_$label.log" 2>&1; then
    echo "  OK    $label"
  else
    echo "  FAIL  $label  (tail /tmp/regen_$label.log)"; fails=$((fails+1))
  fi
}

# Order: cheap authored pages first, data-dependent ones after.
run textpages "$SITE"               "$PY" generate_text_pages.py
run about     "$SITE"               "$PY" generate_about_page.py
run research  "$SITE"               "$PY" generate_research_page.py
run insights  "$SITE"               "$PY" generate_insights.py
run learn     "$SITE"               "$PY" generate_learn.py
run ticker    "$SITE/ticker_pages"  "$PY" generate_ticker_pages.py
run scorecard "$SITE"               "$PY" generate_scorecard.py     # needs appserver
run dailypick "$SITE"               "$PY" generate_daily_ai_pick.py # needs appserver
run home      "$SITE"               "$PY" generate_home_page.py     # needs appserver + live Stripe (refuses on bad price = intended)

# Market/index pages are SMN-COUPLED: generate_security_pages.py imports
# generate_tw_security_pages, which lives in the SMN tree (/home/flask/smn). On a box
# without SMN it cannot run - the market pages are produced by the SMN pipeline where
# SMN lives and rsync'd into /var/www/tradewave/markets|_static/markets. Skip cleanly here.
if [ -d /home/flask/smn ] && [ -f /home/flask/smn/generate_tw_security_pages.py ]; then
  run markets "$SITE" "$PY" generate_security_pages.py
else
  echo "  SKIP  markets - SMN tree (/home/flask/smn) not on this box."
  echo "        Market pages come from the SMN content pipeline + rsync, not from a bare web box."
fi

echo "== regen_site done: $fails generator failure(s) =="
exit "$fails"
