#!/usr/bin/env python3
"""Audit and repair web/API Stripe subscription identity separation.

Run after Alembic revision d8c4e6a2f9b1 and before the MailerLite lifecycle
backfill. The default is a read-only dry run: it reads users and retrieves the
stored subscriptions from Stripe, but writes nothing. ``--apply`` is allowed
only while MailerLite outbound writes are disabled.

Automatic repair is intentionally narrow:

* a confirmed web/EOD subscription is never changed;
* an unlabelled legacy web subscription is preserved;
* before an API-line ID leaves the web column, every Stripe subscription for
  that customer is paged and classified; one unambiguous EOD identity is
  restored when it exactly matches current web state;
* a paid web tier is never cleared automatically;
* a web-column API ID moves into the empty API identity, or is cleared from web
  when the exact same ID is already in the API identity;
* retrieval errors, partial pagination, customer/tier/status mismatches, shared
  IDs, conflicting metadata, and multiple candidate subscriptions block the
  entire apply for manual review;
* ``--apply`` also requires an explicit ``TW2_ENV=prod`` and disabled
  MailerLite outbound writes.

Canonical production commands:

  sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; \
    cd /home/flask && /home/flask/venv/bin/python \
    /home/flask/ops/audit_stripe_subscription_identity.py'
  sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; \
    cd /home/flask && /home/flask/venv/bin/python \
    /home/flask/ops/audit_stripe_subscription_identity.py --apply'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(ROOT), str(ROOT / "web"), "/home/flask", "/home/flask/web"):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import stripe  # noqa: E402
from sqlalchemy import or_  # noqa: E402

import config  # noqa: E402
from models import AuditLog, Session, User  # noqa: E402
from ops.stripe_subscription_identity import (  # noqa: E402
    SubscriptionClassification,
    UserIdentitySnapshot,
    classification_error,
    classify_subscription_payload,
    plan_identity_reconciliation,
)


AUDIT_ACTOR = "ops:audit_stripe_subscription_identity"
AUDIT_ACTION = "stripe_subscription_identity_reconciled"


def _plain(value: Any):
    """Recursively convert StripeObject values into plain Python containers."""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    for method_name in ("to_dict_recursive", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            return _plain(method())
    return value


def _complete_list(raw: Any, *, context: str) -> list:
    """Materialize every Stripe list page or fail instead of using a prefix."""
    auto_paging_iter = getattr(raw, "auto_paging_iter", None)
    if callable(auto_paging_iter):
        return [_plain(item) for item in auto_paging_iter()]
    payload = _plain(raw)
    if not isinstance(payload, Mapping):
        raise RuntimeError("%s did not return a Stripe list" % context)
    if payload.get("has_more"):
        raise RuntimeError("%s is paginated but has no auto_paging_iter" % context)
    data = payload.get("data") or []
    if not isinstance(data, list):
        raise RuntimeError("%s returned malformed list data" % context)
    return data


def _expanded_subscription(subscription_id: str) -> dict:
    """Retrieve a subscription and ensure each Price's Product is expanded."""
    raw = stripe.Subscription.retrieve(
        subscription_id,
        expand=["items.data.price.product"],
    )
    subscription = _plain(raw)
    if str(subscription.get("id") or "") != str(subscription_id):
        raise RuntimeError("Stripe returned a different subscription ID")
    items_container = subscription.get("items") or {}
    if items_container.get("has_more"):
        raw_items = stripe.SubscriptionItem.list(
            subscription=subscription_id,
            limit=100,
            expand=["data.price.product"],
        )
        items = _complete_list(
            raw_items, context="subscription %s items" % subscription_id,
        )
        subscription["items"] = {"data": items, "has_more": False}
    else:
        items = items_container.get("data") or []
    for item in items:
        price = item.get("price") or {}
        product = price.get("product")
        if isinstance(product, Mapping):
            continue
        price_id = str(price.get("id") or "").strip()
        if not price_id:
            continue
        # Some Stripe API versions do not honor the nested Product expansion.
        # A direct Price lookup keeps the audit based on current Product metadata.
        item["price"] = _plain(
            stripe.Price.retrieve(price_id, expand=["product"])
        )
    return subscription


