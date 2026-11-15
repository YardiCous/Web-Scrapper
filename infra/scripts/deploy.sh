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

log "Waiting for Postgres initialisation"
kubectl -n data rollout status statefulset/postgres --timeout=5m

log "Waiting for pipeline, scoring and web"
for d in listing-store collector-store-a collector-store-b collector-store-c normaliser matcher; do
  kubectl -n pipeline rollout status "deploy/$d" --timeout=5m
done
kubectl -n pipeline wait scaledobject --all --for=condition=Ready --timeout=2m
kubectl -n scoring wait ksvc/scorer --for=condition=Ready --timeout=5m
kubectl -n scoring wait kafkasink/listings-dlq --for=condition=Ready --timeout=5m
kubectl -n scoring wait kafkasource/scorer-feed --for=condition=Ready --timeout=5m
for d in store-a store-b store-c gateway frontend; do
  kubectl -n web rollout status "deploy/$d" --timeout=5m
done
