"""Typed models for the TradeWave Data API.

Every model is a dataclass with a tolerant ``from_dict`` classmethod: it reads
fields with ``.get`` and NEVER raises on an unknown or missing key, so a server
that adds a field (or omits one) can never crash your client. The original
parsed JSON is preserved on every model as ``.raw`` so power users are never
blocked by a model lag - if the SDK has not yet modeled a field, read it
straight off ``.raw``.

SAFETY: TradeWave is a signals-only API. There are no price fields here by
design - all monetary movement is expressed as percentages, and the seasonal
curve ``index`` is a 0-100 normalized relative shape, never a price.

Field-name footgun (documented in the API contract):
  - ``historical_win_rate`` = share of profitable years (the seasonal record).
  - ``ml_win_prob`` (on SignalCardML) / ``win_prob`` (on the legacy MLScore) =
    the ML model's predicted probability.
These are DISTINCT and are intentionally never both called "win rate".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _as_dict(value: Any) -> Dict[str, Any]:
    """Coerce a value to a dict, tolerating None/non-dict inputs."""
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    """Coerce a value to a list, tolerating None/non-list inputs."""
    return value if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# Markets / symbols
# ---------------------------------------------------------------------------


@dataclass
class Market:
    """One of the 17 TradeWave markets and the caller's access scope."""

    id: Optional[str] = None
    name: Optional[str] = None
    ml_eligible: Optional[bool] = None
    in_scope: Optional[bool] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "Market":
        d = _as_dict(data)
        return cls(
            id=d.get("id"),
            name=d.get("name"),
            ml_eligible=d.get("ml_eligible"),
            in_scope=d.get("in_scope"),
            raw=d,
        )


@dataclass
class Symbol:
    """A symbol within a market."""

    symbol: Optional[str] = None
    name: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "Symbol":
        d = _as_dict(data)
        return cls(symbol=d.get("symbol"), name=d.get("name"), raw=d)


@dataclass
class MarketRef:
    """A compact market reference embedded on a SignalCard."""

    id: Optional[str] = None
    name: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "MarketRef":
        d = _as_dict(data)
        return cls(id=d.get("id"), name=d.get("name"), raw=d)


@dataclass
class Me:
    """The /me response - identity + capabilities for the caller's API key.

    ``ml_remaining_today`` and ``ml_daily_limit`` are ``None`` when unlimited.
    ``rate`` is the plan's rate-limit block (``per_minute`` / ``per_day``),
    kept as a raw dict so new keys flow through without a model bump.
    """

    tier: Optional[str] = None
    tier_name: Optional[str] = None
    ml_remaining_today: Optional[int] = None
    ml_daily_limit: Optional[int] = None
    opp_limit: Optional[int] = None
    rate: Dict[str, Any] = field(default_factory=dict)
    markets_in_scope: List[Market] = field(default_factory=list)
    upgrade_url: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "Me":
        d = _as_dict(data)
        return cls(
            tier=d.get("tier"),
            tier_name=d.get("tier_name"),
            ml_remaining_today=d.get("ml_remaining_today"),
            ml_daily_limit=d.get("ml_daily_limit"),
            opp_limit=d.get("opp_limit"),
            rate=_as_dict(d.get("rate")),
            markets_in_scope=[
                Market.from_dict(m) for m in _as_list(d.get("markets_in_scope"))
            ],
            upgrade_url=d.get("upgrade_url"),
            raw=d,
        )


# ---------------------------------------------------------------------------
# ML blocks (two shapes: legacy MLScore vs SignalCardML)
# ---------------------------------------------------------------------------


@dataclass
class MLScore:
    """Legacy ML block used by /score and bulk /opportunities.

    Field names here are the LEGACY names (``win_prob``, ``pred_return``,
    ``pred_mfe``). The SignalCard uses :class:`SignalCardML`, whose names differ
    (``ml_win_prob``, ``pred_return_pct``, ``pred_mfe_pct``).

    ``note`` is present only on /score items that were left unscored because the
    daily ML allowance ran out mid-batch.
    """

    ml_score: Optional[float] = None
    win_prob: Optional[float] = None
    pred_return: Optional[float] = None
    pred_mfe: Optional[float] = None
    note: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "MLScore":
        d = _as_dict(data)
        return cls(
            ml_score=d.get("ml_score"),
            win_prob=d.get("win_prob"),
            pred_return=d.get("pred_return"),
            pred_mfe=d.get("pred_mfe"),
            note=d.get("note"),
            raw=d,
        )


