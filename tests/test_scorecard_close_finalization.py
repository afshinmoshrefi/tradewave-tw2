import datetime as dt
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = REPO_ROOT / "site"
SITE_LIB = SITE_DIR / "lib"
for candidate in (SITE_DIR, SITE_LIB):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import generate_scorecard as scorecard
from market_clock import NEW_YORK


def _entry():
    return {
        "featured_date": "2026-07-01",
        "resource_id": 2,
        "symbol": "TEST",
        "date": "2026-07-01",
        "daysOut": 22,
        "direction": "l",
        "start_price": 100.0,
        "status": "closed",
        "end_price": 90.0,
        "actual_return": -10.0,
        "win": False,
    }


def _isolate_network(monkeypatch):
    monkeypatch.setattr(scorecard, "save_history", lambda history: None)
    monkeypatch.setattr(
        scorecard, "fetch_realtime_prices_bulk", lambda symbols: {}
    )
    monkeypatch.setattr(
        scorecard, "fetch_current_price", lambda *args: 101.0
    )
    monkeypatch.setattr(
        scorecard, "fetch_peak_price", lambda *args: 110.0
    )


def test_same_day_bar_does_not_close_before_market_finalization(
    monkeypatch,
):
    _isolate_network(monkeypatch)
    monkeypatch.setattr(
        scorecard,
        "fetch_end_price",
        lambda *args: {"price": 105.0, "session_date": "2026-07-23"},
    )
    history = [_entry()]
    before_close = dt.datetime(2026, 7, 23, 15, 30, tzinfo=NEW_YORK)

    scorecard.enrich_positions(history, "token", now=before_close)

    assert history[0]["status"] == "open"
    assert "actual_return" not in history[0]
    assert "resolved_session_date" not in history[0]


def test_final_bar_closes_and_records_actual_resolution_session(
    monkeypatch,
):
    _isolate_network(monkeypatch)
    monkeypatch.setattr(
        scorecard,
        "fetch_end_price",
        lambda *args: {"price": 105.0, "session_date": "2026-07-23"},
    )
    history = [_entry()]
    after_close = dt.datetime(2026, 7, 23, 17, 0, tzinfo=NEW_YORK)

    scorecard.enrich_positions(history, "token", now=after_close)

    assert history[0]["status"] == "closed"
    assert history[0]["actual_return"] == 5.0
    assert history[0]["resolved_session_date"] == "2026-07-23"
    assert history[0]["peak_return"] == 10.0
    assert history[0]["result_finalized_at"]


def test_missing_bar_never_falls_back_to_stale_close(monkeypatch):
    class Response:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "ChartHistorical2": [
                    ["2026-07-21", 1, 1, 1, 90, 1],
                    ["2026-07-22", 1, 1, 1, 91, 1],
                ]
            }

    monkeypatch.setattr(scorecard.requests, "get", lambda *args, **kwargs: Response())

    assert scorecard.fetch_end_price(2, "TEST", "2026-07-23", "token") is None
