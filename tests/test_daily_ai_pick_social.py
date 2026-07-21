import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = REPO_ROOT / "site"
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))

import m_daily_ai_pick_social as social


@pytest.fixture
def pick():
    return {
        "featured_date": "2026-07-21",
        "symbol": "AAPL",
        "date": "2026-07-21",
        "end_date": "2026-08-10",
        "daysOut": 20,
        "direction": "long",
        "avg_profit": 8.4,
        "sharpe_ratio": 1.72,
        "years": "pe1-6",
        "win_prob": 0.81,
    }


def test_loads_exact_canonical_featured_date(tmp_path, pick):
    history = tmp_path / "featured_history.json"
    history.write_text(json.dumps([
        {**pick, "featured_date": "2026-07-18", "symbol": "MSFT"},
        pick,
    ]), encoding="utf-8")

    loaded = social.load_featured_pick(str(history), "2026-07-21")

    assert loaded["symbol"] == "AAPL"


def test_rejects_stale_canonical_history(tmp_path, pick):
    history = tmp_path / "featured_history.json"
    history.write_text(json.dumps([
        {**pick, "featured_date": "2026-07-18"},
    ]), encoding="utf-8")

    with pytest.raises(social.DailyPickError, match="newest ledger record is 2026-07-18"):
        social.load_featured_pick(str(history), "2026-07-21")


def test_composes_bounded_factual_x_post(pick):
    message = social.compose_x_message(pick, "https://tradewave.ai/scorecard.html")

    assert "Today's TradeWave AI Pick: $AAPL" in message
    assert "Long seasonal window" in message
    assert "Hist avg 8.4%" in message
    assert "Sharpe 1.72" in message
    assert "6 PE+1 samples" in message
    assert "Est. win probability: 81%" in message
    assert "https://tradewave.ai/scorecard.html" in message
    assert len(social._CASHTAG_RE.findall(message)) == 1
    assert social.estimated_x_length(message) <= 280


def test_compose_rejects_more_than_one_cashtag():
    with pytest.raises(social.DailyPickError, match="only one cashtag"):
        social.validate_x_message("$AAPL and $MSFT")


def test_posts_directly_to_x_and_requires_created_id(monkeypatch):
    monkeypatch.setattr(social.config, "X_API_KEY", "key", raising=False)
    monkeypatch.setattr(social.config, "X_API_KEY_SECRET", "secret", raising=False)
    monkeypatch.setattr(social.config, "X_ACCESS_TOKEN", "token", raising=False)
    monkeypatch.setattr(social.config, "X_ACCESS_TOKEN_SECRET", "token-secret", raising=False)
    auth_calls = []
    monkeypatch.setattr(social, "OAuth1", lambda *values: auth_calls.append(values) or "oauth")
    request = {}

    class Response:
        status_code = 201

        @staticmethod
        def json():
            return {"data": {"id": "12345", "text": "hello"}}

    def fake_post(url, **kwargs):
        request["url"] = url
        request.update(kwargs)
        return Response()

    result = social.post_to_x("hello", http_post=fake_post)

    assert result == {
        "ok": True,
        "status": 201,
        "post_id": "12345",
        "post_url": "https://x.com/i/web/status/12345",
    }
    assert request["url"] == "https://api.x.com/2/tweets"
    assert request["json"] == {"text": "hello"}
    assert request["auth"] == "oauth"
    assert auth_calls == [("key", "secret", "token", "token-secret")]


def test_does_not_treat_201_without_post_id_as_success(monkeypatch):
    monkeypatch.setattr(social.config, "X_API_KEY", "key", raising=False)
    monkeypatch.setattr(social.config, "X_API_KEY_SECRET", "secret", raising=False)
    monkeypatch.setattr(social.config, "X_ACCESS_TOKEN", "token", raising=False)
    monkeypatch.setattr(social.config, "X_ACCESS_TOKEN_SECRET", "token-secret", raising=False)
    monkeypatch.setattr(social, "OAuth1", lambda *values: "oauth")

    class Response:
        status_code = 201

        @staticmethod
        def json():
            return {"data": {}}

    result = social.post_to_x("hello", http_post=lambda *args, **kwargs: Response())

    assert result["ok"] is False


def test_success_lock_round_trip_is_per_featured_date(tmp_path, pick):
    result = {
        "post_id": "12345",
        "post_url": "https://x.com/i/web/status/12345",
    }

    social.write_post_lock(str(tmp_path), "2026-07-21", pick, result)

    lock = social.read_post_lock(str(tmp_path), "2026-07-21")
    assert lock["provider"] == "x-direct"
    assert lock["symbol"] == "AAPL"
    assert lock["post_id"] == "12345"
    assert social.read_post_lock(str(tmp_path), "2026-07-22") is None


def test_main_dry_run_never_calls_x(tmp_path, pick, monkeypatch, capsys):
    history = tmp_path / "featured_history.json"
    history.write_text(json.dumps([pick]), encoding="utf-8")
    monkeypatch.setattr(social, "post_to_x", lambda message: pytest.fail("network called"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "m_daily_ai_pick_social.py",
            "--date",
            "2026-07-21",
            "--history",
            str(history),
            "--lock-dir",
            str(tmp_path),
        ],
    )

    assert social.main() == 0
    assert "DRY-RUN: nothing was posted" in capsys.readouterr().out


def test_main_send_skips_all_nonproduction_environments(
    tmp_path, pick, monkeypatch, capsys
):
    history = tmp_path / "featured_history.json"
    history.write_text(json.dumps([pick]), encoding="utf-8")
    monkeypatch.setattr(social.config, "tw2_env", "staging")
    monkeypatch.setattr(social.config, "X_POSTING_ENABLED", True, raising=False)
    monkeypatch.setattr(social, "post_to_x", lambda message: pytest.fail("network called"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "m_daily_ai_pick_social.py",
            "--send",
            "--date",
            "2026-07-21",
            "--history",
            str(history),
            "--lock-dir",
            str(tmp_path),
        ],
    )

    assert social.main() == 0
    assert "X writes are production-only" in capsys.readouterr().out


def test_release_installs_social_cron_after_homepage_writer():
    installer = (
        REPO_ROOT / "ops" / "install_daily_ai_pick_social_cron.sh"
    ).read_text(encoding="utf-8")
    bulletproof = (
        REPO_ROOT / "ops" / "staging" / "make_bulletproof.sh"
    ).read_text(encoding="utf-8")

    canonical_schedule = "10 7 * * 1-5"
    assert canonical_schedule in installer
    assert canonical_schedule in bulletproof
    assert "m_daily_ai_pick_social.py' || true" in installer
    assert bulletproof.index("generate_home_page.py") < bulletproof.index(
        "m_daily_ai_pick_social.py --send"
    )


def test_routine_deploy_installs_social_cron():
    deploy = (REPO_ROOT / "ops" / "deploy.sh").read_text(encoding="utf-8")

    assert 'bash "$repo/ops/install_daily_ai_pick_social_cron.sh"' in deploy
