#!/usr/bin/env bash
# migrate.sh — bring this box's Postgres to the schema the code expects.
#
#   1. alembic upgrade head            — versioned migrations (web/models.py).
#   2. apiserver/schema.sql            — ADDITIVE (CREATE TABLE/COLUMN IF NOT EXISTS):
#      api_keys, api_usage_daily, and users.api_tier. The WEB tier's User model
#      references users.api_tier, so this must run even when the API/MCP product is
#      "dark" (no services/routes) — otherwise every User query (login, checkout,
#      /healthz) 500s. Idempotent; touches no existing data.
#
# Run as the flask user (deploy.sh: `sudo -u flask bash ops/migrate.sh`). Fail-closed
# (set -e): a failure aborts the deploy BEFORE the web tier restarts, so the app
# never starts against a schema it doesn't expect. cd to the repo root first:
# alembic 1.18 probes ./pyproject.toml in the CWD, which over SSH is /root (not
# readable by flask) -> PermissionError.
set -euo pipefail
cd /home/flask

if [ ! -r /etc/tradewave/secrets.env ]; then
  echo "migrate.sh: cannot read /etc/tradewave/secrets.env (need POSTGRES_DSN)" >&2
  exit 1
fi
set -a
. /etc/tradewave/secrets.env
set +a

echo "migrate.sh: alembic upgrade head ..."
/home/flask/venv/bin/alembic -c /home/flask/web/alembic.ini upgrade head

echo "migrate.sh: applying additive apiserver/schema.sql (users.api_tier + api tables) ..."
/home/flask/venv/bin/python - <<'PY'
import sys
sys.path.insert(0, "/home/flask")
import config
from sqlalchemy import create_engine
sql = open("/home/flask/apiserver/schema.sql").read()
eng = create_engine(config.POSTGRES_DSN)
with eng.begin() as c:
    c.exec_driver_sql(sql)
eng.dispose()
print("apiserver/schema.sql applied")
PY

echo "migrate.sh: done"
