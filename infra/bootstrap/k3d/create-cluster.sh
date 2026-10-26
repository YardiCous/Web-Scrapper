#!/usr/bin/env bash
# Creates the local k3d cluster if it does not exist yet.
. "$(dirname "$0")/../../scripts/lib.sh"
need k3d kubectl

if k3d cluster get "$CLUSTER" >/dev/null 2>&1; then
  log "k3d cluster '$CLUSTER' exists"
  k3d cluster start "$CLUSTER" >/dev/null
else
  log "Creating k3d cluster '$CLUSTER' ($K3S_IMAGE, 1 server + 2 agents)"
  # Host ports: HTTP_PORT -> Traefik ingress, 8081 -> Kourier NodePort (Knative),
  # 32100-32103 -> Kafka external listener (bootstrap + one per broker).
  k3d cluster create "$CLUSTER" \
    --image "$K3S_IMAGE" \
    --servers 1 --agents 2 \
    --port "$HTTP_PORT:80@loadbalancer" \
    --port "8081:31080@server:0" \
    --port "32100:32100@server:0" \
    --port "32101:32101@server:0" \
    --port "32102:32102@server:0" \
    --port "32103:32103@server:0" \
    --wait
fi

kubectl config use-context "k3d-$CLUSTER" >/dev/null
kubectl wait node --all --for=condition=Ready --timeout=300s
