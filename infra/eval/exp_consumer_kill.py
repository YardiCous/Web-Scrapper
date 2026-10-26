"""Experiment: take one smoke-consumer replica away while it is processing a load.

Two modes per trial:
  crash   the consumer process dies after writing a batch to Postgres but before committing its
          offsets (fault-injection file /tmp/crash-before-commit). Its partitions move only after
          the session timeout, and that batch is redelivered to another replica.
  delete  `kubectl delete pod`: SIGTERM, the consumer commits and leaves the group (graceful).

For each run: time until the lost member's partitions are owned by others (group coordinator's
view), time until the group is back to full size, rows = messages (lost = 0), duplicate rows (0),
and how many redelivered messages the idempotent upsert absorbed. Writes results/consumer_kill.csv.
"""
import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (Lag, append_csv, group_members, json_logs, kubectl, new_run_id, now_iso, pause_keda,  # noqa: E402
                    pods, profile, psql, rows_for_run, start_job, wait_job, wait_lag_zero, wait_until)

NS, APP, GROUP, TOPIC = "pipeline", "smoke-consumer", "cdc.smoke-consumer", "listings.raw"
SELECTOR = f"app.kubernetes.io/name={APP}"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--count", type=int, default=6000)
    p.add_argument("--rate", type=float, default=300)
    p.add_argument("--replicas", type=int, default=3)
    p.add_argument("--kill-after", type=float, default=8, help="seconds after the load starts")
    p.add_argument("--modes", default="crash,delete")
    p.add_argument("--trials", type=int, default=3, help="per mode")
    a = p.parse_args()
    lag = Lag(GROUP, TOPIC)
    try:
        for trial in range(1, a.trials + 1):
            for mode in a.modes.split(","):
                run_trial(a, lag, trial, mode)
    finally:
        pause_keda(APP, None)
        lag.close()


def run_trial(a, lag, trial, mode):
    pause_keda(APP, a.replicas)
    wait_until(lambda: len(pods(NS, SELECTOR)) == a.replicas and len(group_members(GROUP)) == a.replicas,
               300, what=f"{a.replicas} consumers in the group")
    wait_lag_zero(lag, 300)

    run_id = new_run_id()
    t_start = time.time()
    job = start_job("loadgen", ["loadgen", "--count", str(a.count), "--rate", str(a.rate), "--run-id", run_id])
    wait_until(lambda: lag.total() > 0, 120, what="load arriving")
    time.sleep(a.kill_after)

    victim, victim_ip = random.choice(pods(NS, SELECTOR))
    victim_member = next(m for m, (host, _) in group_members(GROUP).items() if host == victim_ip)
    t_kill = time.time()
    if mode == "crash":
        kubectl("-n", NS, "exec", victim, "--", "touch", "/tmp/crash-before-commit")
    else:
        kubectl("-n", NS, "delete", "pod", victim, "--wait=false")

    def reassigned():
        members = group_members(GROUP)
        owned = set().union(*(parts for _, parts in members.values())) if members else set()
        return victim_member not in members and len(owned) == 6
    t_reassigned = wait_until(reassigned, 120, interval_s=0.25, what="partitions reassigned")
    t_full = wait_until(lambda: len(group_members(GROUP)) == a.replicas, 300, what="group back to full size")

    loadgen_ok = wait_job(job, a.count / a.rate + 600)
    wait_lag_zero(lag, 600)
    rows = rows_for_run(run_id)
    dup_rows = int(psql(f"SELECT count(*) - count(DISTINCT listing_id) FROM listings "
                        f"WHERE listing_id LIKE '%:LG-{run_id}-%'"))
    # Only this run's keys are in flight, so an upsert that updated a row is a redelivery.
    redelivered = sum(r.get("updated", 0) for name, _ in pods(NS, SELECTOR)
                      for r in json_logs(name, NS, since_ts=t_start) if r.get("event") == "batch")

    append_csv("consumer_kill", {
        "time": now_iso(), "profile": profile(), "mode": mode, "trial": trial, "run_id": run_id,
        "count": a.count, "rate": a.rate, "replicas": a.replicas, "loadgen_ok": loadgen_ok,
        "rebalance_s": round(t_reassigned - t_kill, 2), "group_full_s": round(t_full - t_kill, 2),
        "rows": rows, "lost": a.count - rows, "duplicate_rows": dup_rows, "redelivered_absorbed": redelivered,
    })


if __name__ == "__main__":
    main()
