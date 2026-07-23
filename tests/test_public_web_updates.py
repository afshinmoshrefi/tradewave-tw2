"""Regression checks for the final public-site content release."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_homepage_has_revised_hero_and_market_strip():
    generator = _source("site/generate_home_page.py")
    template = _source("site/templates/index-dark-blue.html")

    assert "Apply the same analysis to your own portfolios." in generator
    assert '"market_strip": (' in generator
    assert 'class="market-strip"' in template
    assert 'max-width:740px' in template


def test_public_ledger_precedes_calendar_reminders():
    template = _source("site/templates/index-dark-blue.html")

    assert template.index('id="ledger"') < template.index('id="calendar-reminders"')


def test_learn_pages_credit_the_creator_without_losing_company_footer():
    generator = _source("site/generate_learn.py")
    index_template = _source("site/templates/learn_index.html")
    article_template = _source("site/templates/learn_article.html")

    assert "Michael Sacchitello, CMT" in generator
    assert "FatTail Studio" in generator
    assert 'class="learn-creator"' in index_template
    assert 'class="article-byline"' in article_template
    assert '"@type": "Person"' in index_template
    assert '"@type": "Person"' in article_template
    assert "https://taradataresearch.com/" in index_template
    assert "https://taradataresearch.com/" in article_template
