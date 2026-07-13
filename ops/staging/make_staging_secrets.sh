#!/usr/bin/env bash
# Build /tmp/staging_secrets.env from /etc/tradewave/secrets.env on this dev box.
# Run as root on .176. Output is mode 600 root:root, then scp to staging-app.
#
# What this does:
#   - Copies all "shared" 3rd-party keys verbatim from dev (EOD_TOKEN,
#     MAILERLITE_*, ANTHROPIC_TOKEN, FACEBOOK_*, PUBLER_*, etc.).
#   - Regenerates per-pair secrets so dev tokens can't auth on staging:
#       APPSERVER_JWT_SECRET, SERVICE_API_KEY, WORKOS_COOKIE_PASSWORD,
#       and a fresh POSTGRES_PASSWORD for the tradewave role.
#   - Overrides env-specific URL/IP vars per target (target.env / prod_target.env):
#       TW2_DOMAIN_ROOT      = https://$TGT_WEB_HOST
#       TW2_APPSERVER_URL    = https://$TGT_APP_HOST
#       TW2_APPSERVER_IP     = $TGT_APP_VLAN
#       TW2_WEBSERVER_IP     = $TGT_WEB_VLAN
#       TW2_PUBLIC_HOST      = $TGT_WEB_HOST
#       POSTGRES_DSN         = postgresql://tradewave:<pw>@127.0.0.1:5432/tradewave   (used by app box)
#   - Leaves placeholders for what needs configuring in 3rd-party dashboards:
#       STRIPE_WEBHOOK_SECRET   (create a new endpoint in Stripe dashboard for
#                                https://$TGT_APP_HOST/api/stripe/webhook,
#                                paste its signing secret here)
#       SMN_EMAIL_GROUP_ID      (Mailerlite group for SMN subscribers)
#       DAILY_AI_PICK_GROUP_ID  (optional; falls back to SMN group)
#
# After this script:
#   1. Review /tmp/staging_secrets.env once
#   2. scp -P $TGT_SSH_PORT /tmp/staging_secrets.env root@$TGT_APP_PUB:/etc/tradewave/secrets.env
#   3. ssh root@$TGT_APP_PUB -p $TGT_SSH_PORT 'chown root:flask /etc/tradewave/secrets.env && chmod 640 /etc/tradewave/secrets.env'
#   4. Save the printed POSTGRES password somewhere — bootstrap_stage_app_db.sh will use it.

set -euo pipefail

# Per-env target coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

case "${TGT_WEB_HOST}" in
    tw2-stage.trxstat.com) TARGET_TW2_ENV=staging ;;
    tw2-prod.trxstat.com|tradewave.ai) TARGET_TW2_ENV=prod ;;
    *)
        echo "Unsupported TGT_WEB_HOST for TW2_ENV: ${TGT_WEB_HOST}" >&2
        exit 1
        ;;
esac

SRC=/etc/tradewave/secrets.env
DST=/tmp/staging_secrets.env

if [[ "$EUID" -ne 0 ]]; then
    echo "Run as root (needs to read $SRC)." >&2
    exit 1
fi
[[ -r "$SRC" ]] || { echo "Cannot read $SRC" >&2; exit 1; }

# Wipe the output file on ANY exit path (success, error, ^C, SIGTERM, SIGHUP).
# The output file contains every secret the staging env needs — if scp races
# with a crash, we don't want it lingering on .176 disk.
on_exit() {
    [[ -f "$DST" ]] && shred -u "$DST" 2>/dev/null || true
}
trap on_exit INT TERM HUP   # NOT EXIT — normal exit keeps the file for scp

# Helper: get a value from the dev file by key name. Empty if absent.
get_dev() {
    grep -E "^${1}=" "$SRC" | head -1 | sed -E "s/^${1}=//"
}

# Helper: 32 bytes hex.
randhex32() { openssl rand -hex 32; }
# Fernet key: 32 url-safe base64-encoded bytes. WorkOS SDK seal_data() calls
# Fernet(cookie_password) which REJECTS anything else with ValueError.
fernet_key() { python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"; }

# Fresh per-pair secrets for staging.
STAGE_JWT=$(randhex32)
STAGE_SERVICE_API=$(randhex32)
STAGE_WORKOS_COOKIE=$(fernet_key)
STAGE_PG_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-32)

