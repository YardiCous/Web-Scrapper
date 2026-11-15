"""Search orchestration for the HTTP baseline and the distributed Kafka deployment."""
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests
from psycopg2.extras import Json, RealDictCursor

try:
    from . import db
    from .platforms import PLATFORMS, collection_targets, resolve_url
except ImportError:
    import db
    from platforms import PLATFORMS, collection_targets, resolve_url


class SearchError(Exception):
    pass


def select_results(rows, url):
    from normaliser.core.pipeline import rows_for_url
    result = rows_for_url(rows, url)
    if result:
        return result
    platform, canonical = resolve_url(url)
    parts = urlsplit(canonical)
    if parts.query or parts.fragment or "/products/" in parts.path:
        raise SearchError("No listing was found for this product URL.")
    clusters = {r["cluster_id"] for r in rows if r["source_platform"] == PLATFORMS[platform]["name"]}
    return sorted((r for r in rows if r["cluster_id"] in clusters),
                  key=lambda r: (r["cluster_id"], r["price_sgd"]))


def _update(request_id, status, *, result=None, error=None):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE search_requests SET status = %s, result = %s, error = %s
                       WHERE request_id = %s AND status = 'pending'""",
                    (status, Json(result) if result is not None else None, error, request_id))


def _collect(target):
    key, url = target
    endpoint = os.environ.get(f"COLLECTOR_{key.upper()}_URL",
                              f"http://localhost:{PLATFORMS[key]['port']}").rstrip("/")
    response = requests.post(endpoint + "/collect", json={"url": url}, timeout=(3.05, 120))
    response.raise_for_status()
    listings = response.json()["listings"]
    if not isinstance(listings, list) or not listings or any(not isinstance(r, dict) for r in listings):
        raise SearchError("The collector returned no valid listings.")
    return listings


def run_http(url):
    """Compose baseline: real HTTP collectors -> shared matching -> real HTTP scorer."""
    from normaliser.core.pipeline import normalise_and_match
    with ThreadPoolExecutor(max_workers=3) as executor:
        records = [row for batch in executor.map(_collect, collection_targets(url)) for row in batch]
    rows = normalise_and_match(records)
    endpoint = os.environ.get("SCORER_URL", "http://localhost:8200").rstrip("/")
    for row in rows:
        response = requests.post(endpoint + "/", json=row, timeout=(3.05, 60))
        response.raise_for_status()
        score = response.json()
        if score.get("listing_id") != row["listing_id"] or score.get("saved") is None:
            raise SearchError("The scorer did not persist this listing's risk score.")
        row.update(risk_score=score["score"], risk_band=score["band"],
                   coverage=score["coverage"], reasons=score["reasons"])
    return select_results(rows, url)


def publish_requests(request_id, url, requested_at):
    from confluent_kafka import Producer
    producer = Producer({
        "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        "client.id": "cdc.gateway", "acks": "all", "enable.idempotence": True,
        "partitioner": "murmur2_random", "delivery.timeout.ms": 15000,
    })
    errors = []

    def delivered(error, _message):
        if error:
            errors.append(str(error))

    for key, target in collection_targets(url):
        name = PLATFORMS[key]["name"]
        payload = {"request_id": request_id, "source_platform": name, "product_url": target,
                   "source_listing_id": None, "reason": "user_request", "requested_at": requested_at}
        producer.produce("scrape.requests", key=name.encode(), value=json.dumps(payload).encode(),
                         on_delivery=delivered)
    if producer.flush(20) or errors:
        raise SearchError("The collection queue is unavailable. Please try again shortly.")


def start(url):
    _, url = resolve_url(url)
    request_id = str(uuid.uuid4())
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO search_requests (request_id, product_url) VALUES (%s, %s)
                       RETURNING requested_at""", (request_id, url))
        requested_at = cur.fetchone()[0].isoformat()
    try:
        if os.environ.get("PIPELINE_MODE", "http") == "kafka":
            publish_requests(request_id, url, requested_at)
        else:
            _update(request_id, "complete", result=run_http(url))
    except Exception as error:
        _update(request_id, "failed", error="Could not complete product comparison. "
                "Check the URL and try again shortly.")
        raise SearchError("Could not complete product comparison. Check the URL and try again shortly.") from error
    return get(request_id)


def _progress(job, cur):
    cur.execute("SELECT * FROM collection_runs WHERE request_id = %s", (job["request_id"],))
    runs = cur.fetchall()
    if any(run["error"] for run in runs):
        return "failed", None, "A platform could not collect its listings. Please try again shortly."
    if len(runs) < len(PLATFORMS):
        return "pending", None, None
    ids = sorted({lid for run in runs for lid in run["listing_ids"]})
    if not ids:
        return "failed", None, "No products were found."
    cur.execute("""
        SELECT m.payload, c.cluster_id, c.size AS cluster_size, c.platforms AS cluster_platforms,
               c.price_median_sgd AS cluster_price_median_sgd,
               c.price_min_sgd AS cluster_price_min_sgd, c.price_max_sgd AS cluster_price_max_sgd,
               r.score AS risk_score, r.band AS risk_band, r.coverage, r.reasons
        FROM matcher_listings m JOIN clusters c ON m.listing_id = ANY(c.member_listing_ids)
        JOIN risk_scores r ON r.listing_id = m.listing_id AND r.cluster_id = c.cluster_id
        WHERE m.listing_id = ANY(%s) AND r.source_scraped_at >= %s
          AND r.computed_at >= c.updated_at
        ORDER BY m.listing_id
    """, (ids, job["requested_at"]))
    rows = [{**row.pop("payload"), **row} for row in cur.fetchall()]
    if len(rows) != len(ids):
        return "pending", None, None
    # Decimal SQL price aggregates need JSON numbers for the API and stored snapshot.
    rows = json.loads(json.dumps(rows, default=float))
    try:
        return "complete", select_results(rows, job["product_url"]), None
    except SearchError as error:
        return "failed", None, str(error)


def get(request_id):
    with db.connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM search_requests WHERE request_id = %s", (request_id,))
        job = cur.fetchone()
        if job is None:
            return None
        if job["status"] == "pending":
            age = (datetime.now(timezone.utc) - job["requested_at"]).total_seconds()
            if age > float(os.environ.get("SEARCH_TIMEOUT_SECONDS", "300")):
                status, result, error = "failed", None, "The comparison timed out. Please try again."
            else:
                status, result, error = _progress(job, cur)
            if status != "pending":
                cur.execute("""UPDATE search_requests SET status = %s, result = %s, error = %s
                               WHERE request_id = %s AND status = 'pending'""",
                            (status, Json(result), error, request_id))
                job.update(status=status, result=result, error=error)
    return {"request_id": str(job["request_id"]), "url": job["product_url"],
            "status": job["status"], "listings": job["result"] or [], "error": job["error"]}
