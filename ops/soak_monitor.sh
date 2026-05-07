#!/usr/bin/env bash
# 24-hour soak monitoring — runs as cron, captures errors + uptime status
# Installed by S3 test agent on 2026-05-07
set +e
LOG=/var/log/tradewave/soak.log

# Pull POSTGRES_DSN from the systemd EnvironmentFile (flask is in the file's group).
if [ -r /etc/tradewave/secrets.env ]; then
    DSN=$(grep -E '^POSTGRES_DSN=' /etc/tradewave/secrets.env | head -1 | cut -d= -f2-)
else
    DSN=""
fi

{
  echo "=== $(date -u +%FT%TZ) ==="
  echo "Services:"
  systemctl is-active tradewave-web tradewave-appserver tradewave-blog-queue tradewave-article-processor nginx postgresql redis-server 2>&1
  echo "Web errors (last 30 min):"
  journalctl -u tradewave-web --since "30 min ago" --no-pager 2>&1 | grep -iE 'error|exception|traceback' | tail -5
  echo "Appserver errors (last 30 min):"
  journalctl -u tradewave-appserver --since "30 min ago" --no-pager 2>&1 | grep -iE 'error|exception|traceback' | tail -5
  echo "DB connections:"
  if [ -n "$DSN" ]; then
      psql "$DSN" -tAc "SELECT count(*) FROM pg_stat_activity WHERE datname='tradewave';" 2>&1
  else
      echo "DSN_NOT_AVAILABLE"
  fi
  echo "Disk:"
  df -h / | tail -1
  echo ""
} >> "$LOG"
