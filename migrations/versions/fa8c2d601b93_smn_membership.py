"""Add isolated SMN reader authorities, membership, offers and access grants."""
from alembic import op

revision = "fa8c2d601b93"
down_revision = "e9b7c4d2a6f1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE smn_offers (
      id serial PRIMARY KEY, mode text NOT NULL CHECK (mode IN ('free','paid')),
      currency text NOT NULL CHECK (currency IN ('usd','eur','gbp','cad','aud','jpy')),
      monthly_amount integer NOT NULL CHECK (monthly_amount >= 0),
      annual_mode text NOT NULL CHECK (annual_mode IN ('explicit','discount')),
      annual_amount integer NOT NULL CHECK (annual_amount >= 0),
      annual_discount_bps integer CHECK (annual_discount_bps BETWEEN 0 AND 9999),
      trial_days integer NOT NULL CHECK (trial_days BETWEEN 0 AND 365),
      intervals jsonb NOT NULL, stripe_product_id text, stripe_monthly_price_id text,
      stripe_annual_price_id text, activated_at timestamptz,
      created_by uuid REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE smn_settings (
      id integer PRIMARY KEY CHECK (id = 1), version integer NOT NULL DEFAULT 1,
      active_offer_id integer NOT NULL REFERENCES smn_offers(id)
    );
    CREATE TABLE smn_memberships (
      user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      enrollment_offer_id integer NOT NULL REFERENCES smn_offers(id),
      verified_at timestamptz NOT NULL, first_trial_started_at timestamptz,
      first_trial_ends_at timestamptz, suspended_at timestamptz,
      stripe_customer_id text UNIQUE, stripe_subscription_id text UNIQUE,
      stripe_subscription_status text, subscription_offer_id integer REFERENCES smn_offers(id),
      cancel_at_period_end boolean NOT NULL DEFAULT false, period_ends_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE smn_grants (
      id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES smn_memberships(user_id) ON DELETE CASCADE,
      source text NOT NULL CHECK (source IN ('free_launch','trial','paid','admin')),
      source_key text NOT NULL UNIQUE, offer_id integer NOT NULL REFERENCES smn_offers(id),
      starts_at timestamptz NOT NULL, ends_at timestamptz CHECK (ends_at >= starts_at),
      revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_smn_grants_user ON smn_grants(user_id);
    CREATE TABLE smn_authorities (
      token_hash text PRIMARY KEY, kind text NOT NULL CHECK (kind IN ('reader','admin')),
      csrf_hash text, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      workos_user_id text NOT NULL, workos_session_id text NOT NULL,
      environment text NOT NULL, expires_at timestamptz NOT NULL,
      revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
    );
    ALTER TABLE stripe_checkout_claims DROP CONSTRAINT stripe_checkout_claims_product_line_check;
    ALTER TABLE stripe_checkout_claims ADD CONSTRAINT stripe_checkout_claims_product_line_check
      CHECK (product_line IN ('eod','api','smn'));
    INSERT INTO smn_offers(mode,currency,monthly_amount,annual_mode,annual_amount,trial_days,intervals,activated_at)
      VALUES ('free','usd',0,'explicit',0,0,'[]'::jsonb,now());
    INSERT INTO smn_settings(id,version,active_offer_id) VALUES (1,1,currval('smn_offers_id_seq'));
    """)


def downgrade():
    # Membership/payment authority is durable. App rollback must never drop it.
    raise RuntimeError("SMN membership records must be preserved through application rollback")
