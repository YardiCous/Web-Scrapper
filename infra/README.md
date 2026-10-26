# infra

Infrastructure for the Online Retail Item Authenticity Checker (CSC3104 Group 1). It runs a local Kubernetes cluster (k3d) with:
- Kafka (Strimzi, KRaft) and Kafka UI
- PostgreSQL
- KEDA
- Knative Serving and Eventing (KafkaSource → scorer)
- the three dummy stores

It also provides the slots, templates and contracts the team's services plug into, and the evaluation experiments.

**Marker:** follow [docs/testing-instructions.md](docs/testing-instructions.md).
**Teammates:** read [docs/onboarding.md](docs/onboarding.md) and [docs/contracts.md](docs/contracts.md).
**Overview:** [docs/architecture.md](docs/architecture.md).

## Quick start

Needs Docker, k3d, kubectl, helm, make, python3 and openssl. On Windows, run everything inside WSL2 (details in the testing instructions).

```bash
make -C infra up       # ~10-15 min the first time, ~1-2 min after; safe to re-run
make -C infra smoke    # end-to-end check: Kafka -> Postgres, Kafka -> Knative scorer
make -C infra status   # pods, topics, KEDA/Knative, consumer-group lag
make -C infra down     # delete the cluster and its data
```

Profiles: `PROFILE=lite` (default) runs 1 Kafka broker with RF 1 and uses about 4.5 GB. `PROFILE=default` runs 3 brokers with RF 3 and `min.insync.replicas` 2, and needs about 12 GB. Example: `make -C infra up PROFILE=default`.

| What | Where |
|---|---|
| Kafka UI | http://kafka-ui.localhost:8080 |
| Dummy stores | http://store-a.localhost:8080, http://store-b.localhost:8080, http://store-c.localhost:8080 |
| Gateway / frontend (placeholders until ready) | http://api.localhost:8080, http://app.localhost:8080 |
| Kafka from a pod / from this machine | `cdc-kafka-bootstrap.kafka.svc:9092` / `localhost:32100` |
| Postgres shell | `kubectl -n data exec -it postgres-0 -- psql -U cdc -d cdc` |

Other targets (`make -C infra help` lists them all):

| Target | Does |
|---|---|
| `deploy` | re-apply manifests only, after editing `k8s/` |
| `images`, `push` | build and import our images into k3d; build multi-arch and push to `ghcr.io/$(GHCR_OWNER)` |
| `load N=… RATE=…` | publish N synthetic listings to `listings.raw` |
| `ttl-refresh` | run the TTL refresh once now |
| `experiments`, `exp-*`, `graphs` | evaluation: CSV and PNG output in `eval/results/` |

## Layout

| Path | Contents |
|---|---|
| `Makefile`, `scripts/` | entry points; `scripts/knative.sh` installs Knative, `secrets.sh` creates the DB secret |
| `versions.env` | pinned versions of k3s, Strimzi, KEDA and Knative |
| `bootstrap/k3d/` | everything k3d-specific: cluster creation, local-only manifest patches, Kourier NodePort |
| `k8s/base/` | portable manifests, one folder per namespace (`kafka`, `data`, `pipeline`, `scoring`, `web`); `kustomization.yaml` lists every image |
| `k8s/components/lite/`, `k8s/overlays/` | lite profile; `local-lite` / `local-default` = base + profile + k3d |
| `images/` | `tools/` (smoke test, smoke-consumer, TTL refresh, load generator, placeholder service), `site/` (dummy stores) |
| `templates/` | starting points for Kafka workers, KEDA ScaledObjects and Knative services |
| `schemas/`, `samples/` | JSON Schema per topic, sample records |
| `eval/` | experiment scripts and `plot.py` (run on this machine) |
| `docs/` | contracts, onboarding, architecture, testing instructions |
