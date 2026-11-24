"""The VIX pause users see is decided and shown from the live VIX (2026-11-24).

The AI scorer refuses to score while ITS latest VIX is above its cutoff and reports
"VIX=<value> exceeds cutoff (<limit>)". The scorer's VIX can be stale: on Nov 24 the
staging scorer still held the Nov 20 close (35.89) while the live VIX was about 27.
The scorer's gate now uses the live VIX itself (ml_scorer live_vix.py) and reports
vix_source="live" with the value and time it used; such a decision is kept as is.
For a scorer without that gate (the legacy v2 scorer), this module, applied when
score responses leave the appserver (Wave Viewer and Tara), checks every paused item
against TradeWave's live VIX quote:

1. live VIX above the limit: the pause is real. The item shows the live value and the
   time of that quote (vix_value, vix_source="live", vix_time). The scorer's own value
   is kept as scorer_vix_value.
2. live VIX at or under the limit: the scorer is working from stale data. The item is
   reported as "AI scores are temporarily unavailable" (retryable) instead of blaming
   volatility. The pause result is also cached for 5 minutes at most
   (ml_checkpoint_context.PAUSE_CACHE_SECONDS), so real scores return within minutes
   once the scorer refreshes.
3. no live quote: TradeWave's latest completed daily VIX close is used the same way
   (vix_source="close", vix_date).

Scores the scorer returns are never touched: only a refusal can become a pause.
Everything is fail-soft: if no VIX can be read, responses pass through unchanged.
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
_CACHE: dict = {"at": 0.0, "rows": None, "live_at": 0.0, "live": None}
_LOCK = threading.Lock()
_HISTORY_TTL_SECONDS = 600
_LIVE_TTL_SECONDS = 60
_LIVE_MAX_AGE_SECONDS = 4 * 24 * 3600   # a quote older than this is not "live"
STALE_MESSAGE = "AI scores are temporarily unavailable."
LiveQuote = Tuple[float, Optional[float]]   # (value, epoch seconds of the quote)


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


# --- sources ------------------------------------------------------------------------

def _default_live_loader() -> Optional[LiveQuote]:
    """Live VIX: the realtime price service, then EODHD real-time (same as the site's market bar)."""
    import requests
    import config  # appserver config; imported lazily
    rt_url = str(getattr(config, "realtime_service_url", "") or "").rstrip("/")
    if rt_url:
        try:
            resp = requests.get(f"{rt_url}/prices/VIX", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                value = _number(data.get("price")) if isinstance(data, dict) and "error" not in data else None
                if value is not None:
                    return value, _number(data.get("timestamp"))
        except Exception:  # noqa: BLE001
            log.info("realtime VIX quote unavailable", exc_info=True)
    token = getattr(config, "EOD_token", "")
    if token:
        resp = requests.get("https://eodhd.com/api/real-time/VIX.INDX",
                            params={"api_token": token, "fmt": "json"}, timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            value = _number(data.get("close")) if isinstance(data, dict) else None
            if value is not None:
                return value, _number(data.get("timestamp"))
    return None


def _default_loader() -> List[Tuple[str, float]]:
    from get_symbol_csv import get_symbol_csv  # appserver module; imported lazily
    df = get_symbol_csv("VIX", "INDX")
    return [(str(date)[:10], float(close)) for date, close in zip(df["date"].tolist(), df["close"].tolist())]


def _history(loader: Optional[Callable[[], List[Tuple[str, float]]]] = None) -> List[Tuple[str, float]]:
    if loader is not None:
        return list(loader())
    with _LOCK:
        if _CACHE["rows"] is not None and time.time() - _CACHE["at"] < _HISTORY_TTL_SECONDS:
            return list(_CACHE["rows"])
    rows = _default_loader()
    with _LOCK:
        _CACHE.update(rows=rows, at=time.time())
    return list(rows)


def _live(live_loader: Optional[Callable[[], Optional[LiveQuote]]] = None) -> Optional[LiveQuote]:
    if live_loader is not None:
        return live_loader()
    with _LOCK:
        if time.time() - _CACHE["live_at"] < _LIVE_TTL_SECONDS:
            return _CACHE["live"]
    try:
        quote = _default_live_loader()
    except Exception:  # noqa: BLE001
        log.info("live VIX quote unavailable", exc_info=True)
        quote = None
    with _LOCK:
        _CACHE.update(live=quote, live_at=time.time())
    return quote


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


def current_vix(now: Optional[dt.datetime] = None,
                live_loader: Optional[Callable[[], Optional[LiveQuote]]] = None,
                loader: Optional[Callable[[], List[Tuple[str, float]]]] = None) -> Optional[dict]:
    """The VIX users should see: live quote first, else the latest completed close."""
    now = now or dt.datetime.now(dt.timezone.utc)
    quote = _live(live_loader)
    if quote is not None:
        value, stamp = quote
        if stamp is None or abs(now.timestamp() - stamp) <= _LIVE_MAX_AGE_SECONDS:
            when = dt.datetime.fromtimestamp(stamp, dt.timezone.utc) if stamp else now
            return {"value": round(value, 2), "source": "live",
                    "time": when.astimezone(_NY).isoformat(timespec="minutes")}
    try:
        closes = completed_closes(_history(loader), now)
    except Exception:  # noqa: BLE001
        log.info("VIX history unavailable", exc_info=True)
        closes = []
    if closes:
        date, close = closes[-1]
        return {"value": round(close, 2), "source": "close", "date": date}
    return None


# --- annotation ---------------------------------------------------------------------

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


def annotate_scores(scores: Any, now: Optional[dt.datetime] = None,
                    loader: Optional[Callable[[], List[Tuple[str, float]]]] = None,
                    live_loader: Optional[Callable[[], Optional[LiveQuote]]] = None) -> Any:
    """Return a copy of `scores` with each scorer refusal judged against the live VIX."""
    try:
        found: list = []
        _paused_errors(scores, found)
        if not found:
            return scores
        vix = current_vix(now, live_loader, loader)
        if vix is None:
            return scores
        scores = copy.deepcopy(scores)
        found = []
        _paused_errors(scores, found)
        cutoff = next((v for v in (_number(e.get("vix_cutoff")) for _, e in found) if v is not None), None)
        for item, err in found:
            limit = _number(err.get("vix_cutoff")) or cutoff
            if limit is None:
                continue
            if str(err.get("vix_source") or "").lower() == "live" and _number(err.get("vix_value")) is not None:
                # A scorer with the live-VIX gate decided on the live quote and reports
                # the value and time it used: that decision is the source of truth.
                err["vix_cutoff"] = round(limit, 2)
                continue
            scorer_value = _number(err.get("vix_value"))
            if vix["value"] <= limit:
                err.update(code="provider_unavailable", message=STALE_MESSAGE, retryable=True,
                           stale_vix_gate=True, latest_vix=vix["value"], latest_vix_source=vix["source"])
                for key in ("vix_value", "vix_date", "vix_source", "vix_time"):
                    err.pop(key, None)
                if scorer_value is not None:
                    err["scorer_vix_value"] = round(scorer_value, 2)
                if item.get("vix_blocked") is True:
                    item["vix_blocked"] = False
                if str(item.get("reason") or "").lower() == "vix_blocked":
                    item["reason"] = "provider_unavailable"
                continue
            if scorer_value is not None:
                err["scorer_vix_value"] = round(scorer_value, 2)
            err["vix_cutoff"] = round(limit, 2)
            err["vix_value"] = vix["value"]
            err["vix_source"] = vix["source"]
            err.pop("vix_time", None)
            err.pop("vix_date", None)
            if vix["source"] == "live":
                err["vix_time"] = vix["time"]
            else:
                err["vix_date"] = vix["date"]
        return scores
    except Exception:  # noqa: BLE001 - never break score responses
        log.warning("VIX pause annotation skipped", exc_info=True)
        return scores
