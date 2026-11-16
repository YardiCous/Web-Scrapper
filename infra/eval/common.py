"""Helpers shared by the experiment scripts. They run on the laptop and need kubectl plus Kafka at
KAFKA_BOOTSTRAP (default localhost:32100, the k3d external listener)."""
import csv
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

RESULTS = Path(os.environ.get("RESULTS_DIR", Path(__file__).resolve().parent / "results"))
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:32100")


def kubectl(*args, input=None, check=True):
    res = subprocess.run(["kubectl", *args], input=input, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)}: {res.stderr.strip()}")
    return res.stdout


def kubectl_json(*args):
    return json.loads(kubectl(*args, "-o", "json"))


def new_run_id():
    return uuid.uuid4().hex[:8]


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def profile():
    """'lite' or 'default', from the number of Kafka broker pods."""
    pods = kubectl_json("-n", "kafka", "get", "pods", "-l", "strimzi.io/cluster=cdc,strimzi.io/broker-role=true")
    return "lite" if len(pods["items"]) <= 1 else "default"


def start_job(cronjob, args, namespace="pipeline"):
    """Create a Job from a suspended CronJob template with different container args; returns its name."""
    tmpl = kubectl_json("-n", namespace, "get", "cronjob", cronjob)
    name = f"{cronjob}-{int(time.time())}"
    spec = tmpl["spec"]["jobTemplate"]["spec"]
    spec["template"]["spec"]["containers"][0]["args"] = args
    job = {"apiVersion": "batch/v1", "kind": "Job",
           "metadata": {"name": name, "namespace": namespace, "labels": {"cdc/experiment": "true"}},
           "spec": spec}
    kubectl("apply", "-f", "-", input=json.dumps(job))
    return name


def wait_job(name, timeout_s, namespace="pipeline"):
    """Polls until the Job finishes; returns True if it succeeded."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = kubectl_json("-n", namespace, "get", "job", name).get("status", {})
        if status.get("succeeded"):
            return True
        if status.get("failed"):
            return False
        time.sleep(1)
    raise TimeoutError(f"job {name} still running after {timeout_s}s")


def json_logs(target, namespace="pipeline", since_ts=None):
    """JSON log lines (as dicts) of a pod or job/<name>, optionally only those with ts >= since_ts."""
    out = []
    for line in kubectl("-n", namespace, "logs", target, check=False).splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if since_ts is None or rec.get("ts", 0) >= since_ts:
            out.append(rec)
    return out


def psql(sql):
    """Runs a query inside the Postgres pod (local socket, no password needed); returns the first value."""
    return kubectl("-n", "data", "exec", "postgres-0", "--", "psql", "-U", "cdc", "-d", "cdc", "-tAc", sql).strip()


def rows_for_run(run_id):
    return int(psql(f"SELECT count(*) FROM listings WHERE listing_id LIKE '%:LG-{run_id}-%'"))


class Lag:
    """Consumer-group lag and partition health, read from Kafka without joining the group."""

    def __init__(self, group, topic):
        from confluent_kafka import Consumer
        self.topic = topic
        self.c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": group, "enable.auto.commit": False})

    def _partitions(self, timeout=5):
        from confluent_kafka import TopicPartition
        md = self.c.list_topics(self.topic, timeout=timeout).topics[self.topic]
        return md, [TopicPartition(self.topic, p) for p in sorted(md.partitions)]

    def total(self, timeout=5):
        _, tps = self._partitions(timeout)
        lag = 0
        for tp in self.c.committed(tps, timeout=timeout):
            low, high = self.c.get_watermark_offsets(tp, timeout=timeout)
            lag += high - (tp.offset if tp.offset >= 0 else low)
        return lag

    def under_replicated(self, timeout=5):
        md, _ = self._partitions(timeout)
        return sum(1 for p in md.partitions.values() if len(p.isrs) < len(p.replicas))

    def close(self):
        self.c.close()


def group_members(group):
    """{member_id: (host, {partitions})} of the group's members, as the group coordinator sees them."""
    from confluent_kafka.admin import AdminClient
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    desc = admin.describe_consumer_groups([group], request_timeout=5)[group].result(timeout=10)
    return {m.member_id: (m.host.lstrip("/"), {tp.partition for tp in m.assignment.topic_partitions})
            for m in desc.members}


def pods(namespace, selector):
    """Running, not-terminating pods matching a label selector: [(name, ip)]."""
    items = kubectl_json("-n", namespace, "get", "pods", "-l", selector)["items"]
    return [(p["metadata"]["name"], p["status"].get("podIP")) for p in items
            if p["status"].get("phase") == "Running" and not p["metadata"].get("deletionTimestamp")]


def pause_keda(scaledobject, replicas, namespace="pipeline"):
    """Pin a ScaledObject's target at `replicas` (None = resume autoscaling)."""
    if replicas is None:
        kubectl("-n", namespace, "annotate", "scaledobject", scaledobject, "autoscaling.keda.sh/paused-replicas-")
    else:
        kubectl("-n", namespace, "annotate", "--overwrite", "scaledobject", scaledobject,
                f"autoscaling.keda.sh/paused-replicas={replicas}")


def wait_until(predicate, timeout_s, interval_s=0.5, what="condition"):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if predicate():
                return time.time()
        except Exception:
            pass
        time.sleep(interval_s)
    raise TimeoutError(f"{what} not reached within {timeout_s}s")


def wait_lag_zero(lag, timeout_s, settle_s=3):
    """Waits until lag has been 0 for settle_s seconds; returns the time it first reached 0."""
    deadline = time.time() + timeout_s
    zero_since = None
    while time.time() < deadline:
        try:
            current = lag.total()
        except Exception:
            current = None
        if current == 0:
            zero_since = zero_since or time.time()
            if time.time() - zero_since >= settle_s:
                return zero_since
        else:
            zero_since = None
        time.sleep(0.5)
    raise TimeoutError(f"lag not drained within {timeout_s}s")


def append_csv(name, row):
    """Appends one row (a dict) to results/<name>.csv, writing the header for a new file."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{name}.csv"
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"{path}: {row}")
