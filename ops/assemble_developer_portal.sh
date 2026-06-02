#!/usr/bin/env bash
# assemble_developer_portal.sh - (re)build the public developer-portal docroot.
#
# Generates the marketing pages, the API/MCP docs + downloadable artifacts, the
# learning track, and the interactive playground, then publishes them into the
# nginx docroot that 'developers.*' serves:
#
#   /var/www/developers/                  <- site/api_marketing/out/
#     index.html pricing.html mcp.html use-cases.html
#   /var/www/developers/.well-known/mcp.json   (also kept at /docs/.well-known/)
#   /var/www/developers/docs/             <- site/api_docs/ (HTML + openapi + postman)
#   /var/www/developers/learn/            <- site/api_learn/out/
#   /var/www/developers/playground/       <- site/api_playground/out/
#
# This is a WEB-BOX script: the operator runs it ON the target box (dev / staging /
# prod). It does NOT ssh anywhere and it does NOT restart any service. It is
# idempotent - run it any time the generators or their source content change.
#
# HOSTS: the generators read the public hostnames from site/lib/portal_urls.py,
# which falls back to /etc/tradewave/secrets.env, then to the DEV defaults
# (*-dev.trxstat.com). To build for staging/prod, export the right hosts FIRST
# (or have them in secrets.env), e.g. prod:
#   export TW2_PUBLIC_HOST=tradewave.ai \
#          TW2_DEVELOPERS_PUBLIC_HOST=developers.tradewave.ai \
#          TW2_API_PUBLIC_HOST=api.tradewave.ai \
#          TW2_MCP_PUBLIC_HOST=mcp.tradewave.ai
# With nothing exported it builds the DEV portal (developers-dev.trxstat.com).
#
# Usage:  bash ops/assemble_developer_portal.sh
#
# Brand rule: no em-dashes anywhere (use ' - ').
set -euo pipefail

REPO=/home/flask
PY="$REPO/venv/bin/python"
SITE="$REPO/site"
DOCROOT=/var/www/developers

hdr(){ printf '\n=== %s ===\n' "$*"; }

[[ -x "$PY" ]] || { echo "ERROR: python not found at $PY"; exit 1; }
[[ -d "$SITE" ]] || { echo "ERROR: site dir not found at $SITE"; exit 1; }

hdr "0/4  portal hosts (from env / secrets.env; dev defaults if unset)"
echo "  TW2_PUBLIC_HOST=${TW2_PUBLIC_HOST:-<unset -> dev default>}"
echo "  TW2_DEVELOPERS_PUBLIC_HOST=${TW2_DEVELOPERS_PUBLIC_HOST:-<unset -> dev default>}"
echo "  TW2_API_PUBLIC_HOST=${TW2_API_PUBLIC_HOST:-<unset -> dev default>}"
echo "  TW2_MCP_PUBLIC_HOST=${TW2_MCP_PUBLIC_HOST:-<unset -> dev default>}"
echo "  (export these before running to build staging/prod; portal_urls resolves the rest)"

hdr "1/4  run the 5 portal generators with $PY"
run_gen(){
  # run_gen <relative-script-path>
  local script="$SITE/$1"
  [[ -f "$script" ]] || { echo "ERROR: generator not found: $script"; exit 1; }
  echo "--- generating: $1 ---"
  ( cd "$REPO" && "$PY" "$script" )
}
run_gen api_marketing/generate.py
run_gen api_docs/generate_api_docs.py
run_gen api_docs/generate_api_extras.py
run_gen api_learn/generate_learn_api.py
run_gen api_playground/generate_playground.py
# SEO/discovery files (sitemap.xml, robots.txt, llms.txt, og-developers.png). MUST be last:
# it scans the page generators' output to build the sitemap. Writes into the marketing
# staging dir so it deploys to the portal root.
run_gen api_docs/generate_seo_files.py

