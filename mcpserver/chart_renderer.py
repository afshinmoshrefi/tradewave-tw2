"""TradeWave charts for MCP image content, drawn by the shared chart system.

TW-TASK-0014 item 5: MCP images come from ``twcharts.chartkit`` - the same visual system as
the SMN article charts - instead of a separate MCP-only style. The gateway remains the source
of every number: this module only turns a PatternCard's chart data (percentages and the
normalized seasonal index, never prices) into PNGs, and never calls another service.
"""

from __future__ import annotations

import datetime
import io
import math
from typing import Any

from twcharts import chartkit

_CYCLE_NAMES = {"0": "presidential election years", "1": "post-election years",
                "2": "midterm election years", "3": "pre-election years"}


def _number(v: Any) -> float | None:
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _lookback_label(card: dict[str, Any], n: int) -> str:
    """'8 midterm election years' for a PE slice; '' for a consecutive lookback."""
    years = str((card.get("stats") or {}).get("years") or "")
    if years.startswith("pe") and "-" in years:
        phase = years[2:].split("-", 1)[0]
        name = _CYCLE_NAMES.get(phase)
        if name:
            return f"{n} {name}"
    return ""


def _setup(card: dict[str, Any]) -> tuple[str, str, int]:
    setup = card.get("setup") or {}
    return (str(setup.get("entry_date") or ""), str(setup.get("exit_date") or ""),
            int(setup.get("hold_days") or 0))


def _year_rows(card: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [r for r in ((card.get("chart") or {}).get("per_year_bars") or [])
            if isinstance(r, dict) and _number(r.get("net_pct")) is not None]
    return sorted(rows, key=lambda r: str(r.get("year")))


def render_year_evidence_chart(card: dict[str, Any]) -> tuple[bytes, dict[str, Any]] | None:
    """Per-year bars with the full intra-window range needles (SMN 'bars_mae_mfe')."""
    rows = _year_rows(card)
    if not rows:
        return None
    direction = str(card.get("direction") or "long").lower()
    years, nets, mfe, mae = [], [], [], []
    for row in rows:
        net, fav, adv = _number(row.get("net_pct")), _number(row.get("mfe_pct")), _number(row.get("mae_pct"))
        # Card bars are trade-relative; the chart system uses the price convention
        # ("positive = price rose") and states the direction in its title.
        if direction == "short":
            net, fav, adv = -net, (-adv if adv is not None else None), (-fav if fav is not None else None)
        years.append(int(row["year"]))
        nets.append(net)
        mfe.append(fav if fav is not None else 0.0)
        mae.append(adv if adv is not None else 0.0)
    entry, exit_, hold = _setup(card)
    meta = {"symbol": str(card.get("symbol") or ""), "direction": direction,
            "window_start": entry, "window_end": exit_, "days": hold or "",
            "lookback_label": _lookback_label(card, len(years)), "variant": "bars_mae_mfe"}
    buf = io.BytesIO()
    semantics = chartkit.record_bars(years, nets, meta, buf, mfe=mfe, mae=mae)
    return buf.getvalue(), semantics


def render_trend_chart(card: dict[str, Any]) -> tuple[bytes, dict[str, Any]] | None:
    """The normalized seasonal path with the trade window shaded (SMN 'trend')."""
    points = [(str(p.get("date") or ""), _number(p.get("index")))
              for p in ((card.get("chart") or {}).get("trend_chart") or []) if isinstance(p, dict)]
    points = [(d, v) for d, v in points if d and v is not None]
    entry, exit_, hold = _setup(card)
    if len(points) < 2 or not entry or not exit_:
        return None
    rows = _year_rows(card)
    n = len(rows)
    symbol = str(card.get("symbol") or "")
    label = _lookback_label(card, n)
    span = label or f"the past {n} years"
    first = datetime.date.fromisoformat(points[0][0])
    meta = {"symbol": symbol, "n": n, "days": hold or "",
            "year_first": rows[0]["year"] if rows else "", "year_last": rows[-1]["year"] if rows else "",
            "lookback_label": label,
            # The MCP curve is anchored at the entry date (no pre-roll), so say that.
            "spec": (f"{symbol}'s average seasonal path over {span}, from "
                     f"{first.strftime('%b %d').replace(' 0', ' ')} · shaded: the {hold}-day window")}
    if label and rows:
        # A PE slice is not consecutive: "3-year average (2014-2022)" would misstate it.
        meta["source"] = (f"Source: TradeWave seasonal database · average of the {label} "
                          f"({rows[0]['year']}–{rows[-1]['year']}) · not a forecast")
    buf = io.BytesIO()
    semantics = chartkit.trend_window([d for d, _ in points], [v for _, v in points], entry, exit_,
                                      str(card.get("direction") or "long"), meta, buf)
    return buf.getvalue(), semantics


def render_card_charts(card: dict[str, Any]) -> list[tuple[str, bytes]]:
    """Return (alt text, PNG) pairs in the recommended evidence order."""
    rendered: list[tuple[str, bytes]] = []
    for renderer in (render_year_evidence_chart, render_trend_chart):
        result = renderer(card)
        if result:
            png, semantics = result
            rendered.append((semantics.get("alt") or semantics.get("title") or "TradeWave chart", png))
    return rendered