@dataclass
class SignalCardML:
    """ML block as it appears on a SignalCard.

    Note ``ml_win_prob`` (the model's predicted probability) is DISTINCT from
    the card's ``stats.historical_win_rate`` (share of profitable years).
    """

    ml_score: Optional[float] = None
    ml_win_prob: Optional[float] = None
    pred_return_pct: Optional[float] = None
    pred_mfe_pct: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> Optional["SignalCardML"]:
        if not isinstance(data, dict):
            return None
        d = _as_dict(data)
        return cls(
            ml_score=d.get("ml_score"),
            ml_win_prob=d.get("ml_win_prob"),
            pred_return_pct=d.get("pred_return_pct"),
            pred_mfe_pct=d.get("pred_mfe_pct"),
            raw=d,
        )


# ---------------------------------------------------------------------------
# Opportunity (bulk primitive)
# ---------------------------------------------------------------------------


@dataclass
class Opportunity:
    """A ranked seasonal trade setup from /opportunities. Returns are percents.

    ``win_rate`` is the REAL historical win rate (share of profitable years),
    distinct from ``ml.win_prob``. It may be ``None`` on the bulk list for rows
    past the per-row enrichment cap.
    """

    symbol: Optional[str] = None
    market: Optional[str] = None
    direction: Optional[str] = None
    entry_date: Optional[str] = None
    days_out: Optional[int] = None
    sharpe_ratio: Optional[float] = None
    avg_profit_pct: Optional[float] = None
    median_profit_pct: Optional[float] = None
    win_rate: Optional[float] = None
    years: Optional[str] = None
    ml: Optional[MLScore] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "Opportunity":
        d = _as_dict(data)
        ml_raw = d.get("ml")
        return cls(
            symbol=d.get("symbol"),
            market=d.get("market"),
            direction=d.get("direction"),
            entry_date=d.get("entry_date"),
            days_out=d.get("days_out"),
            sharpe_ratio=d.get("sharpe_ratio"),
            avg_profit_pct=d.get("avg_profit_pct"),
            median_profit_pct=d.get("median_profit_pct"),
            win_rate=d.get("win_rate"),
            years=d.get("years"),
            ml=MLScore.from_dict(ml_raw) if isinstance(ml_raw, dict) else None,
            raw=d,
        )


@dataclass
class OpportunityList:
    """The /opportunities response - single entry-date ranked list.

    ``window_supported`` is always false: this primitive does not widen across a
    date window (use :meth:`tradewave.Client.scan`). ``evaluated_count`` and
    ``enrichment_capped`` report the per-row win_rate enrichment cap so the
    ``min_win_rate`` filter is never silently misleading.
    """

    entry_date: Optional[str] = None
    window_supported: Optional[bool] = None
    evaluated_count: Optional[int] = None
    enrichment_capped: Optional[bool] = None
    ml_remaining_today: Optional[int] = None
    opportunities: List[Opportunity] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "OpportunityList":
        d = _as_dict(data)
        return cls(
            entry_date=d.get("entry_date"),
            window_supported=d.get("window_supported"),
            evaluated_count=d.get("evaluated_count"),
            enrichment_capped=d.get("enrichment_capped"),
            ml_remaining_today=d.get("ml_remaining_today"),
            opportunities=[
                Opportunity.from_dict(o) for o in _as_list(d.get("opportunities"))
            ],
            raw=d,
        )


# ---------------------------------------------------------------------------
# SignalCard and its sub-objects
# ---------------------------------------------------------------------------


@dataclass
class SignalSetup:
    """Timing of a setup. Dates only - no price levels."""

    entry_date: Optional[str] = None
    entry_window: Optional[str] = None
    hold_days: Optional[int] = None
    exit_date: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "SignalSetup":
        d = _as_dict(data)
        return cls(
            entry_date=d.get("entry_date"),
            entry_window=d.get("entry_window"),
            hold_days=d.get("hold_days"),
            exit_date=d.get("exit_date"),
            raw=d,
        )


