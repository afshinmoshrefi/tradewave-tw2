"""Screenshot self-contained rendered HTML files via Playwright (headless)."""
import sys
from playwright.sync_api import sync_playwright

# args: pairs of html_path::png_path
pairs = [a.split("::") for a in sys.argv[1:]]

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
    for html_path, png_path in pairs:
        pg.goto("file://" + html_path, wait_until="networkidle")
        pg.wait_for_timeout(250)
        pg.screenshot(path=png_path, full_page=True)
        print("shot:", png_path)
    b.close()
