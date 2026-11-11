"""Kafka loop shared by the adapters, same delivery rules as infra's smoke-consumer: read a batch, hand
each message to the adapter, publish what it returns, then commit (at-least-once). A message the adapter
can't handle goes to the DLQ with the error; anything else (Kafka or database down) crashes the pod so the
restart re-reads from the last commit."""
import json
import os

from confluent_kafka import Consumer, Producer

from cdc_tools.common import Shutdown, consumer_config, heartbeat, log, producer_config

INPUT_TOPIC = os.environ["KAFKA_INPUT_TOPIC"]
OUTPUT_TOPIC = os.environ["KAFKA_OUTPUT_TOPIC"]
DLQ_TOPIC = os.environ.get("KAFKA_DLQ_TOPIC", "listings.dlq")
GROUP = os.environ["KAFKA_GROUP_ID"]
BATCH = int(os.environ.get("BATCH_SIZE", "50"))


class Reject(Exception):
    """The message itself is bad (not retryable): send it to the DLQ."""


def _to_dlq(producer, msg, error):
    producer.produce(DLQ_TOPIC, key=msg.key(), value=msg.value(), headers=[
        ("dlq-error", str(error)[:500].encode()),
        ("dlq-service", GROUP.encode()),
        ("dlq-source-topic", msg.topic().encode()),
        ("dlq-source-partition", str(msg.partition()).encode()),
        ("dlq-source-offset", str(msg.offset()).encode()),
    ])


def run(handle, end_batch=None, after_publish=None):
    """handle(key, value) -> [(key, value), ...] for OUTPUT_TOPIC; raise Reject for a bad message.
    end_batch() -> [(key, value), ...], called once per batch after every handle().
    after_publish() runs once the batch's output is in Kafka, before the offsets are committed."""
    stop = Shutdown()
    producer = Producer(producer_config())
    consumer = Consumer(consumer_config(GROUP))
    consumer.subscribe([INPUT_TOPIC],
                       on_assign=lambda _c, p: log("assigned", partitions=sorted(x.partition for x in p)),
                       on_revoke=lambda _c, p: log("revoked", partitions=sorted(x.partition for x in p)))
    log("started", input=INPUT_TOPIC, output=OUTPUT_TOPIC, group=GROUP)

    while not stop.requested:
        heartbeat()
        msgs = consumer.consume(num_messages=BATCH, timeout=1.0)
        if not msgs:
            continue
        out, dlq = [], 0
        for msg in msgs:
            if msg.error():
                log("consume_error", error=str(msg.error()))
                continue
            try:
                value = json.loads(msg.value())
                out += handle(msg.key().decode() if msg.key() else None, value)
            except (Reject, ValueError, KeyError, TypeError) as e:
                log("rejected", key=msg.key().decode(errors="replace") if msg.key() else None, error=str(e)[:300])
                _to_dlq(producer, msg, e)
                dlq += 1
        if end_batch:
            out += end_batch()
        for key, value in out:
            producer.produce(OUTPUT_TOPIC, key=key.encode(), value=json.dumps(value, default=str).encode())
            producer.poll(0)
        if producer.flush(60):
            raise RuntimeError("could not deliver every output message")
        if after_publish:
            after_publish()
        consumer.commit(asynchronous=False)
        log("batch", messages=len(msgs), published=len(out), dlq=dlq)

    consumer.close()
    log("stopped")
    return 0
