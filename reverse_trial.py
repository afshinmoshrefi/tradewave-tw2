"""Reverse-trial cutoff math - the SINGLE source of truth shared by the web tier
(web/app.py:effective_tier) and the API/MCP gateway (apiserver/auth.py).

Dependency-free on purpose (stdlib datetime only): it is imported by BOTH the web venv
and the gateway venv (venv-api), which otherwise import nothing from each other. Both
processes run with PYTHONPATH=/home/flask, so `import reverse_trial` resolves in each.
Do NOT add imports of config/web/appserver here or the gateway can no longer load it.

WHY this exists: the web tier owns the AUTHORITATIVE elevation (effective_tier mints the
LTK). The gateway MIRRORS the same rule into the MCP/consumer-OAuth scope so a trialing
user is never WORSE off inside ChatGPT/Claude than on the website - that would be a
bait-and-switch. Keeping the math in one place means the two products cannot drift.
"""
from datetime import datetime, timedelta, timezone

# Mirror of config.ROLE_BYPASSES_TIER. DUPLICATED (not imported) so this module stays
# dependency-free / loadable from the gateway venv, which must not import config.py.
# web/app.py:effective_tier passes config.ROLE_BYPASSES_TIER explicitly (so config stays
# authoritative there); the gateway uses this default. If the config set ever changes,
# update this too - test_reverse_trial asserts the two are equal.
ROLE_BYPASSES_TIER = {"super_admin", "staff_admin", "service_account"}

# Navigator's one-time first-MCP-connect teaser window: 7 days of Analyst scope (the AI
# taste Navigator otherwise lacks). HOISTED here so the web tier (account card) and the
# gateway (apiserver/auth.py) compute the SAME window from the same constant, exactly like
# the reverse-trial math above. The arm/persist of navigator_mcp_first_connect_at stays in
# the gateway (db.arm_navigator_teaser_if_null); this module is read-only math.
NAV_TEASER_SECONDS = 7 * 86400


def navigator_teaser_window(first_connect_at):
    """The Navigator first-MCP-connect teaser window from a stamped first-connect timestamp.

    Returns (active: bool, ends_at_iso: str|None):
      - active = first_connect_at is not None and (now_utc - first_connect_at) < NAV_TEASER_SECONDS
      - ends_at = (first_connect_at + NAV_TEASER_SECONDS).isoformat(), or None when never connected

    READ-ONLY: never arms/persists the column (that is the gateway's job on first connect).
    `first_connect_at` is a tz-aware datetime or None.
    """
    if first_connect_at is None:
        return False, None
    ends_at = first_connect_at + timedelta(seconds=NAV_TEASER_SECONDS)
    active = (datetime.now(timezone.utc) - first_connect_at).total_seconds() < NAV_TEASER_SECONDS
    return active, ends_at.isoformat()


def in_reverse_trial(reverse_trial_ends_at) -> bool:
    """True iff the user is inside an ACTIVE reverse trial (the 7-day full-Strategist
    window from signup). `reverse_trial_ends_at` is a tz-aware datetime or None."""
    return (
        reverse_trial_ends_at is not None
        and reverse_trial_ends_at > datetime.now(timezone.utc)
    )


def effective_web_tier(tier, roles, reverse_trial_ends_at, bypass_roles=ROLE_BYPASSES_TIER) -> str:
    """The web tier used for ACCESS decisions, replicating web/app.py:effective_tier from
    raw fields (so the gateway can compute it without importing web/models):

      - an admin/service role (bypass_roles) -> 'strategist' (founder never paywalls himself)
      - an 'explorer' inside the reverse trial -> 'strategist'
      - otherwise the raw web tier

    Never MUTATES the billing tier; this is access-only, exactly like effective_tier.
    """
    tier = tier or "explorer"
    try:
        roleset = set(roles or [])
    except TypeError:
        roleset = set()
    if roleset & set(bypass_roles or ()):
        return "strategist"
    if tier == "explorer" and in_reverse_trial(reverse_trial_ends_at):
        return "strategist"
    return tier
