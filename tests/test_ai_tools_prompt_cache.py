"""Tests for Anthropic system-block cache breakpoint handling."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "appserver" / "appserver"))

import AI_tools_appserver as ai_tools  # noqa: E402
from AI_tools_appserver import _prepare_system  # noqa: E402


def test_segmented_system_keeps_dynamic_suffix_after_cache_breakpoint():
    source = [
        {"type": "text", "text": "stable", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "selected topic"},
        {"type": "text", "text": "live screen"},
    ]
    prepared = _prepare_system(source, cache_system=True, cache_ttl="5m")

    assert prepared[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in prepared[1]
    assert "cache_control" not in prepared[2]
    # The caller's reusable block list must not be mutated.
    assert source[0]["cache_control"] == {"type": "ephemeral"}


def test_one_hour_ttl_is_applied_to_the_explicit_stable_breakpoint():
    prepared = _prepare_system(
        [
            {"type": "text", "text": "stable", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "dynamic"},
        ],
        cache_system=True,
        cache_ttl="1h",
    )

    assert prepared[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "cache_control" not in prepared[1]


def test_legacy_string_still_caches_as_one_block():
    prepared = _prepare_system("legacy prompt", cache_system=True, cache_ttl="5m")

    assert prepared == [
        {
            "type": "text",
            "text": "legacy prompt",
            "cache_control": {"type": "ephemeral"},
        }
    ]


def test_send_claude_messages_posts_ordered_segmented_blocks(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"content": [{"type": "text", "text": "ok"}]}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return Response()

    monkeypatch.setattr(ai_tools.requests, "post", fake_post)
    reply = ai_tools.send_claude_messages(
        [{"role": "user", "content": "hello"}],
        model="test-model",
        system=[
            {"type": "text", "text": "stable", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "live"},
        ],
        cache_system=True,
    )

    assert reply == "ok"
    assert captured["headers"]["anthropic-beta"] == "prompt-caching-2024-07-31"
    assert captured["payload"]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in captured["payload"]["system"][1]
