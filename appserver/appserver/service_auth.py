"""Dependency-free authorization helpers for the internal service-login boundary."""

import hmac


def has_service_account_role(roles):
    """Accept only an explicit JSON-list service_account role.

    The appserver must never promote an ordinary user merely because their row has
    an api_key_hash.  ``compare_digest`` avoids turning this privileged role check
    into a value-dependent string comparison.
    """
    if not isinstance(roles, list):
        return False
    return any(
        isinstance(role, str) and hmac.compare_digest(role, "service_account")
        for role in roles
    )
