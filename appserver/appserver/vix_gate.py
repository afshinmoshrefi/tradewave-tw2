"""Make the scorer's VIX pause checkable by users (2026-11-24).

The AI scorer pauses scoring when its latest VIX close is above its cutoff and
reports "VIX=<value> exceeds cutoff (<limit>)". This module, applied when score
responses leave the appserver (Wave Viewer and Tara):

1. fills the VIX value on paused items that lack it (results cached before the
   value was kept) from other paused items in the same response: the gate is one
   global switch, so every paused item shares the scorer's value;
2. adds the real close date of that value from TradeWave's own VIX history
   (INDX/VIX), only when a recent completed close matches it;
3. if TradeWave's own latest completed VIX close is at or under the limit while the
   scorer still reports a pause, the scorer is working from stale data: the item is
   reported as "AI scores are temporarily unavailable" instead of blaming volatility.

Everything is fail-soft: if the history cannot be read, responses pass through.
"""
from __future__ import annotations

import copy
import datetime as dt
import logging
import math
import threading
import time
from typing import Any, Callable, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

_NY = ZoneInfo("America/New_York")
_CACHE: dict = {"at": 0.0, "rows": None}
_LOCK = threading.Lock()
_TTL_SECONDS = 600
_DATE_SEARCH_CLOSES = 15
STALE_MESSAGE = "AI scores are temporarily unavailable."


def _default_loader() -> List[Tuple[str, float]]:
    from get_symbol_csv import get_symbol_csv  # appserver module; imported lazily
    df = get_symbol_csv("VIX", "INDX")
    rows = []
    for date, close in zip(df["date"].tolist(), df["close"].tolist()):
        rows.append((str(date)[:10], float(close)))
    return rows


def _history(loader: Optional[Callable[[], List[Tuple[str, float]]]] = None) -> List[Tuple[str, float]]:
    if loader is not None:
        return list(loader())
    with _LOCK:
        if _CACHE["rows"] is not None and time.time() - _CACHE["at"] < _TTL_SECONDS:
            return list(_CACHE["rows"])
    rows = _default_loader()
    with _LOCK:
        _CACHE.update(rows=rows, at=time.time())
    return list(rows)


def completed_closes(rows: List[Tuple[str, float]], now: Optional[dt.datetime] = None) -> List[Tuple[str, float]]:
    """Daily closes that are final: before today's US market date, plus today after 16:30 ET."""
    now_ny = (now or dt.datetime.now(dt.timezone.utc)).astimezone(_NY)
    today = now_ny.date().isoformat()
    after_close = (now_ny.hour, now_ny.minute) >= (16, 30)
    out = []
    for date, close in rows:
        if not isinstance(close, (int, float)) or not math.isfinite(close) or close <= 0:
            continue
        if date < today or (date == today and after_close):
            out.append((date, float(close)))
    return sorted(out)


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _paused_errors(node: Any, found: list) -> None:
    if isinstance(node, dict):
        err = node.get("error")
        if isinstance(err, dict) and str(err.get("code") or "").lower() == "vix_blocked":
            found.append((node, err))
        for value in node.values():
            _paused_errors(value, found)
    elif isinstance(node, list):
        for value in node:
            _paused_errors(value, found)


def _close_date_for(value: float, closes: List[Tuple[str, float]]) -> Optional[str]:
    for date, close in reversed(closes[-_DATE_SEARCH_CLOSES:]):
        if abs(round(close, 2) - value) <= 0.005 or abs(round(close, 1) - value) <= 1e-9:
            return date
    return None


def annotate_scores(scores: Any, now: Optional[dt.datetime] = None,
                    loader: Optional[Callable[[], List[Tuple[str, float]]]] = None) -> Any:
    """Return a copy of `scores` with VIX pause facts added (see module doc)."""
    try:
        found: list = []
        _paused_errors(scores, found)
        if not found:
            return scores
        scores = copy.deepcopy(scores)
        found = []
        _paused_errors(scores, found)
        value = next((v for v in (_number(e.get("vix_value")) for _, e in found) if v is not None), None)
        cutoff = next((v for v in (_number(e.get("vix_cutoff")) for _, e in found) if v is not None), None)
        closes = completed_closes(_history(loader), now)
        latest = closes[-1] if closes else None
        close_date = _close_date_for(value, closes) if value is not None else None
        for item, err in found:
            limit = _number(err.get("vix_cutoff")) or cutoff
            if latest is not None and limit is not None and latest[1] <= limit:
                err.update(code="provider_unavailable", message=STALE_MESSAGE, retryable=True,
                           stale_vix_gate=True, latest_vix_close=round(latest[1], 2),
                           latest_vix_date=latest[0])
                if item.get("vix_blocked") is True:
                    item["vix_blocked"] = False
                if str(item.get("reason") or "").lower() == "vix_blocked":
                    item["reason"] = "provider_unavailable"
                continue
            if _number(err.get("vix_value")) is None and value is not None:
                err["vix_value"] = round(value, 2)
            if _number(err.get("vix_cutoff")) is None and cutoff is not None:
                err["vix_cutoff"] = round(cutoff, 2)
            own = _number(err.get("vix_value"))
            date = close_date if own is not None and value is not None and abs(own - value) < 1e-9 else (
                _close_date_for(own, closes) if own is not None else None)
            if date:
                err["vix_date"] = date
            else:
                err.pop("vix_date", None)
        return scores
    except Exception:  # noqa: BLE001 - never break score responses
        log.warning("VIX pause annotation skipped", exc_info=True)
        return scores
