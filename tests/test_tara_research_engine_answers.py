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


@pytest.fixture
def engine(monkeypatch):
    """Replay recorded engine responses and capture every engine request."""

    calls = {"opplist": [], "chart": []}

    def opplist(market, day, year1, year2, day_range, token):
        key = "%s|%s|%s|%s|%s" % (market, day.isoformat(), year1, year2, day_range)
        calls["opplist"].append({"market": str(market), "day": day, "year1": int(year1),
                                 "year2": int(year2), "day_range": day_range})
        hit = FIXTURE["opplist"].get(key)
        return (hit["status"], hit["rows"]) if hit else (None, None)

    def chart(market, symbol, entry_date, days_out, years_value, token, **params):
        key = "%s|%s|%s|%s|%s|%s" % (
            market, symbol, entry_date, days_out, years_value,
            "&".join("%s=%s" % item for item in sorted(params.items())))
        calls["chart"].append({"market": str(market), "symbol": symbol, "entry": entry_date,
                               "days": int(days_out), "years": str(years_value), "params": params})
        hit = FIXTURE["chart"].get(key)
        return (hit["status"], hit["payload"]) if hit else (None, None)

    def resolve(symbol, question, token, current_view=None):
        return FIXTURE["resolve"].get(
            str(symbol).upper(), {"status": "not_found", "symbol": str(symbol).upper()})

    def available_years(market, symbol, token, pe_cycle=None):
        return FIXTURE["years"].get("%s|%s|%s" % (market, str(symbol).upper(), pe_cycle or "cons"))

    monkeypatch.setattr(research, "_engine_opplist", opplist)
    monkeypatch.setattr(research, "_engine_chart", chart)
    monkeypatch.setattr(research, "_engine_symbol_names", lambda market, token: FIXTURE["names"])
    monkeypatch.setattr(tara_gateway, "_resolve_question_symbol", resolve)
    monkeypatch.setattr(tara_gateway, "_symbol_max_available_years", available_years)
    return calls


def ask(message, view=None, **kwargs):
    kwargs.setdefault("today", TODAY)
    return research.build_research_command(message, view or {}, "user-token", **kwargs)


def text_of(command):
    reply = re.sub(r"</?div[^>]*>|<br>", "\n", command["reply"])
    return re.sub(r"<[^>]+>", "", reply)


def ranked_lines(command):
    return [line.strip() for line in text_of(command).split("\n") if re.match(r"\s*\d+\. ", line)]


def chart_payload(call):
    key = "%s|%s|%s|%s|%s|%s" % (
        call["market"], call["symbol"], call["entry"], call["days"], call["years"],
        "&".join("%s=%s" % item for item in sorted(call["params"].items())))
    return FIXTURE["chart"][key]["payload"]


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
    # Every trading day of the week is screened (the Monday table carries the weekend).
    assert sorted({call["day"].isoformat() for call in engine["opplist"]}) == [
        "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]
    assert {call["market"] for call in engine["opplist"]} == {"2"}
    # The widest in-band detector table (S&P 500 at 10 years = at least 8 winners).
    assert {(call["year1"], call["year2"]) for call in engine["opplist"]} == {(10, 8)}

    lines = ranked_lines(command)
    assert len(lines) == 10, "a one-name 'list' was the reported failure"
    symbols = [re.match(r"\d+\. (\S+)", line).group(1) for line in lines]
    assert len(set(symbols)) == 10
    for line in lines:
        assert re.search(r"fell in \d+ of \d+ years \(\d+%\)", line)
        assert "Sharpe" in line and "avg move -" in line
    sharpes = [float(re.search(r"Sharpe (-?\d+\.\d+)", line).group(1)) for line in lines]
    assert sharpes == sorted(sharpes, reverse=True)
    # A weekend-dated pattern is presented on its first session, never as "entry Sunday".
    assert not re.search(r"starts (?:Sat|Sun) ", text_of(command))
    assert "calendar start Sun Nov 15" in text_of(command)
    assert "not sell or short recommendations" in text_of(command)


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
      "first": "2026-11-16", "last": "2026-11-22"}),
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
      "first": "2026-11-17", "last": "2026-11-19"}),
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
    assert "Best year: 2007" in reply and "Worst year: 2018" in reply
    assert "(MFE)" in reply and "(MAE)" in reply
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


def test_comparison_without_dates_asks_for_the_window(engine):
    command = ask("compare XLK vs XLF")
    assert "Which dates should I compare XLK and XLF over?" in command["reply"]
    assert command["actions"] == [] and engine["chart"] == []


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

def test_chartdata4_excursion_dates_are_opt_in_and_separately_cached():
    source = (ROOT / "appserver/appserver/appserver.py").read_text()
    assert "_excursion_dates = request.args.get('excursion_dates') == '1'" in source
    assert "redis_key_chartdata += '_excursion_dates'" in source
    # Dates are attached only in the opt-in mode, from the same slice as the MFE/MAE values.
    assert source.count("if _excursion_dates:") == 3
    for field in ("entry_trade_date", "exit_trade_date", "high_date", "low_date"):
        assert "yearDict['%s']" % field in source


def test_recorded_excursion_rows_keep_the_legacy_values_and_add_dates():
    payload = FIXTURE["chart"]["5|SPX|2026-09-27|295|pe2-24|excursion_dates=1"]["payload"]
    for row in payload["ChartData4"]:
        assert len(row["pct"].split(",")) == 3
        assert row["entry_trade_date"] <= row["low_date"] <= row["exit_trade_date"]
        assert row["entry_trade_date"] <= row["high_date"] <= row["exit_trade_date"]
    assert payload["stats"]["Num Winners"] == "23" and payload["stats"]["Num Losers"] == "1"
