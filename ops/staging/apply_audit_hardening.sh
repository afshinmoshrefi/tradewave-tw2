#!/usr/bin/env bash
# Apply the 2026-05-15 audit HIGH hardening to live boxes:
#   - new CSP allow-list (Cloudflare Insights + Mailerlite)
#   - systemd unit hardening (NoNewPrivileges, ProtectSystem=strict,
#     PrivateTmp, ProtectKernel*, RestrictSUIDSGID, LockPersonality)
#
# Run on .176 as root. Idempotent.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

# Per-env coordinates (staging by default; run.sh sets TGT_ENV_FILE for prod).
. "${TGT_ENV_FILE:-$(dirname "${BASH_SOURCE[0]}")/target.env}"

NEW_CSP='add_header Content-Security-Policy "default-src '"'"'self'"'"'; script-src '"'"'self'"'"' '"'"'unsafe-inline'"'"' https://www.googletagmanager.com https://js.stripe.com https://static.cloudflareinsights.com https://assets.mailerlite.com https://accounts.google.com; style-src '"'"'self'"'"' '"'"'unsafe-inline'"'"' https://assets.mailerlite.com; img-src '"'"'self'"'"' data: blob: https:; font-src '"'"'self'"'"' data: https:; connect-src '"'"'self'"'"' https://*.google-analytics.com https://*.analytics.google.com https://www.googletagmanager.com https://api.stripe.com https://api.workos.com https://*.authkit.app https://cloudflareinsights.com https://static.cloudflareinsights.com https://assets.mailerlite.com https://accounts.google.com https://www.googleapis.com; frame-src '"'"'self'"'"' https://js.stripe.com https://checkout.stripe.com https://*.authkit.app https://accounts.google.com; frame-ancestors '"'"'self'"'"'; base-uri '"'"'self'"'"'; form-action '"'"'self'"'"' https://checkout.stripe.com https://api.workos.com https://*.authkit.app https://assets.mailerlite.com; object-src '"'"'none'"'"'; upgrade-insecure-requests" always;'

apply_csp_locally() {
    local target=/etc/nginx/snippets/security_headers.conf
    if [[ -f "$target" ]]; then
        # Replace the existing CSP line, in place.
        python3 -c "
import re,sys
p='$target'
s=open(p).read()
s2=re.sub(r'add_header Content-Security-Policy .*always;', '''$NEW_CSP''', s, count=1)
open(p,'w').write(s2)
" && echo "  CSP updated at $target"
    fi
}

apply_appserver_hardening() {
    local unit=/etc/systemd/system/tradewave-appserver.service
    if [[ -f "$unit" ]] && ! grep -q "^NoNewPrivileges" "$unit"; then
        # Insert hardening block after [Service]
        python3 -c "
p='$unit'
s=open(p).read()
block='''
NoNewPrivileges=true
ProtectSystem=full
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
'''
import re
s2=re.sub(r'(\[Service\]\n)', r'\\1'+block, s, count=1)
open(p,'w').write(s2)
" && echo "  appserver unit hardened"
    fi
}

apply_web_hardening() {
    local unit=/etc/systemd/system/tradewave-web.service
    if [[ -f "$unit" ]] && ! grep -q "^NoNewPrivileges" "$unit"; then
        python3 -c "
p='$unit'
s=open(p).read()
block='''
NoNewPrivileges=true
ProtectSystem=full
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
'''
import re
s2=re.sub(r'(\[Service\]\n)', r'\\1'+block, s, count=1)
open(p,'w').write(s2)
" && echo "  web unit hardened"
    fi
}

remote_apply() {
    local host=$1
    local role=$2   # 'app' or 'web'
    hdr "remote $host ($role)"
    ssh -p "$TGT_SSH_PORT" "root@$host" "$(declare -f apply_csp_locally apply_appserver_hardening apply_web_hardening); \
        NEW_CSP=\"$NEW_CSP\"; \
        apply_csp_locally; \
        if [[ '$role' == app ]]; then apply_appserver_hardening; systemctl daemon-reload; systemctl restart tradewave-appserver; fi; \
        if [[ '$role' == web ]]; then apply_web_hardening; systemctl daemon-reload; systemctl restart tradewave-web; nginx -t && systemctl reload nginx; fi"
}

hdr "1. local (.176 dev)"
apply_csp_locally
apply_appserver_hardening
apply_web_hardening
systemctl daemon-reload
systemctl restart tradewave-appserver tradewave-web
nginx -t && systemctl reload nginx
echo "  .176 done"

remote_apply "$TGT_WEB_PUB" web
remote_apply "$TGT_APP_PUB" app

echo
echo "=== audit hardening applied to dev + staging ==="
