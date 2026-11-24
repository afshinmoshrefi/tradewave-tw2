"""vix_gate: a scorer refusal is judged and shown with the live VIX."""
import datetime as dt
import json

import vix_gate
from ml_checkpoint_context import (
    PAUSE_CACHE_SECONDS,
    pause_cache_ttl,
    read_cached_legacy_score,
    vix_gate_details,
    write_cached_legacy_score,
)

HISTORY = [("2026-11-19", 28.44), ("2026-11-20", 35.89), ("2026-11-23", 26.62), ("2026-11-24", 29.54)]
HIGH = [("2026-11-19", 28.44), ("2026-11-20", 35.89), ("2026-11-23", 38.42), ("2026-11-24", 39.1)]
MORNING = dt.datetime(2026, 11, 24, 15, 42, tzinfo=dt.timezone.utc)   # 10:42 ET
QUOTE_TS = MORNING.timestamp()
EVENING = dt.datetime(2026, 11, 24, 22, 0, tzinfo=dt.timezone.utc)


def paused(value=None, cutoff=35.0, **extra):
    err = {"code": "vix_blocked", "message": "AI scoring is paused while volatility is high.", "retryable": False}
    if value is not None:
        err["vix_value"] = value
    if cutoff is not None:
        err["vix_cutoff"] = cutoff
    err.update(extra)
    return {"status": "unavailable", "error": err}


def test_completed_closes_exclude_todays_partial_bar_until_after_the_close():
    assert vix_gate.completed_closes(HISTORY, MORNING)[-1] == ("2026-11-23", 26.62)
    assert vix_gate.completed_closes(HISTORY, EVENING)[-1] == ("2026-11-24", 29.54)


def test_real_pause_shows_the_live_vix_and_quote_time():
    scores = {"A|1|l": {"horizons": [paused(35.89)]}, "B|2|l": paused(None, cutoff=None)}
    out = vix_gate.annotate_scores(scores, now=MORNING, live_loader=lambda: (41.27, QUOTE_TS), loader=lambda: HIGH)
    a = out["A|1|l"]["horizons"][0]["error"]
    b = out["B|2|l"]["error"]
    assert a["code"] == "vix_blocked" and a["vix_value"] == 41.27 and a["vix_source"] == "live"
    assert a["vix_time"] == "2026-11-24T10:42-05:00" and a["scorer_vix_value"] == 35.89
    assert "vix_date" not in a
    assert b["vix_value"] == 41.27 and b["vix_cutoff"] == 35.0      # cached item without values
    assert scores["B|2|l"]["error"].get("vix_value") is None          # input not mutated


def test_stale_scorer_pause_becomes_temporarily_unavailable_when_live_vix_is_under_the_limit():
    # Nov 24: the scorer still says 35.89 (Friday Nov 20) but the live VIX is 27.26.
    out = vix_gate.annotate_scores({"A|1|l": paused(35.89)}, now=MORNING,
                                   live_loader=lambda: (27.26, QUOTE_TS), loader=lambda: HISTORY)
    err = out["A|1|l"]["error"]
    assert err["code"] == "provider_unavailable" and err["message"] == "AI scores are temporarily unavailable."
    assert err["stale_vix_gate"] is True and err["retryable"] is True
    assert err["latest_vix"] == 27.26 and err["latest_vix_source"] == "live"
    assert "vix_value" not in err and err["scorer_vix_value"] == 35.89


def test_without_a_live_quote_the_latest_completed_close_is_used():
    out = vix_gate.annotate_scores({"A": paused(35.89)}, now=MORNING, live_loader=lambda: None, loader=lambda: HIGH)
    err = out["A"]["error"]
    assert err["code"] == "vix_blocked" and err["vix_value"] == 38.42
    assert err["vix_source"] == "close" and err["vix_date"] == "2026-11-23"
    out = vix_gate.annotate_scores({"A": paused(35.89)}, now=MORNING, live_loader=lambda: None, loader=lambda: HISTORY)
    assert out["A"]["error"]["code"] == "provider_unavailable"


