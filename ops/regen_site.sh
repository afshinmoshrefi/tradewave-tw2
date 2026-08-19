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
FAVICON_HELPER=/home/flask/ops/lib/tradewave_favicon.sh

# --- env: bake with the correct public host or refuse -------------------------
[ -r "$SECRETS" ] || { echo "FATAL: $SECRETS not readable"; exit 2; }
set -a; . "$SECRETS"; set +a
[ -n "${TW2_PUBLIC_HOST:-}" ] || { echo "FATAL: TW2_PUBLIC_HOST is unset -> pages would bake the tw2-dev fallback. Refusing."; exit 2; }
[ -n "${TW2_ENV:-}" ] || { echo "FATAL: TW2_ENV is unset -> environment favicon cannot be selected. Refusing."; exit 2; }
[ -x "$PY" ] || { echo "FATAL: $PY missing"; exit 2; }
[ -r "$FAVICON_HELPER" ] || { echo "FATAL: $FAVICON_HELPER missing"; exit 2; }

# /favicon.png is shared by the static site and the React shell. Publish the
# environment marker independently of the env-agnostic React bundle:
# dev = white, staging = black, prod = brand colour.
. "$FAVICON_HELPER"
tw_publish_environment_favicon "$TW2_ENV" "$SITE/static" "/var/www/tradewave/favicon.png" || exit 2

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

# Full DATA-compute-then-RENDER sequence. Order matters where a render reads data that an
# earlier step writes (verified against the code + the flask crontab):
#  - insights_charts emits the embedded /insights/charts/*.svg assets BEFORE insights renders them.
#  - home_opportunities (DATA) refreshes data/home_opportunities.csv BEFORE the home render reads it
#    (else the home "Top Patterns" bar shows a stale CSV, and its <3-fresh-row guard can blank it).
#  - home is the SOLE writer of the new featured-pick row in data/featured_history.json, so it MUST
#    run BEFORE scorecard, which reads that row then recomputes outcomes live and saves them back.
#    (Running scorecard before home renders it against the PREVIOUS pick - the bug this order fixes.)
# Cheap authored pages first; appserver/Stripe/ML-scorer-dependent ones after (appserver is
# restarted by deploy.sh before regen). Each step is fail-soft (run() logs + counts, never aborts).
run insightschart "$SITE"           "$PY" generate_insights_charts.py  # embedded insights SVG/PNG assets (before insights)
run textpages "$SITE"               "$PY" generate_text_pages.py
run about     "$SITE"               "$PY" generate_about_page.py
run research  "$SITE"               "$PY" generate_research_page.py
run 100yp     "$SITE"               "$PY" generate_100_year_pattern.py
run webinars  "$SITE"               "$PY" generate_webinar_page.py
run insights  "$SITE"               "$PY" generate_insights.py
run learn     "$SITE"               "$PY" generate_learn.py
run ticker    "$SITE/ticker_pages"  "$PY" generate_ticker_pages.py     # appserver; also emits the OG share images
run home_opp  "$SITE"               "$PY" home_opportunities.py         # DATA: refresh Top Patterns CSV (appserver; fail-closed, atomic os.replace)
run home      "$SITE"               "$PY" generate_home_page.py         # appserver + ML scorer + live Stripe; SOLE writer of the new featured-pick row
run scorecard "$SITE"               "$PY" generate_scorecard.py         # appserver; reads the fresh pick row + recomputes outcomes live (MUST be after home)
run dailypick "$SITE"               "$PY" generate_daily_ai_pick.py     # appserver; self-contained (no on-disk store)

# Market/index pages are SMN-COUPLED: generate_security_pages.py imports
# generate_tw_security_pages, which lives in the SMN tree (/home/flask/smn). On a box
# without SMN it cannot run - the market pages are produced by the SMN pipeline where
# SMN lives and rsync'd into /var/www/tradewave/markets|_static/markets. Skip cleanly here.
if [ -d /home/flask/smn ] && [ -f /home/flask/smn/generate_tw_security_pages.py ]; then
  run markets "$SITE" "$PY" generate_security_pages.py
else
  echo "  SKIP  markets - SMN tree (/home/flask/smn) not on this box."
  echo "        Market pages come from the SMN content pipeline + rsync, not from a bare web box."
  # Those rsynced copies were BUILT on the SMN/dev box and can carry ITS absolute
  # hosts (staging 2026-07-04: 6x tw2-dev links per page -> host-leak FAILs).
  # Rebase any known lower-env host in them to THIS box's public hosts. Idempotent;
  # no-ops when the pages are already clean (e.g. prod's current copies).
  if ls /var/www/tradewave/markets/*.html >/dev/null 2>&1; then
    NEWS_HOST=$(echo "${TW2_NEWS_WEBSITE_URL:-}" | sed -E 's|https?://||; s|/$||')
    # tw2-prod.trxstat.com = the box's pre-cutover placeholder (prod's copies were
    # baked with it); tw2.trxstat.com = the even older dev placeholder.
    sed -i "s|tw2-dev\.trxstat\.com|$TW2_PUBLIC_HOST|g; s|tw2-stage\.trxstat\.com|$TW2_PUBLIC_HOST|g; s|tw2-prod\.trxstat\.com|$TW2_PUBLIC_HOST|g; s|tw2\.trxstat\.com|$TW2_PUBLIC_HOST|g; s|http://192\.168\.1\.176|https://$TW2_PUBLIC_HOST|g; s|192\.168\.1\.176|$TW2_PUBLIC_HOST|g" /var/www/tradewave/markets/*.html
    [ -n "$NEWS_HOST" ] && sed -i "s|smn-dev\.trxstat\.com|$NEWS_HOST|g; s|smn-stage\.trxstat\.com|$NEWS_HOST|g" /var/www/tradewave/markets/*.html
    echo "  OK    markets-rebase - absolute hosts rebased to $TW2_PUBLIC_HOST"
  fi
fi

# Re-inject live prices into the just-built home.html + markets/*.html price spans and write
# assets/quotes.json + market-quotes.js (the single source the client JS polls). Must run after
# home + markets are (re)built; no-ops on any file not present, so it is safe on a bare box.
run quotes    "$SITE"               "$PY" refresh_market_quotes.py

# LAST: rebuild robots.txt / sitemap.xml / llms.txt from what's on disk RIGHT NOW.
# Must be the final step - sitemap.xml scans the pages every generator above just
# wrote, so running this any earlier would ship a stale/incomplete sitemap.
run seo       "$SITE"               "$PY" generate_seo_files.py

echo "== regen_site done: $fails generator failure(s) =="
exit "$fails"
