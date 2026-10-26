# Onboarding: plugging your service in

Each teammate's service already has a slot in the cluster, running a placeholder image. Going live means building your image and pointing your slot at it. Message formats and Kafka rules are in [contracts.md](contracts.md); read that first.

## Your slot

| Service | Owner | Manifest | Namespace | Consumer group | Reads → writes |
|---|---|---|---|---|---|
| `collector-store-a/b/c` | JJ | `k8s/base/pipeline/services.yaml` | pipeline | `cdc.collector.store_a` … | `scrape.requests` → `listings.raw` |
| `normaliser` | Gordon | `k8s/base/pipeline/services.yaml` | pipeline | `cdc.normaliser` | `listings.raw` → `listings.cleaned` |
| `matcher` | Gordon | `k8s/base/pipeline/services.yaml` | pipeline | `cdc.matcher` | `listings.cleaned` → `listings.normalized` |
| `scorer` | Declan | `k8s/base/scoring/scorer.yaml` (Knative) | scoring | `cdc.scorer` (KafkaSource) | CloudEvents over HTTP → `risk_scores` |
| `gateway` | Yu Da | `k8s/base/web/apps.yaml` | web | – | HTTP at `api.localhost:8080` |
| `frontend` | (team) | `k8s/base/web/apps.yaml` | web | – | HTTP at `app.localhost:8080` |
| ScaledObjects | Wylie | copy `templates/kafka-worker-scaledobject.yaml` | pipeline | – | example: `k8s/base/pipeline/smoke-consumer.yaml` |

The pipeline slots run at `replicas: 0` until you go live, so a placeholder never commits offsets in your consumer group. The annotated starting points are in [`templates/`](../templates/): `kafka-worker.yaml`, `kafka-worker-scaledobject.yaml` and `knative-service.yaml`.

## What your container gets and must do

Environment (from the `cdc-env` ConfigMap, the `postgres-credentials` Secret and your slot):

| Variable | Example | Notes |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `cdc-kafka-bootstrap.kafka.svc:9092` | |
| `KAFKA_GROUP_ID` | `cdc.normaliser` | Kafka workers only |
| `KAFKA_INPUT_TOPIC`, `KAFKA_OUTPUT_TOPIC`, `KAFKA_DLQ_TOPIC` | `listings.raw`, `listings.cleaned`, `listings.dlq` | Kafka workers only |
| `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` | `postgres.data.svc`, `5432`, `cdc`, … | libpq names: `psycopg.connect()` needs no arguments |
| `DATABASE_URL` | `postgresql://cdc:…@postgres.data.svc:5432/cdc` | the same database as one connection string |
| `SERVICE_NAME` | `normaliser` | use it as the Kafka `client.id` and in log lines |
| `PORT` | `8080` | Knative/HTTP services: listen on it |

Requirements:
- **Kafka workers:** follow the client rules in contracts.md (manual commit after the work, idempotent writes, murmur2 partitioner in confluent-kafka). On **SIGTERM**, stop polling, finish the batch, commit and `close()` the consumer within 30 s. Touch `/tmp/healthy` on every poll-loop iteration; the liveness probe restarts the pod if the file is more than 60 s old. If you'd rather not, delete the probe from your slot.
- **HTTP services (scorer, gateway, frontend):** listen on `$PORT` (8080) and answer `GET /healthz` with 200.
- Log to stdout; JSON lines are easiest to search.
- Images must run on both `linux/amd64` and `linux/arm64`. Ernest's laptop is ARM; the marker's machine and the cloud may not be.

Reference implementation: [`images/tools/cdc_tools/consume.py`](../images/tools/cdc_tools/consume.py) (smoke-consumer) does all of the above in Python.

**Scorer (Declan):** the KafkaSource POSTs each `listings.normalized` message to `/` as a binary-mode CloudEvent. The body is the message JSON unchanged. Headers seen in the cluster:
```
ce-type: dev.knative.kafka.event        ce-id: partition:5/offset:17         ce-subject: partition:5#17
ce-key: store_c:C-3005 (Kafka key)      ce-source: /apis/v1/namespaces/scoring/kafkasources/scorer-feed#listings.normalized
ce-time, ce-knativekafkapartition, ce-knativekafkaoffset, ce-kafkaheader<name> (one per Kafka header)
```
Reply 2xx when done. Any other status is retried 5 times with exponential backoff (0.5 s, 1 s, 2 s …) and then sent to `listings.dlq`. Delivery is ordered per partition, so one event per `cluster_id` is in flight at a time. Write `risk_scores` idempotently (see contracts.md).

## Build, try locally, go live

1. **Build** for your machine and tag with a version (never `latest`):
   ```bash
   docker build -t ghcr.io/yardicous/normaliser:0.1.0 .
   ```
2. **Load it into the local cluster** (no registry needed):
   ```bash
   k3d image import -c cdc ghcr.io/yardicous/normaliser:0.1.0
   ```
3. **Point your slot at it.** In `k8s/base/kustomization.yaml`, change only your entry:
   ```yaml
   - name: normaliser          # Gordon
     newName: ghcr.io/GHCR_OWNER/normaliser   # GHCR_OWNER is filled in from the Makefile
     newTag: "0.1.0"
   ```
   For a pipeline slot, also set `replicas: 1` in `services.yaml`, or add a ScaledObject (KEDA then owns the replica count).
4. **Deploy:** `make -C infra deploy`, then watch with `kubectl -n pipeline logs deploy/normaliser -f`.
   Rebuilding under the same tag? Import again and run `kubectl -n pipeline rollout restart deploy/normaliser`.

## Share it: push to GHCR

The marker's machine pulls your image from GHCR, so push a multi-arch build and **make the package public** (GitHub → your profile → Packages → the package → Package settings → Change visibility). A private package would need an image pull secret in the cluster.

One-time setup:
```bash
gh auth refresh -s write:packages
gh auth token | docker login ghcr.io -u <your-github-user> --password-stdin
docker buildx create --name cdc --driver docker-container --use
docker run --privileged --rm tonistiigi/binfmt --install amd64,arm64   # Linux/WSL only; Docker Desktop has this built in
```
Each release:
```bash
docker buildx build --platform linux/amd64,linux/arm64 -t ghcr.io/yardicous/normaliser:0.1.0 --push .
```
Then commit the `kustomization.yaml` change. The images built in this repo (`cdc-tools`, `cdc-placeholder`, `store-a/b/c`) are pushed with `make -C infra push`.

## Useful commands

| What | Command |
|---|---|
| Everything at a glance | `make -C infra status` |
| Logs | `kubectl -n pipeline logs deploy/<service> -f` |
| Topics and messages | Kafka UI at http://kafka-ui.localhost:8080 |
| Database shell | `kubectl -n data exec -it postgres-0 -- psql -U cdc -d cdc` |
| Kafka from the machine running the cluster | bootstrap `localhost:32100` |
| Push test traffic | `make -C infra load N=1000 RATE=100` (synthetic listings into `listings.raw`) |
