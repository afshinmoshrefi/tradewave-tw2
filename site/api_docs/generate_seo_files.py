#!/usr/bin/env python3
"""Build the portal-level SEO + discovery files into the developer-portal root staging dir
(site/api_marketing/out/, which the deploy rsyncs to /var/www/developers/):

  - sitemap.xml   : every public portal page (marketing + docs + learn + playground)
  - robots.txt    : allow all + Sitemap pointer
  - llms.txt      : an AI-agent-friendly map (llmstxt.org convention) - apt for an MCP product
  - og-developers.png : the Open Graph / Twitter share card image

Run AFTER the four page generators (it scans their output dirs). Run with the web venv:
  /home/flask/venv/bin/python site/api_docs/generate_seo_files.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "site" / "lib"))
import portal_urls   # noqa: E402
import portal_seo    # noqa: E402

PORTAL = portal_urls.PORTAL_URL
# The portal root docroot maps from the marketing staging dir, so the SEO files live there.
ROOT_OUT = REPO / "site" / "api_marketing" / "out"
MARKETING_OUT = REPO / "site" / "api_marketing" / "out"
DOCS_OUT = REPO / "site" / "api_docs"
LEARN_OUT = REPO / "site" / "api_learn" / "out"
PLAY_OUT = REPO / "site" / "api_playground" / "out"

# (subdir on the live portal, staging dir, changefreq, priority)
SECTIONS = [
    ("", MARKETING_OUT, "weekly", "1.0"),       # marketing pages at the root
    ("docs/", DOCS_OUT, "weekly", "0.8"),
    ("learn/", LEARN_OUT, "monthly", "0.7"),
    ("playground/", PLAY_OUT, "monthly", "0.6"),
]


def collect_urls():
    urls = []
    seen = set()
    for sub, out_dir, freq, prio in SECTIONS:
        if not out_dir.exists():
            continue
        for html in sorted(out_dir.glob("*.html")):
            name = html.name
            if name == "index.html":
                loc = PORTAL + "/" + sub                  # canonical dir URL
            else:
                loc = PORTAL + "/" + sub + name
            if loc in seen:
                continue
            seen.add(loc)
            # landing gets top priority
            p = "1.0" if (sub == "" and name == "index.html") else prio
            urls.append((loc, freq, p))
    return urls


def build_og_image(path: Path):
    """A simple 1200x630 dark-brand Open Graph card. Best-effort; skips if fonts/PIL fail."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        print("  (PIL unavailable, skipping og image: %s)" % e)
        return False
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), (15, 10, 21))
    d = ImageDraw.Draw(img)
    # a subtle gradient bar
    for x in range(W):
        t = x / W
        d.line([(x, 0), (x, 8)], fill=(int(99 + t * 60), int(102 - t * 20), int(241 - t * 40)))

    def _font(size, bold=True):
        for cand in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]:
            if Path(cand).exists():
                return ImageFont.truetype(cand, size)
        return ImageFont.load_default()

    d.text((80, 150), "TradeWave Developers", font=_font(72), fill=(255, 255, 255))
    d.text((80, 260), "Seasonal + ML trading signals", font=_font(40, bold=False), fill=(180, 170, 200))
    d.text((80, 320), "REST API and MCP server for AI agents", font=_font(40, bold=False), fill=(180, 170, 200))
    d.text((80, 470), "Signals only. Works with any broker. A public, forward-tested track record.",
           font=_font(28, bold=False), fill=(130, 120, 150))
    d.text((80, 540), PORTAL.replace("https://", ""), font=_font(30), fill=(129, 140, 248))
    img.save(path, "PNG")
    return True


def main():
    ROOT_OUT.mkdir(parents=True, exist_ok=True)
    urls = collect_urls()
    (ROOT_OUT / "sitemap.xml").write_text(portal_seo.build_sitemap(urls), encoding="utf-8")
    print("  sitemap.xml  (%d urls)" % len(urls))
    (ROOT_OUT / "robots.txt").write_text(portal_seo.build_robots(), encoding="utf-8")
    print("  robots.txt")
    (ROOT_OUT / "llms.txt").write_text(portal_seo.build_llms(), encoding="utf-8")
    print("  llms.txt")
    if build_og_image(ROOT_OUT / "og-developers.png"):
        print("  og-developers.png")
    print("Done.")


if __name__ == "__main__":
    main()
