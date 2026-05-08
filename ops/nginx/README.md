# Nginx config reference copies

These are reference copies of the nginx config files installed on each
TW2 box. The authoritative location is `/etc/nginx/`. These tracked
copies exist so staging/prod deploys can verify their config is up to
date. Update the tracked copies whenever you change the live ones.

## Layout

- `snippets/security_headers.conf` - shared HTTP security headers (CSP,
  HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy,
  Permissions-Policy). Included into both vhost server blocks.
- `snippets/tw2-proxy-headers.conf` - shared proxy_set_header directives
  for upstream forwarding to tw2-web. Included by every location block
  that proxy_passes to tw2_web.
- `sites-available/tradewave` - the tw2 marketing + app vhost.
- `sites-available/smn-dev` - the SMN news vhost.

## Install on a fresh box

    sudo cp ops/nginx/snippets/security_headers.conf /etc/nginx/snippets/
    sudo cp ops/nginx/snippets/tw2-proxy-headers.conf /etc/nginx/snippets/
    sudo cp ops/nginx/sites-available/tradewave /etc/nginx/sites-available/
    sudo cp ops/nginx/sites-available/smn-dev /etc/nginx/sites-available/
    sudo ln -sf ../sites-available/tradewave /etc/nginx/sites-enabled/tradewave
    sudo ln -sf ../sites-available/smn-dev   /etc/nginx/sites-enabled/smn-dev
    sudo nginx -t && sudo systemctl reload nginx

The CSP allowlist is conservative. If a new third party (e.g. Sentry,
analytics) is added, update connect-src or script-src in
`security_headers.conf`.
