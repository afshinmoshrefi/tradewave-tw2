import ast
import csv
import datetime as dt
import statistics
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "site" / "generate_100_year_pattern_data.py"
CSV_PATH = ROOT / "site" / "static" / "100-year-pattern-cycles.csv"
METHODOLOGY_PATH = ROOT / "site" / "static" / "methodology.md"

EXPECTED_COLUMNS = [
    "cycle_number",
    "midterm_year",
    "nominal_entry",
    "nominal_exit",
    "resolved_entry",
    "resolved_exit",
    "entry_shift_days",
    "exit_shift_days",
    "entry_close",
    "exit_close",
    "return_pct",
    "mae_close_pct",
    "mae_close_date",
    "mae_intraday_pct",
    "mae_intraday_date",
    "calendar_days_held",
    "trading_days_held",
]


def _rows():
    with CSV_PATH.open("r", newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        return reader.fieldnames, rows


def test_generator_parses_as_python_38():
    ast.parse(
        SCRIPT.read_text(encoding="utf-8"),
        filename=str(SCRIPT),
        feature_version=(3, 8),
    )


def test_cycle_csv_schema_dates_and_precision():
    columns, rows = _rows()
    assert columns == EXPECTED_COLUMNS
    assert len(rows) == 24
    assert [int(row["cycle_number"]) for row in rows] == list(range(1, 25))
    assert [int(row["midterm_year"]) for row in rows] == list(
        range(1930, 2023, 4)
    )

    for row in rows:
        year = int(row["midterm_year"])
        nominal_entry = dt.datetime.strptime(
            row["nominal_entry"], "%Y-%m-%d"
        ).date()
        nominal_exit = dt.datetime.strptime(
            row["nominal_exit"], "%Y-%m-%d"
        ).date()
        resolved_entry = dt.datetime.strptime(
            row["resolved_entry"], "%Y-%m-%d"
        ).date()
        resolved_exit = dt.datetime.strptime(
            row["resolved_exit"], "%Y-%m-%d"
        ).date()

        assert nominal_entry == dt.date(year, 9, 27)
        assert nominal_exit == dt.date(year + 1, 7, 18)
        assert (nominal_exit - nominal_entry).days + 1 == 295
        assert int(row["entry_shift_days"]) == (
            resolved_entry - nominal_entry
        ).days
        assert int(row["exit_shift_days"]) == (
            resolved_exit - nominal_exit
        ).days
        assert int(row["calendar_days_held"]) == (
            resolved_exit - resolved_entry
        ).days + 1
        assert int(row["trading_days_held"]) > 0
        assert Decimal(row["mae_close_pct"]) <= 0
        if year <= 1958:
            assert row["mae_intraday_pct"] == ""
            assert row["mae_intraday_date"] == ""
        else:
            assert Decimal(row["mae_intraday_pct"]) <= 0
            assert row["mae_intraday_date"] != ""

        for field in (
            "entry_close",
            "exit_close",
            "return_pct",
            "mae_close_pct",
        ):
            assert len(row[field].split(".")[-1]) == 4
        if row["mae_intraday_pct"]:
            assert len(row["mae_intraday_pct"].split(".")[-1]) == 4

    assert sum(row["mae_intraday_pct"] == "" for row in rows) == 8
    assert sum(row["mae_intraday_date"] == "" for row in rows) == 8


def test_csv_reproduces_printed_display_record():
    _, rows = _rows()
    returns = [round(float(row["return_pct"]), 2) for row in rows]
    growth = 1.0
    for return_pct in returns:
        growth *= 1.0 + return_pct / 100.0

    winners = sum(return_pct >= 0 for return_pct in returns)
    losing_years = [
        int(row["midterm_year"])
        for row, return_pct in zip(rows, returns)
        if return_pct < 0
    ]

    assert int((growth - 1.0) * 100.0) == 5045
    assert round(statistics.mean(returns)) == 19
    assert winners == 23
    assert round(100 * winners / len(returns)) == 96
    assert losing_years == [1930]


def test_methodology_contains_required_definitions_and_ascii_dashes():
    methodology = METHODOLOGY_PATH.read_text(encoding="utf-8")
    assert "90-stock S&P Composite predecessor" in methodology
    assert "Dividends are not reinvested" in methodology
    assert "Transaction costs and slippage: zero" in methodology
    assert "the entry date counts as day 1" in methodology
    assert "MAE reference price: `entry_close` for both" in methodology
    assert "No close value is substituted" in methodology
    assert (
        "22 of 24 cycles gained more than 2%; the 1978 cycle gained 0.03%"
        in methodology
    )

    for path in (SCRIPT, CSV_PATH, METHODOLOGY_PATH):
        content = path.read_text(encoding="utf-8")
        assert "\u2014" not in content
        assert "\u2013" not in content


def test_near_zero_1978_cycle_is_disclosed_by_the_data():
    _, rows = _rows()
    material_gains = [row for row in rows if Decimal(row["return_pct"]) > 2]
    small_positive = [
        row for row in rows if 0 < Decimal(row["return_pct"]) <= 2
    ]
    losses = [row for row in rows if Decimal(row["return_pct"]) < 0]

    assert len(material_gains) == 22
    assert len(small_positive) == 1
    assert small_positive[0]["midterm_year"] == "1978"
    assert small_positive[0]["entry_close"] == "101.6600"
    assert small_positive[0]["exit_close"] == "101.6900"
    assert small_positive[0]["return_pct"] == "0.0295"
    assert [row["midterm_year"] for row in losses] == ["1930"]
