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
format_backup="$(mktemp)"
had_format=0
if [ -f "$FORMAT" ]; then cp -p "$FORMAT" "$format_backup"; had_format=1; fi
install -m 0644 /home/flask/ops/nginx/conf.d/tradewave-log-format.conf \
  "$FORMAT"

# Preserve access_log off; force every file-backed access log to use tw_noargs.
rendered="$(mktemp)"
backup="$(mktemp)"
trap 'rm -f "$rendered" "$backup" "$format_backup"' EXIT
cp -p "$VHOST" "$rendered"
sed -Ei '/^[[:space:]]*access_log[[:space:]]+off[[:space:]]*;/! s#^([[:space:]]*access_log[[:space:]]+[^;[:space:]]+)([[:space:]]+[^;]+)?[[:space:]]*;#\1 tw_noargs;#' "$rendered"
if grep -E '^[[:space:]]*access_log[[:space:]]+' "$rendered" \
    | grep -Ev '^[[:space:]]*access_log[[:space:]]+off[[:space:]]*;|[[:space:]]tw_noargs[[:space:]]*;' >/dev/null; then
  echo "FAIL: an access_log directive is not query-safe in $VHOST" >&2
  exit 1
fi

cp -p "$VHOST" "$backup"
install -m 0644 "$rendered" "$VHOST"
restore_prior() {
  install -m 0644 "$backup" "$VHOST"
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
