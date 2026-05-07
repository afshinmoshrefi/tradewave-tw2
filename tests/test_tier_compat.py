"""
Coverage for /home/flask/web/tier_compat.py.

The mapping was inverted earlier today (2026-05-06) — Strategist users
got Analyst access and vice versa. These tests pin the mapping in place
and explicitly assert the anti-regression conditions.

Keep these tests passing or you have re-introduced the inversion.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from tier_compat import (
    TIER_TO_LEGACY_LEVEL,
    LEGACY_LEVEL_TO_TIER,
    tier_to_legacy_level,
    tier_to_wp_user_levels,
    legacy_levels_to_tier,
)


# ---------------------------------------------------------------------
# tier → level
# ---------------------------------------------------------------------

class TestTierToLegacyLevel:
    def test_explorer(self):
        assert tier_to_legacy_level("explorer") == "1"

    def test_analyst(self):
        assert tier_to_legacy_level("analyst") == "4"

    def test_strategist(self):
        assert tier_to_legacy_level("strategist") == "6"

    def test_canceled_falls_back_to_free(self):
        # `canceled` is a valid users.tier value (CHECK constraint allows
        # it) but isn't in the mapping — it must default to '1'.
        assert tier_to_legacy_level("canceled") == "1"

    def test_garbage_falls_back_to_free(self):
        assert tier_to_legacy_level("totally-not-a-tier") == "1"

    def test_none_falls_back(self):
        # The function does .get(tier, '1') so None → '1' (safe default).
        assert tier_to_legacy_level(None) == "1"


class TestTierToWpUserLevels:
    def test_analyst_returns_list(self):
        assert tier_to_wp_user_levels("analyst") == ["4"]

    def test_explorer_returns_list(self):
        assert tier_to_wp_user_levels("explorer") == ["1"]

    def test_strategist_returns_list(self):
        assert tier_to_wp_user_levels("strategist") == ["6"]

    def test_unknown_returns_free_list(self):
        assert tier_to_wp_user_levels("nonsense") == ["1"]


# ---------------------------------------------------------------------
# levels → tier
# ---------------------------------------------------------------------

class TestLegacyLevelsToTier:
    @pytest.mark.parametrize("levels,expected", [
        (["1"], "explorer"),
        (["4"], "analyst"),
        (["5"], "analyst"),       # monthly variant of analyst
        (["6"], "strategist"),
        (["7"], "strategist"),    # monthly variant of strategist
    ])
    def test_single_level(self, levels, expected):
        assert legacy_levels_to_tier(levels) == expected

    def test_highest_wins_explorer_plus_analyst(self):
        assert legacy_levels_to_tier(["1", "4"]) == "analyst"

    def test_highest_wins_analyst_plus_strategist(self):
        assert legacy_levels_to_tier(["4", "6"]) == "strategist"

    def test_highest_wins_unordered(self):
        assert legacy_levels_to_tier(["6", "4", "1"]) == "strategist"

    def test_empty_list_defaults_to_explorer(self):
        assert legacy_levels_to_tier([]) == "explorer"

    def test_unknown_levels_default_to_explorer(self):
        assert legacy_levels_to_tier(["999", "abc"]) == "explorer"

    def test_mixed_unknown_and_known(self):
        # Unknown stays at explorer rank; known '6' wins.
        assert legacy_levels_to_tier(["999", "6"]) == "strategist"

    def test_int_inputs_coerced(self):
        # The function does str(lid) so int inputs work too.
        assert legacy_levels_to_tier([4]) == "analyst"
        assert legacy_levels_to_tier([6]) == "strategist"


# ---------------------------------------------------------------------
# Roundtrip + anti-inversion
# ---------------------------------------------------------------------

class TestRoundtrip:
    @pytest.mark.parametrize("tier", ["explorer", "analyst", "strategist"])
    def test_tier_legacy_tier_roundtrip(self, tier):
        legacy = tier_to_legacy_level(tier)
        roundtrip = legacy_levels_to_tier([legacy])
        assert roundtrip == tier, (
            f"roundtrip broken for {tier}: got {roundtrip} via legacy={legacy}"
        )


class TestAntiInversionGuards:
    """
    On 2026-05-06 the mapping briefly had analyst='6' / strategist='4',
    which gave Analyst users top-tier React access and Strategist users
    only entry-paid access. These guards make the inversion impossible
    to silently re-introduce: anyone changing the dict has to also
    rewrite these assertions to lie, which is loud.
    """

    def test_analyst_is_NOT_six(self):
        assert tier_to_legacy_level("analyst") != "6", (
            "Inversion regression — analyst maps to '6' (the strategist value)."
        )

    def test_strategist_is_NOT_four(self):
        assert tier_to_legacy_level("strategist") != "4", (
            "Inversion regression — strategist maps to '4' (the analyst value)."
        )

    def test_strategist_outranks_analyst_via_levels(self):
        # If the mapping were inverted, [6] would resolve to analyst.
        assert legacy_levels_to_tier(["6"]) == "strategist"
        assert legacy_levels_to_tier(["4"]) == "analyst"

    def test_dict_invariants(self):
        # Belt-and-suspenders: the data structures themselves carry the
        # contract.
        assert TIER_TO_LEGACY_LEVEL["explorer"] == "1"
        assert TIER_TO_LEGACY_LEVEL["analyst"] == "4"
        assert TIER_TO_LEGACY_LEVEL["strategist"] == "6"
        assert LEGACY_LEVEL_TO_TIER["1"] == "explorer"
        assert LEGACY_LEVEL_TO_TIER["4"] == "analyst"
        assert LEGACY_LEVEL_TO_TIER["5"] == "analyst"
        assert LEGACY_LEVEL_TO_TIER["6"] == "strategist"
        assert LEGACY_LEVEL_TO_TIER["7"] == "strategist"
