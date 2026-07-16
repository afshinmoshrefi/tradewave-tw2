"""Pure classification/planning helpers for Stripe subscription identity repair.

This module deliberately has no database, Stripe SDK, or application imports so
the safety decisions can be tested without credentials or external services.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple


KNOWN_PRODUCT_LINES = {"api", "eod"}
LIVE_SUBSCRIPTION_STATUSES = {"active", "trialing", "past_due"}
TERMINAL_SUBSCRIPTION_STATUSES = {"canceled", "unpaid", "incomplete_expired"}
FREE_WEB_TIERS = {"explorer", "canceled"}


def _as_dict(value: Any) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {}
    for method_name in ("to_dict_recursive", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            converted = method()
            if isinstance(converted, Mapping):
                return dict(converted)
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def _text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def _lower(value: Any) -> Optional[str]:
    value = _text(value)
    return value.lower() if value else None


def _object_id(value: Any) -> Optional[str]:
    value_dict = _as_dict(value)
    if value_dict:
        return _text(value_dict.get("id"))
    return _text(value)


def _period(value: Any) -> Optional[str]:
    value = _lower(value)
    return {
        "month": "monthly",
        "monthly": "monthly",
        "year": "yearly",
        "annual": "yearly",
        "yearly": "yearly",
    }.get(value)


@dataclass(frozen=True)
class SubscriptionClassification:
    subscription_id: Optional[str]
    line: str
    status: Optional[str] = None
    customer_id: Optional[str] = None
    tier: Optional[str] = None
    period: Optional[str] = None
    livemode: Optional[bool] = None
    reason: str = ""


def classification_error(subscription_id: str, error_name: str):
    """Represent a Stripe retrieval failure without treating it as absence."""
    return SubscriptionClassification(
        subscription_id=_text(subscription_id),
        line="error",
        reason="stripe-retrieval-error:%s" % (_text(error_name) or "unknown"),
    )


def classify_subscription_payload(payload: Any) -> SubscriptionClassification:
    """Classify one expanded Stripe Subscription fail-closed.

    Product metadata is primary evidence. Subscription metadata is accepted as
    a fallback/cross-check because TradeWave writes it at Checkout. Conflicting
    product lines, partially labelled multi-item subscriptions, and conflicting
    tiers are never auto-repaired.
    """
    sub = _as_dict(payload)
    subscription_id = _text(sub.get("id"))
    status = _lower(sub.get("status"))
    customer_id = _object_id(sub.get("customer"))
    livemode = sub.get("livemode")
    if not isinstance(livemode, bool):
        livemode = None
    sub_metadata = _as_dict(sub.get("metadata"))
    sub_line = _lower(sub_metadata.get("product_line"))
    sub_tier = _lower(
        sub_metadata.get("tier") or sub_metadata.get("tw2_tier_target")
    )
    sub_period = _period(
        sub_metadata.get("period") or sub_metadata.get("interval")
    )

    items_container = _as_dict(sub.get("items"))
    if items_container.get("has_more"):
        return SubscriptionClassification(
            subscription_id, "conflict", status, customer_id,
            reason="subscription-items-not-fully-loaded",
        )
    raw_items = items_container.get("data") or []
    item_lines = []
    item_tiers = []
    item_periods = []
    unlabeled_items = 0

    for raw_item in raw_items:
        item = _as_dict(raw_item)
        price = _as_dict(item.get("price"))
        product = _as_dict(price.get("product"))
        product_metadata = _as_dict(product.get("metadata"))
        price_metadata = _as_dict(price.get("metadata"))
        line_values = {
            value for value in (
                _lower(product_metadata.get("product_line")),
                _lower(price_metadata.get("product_line")),
            ) if value
        }
        if len(line_values) > 1:
            return SubscriptionClassification(
                subscription_id, "conflict", status, customer_id,
                reason="price-product-line-conflict:%s"
                % ",".join(sorted(line_values)),
            )
        line = next(iter(line_values), None)
        if not line:
            unlabeled_items += 1
            continue
        item_lines.append(line)
        tier_values = {
            value for value in (
                _lower(product_metadata.get("tier")),
                _lower(price_metadata.get("tier")),
            ) if value
        }
        if len(tier_values) > 1:
            return SubscriptionClassification(
                subscription_id, "conflict", status, customer_id,
                reason="price-product-tier-conflict:%s"
                % ",".join(sorted(tier_values)),
            )
        item_tier = next(iter(tier_values), None)
        if item_tier:
            item_tiers.append(item_tier)
        period_values = {
            value for value in (
                _period(
                    product_metadata.get("period")
                    or product_metadata.get("interval")
                ),
                _period(
                    price_metadata.get("period")
                    or price_metadata.get("interval")
                ),
                _period(_as_dict(price.get("recurring")).get("interval")),
            ) if value
        }
        if len(period_values) > 1:
            return SubscriptionClassification(
                subscription_id, "conflict", status, customer_id,
                reason="price-product-period-conflict:%s"
                % ",".join(sorted(period_values)),
            )
        item_period = next(iter(period_values), None)
        if item_period:
            item_periods.append(item_period)

    if not raw_items:
        return SubscriptionClassification(
            subscription_id, "unknown", status, customer_id,
            reason="subscription-has-no-items",
        )

    distinct_lines = set(item_lines)
    if len(distinct_lines) > 1:
        return SubscriptionClassification(
            subscription_id, "conflict", status, customer_id,
            reason="mixed-product-lines:%s" % ",".join(sorted(distinct_lines)),
        )

    product_line = next(iter(distinct_lines), None)
    if sub_line and product_line and sub_line != product_line:
        return SubscriptionClassification(
            subscription_id, "conflict", status, customer_id,
            reason="subscription-product-line-conflict:%s/%s"
            % (sub_line, product_line),
        )
    if unlabeled_items and product_line:
        return SubscriptionClassification(
            subscription_id, "conflict", status, customer_id,
            reason="partially-labelled-multi-item-subscription",
        )

    line = product_line or sub_line
    if not line:
        return SubscriptionClassification(
            subscription_id, "unknown", status, customer_id,
            reason="no-product-line-metadata",
        )

    tier_values = set(item_tiers)
    if sub_tier:
        tier_values.add(sub_tier)
    if len(tier_values) > 1:
        return SubscriptionClassification(
            subscription_id, "conflict", status, customer_id,
            reason="conflicting-tier-metadata:%s"
            % ",".join(sorted(tier_values)),
        )
    tier = next(iter(tier_values), None)

    period_values = set(item_periods)
    if sub_period:
        period_values.add(sub_period)
    if len(period_values) > 1:
        return SubscriptionClassification(
            subscription_id, "conflict", status, customer_id, tier=tier,
            reason="conflicting-period-metadata:%s"
            % ",".join(sorted(period_values)),
        )
    period = next(iter(period_values), None)

    normalized_line = line if line in KNOWN_PRODUCT_LINES else "other"
    source = "price/product+subscription" if product_line and sub_line else (
        "price/product" if product_line else "subscription"
    )
    return SubscriptionClassification(
        subscription_id=subscription_id,
        line=normalized_line,
        status=status,
        customer_id=customer_id,
        tier=tier,
        period=period,
        livemode=livemode,
        reason="classified-from-%s%s" % (
            source,
            ":%s" % line if normalized_line == "other" else "",
        ),
    )


@dataclass(frozen=True)
class UserIdentitySnapshot:
    user_id: str
    email: str
    customer_id: Optional[str]
    web_subscription_id: Optional[str]
    web_subscription_status: Optional[str]
    api_subscription_id: Optional[str]
    api_subscription_status: Optional[str]
    web_tier: Optional[str] = None
    api_tier: Optional[str] = None


@dataclass(frozen=True)
class IdentityPlan:
    action: str
    applyable: bool
    blocking: bool
    reason: str
    web_subscription_id: Optional[str]
    web_subscription_status: Optional[str]
    api_subscription_id: Optional[str]
    api_subscription_status: Optional[str]

    @property
    def changed(self) -> bool:
        return self.applyable


def _unchanged(snapshot: UserIdentitySnapshot, action: str, *,
               blocking: bool, reason: str) -> IdentityPlan:
    return IdentityPlan(
        action=action,
        applyable=False,
        blocking=blocking,
        reason=reason,
        web_subscription_id=snapshot.web_subscription_id,
        web_subscription_status=snapshot.web_subscription_status,
        api_subscription_id=snapshot.api_subscription_id,
        api_subscription_status=snapshot.api_subscription_status,
    )


def _customer_matches(snapshot: UserIdentitySnapshot,
                      evidence: SubscriptionClassification) -> bool:
    return bool(
        snapshot.customer_id
        and evidence.customer_id
        and evidence.customer_id == snapshot.customer_id
    )


def _strong_product_evidence(evidence: SubscriptionClassification) -> bool:
    return evidence.reason.startswith("classified-from-price/product")


def _api_state_problem(
    snapshot: UserIdentitySnapshot,
    evidence: SubscriptionClassification,
) -> Optional[str]:
    """Return why Stripe API state and the entitlement column disagree."""
    status = _lower(evidence.status)
    evidence_tier = _lower(evidence.tier)
    snapshot_tier = _lower(snapshot.api_tier)
    if status in LIVE_SUBSCRIPTION_STATUSES:
        if evidence_tier not in {"dev", "pro", "business"}:
            return "live API subscription has no recognized tier metadata"
        if snapshot_tier != evidence_tier:
            return "live API tier mismatch: database=%s stripe=%s" % (
                snapshot_tier or "none", evidence_tier,
            )
        return None
    if status in TERMINAL_SUBSCRIPTION_STATUSES:
        if snapshot_tier:
            return "terminal API subscription still has database API tier %s" % (
                snapshot_tier,
            )
        return None
    return "API subscription has ambiguous status %s" % (status or "missing")


def _safe_customer_web_rebind(
    snapshot: UserIdentitySnapshot,
    stored_web_id: str,
    customer_subscriptions: Tuple[SubscriptionClassification, ...],
    *,
    customer_scan_complete: bool,
    customer_scan_error: Optional[str],
    shared_subscription_ids: set,
    expected_livemode: Optional[bool],
) -> Optional[SubscriptionClassification]:
    """Return one conclusive customer-owned web identity, else ``None``.

    The stored web ID must be absent from a complete customer scan, and that
    scan must contain exactly one subscription total. The sole replacement
    must be strongly product-classified EOD, live, owned by the stored Stripe
    customer, unshared, in the expected Stripe mode, and match the paid DB web
    tier. These constraints repair a stale foreign binding without guessing.
    """
    if customer_scan_error or not customer_scan_complete:
        return None
    unique = {}
    for candidate in customer_subscriptions:
        candidate_id = _text(candidate.subscription_id)
        if candidate_id:
            unique[candidate_id] = candidate
    if stored_web_id in unique or len(unique) != 1:
        return None
    candidate = next(iter(unique.values()))
    web_tier = _lower(snapshot.web_tier)
    if (
        candidate.line != "eod"
        or not _strong_product_evidence(candidate)
        or not _customer_matches(snapshot, candidate)
        or _lower(candidate.status) not in LIVE_SUBSCRIPTION_STATUSES
        or _lower(candidate.tier) != web_tier
        or web_tier not in {"navigator", "analyst", "strategist"}
        or candidate.subscription_id in shared_subscription_ids
        or (
            expected_livemode is not None
            and candidate.livemode is not expected_livemode
        )
    ):
        return None
    return candidate


def plan_identity_reconciliation(
    snapshot: UserIdentitySnapshot,
    web_evidence: Optional[SubscriptionClassification],
    api_evidence: Optional[SubscriptionClassification],
    *,
    shared_subscription_ids: Tuple[str, ...] = (),
    customer_subscriptions: Tuple[SubscriptionClassification, ...] = (),
    customer_scan_complete: bool = False,
    customer_scan_error: Optional[str] = None,
    expected_livemode: Optional[bool] = None,
) -> IdentityPlan:
    """Return the only safe automatic identity mutation for one user.

    Unknown legacy web subscriptions are intentionally preserved. Automatic
    changes are limited to (a) a web-column subscription proven to be API-line
    with an empty/matching API column, or (b) a stale foreign web ID for which a
    complete Stripe customer scan proves exactly one matching live web plan.
    """
    shared = set(shared_subscription_ids)
    web_id = _text(snapshot.web_subscription_id)
    api_id = _text(snapshot.api_subscription_id)

    if api_id:
        if api_id in shared:
            return _unchanged(
                snapshot, "blocked-shared-api-id", blocking=True,
                reason="API subscription ID is stored on more than one user",
            )
        if (
            api_evidence is None
            or api_evidence.line != "api"
            or not _strong_product_evidence(api_evidence)
        ):
            line = api_evidence.line if api_evidence else "missing"
            return _unchanged(
                snapshot, "blocked-api-column-classification", blocking=True,
                reason="API column resolves as %s" % line,
            )
        if not _customer_matches(snapshot, api_evidence):
            return _unchanged(
                snapshot, "blocked-api-customer-mismatch", blocking=True,
                reason="API subscription belongs to a different Stripe customer",
            )
        if (
            expected_livemode is not None
            and api_evidence.livemode is not expected_livemode
        ):
            return _unchanged(
                snapshot, "blocked-api-stripe-mode", blocking=True,
                reason="API subscription does not match the expected Stripe mode",
            )
        api_problem = _api_state_problem(snapshot, api_evidence)
        if api_problem:
            return _unchanged(
                snapshot, "blocked-api-entitlement-state", blocking=True,
                reason=api_problem,
            )

    if not web_id:
        return _unchanged(
            snapshot,
            "verified-api-only" if api_id else "no-subscription-identity",
            blocking=False,
            reason="No web subscription identity needs reconciliation",
        )

    if web_id in shared:
        return _unchanged(
            snapshot, "blocked-shared-web-id", blocking=True,
            reason="Web subscription ID is stored on more than one user",
        )
    if web_evidence is None:
        return _unchanged(
            snapshot, "blocked-missing-web-evidence", blocking=True,
            reason="No Stripe evidence was loaded for the web subscription",
        )
    if (
        expected_livemode is not None
        and web_evidence.line in KNOWN_PRODUCT_LINES
        and web_evidence.livemode is not expected_livemode
    ):
        return _unchanged(
            snapshot, "blocked-web-stripe-mode", blocking=True,
            reason="Web-column subscription does not match the expected Stripe mode",
        )
    recovered_web = _safe_customer_web_rebind(
        snapshot,
        web_id,
        customer_subscriptions,
        customer_scan_complete=customer_scan_complete,
        customer_scan_error=customer_scan_error,
        shared_subscription_ids=shared,
        expected_livemode=expected_livemode,
    )
    if recovered_web:
        return IdentityPlan(
            action="rebind-web-to-customer-subscription",
            applyable=True,
            blocking=False,
            reason=(
                "Complete Stripe customer scan proves one matching live "
                "web/EOD subscription and excludes the stale stored ID"
            ),
            web_subscription_id=recovered_web.subscription_id,
            web_subscription_status=recovered_web.status,
            api_subscription_id=api_id,
            api_subscription_status=snapshot.api_subscription_status,
        )
    if web_evidence.line == "unknown":
        return _unchanged(
            snapshot, "preserve-legacy-web", blocking=False,
            reason=web_evidence.reason or "Unscoped legacy web subscription preserved",
        )
    if web_evidence.line in {"error", "conflict", "other"}:
        return _unchanged(
            snapshot, "blocked-web-classification", blocking=True,
            reason="Web column resolves as %s (%s)"
            % (web_evidence.line, web_evidence.reason),
        )
    if not _customer_matches(snapshot, web_evidence):
        return _unchanged(
            snapshot, "blocked-web-customer-mismatch", blocking=True,
            reason="Web subscription belongs to a different Stripe customer",
        )
    if web_evidence.line == "eod":
        return _unchanged(
            snapshot, "preserve-valid-web", blocking=False,
            reason="Stripe metadata confirms a web/EOD subscription",
        )

    if api_id and api_id != web_id:
        return _unchanged(
            snapshot, "blocked-two-api-subscriptions", blocking=True,
            reason=(
                "Web column is API-line but a different API subscription is already "
                "tracked; operator must resolve the two Stripe subscriptions"
            ),
        )

    if not _strong_product_evidence(web_evidence):
        return _unchanged(
            snapshot, "blocked-api-without-price-product-evidence", blocking=True,
            reason=(
                "Subscription metadata says API, but current Stripe Price/Product "
                "metadata does not prove it"
            ),
        )

    api_problem = _api_state_problem(snapshot, web_evidence)
    if api_problem:
        return _unchanged(
            snapshot, "blocked-api-entitlement-state", blocking=True,
            reason=api_problem,
        )

    if customer_scan_error:
        return _unchanged(
            snapshot, "blocked-customer-subscription-scan", blocking=True,
            reason="Stripe customer subscription scan failed: %s"
            % customer_scan_error,
        )
    if not customer_scan_complete:
        return _unchanged(
            snapshot, "blocked-incomplete-customer-subscription-scan",
            blocking=True,
            reason=(
                "Complete Stripe customer subscription history is required "
                "before moving an API ID out of the web column"
            ),
        )

    unique_customer_evidence = {}
    for candidate in customer_subscriptions:
        candidate_id = _text(candidate.subscription_id)
        if candidate_id:
            unique_customer_evidence[candidate_id] = candidate
    customer_evidence = tuple(unique_customer_evidence.values())
    if web_id not in unique_customer_evidence:
        return _unchanged(
            snapshot, "blocked-stored-id-missing-from-customer-scan", blocking=True,
            reason=(
                "Stored web-column subscription was not returned by the complete "
                "Stripe customer subscription scan"
            ),
        )

    ambiguous = [
        candidate for candidate in customer_evidence
        if candidate.line in {"unknown", "error", "conflict", "other"}
        or (
            candidate.line in KNOWN_PRODUCT_LINES
            and not _strong_product_evidence(candidate)
        )
        or not _customer_matches(snapshot, candidate)
        or (
            expected_livemode is not None
            and candidate.livemode is not expected_livemode
        )
    ]
    if ambiguous:
        return _unchanged(
            snapshot, "blocked-ambiguous-customer-subscriptions", blocking=True,
            reason="Customer has unclassified, conflicting, or mismatched subscription evidence",
        )

    other_api = [
        candidate for candidate in customer_evidence
        if candidate.line == "api" and candidate.subscription_id != web_id
    ]
    if other_api:
        return _unchanged(
            snapshot, "blocked-additional-api-subscriptions", blocking=True,
            reason=(
                "Customer has another API subscription; operator must select "
                "the canonical API identity"
            ),
        )

    eod_candidates = [
        candidate for candidate in customer_evidence
        if candidate.line == "eod"
    ]
    if len(eod_candidates) > 1:
        return _unchanged(
            snapshot, "blocked-multiple-web-subscriptions", blocking=True,
            reason=(
                "Customer has more than one web/EOD subscription; operator "
                "must select the canonical web identity"
            ),
        )

    web_tier = _lower(snapshot.web_tier)
    restored_web = eod_candidates[0] if eod_candidates else None
    if restored_web:
        if restored_web.subscription_id in shared:
            return _unchanged(
                snapshot, "blocked-shared-recovered-web-id", blocking=True,
                reason="Recovered web/EOD subscription ID is stored on another user",
            )
        restored_status = _lower(restored_web.status)
        restored_tier = _lower(restored_web.tier)
        if restored_tier not in {"navigator", "analyst", "strategist"}:
            return _unchanged(
                snapshot, "blocked-web-tier-metadata", blocking=True,
                reason="Recovered web/EOD subscription has no recognized tier metadata",
            )
        if web_tier in FREE_WEB_TIERS:
            if restored_status in LIVE_SUBSCRIPTION_STATUSES:
                return _unchanged(
                    snapshot, "blocked-live-web-tier-mismatch", blocking=True,
                    reason=(
                        "Stripe has a live web/EOD subscription but the database "
                        "web tier is %s" % (web_tier or "missing")
                    ),
                )
            if restored_status not in TERMINAL_SUBSCRIPTION_STATUSES:
                return _unchanged(
                    snapshot, "blocked-ambiguous-web-status", blocking=True,
                    reason="Recovered web/EOD subscription status is ambiguous",
                )
        else:
            if (
                web_tier not in {"navigator", "analyst", "strategist"}
                or restored_status not in LIVE_SUBSCRIPTION_STATUSES
                or restored_tier != web_tier
            ):
                return _unchanged(
                    snapshot, "blocked-paid-web-state-mismatch", blocking=True,
                    reason=(
                        "Paid database web tier does not match one live Stripe "
                        "web/EOD subscription"
                    ),
                )
    elif web_tier not in FREE_WEB_TIERS:
        return _unchanged(
            snapshot, "blocked-paid-web-tier-without-eod-identity", blocking=True,
            reason=(
                "Refusing to clear an API ID from a paid web tier without one "
                "verified Stripe web/EOD subscription to restore"
            ),
        )

    # The web column is conclusively carrying an API-line subscription.
    live_status = (
        web_evidence.status
        or snapshot.api_subscription_status
        or snapshot.web_subscription_status
    )
    if not api_id:
        return IdentityPlan(
            action=(
                "restore-web-and-move-api" if restored_web
                else "move-api-from-web"
            ),
            applyable=True,
            blocking=False,
            reason="Stripe metadata proves the web-column ID is API-line",
            web_subscription_id=(
                restored_web.subscription_id if restored_web else None
            ),
            web_subscription_status=(
                restored_web.status if restored_web else None
            ),
            api_subscription_id=web_id,
            api_subscription_status=live_status,
        )
    if api_id == web_id:
        return IdentityPlan(
            action="clear-duplicate-api-from-web",
            applyable=True,
            blocking=False,
            reason="The same API subscription is duplicated in both identities",
            web_subscription_id=(
                restored_web.subscription_id if restored_web else None
            ),
            web_subscription_status=(
                restored_web.status if restored_web else None
            ),
            api_subscription_id=api_id,
            api_subscription_status=live_status,
        )
    return _unchanged(
        snapshot, "blocked-two-api-subscriptions", blocking=True,
        reason=(
            "Web column is API-line but a different API subscription is already "
            "tracked; operator must resolve the two Stripe subscriptions"
        ),
    )
