#!/usr/bin/env bash
# Render/install the API, MCP, and developer-portal nginx surface on the APP box.
set -euo pipefail

SECRETS=/etc/tradewave/secrets.env
TEMPLATE=/home/flask/ops/nginx/tradewave-developer-portal.conf
DEST=/etc/nginx/sites-available/tradewave-developer-portal

[ "$(id -u)" -eq 0 ] || { echo "FAIL: run as root" >&2; exit 1; }
[ -r "$SECRETS" ] || { echo "FAIL: $SECRETS is not readable" >&2; exit 1; }
[ -r "$TEMPLATE" ] || { echo "FAIL: $TEMPLATE is missing" >&2; exit 1; }
set -a
. "$SECRETS"
set +a

: "${TW2_ENV:?TW2_ENV must be set in $SECRETS}"
: "${TW2_API_PUBLIC_HOST:?TW2_API_PUBLIC_HOST must be set in $SECRETS}"
: "${TW2_MCP_PUBLIC_HOST:?TW2_MCP_PUBLIC_HOST must be set in $SECRETS}"
: "${TW2_DEVELOPERS_PUBLIC_HOST:?TW2_DEVELOPERS_PUBLIC_HOST must be set in $SECRETS}"
case "$TW2_ENV" in
  dev) default_port=80 ;;
  staging|prod) default_port=8080 ;;
  *) echo "FAIL: TW2_ENV must be dev, staging, or prod" >&2; exit 1 ;;
esac
PORT="${TW2_DEVELOPER_PORT:-$default_port}"
case "$PORT" in *[!0-9]*|'') echo "FAIL: invalid TW2_DEVELOPER_PORT" >&2; exit 1 ;; esac
for host in "$TW2_API_PUBLIC_HOST" "$TW2_MCP_PUBLIC_HOST" "$TW2_DEVELOPERS_PUBLIC_HOST"; do
  case "$host" in *[!A-Za-z0-9.-]*|'') echo "FAIL: invalid public hostname" >&2; exit 1 ;; esac
done

rendered="$(mktemp)"
backup="$(mktemp)"
support_backup="$(mktemp -d)"
trap 'rm -f "$rendered" "$backup"; rm -rf "$support_backup"' EXIT
sed \
  -e "s|__TW2_DEVELOPER_PORT__|$PORT|g" \
  -e "s|__TW2_API_PUBLIC_HOST__|$TW2_API_PUBLIC_HOST|g" \
  -e "s|__TW2_MCP_PUBLIC_HOST__|$TW2_MCP_PUBLIC_HOST|g" \
  -e "s|__TW2_DEVELOPERS_PUBLIC_HOST__|$TW2_DEVELOPERS_PUBLIC_HOST|g" \
  "$TEMPLATE" >"$rendered"
if grep -q '__TW2_' "$rendered"; then
  echo "FAIL: unresolved nginx template placeholder" >&2
  exit 1
fi

install -d -m 0755 /etc/nginx/conf.d /etc/nginx/snippets /etc/nginx/sites-available /etc/nginx/sites-enabled
support_paths=(
  /etc/nginx/conf.d/tradewave-log-format.conf
  /etc/nginx/snippets/security_headers.conf
  /etc/nginx/snippets/dotfile_deny.conf
  /etc/nginx/snippets/tw2-proxy-headers.conf
)
for path in "${support_paths[@]}"; do
  name="$(basename "$path")"
  if [ -f "$path" ]; then cp -p "$path" "$support_backup/$name"; else touch "$support_backup/.missing-$name"; fi
done
restore_support_files() {
  for path in "${support_paths[@]}"; do
    name="$(basename "$path")"
    if [ -f "$support_backup/.missing-$name" ]; then rm -f "$path"; else install -m 0644 "$support_backup/$name" "$path"; fi
  done
}
install -m 0644 /home/flask/ops/nginx/conf.d/tradewave-log-format.conf \
  /etc/nginx/conf.d/tradewave-log-format.conf
for snippet in security_headers.conf dotfile_deny.conf tw2-proxy-headers.conf; do
  install -m 0644 "/home/flask/ops/nginx/snippets/$snippet" "/etc/nginx/snippets/$snippet"
done

# The final two-box topology binds gunicorn appserver directly to APP :80. Its
# bootstrap-era nginx proxy vhost must not remain enabled when nginx is brought
# back for API/MCP/portal :8080, or nginx cannot bind and the public surface stays down.
if [ "$TW2_ENV" = staging ] && grep -q '^TW2_APPSERVER_BIND=.*:80$' /etc/tradewave/appserver.env 2>/dev/null; then
  rm -f /etc/nginx/sites-enabled/tw2-stage-app
elif [ "$TW2_ENV" = prod ] && grep -q '^TW2_APPSERVER_BIND=.*:80$' /etc/tradewave/appserver.env 2>/dev/null; then
  rm -f /etc/nginx/sites-enabled/tw2-prod-app
fi
had_dest=0
if [ -f "$DEST" ]; then cp -p "$DEST" "$backup"; had_dest=1; fi
install -m 0644 "$rendered" "$DEST"
ln -sfn "$DEST" /etc/nginx/sites-enabled/tradewave-developer-portal
if ! nginx -t; then
  echo "FAIL: rendered developer vhost did not pass nginx -t; restoring prior config" >&2
  if [ "$had_dest" -eq 1 ]; then install -m 0644 "$backup" "$DEST"; else rm -f "$DEST" /etc/nginx/sites-enabled/tradewave-developer-portal; fi
  restore_support_files
  nginx -t >/dev/null 2>&1 || true
  exit 1
fi
if ! systemctl enable nginx >/dev/null; then
  if [ "$had_dest" -eq 1 ]; then install -m 0644 "$backup" "$DEST"; else rm -f "$DEST" /etc/nginx/sites-enabled/tradewave-developer-portal; fi
  restore_support_files
  echo "FAIL: could not enable nginx; prior config restored" >&2
  exit 1
fi
if systemctl is-active --quiet nginx; then
  if ! systemctl reload nginx; then
    echo "FAIL: nginx reload failed; restoring prior developer vhost" >&2
    if [ "$had_dest" -eq 1 ]; then install -m 0644 "$backup" "$DEST"; else rm -f "$DEST" /etc/nginx/sites-enabled/tradewave-developer-portal; fi
    restore_support_files
    nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
    exit 1
  fi
else
  if ! systemctl start nginx; then
    if [ "$had_dest" -eq 1 ]; then install -m 0644 "$backup" "$DEST"; else rm -f "$DEST" /etc/nginx/sites-enabled/tradewave-developer-portal; fi
    restore_support_files
    echo "FAIL: nginx start failed; prior config restored" >&2
    exit 1
  fi
fi
echo "developer API/MCP/portal nginx installed on port $PORT"
