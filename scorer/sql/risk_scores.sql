-- Scorer output. listing_id is the normalised key "<platform>:<platform_listing_id>".
CREATE TABLE IF NOT EXISTS risk_scores (
    listing_id     TEXT PRIMARY KEY,
    cluster_id     TEXT NOT NULL,
    score          REAL NOT NULL,
    band           TEXT NOT NULL,
    coverage       REAL NOT NULL,
    contributions  JSONB NOT NULL,
    reasons        JSONB NOT NULL,
    model_version  TEXT NOT NULL,
    input_hash     TEXT NOT NULL,
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_risk_scores_cluster ON risk_scores (cluster_id);
