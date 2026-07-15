"""The TradeWave API client.

Usage::

    from tradewave import Client

    with Client(api_key="tw_live_...") as tw:
        pick = tw.daily_pick()
        print(pick.card.headline)

        scan = tw.scan(window="now", min_win_rate=0.6)
        for card in scan:
            print(card.rank, card.symbol, card.edge_score, card.headline)

The API key may also be supplied via the ``TRADEWAVE_API_KEY`` environment
variable, in which case ``Client()`` needs no arguments.

Every method returns a typed model (see :mod:`tradewave.models`); each model
also exposes ``.raw`` (the parsed JSON dict) so you are never blocked by a model
lag. For endpoints where you want the untouched payload, pass ``raw=True`` to
get the parsed dict directly.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional, Union

import requests

from ._http import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    HTTPClient,
)
from .errors import TradeWaveError
from .models import (
    AnalyzeResult,
    DailyPickResult,
    Market,
    Me,
    MLDailyLimit,
    Opportunity,
    OpportunityList,
    Pattern,
    ScanResult,
    ScoreResult,
    SeasonalChart,
    Symbol,
    TrackRecord,
)

_ENV_KEY = "TRADEWAVE_API_KEY"


class Client:
    """Synchronous client for the TradeWave Data API (v1).

    Args:
        api_key: Your TradeWave API key (``tw_live_...``). Falls back to the
            ``TRADEWAVE_API_KEY`` environment variable when omitted.
        base_url: Override the API base URL. When omitted, the
            ``TRADEWAVE_API_URL`` (then ``TRADEWAVE_BASE_URL``) environment
            variable is honored, else the default
            ``https://api.tradewave.ai/v1``.
        timeout: Per-request timeout in seconds (default 30).
        max_retries: Automatic retries on 429/5xx with exponential backoff and
            jitter (default 3). 4xx other than 429 are never retried.
        session: Provide your own ``requests.Session`` (advanced). If omitted,
            the client creates and owns one.

    The client is a context manager - prefer ``with Client(...) as tw:`` so the
    underlying session is closed for you.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        session: Optional[requests.Session] = None,
    ) -> None:
        key = api_key or os.environ.get(_ENV_KEY)
        if not key:
            raise TradeWaveError(
                "No API key provided. Pass api_key=... or set the "
                f"{_ENV_KEY} environment variable."
            )
        self._http = HTTPClient(
            key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            session=session,
        )

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP session (no-op for a borrowed session)."""
        self._http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def rate_limit(self) -> Dict[str, str]:
        """The ``X-RateLimit-*`` headers from the most recent response, if any."""
        return dict(self._http.last_rate_limit)

    # -- internal ----------------------------------------------------------

    def _get(self, path: str, params: Optional[Mapping[str, Any]] = None) -> Any:
        return self._http.request("GET", path, params=params)

    def _post(self, path: str, json: Any) -> Any:
        return self._http.request("POST", path, json=json)

    # -- identity ------------------------------------------------------------

    def me(self, *, raw: bool = False) -> Union[Me, dict]:
        """Identity + capabilities for your API key.

        Returns the plan tier, the ML allowance left today
        (``ml_remaining_today``, ``None`` = unlimited), the per-call row cap
        (``opp_limit``), the rate limits, and the markets in scope. Reads only -
        never consumes ML allowance.

        Maps to ``GET /me``.
        """
        data = self._get("/me")
        return data if raw else Me.from_dict(data)

    # -- markets -----------------------------------------------------------

    def list_markets(self, *, raw: bool = False) -> Union[List[Market], dict]:
        """List the 15 markets and the caller's access scope.

        Maps to ``GET /markets``.
        """
        data = self._get("/markets")
        if raw:
            return data
        items = data.get("markets") if isinstance(data, dict) else None
        return [Market.from_dict(m) for m in (items or [])]

    def list_symbols(
        self,
        market: str,
        *,
        prefix: Optional[str] = None,
        limit: Optional[int] = None,
        raw: bool = False,
    ) -> Union[List[Symbol], dict]:
        """List the symbols in a market.

        A full market is large (the S&P 500 list alone is ~150KB), so the
        endpoint pages: ``prefix`` filters by ticker prefix (case-insensitive)
        and ``limit`` caps the rows returned. Pass ``raw=True`` to see the
        ``total`` / ``matched`` / ``count`` truncation counters.

        Args:
            market: Permanent resource key ``'0'..'16'``.
            prefix: Ticker-prefix filter, e.g. ``'AA'`` (case-insensitive).
            limit: Cap the rows returned.

        Maps to ``GET /markets/{id}/symbols``.
        """
        data = self._get(
            f"/markets/{market}/symbols", {"prefix": prefix, "limit": limit}
        )
        if raw:
            return data
        items = data.get("symbols") if isinstance(data, dict) else None
        return [Symbol.from_dict(s) for s in (items or [])]

    # -- opportunities -----------------------------------------------------

    def opportunities(
        self,
        market: str,
        *,
        from_: Optional[str] = None,
        direction: Optional[str] = None,
        min_win_rate: Optional[float] = None,
        limit: Optional[int] = None,
        to: Optional[str] = None,
        raw: bool = False,
    ) -> Union[OpportunityList, dict]:
        """Ranked seasonal opportunities for one market at a single entry date.

        This is the single-entry-date primitive; it does NOT widen across a date
        window (use :meth:`scan` for windows). ``to`` is accepted but ignored by
        the API (``window_supported`` is always false).

        Args:
            market: Market id ``'0'..'16'`` (required).
            from_: Entry date (``YYYY-MM-DD``) to evaluate; defaults to today on
                the server. Sent on the wire as ``from`` (a Python reserved
                word, hence the trailing underscore).
            direction: ``'long'`` or ``'short'``.
            min_win_rate: Filter on the REAL historical win rate (0..1), not the
                ML win probability.
            limit: Tier-capped row limit.
            to: Accepted but ignored - does not widen the window.

        Maps to ``GET /opportunities``.
        """
        params = {
            "market": market,
            "from": from_,
            "to": to,
            "direction": direction,
            "min_win_rate": min_win_rate,
            "limit": limit,
        }
        data = self._get("/opportunities", params)
        return data if raw else OpportunityList.from_dict(data)

    def opportunities_for_symbol(
        self, symbol: str, *, market: str, raw: bool = False
    ) -> Union[List[Opportunity], dict]:
        """Every seasonal setup for one symbol (no enrichment).

        Args:
            symbol: The symbol, e.g. ``'AAPL'``.
            market: Market id ``'0'..'16'`` (required).

        Maps to ``GET /opportunities/{symbol}``.
        """
        data = self._get(f"/opportunities/{symbol}", {"market": market})
        if raw:
            return data
        items = data.get("opportunities") if isinstance(data, dict) else None
        return [Opportunity.from_dict(o) for o in (items or [])]

    # -- flagship: scan ----------------------------------------------------

    def scan(
        self,
        *,
        markets: Optional[str] = None,
        window: Optional[str] = None,
        direction: Optional[str] = None,
        min_win_rate: Optional[float] = None,
        min_years: Optional[int] = None,
        rank_by: Optional[str] = None,
        limit: Optional[int] = None,
        raw: bool = False,
    ) -> Union[ScanResult, dict]:
        """FLAGSHIP. Scan selected markets for the best seasonal setups.

        Returns ranked :class:`~tradewave.models.PatternCard` objects. ML fields
        populate inline on ML-eligible markets up to the caller's daily ML
        allowance; ``ml_remaining_today`` on the result reflects what remains
        (``None`` = unlimited).

        Args:
            markets: CSV of ids or aliases, e.g. ``'2,11'`` or ``'sp500,etf'``.
                Omit for the liquid-equities core (DOW 30, NASDAQ 100,
                S&P 500, ETFs) intersected with the caller's scope; pass markets
                explicitly to scan others.
            window: ``'now'`` (default) | ``'next_2_weeks'`` | ``'next_month'``
                | a ``'from..to'`` range. ``'now'`` = setups whose entry date is
                within the next ~10 trading days.
            direction: ``'long'`` or ``'short'``.
            min_win_rate: Filter on historical win rate (share of profitable
                years), 0..1. NOT the ML win probability.
            min_years: Trust filter - require ``years_tested >= N``.
            rank_by: ``'edge'`` | ``'win_rate'`` | ``'sharpe'`` (default) |
                ``'ml'`` | ``'avg_return'``.
            limit: Tier-capped result count.

        Maps to ``GET /scan``.
        """
        params = {
            "markets": markets,
            "window": window,
            "direction": direction,
            "min_win_rate": min_win_rate,
            "min_years": min_years,
            "rank_by": rank_by,
            "limit": limit,
        }
        data = self._get("/scan", params)
        return data if raw else ScanResult.from_dict(data)

    # -- flagship: analyze -------------------------------------------------

    def analyze(
        self,
        symbol: str,
        *,
        market: Optional[str] = None,
        direction: Optional[str] = None,
        days_out: Optional[int] = None,
        raw: bool = False,
    ) -> Union[AnalyzeResult, dict]:
        """FLAGSHIP. Deep-dive one symbol into one rich PatternCard + alternates.

        Args:
            symbol: The symbol to analyze.
            market: Permanent resource key ``'0'..'16'``. Optional - resolved if
                the symbol is unique.
            direction: ``'long'`` or ``'short'``.
            days_out: Holding period in days.

        Maps to ``GET /analyze/{symbol}``.
        """
        params = {
            "market": market,
            "direction": direction,
            "days_out": days_out,
        }
        data = self._get(f"/analyze/{symbol}", params)
        return data if raw else AnalyzeResult.from_dict(data)

    # -- patterns / chart --------------------------------------------------

    def pattern(
        self, market: str, symbol: str, *, raw: bool = False
    ) -> Union[Pattern, dict]:
        """Aggregate seasonal-pattern stats for a symbol (no price series).

        Args:
            market: Market id ``'0'..'16'``.
            symbol: The symbol.

        Maps to ``GET /patterns/{market}/{symbol}``.
        """
        data = self._get(f"/patterns/{market}/{symbol}")
        return data if raw else Pattern.from_dict(data)

    def seasonal_chart(
        self,
        *,
        market: str,
        symbol: str,
        entry_date: Optional[str] = None,
        days_out: Optional[int] = None,
        direction: Optional[str] = None,
        years: Optional[str] = None,
        raw: bool = False,
    ) -> Union[SeasonalChart, dict]:
        """Seasonal trendchart as DATA - a year-averaged 0-100 normalized curve.

        The ``index`` on each point is a relative seasonal SHAPE, never a price;
        prices cannot be reconstructed.

        Args:
            market: Market id ``'0'..'16'`` (required).
            symbol: The symbol (required).
            entry_date: Start of the annual cycle (``YYYY-MM-DD``).
            days_out: Echoed for parity; does not change the full-cycle curve.
            direction: ``'long'`` or ``'short'``.
            years: Lookback window label (stays a string).

        Maps to ``GET /seasonal-chart``.
        """
        params = {
            "market": market,
            "symbol": symbol,
            "entry_date": entry_date,
            "days_out": days_out,
            "direction": direction,
            "years": years,
        }
        data = self._get("/seasonal-chart", params)
        return data if raw else SeasonalChart.from_dict(data)

    # -- scoring -----------------------------------------------------------

    def score(
        self,
        opportunities: List[Mapping[str, Any]],
        *,
        market: Optional[str] = None,
        raw: bool = False,
    ) -> Union[ScoreResult, MLDailyLimit, dict]:
        """ML scores for a batch of opportunities (all tiers, metered per day).

        Args:
            opportunities: A list of dicts, each with the keys ``symbol``,
                ``date``, ``days_out``, and ``direction``.
            market: One ML-eligible market id for the whole batch. Defaults to
                ``'2'`` server-side. Do not put a market inside individual items.

        Returns a :class:`~tradewave.models.ScoreResult` with the scored items,
        ``granted`` (how many were actually scored) and ``ml_remaining_today``.

        IMPORTANT: when the daily ML allowance was ALREADY fully spent, the API
        responds (HTTP 200) with the graceful upgrade nudge - this is NOT an
        error. The SDK surfaces it as :class:`~tradewave.models.MLDailyLimit`
        (check ``isinstance(result, MLDailyLimit)`` or
        ``result.limit_reached``). It is never raised.

        Maps to ``POST /score``.
        """
        body: Dict[str, Any] = {"opportunities": list(opportunities)}
        if market is not None:
            body["market"] = market
        data = self._post("/score", body)
        if raw:
            return data
        # The 200 limit stub has 'requires'/'reason' and no 'scores' array.
        if isinstance(data, dict) and "scores" not in data and (
            data.get("requires") is not None or data.get("reason") == "ml_daily_limit"
        ):
            return MLDailyLimit.from_dict(data)
        return ScoreResult.from_dict(data)

    # -- daily pick --------------------------------------------------------

    def daily_pick(self, *, raw: bool = False) -> Union[DailyPickResult, dict]:
        """Today's AI pick as a PatternCard, with its live track record.

        The card's ``receipts.live_track_record`` carries the forward-tested
        record of past picks; ``track_record`` echoes it at the top level.

        Maps to ``GET /daily-pick``.
        """
        data = self._get("/daily-pick")
        return data if raw else DailyPickResult.from_dict(data)

    def daily_pick_track_record(
        self, *, raw: bool = False
    ) -> Union[TrackRecord, dict]:
        """Historical track record of past daily picks (realized win/loss).

        Maps to ``GET /daily-pick/track-record``.
        """
        data = self._get("/daily-pick/track-record")
        return data if raw else TrackRecord.from_dict(data)
