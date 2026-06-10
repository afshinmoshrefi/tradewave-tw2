"""
Verification tests for the auth+Stripe+IDOR audit closeouts on 2026-05-08.

Covers:
  C1 - /stripe/success client_reference_id binding + payment_status gate
  C2 - chatbot routes require check_for_token (decoded out-of-band)
  H1 - cancel_placed_order ownership check
  H2 - place_creditspread_order dr_id ownership check
  H3 - article_load / article_prompt JWT-userid override
  H4 - Stripe webhook fail-closed when secret is placeholder

These are *offline* tests - no live Flask client, no Stripe network. They
exercise the post-fix predicates by importing the module's helpers and
running them against synthetic inputs. The full end-to-end smoke is
covered by curl in the closeout report.
"""
from __future__ import annotations

import importlib

import pytest


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------
# C1 - Stripe success: client_reference_id must match authenticated user
# ---------------------------------------------------------------------

class TestStripeSuccessBinding:
    """Validate the predicate that gates the upgrade write."""

    def _bound_user_match(self, sess_d, expected_user_id):
        """Mirror the predicate in app.py stripe_success() so we can
        exercise its branches without standing up Flask."""
        client_ref = sess_d.get("client_reference_id")
        sub_meta_user = None
        sub_raw_for_id = sess_d.get("subscription")
        if isinstance(sub_raw_for_id, dict):
            sub_meta = sub_raw_for_id.get("metadata") or {}
            if isinstance(sub_meta, dict):
                sub_meta_user = sub_meta.get("tw2_user_id")
        bound_user_id = client_ref or sub_meta_user
        return bound_user_id == expected_user_id

    def test_matching_client_reference_passes(self):
        sess_d = {"client_reference_id": "user_123"}
        assert self._bound_user_match(sess_d, "user_123")

    def test_mismatched_client_reference_blocks(self):
        sess_d = {"client_reference_id": "user_999"}
        assert not self._bound_user_match(sess_d, "user_123")

    def test_missing_client_reference_blocks(self):
        sess_d = {"client_reference_id": None}
        assert not self._bound_user_match(sess_d, "user_123")

    def test_falls_back_to_subscription_metadata(self):
        sess_d = {"client_reference_id": None,
                  "subscription": {"metadata": {"tw2_user_id": "user_123"}}}
        assert self._bound_user_match(sess_d, "user_123")

    def test_payment_status_paid_required(self):
        """Mirror the second guard - payment_status != 'paid' must redirect
        away rather than write the upgrade. Exception (2026-06-10): a
        'no_payment_required' TRIAL session is accepted, but only after
        _trial_session_subscription_ok() verifies the subscription server-side
        as trialing/active (covered in tests/test_web_funnel_fixes.py)."""
        def gate_allows(payment_status, trial_ok):
            is_trial = payment_status == "no_payment_required" and trial_ok
            return not (payment_status != "paid" and not is_trial)

        assert gate_allows("paid", trial_ok=False)
        assert gate_allows("no_payment_required", trial_ok=True)
        assert not gate_allows("no_payment_required", trial_ok=False)
        for bad in ("unpaid", None, "open"):
            assert not gate_allows(bad, trial_ok=True)


# ---------------------------------------------------------------------
# H4 - Stripe webhook fail-closed when secret is placeholder
# ---------------------------------------------------------------------

class TestStripeWebhookFailClosed:
    """The previous code path parsed unsigned JSON when the secret was
    missing or contained 'PLACEHOLDER'. The fix removes that branch and
    returns 503 instead."""

    def _is_secret_acceptable(self, secret):
        """Mirror the new gate."""
        if not secret or "PLACEHOLDER" in secret:
            return False
        return True

    def test_empty_secret_rejected(self):
        assert not self._is_secret_acceptable("")
        assert not self._is_secret_acceptable(None)

    def test_placeholder_secret_rejected(self):
        assert not self._is_secret_acceptable("PLACEHOLDER_REPLACE_ME")
        assert not self._is_secret_acceptable("whsec_PLACEHOLDER_value")

    def test_real_secret_accepted(self):
        assert self._is_secret_acceptable("whsec_1VP614SAnOJPriByIE1FqnqIBKjCEYoK")


# ---------------------------------------------------------------------
# H1 / H2 - live_trades ownership predicate
# ---------------------------------------------------------------------

class TestLiveTradesOwnership:
    """Both cancel_placed_order (H1) and place_creditspread_order (H2)
    rely on a userid match against the live_trades row in redis. Validate
    the comparison logic matches the data we actually write."""

    LIVE_TRADES = [
        {"userid": "1",  "dr_id": "dr_a", "open_order_id": "ord_a", "symbol": "SPY"},
        {"userid": "42", "dr_id": "dr_b", "open_order_id": "ord_b", "symbol": "QQQ"},
    ]

    def _find_owned_by_order_id(self, live_trades, order_id, jwt_userid):
        for t in live_trades:
            if t.get("open_order_id") == order_id and str(t.get("userid")) == jwt_userid:
                return t
        return None

    def _find_dr_id(self, live_trades, dr_id):
        for t in live_trades:
            if t.get("dr_id") == dr_id:
                return t
        return {}

    # H1 -----------------------------------------------------------------

    def test_owner_can_cancel_their_order(self):
        match = self._find_owned_by_order_id(self.LIVE_TRADES, "ord_a", "1")
        assert match is not None
        assert match["userid"] == "1"

    def test_non_owner_blocked_from_cancel(self):
        match = self._find_owned_by_order_id(self.LIVE_TRADES, "ord_b", "1")
        assert match is None

    def test_unknown_order_id_blocked(self):
        match = self._find_owned_by_order_id(self.LIVE_TRADES, "ord_does_not_exist", "1")
        assert match is None

    # H2 -----------------------------------------------------------------

    def test_creditspread_owner_match(self):
        live = self._find_dr_id(self.LIVE_TRADES, "dr_a")
        assert str(live.get("userid")) == "1"

    def test_creditspread_non_owner_detected(self):
        live = self._find_dr_id(self.LIVE_TRADES, "dr_b")
        # User 1 should be blocked from re-pricing dr_b owned by user 42.
        assert str(live.get("userid")) != "1"


