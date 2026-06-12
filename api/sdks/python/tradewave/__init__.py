"""tradewave - official Python SDK for the TradeWave Data API (v1).

Seasonal trading opportunities and ML win-probability signals for the 17
TradeWave markets, plus the tracked daily AI pick. Derived signals only - no raw
market data.

Quickstart::

    from tradewave import Client

    with Client(api_key="tw_live_...") as tw:   # or set TRADEWAVE_API_KEY
        print(tw.daily_pick().card.headline)
        for card in tw.scan(window="now", min_win_rate=0.6):
            print(card.rank, card.symbol, card.edge_score)
"""

from __future__ import annotations

__version__ = "0.1.1"

from .client import Client
from .errors import (
    AuthError,
    ConnectionError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutError,
    TradeWaveError,
)
from .models import (
    AnalyzeResult,
    CompactSetup,
    CurveSummary,
    DailyPickResult,
    Market,
    MarketRef,
    Me,
    MLDailyLimit,
    MLScore,
    NextStep,
    Opportunity,
    OpportunityList,
    OrderTicket,
    Pattern,
    PerYearRow,
    Receipts,
    ScanResult,
    ScoreResult,
    SeasonalChart,
    SeasonalPoint,
    SetReminder,
    SignalCard,
    SignalCardML,
    SignalSetup,
    SignalStats,
    Symbol,
    TrackRecord,
    TrackRecordPick,
    TrackRecordSummary,
    YearReturn,
)

__all__ = [
    "__version__",
    # client
    "Client",
    # errors
    "TradeWaveError",
    "AuthError",
    "RateLimitError",
    "NotFoundError",
    "ServerError",
    "TimeoutError",
    "ConnectionError",
    # models
    "AnalyzeResult",
    "CompactSetup",
    "CurveSummary",
    "DailyPickResult",
    "Market",
    "MarketRef",
    "Me",
    "MLDailyLimit",
    "MLScore",
    "NextStep",
    "Opportunity",
    "OpportunityList",
    "OrderTicket",
    "Pattern",
    "PerYearRow",
    "Receipts",
    "ScanResult",
    "ScoreResult",
    "SeasonalChart",
    "SeasonalPoint",
    "SetReminder",
    "SignalCard",
    "SignalCardML",
    "SignalSetup",
    "SignalStats",
    "Symbol",
    "TrackRecord",
    "TrackRecordPick",
    "TrackRecordSummary",
    "YearReturn",
]
