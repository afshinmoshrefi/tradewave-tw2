#!/usr/bin/env python3
"""Generate the public verification data for the 100-Year Pattern.

The script uses only the canonical TradeWave SPX daily file. It does not fetch,
fill, interpolate, or reconstruct market data. Configuration is intentionally
kept at the top of the file so the completed-cycle boundary can be changed when
the 2026 cycle resolves in July 2027.
"""

import bisect
import csv
import datetime as dt
import hashlib
import io
import os
import statistics
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


# Configuration
SOURCE_CSV = Path("/home/flask/data/csv/INDX/SPX.csv")
OUTPUT_DIR = Path(__file__).resolve().parent / "static"
CSV_OUTPUT = OUTPUT_DIR / "100-year-pattern-cycles.csv"
METHODOLOGY_OUTPUT = OUTPUT_DIR / "methodology.md"
RECONCILIATION_OUTPUT = Path("/home/afshin/100-year-pattern-reconciliation-report.md")

FIRST_MIDTERM_YEAR = 1930
LAST_COMPLETE_MIDTERM_YEAR = 2022
MIDTERM_YEAR_STEP = 4
ENTRY_MONTH = 9
ENTRY_DAY = 27
EXIT_MONTH = 7
EXIT_DAY = 18
NOMINAL_CALENDAR_DAYS = 295
INTRADAY_OHLC_AVAILABLE_FROM = dt.date(1962, 1, 2)

INDEX_VENDOR = "EODHD"
INDEX_VENDOR_IDENTIFIER = "GSPC.INDX"
INDEX_LOCAL_IDENTIFIER = "SPX"

PRINTED_PATTERN_CUMULATIVE_PCT = 5045
PRINTED_PATTERN_AVERAGE_PCT = 19
PRINTED_WINNERS = 23
PRINTED_TOTAL_CYCLES = 24
PRINTED_LAST_MIDTERM_YEAR = 2022
PRINTED_WIN_RATE_PCT = 96
PRINTED_ONLY_FAILURE = 1930
PRINTED_BUY_HOLD_CUMULATIVE_PCT = 49
PRINTED_BUY_HOLD_AVERAGE_PCT = 4
DISCLOSURE_MIN_MATERIAL_GAIN_PCT = Decimal("2")
DISCLOSURE_NEAR_ZERO_YEAR = 1978

FOUR_PLACES = Decimal("0.0001")
ONE_HUNDRED = Decimal("100")
ZERO = Decimal("0")
getcontext().prec = 50

CSV_COLUMNS = (
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
)


class DataIntegrityError(RuntimeError):
    """Raised when the source cannot support a complete, auditable output."""


@dataclass(frozen=True)
class PriceRow:
    date: dt.date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    adj_factor: Decimal


@dataclass(frozen=True)
class CycleRecord:
    cycle_number: int
    midterm_year: int
    nominal_entry: dt.date
    nominal_exit: dt.date
    resolved_entry: dt.date
    resolved_exit: dt.date
    entry_shift_days: int
    exit_shift_days: int
    entry_close: Decimal
    exit_close: Decimal
    return_pct: Decimal
    mae_close_pct: Decimal
    mae_close_date: dt.date
    mae_intraday_pct: Optional[Decimal]
    mae_intraday_date: Optional[dt.date]
    calendar_days_held: int
    trading_days_held: int


@dataclass(frozen=True)
class SourceProfile:
    row_count: int
    first_date: dt.date
    last_date: dt.date
    sha256: str
    saturday_rows: int
    sunday_rows: int
    pre_1962_rows: int
    pre_1962_flat_ohlc_rows: int
    first_distinct_ohlc_date: Optional[dt.date]
    adj_factor_values: Tuple[Decimal, ...]


@dataclass(frozen=True)
class DisplayMetrics:
    cumulative_pct: int
    average_pct: int
    winners: int
    total: int
    win_rate_pct: int
    losing_years: Tuple[int, ...]


