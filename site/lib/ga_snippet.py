"""
Shared GA4 <head> snippet for the static-site generators.

One helper, identical output on every page: when config.ga_measurement_id
(TW2_GA_MEASUREMENT_ID in /etc/tradewave/secrets.env; empty on dev) is set,
returns the standard gtag.js loader + config block; when empty, returns ''
so dev/staging pages carry no analytics.

Usage (Jinja generators):   render(..., ga_head_snippet=ga_head_snippet())
                            template: {{ ga_head_snippet|safe }} inside <head>
Usage (f-string generators): splice ga_head_snippet() into the <head> block.
"""

import sys

sys.path.insert(0, '/home/flask')
import config


def ga_head_snippet(measurement_id=None):
    """Return the GA4 gtag <head> snippet, or '' when no measurement id is set."""
    mid = config.ga_measurement_id if measurement_id is None else measurement_id
    mid = (mid or '').strip()
    if not mid:
        return ''
    return (
        '<!-- Google Analytics 4 -->\n'
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={mid}"></script>\n'
        '<script>window.dataLayer=window.dataLayer||[];'
        'function gtag(){dataLayer.push(arguments);}'
        f"gtag('js',new Date());gtag('config','{mid}');</script>"
    )
