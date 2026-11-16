"""`make load N=... RATE=...`: run the load generator once as a Job and print its result. Stdlib only."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import json_logs, new_run_id, start_job, wait_job  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=1000)
    p.add_argument("--rate", type=float, default=100)
    a = p.parse_args()

    run_id = new_run_id()
    job = start_job("loadgen", ["loadgen", "--count", str(a.count), "--rate", str(a.rate), "--run-id", run_id])
    print(f"job pipeline/{job}: {a.count} listings at {a.rate}/s (run {run_id})")
    ok = wait_job(job, timeout_s=a.count / a.rate + 600)
    done = [r for r in json_logs(f"job/{job}") if r.get("event") == "loadgen_done"]
    print(done[-1] if done else "no result line in the job log")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