hdr "2/4  publish into $DOCROOT (rsync -a --delete, only within the docroot subdirs)"
mkdir -p "$DOCROOT" "$DOCROOT/docs" "$DOCROOT/learn" "$DOCROOT/playground" "$DOCROOT/.well-known"

# Marketing pages -> docroot ROOT. No --delete here: the root also holds docs/,
# learn/, playground/, .well-known/ which are populated below, so a --delete on
# the root would wipe them. We sync the four marketing files explicitly instead.
echo "--- marketing -> $DOCROOT/ ---"
rsync -a "$SITE/api_marketing/out/" "$DOCROOT/"

# API docs -> docs/ . EXCLUDE the generators + caches so we never publish .py.
# --delete is scoped strictly to $DOCROOT/docs/.
echo "--- docs -> $DOCROOT/docs/ (excluding *.py, __pycache__) ---"
rsync -a --delete \
  --exclude='*.py' --exclude='__pycache__/' --exclude='__pycache__' \
  "$SITE/api_docs/" "$DOCROOT/docs/"

# Learning track -> learn/ . --delete scoped strictly to $DOCROOT/learn/.
echo "--- learn -> $DOCROOT/learn/ ---"
rsync -a --delete "$SITE/api_learn/out/" "$DOCROOT/learn/"

# Playground -> playground/ . --delete scoped strictly to $DOCROOT/playground/.
echo "--- playground -> $DOCROOT/playground/ ---"
rsync -a --delete "$SITE/api_playground/out/" "$DOCROOT/playground/"

# MCP discovery manifest: it ships under site/api_docs/.well-known/, so the
# docs/ rsync already lands it at $DOCROOT/docs/.well-known/mcp.json. Agents
# probe the docroot ROOT (developers.*/.well-known/mcp.json), so place it there
# too. --delete is scoped strictly to $DOCROOT/.well-known/.
echo "--- .well-known/mcp.json -> $DOCROOT/.well-known/ ---"
WK_SRC="$SITE/api_docs/.well-known/"
[[ -f "$WK_SRC/mcp.json" ]] || { echo "ERROR: missing $WK_SRC/mcp.json (run generate_api_extras.py)"; exit 1; }
rsync -a --delete "$WK_SRC" "$DOCROOT/.well-known/"

hdr "3/4  ownership: mirror /var/www/tradewave"
# Match how the existing static docroot is owned so nginx serves it identically.
if [[ -d /var/www/tradewave ]]; then
  OWNER="$(stat -c '%U:%G' /var/www/tradewave)"
else
  OWNER="flask:flask"
  echo "  /var/www/tradewave not found; defaulting owner to $OWNER"
fi
echo "  chown -R $OWNER $DOCROOT"
chown -R "$OWNER" "$DOCROOT"

hdr "4/4  smoke (local, via nginx on :80)"
echo '--- curl -sI http://127.0.0.1/ -H "Host: developers-dev.trxstat.com" ---'
echo '    (on staging/prod use the matching Host: developers-stage.trxstat.com / developers.tradewave.ai)'
curl -sI http://127.0.0.1/ -H 'Host: developers-dev.trxstat.com' || \
  echo "  (curl failed - nginx/tunnel may not be wired for this host yet; the docroot is still built)"

echo
echo "=== developer portal assembled at $DOCROOT ==="
echo "    root:       $(ls -1 "$DOCROOT"/*.html 2>/dev/null | xargs -r -n1 basename | tr '\n' ' ')"
echo "    docs:       $(ls -1 "$DOCROOT/docs"/*.html 2>/dev/null | wc -l) html + openapi/postman"
echo "    learn:      $(ls -1 "$DOCROOT/learn"/*.html 2>/dev/null | wc -l) html"
echo "    playground: $(ls -1 "$DOCROOT/playground"/*.html 2>/dev/null | wc -l) html"
echo "    mcp.json:   $DOCROOT/.well-known/mcp.json + $DOCROOT/docs/.well-known/mcp.json"
