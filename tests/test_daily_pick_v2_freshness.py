"""V2 daily-pick freshness, loud failure, homepage no-pick, and outage gap."""

import datetime as dt
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
APPSERVER_DIR = ROOT / "appserver" / "appserver"
if str(APPSERVER_DIR) not in sys.path:
    sys.path.insert(0, str(APPSERVER_DIR))

from data_updater.eod_readiness import (  # noqa: E402
    build_status_marker,
    evaluate_eod_readiness,
    terminal_row_fingerprint,
    validate_success_marker,
)
from ml_checkpoint_context import _legacy_v2_metadata  # noqa: E402


# Production V2 /health. No provenance fields.
V2_HEALTH = {
    "feature_count": 59,
    "status": "ok",
    "tiers": ["10_30", "31_60", "61_90"],
    "uptime_seconds": 86400,
    "vix_cutoff": 35,
}
SESSION = dt.date(2026, 10, 8)


def load_module(monkeypatch, relative):
    monkeypatch.syspath_prepend(str(ROOT / "site/lib"))
    monkeypatch.setitem(sys.modules, "config", SimpleNamespace(
        appserver_url="http://engine",
        ml_scorer_url="http://scorer",
        SERVICE_API_KEY="test-key",
    ))
    spec = importlib.util.spec_from_file_location(
        "daily_pick_v2_under_test", ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _observation(key, day):
    return {
        "state": "verified",
        "terminal_date": day,
        "terminal_row_fingerprint": terminal_row_fingerprint([key, day, 1.0]),
    }


def complete_marker(session):
    """A marker validate_success_marker accepts for this completed session."""
    session_iso = session.isoformat()
    targets = {
        "US": ["S%03d" % index for index in range(100)],
        "ETF": ["E%03d" % index for index in range(25)],
    }
    observations = {
        "%s:%s" % (exchange, symbol): _observation(
            "%s:%s" % (exchange, symbol), session_iso)
        for exchange, symbols in targets.items()
        for symbol in symbols
    }
    readiness = evaluate_eod_readiness(
        targets_by_exchange=targets,
        observations=observations,
        completed_session=session,
        resource_ids=["0", "1", "2", "3", "4", "11"],
    )
    marker = build_status_marker(
        base={
            "started_at": "2026-10-09T07:00:00+00:00",
            "completed_at": "2026-10-09T07:05:00+00:00",
            "market_date": session_iso,
            "target_table_date": (session + dt.timedelta(days=1)).isoformat(),
            "latest_us_date": session_iso,
            "total": 125,
            "updated": 125,
            "skipped": 0,
            "missing": 0,
            "failed": 0,
            "source": "http://update-server/",
        },
        readiness=readiness,
    )
    assert validate_success_marker(
        marker, expected_completed_session=session_iso)
    return marker


def _health_response(payload):
    return SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: payload,
    )


def test_v2_health_payload_has_no_provenance_fields():
    assert set(V2_HEALTH) == {
        "feature_count", "status", "tiers", "uptime_seconds", "vix_cutoff",
    }
    assert V2_HEALTH["feature_count"] == 59
    assert V2_HEALTH["vix_cutoff"] == 35
    assert V2_HEALTH["status"] == "ok"


def test_v2_health_passes_when_eod_session_is_complete(monkeypatch):
    module = load_module(monkeypatch, "site/lib/daily_pattern_picks.py")
    marker = complete_marker(SESSION)
    monkeypatch.setattr(
        module, "latest_completed_us_equity_session", lambda: SESSION)
    monkeypatch.setattr(
        module.requests, "get", lambda *a, **k: _health_response(V2_HEALTH))
    monkeypatch.setattr(module, "load_authoritative_eod_marker", lambda: marker)
    posted = {}

    def post(*_a, **_k):
        posted["called"] = True
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"picks": [{"symbol": "AAA"}]},
        )

    monkeypatch.setattr(module.requests, "post", post)
    identity = module.current_pick_data_identity()
    contract = _legacy_v2_metadata(V2_HEALTH, "http://scorer")
    assert identity["data_as_of"] == "2026-10-08"
    assert identity["model_release"] == "v2-legacy-59"
    assert identity["model_manifest_hash"] == contract["model_manifest_hash"]
    assert identity["feature_schema_hash"] == contract["feature_schema_hash"]
    assert identity["data_generation_hash"] == marker["generation_fingerprint"]
    assert identity["data_generation_hash"] != contract["data_generation_hash"]
    result = module.get_daily_picks(
        "2026-10-09", ["2"], 1, "l", 10, 30, 5, 0.8)
    assert posted["called"] is True
    assert result["metadata"]["data_as_of"] == "2026-10-08"
    assert result["picks"] == [{"symbol": "AAA"}]


@pytest.mark.parametrize("marker_change", ["stale", "incomplete", "missing"])
def test_v2_stale_or_incomplete_eod_is_refused(monkeypatch, marker_change):
    module = load_module(monkeypatch, "site/lib/daily_pattern_picks.py")
    monkeypatch.setattr(
        module, "latest_completed_us_equity_session", lambda: SESSION)
    monkeypatch.setattr(
        module.requests, "get", lambda *a, **k: _health_response(V2_HEALTH))
    monkeypatch.setattr(
        module.requests, "post", lambda *a, **k: pytest.fail("stale scorer was called"))
    if marker_change == "missing":
        monkeypatch.setattr(module, "load_authoritative_eod_marker", lambda: None)
        match = "scorer data through None"
    elif marker_change == "stale":
        stale = complete_marker(dt.date(2026, 10, 7))
        monkeypatch.setattr(module, "load_authoritative_eod_marker", lambda: stale)
        match = "through 2026-10-07"
    else:
        incomplete = complete_marker(SESSION)
        incomplete["ok"] = False
        monkeypatch.setattr(
            module, "load_authoritative_eod_marker", lambda: incomplete)
        match = "incomplete"
    with pytest.raises(RuntimeError, match=match):
        module.get_daily_picks("2026-10-09", ["2"], 1, "l", 10, 30, 5, 0.8)


