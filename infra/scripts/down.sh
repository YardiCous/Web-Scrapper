#!/usr/bin/env bash
. "$(dirname "$0")/lib.sh"
need k3d

if k3d cluster get "$CLUSTER" >/dev/null 2>&1; then
  log "Deleting k3d cluster '$CLUSTER' (all data, including volumes)"
  k3d cluster delete "$CLUSTER"
else
  log "No k3d cluster '$CLUSTER'"
fi
