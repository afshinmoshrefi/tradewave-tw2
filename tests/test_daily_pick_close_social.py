import datetime as dt
import json
import sys
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = REPO_ROOT / "site"
SITE_LIB = SITE_DIR / "lib"
for candidate in (SITE_DIR, SITE_LIB):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import daily_pick_close_card as close_card
import m_daily_pick_close_social as close_social


def _entry(symbol, actual, peak, target, hit=False):
    return {
        "symbol": symbol,
        "featured_date": "2026-07-01",
        "date": "2026-07-01",
        "daysOut": 22,
        "end_date": "2026-07-23",
        "status": "closed",
        "resolved_session_date": "2026-07-23",
        "actual_return": actual,
        "peak_return": target + 0.1 if hit else peak,
        "pred_return": target,
    }


def test_combines_wins_and_losses_in_one_bounded_factual_post():
    entries = [
        _entry("ALGN", 2.15, 9.9, 5.7, hit=True),
        _entry("EPAM", 1.08, 3.78, 6.3),
        _entry("BLDR", -21.39, 2.52, 6.0),
    ]

    message = close_social.compose_close_message(
        entries,
        "2026-07-23",
        "https://tradewave.ai/close-ledger/2026-07-23.html",
    )

    assert "3 AI windows closed: 2 wins, 1 loss." in message
    assert "ALGN" in message and "target" in message
    assert "EPAM" in message and "+1.1%" in message
    assert "BLDR" in message and "-21.4%" in message
    assert close_social.estimated_x_length(message) <= 280


def test_five_results_still_fit_and_every_symbol_is_listed():
    entries = [
        _entry("ALGN", 2.1, 9.9, 5.7, hit=True),
        _entry("EPAM", 1.1, 3.8, 6.3),
        _entry("BLDR", -21.4, 2.5, 6.0),
        _entry("AAPL", -1.2, 1.0, 4.0),
        _entry("MSFT", 0.8, 2.1, 3.0),
    ]

    message = close_social.compose_close_message(
        entries,
        "2026-07-23",
        "https://tradewave.ai/close-ledger/2026-07-23.html",
    )

    assert close_social.estimated_x_length(message) <= 280
    assert all(entry["symbol"] in message for entry in entries)


def test_selects_only_results_resolved_on_that_market_session():
    today = _entry("TODAY", 1, 2, 3)
    prior = dict(
        _entry("PRIOR", 1, 2, 3),
        resolved_session_date="2026-07-22",
    )

    assert close_social.closing_entries([prior, today], "2026-07-23") == [
        today
    ]


def test_generates_large_image_and_unique_link_page(tmp_path):
    entries = [
        _entry("ALGN", 2.15, 9.9, 5.7, hit=True),
        _entry("BLDR", -21.39, 2.52, 6.0),
    ]

    assets = close_card.generate_close_assets(
        entries, "2026-07-23", tmp_path, "https://tradewave.ai/"
    )

    image_path = Path(assets["image_path"])
    page_path = Path(assets["page_path"])
    with Image.open(image_path) as image:
        assert image.size == (1200, 630)
        assert image.mode == "RGB"
    page = page_path.read_text(encoding="utf-8")
    assert 'twitter:card" content="summary_large_image' in page
    assert "daily-close-2026-07-23.png" in page
    assert assets["page_url"].endswith("/close-ledger/2026-07-23.html")


def test_send_with_no_closures_writes_no_close_lock_and_never_calls_x(
    tmp_path, monkeypatch, capsys
):
    history_path = tmp_path / "featured_history.json"
    history_path.write_text("[]", encoding="utf-8")
    completed_at = dt.datetime.now(dt.timezone.utc).isoformat()
    monkeypatch.setattr(close_social.config, "tw2_env", "prod")
    monkeypatch.setattr(
        close_social.config, "X_CLOSE_POSTING_ENABLED", True, raising=False
    )
    monkeypatch.setattr(
        close_social,
        "fetch_eod_status",
        lambda: {
            "ok": True,
            "market_date": "2026-07-23",
            "latest_us_date": "2026-07-23",
            "completed_at": completed_at,
        },
    )
    monkeypatch.setattr(close_social, "regenerate_scorecard", lambda: None)
    monkeypatch.setattr(
        close_social,
        "post_to_x",
        lambda message: (_ for _ in ()).throw(AssertionError("X called")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "m_daily_pick_close_social.py",
            "--send",
            "--history",
            str(history_path),
            "--lock-dir",
            str(tmp_path),
        ],
    )

    assert close_social.main() == 0
    lock = close_social.read_lock(str(tmp_path), "2026-07-23")
    assert lock["status"] == "no_closures"
    assert "no X post" in capsys.readouterr().out


def test_crons_follow_keyprovider_then_appserver_then_close_publisher():
    eod = (REPO_ROOT / "ops" / "install_eod_cron.sh").read_text(
        encoding="utf-8"
    )
    social = (
        REPO_ROOT / "ops" / "install_daily_ai_pick_social_cron.sh"
    ).read_text(encoding="utf-8")
    deploy = (REPO_ROOT / "ops" / "deploy.sh").read_text(encoding="utf-8")

    assert "5 3-5 * * 2-6" in eod
    assert "/var/lib/tradewave/eod/update_status.json" in (
        REPO_ROOT / "data_updater" / "update_client2.py"
    ).read_text(encoding="utf-8")
    assert "*/10 3-6 * * 2-6" in social
    assert "m_daily_pick_close_social.py --send" in social
    assert 'bash "$repo/ops/install_eod_cron.sh"' in deploy
