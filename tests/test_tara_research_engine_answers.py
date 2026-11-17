"""TW-TASK-0030: engine-grounded answers for the five research classes Tara failed live.

The engine seams are replayed from responses recorded from the TradeWave engine on
2026-11-17 (tests/fixtures/tara_research_engine_20261117.json). No expected statistic is
recomputed here: assertions compare the reply with the recorded engine values, and with
the engine requests Tara had to make (dates, direction, band, lookback, symbols).
"""
import datetime
import json
import re
import sys
import time
from pathlib import Path

import jwt
import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "appserver/appserver"))

import chatbot  # noqa: E402
import tara_gateway  # noqa: E402
import tara_research as research  # noqa: E402

FIXTURE = json.loads((ROOT / "tests/fixtures/tara_research_engine_20261117.json").read_text())
TODAY = datetime.date.fromisoformat(FIXTURE["today"])          # Tuesday 2026-11-17
LOADED_AAPL = {"symbol": "AAPL", "market": "2", "start_date": "2026-11-17",
               "days_out": "45", "years": "20", "pe_cycle": "cons"}


def plan_token(level):
    """A token carrying a plan level, as the browser sends it (signature irrelevant here)."""

    return jwt.encode({"user": "research-test", "user_level": str(level)},
                      "test-only-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", algorithm="HS256")


def _section(token):
    """Recorded engine responses for the plan level in the token (Strategist by default)."""

    try:
        level = jwt.decode(token, options={"verify_signature": False}).get("user_level", "6")
    except Exception:
        level = "6"
    return FIXTURE["levels"]["L%s" % level]


def chart_key(market, symbol, entry, days, years, params):
    return "%s|%s|%s|%s|%s|%s" % (
        market, symbol, entry, days, years,
        "&".join("%s=%s" % item for item in sorted(params.items())))


@pytest.fixture
def engine(monkeypatch):
    """Replay recorded engine responses and capture every engine request."""

    calls = {"opplist": [], "chart": [], "names": 0}

    def opplist(market, day, year1, year2, day_range, token):
        key = "%s|%s|%s|%s|%s" % (market, day.isoformat(), year1, year2, day_range)
        calls["opplist"].append({"market": str(market), "day": day, "year1": int(year1),
                                 "year2": int(year2), "day_range": day_range})
        hit = _section(token)["opplist"].get(key)
        return (hit["status"], hit["rows"]) if hit else (None, None)

    def chart(market, symbol, entry_date, days_out, years_value, token, **params):
        calls["chart"].append({"market": str(market), "symbol": symbol, "entry": entry_date,
                               "days": int(days_out), "years": str(years_value), "params": params})
        hit = _section(token)["chart"].get(
            chart_key(market, symbol, entry_date, days_out, years_value, params))
        return (hit["status"], hit["payload"]) if hit else (None, None)

    def names(market, token):
        calls["names"] += 1
        return FIXTURE["names"]

    def resolve(symbol, question, token, current_view=None):
        return _section(token)["resolve"].get(
            str(symbol).upper(), {"status": "not_found", "symbol": str(symbol).upper()})

    def available_years(market, symbol, token, pe_cycle=None):
        return _section(token)["years"].get(
            "%s|%s|%s" % (market, str(symbol).upper(), pe_cycle or "cons"))

    monkeypatch.setattr(research, "_engine_opplist", opplist)
    monkeypatch.setattr(research, "_engine_chart", chart)
    monkeypatch.setattr(research, "_engine_symbol_names", names)
    monkeypatch.setitem(research._NAMES_CACHE, "index", None)
    monkeypatch.setattr(tara_gateway, "_resolve_question_symbol", resolve)
    monkeypatch.setattr(tara_gateway, "_symbol_max_available_years", available_years)
    return calls


def ask(message, view=None, token="user-token", **kwargs):
    kwargs.setdefault("today", TODAY)
    return research.build_research_command(message, view or {}, token, **kwargs)


def text_of(command):
    reply = re.sub(r"</?div[^>]*>|<br>", "\n", command["reply"])
    return re.sub(r"<[^>]+>", "", reply)


def ranked_lines(command):
    return [line.strip() for line in text_of(command).split("\n") if re.match(r"\s*\d+\. ", line)]


def chart_payload(call, token="user-token"):
    return _section(token)["chart"][chart_key(
        call["market"], call["symbol"], call["entry"], call["days"], call["years"],
        call["params"])]["payload"]


# ---------------------------------------------------------------------------
# 1. Index screen: patterns ENTERING in a window, for a direction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "find s&p500 stocks entering seasonaly bearish patterns htis week",
    "find s&p500 stocks entering seasonaly bearish patterns this week",
    "Find S&P 500 stocks entering a historically bearish seasonal window this week.",
    "which S&P 500 names start a short seasonal pattern this week?",
])
def test_bearish_week_screen_returns_a_ranked_list_for_the_whole_week(engine, message):
    command = ask(message)
    assert command["trace"]["event"] == "research_screen"
    assert command["trace"]["direction"] == "short"
    # Every remaining trading day of the week is screened - never days already gone.
    assert sorted({call["day"].isoformat() for call in engine["opplist"]}) == [
        "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]
    assert {call["market"] for call in engine["opplist"]} == {"2"}
    # The widest in-band detector table (S&P 500 at 10 years = at least 8 winners).
    assert {(call["year1"], call["year2"]) for call in engine["opplist"]} == {(10, 8)}

    lines = ranked_lines(command)
    assert len(lines) == 10, "a one-name 'list' was the reported failure"
    symbols = [re.match(r"\d+\. (\S+)", line).group(1) for line in lines]
    assert len(set(symbols)) == 10
    for line in lines:
        assert re.search(r"fell in \d+ of \d+ years \(\d+%\)", line)
        assert "Sharpe" in line and re.search(r"avg short-side return \+\d", line)
        assert re.search(r"starts (?:Tue Nov 17|Wed Nov 18|Thu Nov 19|Fri Nov 20)", line)
    sharpes = [float(re.search(r"Sharpe (-?\d+\.\d+)", line).group(1)) for line in lines]
    assert sharpes == sorted(sharpes, reverse=True)
    assert "not sell or short recommendations" in text_of(command)


def test_weekend_dated_patterns_are_shown_on_their_first_session(engine):
    command = ask("Top 5 Nasdaq 100 stocks by win rate next week, 10-day holds")
    reply = text_of(command)
    assert not re.search(r"starts (?:Sat|Sun) ", reply)
    assert "starts Mon Nov 23 (calendar start Sat Nov 21)" in reply


def test_screen_records_are_the_engine_completed_year_results(engine):
    command = ask("find s&p500 stocks entering seasonaly bearish patterns this week")
    by_symbol = {call["symbol"]: call for call in engine["chart"]}
    assert all(call["params"] == {"comparison_direction": "short"} for call in engine["chart"])
    assert all(call["years"] == "10" for call in engine["chart"])
    for row in command["rows"]:
        stats = chart_payload(by_symbol[row["symbol"]])["stats"]
        assert row["wins"] == int(stats["Num Winners"])
        assert row["n"] == int(stats["Num Winners"]) + int(stats["Num Losers"])
        assert "%.2f" % row["sharpe"] == "%.2f" % float(stats["Sharpe Ratio"])
        assert "%.2f" % row["avg"] == "%.2f" % float(stats["Avg Profit - All"].rstrip("%"))


# ---------------------------------------------------------------------------
# 2. Ranked screen: highest win rate over the next N days
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "which S&P500 stocks have the highest seasonal win rate over the next 10 days",
    "Which S&P 500 stocks have the highest seasonal win rate over the next 10 days?",
    "rank S&P 500 stocks by win rate for the next ten days",
])
def test_win_rate_ranking_uses_engine_win_records(engine, message):
    command = ask(message)
    assert command["trace"]["rank"] == "win_rate"
    assert command["trace"]["entry_first"] == "2026-11-17"
    assert command["trace"]["entry_last"] == "2026-11-26"
    # The strictest band ("won every year") is read first.
    assert (engine["opplist"][0]["year1"], engine["opplist"][0]["year2"]) == (10, 10)
    lines = ranked_lines(command)
    assert len(lines) == 10
    records = [tuple(map(int, re.search(r"profitable in (\d+) of (\d+) years", line).groups()))
               for line in lines]
    rates = [wins / years for wins, years in records]
    assert rates == sorted(rates, reverse=True)
    sharpes = [float(re.search(r"Sharpe (-?\d+\.\d+)", line).group(1)) for line in lines]
    for index in range(1, len(lines)):                       # ties broken by Sharpe
        if rates[index] == rates[index - 1]:
            assert sharpes[index] <= sharpes[index - 1]
    reply = text_of(command)
    assert "did not return win-rate" not in reply
    assert "Top 10 by win rate" in reply
    assert "START in the next 10 days" in reply and "10-day holds" in reply


