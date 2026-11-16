# Services

Every service owns its application code, dependencies and Dockerfile. Build commands run from the repository root so Docker can include `shared/` alongside the selected service.

| Folder | Responsibility | Default container command | Kubernetes worker command |
|---|---|---|---|
| `collector/` | Scrape one platform; save HTTP collections or publish Kafka raw listings | Gunicorn `services.collector.app:app` | `python -m services.collector.worker` |
| `normaliser/` | Standardise raw fields, currencies and attributes | Gunicorn `services.normaliser.app:app` | `python -m services.normaliser.worker` |
| `matcher/` | Match cleaned listings and calculate cluster statistics | Gunicorn `services.matcher.app:app` | `python -m services.matcher.worker` |
| `scorer/` | Calculate and persist explained risk scores | Uvicorn `services.scorer.app:app` | Same HTTP server, called by KafkaSource |
| `gateway/` | Search API, orchestration and durable progress | Gunicorn `services.gateway.app:app` | Same server with `PIPELINE_MODE=kafka` |
| `frontend/` | Render browser pages and forward API calls to the gateway | Gunicorn `services.frontend.app:app` | Same server |
| `storage/` | Persist `listings.raw` idempotently; deployed as `listing-store` | `python -m services.storage.worker` | Same worker |
| `maintenance/` | TTL refresh and evaluation load generation | `python -m services.maintenance` | CronJobs pass `ttl-refresh` or `loadgen` arguments |

For example:

```bash
docker build -f services/normaliser/Dockerfile -t cdc-normaliser .
docker build -f services/matcher/Dockerfile -t cdc-matcher .
```

Compose runs collector, normaliser and matcher HTTP endpoints. Kubernetes overrides those three images' commands to run their Kafka workers. Each image contains its own service and common helpers; normalisation, matching and scoring use separate images.

All Kubernetes manifests live under `infra/k8s/`. The image names and tags are mapped in `infra/k8s/base/kustomization.yaml`; `infra/scripts/images.sh` builds each image from its service folder.

Product websites are external data sources. The application does not host or deploy them.
