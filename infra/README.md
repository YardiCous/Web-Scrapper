# infra

Infrastructure for the Online Retail Item Authenticity Checker (CSC3104 Group 1): a local Kubernetes cluster (k3d) running Kafka (Strimzi, KRaft) and Kafka UI, plus the deploy setup the pipeline services plug into.

## Prerequisites

Docker, k3d, kubectl, helm, make, bash and Python 3. Docker needs about 8 GB of memory for the lite profile and about 12 GB for the default profile.

- **Windows:** use WSL2 (Ubuntu 24.04) and run everything inside it. Install Docker Engine there (`curl -fsSL https://get.docker.com | sudo sh`, then `sudo usermod -aG docker $USER`) or use Docker Desktop with WSL integration. Install [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/), [k3d](https://k3d.io/stable/#installation) and [helm](https://helm.sh/docs/intro/install/) inside WSL, plus `sudo apt-get install -y make git python3-venv`. Clone the repo inside WSL or use it from `/mnt/c/...`.
- **macOS:** Docker Desktop (or Colima/OrbStack), then `brew install k3d kubectl helm`.

## Quick start

```bash
make -C infra up       # first run takes ~10 min; safe to re-run
make -C infra smoke    # end-to-end check through Kafka
make -C infra status   # pods, topics, consumer-group lag
make -C infra down     # delete the cluster and its data
```

`PROFILE=lite` (default: 1 Kafka broker, RF 1) or `PROFILE=default` (3 brokers, RF 3, `min.insync.replicas` 2), for example `make -C infra up PROFILE=default`. Run `make -C infra help` for all targets.

| What | Where |
|---|---|
| Kafka UI | http://kafka-ui.localhost:8080 |
| Kafka from a pod | `cdc-kafka-bootstrap.kafka.svc:9092` |
| Kafka from your laptop | `localhost:32100` |

## Layout

| Path | Contents |
|---|---|
| `Makefile`, `scripts/` | entry points (`make up/down/status/smoke/deploy/images/push`) |
| `versions.env` | pinned versions of k3s and the operators |
| `bootstrap/k3d/` | everything k3d-specific: cluster creation and the local-only manifest patches |
| `k8s/base/` | portable manifests, one folder per namespace; `kustomization.yaml` lists every image |
| `k8s/components/lite/` | lite-profile patches |
| `k8s/overlays/` | `local-lite`, `local-default` (base + profile + k3d) |
| `images/` | Dockerfiles for images built here (`cdc-tools`: smoke test and helpers) |
| `schemas/`, `samples/`, `docs/contracts.md` | message contracts per topic |
