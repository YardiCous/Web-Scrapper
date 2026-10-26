"""TTL refresh: publish a scrape request for every listing not seen within LISTING_TTL_MINUTES."""
import json
import os
import uuid
from datetime import datetime, timezone

import psycopg
from confluent_kafka import Producer

from .common import log, producer_config

TTL_MINUTES = int(os.environ.get("LISTING_TTL_MINUTES", "60"))
LIMIT = int(os.environ.get("REFRESH_LIMIT", "1000"))
TOPIC = os.environ.get("KAFKA_OUTPUT_TOPIC", "scrape.requests")

STALE = """
SELECT source_platform, source_listing_id, product_url
FROM listings
WHERE last_seen_at < now() - make_interval(mins => %s)
ORDER BY last_seen_at
LIMIT %s
"""


def run():
    with psycopg.connect() as db:
        stale = db.execute(STALE, (TTL_MINUTES, LIMIT)).fetchall()

    producer = Producer(producer_config())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    errors = []
    for platform, listing_id, url in stale:
        request = {"request_id": str(uuid.uuid4()), "source_platform": platform, "product_url": url,
                   "source_listing_id": listing_id, "reason": "ttl_refresh", "requested_at": now}
        producer.produce(TOPIC, key=platform.encode(), value=json.dumps(request).encode(),
                         on_delivery=lambda err, _m: err and errors.append(str(err)))
        producer.poll(0)
    unflushed = producer.flush(60)

    ok = not errors and unflushed == 0
    log("ttl_refresh", ok=ok, ttl_minutes=TTL_MINUTES, stale=len(stale), published=len(stale) - len(errors) - unflushed)
    return 0 if ok else 1
