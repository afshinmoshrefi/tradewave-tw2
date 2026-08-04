"""Release-owned model policy for Tara.

This module is deliberately free of environment switches and user bucketing.  A
release therefore has one model policy in dev, staging, and production.
"""

POLICY_VERSION = "tara-model-policy-v2"
PRIMARY_PROVIDER = "openai"
PRIMARY_MODEL = "gpt-5.6-luna"
FALLBACK_PROVIDER = "anthropic"
FALLBACK_MODEL = "claude-haiku-4-5-20251001"


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
    """Fail closed if a release is built with an unexpected primary policy."""

    expected = ("openai", "gpt-5.6-luna", "anthropic", "claude-haiku-4-5-20251001")
    actual = (PRIMARY_PROVIDER, PRIMARY_MODEL, FALLBACK_PROVIDER, FALLBACK_MODEL)
    if actual != expected:
        raise RuntimeError("invalid Tara release model policy")
    return True
