"""Experiment: force-kill a Kafka broker pod while the load generator is producing.

Lost messages = acknowledged by Kafka (loadgen) minus rows that reached Postgres through
smoke-consumer; expected 0 (acks=all, idempotent producer, persistent storage, commit-after-write).
Recovery is reported three ways: broker pod Ready again, all partitions fully in sync again, and the
longest gap in the producer's acknowledgements. On the lite profile (1 broker, RF 1) the kill is a
full outage that the producer rides out with retries; the default profile shows real failover.
Writes results/broker_kill.csv.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (Lag, append_csv, json_logs, kubectl, kubectl_json, new_run_id, now_iso, pause_keda,  # noqa: E402
                    profile, rows_for_run, start_job, wait_job, wait_lag_zero, wait_until)

GROUP, TOPIC = "cdc.smoke-consumer", "listings.raw"


def broker_ready(name):
    pod = kubectl_json("-n", "kafka", "get", "pod", name)
    if pod["metadata"].get("deletionTimestamp"):
        return False
    return any(c["type"] == "Ready" and c["status"] == "True" for c in pod["status"].get("conditions", []))


def longest_ack_gap(progress):
    """Longest stretch (s) during which loadgen's acked count did not grow, from its 1 s progress lines."""
    gap, last_ts, last_acked = 0.0, None, -1
    for r in progress:
        if r["acked"] > last_acked:
            if last_ts is not None:
                gap = max(gap, r["ts"] - last_ts)
            last_ts, last_acked = r["ts"], r["acked"]
    return round(gap, 2)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--count", type=int, default=15000)
    p.add_argument("--rate", type=float, default=300)
    p.add_argument("--kill-after", type=float, default=10, help="seconds after the load starts")
    p.add_argument("--broker", default="cdc-kafka-0")
    p.add_argument("--trials", type=int, default=3)
    a = p.parse_args()
    lag = Lag(GROUP, TOPIC)
    pause_keda("smoke-consumer", 2)
    try:
        for trial in range(1, a.trials + 1):
            run_trial(a, lag, trial)
    finally:
        pause_keda("smoke-consumer", None)
        lag.close()


def run_trial(a, lag, trial):
    wait_until(lambda: broker_ready(a.broker) and lag.under_replicated() == 0, 600, what="healthy cluster")
    wait_lag_zero(lag, 300)

    run_id = new_run_id()
    job = start_job("loadgen", ["loadgen", "--count", str(a.count), "--rate", str(a.rate), "--run-id", run_id])
    wait_until(lambda: lag.total() > 0, 120, what="load arriving")
    time.sleep(a.kill_after)

    t_kill = time.time()
    kubectl("-n", "kafka", "delete", "pod", a.broker, "--grace-period=0", "--force", "--wait=false")
    wait_until(lambda: not broker_ready(a.broker), 60, interval_s=0.2, what="broker gone")
    t_ready = wait_until(lambda: broker_ready(a.broker), 600, what="broker Ready")
    t_isr = wait_until(lambda: lag.under_replicated() == 0, 600, what="partitions in sync")

    loadgen_ok = wait_job(job, a.count / a.rate + 900)
    logs = json_logs(f"job/{job}")
    done = next(r for r in reversed(logs) if r.get("event") == "loadgen_done")
    wait_lag_zero(lag, 900)
    rows = rows_for_run(run_id)

    append_csv("broker_kill", {
        "time": now_iso(), "profile": profile(), "trial": trial, "run_id": run_id,
        "count": a.count, "rate": a.rate, "killed": a.broker, "loadgen_ok": loadgen_ok,
        "acked": done["acked"], "failed": done["failed"], "rows": rows, "lost": done["acked"] - rows,
        "broker_ready_s": round(t_ready - t_kill, 2), "in_sync_s": round(t_isr - t_kill, 2),
        "producer_stall_s": longest_ack_gap([r for r in logs if r.get("event") == "progress"]),
    })


if __name__ == "__main__":
    main()
