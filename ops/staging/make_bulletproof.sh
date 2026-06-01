#!/usr/bin/env bash
# Make TW2 staging bulletproof: backups (proven), logrotate, journald cap,
# full cron set. Idempotent — re-running converges, never duplicates.
# Run on .176 as root. THIS is the artifact prod cutover re-runs.
#
# app box ($TGT_APP_PUB): DB backups + restore drill + logrotate +
#   journald cap + health probes (it's the DB box).
# web box ($TGT_WEB_PUB): full content/email/quote cron set + system
#   health + logrotate + journald cap.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

APP="$TGT_APP_PUB"
WEB="$TGT_WEB_PUB"
S="-p $TGT_SSH_PORT"

LOGROTATE='/var/log/tradewave/*.log {
  daily
  rotate 14
  missingok
  notifempty
  compress
  delaycompress
  copytruncate
}'

JOURNALD_CAP='sed -i "s/^#\?SystemMaxUse=.*/SystemMaxUse=500M/" /etc/systemd/journald.conf && systemctl restart systemd-journald'

# ---------------------------------------------------------------- stage-app
hdr "STAGE-APP: logrotate + journald + DB backup/restore crons"
ssh $S "root@$APP" "bash -s" <<REMOTE
set -e
printf '%s\n' '$LOGROTATE' > /etc/logrotate.d/tradewave
logrotate -d /etc/logrotate.d/tradewave >/dev/null 2>&1 && echo "logrotate config valid"
$JOURNALD_CAP
echo "journald capped: \$(grep ^SystemMaxUse /etc/systemd/journald.conf)"

# backup_db/uptime/soak run fine as flask. restore_drill needs root
# (it does `sudo -u postgres psql` to drop/create a scratch DB — flask
# can't sudo). So restore_drill goes in ROOT's crontab, the rest in flask's.
CUR=\$(sudo -u flask crontab -l 2>/dev/null || true)
{
  printf '%s\n' "\$CUR"
  echo '30 3 * * * /home/flask/ops/backup_db.sh'
  echo '*/5 * * * * /home/flask/ops/uptime_check.sh'
  echo '*/30 * * * * /home/flask/ops/soak_monitor.sh'
} | grep -vE '^\$' | grep -v restore_drill | sort -u | sudo -u flask crontab -
RCUR=\$(crontab -l 2>/dev/null || true)
{ printf '%s\n' "\$RCUR"; echo '30 4 * * 0 /home/flask/ops/restore_drill.sh >> /var/log/tradewave/restore_drill.log 2>&1'; } | grep -vE '^\$' | sort -u | crontab -
echo "flask crontab:"; sudo -u flask crontab -l | grep -E 'backup_db|uptime|soak'
echo "root crontab:";  crontab -l | grep -E 'restore_drill'
REMOTE

hdr "STAGE-APP: PROVE backup + restore work now (not hoped)"
ssh $S "root@$APP" '
  sudo -u flask /home/flask/ops/backup_db.sh && echo "backup ran"
  ls -la /var/backups/tradewave/ | tail -3
  tail -1 /var/log/tradewave/backup.log
  echo "--- restore drill (as root: needs sudo -u postgres) ---"
  /home/flask/ops/restore_drill.sh 2>&1 | tail -5
'

# ---------------------------------------------------------------- stage-web
hdr "STAGE-WEB: logrotate + journald + full cron set"
ssh $S "root@$WEB" "bash -s" <<REMOTE
set -e
printf '%s\n' '$LOGROTATE' > /etc/logrotate.d/tradewave
logrotate -d /etc/logrotate.d/tradewave >/dev/null 2>&1 && echo "logrotate config valid"
$JOURNALD_CAP
echo "journald capped: \$(grep ^SystemMaxUse /etc/systemd/journald.conf)"

W='set -a; . /etc/tradewave/secrets.env; set +a;'
L='>> /var/log/tradewave'
CUR=\$(sudo -u flask crontab -l 2>/dev/null || true)
{
  printf '%s\n' "\$CUR"
  # system health
  echo "*/5 * * * * /home/flask/ops/uptime_check.sh"
  echo "*/30 * * * * /home/flask/ops/soak_monitor.sh"
  # trial expiry — revert lapsed admin-granted trials to explorer (skips Stripe subs)
  echo "15 4 * * * \$W /home/flask/venv/bin/python /home/flask/web/expire_trials.py \$L/expire_trials.log 2>&1"
  # SMN article pipeline
  echo "0 2 * * 1-5 \$W cd /home/flask/smn && /home/flask/venv/bin/python select_news_articles.py \$L/select_news.log 2>&1"
  echo "0 3 * * 1-5 \$W cd /home/flask/smn && /home/flask/venv/bin/python daily_article_queue.py \$L/daily_queue.log 2>&1"
  # security pages
  echo "30 5 * * 1-5 \$W /home/flask/venv/bin/python /home/flask/site/generate_security_pages.py \$L/security_pages.log 2>&1"
  echo "40 5 * * 1-5 \$W cd /home/flask/smn && /home/flask/venv/bin/python generate_tw_security_pages.py \$L/security_pages.log 2>&1"
  # homepage / scorecard / quotes
  echo "4 0 * * * \$W /home/flask/venv/bin/python /home/flask/site/home_opportunities.py \$L/home_opportunities.log 2>&1"
  echo "0 7 * * 1-5 \$W /home/flask/venv/bin/python /home/flask/site/generate_home_page.py \$L/home_page.log 2>&1"
  echo "*/10 9-16 * * 1-5 \$W /home/flask/venv/bin/python /home/flask/site/generate_scorecard.py \$L/scorecard.log 2>&1"
  echo "* * * * 0-5 \$W /home/flask/venv/bin/python /home/flask/smn/update_news_quotes.py \$L/smn_quote_injection.log 2>&1"
  # emails / social
  echo "30 7 * * 1-5 \$W /home/flask/venv/bin/python /home/flask/site/send_daily_ai_pick.py \$L/daily_ai_pick.log 2>&1"
  echo "0 7 * * 1-5 \$W /home/flask/venv/bin/python /home/flask/smn/send_smn_emails.py \$L/smn_email_cron.log 2>&1"
  echo "0 9 * * 0 \$W /home/flask/venv/bin/python /home/flask/smn/send_smn_emails.py \$L/smn_email_cron.log 2>&1"
  echo "0 6 * * 0-5 \$W /home/flask/venv/bin/python /home/flask/site/generate_daily_ai_pick.py \$L/daily_ai_pick_gen.log 2>&1"
  echo "10 6 * * 0-5 \$W /home/flask/venv/bin/python /home/flask/site/m_daily_ai_pick_social.py --send \$L/m_daily_ai_pick_social.log 2>&1"
} | grep -vE '^\$' | sort -u | sudo -u flask crontab -
echo "web crontab entry count: \$(sudo -u flask crontab -l | grep -vcE '^#|^\$')"
sudo -u flask crontab -l | grep -vE '^#|^\$' | sort
REMOTE

echo
echo "=== bulletproof pass complete ==="
echo "Backups: nightly 03:30 on stage-app, restore-verified weekly. Logs rotate"
echo "daily x14 + journald capped 500M on both boxes. Full cron set live on"
echo "stage-web. Re-run this script on prod-web/prod-app after the build scripts."
