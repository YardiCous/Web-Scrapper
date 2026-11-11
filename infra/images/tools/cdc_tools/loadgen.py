"""Load generator: publish N synthetic listings to listings.raw at a fixed rate.

Listings are copies of the sample records with ids "LG-<run_id>-<seq>", so every message has a
distinct key and the rows of one run can be counted in Postgres afterwards.
"""
import json
import random
import time
from datetime import datetime, timezone

from confluent_kafka import Producer

from .common import DATA_DIR, log, producer_config

TOPIC = "listings.raw"


def run(count, rate, run_id):
    samples = json.loads((DATA_DIR / "samples/raw_listings.json").read_text(encoding="utf-8"))
    producer = Producer(producer_config())
    acked = failed = 0
    errors = []

    def on_delivery(err, _msg):
        nonlocal acked, failed
        if err:
            failed += 1
            if len(errors) < 5:
                errors.append(str(err))
        else:
            acked += 1

    log("loadgen_start", run_id=run_id, count=count, rate=rate, topic=TOPIC)
    start = time.monotonic()
    next_report = start + 1
    for seq in range(count):
        # Pace against the schedule rather than sleeping a fixed gap, so slow produce() calls don't add up.
        due = start + seq / rate
        while (now := time.monotonic()) < due:
            producer.poll(min(due - now, 0.05))
        rec = dict(random.choice(samples))
        rec["source_listing_id"] = f"LG-{run_id}-{seq:07d}"
        rec["price"] = round(rec["price"] * random.uniform(0.8, 1.2), 2)
        rec["scraped_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        rec["synthetic"] = True   # the normaliser skips these, so load tests stay on the smoke-consumer
        key = f"{rec['source_platform']}:{rec['source_listing_id']}"
        while True:
            try:
                producer.produce(TOPIC, key=key.encode(), value=json.dumps(rec).encode(), on_delivery=on_delivery)
                break
            except BufferError:  # local queue full, e.g. while a broker is down: wait for deliveries
                producer.poll(0.5)
        producer.poll(0)
        if time.monotonic() >= next_report:
            log("progress", run_id=run_id, sent=seq + 1, acked=acked, failed=failed)
            next_report += 1

    while producer.flush(1) > 0:
        log("progress", run_id=run_id, sent=count, acked=acked, failed=failed, flushing=True)
    duration = time.monotonic() - start
    log("loadgen_done", run_id=run_id, sent=count, acked=acked, failed=failed, errors=errors,
        duration_s=round(duration, 3), achieved_rate=round(count / duration, 1))
    return 0 if failed == 0 else 1
