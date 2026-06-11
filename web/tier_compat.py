"""
TW2 ↔ TW1 tier name / WP-UMP level numeric ID compat shim.

The React app inherits from TW1 and expects window.current_user_level to be
a numeric WP/UMP level ID. TW2 uses named tiers.

Mapping (matches Stripe product names + price ordering):
  TW2 Explorer   = legacy level 1 (Ripple, free).
  TW2 Analyst    = legacy levels 4 (yearly) / 5 (monthly) - entry paid tier.
                   Premium = US stocks + ETFs (6 markets); date-locked
                   for indices/futures/forex/bonds/foreign/crypto.
                   Stripe: $58/mo or $488/yr.
  TW2 Strategist = legacy levels 6 (yearly) / 7 (monthly) - top paid tier.
                   Premium = all 15 markets; ML scoring; max limits.
                   Stripe: $199/mo or $1574/yr.

Strategist > Analyst > Explorer by access and by price.

The legacy numbers come from WP UMP IDs; React gates on them directly via
window.current_user_level → wpUserLevels.
"""

# Yearly is the "default" landing level since both monthly and yearly users
# get the same access dicts; the distinction matters only for Stripe billing.
TIER_TO_LEGACY_LEVEL = {
    'explorer':   '1',
    'analyst':    '4',  # entry paid (was PRO yearly; '5' for monthly - same access)
    'strategist': '6',  # top paid (was Institutional yearly; '7' for monthly)
}


def tier_to_wp_user_levels(tier: str) -> list[str]:
    return [TIER_TO_LEGACY_LEVEL.get(tier, '1')]


def tier_to_legacy_level(tier: str) -> str:
    return TIER_TO_LEGACY_LEVEL.get(tier, '1')


# Inverse - for migration / Stripe-event handling.
LEGACY_LEVEL_TO_TIER = {
    '1': 'explorer',
    '4': 'analyst',
    '5': 'analyst',
    '6': 'strategist',
    '7': 'strategist',
}


def legacy_levels_to_tier(level_ids) -> str:
    """Given a list of UMP level IDs, return the highest TW2 tier they imply."""
    rank = {'explorer': 0, 'analyst': 1, 'strategist': 2}
    best = 'explorer'
    for lid in level_ids:
        t = LEGACY_LEVEL_TO_TIER.get(str(lid), 'explorer')
        if rank[t] > rank[best]:
            best = t
    return best
