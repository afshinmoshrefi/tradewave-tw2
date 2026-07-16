#!/usr/bin/env bash
# Install TradeWave's query-free access-log format and apply it to one explicit vhost.
set -euo pipefail

VHOST="${1:-}"
[ -n "$VHOST" ] || { echo "usage: $0 /etc/nginx/sites-available/<site>" >&2; exit 2; }
case "$VHOST" in
  /etc/nginx/sites-available/*) ;;
  *) echo "FAIL: vhost must be an explicit /etc/nginx/sites-available path" >&2; exit 2 ;;
esac
[ -f "$VHOST" ] || { echo "FAIL: vhost not found: $VHOST" >&2; exit 1; }

install -d -m 0755 /etc/nginx/conf.d
FORMAT=/etc/nginx/conf.d/tradewave-log-format.conf
NGINX_MAIN=/etc/nginx/nginx.conf
[ -f "$NGINX_MAIN" ] || { echo "FAIL: nginx main config not found: $NGINX_MAIN" >&2; exit 1; }
format_backup="$(mktemp)"
had_format=0
if [ -f "$FORMAT" ]; then cp -p "$FORMAT" "$format_backup"; had_format=1; fi
install -m 0644 /home/flask/ops/nginx/conf.d/tradewave-log-format.conf \
  "$FORMAT"

# Preserve access_log off; force every file-backed access log to use tw_noargs.
# Patch the http-level default as well as the selected vhost: a server block with
# no local access_log inherits nginx.conf, so checking only explicit vhost lines
# leaves that otherwise ordinary configuration query-capable.
rendered="$(mktemp)"
backup="$(mktemp)"
main_rendered="$(mktemp)"
main_backup="$(mktemp)"
trap 'rm -f "$rendered" "$backup" "$main_rendered" "$main_backup" "$format_backup"' EXIT
cp -p "$VHOST" "$rendered"
cp -p "$NGINX_MAIN" "$main_rendered"
render_safe_access_logs() {
  sed -Ei '/^[[:space:]]*access_log[[:space:]]+off[[:space:]]*;/! s#^([[:space:]]*access_log[[:space:]]+[^;[:space:]]+)([[:space:]]+[^;]+)?[[:space:]]*;#\1 tw_noargs;#' "$1"
}
order_format_before_access_logs() {
  local path="$1" first_log format_include ordered
  first_log="$(grep -nE '^[[:space:]]*access_log[[:space:]]+[^;[:space:]]+' "$path" \
    | grep -Ev 'access_log[[:space:]]+off[[:space:]]*;' | head -n1 | cut -d: -f1 || true)"
  format_include="$(grep -nF 'include /etc/nginx/conf.d/*.conf;' "$path" \
    | head -n1 | cut -d: -f1 || true)"
  [ -z "$first_log" ] || [ -z "$format_include" ] || [ "$format_include" -lt "$first_log" ] || {
    ordered="$(mktemp)"
    awk '
      /^[[:space:]]*access_log[[:space:]]+[^;[:space:]]+/ &&
          $0 !~ /access_log[[:space:]]+off[[:space:]]*;/ {
        pending = pending $0 ORS
        next
      }
      { print }
      /^[[:space:]]*include \/etc\/nginx\/conf\.d\/\*\.conf;/ {
        printf "%s", pending
        pending = ""
      }
      END { if (pending != "") exit 42 }
    ' "$path" >"$ordered"
    mv "$ordered" "$path"
  }
}
require_safe_access_logs() {
  local path="$1"
  if grep -E '^[[:space:]]*access_log[[:space:]]+' "$path" \
      | grep -Ev '^[[:space:]]*access_log[[:space:]]+off[[:space:]]*;|[[:space:]]tw_noargs[[:space:]]*;' >/dev/null; then
    echo "FAIL: an access_log directive is not query-safe in $path" >&2
    exit 1
  fi
}
render_safe_access_logs "$rendered"
render_safe_access_logs "$main_rendered"
# Some distro nginx.conf files include conf.d after the global access_log. Move
# only pre-include file-backed log directives below that include so tw_noargs is
# defined before nginx parses its first use.
order_format_before_access_logs "$main_rendered"
require_safe_access_logs "$rendered"
require_safe_access_logs "$main_rendered"

cp -p "$VHOST" "$backup"
cp -p "$NGINX_MAIN" "$main_backup"
install -m 0644 "$rendered" "$VHOST"
install -m 0644 "$main_rendered" "$NGINX_MAIN"
restore_prior() {
  install -m 0644 "$backup" "$VHOST"
  install -m 0644 "$main_backup" "$NGINX_MAIN"
  if [ "$had_format" -eq 1 ]; then install -m 0644 "$format_backup" "$FORMAT"; else rm -f "$FORMAT"; fi
}
if ! nginx -t; then
  restore_prior
  nginx -t >/dev/null 2>&1 || true
  echo "FAIL: safe-log vhost failed nginx -t; prior config restored" >&2
  exit 1
fi
if ! systemctl reload nginx; then
  restore_prior
  nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
  echo "FAIL: nginx reload failed; prior config restored" >&2
  exit 1
fi
echo "query-free nginx logging installed for $VHOST"
