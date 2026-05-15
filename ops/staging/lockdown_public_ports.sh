#!/usr/bin/env bash
# Close public 80/443 on the staging boxes.
# Cloudflared tunnels carry traffic OUTBOUND from each box to Cloudflare;
# no inbound 80/443 is needed for the public hostnames to work. Leaving
# those ports open lets bare-IP scanners reach the boxes directly,
# bypassing Cloudflare's WAF/rate-limits/bot-detection.
#
# Keeps open: 4369 ssh (everywhere). Cross-tier VLAN allows already in place.
# Run on .176 as root.

set -euo pipefail
hdr() { printf '\n=== %s ===\n' "$*"; }

for entry in 199.244.48.157 185.53.209.8; do
    hdr "lockdown $entry"
    ssh -p 4369 "root@${entry}" '
        set -e
        # Delete every existing 80/443 ALLOW rule (idempotent re-runs OK).
        while ufw status numbered | grep -E "ALLOW IN.*\b(80|443)/tcp" >/dev/null; do
            rule=$(ufw status numbered | grep -E "ALLOW IN.*\b(80|443)/tcp" | head -1 | sed "s/].*//;s/\[ *//")
            ufw --force delete "$rule"
        done
        ufw status numbered
    '
done

echo
echo "=== public 80/443 closed on both staging boxes ==="
echo "Verify externally:  nc -z -w3 185.53.209.8 443    # should fail/timeout now"
echo "stage2.trxstat.com and tw2-stage-app.trxstat.com still reachable via cloudflared tunnels."
