#!/usr/bin/env bash
. "$(dirname "$0")/lib.sh"
need docker k3d kubectl helm openssl

bash "$INFRA_DIR/bootstrap/k3d/create-cluster.sh"

log "Building our images and importing them into k3d"
bash "$INFRA_DIR/scripts/images.sh" build
bash "$INFRA_DIR/scripts/images.sh" import

log "Namespaces and secrets"
kubectl apply -f "$INFRA_DIR/k8s/base/namespaces.yaml"
bash "$INFRA_DIR/scripts/secrets.sh"

log "Strimzi operator $STRIMZI_VERSION"
helm upgrade --install strimzi oci://quay.io/strimzi-helm/strimzi-kafka-operator \
  --version "$STRIMZI_VERSION" --namespace kafka --wait --timeout 10m

log "KEDA $KEDA_VERSION"
helm repo add kedacore https://kedacore.github.io/charts --force-update >/dev/null
helm upgrade --install keda kedacore/keda --version "$KEDA_VERSION" \
  --namespace keda --create-namespace --wait --timeout 10m

bash "$INFRA_DIR/scripts/knative.sh"
bash "$INFRA_DIR/bootstrap/k3d/knative.sh"

bash "$INFRA_DIR/scripts/deploy.sh"

log "Up (profile: $PROFILE)"
cat <<EOF
  Kafka UI   http://kafka-ui.localhost:$HTTP_PORT
  Stores     http://store-a.localhost:$HTTP_PORT  http://store-b.localhost:$HTTP_PORT  http://store-c.localhost:$HTTP_PORT
  Gateway    http://api.localhost:$HTTP_PORT   Frontend  http://app.localhost:$HTTP_PORT
  Kafka      localhost:32100 (from this machine)
Next: make smoke
EOF
