"""Release-owned provider selection for Tara's model-bound turns.

The deterministic answer planner still runs first.  Every remaining model-bound
turn starts on the release policy's primary provider; there is no user bucketing,
canary percentage, or environment-specific default.
"""

from tara_runtime_policy import (
    PRIMARY_PROVIDER,
    validate_policy,
)

OPENAI_PROVIDER = "openai"
ANTHROPIC_PROVIDER = "anthropic"


def select_tara_provider():
    """Return the single release primary after validating the tracked policy."""

    validate_policy()
    return PRIMARY_PROVIDER
