#!/usr/bin/env bash
. "$(dirname "$0")/lib.sh"
need kubectl

log "Nodes"
kubectl get nodes

log "Pods"
kubectl get pods -A | awk 'NR == 1 || $1 ~ /^(kafka|data|pipeline|scoring|web|keda|knative-|kourier-)/'

log "Kafka"
kubectl -n kafka get kafka,kafkanodepool

log "Topics"
kubectl -n kafka get kafkatopics \
  -o custom-columns='TOPIC:.spec.topicName,PARTITIONS:.spec.partitions,REPLICAS:.spec.replicas,MIN_ISR:.spec.config.min\.insync\.replicas,READY:.status.conditions[?(@.type=="Ready")].status'

log "KEDA and Knative"
kubectl -n pipeline get scaledobject 2>/dev/null || true
kubectl -n scoring get ksvc,kafkasource,kafkasink 2>/dev/null || true

log "Consumer-group lag (summed over partitions; ASSIGNED = partitions owned by a live consumer)"
if [ -z "$(kafka_pod)" ]; then
  echo "Kafka is not running"
  exit 0
fi
printf '%-36s %-22s %10s %8s\n' GROUP TOPIC LAG MEMBERS
kafka_exec /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups 2>/dev/null |
  awk '$3 ~ /^[0-9]+$/ {
         k = $1 " " $2
         if (!(k in lag)) { lag[k] = "-"; members[k] = 0 }
         if ($6 ~ /^[0-9]+$/) lag[k] = (lag[k] == "-" ? 0 : lag[k]) + $6
         if ($7 != "-") members[k]++
       }
       END { for (k in lag) { split(k, a, " "); printf "%-36s %-22s %10s %8d\n", a[1], a[2], lag[k], members[k] } }' |
  sort
