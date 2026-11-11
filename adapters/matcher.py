"""Matcher adapter: listings.cleaned -> listings.normalized, using Gordon's matching code as is.

listings.cleaned is keyed by brand, so one matcher replica owns every listing of a brand. Each batch
saves its listings to matcher_listings, re-runs find_matches/build_clusters for every brand it touched,
saves each cluster with an optimistic-concurrency version check, and publishes one scoring row per
listing (keyed by cluster_id) for every cluster that changed or holds a listing from the batch. Matching
within a brand gives the same clusters as Gordon's batch run over all listings (checked on
normaliser/data).

The database transaction commits only after the rows are published, so a crash in between rolls the
clusters back and the redelivered batch publishes them again.
"""
from psycopg.types.json import Jsonb

from cdc_tools.common import connect_db, log
from normaliser.core.cluster import build_clusters
from normaliser.core.match import find_matches
from normaliser.core.pipeline import stable_cluster_id, to_scoring_rows

from .normaliser import UNBRANDED
from .worker import Reject, run as run_worker

OCC_ATTEMPTS = 5

SAVE_LISTING = """
INSERT INTO matcher_listings AS m (listing_id, brand_key, payload, scraped_at)
VALUES (%s, %s, %s, %s)
ON CONFLICT (listing_id) DO UPDATE SET
  brand_key = EXCLUDED.brand_key, payload = EXCLUDED.payload, scraped_at = EXCLUDED.scraped_at, updated_at = now()
WHERE m.scraped_at IS NULL OR m.scraped_at <= EXCLUDED.scraped_at
"""
READ_CLUSTER = """
SELECT version, brand, member_listing_ids, platforms, size, price_median_sgd, price_min_sgd, price_max_sgd
FROM clusters WHERE cluster_id = %s
"""
UPDATE_CLUSTER = """
UPDATE clusters SET brand = %s, member_listing_ids = %s, platforms = %s, size = %s, price_median_sgd = %s,
  price_min_sgd = %s, price_max_sgd = %s, version = version + 1, updated_at = now()
WHERE cluster_id = %s AND version = %s
"""

db = None
pending = {}   # listing_id -> (brand_key, cleaned listing); the newest copy in a batch wins


def handle(brand_key, rec):
    if not brand_key or not rec.get("listing_id"):
        raise Reject("missing brand key or listing_id")
    pending[rec["listing_id"]] = (brand_key, rec)
    return []


def _same(stored, fields):
    def norm(v):
        return round(float(v), 2) if v is not None and not isinstance(v, (str, list)) else v
    return [norm(v) for v in stored] == [norm(v) for v in fields]


def save_cluster(cur, c):
    """Write the cluster if it changed. Optimistic concurrency: the update applies only if the version is
    still the one read; otherwise another writer got there first, so re-read and try again."""
    fields = (c["brand"], sorted(m["listing_id"] for m in c["listings"]), c["platforms"], c["num_listings"],
              c["price_median_sgd"], c["price_min_sgd"], c["price_max_sgd"])
    cur.execute("INSERT INTO clusters (cluster_id, brand) VALUES (%s, %s) ON CONFLICT (cluster_id) DO NOTHING",
                (c["cluster_id"], c["brand"]))
    for attempt in range(1, OCC_ATTEMPTS + 1):
        version, *stored = cur.execute(READ_CLUSTER, (c["cluster_id"],)).fetchone()
        if _same(stored, fields):
            return False
        cur.execute(UPDATE_CLUSTER, (*fields, c["cluster_id"], version))
        if cur.rowcount == 1:
            return True
        log("occ_conflict", cluster_id=c["cluster_id"], attempt=attempt)
    raise RuntimeError(f"cluster {c['cluster_id']}: version kept changing after {OCC_ATTEMPTS} attempts")


def end_batch():
    global db
    if not pending:
        return []
    if db is None:
        db = connect_db()
    out, changed = [], 0
    cur = db.cursor()
    for lid, (brand_key, rec) in pending.items():
        cur.execute(SAVE_LISTING, (lid, brand_key, Jsonb(rec), rec.get("scraped_at")))
    for brand_key in sorted({b for b, _ in pending.values()}):
        listings = [row[0] for row in cur.execute(
            "SELECT payload FROM matcher_listings WHERE brand_key = %s ORDER BY listing_id", (brand_key,))]
        clusters = build_clusters(listings, find_matches(listings))
        for c in clusters:
            c["cluster_id"] = stable_cluster_id(c["listings"])
            was_changed = save_cluster(cur, c)
            changed += was_changed
            if was_changed or any(m["listing_id"] in pending for m in c["listings"]):
                out += [(row["cluster_id"], row) for row in to_scoring_rows(c)]
        # Clusters of this brand that no longer exist (e.g. merged into one with a smaller id).
        cur.execute("DELETE FROM clusters WHERE coalesce(brand, '') = %s AND cluster_id <> ALL(%s)",
                    ("" if brand_key == UNBRANDED else brand_key, [c["cluster_id"] for c in clusters]))
    log("matched", listings=len(pending), clusters_changed=changed, rows=len(out))
    pending.clear()
    return out


def after_publish():
    if db is not None:
        db.commit()


def run():
    return run_worker(handle, end_batch, after_publish)
