import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "hundred_year_chartdata4_20260928.json"
TEMPLATE = ROOT / "site" / "templates" / "index-dark-blue.html"


def _module():
    path = ROOT / "site" / "hundred_year_home.py"
    spec = importlib.util.spec_from_file_location("hundred_year_home", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _recorded():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _with_live_row(pct, last_trade_date):
    data = _recorded()
    data["ChartData4"][-1]["pct"] = pct
    data["stats"]["last_trade_date"] = last_trade_date
    return data


def test_upcoming_does_not_call_the_engine():
    calls = []
    card = _module().build_card(lambda req: calls.append(req), today=dt.date(2026, 9, 20))
    assert card["status"] == "upcoming"
    assert calls == []


def test_request_is_the_canonical_signature_view():
    seen = []
    _module().build_card(lambda req: seen.append(req) or _recorded(), today=dt.date(2026, 9, 28))
    assert seen == [{
        "market": "5",
        "entry_date": "2026-09-27",
        "symbol": "SPX",
        "engine_days": 294,
        "years": "pe2-24",
    }]


def test_history_passes_engine_values_through():
    card = _module().build_card(lambda req: _recorded(), today=dt.date(2026, 9, 28))
    hist = card["history"]
    assert card["status"] == "active"
    assert card["day_number"] == 2
    assert card["entry_label"] == "Sep 28, 2026"
    assert card["exit_label"] == "Jul 19, 2027"
    assert hist["cycles"] == 24 and hist["winners"] == 23
    assert (hist["first_year"], hist["last_year"]) == (1930, 2022)
    # Engine strings "18.79%" / "18.92%" with the sign added for display only.
    assert hist["mean"] == "+18.79%"
    assert hist["median"] == "+18.92%"
    assert hist["only_loss"] == {"year": 1930, "value": "-23.41%"}
    # Matches the published evidence page: 21 of 23 winners dipped first.
    assert hist["winners_that_dipped"] == 21


def test_live_score_held_until_five_sessions_after_entry():
    mod = _module()
    # Entry Sep 28; Sep 29..Oct 2 is four closes after entry.
    card = mod.build_card(lambda req: _with_live_row("0.80,1.10,-0.40", "2026-10-02"),
                          today=dt.date(2026, 10, 2))
    assert card["live"]["sessions"] == 4
    assert card["live"]["show_score"] is False
    assert "return" not in card["live"]

    card = mod.build_card(lambda req: _with_live_row("1.47,1.97,-1.62", "2026-10-05"),
                          today=dt.date(2026, 10, 6))
    assert card["live"]["sessions"] == 5
    assert card["live"]["show_score"] is True
    assert card["live"]["return"] == "+1.47%"
    assert card["live"]["is_negative"] is False
    assert card["live"]["as_of"] == "Oct 5, 2026"


def test_negative_live_score_is_flagged():
    card = _module().build_card(lambda req: _with_live_row("-2.10,0.50,-3.00", "2026-10-09"),
                                today=dt.date(2026, 10, 10))
    assert card["live"]["return"] == "-2.10%"
    assert card["live"]["is_negative"] is True


def test_stale_engine_data_hides_the_score():
    card = _module().build_card(lambda req: _with_live_row("3.00,4.00,-1.00", "2026-10-09"),
                                today=dt.date(2026, 10, 20))
    assert card["live"]["show_score"] is False


def test_failures_degrade_to_no_numbers():
    mod = _module()
    for fetch in (lambda req: None, lambda req: (_ for _ in ()).throw(RuntimeError("down"))):
        card = mod.build_card(fetch, today=dt.date(2026, 10, 6))
        assert card["status"] == "active"
        assert card["history"] is None and card["live"] is None

    wrong = _recorded()
    wrong["request"]["years"] = 23
    card = mod.build_card(lambda req: wrong, today=dt.date(2026, 10, 6))
    assert card["history"] is None and card["live"] is None


def test_stats_that_disagree_with_rows_are_not_shown():
    data = copy.deepcopy(_recorded())
    data["stats"]["Num Winners"] = "22"
    card = _module().build_card(lambda req: data, today=dt.date(2026, 9, 28))
    assert card["history"] is None


def test_template_has_live_card_and_book_links():
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "content.home_100_year_pattern_enabled and content.hundred_year" in template
    assert "tw100-live" in template
    assert "Starts after" in template
    assert "https://100yearpattern.com/assets/100-year-pattern-preview.pdf" in template
    assert 'href="https://100yearpattern.com"' in template
