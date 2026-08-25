import csv
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE_SOURCE = ROOT / "site" / "100-year-pattern" / "100-year-pattern.html"
CSV_SOURCE = (
    ROOT
    / "site"
    / "static"
    / "100-year-pattern"
    / "100-year-pattern-cycles.csv"
)
ICS_SOURCE = (
    ROOT
    / "site"
    / "static"
    / "100-year-pattern"
    / "100-year-pattern-september-27-2026.ics"
)
HOME_GENERATOR = ROOT / "site" / "generate_home_page.py"
HOME_TEMPLATE = ROOT / "site" / "templates" / "index-dark-blue.html"
NGINX_SITE = ROOT / "ops" / "nginx" / "sites-available" / "tradewave"
STAGE_BOOTSTRAP = ROOT / "ops" / "staging" / "bootstrap_stage_web_services.sh"


def _load_page_generator():
    path = ROOT / "site" / "generate_100_year_pattern.py"
    spec = importlib.util.spec_from_file_location("generate_100_year_pattern", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_static_evidence_page_contains_the_complete_record():
    html = PAGE_SOURCE.read_text(encoding="utf-8")
    with CSV_SOURCE.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 24
    assert html.count('class="cycle-column"') == 24
    assert html.count('<tr class="loss-row">') == 1
    assert "This record begins in 1930." in html
    assert "Out of 24 completed windows, 23 ended above their starting close." in html
    assert "Twenty-three of 24 completed windows" not in html
    assert (
        "1978 finished +0.03% before transaction costs and is therefore "
        "classified as a positive close-to-close return."
    ) in html
    assert "first prospective out-of-sample test" in html
    assert "July 1 through July 31 is 31 days" in html
    assert "data-countdown-minutes" in html
    assert "decay" not in html.lower()
    assert "Stock Trader's Almanac" in html
    assert "Jeffrey Hirsch calls it the Sweet Spot" in html
    assert (
        '<h1><span>The 100-Year Pattern</span><span>24 completed cycles.</span>'
        '<span class="hero-result">96% finished positive.</span></h1>'
    ) in html
    assert "Next unresolved window" in html
    assert "A historically favorable S&amp;P 500 window is approaching again." in html
    assert "No account. No subscription. No email." in html
    assert "The information remains public whether or not you ever use TradeWave." in html
    assert "You do not need TradeWave to understand or use the public record above." in html
    assert "Add September 27 to my calendar" in html
    assert html.count('type="button" data-calendar-open') == 2
    assert 'const calendarTriggers = document.querySelectorAll("[data-calendar-open]");' in html
    assert 'aria-haspopup="dialog"' in html
    assert "Google Calendar" in html
    assert "Outlook Calendar" in html
    assert "Apple or other calendar" in html
    assert ICS_SOURCE.is_file()
    assert 'href="/signup"' not in html
    assert "U.S. midterm years only" in html
    assert "One cycle every four years" in html
    assert "A positive result means the exit close is higher than the entry close." in html
    assert "This season was documented before TradeWave." in html
    assert "The season is not a TradeWave finding and is not claimed as one here." in html
    assert "This record begins September 27, before Q4 opens" in html
    assert "September 27 to July 18 produced the highest cumulative return in the date-window test." in html
    assert "testing fixed date pairs against all 24 completed cycles selected the exact days." in html
    assert "The same two-step process can be used" not in html
    assert "How It Was Found" not in html
    assert "Visual discovery" not in html
    assert "100-year-pattern-trend-chart.webp" in html
    assert "We do not ask for trust - we publish the proof" not in html
    assert "One failure." not in html
    assert "\u2014" not in html


def test_page_generator_writes_environment_aware_output_atomically(tmp_path, monkeypatch):
    monkeypatch.setenv("TW2_PUBLIC_HOST", "tw2-dev.trxstat.com")
    monkeypatch.setenv("TW2_ENV", "dev")
    generator = _load_page_generator()

    output_html, copied = generator.publish(tmp_path)
    rendered = output_html.read_text(encoding="utf-8")

    assert output_html == tmp_path / "100-year-pattern.html"
    if os.name != "nt":
        assert output_html.stat().st_mode & 0o777 == 0o644
        asset_mode = (tmp_path / "_static" / "100-year-pattern").stat().st_mode
        assert asset_mode & 0o777 == 0o755
    assert 'content="noindex,nofollow"' in rendered
    assert (
        'href="https://tw2-dev.trxstat.com/100-year-pattern"'
        in rendered
    )
    assert 'href="/favicon.png"' in rendered
    assert "__CANONICAL_URL__" not in rendered
    assert {path.name for path in copied} == {
        "100-year-pattern-book.webp",
        "100-year-pattern-cycles.csv",
        "100-year-pattern-september-27-2026.ics",
        "100-year-pattern-trend-chart.webp",
    }
    calendar = (
        tmp_path
        / "_static"
        / "100-year-pattern"
        / "100-year-pattern-september-27-2026.ics"
    ).read_bytes()
    assert b"DTSTART;VALUE=DATE:20260928\r\n" in calendar
    assert b"DTEND;VALUE=DATE:20260929\r\n" in calendar
    assert b"URL:https://tw2-dev.trxstat.com/100-year-pattern\r\n" in calendar
    assert b"__CANONICAL_URL__" not in calendar
    assert b"TRIGGER;VALUE=DATE-TIME:20260921T130000Z\r\n" in calendar
    assert b"TRIGGER;VALUE=DATE-TIME:20260927T130000Z\r\n" in calendar


def test_page_generator_cli_runs_outside_the_repository(tmp_path):
    output = tmp_path / "published"
    environment = os.environ.copy()
    environment.update({"TW2_PUBLIC_HOST": "tw2-dev.trxstat.com", "TW2_ENV": "dev"})
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "site" / "generate_100_year_pattern.py"),
            "--output-dir",
            str(output),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (output / "100-year-pattern.html").is_file()