@dataclass
class SignalStats:
    """Headline percent-only stats on a SignalCard. No price levels."""

    historical_win_rate: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    avg_return_pct: Optional[float] = None
    median_return_pct: Optional[float] = None
    years: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "SignalStats":
        d = _as_dict(data)
        return cls(
            historical_win_rate=d.get("historical_win_rate"),
            sharpe_ratio=d.get("sharpe_ratio"),
            avg_return_pct=d.get("avg_return_pct"),
            median_return_pct=d.get("median_return_pct"),
            years=d.get("years"),
            raw=d,
        )


@dataclass
class YearReturn:
    """A single year's seasonal return (best_year / worst_year)."""

    year: Optional[str] = None
    return_pct: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> Optional["YearReturn"]:
        if not isinstance(data, dict):
            return None
        d = _as_dict(data)
        return cls(year=d.get("year"), return_pct=d.get("return_pct"), raw=d)


@dataclass
class PerYearRow:
    """One per-year row of historical evidence in receipts."""

    year: Optional[str] = None
    return_pct: Optional[float] = None
    result: Optional[str] = None  # "win" | "loss"
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "PerYearRow":
        d = _as_dict(data)
        return cls(
            year=d.get("year"),
            return_pct=d.get("return_pct"),
            result=d.get("result"),
            raw=d,
        )


@dataclass
class CurveSummary:
    """Shape summary of the HOLD SECTION (entry to exit) of the seasonal curve.

    ``peak_day`` / ``trough_day`` are days INTO the hold (0 = entry).
    """

    shape: Optional[str] = None
    trend: Optional[str] = None  # "rising" | "falling" | "flat"
    change_pts: Optional[float] = None
    peak_day: Optional[int] = None
    trough_day: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> Optional["CurveSummary"]:
        if not isinstance(data, dict):
            return None
        d = _as_dict(data)
        return cls(
            shape=d.get("shape"),
            trend=d.get("trend"),
            change_pts=d.get("change_pts"),
            peak_day=d.get("peak_day"),
            trough_day=d.get("trough_day"),
            raw=d,
        )


@dataclass
class TrackRecordSummary:
    """Live forward-tested record of past daily picks."""

    count: Optional[int] = None
    win_count: Optional[int] = None
    win_rate: Optional[float] = None
    avg_return_pct: Optional[float] = None
    note: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> Optional["TrackRecordSummary"]:
        if not isinstance(data, dict):
            return None
        d = _as_dict(data)
        return cls(
            count=d.get("count"),
            win_count=d.get("win_count"),
            win_rate=d.get("win_rate"),
            avg_return_pct=d.get("avg_return_pct"),
            note=d.get("note"),
            raw=d,
        )


@dataclass
class Receipts:
    """The trust layer - per-year historical evidence. Returns are percents.

    ``live_track_record`` is present ONLY on the daily-pick card.
    """

    years_tested: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    historical_win_rate: Optional[float] = None
    avg_return_pct: Optional[float] = None
    median_return_pct: Optional[float] = None
    best_year: Optional[YearReturn] = None
    worst_year: Optional[YearReturn] = None
    per_year: List[PerYearRow] = field(default_factory=list)
    curve_summary: Optional[CurveSummary] = None
    source: Optional[str] = None
    as_of: Optional[str] = None
    live_track_record: Optional[TrackRecordSummary] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "Receipts":
        d = _as_dict(data)
        return cls(
            years_tested=d.get("years_tested"),
            wins=d.get("wins"),
            losses=d.get("losses"),
            historical_win_rate=d.get("historical_win_rate"),
            avg_return_pct=d.get("avg_return_pct"),
            median_return_pct=d.get("median_return_pct"),
            best_year=YearReturn.from_dict(d.get("best_year")),
            worst_year=YearReturn.from_dict(d.get("worst_year")),
            per_year=[PerYearRow.from_dict(r) for r in _as_list(d.get("per_year"))],
            curve_summary=CurveSummary.from_dict(d.get("curve_summary")),
            source=d.get("source"),
            as_of=d.get("as_of"),
            live_track_record=TrackRecordSummary.from_dict(
                d.get("live_track_record")
            ),
            raw=d,
        )


@dataclass
class OrderTicket:
    """Broker-agnostic, copyable order ticket. Carries NO price level."""

    side: Optional[str] = None
    symbol: Optional[str] = None
    type: Optional[str] = None
    time_in_force: Optional[str] = None
    suggested_entry_date: Optional[str] = None
    suggested_exit_date: Optional[str] = None
    note: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> Optional["OrderTicket"]:
        if not isinstance(data, dict):
            return None
        d = _as_dict(data)
        return cls(
            side=d.get("side"),
            symbol=d.get("symbol"),
            type=d.get("type"),
            time_in_force=d.get("time_in_force"),
            suggested_entry_date=d.get("suggested_entry_date"),
            suggested_exit_date=d.get("suggested_exit_date"),
            note=d.get("note"),
            raw=d,
        )


