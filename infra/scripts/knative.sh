#!/usr/bin/env bash
# Installs Knative Serving (Kourier) and Eventing with KafkaSource/KafkaSink from the pinned release YAML.
. "$(dirname "$0")/lib.sh"
need kubectl

gh_release() { echo "https://github.com/$1/releases/download/knative-v$2/$3"; }

log "Knative Serving $KNATIVE_SERVING_VERSION + Kourier $KNATIVE_KOURIER_VERSION"
kubectl apply -f "$(gh_release knative/serving "$KNATIVE_SERVING_VERSION" serving-crds.yaml)" >/dev/null
kubectl wait crd -l knative.dev/crd-install=true --for=condition=Established --timeout=120s >/dev/null
kubectl apply -f "$(gh_release knative/serving "$KNATIVE_SERVING_VERSION" serving-core.yaml)" >/dev/null
kubectl apply -f "$(gh_release knative-extensions/net-kourier "$KNATIVE_KOURIER_VERSION" kourier.yaml)" >/dev/null
kubectl -n knative-serving patch configmap config-network --type merge \
  -p '{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}' >/dev/null
# The queue-proxy sidecar Knative adds to every Knative Service pod has no resources by default.
kubectl -n knative-serving patch configmap config-deployment --type merge -p '{"data":{
  "queue-sidecar-cpu-request":"25m","queue-sidecar-memory-request":"32Mi",
  "queue-sidecar-cpu-limit":"500m","queue-sidecar-memory-limit":"128Mi"}}' >/dev/null

log "Knative Eventing $KNATIVE_EVENTING_VERSION + Kafka source/sink $KNATIVE_KAFKA_VERSION"
kubectl apply -f "$(gh_release knative/eventing "$KNATIVE_EVENTING_VERSION" eventing-crds.yaml)" >/dev/null
kubectl wait crd -l knative.dev/crd-install=true --for=condition=Established --timeout=120s >/dev/null
kubectl apply -f "$(gh_release knative/eventing "$KNATIVE_EVENTING_VERSION" eventing-core.yaml)" >/dev/null
for f in eventing-kafka-controller.yaml eventing-kafka-source.yaml eventing-kafka-sink.yaml; do
  kubectl apply -f "$(gh_release knative-extensions/eventing-kafka-broker "$KNATIVE_KAFKA_VERSION" "$f")" >/dev/null
done

# These ship without limits (or without any resources); every workload here must have both.
set_limits() { # namespace kind/name container cpu memory
  kubectl -n "$1" set resources "$2" -c "$3" --limits="cpu=$4,memory=$5" >/dev/null
}
set_limits knative-eventing deployment/eventing-controller eventing-controller 1 512Mi
set_limits knative-eventing deployment/kafka-controller controller 1 512Mi
set_limits knative-eventing deployment/kafka-sink-receiver kafka-sink-receiver 1 768Mi
kubectl -n knative-eventing set resources statefulset/request-reply --requests=cpu=50m,memory=64Mi \
  --limits=cpu=500m,memory=256Mi >/dev/null

for ns in knative-serving kourier-system knative-eventing; do
  kubectl -n "$ns" wait deployment --all --for=condition=Available --timeout=600s
done
