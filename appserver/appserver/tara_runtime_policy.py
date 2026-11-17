"""Release-owned model policy for Tara.

This module is deliberately free of environment switches and user bucketing.  A
release therefore has one model policy in dev, staging, and production.

Changing Tara's primary model is a ONE-LINE change: set ``ACTIVE_POLICY`` to another
key of ``POLICIES``.  Every model-bound path (the chat tool loop, the report
explanation turn and the portfolio commentary) reads provider and model from here and
dispatches on the provider, so no other file changes.  ``tests/test_tara_runtime_policy.py``
pins the active policy on purpose; update it in the same commit as the switch.
"""

POLICY_VERSION = "tara-model-policy-v2"

# (primary provider, primary model, fallback provider, fallback model)
POLICIES = {
    "luna": ("openai", "gpt-5.6-luna", "anthropic", "claude-haiku-4-5-20251001"),
    "haiku55": ("anthropic", "claude-haiku-5-5", "openai", "gpt-5.6-luna"),
    "sonnet55": ("anthropic", "claude-sonnet-5-5", "openai", "gpt-5.6-luna"),
}

ACTIVE_POLICY = "luna"

PRIMARY_PROVIDER, PRIMARY_MODEL, FALLBACK_PROVIDER, FALLBACK_MODEL = POLICIES[ACTIVE_POLICY]

# Reasoning depth for a current-generation Claude model (``output_config.effort``).
# Luna's effort is fixed in the OpenAI adapter.
CLAUDE_EFFORT = "low"


def public_policy():
    """Return the nonsecret policy fields used by preflight and fingerprints."""

    return {
        "policy_version": POLICY_VERSION,
        "primary_provider": PRIMARY_PROVIDER,
        "primary_model": PRIMARY_MODEL,
        "fallback_provider": FALLBACK_PROVIDER,
        "fallback_model": FALLBACK_MODEL,
    }


def validate_policy():
    """Fail closed if a release is built with a policy outside the reviewed set."""

    actual = (PRIMARY_PROVIDER, PRIMARY_MODEL, FALLBACK_PROVIDER, FALLBACK_MODEL)
    if ACTIVE_POLICY not in POLICIES or actual != POLICIES[ACTIVE_POLICY]:
        raise RuntimeError("invalid Tara release model policy")
    if PRIMARY_PROVIDER == FALLBACK_PROVIDER or {PRIMARY_PROVIDER, FALLBACK_PROVIDER} != {
        "openai", "anthropic"
    }:
        raise RuntimeError("invalid Tara release model policy")
    return True
