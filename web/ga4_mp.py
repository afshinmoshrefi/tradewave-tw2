"""
TradeWave 2.0 - Web Tier - GA4 Measurement Protocol (server-side events)
=========================================================================

Thin, fail-open wrapper for firing GA4 events from the server (Measurement
Protocol collect endpoint), used for events that must be reliable regardless
of what the browser's gtag.js does or whether the tab is still open
(Stripe webhook processing, the WorkOS auth callback, etc).

Design rules (same contract as email_utils.py - this is money-path-adjacent
code and must never be the reason a request fails):
  - NEVER raise. Callers (checkout, the Stripe webhook, the WorkOS auth
    callback) must be completely unaffected by a Google Analytics outage,
    DNS blip, or misconfiguration.
  - Silently no-op (debug log only) when unconfigured: missing measurement
    id, missing api secret, or no client_id. This is the normal state on
    dev/staging (TW2_GA_MEASUREMENT_ID and GA4_MP_API_SECRET are prod-only).
  - No retries - a dropped analytics event is not worth blocking or slowing
    a request over.
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

log = logging.getLogger("tw2.web.ga4_mp")

MP_COLLECT_URL = "https://www.google-analytics.com/mp/collect"

# _ga cookie format: GA1.<version>.<part1>.<part2>, e.g. GA1.1.111111111.2222222222
# or GA1.2.111111111.2222222222. The GA4 Measurement Protocol client_id is just
# "<part1>.<part2>" - the leading "GA1.<version>." prefix is dropped.
_GA_COOKIE_RE = re.compile(r'^GA1\.\d+\.(\d+\.\d+)$')


def parse_ga_client_id(request) -> str | None:
    """Extract the GA4 client_id from the first-party `_ga` cookie on `request`.

    GA1.1.111111111.2222222222 -> "111111111.2222222222" (drop the first two
    dot-segments; require exactly two remaining numeric dot-segments).
    Returns None on anything malformed or absent - callers must treat that as
    "don't send", not an error.
    """
    raw = request.cookies.get('_ga')
    if not raw:
        return None
    m = _GA_COOKIE_RE.match(raw.strip())
    if not m:
        return None
    return m.group(1)


def send_event(client_id, name, params=None, user_id=None) -> bool:
    """POST one event to the GA4 Measurement Protocol collect endpoint.

    Fails open: catches every exception, logs at warning, and returns False -
    a GA outage must never affect the calling request. Silently no-ops
    (debug log, returns False) when the measurement id, api secret, or
    client_id is missing - the normal dev/staging state. No retry.

    `user_id`, if passed, should be the internal numeric/string user id -
    never an email address or other PII.
    """
    measurement_id = getattr(config, 'ga_measurement_id', '') or ''
    api_secret = getattr(config, 'GA4_MP_API_SECRET', '') or ''

    if not measurement_id or not api_secret or not client_id:
        log.debug(
            "ga4_mp.send_event(%s) skipped: measurement_id=%s api_secret=%s client_id=%s",
            name, bool(measurement_id), bool(api_secret), bool(client_id),
        )
        return False

    body = {
        "client_id": client_id,
        "events": [{"name": name, "params": params or {}}],
    }
    if user_id:
        body["user_id"] = str(user_id)

    url = f"{MP_COLLECT_URL}?{urlencode({'measurement_id': measurement_id, 'api_secret': api_secret})}"

    try:
        resp = requests.post(url, json=body, timeout=4)
    except Exception as e:
        log.warning("ga4_mp.send_event(%s) failed: %s", name, e)
        return False

    # /mp/collect returns 204 (no body) on a well-formed request, even if the
    # payload is semantically invalid - GA does not validate synchronously.
    # Treat any 2xx as success; log anything else (still don't raise/retry).
    if 200 <= resp.status_code < 300:
        log.debug("ga4_mp.send_event(%s) ok status=%s", name, resp.status_code)
        return True

    log.warning("ga4_mp.send_event(%s) non-2xx status=%s body=%s",
                name, resp.status_code, (resp.text or "")[:300])
    return False