def _customer_subscription_ids(customer_ids):
    """List every subscription ID for each customer, including all statuses."""
    result = {}
    errors = {}
    for customer_id in sorted(customer_ids):
        try:
            raw = stripe.Subscription.list(
                customer=customer_id,
                status="all",
                limit=100,
            )
            subscriptions = _complete_list(
                raw, context="customer %s subscriptions" % customer_id,
            )
            subscription_ids = []
            for subscription in subscriptions:
                subscription_id = str(subscription.get("id") or "").strip()
                if not subscription_id:
                    raise RuntimeError(
                        "customer subscription list contains an object without an ID"
                    )
                subscription_ids.append(subscription_id)
            result[customer_id] = tuple(sorted(set(subscription_ids)))
        except Exception as exc:
            errors[customer_id] = "%s:%s" % (
                type(exc).__name__, str(exc)[:160],
            )
    return result, errors


def _customer_ids_for_identity_audit(snapshots):
    """Scan every customer whose stored web identity may need verification."""
    return {
        snapshot.customer_id
        for snapshot in snapshots
        if snapshot.customer_id and snapshot.web_subscription_id
    }


def _snapshot_rows():
    session = Session()
    try:
        rows = (
            session.query(User)
            .filter(
                or_(
                    User.stripe_subscription_id.isnot(None),
                    User.api_stripe_subscription_id.isnot(None),
                )
            )
            .order_by(User.created_at, User.id)
            .all()
        )
        snapshots = [
            UserIdentitySnapshot(
                user_id=str(user.id),
                email=(user.email or "").strip().lower(),
                customer_id=(user.stripe_customer_id or None),
                web_subscription_id=(user.stripe_subscription_id or None),
                web_subscription_status=(user.stripe_subscription_status or None),
                api_subscription_id=(user.api_stripe_subscription_id or None),
                api_subscription_status=(
                    user.api_stripe_subscription_status or None
                ),
                web_tier=(user.tier or None),
                api_tier=(user.api_tier or None),
            )
            for user in rows
        ]
        session.rollback()
        return snapshots
    finally:
        session.close()
        Session.remove()


def _classifications(subscription_ids):
    result = {}
    for subscription_id in sorted(subscription_ids):
        try:
            result[subscription_id] = classify_subscription_payload(
                _expanded_subscription(subscription_id)
            )
        except Exception as exc:
            # A 404 can also mean the wrong Stripe mode/key, so absence is not
            # proof that the database identity is stale. Never clear on error.
            result[subscription_id] = classification_error(
                subscription_id, type(exc).__name__,
            )
    return result


def _build_plans(
    snapshots,
    evidence,
    *,
    customer_subscription_ids=None,
    customer_scan_errors=None,
    expected_livemode=None,
):
    customer_subscription_ids = customer_subscription_ids or {}
    customer_scan_errors = customer_scan_errors or {}
    owners = defaultdict(set)
    for snapshot in snapshots:
        for subscription_id in (
            snapshot.web_subscription_id,
            snapshot.api_subscription_id,
        ):
            if subscription_id:
                owners[subscription_id].add(snapshot.user_id)
    plans = []
    for snapshot in snapshots:
        web_evidence = evidence.get(snapshot.web_subscription_id)
        api_evidence = evidence.get(snapshot.api_subscription_id)
        foreign_owned = tuple(
            subscription_id
            for subscription_id, user_ids in owners.items()
            if user_ids - {snapshot.user_id}
        )
        customer_ids = customer_subscription_ids.get(snapshot.customer_id, ())
        customer_evidence = tuple(
            evidence[subscription_id]
            for subscription_id in customer_ids
            if subscription_id in evidence
        )
        plan = plan_identity_reconciliation(
            snapshot,
            web_evidence,
            api_evidence,
            shared_subscription_ids=foreign_owned,
            customer_subscriptions=customer_evidence,
            customer_scan_complete=(
                snapshot.customer_id in customer_subscription_ids
            ),
            customer_scan_error=customer_scan_errors.get(snapshot.customer_id),
            expected_livemode=expected_livemode,
        )
        plans.append((snapshot, web_evidence, api_evidence, plan, customer_evidence))
    return plans


