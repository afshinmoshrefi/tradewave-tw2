"""Render the Learn section into a scratch directory and check its SEO contract."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "site" / "generate_learn.py"
CONTENT = ROOT / "site" / "content" / "learn"


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    out = tmp_path_factory.mktemp("learn")
    mp = pytest.MonkeyPatch()
    mp.setenv("TW_LEARN_OUTPUT_DIR", str(out))
    spec = importlib.util.spec_from_file_location("generate_learn_under_test", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0
    mp.undo()
    return module, out


def _json_ld_blocks(html):
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def test_every_article_renders_with_valid_structured_data(rendered):
    module, out = rendered
    slugs = sorted(p.stem for p in CONTENT.glob("*.md") if not p.name.startswith("_"))
    assert len(slugs) >= 25
    for slug in slugs:
        html = (out / f"{slug}.html").read_text(encoding="utf-8")
        blocks = _json_ld_blocks(html)
        types = {b["@type"] for b in blocks}
        assert {"Article", "BreadcrumbList"} <= types, slug
        assert "—" not in html, f"em dash in {slug}"


def test_internal_learn_links_resolve(rendered):
    _, out = rendered
    known = {p.name for p in out.glob("*.html")}
    for page in out.glob("*.html"):
        for target in re.findall(r'href="/learn/([a-z0-9-]+\.html)', page.read_text(encoding="utf-8")):
            assert target in known, f"{page.name} links to missing /learn/{target}"


def test_videos_embed_privacy_enhanced_youtube_with_video_schema(rendered):
    _, out = rendered
    html = (out / "learn-tradewave-in-4-minutes.html").read_text(encoding="utf-8")
    assert "https://www.youtube-nocookie.com/embed/7ZQoj2e93oo" in html
    video = [b for b in _json_ld_blocks(html) if b["@type"] == "VideoObject"]
    assert video and video[0]["embedUrl"].endswith("7ZQoj2e93oo")

    html = (out / "win-rate-vs-risk-reward-ratio.html").read_text(encoding="utf-8")
    assert "https://www.youtube-nocookie.com/embed/3STPilmV3aU" in html
    video = [b for b in _json_ld_blocks(html) if b["@type"] == "VideoObject"]
    assert video and video[0]["embedUrl"].endswith("3STPilmV3aU")

    index = (out / "index.html").read_text(encoding="utf-8")
    assert "youtube-nocookie.com/embed/7ZQoj2e93oo" in index
    assert "youtube-nocookie.com/embed/3STPilmV3aU" in index


def test_faq_markup_matches_visible_questions(rendered):
    _, out = rendered
    html = (out / "win-rate-vs-risk-reward-ratio.html").read_text(encoding="utf-8")
    faq = [b for b in _json_ld_blocks(html) if b["@type"] == "FAQPage"][0]
    for q in faq["mainEntity"]:
        assert f"<summary>{q['name']}</summary>" in html.replace("&#39;", "'")


def test_creator_credit_only_on_creator_guides(rendered):
    _, out = rendered
    michael = (out / "understanding-the-stats-table.html").read_text(encoding="utf-8")
    research = (out / "sharpe-ratio-explained.html").read_text(encoding="utf-8")
    assert "Michael Sacchitello, CMT" in michael
    assert "Michael Sacchitello" not in research
    assert "TradeWave Research" in research


def test_index_groups_every_category_in_order(rendered):
    module, out = rendered
    index = (out / "index.html").read_text(encoding="utf-8")
    positions = [index.index(f'id="{c["slug"]}"') for c in module.CATEGORIES]
    assert positions == sorted(positions)
