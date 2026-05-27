"""TradeWave API customer console (self-serve).

A self-contained Flask Blueprint that lets a logged-in tradewave.ai customer
manage their API product: API keys, usage vs quota, billing (the 4 API tiers
from apiserver.tiers), and MCP connect instructions.

Integration (the PARENT wires this in web/app.py - this package never does):

    import api_portal
    # Recommended: reuse the web app's existing WorkOS session resolver so the
    # console shares the exact same auth path (no duplicated session logic):
    api_portal.bp.set_user_loader(get_current_user)   # get_current_user from web/app.py
    app.register_blueprint(api_portal.bp, url_prefix="/account/api")

If set_user_loader() is NOT called, the blueprint falls back to reading the
WorkOS sealed-session cookie itself (same cookie name + cookie_password as
web/app.py) and resolving the Postgres User via web/models.py. Either way the
customer is "already logged in via the existing app", per the spec.

Scope: CUSTOMER SELF-SERVE ONLY. No internal/admin views live here.
"""
from .blueprint import bp  # noqa: F401

__all__ = ["bp"]
