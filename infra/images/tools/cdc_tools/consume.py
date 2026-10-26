"""smoke-consumer: listings.raw -> idempotent upsert into Postgres `listings`.

Stands in for the first pipeline consumer, and is what KEDA and the experiments scale and kill.
Offsets are committed only after the database transaction commits (at-least-once), and the upsert
makes redeliveries harmless. A DB error crashes the pod on purpose: the restart re-reads from the
last committed offset.
"""
import json
import os
import time

from confluent_kafka import Consumer, Producer

from .common import Shutdown, connect_db, consumer_config, heartbeat, log, producer_config

INPUT_TOPIC = os.environ.get("KAFKA_INPUT_TOPIC", "listings.raw")
DLQ_TOPIC = os.environ.get("KAFKA_DLQ_TOPIC", "listings.dlq")
GROUP = os.environ.get("KAFKA_GROUP_ID", "cdc.smoke-consumer")
BATCH = int(os.environ.get("BATCH_SIZE", "100"))
# Simulated per-message work, so one replica can fall behind and KEDA has something to scale.
WORK_MS = float(os.environ.get("WORK_MS_PER_MESSAGE", "0"))

UPSERT = """
INSERT INTO listings AS l (listing_id, source_platform, source_listing_id, title, price, currency,
                           seller_id, product_url, payload, last_seen_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (listing_id) DO UPDATE SET
  title = EXCLUDED.title, price = EXCLUDED.price, currency = EXCLUDED.currency,
  seller_id = EXCLUDED.seller_id, product_url = EXCLUDED.product_url, payload = EXCLUDED.payload,
  last_seen_at = EXCLUDED.last_seen_at, updated_at = now()
WHERE l.last_seen_at <= EXCLUDED.last_seen_at
RETURNING (xmax = 0) AS inserted
"""

REQUIRED = ("source_platform", "source_listing_id", "product_url", "scraped_at")


def parse(msg):
    rec = json.loads(msg.value())
    missing = [f for f in REQUIRED if not rec.get(f)]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    listing_id = f"{rec['source_platform']}:{rec['source_listing_id']}"
    return listing_id, (listing_id, rec["source_platform"], str(rec["source_listing_id"]), rec.get("title"),
                        rec.get("price"), rec.get("currency"), rec.get("seller_id"), rec["product_url"],
                        json.dumps(rec), rec["scraped_at"])


def to_dlq(producer, msg, error):
    producer.produce(DLQ_TOPIC, key=msg.key(), value=msg.value(), headers=[
        ("dlq-error", str(error)[:500].encode()),
        ("dlq-service", GROUP.encode()),
        ("dlq-source-topic", msg.topic().encode()),
        ("dlq-source-partition", str(msg.partition()).encode()),
        ("dlq-source-offset", str(msg.offset()).encode()),
    ])


def run():
    stop = Shutdown()
    db = connect_db()
    producer = Producer(producer_config())
    consumer = Consumer(consumer_config(GROUP))

    def on_assign(_c, parts):
        log("assigned", partitions=sorted(p.partition for p in parts))

    def on_revoke(_c, parts):
        log("revoked", partitions=sorted(p.partition for p in parts))

    consumer.subscribe([INPUT_TOPIC], on_assign=on_assign, on_revoke=on_revoke)
    log("started", topic=INPUT_TOPIC, group=GROUP, batch=BATCH, work_ms=WORK_MS)

    while not stop.requested:
        heartbeat()
        msgs = consumer.consume(num_messages=BATCH, timeout=1.0)
        if not msgs:
            continue

        rows, dlq = {}, 0
        for msg in msgs:
            if msg.error():
                log("consume_error", error=str(msg.error()))
                continue
            try:
                listing_id, row = parse(msg)
            except (ValueError, KeyError, TypeError) as e:
                to_dlq(producer, msg, e)
                dlq += 1
                continue
            # The same key twice in one batch: keep the newest, as one statement can't upsert a row twice.
            if listing_id not in rows or rows[listing_id][-1] <= row[-1]:
                rows[listing_id] = row
            if WORK_MS:
                time.sleep(WORK_MS / 1000)

        inserted = updated = 0
        if rows:
            with db.transaction(), db.cursor() as cur:
                cur.executemany(UPSERT, list(rows.values()), returning=True)
                while True:
                    res = cur.fetchone()
                    if res is not None:
                        inserted += res[0]
                        updated += not res[0]
                    if not cur.nextset():
                        break
        if dlq:
            producer.flush(30)
        consumer.commit(asynchronous=False)
        log("batch", messages=len(msgs), inserted=inserted, updated=updated,
            stale=len(rows) - inserted - updated, dlq=dlq)

    consumer.close()  # commits nothing new; leaves the group so the rebalance starts immediately
    db.close()
    log("stopped")
    return 0
