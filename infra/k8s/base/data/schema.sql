-- Runs as an initdb script on first start and again on every `make up` (existing volumes), so every
-- statement must be idempotent.
-- No foreign keys: rows arrive from independent consumers in any order.

CREATE TABLE IF NOT EXISTS listings (
  listing_id        text PRIMARY KEY,          -- "<source_platform>:<source_listing_id>"
  source_platform   text        NOT NULL,
  source_listing_id text        NOT NULL,
  title             text,
  price             numeric(12, 2),
  currency          text,
  seller_id         text,
  product_url       text        NOT NULL,
  cluster_id        text,
  payload           jsonb       NOT NULL,      -- latest full message
  first_seen_at     timestamptz NOT NULL DEFAULT now(),
  last_seen_at      timestamptz NOT NULL,      -- scraped_at of the newest version seen
  updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS listings_last_seen_at_idx ON listings (last_seen_at);

CREATE TABLE IF NOT EXISTS clusters (
  cluster_id         text PRIMARY KEY,
  brand              text,
  member_listing_ids text[]      NOT NULL DEFAULT '{}',
  platforms          text[]      NOT NULL DEFAULT '{}',
  size               integer     NOT NULL DEFAULT 0,
  price_median_sgd   numeric(12, 2),
  price_min_sgd      numeric(12, 2),
  price_max_sgd      numeric(12, 2),
  version            bigint      NOT NULL DEFAULT 1,  -- optimistic concurrency: see docs/contracts.md
  updated_at         timestamptz NOT NULL DEFAULT now()
);

-- Owned by the matcher: every cleaned listing it has seen, so any replica (or a restarted one) can
-- re-cluster a whole brand. brand_key is the listings.cleaned message key.
CREATE TABLE IF NOT EXISTS matcher_listings (
  listing_id  text PRIMARY KEY,
  brand_key   text        NOT NULL,
  payload     jsonb       NOT NULL,
  scraped_at  timestamptz,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS matcher_listings_brand_key_idx ON matcher_listings (brand_key);

-- Owned by the scorer: identical to scorer/sql/risk_scores.sql, so running either file is a no-op once the other has run. One row per listing (latest score);
-- input_hash makes a replayed message a no-op.
CREATE TABLE IF NOT EXISTS risk_scores (
  listing_id     text PRIMARY KEY,
  cluster_id     text        NOT NULL,
  score          real        NOT NULL,
  band           text        NOT NULL,
  coverage       real        NOT NULL,
  contributions  jsonb       NOT NULL,
  reasons        jsonb       NOT NULL,
  model_version  text        NOT NULL,
  input_hash     text        NOT NULL,
  computed_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_risk_scores_cluster ON risk_scores (cluster_id);
