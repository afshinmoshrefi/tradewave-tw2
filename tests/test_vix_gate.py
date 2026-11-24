"""vix_gate: VIX pause facts come from the scorer value and our own VIX history."""
import datetime as dt

import vix_gate

HISTORY = [("2026-11-19", 28.44), ("2026-11-20", 35.89), ("2026-11-23", 26.62), ("2026-11-24", 29.54)]
HIGH = [("2026-11-19", 28.44), ("2026-11-20", 35.89), ("2026-11-23", 38.42), ("2026-11-24", 39.1)]
MORNING = dt.datetime(2026, 11, 24, 14, 39, tzinfo=dt.timezone.utc)   # 9:39 ET, today's bar is partial
EVENING = dt.datetime(2026, 11, 24, 22, 0, tzinfo=dt.timezone.utc)    # 17:00 ET, today's close is final


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


def test_real_pause_gets_close_date_and_cached_items_get_the_value():
    scores = {
        "A|1|l": {"horizons": [paused(38.42)]},
        "B|2|l": paused(None, cutoff=None),          # cached before values were kept
    }
    out = vix_gate.annotate_scores(scores, now=MORNING, loader=lambda: HIGH)
    a = out["A|1|l"]["horizons"][0]["error"]
    b = out["B|2|l"]["error"]
    assert a["code"] == "vix_blocked" and a["vix_date"] == "2026-11-23"
    assert b["vix_value"] == 38.42 and b["vix_cutoff"] == 35.0 and b["vix_date"] == "2026-11-23"
    assert scores["B|2|l"]["error"].get("vix_value") is None   # input not mutated


def test_stale_scorer_pause_becomes_temporarily_unavailable():
    # Nov 24 morning: the scorer still says 35.9 (Friday Nov 20) but Monday closed 26.62.
    out = vix_gate.annotate_scores({"A|1|l": paused(35.9)}, now=MORNING, loader=lambda: HISTORY)
    err = out["A|1|l"]["error"]
    assert err["code"] == "provider_unavailable"
    assert err["message"] == "AI scores are temporarily unavailable."
    assert err["stale_vix_gate"] is True and err["latest_vix_close"] == 26.62
    assert err["latest_vix_date"] == "2026-11-23" and err["retryable"] is True


def test_value_without_a_matching_close_gets_no_date():
    out = vix_gate.annotate_scores({"A": paused(41.0)}, now=MORNING, loader=lambda: HIGH)
    assert "vix_date" not in out["A"]["error"]


def test_wrong_scorer_cache_date_is_replaced_by_the_real_close_date():
    out = vix_gate.annotate_scores({"A": paused(38.4, vix_date="2026-11-24")}, now=MORNING, loader=lambda: HIGH)
    assert out["A"]["error"]["vix_date"] == "2026-11-23"


def test_history_failure_passes_responses_through():
    def boom():
        raise OSError("no data")
    scores = {"A": paused(38.4)}
    assert vix_gate.annotate_scores(scores, now=MORNING, loader=boom) == scores


def test_responses_without_a_pause_are_untouched():
    scores = {"A": {"status": "available", "ml_score": 70}}
    assert vix_gate.annotate_scores(scores, now=MORNING, loader=lambda: HISTORY) is scores
