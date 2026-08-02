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
HOME_GENERATOR = ROOT / "site" / "generate_home_page.py"
HOME_TEMPLATE = ROOT / "site" / "templates" / "index-dark-blue.html"


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
    assert "Includes 1978 at +0.03%" in html
    assert "first prospective out-of-sample test" in html
    assert "July 1 through July 31 is 31 days" in html
    assert "data-countdown-minutes" in html
    assert "decay" not in html.lower()
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
        'href="https://tw2-dev.trxstat.com/100-year-pattern.html"'
        in rendered
    )
    assert 'href="/favicon.png"' in rendered
    assert "__CANONICAL_URL__" not in rendered
    assert {path.name for path in copied} == {
        "100-year-pattern-book.webp",
        "100-year-pattern-cycles.csv",
    }


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
