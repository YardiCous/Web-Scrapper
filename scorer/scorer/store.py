"""
Idempotent writes to risk_scores.

input_hash covers the listing itself and the sorted cluster prices, so a
replayed message is a no-op while a moved cluster median triggers a rescore.
"""

import hashlib
import json

from psycopg.types.json import Jsonb

from .combiner import ScoreResult
from .models import Listing

_UPSERT = """
    INSERT INTO risk_scores (listing_id, cluster_id, score, band, coverage,
                             contributions, reasons, model_version, input_hash)
    VALUES (%(listing_id)s, %(cluster_id)s, %(score)s, %(band)s, %(coverage)s,
            %(contributions)s, %(reasons)s, %(model_version)s, %(input_hash)s)
    ON CONFLICT (listing_id) DO UPDATE SET
        cluster_id    = EXCLUDED.cluster_id,
        score         = EXCLUDED.score,
        band          = EXCLUDED.band,
        coverage      = EXCLUDED.coverage,
        contributions = EXCLUDED.contributions,
        reasons       = EXCLUDED.reasons,
        model_version = EXCLUDED.model_version,
        input_hash    = EXCLUDED.input_hash,
        computed_at   = now()
    WHERE risk_scores.input_hash    IS DISTINCT FROM EXCLUDED.input_hash
       OR risk_scores.model_version IS DISTINCT FROM EXCLUDED.model_version
"""


def input_hash(listing: Listing, cluster_prices) -> str:
    payload = {
        "listing": listing.model_dump(mode="json"),
        "cluster_prices": sorted(cluster_prices),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upsert(conn, listing: Listing, result: ScoreResult, hash_: str) -> bool:
    """Write one score. Returns True if a row was inserted/changed, False on a no-op."""
    with conn.cursor() as cur:
        cur.execute(_UPSERT, {
            "listing_id": listing.listing_id,
            "cluster_id": listing.cluster_id,
            "score": result.score,
            "band": result.band,
            "coverage": result.coverage,
            "contributions": Jsonb(result.contributions),
            "reasons": Jsonb(result.reasons),
            "model_version": result.model_version,
            "input_hash": hash_,
        })
        return cur.rowcount == 1