def test_explicit_hold_length_is_sent_to_the_detector(engine):
    command = ask("Top 5 Nasdaq 100 stocks by win rate next week, 10-day holds")
    assert {call["market"] for call in engine["opplist"]} == {"1"}
    assert {call["day_range"] for call in engine["opplist"]} == {"9-9"}   # engine days = display - 1
    assert min(call["day"] for call in engine["opplist"]) == datetime.date(2026, 11, 23)
    lines = ranked_lines(command)
    assert len(lines) == 5 and all("10-day window" in line for line in lines)
    assert "START in the next" not in text_of(command)
    assert command["actions"] == []                         # no table market was supplied


def test_screen_switches_the_table_when_it_shows_another_market(engine):
    command = ask("Top 5 Nasdaq 100 stocks by win rate next week, 10-day holds", table_market="2")
    assert command["actions"] == [{"type": "set_view", "spec": {"market": "1"}}]


REQUEST_CASES = [
    # (question, expected request fields) - includes real customer phrasings (paraphrase-free
    # question text only) from the production Tara log.
    ("find s&p500 stocks entering seasonaly bearish patterns this week",
     {"market": "2", "direction": "short", "rank": "sharpe", "limit": 10,
      "first": "2026-11-17", "last": "2026-11-22"}),
    ("Which Dow stocks have the highest seasonal win rate over the next 30 days?",
     {"market": "0", "direction": "long", "rank": "win_rate", "first": "2026-11-17",
      "last": "2026-12-16"}),
    ("Top 5 Nasdaq 100 stocks by win rate next week, 10-day holds",
     {"market": "1", "rank": "win_rate", "limit": 5, "hold": (10, 10),
      "first": "2026-11-23", "last": "2026-11-29"}),
    ("Rank the top 10 seasonal opportunities across all U.S. equities by Sharpe Ratio for a 45-day hold.",
     {"market": "4", "rank": "sharpe", "limit": 10, "hold": (45, 45),
      "first": "2026-11-17", "last": "2026-11-17"}),
    ("Show me bullish S&P 500 stock patterns this time of year",
     {"market": "2", "direction": "long", "first": "2026-11-17", "last": "2026-11-17"}),
    ("Find opportunities with an SR of more than 2.5 and that are S&P 500 stocks",
     {"market": "2", "min_sharpe": 2.5}),
    ("Find best opportunities starting tloday or tomorrow of day öfter tomorrow. , win rate min 90%, "
     "SR >1, consequitive years, Wilshire 5000 universe",
     {"market": "4", "min_win_rate": 90, "min_sharpe": 1.0, "rank": "sharpe",
      "first": "2026-11-17", "last": "2026-11-18"}),
    ("Best 10 opportunities , wilshire5000 universelle, min winrate 85%, 10 of 12 years, "
     "conaequitve, AVG profit min 5%, may hold 90days",
     {"market": "4", "limit": 10, "min_win_rate": 85, "min_wins": 10, "year1": 12,
      "min_avg": 5.0, "hold": (1, 90), "rank": "sharpe"}),
    ("Tara, hi, show me a list of best 10 best stocks/opportunities, long, hold for max 90 days "
     "in the Russell 1000",
     {"market": "3", "limit": 10, "direction": "long", "hold": (1, 90)}),
    ("which ETFs have the highest win rate over the next 2 weeks",
     {"market": "11", "rank": "win_rate", "first": "2026-11-17", "last": "2026-11-30"}),
]


@pytest.mark.parametrize("message,expected", REQUEST_CASES, ids=[c[0][:48] for c in REQUEST_CASES])
def test_screen_request_parsing_generalizes(message, expected):
    request = research._screen_request(message, TODAY, None)
    assert request is not None, message
    for field, value in expected.items():
        actual = request[field]
        if isinstance(actual, datetime.date):
            actual = actual.isoformat()
        assert actual == value, (field, actual, value)


def test_table_market_supplies_the_universe_for_a_filtered_screen():
    request = research._screen_request(
        "What opportunities in the next week have a SR over 3", TODAY, "1")
    assert request["market"] == "1" and request["min_sharpe"] == 3.0
    assert research._screen_request(
        "What opportunities in the next week have a SR over 3", TODAY, None) is None


@pytest.mark.parametrize("message", [
    "what's 100 year pattern",
    "best setup for INFY",
    "what are today's best set ups",
    "which tech stocks tend to rise this time of the year",
    "How strong is the KMB window historically? Please show me the win rate and Sharpe.",
    "What is the S&P 500?",
    "what is MAE",
    "show me AAPL",
    "Compare Apple's fourth-quarter seasonal performance in midterm years versus pre-election years.",
    "Scan my Growth watchlist and tell me which tickers are entering a seasonal buy zone next month.",
    "Show me the strongest bullish seasonal patterns in the technology sector right now.",
    "which S&P 500 stocks report earnings this week",
    "which Nasdaq 100 stocks have the highest volume today",
    "what is the highest win rate date for this pattern",
    "how late can I enter this trade",
    "what does MAE mean for this pattern",
    "Which current setups have an AI win probability higher than their 10-year historical win rate?",
])
def test_neighbor_questions_are_left_to_their_existing_paths(engine, message):
    assert ask(message) is None
    assert engine["opplist"] == [] and engine["chart"] == []


def test_unreachable_engine_falls_back_to_the_normal_chat_path(monkeypatch):
    monkeypatch.setattr(research, "_engine_opplist", lambda *args: (None, None))
    assert ask("find s&p500 stocks entering seasonaly bearish patterns this week") is None


def test_empty_screen_says_so_without_inventing_a_candidate(engine, monkeypatch):
    monkeypatch.setattr(research, "_engine_opplist", lambda *args: (200, []))
    command = ask("find s&p500 stocks entering seasonaly bearish patterns this week")
    assert "No S&amp;P 500 bearish seasonal windows matched" in command["reply"]
    assert command["actions"] == [] and engine["chart"] == []


def test_market_outside_the_plan_is_reported(engine, monkeypatch):
    monkeypatch.setattr(research, "_engine_opplist", lambda *args: (403, None))
    command = ask("which Wilshire 5000 stocks have the highest win rate this week")
    assert "outside this account's available markets" in command["reply"]


# ---------------------------------------------------------------------------
# 3. Dated symbol study
# ---------------------------------------------------------------------------

def test_apple_now_to_year_end_loads_and_reports_the_exact_study(engine):
    command = ask("analyze apple historic return from now to year end over the last 20 years")
    assert command["trace"] == {"event": "research_window_study", "symbol": "AAPL"}
    assert engine["chart"] == [{"market": "2", "symbol": "AAPL", "entry": "2026-11-17",
                                "days": 45, "years": "20", "params": {}}]
    stats = chart_payload(engine["chart"][0])["stats"]
    reply = text_of(command)
    assert "Nov 17 – Dec 31, 2026" in reply and "45 calendar days" in reply
    assert "profitable in %s of 20 completed consecutive years" % stats["Num Winners"] in reply
    assert "Average return +%.1f%%" % float(stats["Avg Profit - All"].rstrip("%")) in reply
    assert "median +%.1f%%" % float(stats["Median Profit"].rstrip("%")) in reply
    assert "Sharpe Ratio %s" % stats["Sharpe Ratio"] in reply
    assert "best year: 2007" in reply and "Worst year: 2018" in reply
    assert "Largest rise inside the window (MFE)" in reply
    assert "Deepest drop inside the window (MAE)" in reply
    # The chart Tara loads is the study she described (the live turn loaded 11 PE+0 years).
    assert command["actions"] == [{"type": "set_view", "spec": {
        "symbol": "AAPL", "market": "2", "entry_date": "2026-11-17", "days_out": 45,
        "years": 20, "pe_cycle": "cons"}}]