@dataclass
class SetReminder:
    """A suggested seasonal-entry reminder."""

    type: Optional[str] = None
    fire_on: Optional[str] = None
    message: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> Optional["SetReminder"]:
        if not isinstance(data, dict):
            return None
        d = _as_dict(data)
        return cls(
            type=d.get("type"),
            fire_on=d.get("fire_on"),
            message=d.get("message"),
            raw=d,
        )


@dataclass
class NextStep:
    """The no-broker last mile. ``order_ticket`` is omitted on NO_SIGNAL."""

    headline: Optional[str] = None
    order_ticket: Optional[OrderTicket] = None
    copy_text: Optional[str] = None
    set_reminder: Optional[SetReminder] = None
    framing: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> Optional["NextStep"]:
        if not isinstance(data, dict):
            return None
        d = _as_dict(data)
        return cls(
            headline=d.get("headline"),
            order_ticket=OrderTicket.from_dict(d.get("order_ticket")),
            copy_text=d.get("copy_text"),
            set_reminder=SetReminder.from_dict(d.get("set_reminder")),
            framing=d.get("framing"),
            raw=d,
        )


@dataclass
class SignalCard:
    """THE unit returned by /scan, /analyze/{symbol} and /daily-pick.

    SIGNALS ONLY - all movement is percentages; ``next_step.order_ticket``
    carries no price level. ``ml`` is ``None`` (not absent) when the
    ML-eligible-market quota is exhausted or the market is not ML-eligible;
    ``tier_notes`` carries the context in that case. ``signal`` is one of
    ``BUY`` / ``SELL`` / ``NO_SIGNAL`` (NO_SIGNAL = low conviction; no order
    ticket).
    """

    rank: Optional[int] = None
    symbol: Optional[str] = None
    market: Optional[MarketRef] = None
    direction: Optional[str] = None
    signal: Optional[str] = None
    setup: Optional[SignalSetup] = None
    edge_score: Optional[int] = None
    edge_basis: Optional[str] = None
    stats: Optional[SignalStats] = None
    ml: Optional[SignalCardML] = None
    receipts: Optional[Receipts] = None
    next_step: Optional[NextStep] = None
    headline: Optional[str] = None
    verdict: Optional[str] = None
    disclaimer: Optional[str] = None
    tier_notes: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> Optional["SignalCard"]:
        if not isinstance(data, dict):
            return None
        d = _as_dict(data)
        return cls(
            rank=d.get("rank"),
            symbol=d.get("symbol"),
            market=MarketRef.from_dict(d.get("market")),
            direction=d.get("direction"),
            signal=d.get("signal"),
            setup=SignalSetup.from_dict(d.get("setup")),
            edge_score=d.get("edge_score"),
            edge_basis=d.get("edge_basis"),
            stats=SignalStats.from_dict(d.get("stats")),
            ml=SignalCardML.from_dict(d.get("ml")),
            receipts=Receipts.from_dict(d.get("receipts")),
            next_step=NextStep.from_dict(d.get("next_step")),
            headline=d.get("headline"),
            verdict=d.get("verdict"),
            disclaimer=d.get("disclaimer"),
            tier_notes=d.get("tier_notes"),
            raw=d,
        )

    @property
    def is_actionable(self) -> bool:
        """True when the card carries an actionable BUY/SELL (not NO_SIGNAL)."""
        return self.signal in ("BUY", "SELL")


