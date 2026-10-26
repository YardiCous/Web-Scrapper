#!/usr/bin/env bash
. "$(dirname "$0")/lib.sh"
need docker k3d kubectl helm

bash "$INFRA_DIR/bootstrap/k3d/create-cluster.sh"

log "Building our images and importing them into k3d"
bash "$INFRA_DIR/scripts/images.sh" build
bash "$INFRA_DIR/scripts/images.sh" import

log "Namespaces"
kubectl apply -f "$INFRA_DIR/k8s/base/namespaces.yaml"

log "Strimzi operator $STRIMZI_VERSION"
helm upgrade --install strimzi oci://quay.io/strimzi-helm/strimzi-kafka-operator \
  --version "$STRIMZI_VERSION" --namespace kafka --wait --timeout 10m

bash "$INFRA_DIR/scripts/deploy.sh"

log "Up (profile: $PROFILE). Kafka UI: http://kafka-ui.localhost:$HTTP_PORT  Next: make smoke"
