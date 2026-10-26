#!/usr/bin/env bash
# Applies our manifests and waits until they are healthy. Assumes operators and CRDs are installed (make up).
. "$(dirname "$0")/lib.sh"
need kubectl

log "Applying manifests (overlay: $OVERLAY)"
render | kubectl apply -f -

log "Waiting for Kafka, topics and Kafka UI"
kubectl -n kafka wait kafka/cdc --for=condition=Ready --timeout=15m
kubectl -n kafka wait kafkatopic --all --for=condition=Ready --timeout=5m
kubectl -n kafka rollout status deploy/kafka-ui --timeout=5m
