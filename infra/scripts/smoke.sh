#!/usr/bin/env bash
# Runs one Job from the suspended pipeline/smoke CronJob (the CronJob is only a template).
. "$(dirname "$0")/lib.sh"
need kubectl

job="smoke-$(date +%s)"
log "Smoke test: job pipeline/$job"
kubectl -n pipeline create job "$job" --from=cronjob/smoke >/dev/null
rc=0
wait_job pipeline "$job" 450s || rc=$?
kubectl -n pipeline logs "job/$job"
[ "$rc" = 0 ] || die "smoke test failed (logs above)"
log "Smoke test passed"
