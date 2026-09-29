import base64
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "hundred_year_stocks_20260929.json"
TODAY = dt.date(2026, 9, 29)


def _load(name, rel):
    for extra in (ROOT, ROOT / "site", ROOT / "site" / "lib"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RecordedEngine:
    """Replays recorded engine responses; ML scores are supplied per test."""

    def __init__(self, ml=None):
        self.data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.ml = ml or {}
        self.ml_requests = []

    def opp_list(self, today, low, high):
        return self.data["opp_short"] if (low, high) == (7, 30) else []

    def chart(self, symbol, date, days_out, years):
        return self.data["charts"].get("%s|%s|%s|%s" % (symbol, date, days_out, years))

    def ml_scores(self, opps):
        self.ml_requests.extend(opps)
        return {
            "%s|%s|%s|l" % (o["symbol"], o["date"], o["daysOut"]): {"status": "available", "ml_score": self.ml[o["symbol"]]}
            for o in opps if o["symbol"] in self.ml
        }


def _short_tab(result):
    return next(tab for tab in result["tabs"] if tab["key"] == "short")


def test_filters_use_engine_records():
    mod = _load("hundred_year_stocks", "site/hundred_year_stocks.py")
    result = mod.build(RecordedEngine(), TODAY, lambda s: s + " Inc")
    symbols = [row["symbol"] for row in _short_tab(result)["rows"]]
    # FE split its midterm years 5-5, so it is dropped; the others qualify.
    assert "FE" not in symbols
    assert set(symbols) <= {"AJG", "JPM", "ETR", "CPRT", "AAPL"}
    assert len(symbols) == 5


def test_rank_by_ml_score_and_row_format():
    mod = _load("hundred_year_stocks", "site/hundred_year_stocks.py")
    engine = RecordedEngine(ml={"AAPL": 91.0, "ETR": 88.5, "AJG": 70.0})
    rows = _short_tab(mod.build(engine, TODAY, lambda s: s + " Inc"))["rows"]
    assert [r["symbol"] for r in rows[:3]] == ["AAPL", "ETR", "AJG"]
    aapl = rows[0]
    assert aapl["main"] == "13 of 15 yrs"
    assert aapl["midterm"] == "9 of 11 midterm yrs"
    assert aapl["avg"] == "+2.84%"
    assert aapl["window"] == "Sep 29 → Oct 22"
    raw = base64.b64decode(aapl["url"].split("=", 1)[1]).decode()
    assert raw == "2|AAPL|2026-09-29|24|15"
    # The ML request names the 15-year, 13-win study.
    assert {(o["years"], o["mode"], o["partial"]) for o in engine.ml_requests} == {("15", "consecutive", "13")}


def test_missing_engine_data_drops_the_stock():
    mod = _load("hundred_year_stocks", "site/hundred_year_stocks.py")
    engine = RecordedEngine()
    for key in list(engine.data["charts"]):
        if key.startswith("AAPL|"):
            engine.data["charts"][key] = None
    rows = _short_tab(mod.build(engine, TODAY, str))["rows"]
    assert "AAPL" not in [r["symbol"] for r in rows]


def test_loader_rejects_old_or_bad_files(tmp_path):
    home = _load("hundred_year_home", "site/hundred_year_home.py")
    good = {"as_of": "2026-09-29", "tabs": [{"key": "short", "label": "Next 1–4 weeks", "rows": [
        {"symbol": "AAPL", "name": "Apple", "window": "Sep 29 → Oct 22", "main": "13 of 15 yrs",
         "midterm": "9 of 11 midterm yrs", "avg": "+2.84%", "url": "/app/?o=abc"},
        {"symbol": "BAD", "url": "https://evil.example/"},
    ]}]}
    path = tmp_path / "list.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    loaded = home.load_stock_list(str(path), TODAY)
    assert [r["symbol"] for r in loaded["tabs"][0]["rows"]] == ["AAPL"]
    assert home.load_stock_list(str(path), TODAY + dt.timedelta(days=1)) is None
    assert home.load_stock_list(str(tmp_path / "missing.json"), TODAY) is None


def test_template_and_refresh_wiring():
    template = (ROOT / "site" / "templates" / "index-dark-blue.html").read_text(encoding="utf-8")
    refresh = (ROOT / "ops" / "run_site_refresh.sh").read_text(encoding="utf-8")
    generator = (ROOT / "site" / "generate_home_page.py").read_text(encoding="utf-8")
    assert "{% if hy.stocks %}" in template and "data-tw100-tab" in template
    assert "History, not a forecast." in template
    # A display rule on the list must not defeat the hidden tab panel.
    assert ".tw100-stock-list[hidden]{display:none}" in template
    assert "site/hundred_year_stocks.py ||" in refresh
    assert refresh.index("hundred_year_stocks.py") < refresh.index("generate_home_page.py")
    assert 'hundred_year["stocks"] = stocks' in generator and "show_opportunities = False" in generator