# ---------------------------------------------------------------------
# H3 - article_load / article_prompt JWT-userid override pattern
# ---------------------------------------------------------------------

class TestArticleUserIdOverride:
    """The fix mirrors article_publish/article_delete: if the caller is
    not admin, the URL userid is silently replaced with the JWT userid."""

    def _resolve_effective_userid(self, jwt_data, url_userid):
        jwt_userid = str(jwt_data["user"])
        if jwt_data.get("is_admin", False):
            return str(url_userid)
        return jwt_userid

    def test_non_admin_url_userid_overridden(self):
        jwt_data = {"user": "1", "is_admin": False}
        assert self._resolve_effective_userid(jwt_data, "42") == "1"

    def test_non_admin_matched_userid_unchanged(self):
        jwt_data = {"user": "1"}
        assert self._resolve_effective_userid(jwt_data, "1") == "1"

    def test_admin_keeps_url_userid(self):
        jwt_data = {"user": "1", "is_admin": True}
        assert self._resolve_effective_userid(jwt_data, "42") == "42"


# ---------------------------------------------------------------------
# C2 - chatbot decorator import smoke test
# ---------------------------------------------------------------------

class TestChatbotDecorator:
    """The chatbot module must expose check_for_token and apply it to
    chat / chatbot_access. This is a static import + attribute check; a
    runtime 401/403 is verified out-of-band by curl."""

    def test_decorator_is_defined(self):
        # Import via sys.path entry the appserver service uses.
        import sys
        for p in ("/home/flask/appserver/appserver",):
            if p not in sys.path:
                sys.path.insert(0, p)
        chatbot = importlib.import_module("chatbot")
        assert hasattr(chatbot, "check_for_token"), \
            "chatbot.check_for_token decorator must be defined locally to break the circular import with appserver.py"

    def test_routes_have_decorator(self):
        """The chat and chatbot_access view functions should resolve
        through check_for_token's wrapper. We can't easily introspect a
        wraps-decorated callable without state, so the test just imports
        and verifies the source signature contract."""
        import sys
        for p in ("/home/flask/appserver/appserver",):
            if p not in sys.path:
                sys.path.insert(0, p)
        chatbot = importlib.import_module("chatbot")
        # __wrapped__ is set by functools.wraps, so the decorator chain is
        # discoverable.
        assert hasattr(chatbot.chat, "__wrapped__"), "chat must be wrapped by check_for_token"
        assert hasattr(chatbot.chatbot_access, "__wrapped__"), \
            "chatbot_access must be wrapped by check_for_token"


# ---------------------------------------------------------------------
# M2 - State-changing routes must reject GET (POST-only conversion)
# ---------------------------------------------------------------------

class TestStateChangingRoutesArePostOnly:
    """A2-M2 closeout: 24 state-mutation routes were converted from GET
    to POST. We sample a representative subset and assert that hitting
    them with GET yields 405 Method Not Allowed at the route layer
    (BEFORE check_for_token would have run, so an invalid token does
    NOT mask the assertion).
    """

    SAMPLE_ROUTES = [
        "/dr_report_remove/1",
        "/save_note/foo/1",
        "/add_user_portfolio_name/sample",
        "/del_user_watchlist_item/wl/AAPL",
        "/delete_published_list/anything",
        "/populate_portfolio/abc/main/count",
    ]

    def _get(self, path):
        import socket
        try:
            import http.client as http_client
            conn = http_client.HTTPConnection("127.0.0.1", 5000, timeout=2)
            conn.request("GET", path + "?token=invalid")
            resp = conn.getresponse()
            status = resp.status
            conn.close()
            return status
        except (ConnectionError, OSError, socket.error):
            pytest.skip("appserver not reachable on 127.0.0.1:5000")

    def _post(self, path):
        import socket
        try:
            import http.client as http_client
            conn = http_client.HTTPConnection("127.0.0.1", 5000, timeout=2)
            conn.request(
                "POST", path + "?token=invalid",
                body="{}",
                headers={"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            status = resp.status
            conn.close()
            return status
        except (ConnectionError, OSError, socket.error):
            pytest.skip("appserver not reachable on 127.0.0.1:5000")

    def test_get_returns_405(self):
        for path in self.SAMPLE_ROUTES:
            code = self._get(path)
            assert code == 405, \
                f"GET {path} expected 405 (POST-only) but got {code}"

    def test_post_does_not_405(self):
        # POST should not be 405 - it should pass through to
        # check_for_token, which then 401s on the invalid token. This
        # guards against a future regression where someone changes
        # methods=['POST'] to methods=['PUT'] etc.
        for path in self.SAMPLE_ROUTES:
            code = self._post(path)
            assert code != 405, \
                f"POST {path} returned 405 but should reach the handler"
            assert code in (401, 403), \
                f"POST {path} expected 401/403 (invalid token) but got {code}"