def test_home_countdown_is_scoped_and_disabled_by_default():
    generator = HOME_GENERATOR.read_text(encoding="utf-8")
    template = HOME_TEMPLATE.read_text(encoding="utf-8")

    assert "TW2_HOME_100_YEAR_PATTERN_ENABLED" in generator
    assert "home_100_year_pattern_enabled" in generator
    assert template.count("TW100 HOME COUNTDOWN START") == 3
    assert template.count("TW100 HOME COUNTDOWN END") == 3
    assert "tw100-home-countdown" in template
    assert "2026-09-27T00:00:00-04:00" in template
    assert "setInterval(render,60000)" in template
    assert 'href="/100-year-pattern"' in template
    assert 'href="/100-year-pattern.html"' not in template


def test_100_year_pattern_clean_url_is_canonical_and_backward_compatible():
    redirect_html = (
        "location = /100-year-pattern.html {\n"
        "        absolute_redirect off;\n"
        "        return 308 /100-year-pattern$is_args$args;\n"
        "    }"
    )
    redirect_slash = (
        "location = /100-year-pattern/ {\n"
        "        absolute_redirect off;\n"
        "        return 308 /100-year-pattern$is_args$args;\n"
        "    }"
    )
    nginx = NGINX_SITE.read_text(encoding="utf-8")
    bootstrap = STAGE_BOOTSTRAP.read_text(encoding="utf-8")

    assert "location = /100-year-pattern {" in nginx
    assert redirect_html in nginx
    assert redirect_slash in nginx
    assert "location = /100-year-pattern {" in bootstrap
    assert "location = /100-year-pattern.html { absolute_redirect off; return 308 /100-year-pattern$is_args$args; }" in bootstrap
    assert "location = /100-year-pattern/ { absolute_redirect off; return 308 /100-year-pattern$is_args$args; }" in bootstrap
