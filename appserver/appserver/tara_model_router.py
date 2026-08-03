"""Deterministic provider routing for Tara's model-bound turns.

The answer planner runs before this selector, so the canary never moves verified,
deterministic answers onto an LLM.  A user remains in the same provider bucket across
turns and appserver workers.
"""

import hashlib


ANTHROPIC_PROVIDER = "anthropic"
OPENAI_PROVIDER = "openai"
_CANARY_SALT = "tara-gpt-5.6-luna-v1"


def canary_bucket(user_id):
    """Return a stable 0..99 bucket without retaining or logging the user id."""

    identity = str(user_id or "unknown")
    digest = hashlib.sha256((f"{_CANARY_SALT}:{identity}").encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 100


def select_tara_provider(user_id, canary_percent, openai_available=True):
    """Return ``(provider, bucket)`` for a bounded sticky canary."""

    try:
        percent = int(canary_percent)
    except (TypeError, ValueError):
        percent = 0
    percent = min(max(percent, 0), 100)
    bucket = canary_bucket(user_id)
    if openai_available and bucket < percent:
        return OPENAI_PROVIDER, bucket
    return ANTHROPIC_PROVIDER, bucket