def _print_plans(plans, *, apply_mode: bool):
    counts = Counter()
    blocking = 0
    for snapshot, web_evidence, api_evidence, plan, customer_evidence in plans:
        counts[plan.action] += 1
        blocking += int(plan.blocking)
        print(json.dumps({
            "mode": "APPLY" if apply_mode else "DRY-RUN",
            "user_id": snapshot.user_id,
            "email": snapshot.email,
            "web_subscription_id": snapshot.web_subscription_id,
            "web_classification": (
                web_evidence.line if web_evidence else None
            ),
            "web_stripe_status": (
                web_evidence.status if web_evidence else None
            ),
            "api_subscription_id": snapshot.api_subscription_id,
            "api_classification": (
                api_evidence.line if api_evidence else None
            ),
            "action": plan.action,
            "blocking": plan.blocking,
            "customer_subscriptions": [
                {
                    "id": candidate.subscription_id,
                    "line": candidate.line,
                    "status": candidate.status,
                    "tier": candidate.tier,
                    "livemode": candidate.livemode,
                    "reason": candidate.reason,
                }
                for candidate in customer_evidence
            ],
            "reason": plan.reason,
        }, sort_keys=True))
    print(json.dumps({
        "mode": "APPLY" if apply_mode else "DRY-RUN",
        "summary": dict(sorted(counts.items())),
        "users": len(plans),
        "blocking": blocking,
    }, sort_keys=True))
    return blocking


def _same_snapshot(user: User, snapshot: UserIdentitySnapshot) -> bool:
    return (
        (user.stripe_subscription_id or None)
        == snapshot.web_subscription_id
        and (user.stripe_subscription_status or None)
        == snapshot.web_subscription_status
        and (user.api_stripe_subscription_id or None)
        == snapshot.api_subscription_id
        and (user.api_stripe_subscription_status or None)
        == snapshot.api_subscription_status
        and (user.stripe_customer_id or None) == snapshot.customer_id
        and (user.tier or None) == snapshot.web_tier
        and (user.api_tier or None) == snapshot.api_tier
    )


