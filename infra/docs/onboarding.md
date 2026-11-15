# Service development and deployment

Application code lives in [`services/`](../../services/README.md). Each service owns a Dockerfile and requirements file. Common database, Kafka and listing helpers live in `shared/`; deployment manifests remain in `infra/k8s/`.

| Service folder | Kubernetes workload | Manifest | Consumer group |
|---|---|---|---|
| `services/collector` | `collector-store-a/b/c` | `k8s/base/pipeline/services.yaml` | `cdc.collector.store_a/b/c` |
| `services/normaliser` | `normaliser` | `k8s/base/pipeline/services.yaml` | `cdc.normaliser` |
| `services/matcher` | `matcher` | `k8s/base/pipeline/services.yaml` | `cdc.matcher` |
| `services/scorer` | Knative `scorer` | `k8s/base/scoring/scorer.yaml` | `cdc.scorer` through KafkaSource |
| `services/gateway` | `gateway` | `k8s/base/web/apps.yaml` | — |
| `services/frontend` | `frontend` | `k8s/base/web/apps.yaml` | — |
| `services/storage` | `listing-store` | `k8s/base/pipeline/listing-store.yaml` | `cdc.listing-store` |
| `services/maintenance` | `ttl-refresh`, `loadgen` CronJobs | `k8s/base/pipeline/` | — |
| `services/storefront` | `store-a/b/c` | `k8s/base/web/apps.yaml` | — |

## Build and deploy

Build contexts are always the repository root:

```bash
docker build -f services/normaliser/Dockerfile -t cdc-normaliser .
make -C infra images
make -C infra deploy
```

`make images` builds each unique image referenced by the selected overlay and imports it into k3d. `k8s/base/kustomization.yaml` maps workload aliases to image names and tags. The three collectors share the collector image, with platform-specific environment settings; normaliser and matcher each have their own image.

Docker Compose uses the HTTP entry points. Kubernetes starts collectors, normaliser and matcher with `python -m services.<name>.worker`. The gateway uses `PIPELINE_MODE=kafka`, while the frontend forwards API requests using `GATEWAY_URL`.

## Runtime configuration

- HTTP services listen on port 8080 and expose `/healthz` (collectors also expose `/health`).
- Kafka workers receive `KAFKA_INPUT_TOPIC`, `KAFKA_OUTPUT_TOPIC`, `KAFKA_GROUP_ID`, `KAFKA_BOOTSTRAP_SERVERS` and `SERVICE_NAME` from their manifests and ConfigMaps.
- PostgreSQL settings come from `cdc-env` and the `postgres-credentials` Secret. No credentials are built into images.
- Workers use `shared/kafka.py` and `shared/kafka_worker.py` for consistent producer settings, offset commits, shutdown and liveness handling. `services/storage/worker.py` owns raw-listing persistence.
- KEDA settings live in `k8s/base/pipeline/autoscaling.yaml` and `listing-store.yaml`. Knative scoring settings live in `k8s/base/scoring/scorer.yaml`.

After rebuilding an image under the same tag, import it again and restart its Deployment, for example `kubectl -n pipeline rollout restart deploy/normaliser`. `make -C infra push` publishes the referenced images for both amd64 and arm64; registry credentials must already be configured.

Read [contracts.md](contracts.md) before changing message formats. PostgreSQL initialises `k8s/base/data/schema.sql` once on an empty data volume; deployment assumes a fresh database.
