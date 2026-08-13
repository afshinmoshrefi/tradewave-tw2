#!/usr/bin/env bash
# TW2 staging APP-box code+venv bootstrap.
# Run AFTER bootstrap_stage_app.sh and AFTER the deploy pubkey is on GitHub.
# Usage (env-driven runner prepends the target coordinates):
#   ops/staging/run.sh staging bootstrap_stage_app_code.sh app
# For prod: run via  ops/staging/run.sh prod bootstrap_stage_app_code.sh app
#
# What this does (one-time bootstrap; refuses an existing Git repository):
#   1. Verify SSH-to-github works with the deploy key
#   2. git init /home/flask, add origin, fetch+checkout main
#   3. Configure git (sshCommand using deploy key, user.name/email)
#   4. Create /home/flask/venv on python3.12
#   5. pip install -r requirements.txt
#   6. py_compile sanity check on the major .py files
#
# NOT in this script (intentionally next step):
#   - /etc/tradewave/secrets.env       (next: scp from dev with per-env overrides)
#   - postgres role password           (next: ALTER ROLE from secrets)
#   - alembic upgrade head             (next: needs secrets sourced)
#   - data subset                      (US-only: csv/US + dj30 + sp500 + nasdaq100)
#   - systemd units, nginx, cloudflared

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

REPO_SSH=git@github.com:afshinmoshrefi/tradewave-tw2.git
DEPLOY_KEY=/home/flask/.ssh/id_ed25519
GIT_SSH="ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

hdr "1. ssh-to-github check"
# ssh -T github.com always exits non-zero (GitHub closes channel after greeting).
# Capture output and grep for the auth-success marker independent of exit code.
sudo -u flask ssh -n -i "${DEPLOY_KEY}" -o StrictHostKeyChecking=accept-new -T git@github.com > /tmp/_gh_test 2>&1 || true
if ! grep -q "successfully authenticated" /tmp/_gh_test; then
    echo "FAILED to authenticate to github with deploy key. Output:"
    cat /tmp/_gh_test
    echo "Confirm the pubkey at /home/flask/.ssh/id_ed25519.pub is added as a deploy key on the repo."
    exit 1
fi
echo "GitHub auth OK ($(grep successfully /tmp/_gh_test))."

hdr "2. fresh git init + remote + fetch + detached checkout"
# /home/flask already has useradd skeleton (.bashrc, .profile, .ssh/). git
# leaves those alone; it only writes files that exist in the repo.
sudo -u flask bash -c "
    cd /home/flask
    if [ -d .git ]; then
        echo 'REFUSING: /home/flask already contains a Git repository.' >&2
        echo 'This bootstrap is for a new host only; use the release manager for updates.' >&2
        exit 2
    fi
    git init -q -b main
    git remote add origin '${REPO_SSH}'
    git config core.sshCommand '${GIT_SSH}'
    git config user.name 'Afshin Moshrefi'
    git config user.email 'afshinmoshrefi@hotmail.com'
    GIT_SSH_COMMAND='${GIT_SSH}' git fetch --tags origin
    git checkout --detach origin/main
"
echo "HEAD: $(sudo -u flask git -C /home/flask rev-parse --short HEAD) $(sudo -u flask git -C /home/flask log -1 --pretty=%s)"

hdr "3. venv (python3.12)"
if [ ! -x /home/flask/venv/bin/python ]; then
    sudo -u flask python3 -m venv /home/flask/venv
fi
sudo -u flask /home/flask/venv/bin/pip install --upgrade pip wheel setuptools >/dev/null
echo "python: $(sudo -u flask /home/flask/venv/bin/python --version)"

hdr "4. pip install -r requirements.txt"
# tables and numpy can need compile time; allow up to ~5min
sudo -u flask /home/flask/venv/bin/pip install -r /home/flask/requirements.txt 2>&1 | tail -20
echo "installed packages: $(sudo -u flask /home/flask/venv/bin/pip list 2>/dev/null | wc -l)"

hdr "5. py_compile sanity"
sudo -u flask /home/flask/venv/bin/python -m py_compile \
    /home/flask/web/app.py \
    /home/flask/appserver/appserver/appserver.py \
    /home/flask/config.py \
    /home/flask/site/generate_home_page.py
echo "py_compile: ok"

echo
echo "=== code bootstrap complete ==="
echo "HEAD: $(sudo -u flask git -C /home/flask rev-parse --short HEAD)"
echo "venv: $(sudo -u flask /home/flask/venv/bin/pip list 2>/dev/null | wc -l) packages installed"
echo "Next: secrets.env (transfer from dev), then alembic upgrade head, then services."
