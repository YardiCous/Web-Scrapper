#!/usr/bin/env bash
# k3d-only Knative settings: Kourier as a NodePort (k3d's Traefik already owns port 80 on the
# load balancer) mapped to host port 8081, and a fixed domain so requests can use a Host header.
. "$(dirname "$0")/../../scripts/lib.sh"

# Re-applying kourier.yaml later doesn't undo this: kubectl apply only changes fields whose config changed.
kubectl -n kourier-system patch service kourier --type json -p '[
  {"op": "replace", "path": "/spec/type", "value": "NodePort"},
  {"op": "add", "path": "/spec/ports/0/nodePort", "value": 31080}]' >/dev/null
kubectl -n knative-serving patch configmap config-domain --type merge -p '{"data":{"knative.localhost":""}}' >/dev/null
# Knative pins each image tag to a registry digest, but images loaded with `k3d image import`
# exist only in the cluster, so the lookup fails. Skip it for ghcr.io locally.
kubectl -n knative-serving patch configmap config-deployment --type merge \
  -p '{"data":{"registries-skipping-tag-resolving":"kind.local,ko.local,dev.local,ghcr.io"}}' >/dev/null
echo "Kourier on localhost:8081; Knative URLs end in .knative.localhost; no digest lookups for ghcr.io"
