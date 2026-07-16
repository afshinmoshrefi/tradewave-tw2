"""Durable single-flight and idempotency for Stripe Checkout creation.

The browser can replay a form, and both web processes and Gunicorn threads can
handle those requests concurrently.  Stripe's idempotency key prevents a
duplicate remote object, but only if the key and the exact request parameters
survive a worker crash or an unknown network outcome.  This module persists
both before any Stripe call and leases creation to one worker at a time.

No Stripe calls live here.  Callers reserve, perform the network request with
the returned key/payload, then complete or release the claim.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid

from sqlalchemy import func

from models import Session as DefaultSession, StripeCheckoutClaim, User


LEASE_SECONDS = 120
# Stripe validates Checkout ``expires_at`` at Session.create time and requires
# at least 30 minutes remaining.  A recovery starts only after the creation
# lease expires, so the original payload needs lease time plus a real network /
# scheduling buffer.  One hour keeps the remote session and DB authority window
# identical while leaving ample room for the exact-payload retry path.
STRIPE_MIN_CHECKOUT_REMAINING_SECONDS = 30 * 60
CHECKOUT_RECOVERY_EXPIRY_MARGIN_SECONDS = 60
CHECKOUT_SESSION_TTL_SECONDS = 60 * 60
ALLOWED_PRODUCT_LINES = frozenset({"eod", "api"})


class CheckoutClaimError(RuntimeError):
    pass


class CheckoutClaimBusy(CheckoutClaimError):
    """Another worker owns a still-live creation lease."""


class CheckoutClaimDeferred(CheckoutClaimBusy):
    """An unknown outcome cannot be retried safely before claim expiry."""


class CheckoutClaimConflict(CheckoutClaimError):
    """A different unexpired Checkout request already exists for this line."""


class CheckoutClaimLost(CheckoutClaimError):
    """The caller no longer owns the claim it is attempting to update."""


@dataclass(frozen=True)
class CheckoutReservation:
    user_id: object
    product_line: str
    request_fingerprint: str
    payload: dict
    idempotency_key: str
    lease_token: object | None
    session_id: str | None = None
    session_url: str | None = None
    reused: bool = False


def _new_session(session_factory):
    """Return an unscoped session even when the app passes scoped_session."""
    underlying = getattr(session_factory, "session_factory", None)
    return underlying() if callable(underlying) else session_factory()


def _session_close(session_factory, session) -> None:
    session.close()


def _canonical_payload(payload: dict) -> dict:
    """Return a detached JSON-safe copy, failing before any DB/Stripe write."""
    return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def request_fingerprint(payload: dict) -> str:
    """Fingerprint the logical purchase while ignoring per-attempt expiry.

    The persisted payload still includes the original expiry and is what a
    retry sends.  Ignoring only ``expires_at`` means an immediate browser replay
    can reuse the same live session instead of conflicting merely because the
    caller computed a fresh 30-minute deadline.
    """
    normalized = _canonical_payload(payload)
    normalized.pop("expires_at", None)
    encoded = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _payload_expiry(payload: dict) -> datetime:
    raw = payload.get("expires_at")
    if not isinstance(raw, int):
        raise ValueError("Checkout payload requires an integer expires_at")
    expires_at = datetime.fromtimestamp(raw, tz=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise ValueError("Checkout payload expires_at is not in the future")
    return expires_at


def _reservation(row, *, reused: bool) -> CheckoutReservation:
    return CheckoutReservation(
        user_id=row.user_id,
        product_line=row.product_line,
        request_fingerprint=row.request_fingerprint,
        payload=deepcopy(row.request_payload),
        idempotency_key=row.idempotency_key,
        lease_token=row.lease_token,
        session_id=row.stripe_session_id,
        session_url=row.stripe_session_url,
        reused=reused,
    )


def reserve_checkout(
    user_id,
    product_line: str,
    payload: dict,
    *,
    session_factory=DefaultSession,
) -> CheckoutReservation:
    """Reserve one Checkout creation or return its existing live session.

    The user row lock makes first insert/replacement deterministic across
    processes.  The transaction commits the exact payload and idempotency key
    before the caller performs network I/O.
    """
    if product_line not in ALLOWED_PRODUCT_LINES:
        raise ValueError("Unsupported Stripe product line")
    clean_payload = _canonical_payload(payload)
    desired_fingerprint = request_fingerprint(clean_payload)
    desired_expiry = _payload_expiry(clean_payload)

    session = _new_session(session_factory)
    try:
        # Serialize claim mutations for this user.  This lock is held only for
        # the short local transaction, never across a Stripe request.
        owner = (
            session.query(User.id)
            .filter(User.id == user_id)
            .with_for_update()
            .one_or_none()
        )
        if owner is None:
            raise CheckoutClaimError("Checkout owner no longer exists")
        now = session.query(func.now()).scalar()
        row = (
            session.query(StripeCheckoutClaim)
            .filter_by(user_id=user_id, product_line=product_line)
            .with_for_update()
            .one_or_none()
        )

        # An unexpired claim remains authoritative even after its Checkout
        # completion webhook is consumed.  Route-level subscription/customer
        # checks can have been loaded before that webhook committed; allowing a
        # consumed row to roll immediately would let that stale request create
        # a second subscription.  The browser may reuse the completed session
        # (same purchase) or gets a conflict (different purchase) until Stripe's
        # original Checkout expiry closes the race window.
        if row is not None and row.expires_at > now:
            if row.request_fingerprint != desired_fingerprint:
                raise CheckoutClaimConflict(
                    "A different Checkout session is already pending"
                )
            if row.stripe_session_id and row.stripe_session_url:
                session.commit()
                return _reservation(row, reused=True)
            if row.lease_expires_at and row.lease_expires_at > now:
                raise CheckoutClaimBusy("Checkout creation is already in progress")
            # Unknown prior outcome: retry the *stored* payload and key.  This
            # is the critical path that prevents a network timeout from minting
            # a second Stripe subscription.
            remaining = (row.expires_at - now).total_seconds()
            if remaining < (
                STRIPE_MIN_CHECKOUT_REMAINING_SECONDS
                + CHECKOUT_RECOVERY_EXPIRY_MARGIN_SECONDS
            ):
                # If the original request never reached Stripe, resending this
                # exact payload would now violate Stripe's 30-minute minimum.
                # Changing expiry/key could duplicate an outcome that did reach
                # Stripe, so leave the claim authoritative until it expires.
                raise CheckoutClaimDeferred(
                    "Checkout outcome is unresolved until the claim expires"
                )
        else:
            if row is None:
                row = StripeCheckoutClaim(
                    user_id=user_id,
                    product_line=product_line,
                    request_fingerprint=desired_fingerprint,
                    request_payload=clean_payload,
                    idempotency_key=f"tw2-checkout-{uuid.uuid4().hex}",
                    expires_at=desired_expiry,
                )
                session.add(row)
            else:
                row.request_fingerprint = desired_fingerprint
                row.request_payload = clean_payload
                row.idempotency_key = f"tw2-checkout-{uuid.uuid4().hex}"
                row.stripe_session_id = None
                row.stripe_session_url = None
                row.expires_at = desired_expiry
                row.consumed_at = None

        row.lease_token = uuid.uuid4()
        row.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        row.updated_at = now
        session.commit()
        return _reservation(row, reused=False)
    except Exception:
        session.rollback()
        raise
    finally:
        _session_close(session_factory, session)


def replace_checkout_payload(
    reservation: CheckoutReservation,
    payload: dict,
    *,
    session_factory=DefaultSession,
) -> CheckoutReservation:
    """Replace parameters after a definitive pre-creation validation error.

    Call this only when Stripe returned a deterministic 4xx (for example an
    exhausted promotion).  A new idempotency key is necessary because Stripe
    rejects parameter changes under an existing key.
    """
    clean_payload = _canonical_payload(payload)
    new_expiry = _payload_expiry(clean_payload)
    session = _new_session(session_factory)
    try:
        row = (
            session.query(StripeCheckoutClaim)
            .filter_by(
                user_id=reservation.user_id,
                product_line=reservation.product_line,
            )
            .with_for_update()
            .one_or_none()
        )
        if (
            row is None
            or str(row.lease_token or "") != str(reservation.lease_token or "")
            or row.idempotency_key != reservation.idempotency_key
        ):
            raise CheckoutClaimLost("Checkout claim changed during fallback")
        now = session.query(func.now()).scalar()
        row.request_payload = clean_payload
        # Keep the original browser request fingerprint.  This replacement is
        # an execution fallback after Stripe definitively rejected an optional
        # promotion, not a new logical purchase.  If the successful redirect is
        # lost, replaying the original form must recover the plain Checkout URL
        # instead of conflicting with it.  The exact fallback payload and its
        # new idempotency key are still what an unknown-outcome retry sends.
        row.idempotency_key = f"tw2-checkout-{uuid.uuid4().hex}"
        row.expires_at = new_expiry
        row.updated_at = now
        session.commit()
        return _reservation(row, reused=False)
    except Exception:
        session.rollback()
        raise
    finally:
        _session_close(session_factory, session)


def complete_checkout(
    reservation: CheckoutReservation,
    session_id: str,
    session_url: str,
    *,
    session_factory=DefaultSession,
) -> None:
    if not session_id or not session_url:
        raise ValueError("Stripe Checkout response lacks id or url")
    session = _new_session(session_factory)
    try:
        row = (
            session.query(StripeCheckoutClaim)
            .filter_by(
                user_id=reservation.user_id,
                product_line=reservation.product_line,
            )
            .with_for_update()
            .one_or_none()
        )
        if (
            row is None
            or str(row.lease_token or "") != str(reservation.lease_token or "")
            or row.idempotency_key != reservation.idempotency_key
        ):
            raise CheckoutClaimLost("Checkout claim changed before completion")
        row.stripe_session_id = session_id
        row.stripe_session_url = session_url
        row.lease_token = None
        row.lease_expires_at = None
        row.updated_at = session.query(func.now()).scalar()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        _session_close(session_factory, session)


def release_checkout(
    reservation: CheckoutReservation,
    *,
    session_factory=DefaultSession,
) -> None:
    """Release a lease while retaining payload/key for an idempotent retry."""
    session = _new_session(session_factory)
    try:
        row = (
            session.query(StripeCheckoutClaim)
            .filter_by(
                user_id=reservation.user_id,
                product_line=reservation.product_line,
            )
            .with_for_update()
            .one_or_none()
        )
        if (
            row is not None
            and str(row.lease_token or "") == str(reservation.lease_token or "")
            and row.idempotency_key == reservation.idempotency_key
        ):
            now = session.query(func.now()).scalar()
            row.lease_token = None
            row.lease_expires_at = now
            row.updated_at = now
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        _session_close(session_factory, session)


def consume_checkout(session, user_id, product_line: str, session_id: str) -> bool:
    """Mark a matching completed Checkout claim consumed in caller's transaction.

    The Stripe webhook already owns a locked SQLAlchemy transaction.  Reusing
    it avoids a second scoped session and makes claim consumption atomic with
    receipt processing.  A stale or foreign session is a harmless no-op.
    """
    if product_line not in ALLOWED_PRODUCT_LINES or not session_id:
        return False
    row = (
        session.query(StripeCheckoutClaim)
        .filter_by(user_id=user_id, product_line=product_line)
        .with_for_update()
        .one_or_none()
    )
    if row is None or row.stripe_session_id != session_id:
        return False
    now = session.query(func.now()).scalar()
    row.consumed_at = now
    row.lease_token = None
    row.lease_expires_at = None
    row.updated_at = now
    return True