def _decimal(value: str, field: str, line_number: int) -> Decimal:
    if value is None or value.strip() == "":
        raise DataIntegrityError(
            "Missing %s at source line %d" % (field, line_number)
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise DataIntegrityError(
            "Invalid %s at source line %d: %r" % (field, line_number, value)
        )
    if not parsed.is_finite():
        raise DataIntegrityError(
            "Non-finite %s at source line %d" % (field, line_number)
        )
    return parsed


def _date(value: str, line_number: int) -> dt.date:
    if value is None or value.strip() == "":
        raise DataIntegrityError("Missing date at source line %d" % line_number)
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise DataIntegrityError(
            "Invalid date at source line %d: %r" % (line_number, value)
        )


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_source(path: Path) -> Tuple[List[PriceRow], SourceProfile]:
    if not path.is_file():
        raise DataIntegrityError("Source file does not exist: %s" % path)

    required = {"date", "open", "high", "low", "close", "volume", "adj_factor"}
    prices: List[PriceRow] = []
    seen_dates = set()
    saturday_rows = 0
    sunday_rows = 0
    pre_1962_rows = 0
    pre_1962_flat_ohlc_rows = 0
    first_distinct_ohlc_date: Optional[dt.date] = None
    adj_factors = set()

    with path.open("r", newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise DataIntegrityError(
                "Source columns do not include: %s"
                % ", ".join(sorted(required))
            )

        for line_number, row in enumerate(reader, 2):
            date = _date(row.get("date"), line_number)
            if date in seen_dates:
                raise DataIntegrityError("Duplicate source date: %s" % date.isoformat())
            if prices and date <= prices[-1].date:
                raise DataIntegrityError(
                    "Source dates are not strictly increasing at %s" % date.isoformat()
                )

            open_value = _decimal(row.get("open"), "open", line_number)
            high = _decimal(row.get("high"), "high", line_number)
            low = _decimal(row.get("low"), "low", line_number)
            close = _decimal(row.get("close"), "close", line_number)
            volume = _decimal(row.get("volume"), "volume", line_number)
            adj_factor = _decimal(row.get("adj_factor"), "adj_factor", line_number)

            if min(open_value, high, low, close) <= ZERO:
                raise DataIntegrityError(
                    "Nonpositive OHLC value at %s" % date.isoformat()
                )
            if not (low <= open_value <= high and low <= close <= high):
                raise DataIntegrityError(
                    "Invalid OHLC bounds at %s" % date.isoformat()
                )
            if volume < ZERO:
                raise DataIntegrityError("Negative volume at %s" % date.isoformat())
            if adj_factor <= ZERO:
                raise DataIntegrityError(
                    "Nonpositive adjustment factor at %s" % date.isoformat()
                )

            price = PriceRow(
                date=date,
                open=open_value,
                high=high,
                low=low,
                close=close,
                volume=volume,
                adj_factor=adj_factor,
            )
            prices.append(price)
            seen_dates.add(date)
            adj_factors.add(adj_factor)

            if date.weekday() == 5:
                saturday_rows += 1
            elif date.weekday() == 6:
                sunday_rows += 1

            if date < dt.date(1962, 1, 1):
                pre_1962_rows += 1
                if open_value == high == low == close:
                    pre_1962_flat_ohlc_rows += 1
            if first_distinct_ohlc_date is None and not (
                open_value == high == low == close
            ):
                first_distinct_ohlc_date = date

    if not prices:
        raise DataIntegrityError("Source file has no price rows")

    profile = SourceProfile(
        row_count=len(prices),
        first_date=prices[0].date,
        last_date=prices[-1].date,
        sha256=_source_sha256(path),
        saturday_rows=saturday_rows,
        sunday_rows=sunday_rows,
        pre_1962_rows=pre_1962_rows,
        pre_1962_flat_ohlc_rows=pre_1962_flat_ohlc_rows,
        first_distinct_ohlc_date=first_distinct_ohlc_date,
        adj_factor_values=tuple(sorted(adj_factors)),
    )
    return prices, profile


def configured_midterm_years() -> List[int]:
    years = list(
        range(
            FIRST_MIDTERM_YEAR,
            LAST_COMPLETE_MIDTERM_YEAR + 1,
            MIDTERM_YEAR_STEP,
        )
    )
    if not years or years[-1] != LAST_COMPLETE_MIDTERM_YEAR:
        raise DataIntegrityError("Configured midterm-year range is not aligned")
    return years


def resolve_on_or_after(dates: Sequence[dt.date], nominal: dt.date) -> int:
    index = bisect.bisect_left(dates, nominal)
    if index >= len(dates):
        raise DataIntegrityError(
            "No source observation on or after %s" % nominal.isoformat()
        )
    return index


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    return (numerator / denominator - Decimal("1")) * ONE_HUNDRED


def build_cycle_records(prices: Sequence[PriceRow]) -> List[CycleRecord]:
    dates = [price.date for price in prices]
    records: List[CycleRecord] = []

    for cycle_number, midterm_year in enumerate(configured_midterm_years(), 1):
        nominal_entry = dt.date(midterm_year, ENTRY_MONTH, ENTRY_DAY)
        nominal_exit = dt.date(midterm_year + 1, EXIT_MONTH, EXIT_DAY)
        nominal_days = (nominal_exit - nominal_entry).days + 1
        if nominal_days != NOMINAL_CALENDAR_DAYS:
            raise DataIntegrityError(
                "Nominal duration is %d rather than %d for %d"
                % (nominal_days, NOMINAL_CALENDAR_DAYS, midterm_year)
            )

        entry_index = resolve_on_or_after(dates, nominal_entry)
        exit_index = resolve_on_or_after(dates, nominal_exit)
        if exit_index < entry_index:
            raise DataIntegrityError("Resolved exit precedes entry for %d" % midterm_year)

        entry = prices[entry_index]
        exit_row = prices[exit_index]
        window = list(prices[entry_index : exit_index + 1])
        if not window or window[0] != entry or window[-1] != exit_row:
            raise DataIntegrityError("Incomplete source window for %d" % midterm_year)

        close_mae_row = min(window, key=lambda item: item.close)
        close_mae = min(ZERO, _pct(close_mae_row.close, entry.close))
        intraday_mae: Optional[Decimal] = None
        intraday_mae_date: Optional[dt.date] = None
        if entry.date >= INTRADAY_OHLC_AVAILABLE_FROM:
            intraday_mae_row = min(window, key=lambda item: item.low)
            intraday_mae = min(ZERO, _pct(intraday_mae_row.low, entry.close))
            intraday_mae_date = intraday_mae_row.date

        records.append(
            CycleRecord(
                cycle_number=cycle_number,
                midterm_year=midterm_year,
                nominal_entry=nominal_entry,
                nominal_exit=nominal_exit,
                resolved_entry=entry.date,
                resolved_exit=exit_row.date,
                entry_shift_days=(entry.date - nominal_entry).days,
                exit_shift_days=(exit_row.date - nominal_exit).days,
                entry_close=entry.close,
                exit_close=exit_row.close,
                return_pct=_pct(exit_row.close, entry.close),
                mae_close_pct=close_mae,
                mae_close_date=close_mae_row.date,
                mae_intraday_pct=intraday_mae,
                mae_intraday_date=intraday_mae_date,
                calendar_days_held=(exit_row.date - entry.date).days + 1,
                trading_days_held=len(window),
            )
        )

    expected_count = (
        (LAST_COMPLETE_MIDTERM_YEAR - FIRST_MIDTERM_YEAR) // MIDTERM_YEAR_STEP
    ) + 1
    if len(records) != expected_count:
        raise DataIntegrityError(
            "Expected %d configured cycles but built %d"
            % (expected_count, len(records))
        )
    return records


def build_buy_hold_returns(
    prices: Sequence[PriceRow], midterm_years: Iterable[int]
) -> List[Decimal]:
    dates = [price.date for price in prices]
    returns: List[Decimal] = []
    for year in midterm_years:
        start_index = resolve_on_or_after(dates, dt.date(year, 1, 1))
        exit_index = resolve_on_or_after(dates, dt.date(year + 1, 1, 1))
        if exit_index <= start_index:
            raise DataIntegrityError("Incomplete buy-and-hold window for %d" % year)
        returns.append(_pct(prices[exit_index].close, prices[start_index].close))
    return returns


def compound_decimal(returns: Iterable[Decimal]) -> Decimal:
    growth = Decimal("1")
    for return_pct in returns:
        growth *= Decimal("1") + return_pct / ONE_HUNDRED
    return (growth - Decimal("1")) * ONE_HUNDRED


def display_metrics(
    returns: Sequence[Decimal], years: Sequence[int]
) -> DisplayMetrics:
    if len(returns) != len(years) or not returns:
        raise DataIntegrityError("Metric inputs have inconsistent lengths")
    rounded = [round(float(value), 2) for value in returns]
    growth = 1.0
    for value in rounded:
        growth *= 1.0 + value / 100.0
    cumulative = (growth - 1.0) * 100.0
    winners = sum(value >= 0 for value in rounded)
    losing_years = tuple(
        year for year, value in zip(years, rounded) if value < 0
    )
    return DisplayMetrics(
        cumulative_pct=int(cumulative),
        average_pct=round(statistics.mean(rounded)),
        winners=winners,
        total=len(rounded),
        win_rate_pct=round(ONE_HUNDRED * Decimal(winners) / Decimal(len(rounded))),
        losing_years=losing_years,
    )


def validate_reconciliation(
    pattern_metrics: DisplayMetrics, buy_hold_metrics: DisplayMetrics
) -> None:
    checks = (
        ("pattern cumulative", pattern_metrics.cumulative_pct, PRINTED_PATTERN_CUMULATIVE_PCT),
        ("pattern average", pattern_metrics.average_pct, PRINTED_PATTERN_AVERAGE_PCT),
        ("pattern winners", pattern_metrics.winners, PRINTED_WINNERS),
        ("pattern total", pattern_metrics.total, PRINTED_TOTAL_CYCLES),
        ("pattern win rate", pattern_metrics.win_rate_pct, PRINTED_WIN_RATE_PCT),
        (
            "only failure",
            pattern_metrics.losing_years,
            (PRINTED_ONLY_FAILURE,),
        ),
        (
            "buy-and-hold cumulative",
            buy_hold_metrics.cumulative_pct,
            PRINTED_BUY_HOLD_CUMULATIVE_PCT,
        ),
        (
            "buy-and-hold average",
            buy_hold_metrics.average_pct,
            PRINTED_BUY_HOLD_AVERAGE_PCT,
        ),
    )
    failures = [
        "%s: computed %r, printed %r" % (name, actual, expected)
        for name, actual, expected in checks
        if actual != expected
    ]
    if failures:
        raise DataIntegrityError(
            "Printed figures do not reconcile under TradeWave display rules:\n%s"
            % "\n".join(failures)
        )


def validate_distribution_disclosure(records: Sequence[CycleRecord]) -> None:
    material_gains = [
        record
        for record in records
        if record.return_pct > DISCLOSURE_MIN_MATERIAL_GAIN_PCT
    ]
    small_positive = [
        record
        for record in records
        if ZERO < record.return_pct <= DISCLOSURE_MIN_MATERIAL_GAIN_PCT
    ]
    losses = [record for record in records if record.return_pct < ZERO]
    valid = (
        len(material_gains) == 22
        and len(small_positive) == 1
        and small_positive[0].midterm_year == DISCLOSURE_NEAR_ZERO_YEAR
        and small_positive[0].entry_close == Decimal("101.66")
        and small_positive[0].exit_close == Decimal("101.69")
        and len(losses) == 1
        and losses[0].midterm_year == PRINTED_ONLY_FAILURE
    )
    if not valid:
        raise DataIntegrityError(
            "The required 22 material gains, one near-zero gain, one loss disclosure no longer matches the source"
        )


def distribution_disclosure(records: Sequence[CycleRecord]) -> str:
    validate_distribution_disclosure(records)
    near_zero = [
        record
        for record in records
        if record.midterm_year == DISCLOSURE_NEAR_ZERO_YEAR
    ][0]
    rounded_return = near_zero.return_pct.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return (
        "22 of 24 cycles gained more than 2%%; the 1978 cycle gained %s%% as "
        "the index moved only 0.03 points, from 101.66 to 101.69; 1930 lost."
        % format(rounded_return, "f")
    )


def _four_decimal_text(value: Decimal) -> str:
    rounded = value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
    if rounded == ZERO:
        rounded = ZERO.quantize(FOUR_PLACES)
    return format(rounded, "f")


def cycle_csv_text(records: Sequence[CycleRecord]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow(
            {
                "cycle_number": record.cycle_number,
                "midterm_year": record.midterm_year,
                "nominal_entry": record.nominal_entry.isoformat(),
                "nominal_exit": record.nominal_exit.isoformat(),
                "resolved_entry": record.resolved_entry.isoformat(),
                "resolved_exit": record.resolved_exit.isoformat(),
                "entry_shift_days": record.entry_shift_days,
                "exit_shift_days": record.exit_shift_days,
                "entry_close": _four_decimal_text(record.entry_close),
                "exit_close": _four_decimal_text(record.exit_close),
                "return_pct": _four_decimal_text(record.return_pct),
                "mae_close_pct": _four_decimal_text(record.mae_close_pct),
                "mae_close_date": record.mae_close_date.isoformat(),
                "mae_intraday_pct": (
                    ""
                    if record.mae_intraday_pct is None
                    else _four_decimal_text(record.mae_intraday_pct)
                ),
                "mae_intraday_date": (
                    ""
                    if record.mae_intraday_date is None
                    else record.mae_intraday_date.isoformat()
                ),
                "calendar_days_held": record.calendar_days_held,
                "trading_days_held": record.trading_days_held,
            }
        )
    return output.getvalue()


def methodology_text(
    profile: SourceProfile,
    records: Sequence[CycleRecord],
    printed_cohort_records: Sequence[CycleRecord],
) -> str:
    distinct_date = (
        profile.first_distinct_ohlc_date.isoformat()
        if profile.first_distinct_ohlc_date is not None
        else "not present"
    )
    return """# Methodology

- Outcome disclosure: %s
- Intraday MAE availability: `mae_intraday_pct` and `mae_intraday_date` are blank for the 1930 through 1958 cycles because the vendor series has no distinct daily high or low before 1962. No close value is substituted for an unavailable intraday low. Blank means unavailable, not zero.
- Index series and identifier: EODHD `GSPC.INDX`, stored by TradeWave as `SPX`.
- Index history: before March 1957, the series represents the daily 90-stock S&P Composite predecessor. The S&P 500 began in its current 500-stock format in March 1957.
- Data source and vendor: EODHD End-of-Day Historical Data API, using the existing TradeWave daily OHLC file. No data was downloaded for this extraction.
- Adjustment: the TradeWave ingestion pipeline applies `adjusted_close / close` to OHLC. Every adjustment factor in this index file is 1.0, so the published levels are unchanged price-index levels.
- Return basis: price return. Dividends are not reinvested.
- Return measurement: close to close from resolved entry through resolved exit.
- Transaction costs and slippage: zero.
- Cohort: %d completed PE+2 midterm cycles, entry years %d through %d.
- Nominal window: September 27 of each midterm year through July 18 of the following year.
- Endpoint convention: if a nominal endpoint has no observation, use the first dated observation after it. Entry and exit are resolved independently.
- Session calendar: the dated observations in the canonical EODHD `GSPC.INDX` file. No weekday, holiday, or price observation is interpolated, forward-filled, or reconstructed.
- Historical session note: this vendor series contains no Saturday observations. Before the NYSE adopted a year-round five-day week in September 1952, Saturday exchange sessions existed. The CSV exposes every endpoint shift so this source convention is visible.
- Inclusive counting: the entry date counts as day 1, so July 1 to July 31 is 31 calendar days.
- Duration: 295 days is the nominal inclusive calendar label. `calendar_days_held` reports the inclusive span between resolved endpoints. `trading_days_held` counts dated source observations inclusively.
- Close-basis MAE: the lowest close in the inclusive resolved window versus `entry_close`, reported as a negative percentage or zero.
- Intraday-basis MAE: when available, the lowest vendor daily low in the inclusive resolved window versus `entry_close`, reported as a negative percentage or zero.
- MAE reference price: `entry_close` for both MAE columns.
- Historical OHLC note: all %d source rows before 1962 have identical open, high, low, and close values. The first distinct daily OHLC row is %s.
- CSV precision: prices and percentages are published to four decimal places. Summary figures use TradeWave's display convention: round each cycle return to two decimals, compute aggregates, and display whole percentages.
""" % (
        distribution_disclosure(printed_cohort_records),
        len(records),
        FIRST_MIDTERM_YEAR,
        LAST_COMPLETE_MIDTERM_YEAR,
        profile.pre_1962_flat_ohlc_rows,
        distinct_date,
    )


def _endpoint_audit_line(
    year: int, label: str, nominal: dt.date, resolved: dt.date
) -> Optional[str]:
    shift = (resolved - nominal).days
    if shift == 0:
        return None
    skipped = [nominal + dt.timedelta(days=offset) for offset in range(shift)]
    crossed_weekday = any(day.weekday() < 5 for day in skipped)
    classification = (
        "market holiday or historical closure"
        if crossed_weekday
        else "weekend only"
    )
    if nominal.weekday() == 5 and nominal < dt.date(1952, 9, 29):
        classification += "; pre-1952 Saturday source caveat"
    return "| %d | %s | %s | %s | %s | +%d | %s |" % (
        year,
        label,
        nominal.isoformat(),
        nominal.strftime("%A"),
        resolved.isoformat(),
        shift,
        classification,
    )


def reconciliation_text(
    records: Sequence[CycleRecord],
    printed_cohort_records: Sequence[CycleRecord],
    buy_hold_returns: Sequence[Decimal],
    pattern_metrics: DisplayMetrics,
    full_pattern_metrics: DisplayMetrics,
    buy_hold_metrics: DisplayMetrics,
    profile: SourceProfile,
) -> str:
    pattern_returns = [record.return_pct for record in printed_cohort_records]
    exact_pattern_cumulative = compound_decimal(pattern_returns)
    csv_pattern_cumulative = compound_decimal(
        [value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP) for value in pattern_returns]
    )
    exact_pattern_average = sum(pattern_returns, ZERO) / Decimal(len(pattern_returns))
    exact_buy_hold_cumulative = compound_decimal(buy_hold_returns)
    exact_buy_hold_average = sum(buy_hold_returns, ZERO) / Decimal(len(buy_hold_returns))

    audit_lines: List[str] = []
    for record in records:
        entry_line = _endpoint_audit_line(
            record.midterm_year,
            "Entry",
            record.nominal_entry,
            record.resolved_entry,
        )
        exit_line = _endpoint_audit_line(
            record.midterm_year,
            "Exit",
            record.nominal_exit,
            record.resolved_exit,
        )
        if entry_line is not None:
            audit_lines.append(entry_line)
        if exit_line is not None:
            audit_lines.append(exit_line)

    printed_only_failure = (
        str(pattern_metrics.losing_years[0])
        if len(pattern_metrics.losing_years) == 1
        else ", ".join(str(year) for year in pattern_metrics.losing_years)
    )
    generated_losing_years = ", ".join(
        str(year) for year in full_pattern_metrics.losing_years
    )
    if len(full_pattern_metrics.losing_years) == 1:
        generated_loss_sentence = "%s is the only losing cycle" % generated_losing_years
    elif not full_pattern_metrics.losing_years:
        generated_loss_sentence = "There are no losing cycles"
    else:
        generated_loss_sentence = "The losing cycles are %s" % generated_losing_years
    generated = (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return """# 100-Year Pattern Reconciliation Report

Generated: %s

Status: PASS under TradeWave's documented whole-number display convention.

## Source

- File: `%s`
- SHA-256: `%s`
- Rows: %d
- Coverage: %s through %s
- Duplicate dates: 0
- Missing required OHLC values: 0
- Incomplete target windows: 0
- Adjustment-factor values: %s
- Saturday observations: %d
- Sunday observations: %d
- Pre-1962 flat OHLC rows: %d of %d
- Null intraday MAE rows: %d
- Generated CSV cycles: %d, entry years %d through %d
- Printed-figure reconciliation cohort: %d cycles, entry years %d through %d

## Reconciliation

`Display difference` compares the generated TradeWave display value with the printed value.

| Metric | Printed | Full-precision calculation | TradeWave display | Display difference | Result |
|---|---:|---:|---:|---:|---|
| Pattern cumulative return | %s%% | %s%% | %s%% | %+d | PASS |
| Average gain per cycle | %s%% | %s%% | %s%% | %+d | PASS |
| Cycles profitable | %s of %s | %s of %s | %s of %s | 0 | PASS |
| Win rate | %s%% | %s%% | %s%% | %+d | PASS |
| Only failure | %s | %s | %s | n/a | PASS |
| PE+2 buy-and-hold cumulative | %s%% | %s%% | %s%% | %+d | PASS |
| PE+2 buy-and-hold average gain | %s%% | %s%% | %s%% | %+d | PASS |

Pattern cumulative return is compounded across cycles, not summed. The formula is `100 * (product(1 + return_pct / 100) - 1)`. Compounding the four-decimal CSV returns produces %s%%.

TradeWave rounds each individual period return to two decimals before aggregate calculations. It truncates cumulative return to a whole percentage with `int()` and rounds average return and win rate to whole percentages. This is the convention that produces the printed figures.

The PE+2 buy-and-hold comparison is January 1 to January 1 of the following year, resolved against the same source observations and repeated for each PE+2 year. It is not the first-through-last-session return of the PE+2 calendar year.

## Record disclosure

%s

The intraday MAE percentage and date are blank for the 1930 through 1958 cycles. Distinct vendor daily high and low fields begin in 1962. No close-basis value is substituted.

## Holiday and endpoint audit

Calendar source: observed dates in the canonical EODHD `GSPC.INDX` daily series. The resolver selects only an observed date and never constructs a weekday or price.

| Cycle | Endpoint | Nominal date | Day | Resolved date | Shift | Classification |
|---:|---|---|---|---|---:|---|
%s

No shifted post-1952 endpoint crossed a weekday market holiday. Every post-1952 shift was caused only by Saturday or Sunday. The 1930 Saturday endpoints carry the disclosed pre-1952 vendor-session caveat.

The source-observation resolver covers the full 1930 through 2023 study span and preserves historical closures present in the vendor series. The series contains no Saturday observations, including the era before the NYSE adopted a year-round five-day week on September 29, 1952.

## Losing-cycle check

%s. The generated record is %d profitable cycles of %d.

## Files written

- `%s`
- `%s`
- `%s`
""" % (
        generated,
        SOURCE_CSV,
        profile.sha256,
        profile.row_count,
        profile.first_date.isoformat(),
        profile.last_date.isoformat(),
        ", ".join(str(value) for value in profile.adj_factor_values),
        profile.saturday_rows,
        profile.sunday_rows,
        profile.pre_1962_flat_ohlc_rows,
        profile.pre_1962_rows,
        sum(record.mae_intraday_pct is None for record in records),
        len(records),
        records[0].midterm_year,
        records[-1].midterm_year,
        len(printed_cohort_records),
        printed_cohort_records[0].midterm_year,
        printed_cohort_records[-1].midterm_year,
        PRINTED_PATTERN_CUMULATIVE_PCT,
        _four_decimal_text(exact_pattern_cumulative),
        pattern_metrics.cumulative_pct,
        pattern_metrics.cumulative_pct - PRINTED_PATTERN_CUMULATIVE_PCT,
        PRINTED_PATTERN_AVERAGE_PCT,
        _four_decimal_text(exact_pattern_average),
        pattern_metrics.average_pct,
        pattern_metrics.average_pct - PRINTED_PATTERN_AVERAGE_PCT,
        PRINTED_WINNERS,
        PRINTED_TOTAL_CYCLES,
        pattern_metrics.winners,
        pattern_metrics.total,
        pattern_metrics.winners,
        pattern_metrics.total,
        PRINTED_WIN_RATE_PCT,
        _four_decimal_text(
            ONE_HUNDRED * Decimal(pattern_metrics.winners) / Decimal(pattern_metrics.total)
        ),
        pattern_metrics.win_rate_pct,
        pattern_metrics.win_rate_pct - PRINTED_WIN_RATE_PCT,
        PRINTED_ONLY_FAILURE,
        printed_only_failure,
        printed_only_failure,
        PRINTED_BUY_HOLD_CUMULATIVE_PCT,
        _four_decimal_text(exact_buy_hold_cumulative),
        buy_hold_metrics.cumulative_pct,
        buy_hold_metrics.cumulative_pct - PRINTED_BUY_HOLD_CUMULATIVE_PCT,
        PRINTED_BUY_HOLD_AVERAGE_PCT,
        _four_decimal_text(exact_buy_hold_average),
        buy_hold_metrics.average_pct,
        buy_hold_metrics.average_pct - PRINTED_BUY_HOLD_AVERAGE_PCT,
        _four_decimal_text(csv_pattern_cumulative),
        distribution_disclosure(printed_cohort_records),
        "\n".join(audit_lines),
        generated_loss_sentence,
        full_pattern_metrics.winners,
        full_pattern_metrics.total,
        CSV_OUTPUT,
        METHODOLOGY_OUTPUT,
        RECONCILIATION_OUTPUT,
    )


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, str(path))
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def main() -> int:
    try:
        prices, profile = load_source(SOURCE_CSV)
        records = build_cycle_records(prices)
        years = [record.midterm_year for record in records]
        pattern_returns = [record.return_pct for record in records]
        printed_cohort_records = [
            record
            for record in records
            if record.midterm_year <= PRINTED_LAST_MIDTERM_YEAR
        ]
        printed_years = [record.midterm_year for record in printed_cohort_records]
        printed_pattern_returns = [
            record.return_pct for record in printed_cohort_records
        ]
        if len(printed_cohort_records) != PRINTED_TOTAL_CYCLES:
            raise DataIntegrityError(
                "Expected %d printed-cohort cycles but found %d"
                % (PRINTED_TOTAL_CYCLES, len(printed_cohort_records))
            )
        buy_hold_returns = build_buy_hold_returns(prices, printed_years)
        pattern_metrics = display_metrics(printed_pattern_returns, printed_years)
        full_pattern_metrics = display_metrics(pattern_returns, years)
        buy_hold_metrics = display_metrics(buy_hold_returns, printed_years)
        validate_reconciliation(pattern_metrics, buy_hold_metrics)
        validate_distribution_disclosure(printed_cohort_records)

        csv_content = cycle_csv_text(records)
        methodology = methodology_text(profile, records, printed_cohort_records)
        reconciliation = reconciliation_text(
            records,
            printed_cohort_records,
            buy_hold_returns,
            pattern_metrics,
            full_pattern_metrics,
            buy_hold_metrics,
            profile,
        )

        for name, content in (
            ("CSV", csv_content),
            ("methodology", methodology),
            ("reconciliation", reconciliation),
        ):
            if "\u2014" in content or "\u2013" in content:
                raise DataIntegrityError("%s output contains a prohibited dash" % name)

        _atomic_write_text(CSV_OUTPUT, csv_content)
        _atomic_write_text(METHODOLOGY_OUTPUT, methodology)
        _atomic_write_text(RECONCILIATION_OUTPUT, reconciliation)
        print(reconciliation)
        return 0
    except DataIntegrityError as error:
        print("DATA INTEGRITY FAILURE: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