def test_an_old_quote_is_not_treated_as_live():
    old = (MORNING - dt.timedelta(days=10)).timestamp()
    out = vix_gate.annotate_scores({"A": paused(35.89)}, now=MORNING, live_loader=lambda: (50.0, old), loader=lambda: HIGH)
    assert out["A"]["error"]["vix_source"] == "close"


def test_no_vix_at_all_passes_responses_through():
    def boom():
        raise OSError("no data")
    scores = {"A": paused(38.4)}
    assert vix_gate.annotate_scores(scores, now=MORNING, live_loader=lambda: None, loader=boom) == scores


def test_scores_the_scorer_returns_are_never_touched():
    scores = {"A": {"status": "available", "ml_score": 70}}
    assert vix_gate.annotate_scores(scores, now=MORNING, live_loader=lambda: (50.0, QUOTE_TS)) is scores


def test_vix_gate_details_passes_the_live_facts_to_tara():
    details = vix_gate_details({"vix_value": 41.27, "vix_cutoff": 35, "vix_source": "live",
                                "vix_time": "2026-11-24T10:42-05:00"})
    assert details["vix_source"] == "live" and details["vix_time"] == "2026-11-24T10:42-05:00"


class FakeRedis:
    def __init__(self):
        self.data, self.ttl = {}, {}

    def get(self, key):
        return self.data.get(key)

    def pipeline(self, transaction=True):
        outer = self

        class P:
            def set(self, key, value, ex=None):
                outer.data[key] = value
                outer.ttl[key] = ex

            def execute(self):
                return True
        return P()


META = {"scorer_mode": "v2", "model_release": "v2-legacy", "feature_schema_version": "v2-59",
        "feature_schema_hash": "f1", "model_manifest_hash": "m1", "data_as_of": "2026-11-23",
        "data_generation_hash": "g1", "data_source_manifest_hash": "s1"}


def test_pause_results_are_cached_five_minutes_at_most_and_real_scores_keep_the_full_ttl():
    blocked = {"status": "unavailable", "error": {"code": "vix_blocked", "retryable": False}}
    assert pause_cache_ttl(blocked, 30000) == PAUSE_CACHE_SECONDS
    assert pause_cache_ttl({"status": "available", "ml_score": 70}, 30000) == 30000
    r = FakeRedis()
    write_cached_legacy_score(r, "CIEN", "2026-11-24", 50, "l", {"vix_blocked": True, "status": "unavailable"},
                              metadata=META, ttl_seconds=30000)
    assert set(r.ttl.values()) == {PAUSE_CACHE_SECONDS}


def test_an_older_cached_pause_is_a_cache_miss():
    r = FakeRedis()
    write_cached_legacy_score(r, "CIEN", "2026-11-24", 50, "l", {"vix_blocked": True, "status": "unavailable"},
                              metadata=META, ttl_seconds=30000)
    assert read_cached_legacy_score(r, "CIEN", "2026-11-24", 50, "l", expected_metadata=META) is not None
    for key, raw in list(r.data.items()):
        value = json.loads(raw)
        if "cached_at" in value:
            value["cached_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=6)).isoformat()
            r.data[key] = json.dumps(value)
    assert read_cached_legacy_score(r, "CIEN", "2026-11-24", 50, "l", expected_metadata=META) is None


def test_a_live_vix_decision_from_the_scorer_is_kept_as_is():
    item = paused(41.27, vix_source="live", vix_time="2026-11-24T15:41+00:00")
    out = vix_gate.annotate_scores({"A": item}, now=MORNING, live_loader=lambda: (27.0, QUOTE_TS), loader=lambda: HISTORY)
    err = out["A"]["error"]
    assert err["code"] == "vix_blocked" and err["vix_value"] == 41.27
    assert err["vix_source"] == "live" and err["vix_time"] == "2026-11-24T15:41+00:00"
