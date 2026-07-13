"""TradeWave affiliate dashboard (partner self-serve).

A self-contained Flask Blueprint for logged-in affiliates: program status,
performance (live estimate + settled ledger), payouts, share links, join-page
profile self-service, and the OPTIONAL SMN expert module (opt-in tab).

Integration (the PARENT wires this in web/app.py - this package never does):

    import affiliate_portal
    affiliate_portal.bp.set_user_loader(get_current_user)
    app.register_blueprint(affiliate_portal.bp, url_prefix="/account/affiliate")

Access model: NO new role. A request is an affiliate request iff the session
user has a linked, non-terminated affiliates row (affiliates.user_id FK,
migration e7a1b2c9d4f5). First visit auto-links by exact case-insensitive
email match. Everything money-related is READ-ONLY (pure downstream of
Stripe; commits stay in Flask-Admin). Spec: docs/AFFILIATE_DASHBOARD_SPEC.md.
"""
from .blueprint import bp  # noqa: F401

__all__ = ["bp"]
