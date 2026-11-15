-- Initial schema for a fresh deployment. PostgreSQL runs this once on an empty data volume.
-- Cross-service tables have no foreign keys: independent consumers can write in any order.
-- HTTP collectors write each listing and its reviews in the same transaction.

CREATE TABLE listings (
  id                serial UNIQUE NOT NULL,   -- HTTP collector/review reference
  sku               text,
  listing_id        text PRIMARY KEY,          -- "<source_platform>:<source_listing_id>"
  source_platform   text        NOT NULL,
  source_listing_id text        NOT NULL,
  title             text,
  price             numeric(12, 2),
  currency          text,
  seller_id         text,
  seller_name       text,
  selling_since     date,
  rating            numeric(3, 2),
  review_count      integer NOT NULL DEFAULT 0,
  scraped_at        timestamptz NOT NULL DEFAULT now(),
  product_url       text        NOT NULL,
  cluster_id        text,
  payload           jsonb       NOT NULL,      -- latest full message
  first_seen_at     timestamptz NOT NULL DEFAULT now(),
  last_seen_at      timestamptz NOT NULL,      -- scraped_at of the newest version seen
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX listings_last_seen_at_idx ON listings (last_seen_at);
CREATE TABLE reviews (
  id serial PRIMARY KEY,
  listing_id integer NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  text text,
  rating smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
  review_date date
);
CREATE INDEX idx_reviews_listing ON reviews (listing_id);

CREATE TABLE clusters (
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
CREATE TABLE matcher_listings (
  listing_id  text PRIMARY KEY,
  brand_key   text        NOT NULL,
  payload     jsonb       NOT NULL,
  scraped_at  timestamptz,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX matcher_listings_brand_key_idx ON matcher_listings (brand_key);

-- Owned by the scorer: same columns as scorer/sql/risk_scores.sql. One row per listing (latest score);
-- input_hash makes a replayed message a no-op.
CREATE TABLE risk_scores (
  listing_id     text PRIMARY KEY,
  cluster_id     text        NOT NULL,
  score          real        NOT NULL,
  band           text        NOT NULL,
  coverage       real        NOT NULL,
  contributions  jsonb       NOT NULL,
  reasons        jsonb       NOT NULL,
  model_version  text        NOT NULL,
  input_hash     text        NOT NULL,
  source_scraped_at timestamptz,
  computed_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_risk_scores_cluster ON risk_scores (cluster_id);

-- Durable search progress survives gateway restarts and can be read by any replica.
CREATE TABLE search_requests (
  request_id uuid PRIMARY KEY,
  product_url text NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'complete', 'failed')),
  result jsonb,
  error text,
  requested_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE collection_runs (
  request_id uuid NOT NULL,
  source_platform text NOT NULL,
  listing_ids text[] NOT NULL DEFAULT '{}',
  error text,
  completed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (request_id, source_platform)
);
