#!/usr/bin/env bash
# migrate.sh — apply DB migrations to this box's Postgres (alembic upgrade head).
#
# Run as the flask user (deploy.sh does: `sudo -u flask bash ops/migrate.sh`).
# Sources /etc/tradewave/secrets.env for POSTGRES_DSN (the migrations/env.py reads
# it from the process env). Idempotent — only unapplied revisions run — and
# fail-closed (set -e): a migration failure aborts the deploy BEFORE the web tier
# restarts, so the app never starts against a schema it doesn't expect (a missing
# affiliate column would otherwise 500 every referred checkout + admin view).
set -euo pipefail

# Run from the repo root: alembic (1.18+) probes for ./pyproject.toml in the CWD,
# and when invoked over SSH the CWD is /root (not readable by the flask user) ->
# PermissionError. cd to a flask-readable dir we control before running alembic.
cd /home/flask

if [ ! -r /etc/tradewave/secrets.env ]; then
  echo "migrate.sh: cannot read /etc/tradewave/secrets.env (need POSTGRES_DSN)" >&2
  exit 1
fi
set -a
. /etc/tradewave/secrets.env
set +a

echo "migrate.sh: alembic upgrade head ..."
exec /home/flask/venv/bin/alembic -c /home/flask/web/alembic.ini upgrade head
