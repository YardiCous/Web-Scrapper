# Sourced by the other scripts. Keep compatible with bash 3.2 (macOS default).
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a
. "$INFRA_DIR/versions.env"
set +a

PROFILE="${PROFILE:-lite}"
OVERLAY="${OVERLAY:-local-$PROFILE}"
CLUSTER="${CLUSTER:-cdc}"
GHCR_OWNER="${GHCR_OWNER:-yardicous}"
HTTP_PORT="${HTTP_PORT:-8080}"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

need() {
  local c
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || die "'$c' not found (see README.md, Prerequisites)"
  done
}

# Manifests for the selected overlay, with the registry owner filled in.
render() {
  kubectl kustomize "$INFRA_DIR/k8s/overlays/$OVERLAY" | sed "s#ghcr.io/GHCR_OWNER/#ghcr.io/$GHCR_OWNER/#g"
}

kafka_pod() {
  kubectl -n kafka get pod -l strimzi.io/cluster=cdc,strimzi.io/broker-role=true \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

kafka_exec() {
  kubectl -n kafka exec "$(kafka_pod)" -c kafka -- "$@"
}

# Waits until a Job has finished either way, then fails unless it succeeded.
wait_job() {
  local ns=$1 job=$2 timeout=${3:-300s}
  kubectl -n "$ns" wait "job/$job" --for=jsonpath='{.status.conditions[0].status}'=True --timeout="$timeout" >/dev/null
  [ "$(kubectl -n "$ns" get job "$job" -o jsonpath='{.status.succeeded}')" = "1" ]
}