def test_study_honors_cycle_and_named_index(engine):
    command = ask("How has the S&P 500 historically performed from November through April "
                  "during midterm election years?")
    call = engine["chart"][0]
    assert (call["market"], call["symbol"], call["entry"], call["days"], call["years"]) == (
        "5", "SPX", "2026-11-01", 181, "pe2-24")
    assert "midterm years (PE+2)" in text_of(command)
    assert command["actions"][0]["spec"]["pe_cycle"] == "pe2"


def test_study_reports_the_engine_direction_and_effective_dates(engine):
    command = ask("Analyze AAPL's historical return from January 1 to March 31 over the last 15 years.")
    call = engine["chart"][0]
    assert (call["entry"], call["days"], call["years"]) == ("2026-01-01", 90, "15")
    payload = chart_payload(call)
    reply = text_of(command)
    assert payload["stats"]["Trade Dir"] == "short"
    assert "short-direction pattern" in reply and "fell in %s of" % payload["stats"]["Num Winners"] in reply
    # The engine moves a Jan 1 entry to Jan 2; the action follows the engine, not the request.
    assert command["actions"][0]["spec"]["entry_date"] == payload["request"]["entry_date"] == "2026-01-02"


@pytest.mark.parametrize("message,expected", [
    ("from now to year end", ("2026-11-17", "2026-12-31")),
    ("for the 4th quarter", ("2026-10-01", "2026-12-31")),
    ("in Q1", ("2026-01-01", "2026-03-31")),
    ("from November through April", ("2026-11-01", "2027-04-30")),
    ("from Mid Oct till the end of the year", ("2026-10-15", "2026-12-31")),
    ("from January 1 to March 31", ("2026-01-01", "2026-03-31")),
    ("in the first two weeks of January", ("2026-01-01", "2026-01-14")),
    ("during December", ("2026-12-01", "2026-12-31")),
    ("over the next 30 days", ("2026-11-17", "2026-12-16")),
    ("between Sept 27 and July 18", ("2026-09-27", "2027-07-18")),
])
def test_period_parsing(message, expected):
    start, end, _label = research._parse_period("analyze AAPL " + message, TODAY)
    assert (start.isoformat(), end.isoformat()) == expected


def test_company_names_resolve_only_on_an_exact_engine_name(engine):
    found = research._find_securities("analyze apple historic return from now to year end", "t")
    assert [item["symbol"] for item in found] == ["AAPL"]     # not APLE, and "now" is not DNOW


# ---------------------------------------------------------------------------
# 4. Same-window comparison
# ---------------------------------------------------------------------------

def test_sector_etf_comparison_answers_both_sides(engine):
    command = ask("compare the seasonal performance of technology and utilities ETFs for the 4th quarter")
    assert command["trace"]["symbols"] == ["XLK", "XLU"]
    assert [(c["symbol"], c["market"], c["entry"], c["days"]) for c in engine["chart"]] == [
        ("XLK", "11", "2026-10-01", 92), ("XLU", "11", "2026-10-01", 92)]
    # Report mode: one direction and the same completed years for every symbol.
    assert all(c["params"] == {"comparison_direction": "long", "report_completed_years": "10"}
               for c in engine["chart"])
    reply = text_of(command)
    for call in engine["chart"]:
        stats = chart_payload(call)["stats"]
        assert "%s (" % call["symbol"] in reply
        assert "up in %s of 10 years" % stats["Num Winners"] in reply
        assert "Sharpe %s" % stats["Sharpe Ratio"] in reply
    assert "Higher average return: XLK" in reply
    assert "same 10 completed consecutive years (2016-2025)" in reply
    assert command["actions"][0]["spec"]["symbol"] == "XLK"


def test_named_tickers_define_the_comparison_and_a_sector_mismatch_is_explained(engine):
    command = ask("compare the seasonal performance of technology and utilities ETFs for the "
                  "4th quarter XLK and XLF")
    assert command["trace"]["symbols"] == ["XLK", "XLF"]
    reply = text_of(command)
    assert "XLK vs XLF" in reply
    assert "XLF is the Financials sector ETF; the Utilities sector ETF is XLU" in reply
    assert "up in 9 of 10 years" in reply


def test_comparison_uses_the_lookback_all_symbols_share(engine):
    command = ask("show me what the Eurusd and gbpusd tend to do the best from Mid Oct till the "
                  "end of the year in a 30 year view window")
    assert command["trace"]["symbols"] == ["EURUSD", "GBPUSD"]
    assert all(c["years"] == "23" and c["params"]["report_completed_years"] == "23"
               for c in engine["chart"])
    assert "You asked for 30 years" in text_of(command)
    assert "same 23 completed" in text_of(command)


def test_comparison_with_the_loaded_pattern_uses_its_window_and_lookback(engine):
    command = ask("compare MSFT with the current loaded pattern", LOADED_AAPL)
    assert command["trace"]["symbols"] == ["MSFT", "AAPL"]
    assert {(c["entry"], c["days"], c["years"]) for c in engine["chart"]} == {("2026-11-17", 45, "20")}


def test_comparison_without_dates_uses_a_stated_default_window(engine):
    # TW-TASK-0033: a comparison with no dates used to stop and ask which dates. It now
    # runs on a stated default (the next 30 calendar days when nothing is loaded) and
    # says so, so the user gets an answer and can still name another window.
    command = ask("compare XLK vs XLF")
    # The replay fixture holds no 30-day XLK/XLF study, so the command itself falls back
    # to the normal chat path; what this pins is the study the engine was ASKED for.
    assert command is None or "Which dates should I compare" not in command["reply"]
    assert {(c["symbol"], c["entry"], c["days"]) for c in engine["chart"]} == {
        ("XLK", "2026-11-17", 30), ("XLF", "2026-11-17", 30)}


def test_comparison_without_dates_prefers_the_loaded_window(engine):
    view = {"symbol": "MSFT", "market": "2", "start_date": "2026-11-17", "days_out": 45,
            "years": "20", "pe_cycle": "cons"}
    command = ask("compare AAPL and MSFT", view=view)
    assert "You did not name dates" in command["reply"]
    assert "window loaded in the Wave Viewer" in command["reply"]
    assert {(c["entry"], c["days"]) for c in engine["chart"]} == {("2026-11-17", 45)}


@pytest.mark.parametrize("message, expected", [
    ("screen the wilshire 5000 on 15y, min 13 of 15", 15),
    ("use 20 years for this", 20),
    ("how does it look over the last 25 years", 25),
    ("AAPL 15 yrs", 15),
    ("a 12-year lookback please", 12),
    ("what happened 2 days ago", None),
])
def test_lookback_wordings_are_read(message, expected):
    assert research._lookback_years(message) == expected


def test_unequal_cohorts_are_never_compared(engine, monkeypatch):
    original = research._engine_chart

    def skewed(market, symbol, *args, **params):
        status, payload = original(market, symbol, *args, **params)
        if symbol == "XLU" and payload:
            payload = dict(payload, ChartData4=[dict(row, year=row["year"] - 1)
                                                for row in payload["ChartData4"]])
        return status, payload

    monkeypatch.setattr(research, "_engine_chart", skewed)
    command = ask("compare the seasonal performance of technology and utilities ETFs for the 4th quarter")
    assert "would not be fair" in command["reply"] and command["actions"] == []


# ---------------------------------------------------------------------------
# 5. Date of a pattern's low / high
# ---------------------------------------------------------------------------