def load_home():
    site_dir = str(ROOT / "site")
    if site_dir not in sys.path:
        sys.path.insert(0, site_dir)
    # The homepage generator imports blog_tools, which pulls pandas and
    # matplotlib. These tests only need the publication decision, so the
    # chart helper stays a stub.
    sys.modules.setdefault("blog_tools", SimpleNamespace(
        get_company_name=lambda *_a, **_k: "Co",
        convert_param_base64=lambda *_a, **_k: "abc",
    ))
    spec = importlib.util.spec_from_file_location(
        "tw_generate_home_page", ROOT / "site/generate_home_page.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_pick_exits_nonzero_and_alerts():
    home = load_home()

    calls = []

    def alert(subject, body):
        calls.append((subject, body))
        return False

    code = home.publication_exit_code(
        None, content_only=False, failure_reason="ML scorer call failed: deferred",
        alert=alert)
    assert code == 1
    assert calls and "not published" in calls[0][0]
    assert "No pick today" in calls[0][1]
    assert "UHS" not in calls[0][1]
    assert home.publication_exit_code(
        {"symbol": "AAA"}, content_only=False, failure_reason=None, alert=alert,
    ) == 0
    assert home.publication_exit_code(
        None, content_only=True, failure_reason="ignored", alert=alert,
    ) == 0
    assert len(calls) == 1


def test_homepage_no_pick_state_does_not_reuse_prior_symbol():
    home = load_home()

    prior = [{
        "symbol": "UHS",
        "featured_date": "2026-09-16",
        "ml_score": 80,
        "win_prob": 0.9,
    }]
    assert home.featured_pick_for_page(
        None, content_only=False, history=prior) is None
    state = home.no_pick_state()
    assert state["headline"] == "No pick today"
    assert state["published_today"] is False
    assert "UHS" not in state["message"]

    env = Environment(
        loader=FileSystemLoader(str(ROOT / "site/templates")),
        autoescape=True,
    )
    html = env.get_template("_daily_pick_status.html").render(content={
        "daily_pick_state": state,
        "outage_notices": home.outage_notices(),
    })
    assert "No pick today" in html
    assert "UHS" not in html
    assert "2026-09-17" in html
    assert "2026-10-09" in html
    homepage = (ROOT / "site/templates/index-dark-blue.html").read_text()
    scorecard = (ROOT / "site/templates/scorecard.html").read_text()
    assert '_daily_pick_status.html' in homepage
    assert '_daily_pick_status.html' in scorecard
    assert "No pick today" in homepage


def test_outage_gap_is_excluded_from_track_record_stats(monkeypatch):
    site_lib = str(ROOT / "site/lib")
    if site_lib not in sys.path:
        sys.path.insert(0, site_lib)
    from pick_stats import compute_win_rate, countable_picks
    from apiserver import appserver_client as ac

    history = [
        {"symbol": "UHS", "featured_date": "2026-09-16", "status": "closed",
         "actual_return": 1.2, "peak_return": 0.4, "pred_return": 3.0},
        {"symbol": "NOPE", "featured_date": "2026-09-18", "status": "closed",
         "actual_return": -4.0, "peak_return": 0.2, "pred_return": 3.0},
        {"symbol": "GAP", "featured_date": "2026-09-17",
         "record_type": "scorer_outage"},
        {"symbol": "AFTER", "featured_date": "2026-10-12", "status": "closed",
         "actual_return": 2.0, "peak_return": 0.1, "pred_return": 3.0},
    ]
    kept = [row["symbol"] for row in countable_picks(history)]
    assert kept == ["UHS", "AFTER"]
    win_rate, wins, judged = compute_win_rate(history)
    assert (win_rate, wins, judged) == (100, 2, 2)

    monkeypatch.setattr(ac, "_load_featured_history", lambda: history)
    record = ac.track_record()
    assert [row["symbol"] for row in record["picks"]] == ["UHS", "AFTER"]
    assert record["summary"]["count"] == 2
    assert record["summary"]["judged_count"] == 2
    assert record["summary"]["win_count"] == 2
    assert record["summary"]["win_rate"] == 1.0
    assert record["summary"]["outage_gaps"][0]["start"] == "2026-09-17"
    assert record["summary"]["outage_gaps"][0]["end"] == "2026-10-09"
    pick = ac.daily_pick()
    assert pick["symbol"] == "AFTER"
    assert pick["symbol"] != "GAP"


def test_gap_date_does_not_call_the_scorer_or_write_history(monkeypatch):
    home = load_home()

    monkeypatch.setattr(home, "load_featured_history", lambda: [{
        "symbol": "UHS", "featured_date": "2026-09-16",
    }])
    monkeypatch.setattr(home, "save_featured_history",
                        lambda _history: pytest.fail("history was written"))
    monkeypatch.setattr(
        home, "get_daily_picks",
        lambda **_k: pytest.fail("scorer was called during the outage gap"))
    monkeypatch.setattr(
        home, "new_york_now",
        lambda: dt.datetime(2026, 9, 18, 3, 0, tzinfo=ZoneInfo("America/New_York")))
    assert home.select_featured_from_ml_scorer() is None
    assert "No backfill" in home.select_featured_from_ml_scorer.failure_reason
