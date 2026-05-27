-- API gateway schema (ADDITIVE - only CREATE TABLE IF NOT EXISTS; never ALTERs existing
-- tables). Run at the integration step against the same Postgres as the appserver/web:
--   psql "$POSTGRES_DSN" -f apiserver/schema.sql
-- Safe to run on dev pre-cutover (adds 2 tables, touches nothing existing).

CREATE TABLE IF NOT EXISTS api_keys (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         text NOT NULL,
    key_hash     text NOT NULL UNIQUE,          -- HMAC-SHA256(raw_key, API_KEY_HMAC_SECRET)
    prefix       text NOT NULL,                 -- display only, e.g. 'tw_live_9f3a'
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at   timestamptz
);
CREATE INDEX IF NOT EXISTS api_keys_user_idx ON api_keys (user_id);

-- Daily usage rollup (Redis counters are the hot path; a cron rolls them up here).
CREATE TABLE IF NOT EXISTS api_usage_daily (
    user_id   uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day       date NOT NULL,
    endpoint  text NOT NULL,
    count     bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day, endpoint)
);

-- Optional: an explicit API subscription tier per user, distinct from the web 'tier'.
-- The console/billing agent decides whether to use this column or derive from Stripe;
-- tiers.api_tier_from_user() already falls back to the web tier if absent.
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS api_tier text;   -- enable at integration if wanted
