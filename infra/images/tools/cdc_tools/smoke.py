"""Smoke test: validate the sample records against the topic schemas, publish them, read them back,
check every message landed on the partition a Java client would pick for its key, then check the
pipeline picked them up: smoke-consumer wrote the raw listings to Postgres and the KafkaSource
delivered the normalized ones to the scorer."""
import json
import time
import uuid
from collections import Counter
from datetime import datetime, timezone

import psycopg
from confluent_kafka import Consumer, KafkaException, Producer, TopicPartition
from jsonschema import Draft202012Validator

from .common import DATA_DIR, consumer_config, log, murmur2_partition, producer_config

GROUP = "cdc.smoke"
READ_TIMEOUT_S = 60
# Long enough for the scorer to scale up from zero.
PIPELINE_TIMEOUT_S = 180


def load(relpath):
    return json.loads((DATA_DIR / relpath).read_text(encoding="utf-8"))


def build_messages():
    raw = load("samples/raw_listings.json")
    normalized = load("samples/normalised_output.json")
    msgs = [("listings.raw", f"{r['source_platform']}:{r['source_listing_id']}", r) for r in raw]
    msgs += [("listings.normalized", n["cluster_id"], n) for n in normalized]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    first_url = {}
    for r in raw:
        first_url.setdefault(r["source_platform"], r["product_url"])
    for platform, url in sorted(first_url.items()):
        msgs.append(("scrape.requests", platform, {
            "request_id": str(uuid.uuid4()),
            "source_platform": platform,
            "product_url": url,
            "source_listing_id": None,
            "reason": "user_request",
            "requested_at": now,
        }))
    return msgs


def validate(msgs):
    validators = {}
    errors = 0
    for topic, key, value in msgs:
        if topic not in validators:
            validators[topic] = Draft202012Validator(load(f"schemas/{topic}.schema.json"))
        for err in validators[topic].iter_errors(value):
            errors += 1
            log("schema_error", topic=topic, key=key, path="/".join(map(str, err.absolute_path)), error=err.message)
    return errors


def produce(msgs, run_id):
    producer = Producer(producer_config())
    delivered, failed = {}, []

    def on_delivery(err, msg):
        if err:
            failed.append(str(err))
        else:
            delivered[(msg.topic(), msg.partition(), msg.offset())] = (msg.key(), msg.value())

    for topic, key, value in msgs:
        producer.produce(topic, key=key.encode(), value=json.dumps(value).encode(),
                         headers=[("cdc-run-id", run_id.encode())], on_delivery=on_delivery)
        producer.poll(0)
    unflushed = producer.flush(30)
    partitions = {t: len(m.partitions) for t, m in producer.list_topics(timeout=10).topics.items()}
    return delivered, failed, unflushed, partitions


def read_back(delivered):
    consumer = Consumer(consumer_config(GROUP))
    start = {}
    for topic, partition, offset in delivered:
        start[(topic, partition)] = min(offset, start.get((topic, partition), offset))
    consumer.assign([TopicPartition(t, p, o) for (t, p), o in start.items()])

    pending = set(delivered)
    mismatched = 0
    deadline = time.monotonic() + READ_TIMEOUT_S
    while pending and time.monotonic() < deadline:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            raise KafkaException(msg.error())
        coord = (msg.topic(), msg.partition(), msg.offset())
        if coord in pending:
            pending.discard(coord)
            if (msg.key(), msg.value()) != delivered[coord]:
                mismatched += 1

    # Commit what was read so the group (and its lag) shows up in `make status`.
    ends = {}
    for topic, partition, offset in set(delivered) - pending:
        ends[(topic, partition)] = max(offset + 1, ends.get((topic, partition), 0))
    if ends:
        consumer.commit(offsets=[TopicPartition(t, p, o) for (t, p), o in ends.items()], asynchronous=False)
    consumer.close()
    return len(pending), mismatched


def check_partitions(delivered, partitions):
    wrong = 0
    for (topic, partition, offset), (key, _) in delivered.items():
        expected = murmur2_partition(key, partitions[topic])
        if partition != expected:
            wrong += 1
            log("partition_mismatch", topic=topic, key=key.decode(), offset=offset, got=partition, expected=expected)
    return wrong


def group_caught_up(group, delivered, topic, deadline):
    """True once `group` has committed past every message we produced to `topic`."""
    needed = {}
    for t, partition, offset in delivered:
        if t == topic:
            needed[partition] = max(offset + 1, needed.get(partition, 0))
    consumer = Consumer(consumer_config(group))
    try:
        while time.monotonic() < deadline:
            committed = consumer.committed([TopicPartition(topic, p) for p in needed], timeout=10)
            if all(tp.offset >= needed[tp.partition] for tp in committed):
                return True
            time.sleep(2)
        return False
    finally:
        consumer.close()


def rows_in_db(listing_ids, deadline):
    with psycopg.connect() as db:
        while True:
            n = db.execute("SELECT count(*) FROM listings WHERE listing_id = ANY(%s)", (listing_ids,)).fetchone()[0]
            if n == len(listing_ids) or time.monotonic() >= deadline:
                return n
            time.sleep(2)


def run():
    run_id = uuid.uuid4().hex[:8]
    msgs = build_messages()
    log("smoke_start", run_id=run_id, messages=len(msgs), per_topic=dict(Counter(t for t, _, _ in msgs)))

    schema_errors = validate(msgs)
    if schema_errors:
        log("smoke_result", ok=False, run_id=run_id, schema_errors=schema_errors)
        return 1

    delivered, failed, unflushed, partitions = produce(msgs, run_id)
    missing, mismatched = read_back(delivered)
    wrong_partition = check_partitions(delivered, partitions)

    deadline = time.monotonic() + PIPELINE_TIMEOUT_S
    raw_ids = [k for t, k, _ in msgs if t == "listings.raw"]
    db_rows = rows_in_db(raw_ids, deadline)
    consumer_done = group_caught_up("cdc.smoke-consumer", delivered, "listings.raw", deadline)
    scorer_done = group_caught_up("cdc.scorer", delivered, "listings.normalized", deadline)

    ok = not failed and unflushed == 0 and len(delivered) == len(msgs) \
        and missing == 0 and mismatched == 0 and wrong_partition == 0 \
        and db_rows == len(raw_ids) and consumer_done and scorer_done
    log("smoke_result", ok=ok, run_id=run_id, validated=len(msgs), produced=len(delivered),
        delivery_errors=failed[:5], unflushed=unflushed, not_read_back=missing,
        content_mismatches=mismatched, wrong_partition=wrong_partition,
        listings_rows=f"{db_rows}/{len(raw_ids)}", smoke_consumer_caught_up=consumer_done,
        scorer_feed_caught_up=scorer_done)
    return 0 if ok else 1
