#!/usr/bin/env bash
# Wipe /root/.cloudflared/cert.pem from staging boxes after tunnels are created.
#
# Why: cert.pem is Cloudflare account-wide auth (tunnel-create + DNS-route
# control over EVERY zone). The per-tunnel <UUID>.json credentials file is
# enough for `cloudflared tunnel run` — the cert is only needed to CREATE
# or ROUTE tunnels. Leaving it on the runtime box means a compromise of
# stage-app or stage-web grants control over every Cloudflare zone in
# afshin's account, not just trxstat.com.
#
# Re-run after any future `cloudflared tunnel create` / `route dns`.
# The tunnel daemon keeps running fine without cert.pem.
#
# Run on .176 as root.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

for entry in 199.244.48.157 185.53.209.8; do
    hdr "wipe cert.pem on $entry"
    ssh -p 4369 "root@${entry}" '
        if [[ -f /root/.cloudflared/cert.pem ]]; then
            shred -u /root/.cloudflared/cert.pem
            echo "wiped"
        else
            echo "already gone"
        fi
        echo "remaining:"; ls -la /root/.cloudflared/ 2>/dev/null
        echo "cloudflared service:"; systemctl is-active cloudflared
    '
done

echo
echo "=== cert.pem wiped from both staging boxes ==="
echo "Tunnels keep running. To re-create or re-route a tunnel later,"
echo "re-scp cert.pem temporarily, do the work, then re-run this script."
