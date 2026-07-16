"""Add durable cross-worker Stripe Checkout claims.

Revision ID: e9b7c4d2a6f1
Revises: d8c4e6a2f9b1
Create Date: 2026-07-16
"""
from alembic import op


revision = "e9b7c4d2a6f1"
down_revision = "d8c4e6a2f9b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # apiserver/schema.sql may run first on the API box, so keep the Alembic
    # migration idempotent for the shared database.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS stripe_checkout_claims (
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            product_line text NOT NULL,
            request_fingerprint text NOT NULL,
            request_payload jsonb NOT NULL,
            idempotency_key text NOT NULL UNIQUE,
            lease_token uuid,
            lease_expires_at timestamptz,
            stripe_session_id text UNIQUE,
            stripe_session_url text,
            expires_at timestamptz NOT NULL,
            consumed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, product_line),
            CONSTRAINT stripe_checkout_claims_product_line_check
                CHECK (product_line IN ('eod', 'api')),
            CONSTRAINT stripe_checkout_claims_session_pair_check
                CHECK ((stripe_session_id IS NULL) =
                       (stripe_session_url IS NULL))
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stripe_checkout_claims")
