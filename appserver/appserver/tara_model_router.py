"""Release-owned provider selection for Tara's model-bound turns.

The deterministic answer planner still runs first.  Every remaining model-bound
turn starts on the release policy's OpenAI primary; there is no user bucketing,
canary percentage, or environment-specific default.
"""

from tara_runtime_policy import (
    FALLBACK_PROVIDER as ANTHROPIC_PROVIDER,
    PRIMARY_PROVIDER as OPENAI_PROVIDER,
    validate_policy,
)


def select_tara_provider():
    """Return the single release primary after validating the tracked policy."""

    validate_policy()
    return OPENAI_PROVIDER
