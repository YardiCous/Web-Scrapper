"""Experiment: burst of listings into an idle pipeline; KEDA scales smoke-consumer on consumer lag.

Samples replicas and lag every second from the start of the burst until the lag has drained
(results/keda_burst_timeseries.csv) and summarises scale-out time, peak replicas and drain time
(results/keda_burst.csv). smoke-consumer simulates WORK_MS_PER_MESSAGE of work per message, so one
replica cannot keep up with the burst.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (Lag, append_csv, json_logs, kubectl_json, new_run_id, now_iso, pause_keda, profile,  # noqa: E402
                    start_job, wait_job, wait_lag_zero, wait_until)

NS, APP, GROUP, TOPIC = "pipeline", "smoke-consumer", "cdc.smoke-consumer", "listings.raw"


def replicas():
    d = kubectl_json("-n", NS, "get", "deployment", APP)
    return d["spec"].get("replicas", 0), d["status"].get("readyReplicas", 0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--count", type=int, default=20000)
    p.add_argument("--rate", type=float, default=1000)
    p.add_argument("--trials", type=int, default=1)
    a = p.parse_args()
    lag = Lag(GROUP, TOPIC)
    pause_keda(APP, None)
    try:
        for trial in range(1, a.trials + 1):
            run_trial(a, lag, trial)
    finally:
        lag.close()


def run_trial(a, lag, trial):
    min_replicas = kubectl_json("-n", NS, "get", "scaledobject", APP)["spec"].get("minReplicaCount", 0)
    wait_lag_zero(lag, 600)
    wait_until(lambda: replicas() == (min_replicas, min_replicas), 900, interval_s=2, what="scaled back in")

    run_id = new_run_id()
    t0 = time.time()
    job = start_job("loadgen", ["loadgen", "--count", str(a.count), "--rate", str(a.rate), "--run-id", run_id])
    samples, done_at = [], None
    while True:
        t = time.time() - t0
        desired, ready = replicas()
        try:
            current = lag.total()
        except Exception:
            current = None
        samples.append({"run_id": run_id, "t_s": round(t, 1), "desired": desired, "ready": ready, "lag": current})
        if done_at is None and kubectl_json("-n", NS, "get", "job", job).get("status", {}).get("succeeded"):
            done_at = t
        if done_at is not None and current == 0:
            break
        if t > a.count / a.rate + 900:
            raise TimeoutError("lag did not drain")
        time.sleep(max(0.0, 1 - (time.time() - t0 - t)))
    wait_job(job, 60)

    start = next(r["ts"] for r in json_logs(f"job/{job}") if r.get("event") == "loadgen_start") - t0
    for s in samples:
        s["t_s"] = round(s["t_s"] - start, 1)   # t = 0 at the first produced message
        append_csv("keda_burst_timeseries", s)
    out = [s for s in samples if s["desired"] > min_replicas]
    peak = max(s["desired"] for s in samples)
    append_csv("keda_burst", {
        "time": now_iso(), "profile": profile(), "trial": trial, "run_id": run_id, "count": a.count, "rate": a.rate,
        "scale_out_s": out[0]["t_s"] if out else None,
        "first_extra_ready_s": next((s["t_s"] for s in samples if s["ready"] > min_replicas), None),
        "peak_replicas": peak,
        "time_to_peak_s": next(s["t_s"] for s in samples if s["desired"] == peak),
        "peak_lag": max(s["lag"] or 0 for s in samples),
        "load_done_s": round(done_at - start, 1),
        "drained_s": samples[-1]["t_s"],
    })


if __name__ == "__main__":
    main()