# ---------------------------------------------------------------------------
# Flagship envelopes
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    """The /scan response - ranked SignalCards plus enrichment metadata.

    ``summary`` is the server's plain-English honesty line (what was evaluated,
    what was shown, any degradation). ``capped_by_plan`` is true when the list
    was cut short by the plan's row cap rather than by the filters;
    ``shown_of_evaluated`` ("N of M") and ``upgrade_url`` (present only when
    capped) carry the wall context.
    """

    generated_at: Optional[str] = None
    summary: Optional[str] = None
    window: Optional[str] = None
    rank_by: Optional[str] = None
    count: Optional[int] = None
    evaluated_count: Optional[int] = None
    enrichment_capped: Optional[bool] = None
    capped_by_plan: Optional[bool] = None
    shown_of_evaluated: Optional[str] = None
    upgrade_url: Optional[str] = None
    ml_remaining_today: Optional[int] = None
    opportunities: List[SignalCard] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "ScanResult":
        d = _as_dict(data)
        cards = [
            c
            for c in (SignalCard.from_dict(o) for o in _as_list(d.get("opportunities")))
            if c is not None
        ]
        return cls(
            generated_at=d.get("generated_at"),
            summary=d.get("summary"),
            window=d.get("window"),
            rank_by=d.get("rank_by"),
            count=d.get("count"),
            evaluated_count=d.get("evaluated_count"),
            enrichment_capped=d.get("enrichment_capped"),
            capped_by_plan=d.get("capped_by_plan"),
            shown_of_evaluated=d.get("shown_of_evaluated"),
            upgrade_url=d.get("upgrade_url"),
            ml_remaining_today=d.get("ml_remaining_today"),
            opportunities=cards,
            raw=d,
        )

    def __iter__(self):
        """Iterate the ranked SignalCards directly."""
        return iter(self.opportunities)

    def __len__(self) -> int:
        return len(self.opportunities)


@dataclass
class CompactSetup:
    """A compact alternate setup (percent stats only; no card/receipts/ml)."""

    symbol: Optional[str] = None
    direction: Optional[str] = None
    entry_date: Optional[str] = None
    hold_days: Optional[int] = None
    historical_win_rate: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    avg_return_pct: Optional[float] = None
    median_return_pct: Optional[float] = None
    years: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "CompactSetup":
        d = _as_dict(data)
        return cls(
            symbol=d.get("symbol"),
            direction=d.get("direction"),
            entry_date=d.get("entry_date"),
            hold_days=d.get("hold_days"),
            historical_win_rate=d.get("historical_win_rate"),
            sharpe_ratio=d.get("sharpe_ratio"),
            avg_return_pct=d.get("avg_return_pct"),
            median_return_pct=d.get("median_return_pct"),
            years=d.get("years"),
            raw=d,
        )


@dataclass
class AnalyzeResult:
    """The /analyze/{symbol} response - one rich card plus alternate setups."""

    card: Optional[SignalCard] = None
    other_setups: List[CompactSetup] = field(default_factory=list)
    as_of: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "AnalyzeResult":
        d = _as_dict(data)
        return cls(
            card=SignalCard.from_dict(d.get("card")),
            other_setups=[
                CompactSetup.from_dict(s) for s in _as_list(d.get("other_setups"))
            ],
            as_of=d.get("as_of"),
            raw=d,
        )


# ---------------------------------------------------------------------------
# Patterns / seasonal chart
# ---------------------------------------------------------------------------


@dataclass
class Pattern:
    """Aggregate seasonal-pattern statistics. No raw price series.

    ``win_rate`` is the REAL historical win rate (share of profitable years).
    ``stats`` is the publishable percent-only stat block (kept as a raw dict so
    new keys flow through without a model bump).
    """

    symbol: Optional[str] = None
    market: Optional[str] = None
    win_rate: Optional[float] = None
    stats: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "Pattern":
        d = _as_dict(data)
        return cls(
            symbol=d.get("symbol"),
            market=d.get("market"),
            win_rate=d.get("win_rate"),
            stats=_as_dict(d.get("stats")),
            raw=d,
        )


@dataclass
class SeasonalPoint:
    """One point on the seasonal curve. ``index`` is a 0-100 shape, not a price."""

    date: Optional[str] = None
    index: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "SeasonalPoint":
        d = _as_dict(data)
        return cls(date=d.get("date"), index=d.get("index"), raw=d)


@dataclass
class SeasonalChart:
    """The seasonal trendchart as DATA: a year-averaged 0-100 normalized curve.

    ``seasonal_curve`` is a relative SHAPE, not price levels and not a percent
    return - prices cannot be reconstructed.
    """

    symbol: Optional[str] = None
    market: Optional[str] = None
    direction: Optional[str] = None
    entry_date: Optional[str] = None
    days_out: Optional[int] = None
    years: Optional[str] = None
    win_rate: Optional[float] = None
    seasonal_curve: List[SeasonalPoint] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "SeasonalChart":
        d = _as_dict(data)
        return cls(
            symbol=d.get("symbol"),
            market=d.get("market"),
            direction=d.get("direction"),
            entry_date=d.get("entry_date"),
            days_out=d.get("days_out"),
            years=d.get("years"),
            win_rate=d.get("win_rate"),
            seasonal_curve=[
                SeasonalPoint.from_dict(p) for p in _as_list(d.get("seasonal_curve"))
            ],
            stats=_as_dict(d.get("stats")),
            raw=d,
        )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@dataclass