def _apply(plans) -> int:
    session = Session()
    changed = 0
    try:
        for snapshot, web_evidence, _api_evidence, plan, customer_evidence in plans:
            if not plan.applyable:
                continue
            user = (
                session.query(User)
                .filter_by(id=snapshot.user_id)
                .with_for_update()
                .one()
            )
            if not _same_snapshot(user, snapshot):
                raise RuntimeError(
                    "user %s changed after Stripe audit; rerun dry-run"
                    % snapshot.user_id
                )
            planned_ids = {
                subscription_id for subscription_id in (
                    plan.web_subscription_id,
                    plan.api_subscription_id,
                ) if subscription_id
            }
            if planned_ids:
                foreign_owner = (
                    session.query(User.id)
                    .filter(User.id != user.id)
                    .filter(or_(
                        User.stripe_subscription_id.in_(planned_ids),
                        User.api_stripe_subscription_id.in_(planned_ids),
                    ))
                    .with_for_update()
                    .first()
                )
                if foreign_owner:
                    raise RuntimeError(
                        "planned Stripe subscription identity acquired another owner"
                    )
            before = {
                "stripe_subscription_id": user.stripe_subscription_id,
                "stripe_subscription_status": user.stripe_subscription_status,
                "api_stripe_subscription_id": user.api_stripe_subscription_id,
                "api_stripe_subscription_status": (
                    user.api_stripe_subscription_status
                ),
            }
            user.stripe_subscription_id = plan.web_subscription_id
            user.stripe_subscription_status = plan.web_subscription_status
            user.api_stripe_subscription_id = plan.api_subscription_id
            user.api_stripe_subscription_status = plan.api_subscription_status
            session.add(AuditLog(
                actor_label=AUDIT_ACTOR,
                action=AUDIT_ACTION,
                target_user_id=user.id,
                details={
                    "repair_action": plan.action,
                    "classification": (
                        web_evidence.line if web_evidence else None
                    ),
                    "classification_reason": (
                        web_evidence.reason if web_evidence else None
                    ),
                    "stripe_customer_id": snapshot.customer_id,
                    "database_web_tier": snapshot.web_tier,
                    "database_api_tier": snapshot.api_tier,
                    "customer_subscription_evidence": [
                        {
                            "id": candidate.subscription_id,
                            "line": candidate.line,
                            "status": candidate.status,
                            "tier": candidate.tier,
                            "livemode": candidate.livemode,
                            "reason": candidate.reason,
                        }
                        for candidate in customer_evidence
                    ],
                    "before": before,
                    "after": {
                        "stripe_subscription_id": plan.web_subscription_id,
                        "stripe_subscription_status": plan.web_subscription_status,
                        "api_stripe_subscription_id": plan.api_subscription_id,
                        "api_stripe_subscription_status": (
                            plan.api_subscription_status
                        ),
                    },
                },
            ))
            changed += 1
        session.commit()
        return changed
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        Session.remove()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    apply_group = parser.add_mutually_exclusive_group()
    apply_group.add_argument(
        "--apply", action="store_true",
        help="commit safe LIVE-mode identity moves in prod",
    )
    apply_group.add_argument(
        "--apply-test-mode", action="store_true",
        help="commit safe TEST-mode identity moves in dev only",
    )
    args = parser.parse_args(argv)
    apply_mode = args.apply or args.apply_test_mode
    environment = os.environ.get("TW2_ENV", "").strip().lower()

    if args.apply and environment != "prod":
        print(
            "REFUSING --apply unless TW2_ENV=prod is explicitly set; "
            "dry-run is allowed in every environment.",
            file=sys.stderr,
        )
        return 2
    if args.apply_test_mode and environment != "dev":
        print(
            "REFUSING --apply-test-mode unless TW2_ENV=dev is explicitly set.",
            file=sys.stderr,
        )
        return 2
    if apply_mode and config.MAILERLITE_OUTBOUND_ENABLED:
        print(
            "REFUSING --apply while MAILERLITE_OUTBOUND_ENABLED is true; "
            "set it to 0 and restart the web service first.",
            file=sys.stderr,
        )
        return 2
    secret_key = (config.STRIPE_SECRET_KEY or "").strip()
    if not secret_key or "PLACEHOLDER" in secret_key.upper():
        print("STRIPE_SECRET_KEY is missing or a placeholder", file=sys.stderr)
        return 2
    if args.apply_test_mode and not secret_key.startswith("sk_test_"):
        print(
            "REFUSING --apply-test-mode without a Stripe TEST secret key.",
            file=sys.stderr,
        )
        return 2

    stripe.api_key = secret_key
    stripe.max_network_retries = 2
    stripe.default_http_client = stripe._http_client.RequestsClient(timeout=15)

    try:
        snapshots = _snapshot_rows()
    except Exception as exc:
        print(
            "Could not read subscription identities; run migrations through "
            "d8c4e6a2f9b1 first (%s)." % type(exc).__name__,
            file=sys.stderr,
        )
        return 2
    subscription_ids = {
        subscription_id
        for snapshot in snapshots
        for subscription_id in (
            snapshot.web_subscription_id,
            snapshot.api_subscription_id,
        )
        if subscription_id
    }
    evidence = _classifications(subscription_ids)

    repair_customers = _customer_ids_for_identity_audit(snapshots)
    customer_ids, customer_scan_errors = _customer_subscription_ids(
        repair_customers,
    )
    discovered_ids = {
        subscription_id
        for ids in customer_ids.values()
        for subscription_id in ids
    }
    evidence.update(_classifications(discovered_ids - set(evidence)))
    plans = _build_plans(
        snapshots,
        evidence,
        customer_subscription_ids=customer_ids,
        customer_scan_errors=customer_scan_errors,
        expected_livemode=(
            False if args.apply_test_mode else environment == "prod"
        ),
    )
    blocking = _print_plans(plans, apply_mode=apply_mode)

    if blocking:
        print(
            "REFUSING changes: resolve every blocking row and rerun the dry-run.",
            file=sys.stderr,
        )
        return 2
    if apply_mode:
        try:
            changed = _apply(plans)
        except Exception as exc:
            print(
                "No changes committed: %s: %s"
                % (type(exc).__name__, str(exc)[:200]),
                file=sys.stderr,
            )
            return 2
        print("APPLIED changed=%d" % changed)
    else:
        print(
            "DRY-RUN complete; rerun with --apply only after every row "
            "has been reviewed."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
