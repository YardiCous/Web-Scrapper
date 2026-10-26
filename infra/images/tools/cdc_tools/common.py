"""Shared settings and helpers. Env var names follow docs/contracts.md."""
import json
import os
import time
from pathlib import Path

SERVICE = os.environ.get("SERVICE_NAME", "cdc-tools")
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "cdc-kafka-bootstrap.kafka.svc:9092")
# /app in the image; infra/ when run from a checkout.
DATA_DIR = Path(os.environ.get("CDC_DATA_DIR") or Path(__file__).resolve().parents[3])


def log(event, **fields):
    """One JSON object per line on stdout. The experiment scripts parse these."""
    print(json.dumps({"ts": round(time.time(), 3), "service": SERVICE, "event": event, **fields}), flush=True)


def producer_config(**overrides):
    conf = {
        "bootstrap.servers": BOOTSTRAP,
        "client.id": SERVICE,
        "acks": "all",
        "enable.idempotence": True,
        # librdkafka's default partitioner hashes keys differently from Java clients;
        # murmur2_random puts a key on the same partition any Kafka client would.
        "partitioner": "murmur2_random",
        "linger.ms": 5,
        "delivery.timeout.ms": 300000,
    }
    conf.update(overrides)
    return conf


def consumer_config(group_id, **overrides):
    conf = {
        "bootstrap.servers": BOOTSTRAP,
        "client.id": SERVICE,
        "group.id": group_id,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
        "partition.assignment.strategy": "cooperative-sticky",
        "session.timeout.ms": 10000,
        "heartbeat.interval.ms": 3000,
    }
    conf.update(overrides)
    return conf


def murmur2_partition(key: bytes, partitions: int) -> int:
    """Partition the Java client's default partitioner picks for a non-null key."""
    m, r = 0x5BD1E995, 24
    length = len(key)
    h = (0x9747B28C ^ length) & 0xFFFFFFFF
    for i in range(0, length - length % 4, 4):
        k = key[i] | key[i + 1] << 8 | key[i + 2] << 16 | key[i + 3] << 24
        k = (k * m) & 0xFFFFFFFF
        k ^= k >> r
        k = (k * m) & 0xFFFFFFFF
        h = ((h * m) & 0xFFFFFFFF) ^ k
    tail = length & ~3
    extra = length % 4
    if extra >= 3:
        h ^= key[tail + 2] << 16
    if extra >= 2:
        h ^= key[tail + 1] << 8
    if extra >= 1:
        h ^= key[tail]
        h = (h * m) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * m) & 0xFFFFFFFF
    h ^= h >> 15
    return (h & 0x7FFFFFFF) % partitions