class ScoreResult:
    """The /score response (the scored variant).

    ``granted`` is how many items were actually scored - it may be less than
    requested if the daily allowance ran out mid-batch; items beyond ``granted``
    appear in ``scores`` with a ``note`` and no ML fields.

    When the daily allowance was ALREADY fully spent before the request, the API
    returns a 200 limit stub instead; the SDK surfaces that as
    :class:`MLDailyLimit` (``ScoreResult.requires`` is set in that case).
    """

    scores: List[MLScore] = field(default_factory=list)
    granted: Optional[int] = None
    ml_remaining_today: Optional[int] = None
    # Populated only when the response was the daily-limit stub:
    requires: Optional[str] = None
    reason: Optional[str] = None
    message: Optional[str] = None
    upgrade_url: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "ScoreResult":
        d = _as_dict(data)
        return cls(
            scores=[MLScore.from_dict(s) for s in _as_list(d.get("scores"))],
            granted=d.get("granted"),
            ml_remaining_today=d.get("ml_remaining_today"),
            requires=d.get("requires"),
            reason=d.get("reason"),
            message=d.get("message"),
            upgrade_url=d.get("upgrade_url"),
            raw=d,
        )

    @property
    def limit_reached(self) -> bool:
        """True when this is the daily-ML-limit stub (no scores granted)."""
        return self.requires is not None or self.reason == "ml_daily_limit"


@dataclass
class MLDailyLimit:
    """The graceful daily-ML-limit stub (HTTP 200, NOT an error).

    Returned by /score when the allowance is already fully spent. This is data,
    never an exception - check ``ScoreResult.limit_reached`` or branch on the
    presence of ``requires``.
    """

    requires: Optional[str] = None
    reason: Optional[str] = None
    message: Optional[str] = None
    upgrade_url: Optional[str] = None
    ml_remaining_today: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "MLDailyLimit":
        d = _as_dict(data)
        return cls(
            requires=d.get("requires"),
            reason=d.get("reason"),
            message=d.get("message"),
            upgrade_url=d.get("upgrade_url"),
            ml_remaining_today=d.get("ml_remaining_today"),
            raw=d,
        )


# ---------------------------------------------------------------------------
# Daily pick / track record
# ---------------------------------------------------------------------------


@dataclass
class DailyPickResult:
    """The /daily-pick response - the pick as a SignalCard plus its record."""

    card: Optional[SignalCard] = None
    featured_date: Optional[str] = None
    track_record: Optional[TrackRecordSummary] = None
    as_of: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "DailyPickResult":
        d = _as_dict(data)
        return cls(
            card=SignalCard.from_dict(d.get("card")),
            featured_date=d.get("featured_date"),
            track_record=TrackRecordSummary.from_dict(d.get("track_record")),
            as_of=d.get("as_of"),
            raw=d,
        )


@dataclass
class TrackRecordPick:
    """One realized pick in the track record."""

    symbol: Optional[str] = None
    featured_date: Optional[str] = None
    return_pct: Optional[float] = None
    result: Optional[str] = None  # "win" | "loss" | "open"
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "TrackRecordPick":
        d = _as_dict(data)
        return cls(
            symbol=d.get("symbol"),
            featured_date=d.get("featured_date"),
            return_pct=d.get("return_pct"),
            result=d.get("result"),
            raw=d,
        )


@dataclass
class TrackRecord:
    """The /daily-pick/track-record response - realized win/loss of past picks."""

    summary: Optional[TrackRecordSummary] = None
    picks: List[TrackRecordPick] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Any) -> "TrackRecord":
        d = _as_dict(data)
        summary_raw = d.get("summary")
        return cls(
            summary=TrackRecordSummary.from_dict(summary_raw)
            if summary_raw is not None
            else None,
            picks=[TrackRecordPick.from_dict(p) for p in _as_list(d.get("picks"))],
            raw=d,
        )
