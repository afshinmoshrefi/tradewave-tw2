#!/usr/bin/env python3
"""
TradeWave Research Page Generator
Generates a static research page from the research template.

Usage:
    python generate_research_page.py
"""

from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
import sys
sys.path.insert(0, '/home/flask')
sys.path.insert(0, '/home/flask/site/lib')
import config
from ga_snippet import ga_head_snippet

# =============================================================================
# CONFIGURATION
# =============================================================================

OUTPUT_DIR = config.web_root_dir
OUTPUT_FILENAME = "research.html"
TEMPLATES_DIR = "/home/flask/site/templates"

# In TW2 the marketing chrome owns the auth links (header includes a /login
# link and a /pricing CTA). Wave Viewer lives at /app/ rather than the
# WordPress /wave-viewer page. domain_root may be empty in dev.
DOMAIN_ROOT = (config.domain_root or "/").rstrip("/") + "/"
SIGNUP_URL  = "/pricing"
LOGIN_URL   = "/login"
LOGOUT_URL  = "/logout"
CONTACT_URL = "mailto:afshin@tradewave.ai"

DISCLAIMER = (
    "TradeWave is a research platform. It is not a brokerage and "
    "does not execute trades. All data is based on historical analysis "
    "and is provided for informational and educational purposes only. "
    "Past performance does not guarantee future results. Trading and "
    "investing involve substantial risk of loss. You should consult "
    "with a qualified financial advisor before making any investment "
    "decisions. Nothing on this website constitutes a recommendation "
    "to buy or sell any security."
)


def main():
    print("TradeWave Research Page Generator")

    jinja_env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )

    template = jinja_env.get_template("research.html")

    upgrade_url = "/pricing"
    wave_viewer_url = "/app/"

    html = template.render(
        enable_seo=False,
        canonical_url=DOMAIN_ROOT + "research.html",
        favicon=config.tw_favicon,
        ga_head_snippet=ga_head_snippet(),
        signup_url=SIGNUP_URL,
        login_url=LOGIN_URL,
        logout_url=LOGOUT_URL,
        upgrade_url=upgrade_url,
        wave_viewer_url=wave_viewer_url,
        contact_url=CONTACT_URL,
        copyright="%d Tara Data Research LLC. All rights reserved." % datetime.now().year,
        disclaimer=DISCLAIMER,
    )

    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_FILENAME
    output_path.write_text(html)

    print("   Generated: %s" % output_path)
    print("   Size: %d bytes" % len(html))
    print("   Done!")


if __name__ == "__main__":
    main()