umask 077
{
cat <<EOF
# /etc/tradewave/secrets.env  -  TW2 target: ${TGT_WEB_HOST}
# Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) on $(hostname) by make_staging_secrets.sh
# Mode: 640 root:flask on each box. See bootstrap_stage_app.sh.

# === Per-env public URLs ===
TW2_DOMAIN_ROOT=https://${TGT_WEB_HOST}
TW2_APPSERVER_URL=https://${TGT_APP_HOST}
TW2_PUBLIC_HOST=${TGT_WEB_HOST}
TW2_ENV=${TARGET_TW2_ENV}

# === Per-env VLAN IPs (cross-tier traffic rides 10.0.0.0/24) ===
TW2_APPSERVER_IP=${TGT_APP_VLAN}
TW2_WEBSERVER_IP=${TGT_WEB_VLAN}

# === Per-env datastores ===
# Postgres lives on the app box. Web reaches it via VLAN (${TGT_APP_VLAN}:5432).
# When this file is dropped on the WEB box, change 127.0.0.1 to ${TGT_APP_VLAN}.
POSTGRES_DSN=postgresql://tradewave:${STAGE_PG_PASSWORD}@127.0.0.1:5432/tradewave

# === Pair-specific secrets (regenerated; do NOT reuse dev's) ===
APPSERVER_JWT_SECRET=${STAGE_JWT}
SERVICE_API_KEY=${STAGE_SERVICE_API}
WORKOS_COOKIE_PASSWORD=${STAGE_WORKOS_COOKIE}

# === Shared 3rd-party keys (copied verbatim from dev) ===
ANTHROPIC_TOKEN=$(get_dev ANTHROPIC_TOKEN)
EOD_TOKEN=$(get_dev EOD_TOKEN)
FACEBOOK_ACCESS_TOKEN=$(get_dev FACEBOOK_ACCESS_TOKEN)
FACEBOOK_APP_ID=$(get_dev FACEBOOK_APP_ID)
FACEBOOK_APP_SECRET=$(get_dev FACEBOOK_APP_SECRET)
FACEBOOK_OPP_PAGES_JSON=$(get_dev FACEBOOK_OPP_PAGES_JSON)
FACEBOOK_PAGE_ID=$(get_dev FACEBOOK_PAGE_ID)
GROK_API_KEY=$(get_dev GROK_API_KEY)
INDEXNOW_KEY=$(get_dev INDEXNOW_KEY)
MAILERLITE_API_KEY=$(get_dev MAILERLITE_API_KEY)
MAILERLITE_GROUP_ID=$(get_dev MAILERLITE_GROUP_ID)
MAILERLITE_TOKEN=$(get_dev MAILERLITE_TOKEN)
# App-originated MailerLite subscriber writes are always off on staging. The
# account is shared, so production lifecycle group IDs are never copied here.
MAILERLITE_OUTBOUND_ENABLED=0
MAILERLITE_TRIAL_STARTED_GROUP_ID=
MAILERLITE_TRIAL_ENDED_EXPLORER_GROUP_ID=
MAILERLITE_WINBACK_GROUP_ID=
MAILERLITE_WEBHOOK_SECRET=PLACEHOLDER_GENERATE_UNIQUE_STAGING_SECRET
OPENAI_KEY=$(get_dev OPENAI_KEY)
PERPLEXITY_API_KEY=$(get_dev PERPLEXITY_API_KEY)
PUBLER_API_KEY=$(get_dev PUBLER_API_KEY)
PUBLER_WORKSPACE_ID=$(get_dev PUBLER_WORKSPACE_ID)
PUBLER_X_ACCOUNT_ID=$(get_dev PUBLER_X_ACCOUNT_ID)
REPLICATE_API_TOKEN=$(get_dev REPLICATE_API_TOKEN)
TAVILY_API_KEY=$(get_dev TAVILY_API_KEY)
SENTRY_DSN=$(get_dev SENTRY_DSN)

# === WorkOS (shared test env across dev+staging) ===
# REMINDER: add https://${TGT_WEB_HOST}/auth/callback to the WorkOS
# AuthKit redirect URIs in the WorkOS dashboard (Dev → Redirects).
WORKOS_API_KEY=$(get_dev WORKOS_API_KEY)
WORKOS_AUTHKIT_DOMAIN=$(get_dev WORKOS_AUTHKIT_DOMAIN)
WORKOS_CLIENT_ID=$(get_dev WORKOS_CLIENT_ID)

# === Stripe (test mode shared with dev) ===
# REMINDER: in Stripe dashboard → Developers → Webhooks, add a new endpoint
# https://${TGT_APP_HOST}/api/stripe/webhook (or /stripe/webhook),
# subscribe to checkout.session.completed + customer.subscription.* events,
# then paste its signing secret in STRIPE_WEBHOOK_SECRET below.
STRIPE_PUBLISHABLE_KEY=$(get_dev STRIPE_PUBLISHABLE_KEY)
STRIPE_SECRET_KEY=$(get_dev STRIPE_SECRET_KEY)
STRIPE_WEBHOOK_SECRET=PLACEHOLDER_SET_AFTER_CREATING_STAGING_WEBHOOK

# === Central services (TW1 prod data tier, consumed by dev + staging) ===
TW2_BLOG_QUEUE_SERVER=$(get_dev TW2_BLOG_QUEUE_SERVER)
TW2_EDGAR_SERVICE_URL=$(get_dev TW2_EDGAR_SERVICE_URL)
TW2_KEYSTORE_URL=$(get_dev TW2_KEYSTORE_URL)
TW2_LOGCOLLECTOR_URL=$(get_dev TW2_LOGCOLLECTOR_URL)
TW2_MASTER_APPSERVER=$(get_dev TW2_MASTER_APPSERVER)
TW2_ML_SCORER_URL=$(get_dev TW2_ML_SCORER_URL)
TW2_NEWS_WEBSITE_URL=$(get_dev TW2_NEWS_WEBSITE_URL)
TW2_REALTIME_SERVICE_URL=$(get_dev TW2_REALTIME_SERVICE_URL)
TW2_STOCKSCORE_URL=$(get_dev TW2_STOCKSCORE_URL)
TW2_UPDATE_SERVER=$(get_dev TW2_UPDATE_SERVER)

# === Favicons (per-env black/colour split) ===
TW2_ARTICLE_FAVICON_URL=$(get_dev TW2_ARTICLE_FAVICON_URL)
TW2_SMN_FAVICON_URL=$(get_dev TW2_SMN_FAVICON_URL)
TW2_X_PROFILE_URL=$(get_dev TW2_X_PROFILE_URL)

# === WordPress (TW2 has no WP; carry whatever dev had — likely empty) ===
TW2_WORDPRESS_URL=$(get_dev TW2_WORDPRESS_URL)
TW2_WORDPRESS_USERNAME=$(get_dev TW2_WORDPRESS_USERNAME)
WORDPRESS_APP_PASSWORD=$(get_dev WORDPRESS_APP_PASSWORD)

# === New for staging (from the May-14 cron-port work) ===
# Set these to the Mailerlite group IDs for staging-test recipients.
# Until they're set, send_smn_emails.py and send_daily_ai_pick.py will
# fail-loud rather than send to the wrong list.
SMN_EMAIL_GROUP_ID=PLACEHOLDER_SET_MAILERLITE_SMN_GROUP_ID
DAILY_AI_PICK_GROUP_ID=PLACEHOLDER_SET_OR_LEAVE_BLANK_TO_FALL_BACK_TO_SMN
EOF
} > "$DST"

