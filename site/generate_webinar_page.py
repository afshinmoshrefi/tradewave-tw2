#!/usr/bin/env python3
"""Generate /webinars/ from the TradeWave webinar Google Sheet.

The canonical page is /webinars/. The compatibility alias /webinar redirects
there. A browser-facing JSON schedule is written beside the page so the home
footer can reveal its Webinars link only while a future session exists.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/site/lib")
import config  # noqa: E402
from ga_snippet import ga_head_snippet  # noqa: E402
from webinar_schedule import (  # noqa: E402
    fetch_webinar_data,
    get_upcoming_webinars,
    public_sessions,
)


SITE_DIR = Path("/home/flask/site")
TEMPLATES_DIR = SITE_DIR / "templates"
HEADER_PARTIAL = TEMPLATES_DIR / "_tw_header.html"
OUTPUT_DIR = Path(config.web_root_dir)
DOMAIN_ROOT = (config.domain_root or "/").rstrip("/") + "/"
CANONICAL_URL = DOMAIN_ROOT + "webinars/"
ENABLE_SEO = os.environ.get("TW2_ENV", "").strip().lower() == "prod"


def _write_atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / ("." + path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _alias_html():
    """Static fallback keeps /webinar and /webinar/ working on every nginx tier."""
    return """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
  <meta name=\"robots\" content=\"noindex,follow\">
  <link rel=\"canonical\" href=\"{canonical}\">
  <meta http-equiv=\"refresh\" content=\"0;url=/webinars/\">
  <title>TradeWave Webinars</title>
  <script>window.location.replace('/webinars/' + window.location.search + window.location.hash);</script>
</head>
<body><p>This page has moved to <a href=\"/webinars/\">TradeWave Webinars</a>.</p></body>
</html>
""".format(canonical=CANONICAL_URL)


def _event_json_ld(sessions):
    graph = []
    for session in sessions:
        start = datetime.fromisoformat(session["start_iso"])
        graph.append({
            "@type": "Event",
            "name": session["title"],
            "description": session["description"],
            "startDate": start.isoformat(),
            "endDate": (start + timedelta(hours=1)).isoformat(),
            "eventStatus": "https://schema.org/EventScheduled",
            "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
            "location": {"@type": "VirtualLocation", "url": CANONICAL_URL},
            "organizer": {
                "@type": "Organization",
                "name": "TradeWave",
                "url": DOMAIN_ROOT,
            },
            "offers": {
                "@type": "Offer",
                "price": "0",
                "priceCurrency": "USD",
                "availability": "https://schema.org/InStock",
                "url": CANONICAL_URL,
            },
        })
    return json.dumps({"@context": "https://schema.org", "@graph": graph})


def generate(force_refresh=False):
    data = fetch_webinar_data(force_refresh=force_refresh)
    sessions = get_upcoming_webinars(data)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("webinars.html")
    html = template.render(
        canonical_url=CANONICAL_URL,
        robots_content="index, follow" if ENABLE_SEO else "noindex, nofollow",
        favicon=config.tw_favicon,
        ga_head_snippet=ga_head_snippet(),
        header_html=HEADER_PARTIAL.read_text(encoding="utf-8"),
        sessions=sessions,
        event_json_ld=_event_json_ld(sessions),
        year=datetime.now().year,
    )

    page_dir = OUTPUT_DIR / "webinars"
    page = page_dir / "index.html"
    public_feed = page_dir / "webinars.json"
    alias = OUTPUT_DIR / "webinar" / "index.html"
    _write_atomic(page, html)
    _write_atomic(public_feed, json.dumps(public_sessions(sessions), indent=2) + "\n")
    _write_atomic(alias, _alias_html())
    print("Generated: %s (%d future sessions)" % (page, len(sessions)))
    print("Generated: %s" % public_feed)
    print("Generated alias: %s -> /webinars/" % alias)
    return sessions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="refresh the Google Sheet feed")
    args = parser.parse_args()
    generate(force_refresh=args.force)


if __name__ == "__main__":
    main()
