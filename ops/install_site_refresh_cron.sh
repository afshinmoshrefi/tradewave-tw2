#!/usr/bin/env bash
# Install only the homepage, scorecard and static daily-pick refresh jobs.
set -euo pipefail
tw2_env=$(grep -m1 '^TW2_ENV=' /etc/tradewave/secrets.env | cut -d= -f2-)
case "$tw2_env" in
  dev) RELEASE_ROOT=/home/flask/.tw2-app-current ;;
  staging|prod) RELEASE_ROOT=/home/flask ;;
  *) echo 'FAIL: TW2_ENV must be dev, staging, or prod'; exit 1 ;;
esac
[ -r "$RELEASE_ROOT/ops/run_site_refresh.sh" ]
install -d -o flask -g flask -m 0750 /var/lib/tradewave/site /var/log/tradewave
for log in homepage scorecard daily_ai_pick_gen; do
  touch "/var/log/tradewave/$log.log"
  chown flask:flask "/var/log/tradewave/$log.log"
done
backup=$(mktemp /var/lib/tradewave/site/crontab.before.XXXXXXXX)
sudo -u flask crontab -l > "$backup" 2>/dev/null || true
{
  # Preserve unrelated jobs and comments. Also replace our own prior entries.
  awk '/^[[:space:]]*#/ || !/home_opportunities[.]py|generate_home_page[.]py|generate_scorecard[.]py|generate_daily_ai_pick[.]py|ops\/run_site_refresh[.]sh/' "$backup"
  echo "0 7 * * 1-5 bash $RELEASE_ROOT/ops/run_site_refresh.sh home >> /var/log/tradewave/homepage.log 2>&1"
  echo "*/10 * * * 1-5 bash $RELEASE_ROOT/ops/run_site_refresh.sh scorecard >> /var/log/tradewave/scorecard.log 2>&1"
  echo "0 6 * * 0-5 bash $RELEASE_ROOT/ops/run_site_refresh.sh daily-pick >> /var/log/tradewave/daily_ai_pick_gen.log 2>&1"
} | sudo -u flask crontab -
echo "OK: publication jobs use $RELEASE_ROOT; prior crontab saved at $backup"
