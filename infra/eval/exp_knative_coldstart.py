"""Experiment: Knative scale-to-zero and cold start of the scorer.

Each iteration waits until the scorer has no pods (recording how long that took after the last
request), then sends one CloudEvent (cold: a pod must start) followed by a few more (warm), timing
each round trip through Kourier on localhost:8081. Writes results/knative_coldstart.csv.
"""
import argparse
import json
import statistics
import sys
import time
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import append_csv, kubectl_json, now_iso, profile, wait_until  # noqa: E402

URL = "http://localhost:8081/"
HOST = "scorer.scoring.knative.localhost"


def scorer_pods():
    items = kubectl_json("-n", "scoring", "get", "pods", "-l", "serving.knative.dev/service=scorer")["items"]
    return sum(1 for p in items if not p["metadata"].get("deletionTimestamp"))


def post_event():
    body = json.dumps({"listing_id": "coldstart-probe"}).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Host": HOST, "Content-Type": "application/json", "ce-specversion": "1.0",
        "ce-id": str(uuid.uuid4()), "ce-type": "cdc.eval.probe", "ce-source": "eval/exp_knative_coldstart"})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        resp.read()
        status = resp.status
    return (time.perf_counter() - t) * 1000, status


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--iterations", type=int, default=5)
    p.add_argument("--warm-requests", type=int, default=5)
    a = p.parse_args()

    last_request = None
    for i in range(1, a.iterations + 1):
        t_zero = wait_until(lambda: scorer_pods() == 0, 900, what="scale to zero")
        cold_ms, status = post_event()
        warm = [post_event()[0] for _ in range(a.warm_requests)]
        append_csv("knative_coldstart", {
            "time": now_iso(), "profile": profile(), "iteration": i, "status": status,
            "cold_ms": round(cold_ms, 1), "warm_median_ms": round(statistics.median(warm), 1),
            "scale_to_zero_s": round(t_zero - last_request, 1) if last_request else None,
        })
        last_request = time.time()


if __name__ == "__main__":
    main()