chmod 600 "$DST"

# Safety: this copied WorkOS + Stripe keys from THIS dev box (test mode / shared
# "Staging" WorkOS env). Production must use its OWN WorkOS production env + LIVE
# Stripe keys - warn loudly if the target looks like prod.
case "${TGT_WEB_HOST}" in
  *prod*|tradewave.ai)
    echo "!!! WARNING: WORKOS_* and STRIPE_* were copied from dev (test mode). PROD needs" >&2
    echo "    its own production WorkOS env + LIVE Stripe keys - replace them before serving." >&2
    ;;
esac

echo "Wrote $DST ($(wc -l < "$DST") lines, mode 600)"
echo
echo "POSTGRES password is embedded in POSTGRES_DSN in $DST."
echo "bootstrap_stage_app_db.sh reads it from /etc/tradewave/secrets.env after you scp."
echo "If you need it on .176 for a manual check:  grep POSTGRES_DSN $DST | cut -d: -f3 | cut -d@ -f1"
echo
echo "Next:"
echo "  1. Inspect /tmp/staging_secrets.env (less /tmp/staging_secrets.env)"
echo "  2. scp -P ${TGT_SSH_PORT} /tmp/staging_secrets.env root@${TGT_APP_PUB}:/etc/tradewave/secrets.env"
echo "  3. ssh root@${TGT_APP_PUB} -p ${TGT_SSH_PORT} 'chown root:flask /etc/tradewave/secrets.env && chmod 640 /etc/tradewave/secrets.env'"
echo "  4. (Optional but recommended) shred -u /tmp/staging_secrets.env after scp"