def test_hundred_year_pattern_latest_bottom_comes_from_engine_low_dates(engine):
    command = ask("what's the latest date that the 100 year pattern has bottomed")
    assert engine["chart"] == [{"market": "5", "symbol": "SPX", "entry": "2026-09-27",
                                "days": 295, "years": "pe2-24",
                                "params": {"excursion_dates": "1"}}]
    rows = [row for row in chart_payload(engine["chart"][0])["ChartData4"] if row["completed"]]
    assert len(rows) == 24
    latest_row = next(row for row in rows if row["year"] == 1930)
    assert latest_row["low_date"] == "1931-06-02"
    reply = text_of(command)
    assert "The latest the pattern has bottomed: 1930 cycle: Jun 2, 1931, calendar day 249 of 295" in reply
    assert "Across 24 completed cycles" in reply
    recent = next(row for row in rows if row["year"] == 2022)
    assert recent["low_date"] == "2022-10-13" and "Oct 13, 2022" in reply
    assert "still running" in reply and "excluded from the completed record" in reply
    # Every date printed is a recorded engine low date.
    engine_dates = {row["low_date"] for row in chart_payload(engine["chart"][0])["ChartData4"]}
    for month, day, year in re.findall(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", reply):
        printed = datetime.datetime.strptime("%s %s %s" % (month, day, year), "%b %d %Y").date()
        assert printed.isoformat() in engine_dates
    assert command["actions"][0]["spec"] == {
        "symbol": "SPX", "market": "5", "entry_date": "2026-09-27", "days_out": 295,
        "years": 24, "pe_cycle": "pe2"}


@pytest.mark.parametrize("message,needle", [
    ("when does this pattern usually bottom?", "AAPL loaded pattern: date of the low"),
    ("what is the earliest date the loaded pattern has hit its low", "The earliest the pattern has bottomed"),
])
def test_loaded_pattern_low_dates(engine, message, needle):
    command = ask(message, LOADED_AAPL)
    call = engine["chart"][0]
    assert (call["symbol"], call["entry"], call["days"], call["years"]) == ("AAPL", "2026-11-17", 45, "20")
    assert call["params"] == {"excursion_dates": "1"}
    assert needle in text_of(command)


def test_missing_engine_dates_are_stated_not_invented(engine, monkeypatch):
    original = research._engine_chart

    def without_dates(*args, **params):
        status, payload = original(*args, **params)
        rows = [{k: v for k, v in row.items() if not k.endswith("_date")}
                for row in payload["ChartData4"]]
        return status, dict(payload, ChartData4=rows)

    monkeypatch.setattr(research, "_engine_chart", without_dates)
    command = ask("what's the latest date that the 100 year pattern has bottomed")
    assert "the date of that low is not available" in command["reply"]
    assert not re.search(r"\b(?:19|20)\d{2}\b", text_of(command))
    assert command["actions"] == []


# ---------------------------------------------------------------------------
# Wiring: the chat endpoint answers these before any model or legacy shortcut
# ---------------------------------------------------------------------------

@pytest.fixture
def chat_app(tmp_path, monkeypatch, engine):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "tara-test-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    app.register_blueprint(chatbot.chatbot_bp, url_prefix="/chatbot")
    monkeypatch.setattr(chatbot, "ACTION_AUDIT_LOG", str(tmp_path / "tara-actions.jsonl"))
    monkeypatch.setattr(chatbot, "QUESTION_LOG", str(tmp_path / "tara-questions.jsonl"))
    monkeypatch.setattr(tara_gateway, "_market_today", lambda: TODAY)
    for name in ("run_chat_with_openai_tools", "run_chat_with_tools", "send_openai_messages",
                 "send_claude_messages"):
        monkeypatch.setattr(chatbot, name, lambda *args, **kwargs: pytest.fail(
            "an engine-answerable research request reached the model"))
    return app


def _post(app, message, view=None):
    token = jwt.encode({"user": "research-user", "user_level": "6", "aud": "tw2-appserver",
                        "iss": "tw2-web", "exp": int(time.time()) + 300},
                       app.config["SECRET_KEY"], algorithm="HS256")
    response = app.test_client().post("/chatbot/chat", json={
        "token": token, "message": message, "history": [{"role": "user", "content": message}],
        "wave_viewer": view or {}, "opportunities": [], "opp_table_market": "2"})
    assert response.status_code == 200
    return response.get_json()


@pytest.mark.parametrize("message,needle,action_symbol", [
    ("find s&p500 stocks entering seasonaly bearish patterns this week", "10. <b>", None),
    ("which S&P500 stocks have the highest seasonal win rate over the next 10 days",
     "Top 10 by win rate", None),
    ("analyze apple historic return from now to year end over the last 20 years",
     "20 completed consecutive years", "AAPL"),
    ("compare the seasonal performance of technology and utilities ETFs for the 4th quarter",
     "<b>XLU</b>", "XLK"),
    ("what's the latest date that the 100 year pattern has bottomed", "Jun 2, 1931", "SPX"),
])
def test_chat_endpoint_answers_the_five_failed_questions(chat_app, message, needle, action_symbol):
    payload = _post(chat_app, message)
    assert needle in payload["reply"]
    symbols = [action["spec"].get("symbol") for action in payload["actions"]]
    assert symbols == ([action_symbol] if action_symbol else [])


def test_named_pattern_summary_still_loads_for_a_plain_question(chat_app):
    payload = _post(chat_app, "what's 100 year pattern")
    assert "Loaded The 100-Year Pattern" in payload["reply"]


@pytest.mark.parametrize("message", [
    "what should I buy in the S&P 500 this week?",
    "I have $5000, which S&P 500 stocks should I buy this week?",
])
def test_suitability_questions_are_not_turned_into_screens(engine, message):
    intent = tara_gateway.classify_investor_intent(message)
    assert ask(message, investor_intent=intent) is None
    assert engine["opplist"] == []


# ---------------------------------------------------------------------------
# Engine contract: the opt-in ChartData4 excursion dates
# ---------------------------------------------------------------------------

def test_recorded_excursion_rows_keep_the_legacy_values_and_add_dates():
    payload = FIXTURE["levels"]["L6"]["chart"]["5|SPX|2026-09-27|295|pe2-24|excursion_dates=1"]["payload"]
    for row in payload["ChartData4"]:
        assert len(row["pct"].split(",")) == 3
        assert row["entry_trade_date"] <= row["low_date"] <= row["exit_trade_date"]
        assert row["entry_trade_date"] <= row["high_date"] <= row["exit_trade_date"]
    assert payload["stats"]["Num Winners"] == "23" and payload["stats"]["Num Losers"] == "1"


# ===========================================================================
# Independent-review regressions (2026-11-17): silently wrong answers
# ===========================================================================

NOT_ENGINE_ANSWERABLE = [
    # B1 - ordinary English words are not company names
    "how has healthcare performed in Q4",
    "analyze information technology returns in December",
    "how has liquidity affected returns in january",
    "what are the historical returns for capital goods in Q1",
    "analyze progressive returns in the first half of january",
    "how does the southern hemisphere summer affect returns in january",
    "what was news in March for apple",
    "what is the return policy? I signed up in March",
    "how do I change the date range from January to March?",
    # B2 - upper-case words and currency codes are not tickers
    "analyze IT sector performance in Q4",
    "show ME the best performing stocks for Q4",
    "How has ALL performed in November through January",
    "compare IT and ALL for Q4",
    # B3 / S3 - a date the screen or study cannot honor is never answered for "today"
    "which S&P 500 stocks historically rise in January",
    "which S&P 500 stocks are bullish this fall",
    "best S&P 500 seasonal patterns for the fall, top 5",
    "which S&P 500 stocks are bullish in Q1",
    "which S&P 500 stocks were bullish in 2022",
    "find S&P 500 stocks with bullish patterns starting next Friday",
    "How did AAPL perform in December 2022?",
    "how did the market perform in Q4 2018",
    "how did the dow perform in 2008?",
    # B4 - negated, two-sided or inverse direction requests
    "which dow stocks are not bearish this week",
    "top 5 strongest nasdaq patterns but exclude short ones",
    "which S&P 500 stocks have strong patterns this week, nothing weak",
    "which S&P 500 stocks rarely fall this week (highest win rate)",
    "which s&p 500 stocks drop the least this week historically",
    "which s&p 500 stocks tend to fall after a strong rise this week",
    "which S&P 500 stocks have the lowest win rate this week",
    "which dow stocks have the worst sharpe this week",
    "show bullish and bearish S&P 500 patterns this week",
    # S4 - "high"/"low" that is not a WHEN question
    "What is the latest price for this chart - is it near its high?",
    "usually how high does this pattern go?",
    "what dates does the 100 year pattern cover, and why is 1930 so low",
    "how long does the 100-year pattern last and how high is its win rate",
    "when did this pattern have its highest return year",
    "what is the lowest win rate you show for this pattern?",
    "why is the low so deep in 2008 for this pattern?",
    "is the 100 year pattern bullish right now?",
    "when does the 100-year pattern start?",
    # S5 / S6 - filters the detector cannot apply
    "which s&p 500 stocks have 1-day holds with win rate above 90% today",
    "S&P 500 stocks bullish this week in midterm years",
    "which S&P 500 stocks are bullish this week in midterm years",
    # sector-in-index and off-topic screens
    "which sector ETFs are bullish this week",
    "tell me about tech stocks in the nasdaq",
    "find S&P 500 stocks with the highest AI score this week",
    "which stocks have earnings this week",
    # general product questions
    "what is a sharpe ratio?", "what does win rate mean?", "how do I compare two symbols?",
    "compare plans: analyst vs strategist", "what's the difference between long and short patterns",
    "how do I filter the table by win rate of at least 90%", "rank them by win rate",
    "what does a win rate of 90% mean, at minimum 5 years?",
    "why is the minimum 10 years for the top 10 list",
    "how do the returns in this chart compare to the previous one",
    "compare this pattern to last year",
    "general question: how do returns in election years compare against midterm years for SPX",
]


@pytest.mark.parametrize("message", NOT_ENGINE_ANSWERABLE)
def test_review_probes_that_must_not_be_answered_here(engine, message):
    assert ask(message, LOADED_AAPL, table_market="2") is None
    assert engine["opplist"] == [] and engine["chart"] == []


def test_common_words_never_resolve_to_companies(engine):
    """B1: 'happen', 'people', 'post', 'southern' are engine security names, not requests."""

    for message, expected in [
        ("what tends to happen to apple in December historically", ["AAPL"]),
        ("what do people usually see for AAPL returns in December", ["AAPL"]),
        ("how does the s&p 500 perform in post-election years from now to year end", ["SPX"]),
        ("how does the southern company perform in Q4", []),
        ("analyze home depot from now to year end", []),      # resolvable name, not in fixture resolve
    ]:
        found = [item["symbol"] for item in research._find_securities(message, "t")]
        assert found == expected, (message, found)
    index = research._company_index("t")
    assert "home depot" in index and "american express" in index
    assert all(" " in name for name in index)                 # one-word names are never indexed


def test_engine_name_list_is_fetched_once_per_process(engine):
    for _ in range(3):
        research._find_securities("analyze coca-cola returns from now to year end", "t")
    assert engine["names"] == 1


def test_post_election_question_is_one_study_not_a_comparison(engine):
    command = ask("how does the s&p 500 perform in post-election years from now to year end")
    assert command["trace"] == {"event": "research_window_study", "symbol": "SPX"}
    assert [(c["symbol"], c["years"]) for c in engine["chart"]] == [("SPX", "pe1-25")]
    assert "post-election years (PE+1)" in text_of(command)


@pytest.mark.parametrize("message,expected", [
    ("how has EUR/USD performed in Q1", ["EURUSD"]),
    ("how has EUR-USD performed in Q1", ["EURUSD"]),
    ("compare eurusd and GBP/USD in Q1", ["EURUSD", "GBPUSD"]),
    ("is NOW a good time to analyze gold from now to year end", ["GC"]),
    ("how has $NOW stock performed in Q4", []),               # marked ticker, not in fixture resolve
])
def test_currency_pairs_and_english_tickers(engine, message, expected):
    assert [item["symbol"] for item in research._find_securities(message, "t")] == expected


def test_marked_english_word_tickers_are_still_tickers():
    assert research._explicit_tickers("how has $NOW performed") == ["NOW"]
    assert research._explicit_tickers("how has ALL stock performed") == ["ALL"]
    assert research._explicit_tickers("is NOW a good time for IT or ALL of it") == []
    assert research._explicit_tickers("EUR/USD and USD in Q1") == []
    assert research._explicit_tickers("Find SP500 and NASDAQ100 stocks") == []
    assert research._explicit_tickers("compare AAPL and MSFT") == ["AAPL", "MSFT"]


def test_eurusd_study_is_one_instrument(engine):
    command = ask("how has EUR/USD performed in Q1")
    assert command["trace"] == {"event": "research_window_study", "symbol": "EURUSD"}
    assert {call["symbol"] for call in engine["chart"]} == {"EURUSD"}


def test_explicit_entry_date_is_screened_for_that_date(engine):
    command = ask("which nasdaq stocks have bearish patterns starting Dec 1")
    assert {call["day"].isoformat() for call in engine["opplist"]} == {"2026-12-01"}
    assert all("starts Tue Dec 1" in line for line in ranked_lines(command))


@pytest.mark.parametrize("message,first,last", [
    ("which S&P 500 stocks historically rise in December", "2026-12-01", "2026-12-31"),
    ("Which ETFs are bullish next month?", "2026-12-01", "2026-12-31"),
    ("which nasdaq stocks have bearish patterns starting Dec 1", "2026-12-01", "2026-12-01"),
    ("which S&P 500 stocks are bullish in November", "2026-11-17", "2026-11-30"),
])
def test_screen_honors_named_months_and_dates(message, first, last):
    request = research._screen_request(message, TODAY, None)
    assert (request["first"].isoformat(), request["last"].isoformat()) == (first, last)


@pytest.mark.parametrize("today,phrase,first,last,tables", [
    # Tuesday: only the days still ahead
    ("2026-11-17", "this week", "2026-11-17", "2026-11-22", ["17", "18", "19", "20"]),
    # Friday: one session left
    ("2026-11-20", "this week", "2026-11-20", "2026-11-22", ["20"]),
    # Saturday / Sunday: the week about to start
    ("2026-11-21", "this week", "2026-11-23", "2026-11-29", ["23", "24", "25", "26", "27"]),
    ("2026-11-22", "this week", "2026-11-23", "2026-11-29", ["23", "24", "25", "26", "27"]),
    ("2026-11-20", "next week", "2026-11-23", "2026-11-29", ["23", "24", "25", "26", "27"]),
    ("2026-11-20", "in the next 5 trading days", "2026-11-20", "2026-11-26",
     ["20", "23", "24", "25", "26"]),
    ("2026-12-28", "in the next 10 days", "2026-12-28", "2026-12-31", ["28", "29", "30", "31"]),
])
def test_entry_windows_on_fridays_weekends_and_year_end(today, phrase, first, last, tables):
    day = datetime.date.fromisoformat(today)
    request = research._screen_request("which S&P 500 stocks start bullish patterns " + phrase, day, None)
    assert (request["first"].isoformat(), request["last"].isoformat()) == (first, last)
    assert [d.strftime("%d") for d in research._request_days(request["first"], request["last"])] == tables


def test_next_week_and_next_month_past_year_end_are_not_screened():
    for today, phrase in [("2026-12-28", "next week"), ("2026-12-28", "next month")]:
        assert research._screen_request(
            "which S&P 500 stocks start bullish patterns " + phrase,
            datetime.date.fromisoformat(today), None) is None


@pytest.mark.parametrize("message,direction", [
    ("give me a short list of bullish S&P 500 stocks this week", "long"),
    ("show bullish s&p 500 patterns with a short holding period this week", "long"),
    ("find long-term bullish s&p 500 patterns this week", "long"),
    ("which S&P 500 stocks historically fall this week", "short"),
    ("find s&p 500 shorts with win rate over 85% this week", "short"),
    ("which S&P 500 stocks are seasonally weakest this week", "short"),
    ("top 5 strongest S&P 500 patterns today", "long"),
])
def test_direction_is_read_from_trade_words_only(message, direction):
    assert research._screen_request(message, TODAY, None)["direction"] == direction


def test_one_day_hold_is_never_sent_as_an_unfiltered_range():
    assert research._screen_request(
        "which s&p 500 stocks have 1-day holds today", TODAY, None) is None
    request = research._screen_request("which s&p 500 stocks have 2-day holds today", TODAY, None)
    assert request["hold"] == (2, 2)


def test_two_day_hold_range_reaches_the_detector(engine):
    ask("which s&p 500 stocks have 2-day holds today")
    assert {call["day_range"] for call in engine["opplist"]} == {"1-1"}


@pytest.mark.parametrize("message", [
    "which dow stocks have the highest win rate among bearish patterns next month over the last 60 years",
    "which S&P 500 stocks have the highest win rate this week over the last 30 years",
    "which S&P500 stocks have the highest seasonal win rate over the next 10 days",
    "rank S&P 500 stocks by win rate for the next 31 days",
])
def test_fanout_is_bounded(engine, message):
    """S2: one message reads a bounded number of bands and forty engine responses in total."""

    ask(message)
    assert len({call["year2"] for call in engine["opplist"]}) <= research._MAX_TIERS == 6
    assert len(engine["opplist"]) + len(engine["chart"]) <= research._MAX_ENGINE_CALLS == 40


def test_engine_reads_share_a_process_wide_limit():
    assert research._ENGINE_SLOTS._initial_value == research._FANOUT_WORKERS <= 3


def test_average_return_ranking_is_labelled_honestly(engine):
    command = ask("rank S&P 500 stocks by average return today")
    assert "by average return (comparing each stock's highest-Sharpe window)" in text_of(command)


def test_advice_wording_gets_a_boundary_before_the_research_list(engine):
    message = "what stocks should I buy this week in the S&P 500 with the highest win rate"
    command = ask(message, investor_intent=tara_gateway.classify_investor_intent(message))
    if command is not None:           # the investor funnel may own the turn instead
        reply = text_of(command)
        assert "TradeWave cannot tell you what to buy, sell, short or avoid" in reply
        assert reply.index("TradeWave cannot tell you") < reply.index("1. ")
    assert research._ADVICE_RE.search(message)
    assert research._ADVICE_RE.search("which etfs should I avoid this week")
    assert not research._ADVICE_RE.search("which S&P 500 stocks are bullish this week")


# --- B5 / S1: plan limits ---------------------------------------------------

def test_free_plan_screen_is_limited_to_today_and_says_so(engine):
    command = ask("find dow stocks entering bullish patterns this week", token=plan_token(1),
                  years_cap=10)
    assert {call["day"].isoformat() for call in engine["opplist"]} == {"2026-11-17"}
    lines = ranked_lines(command)
    assert 1 <= len(lines) <= 5 and all("starts Tue Nov 17" in line for line in lines)
    reply = text_of(command)
    assert "today's entries only" in reply and "top 5 patterns per day" in reply
    assert command["trace"]["plan_limited"] is True
    by_symbol = {call["symbol"]: call for call in engine["chart"]}
    for row in command["rows"]:
        echo = chart_payload(by_symbol[row["symbol"]], plan_token(1))["request"]
        assert (echo["entry_date"], echo["days_out"]) == (row["date"], row["days_out"])


def test_free_plan_never_reports_a_truncated_table_as_none_found(engine):
    command = ask("find dow stocks entering bearish patterns this week", token=plan_token(1),
                  years_cap=10)
    reply = text_of(command)
    assert "detector found no" not in reply
    assert "I can't give a full Dow 30 bearish screen on this plan" in reply
    assert "says nothing about the full market" in reply


def test_market_outside_the_free_plan_is_refused(engine):
    command = ask("find s&p 500 stocks entering bearish patterns this week", token=plan_token(1))
    assert "outside this account's available markets" in command["reply"]


def test_date_locked_study_is_refused_not_mislabelled(engine):
    """The engine answers a free plan's Q1 request with today's window; never print it as Q1."""

    command = ask("analyze apple historic return in Q1 over the last 20 years",
                  token=plan_token(1), years_cap=10)
    reply = text_of(command)
    assert "I can't run that AAPL study on this plan" in reply
    assert "profitable in" not in reply and command["actions"] == []
    recorded = FIXTURE["levels"]["L1"]["chart"]
    echoed = [recorded[key]["payload"]["request"]["entry_date"] for key in recorded
              if key.startswith("0|AAPL|2026-01-01|90|") and recorded[key]["payload"]]
    assert "2026-11-17" in echoed                               # what the engine really computed


def test_screen_rows_whose_engine_echo_differs_are_dropped(engine, monkeypatch):
    original = research._engine_chart

    def relocated(market, symbol, entry_date, days_out, years_value, token, **params):
        status, payload = original(market, symbol, entry_date, days_out, years_value, token, **params)
        if payload and symbol == "WELL":
            payload = dict(payload, request=dict(payload["request"], entry_date="2026-11-17"))
        return status, payload

    monkeypatch.setattr(research, "_engine_chart", relocated)
    command = ask("find s&p500 stocks entering seasonaly bearish patterns this week")
    assert "WELL" not in [row["symbol"] for row in command["rows"]]
    assert "could not be verified on the dates listed" in text_of(command)


def test_study_with_a_shifted_engine_window_is_refused(engine, monkeypatch):
    original = research._engine_chart

    def shifted(*args, **params):
        status, payload = original(*args, **params)
        return status, dict(payload, request=dict(payload["request"], days_out=30))

    monkeypatch.setattr(research, "_engine_chart", shifted)
    command = ask("analyze apple historic return from now to year end over the last 20 years")
    assert "I can't run that AAPL study on this plan" in command["reply"]
    assert command["actions"] == []


def test_capped_plan_screen_prints_the_effective_lookback(engine):
    command = ask("which s&p 500 stocks have the highest win rate over the last 20 years this week",
                  token=plan_token(2), years_cap=15)
    assert {call["year1"] for call in engine["opplist"]} == {15}
    assert {call["years"] for call in engine["chart"]} == {"15"}
    reply = text_of(command)
    assert "over a 15-year lookback" in reply and "20-year lookback" not in reply
    assert "capped at 15 years" in reply
    assert all(re.search(r"of 15 years", line) for line in ranked_lines(command))


def test_capped_plan_study_states_the_cap(engine):
    command = ask("analyze apple historic return from now to year end over the last 20 years",
                  token=plan_token(2), years_cap=15)
    assert [call["years"] for call in engine["chart"]] == ["15"]
    reply = text_of(command)
    assert "your plan's lookback is capped at 15" in reply
    assert "15 completed consecutive years" in reply
    assert command["actions"][0]["spec"]["years"] == 15


def test_years_cap_is_read_from_the_token_when_the_caller_passes_none(engine):
    command = ask("which s&p 500 stocks have the highest win rate over the last 20 years this week",
                  token=plan_token(2))
    assert {call["year1"] for call in engine["opplist"]} == {15}
    assert "over a 15-year lookback" in text_of(command)


def test_free_plan_can_still_ask_about_the_public_hundred_year_pattern(engine):
    command = ask("what's the latest date that the 100 year pattern has bottomed", token=plan_token(1))
    assert "Jun 2, 1931" in text_of(command)


def test_engine_failure_falls_back_to_the_model_path(engine, monkeypatch):
    monkeypatch.setattr(research, "_engine_chart", lambda *args, **params: (500, None))
    assert ask("analyze apple historic return from now to year end over the last 20 years") is None
    assert ask("what's the latest date that the 100 year pattern has bottomed") is None


# --- S8 / S9: engine day numbers and direction-aware labels -------------------

def test_day_numbers_and_dates_come_from_the_engine(engine):
    command = ask("what's the latest date that the 100 year pattern has bottomed")
    rows = {row["year"]: row for row in chart_payload(engine["chart"][0])["ChartData4"]}
    assert rows[1930]["low_day"] == 249 and rows[2022]["low_day"] == 17
    reply = text_of(command)
    assert "calendar day %d of 295" % rows[1930]["low_day"] in reply
    assert "calendar day %d of 295" % rows[2022]["low_day"] in reply
    # No frequency or session-count statistic is derived in the chatbot.
    assert "within the first 30" not in reply and "completed cycles the low" not in reply
    for item in command["dated"]:
        assert item["day"] == rows[item["year"]]["low_day"]


def test_missing_engine_day_numbers_are_not_recomputed(engine, monkeypatch):
    original = research._engine_chart

    def without_days(*args, **params):
        status, payload = original(*args, **params)
        rows = [{k: v for k, v in row.items() if not k.endswith("_day")}
                for row in payload["ChartData4"]]
        return status, dict(payload, ChartData4=rows)

    monkeypatch.setattr(research, "_engine_chart", without_days)
    command = ask("what's the latest date that the 100 year pattern has bottomed")
    assert "is not available in this response" in command["reply"]
    assert not re.search(r"calendar day \d+", command["reply"])


def test_short_pattern_labels_follow_the_engine_trade_direction(engine):
    command = ask("Analyze AAPL's historical return from January 1 to March 31 over the last 15 years.")
    assert chart_payload(engine["chart"][0])["stats"]["Trade Dir"] == "short"
    reply = text_of(command)
    assert "Largest rise inside the window (MAE)" in reply
    assert "Deepest drop inside the window (MFE)" in reply


@pytest.mark.parametrize("message,kind", [
    ("what's the latest date that the 100 year pattern has bottomed", "low"),
    ("when does the 100-year pattern usually peak?", "high"),
    ("when was the high for this chart?", "high"),
    ("when does this pattern usually bottom?", "low"),
    ("what is the earliest date the loaded pattern has hit its low", "low"),
    ("on what date did the 100 year pattern hit its low in the latest cycle", "low"),
])
def test_when_questions_about_an_extreme_are_recognized(message, kind):
    assert research._extreme_request(message) == kind


# ---------------------------------------------------------------------------
# Engine: default ChartData4 output is unchanged without excursion_dates
# ---------------------------------------------------------------------------

@pytest.fixture
def chart_engine(monkeypatch):
    """The real ChartData4 route over a small synthetic price history."""

    import pandas as pd
    import appserver as appserver_module

    rows, price = [], 100.0
    day = datetime.date(2012, 1, 2)
    step = 0
    while day <= datetime.date(2026, 11, 16):
        if day.weekday() < 5:
            step += 1
            price = round(price * (1 + (((step * 37) % 23) - 11) / 1000.0), 4)
            rows.append({"date": day.isoformat(), "open": price, "high": round(price * 1.01, 4),
                         "low": round(price * 0.99, 4), "close": price, "adj_factor": 1.0,
                         "volume": 1000 + step})
        day += datetime.timedelta(days=1)
    frame = pd.DataFrame(rows)

    class _Redis:
        def __init__(self):
            self.values = {}

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value):
            self.values[key] = value

        def expire(self, key, seconds):
            return True

    redis = _Redis()
    monkeypatch.setattr(appserver_module, "redis_client", redis)
    monkeypatch.setattr(appserver_module, "_singleflight_cache_values",
                        lambda keys, wait_seconds=10: [redis.get(key) for key in keys])
    monkeypatch.setattr(appserver_module, "get_symbol_csv", lambda symbol, exchange: frame.copy())
    monkeypatch.setattr(appserver_module, "stockscore_with_availability",
                        lambda *args: (0, 0, 0, 0, False))
    monkeypatch.setattr(appserver_module, "update_activity_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(appserver_module, "get_geo_from_token", lambda token: (0, "u", "", "US", "0"))
    monkeypatch.setattr(appserver_module, "get_earnings_dates", lambda symbol: None)
    monkeypatch.setattr(appserver_module, "_market_today", lambda: datetime.date(2026, 11, 17))
    monkeypatch.setattr(appserver_module.limiter, "enabled", False)
    token = jwt.encode({"user": "engine-test", "user_level": "6", "aud": "tw2-appserver",
                        "iss": "tw2-web", "exp": int(time.time()) + 300},
                       appserver_module.app.config["SECRET_KEY"], algorithm="HS256")
    client = appserver_module.app.test_client()

    def get(path, **params):
        params["token"] = token
        response = client.get(path, query_string=params)
        assert response.status_code == 200, response.get_data(as_text=True)[:300]
        return response.get_data(), response.get_json(), redis

    return get


CHART_STUDIES = ["/ChartData4/2/2026-03-03/TEST/20/10", "/ChartData4/2/2026-11-17/TEST/44/12",
                 "/ChartData4/2/2026-09-27/TEST/294/pe2-3"]


@pytest.mark.parametrize("path", CHART_STUDIES)
def test_default_chartdata4_output_is_byte_identical_without_excursion_dates(chart_engine, path):
    baseline_bytes, baseline, redis = chart_engine(path)
    assert set(baseline["ChartData4"][0]) == {"year", "pct", "price", "completed"}
    default_keys = set(redis.values)

    dated_bytes, dated, _ = chart_engine(path, excursion_dates="1")
    # Opt-in rows: the legacy fields are untouched, four dates and two day numbers are added.
    assert dated["stats"] == baseline["stats"]
    for plain, rich in zip(baseline["ChartData4"], dated["ChartData4"]):
        assert {key: rich[key] for key in plain} == plain
    completed = [row for row in dated["ChartData4"] if row.get("completed")]
    assert completed
    for row in completed:
        assert set(row) - {"year", "pct", "price", "completed"} == {
            "entry_trade_date", "exit_trade_date", "high_date", "low_date", "high_day", "low_day"}
        assert row["entry_trade_date"] <= row["low_date"] <= row["exit_trade_date"]
        assert row["entry_trade_date"] <= row["high_date"] <= row["exit_trade_date"]
        assert row["low_day"] >= 1 and row["high_day"] >= 1
    # The opt-in response is cached under its own key and never replaces the default one.
    assert any(key.endswith("_excursion_dates") for key in set(redis.values) - default_keys)

    again_bytes, again, _ = chart_engine(path)                  # served from the default cache key
    assert again_bytes == baseline_bytes
    redis.values.clear()
    fresh_bytes, _fresh, _ = chart_engine(path)                 # recomputed after the opt-in call
    assert fresh_bytes == baseline_bytes


def test_excursion_day_number_counts_the_window_start_as_day_one(chart_engine):
    _bytes, dated, _ = chart_engine("/ChartData4/2/2026-03-03/TEST/20/10", excursion_dates="1")
    for row in dated["ChartData4"]:
        if not row.get("completed"):
            continue
        start = datetime.date(row["year"], 3, 3)
        assert row["low_day"] == (datetime.date.fromisoformat(row["low_date"]) - start).days + 1
        assert row["high_day"] == (datetime.date.fromisoformat(row["high_date"]) - start).days + 1



# ===========================================================================
# Re-review regressions (2026-11-17, second round)
# ===========================================================================

@pytest.mark.parametrize("message", [
    "which S&P 500 stocks go down this week historically",
    "which S&P 500 stocks have negative seasonal returns this week",
    "which S&P 500 stocks underperform this week seasonally",
    "which S&P 500 stocks historically sink this week",
    "which S&P 500 stocks tend to slide this week seasonally",
    "which S&P 500 stocks tank this week historically",
    "show me seasonal sell candidates in the S&P 500 this week",
])
def test_bearish_wording_outside_the_basic_vocabulary_is_a_short_screen(message):
    """R1: these used to return a bullish list."""

    request = research._screen_request(message, TODAY, None)
    assert request is not None and request["direction"] == "short", message


@pytest.mark.parametrize("message", [
    "what are the worst S&P 500 stocks seasonally this week",
    "which S&P 500 stocks do poorly this week seasonally",
    "which S&P 500 stocks are seasonal losers this week",
    "which S&P 500 stocks should be avoided this week seasonally",
    "which S&P 500 stocks are historically down this week",
    "which bullish S&P 500 stocks tend to sink this week",
])
def test_possibly_bearish_wording_never_defaults_to_a_bullish_list(engine, message):
    assert ask(message) is None
    assert engine["opplist"] == []


def _synthetic_band_engine(monkeypatch, rows_by_band):
    """A stand-in detector: which symbols each min-winning-years band lists (routing only)."""

    calls = []

    def opplist(market, day, year1, year2, day_range, token):
        calls.append((day.isoformat(), int(year1), int(year2)))
        return 200, [[day.isoformat(), symbol, "9", "Long", "1.00", 2.0]
                     for symbol in rows_by_band.get(int(year2), []) if day == TODAY]

    def chart(market, symbol, entry_date, days_out, years_value, token, **params):
        wins = max(band for band, symbols in rows_by_band.items()
                   if isinstance(band, int) and symbol in symbols)
        total = int(years_value)
        return 200, {
            "request": {"symbol": symbol, "entry_date": entry_date, "days_out": int(days_out),
                        "years": total, "pe_cycle": "cons"},
            "stats": {"Num Winners": str(wins), "Num Losers": str(total - wins),
                      "Percent Profitable": "%s%%" % rows_by_band["pct"][wins],
                      "Avg Profit - All": "2.0%", "Median Profit": "2.0%", "Sharpe Ratio": "1.0"},
            "ChartData4": []}

    monkeypatch.setattr(research, "_engine_opplist", opplist)
    monkeypatch.setattr(research, "_engine_chart", chart)
    return calls


def test_win_rate_ranking_reads_consecutive_bands_and_never_skips_one(monkeypatch):
    """R2: bands 30, 29, 24 were read, so a 27-of-30 name was missed below 25-of-30 names."""

    bands = {30: [], 29: ["AAA"], 28: ["AAA", "BBB"], 27: ["AAA", "BBB", "PEP"],
             24: ["AAA", "BBB", "PEP", "LOW1", "LOW2"],
             "pct": {29: "96.67", 28: "93.33", 27: "90.0", 24: "80.0"}}
    calls = _synthetic_band_engine(monkeypatch, bands)
    command = ask("which nasdaq stocks have the highest win rate this week over the last 30 years")
    read = sorted({band for _day, _year1, band in calls}, reverse=True)
    assert read == [30, 29, 28, 27, 26, 25], "bands must be consecutive from the strictest"
    symbols = [row["symbol"] for row in command["rows"]]
    assert symbols == ["AAA", "BBB", "PEP"]           # the 27-of-30 name is found, in order
    assert "LOW1" not in symbols                      # nothing below the last band read is ranked
    reply = text_of(command)
    assert "covers every pattern that won at least 25 of the last 30 years" in reply
    assert "strictest bands, which is as far as one screen reads" in reply
    assert "names with a lower record are not ranked here" in reply


def test_long_window_win_rate_ranking_discloses_its_single_band(monkeypatch):
    bands = {10: ["AAA"], 9: ["AAA", "BBB"], 8: ["AAA", "BBB", "CCC"],
             "pct": {10: "100.0", 9: "90.0", 8: "80.0"}}
    calls = _synthetic_band_engine(monkeypatch, bands)
    command = ask("rank S&P 500 stocks by win rate for the next 31 days")
    assert {band for _day, _year1, band in calls} == {10}
    assert [row["symbol"] for row in command["rows"]] == ["AAA"]
    reply = text_of(command)
    assert "covers every pattern that won at least 10 of the last 10 years" in reply
    assert "1 strictest band," in reply


def test_empty_strict_bands_are_not_reported_as_no_patterns_at_all(monkeypatch):
    bands = {8: ["AAA"], "pct": {8: "80.0"}}
    _synthetic_band_engine(monkeypatch, bands)
    command = ask("rank S&P 500 stocks by win rate for the next 31 days")
    reply = text_of(command)
    assert "won at least 10 of the last 10 years" in reply
    assert "ask for the best by Sharpe Ratio to include records down to 8 of 10" in reply


def test_win_rate_ranking_that_reaches_the_floor_needs_no_caveat(engine):
    command = ask("which S&P500 stocks have the highest seasonal win rate over the next 10 days")
    assert len(command["rows"]) == 10
    assert "as far as one screen reads" not in text_of(command)


@pytest.mark.parametrize("message,known,expected_calls", [
    ("compare the performance of F and GM in Q4", {"F", "GM"}, {"F", "GM"}),
    ("how has T performed vs VZ in december", {"T", "VZ"}, {"T", "VZ"}),
])
def test_one_letter_tickers_are_read_in_a_comparison(engine, monkeypatch, message, known, expected_calls):
    """R3: 'compare F and GM' answered for GM alone."""

    monkeypatch.setattr(tara_gateway, "_resolve_question_symbol",
                        lambda symbol, question, token, view=None: (
                            {"status": "ok", "symbol": symbol, "market": "2", "name": symbol}
                            if symbol in known else {"status": "not_found", "symbol": symbol}))
    monkeypatch.setattr(tara_gateway, "_symbol_max_available_years", lambda *args: 30)
    found = [item["symbol"] for item in research._find_securities(message, "t")]
    assert set(found) == known and len(found) == 2
    ask(message)
    assert {call["symbol"] for call in engine["chart"]} == expected_calls


@pytest.mark.parametrize("message", [
    "compare apple and samsung performance in Q4",
    "compare the performance of AAPL and ZZZZQ in Q4",
    "how has apple performed vs the competition in december",
    "compare apple performance in Q4",
])
def test_comparison_with_an_unresolved_side_is_never_a_single_symbol_study(engine, message):
    assert ask(message) is None
    assert engine["chart"] == []


def test_single_letters_are_not_tickers_outside_a_comparison():
    assert research._explicit_tickers("how has T performed in Q4") == []
    assert research._explicit_tickers("compare F and GM", allow_single=True) == ["F", "GM"]
    assert research._explicit_tickers("is A or I a ticker", allow_single=True) == []


@pytest.mark.parametrize("text", [
    "analyze AAPL returns vs the russell 2000 in Q4", "analyze the Russell 2000 in Q4",
    "analyze the wilshire 5000 in Q4", "analyze the S&P 500 in Q4", "analyze the nasdaq 100 in Q4",
    "analyze the dow 30 in Q4",
])
def test_index_names_with_numbers_are_not_calendar_years(text):
    assert research._parse_period(text, TODAY) is not None
    assert research._parse_period(text + " 2019", TODAY) is None


def test_russell_named_screen_is_not_blocked_by_the_year_guard():
    request = research._screen_request(
        "which russell 1000 stocks are bullish this week, like the russell 2000", TODAY, None)
    assert request is not None and request["market"] == "3"


@pytest.mark.parametrize("message", [
    "when is the high season for this pattern",
    "when is the low season for this chart",
    "when is the high probability period for this pattern",
])
def test_high_season_is_not_a_high_date_question(engine, message):
    assert research._extreme_request(message) is None
    assert ask(message, LOADED_AAPL) is None and engine["chart"] == []


def test_january_first_detector_rows_match_the_engine_january_second_echo():
    payload = {"request": {"symbol": "AAA", "entry_date": "2026-01-02", "days_out": 20,
                           "years": 10, "pe_cycle": "cons"}}
    assert research._echo_matches(payload, "AAA", "2026-01-01", 20, 10, "cons")
    assert not research._echo_matches(payload, "AAA", "2026-01-03", 20, 10, "cons")
    assert not research._echo_matches(payload, "AAA", "2026-01-01", 21, 10, "cons")
    payload["request"]["entry_date"] = "2026-11-17"                 # a date-locked plan's answer
    assert not research._echo_matches(payload, "AAA", "2026-01-01", 20, 10, "cons")


def test_short_side_figures_are_engine_values_never_negated(engine):
    command = ask("Analyze AAPL's historical return from January 1 to March 31 over the last 15 years.")
    stats = chart_payload(engine["chart"][0])["stats"]
    reply = text_of(command)
    assert "the underlying averaged" not in reply
    assert "a positive figure means the underlying fell" in reply
    assert "average %s" % tara_gateway._fmt_pct(float(stats["Avg Profit - All"].rstrip("%"))) in reply

    screen = ask("find s&p500 stocks entering seasonaly bearish patterns this week")
    by_symbol = {call["symbol"]: call for call in engine["chart"]}
    for line, row in zip(ranked_lines(screen), screen["rows"]):
        engine_avg = float(chart_payload(by_symbol[row["symbol"]])["stats"]["Avg Profit - All"].rstrip("%"))
        assert "avg short-side return %s" % tara_gateway._fmt_pct(engine_avg) in line
