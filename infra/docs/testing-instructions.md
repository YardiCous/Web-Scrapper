# Testing instructions (for the marker)

These steps start the whole system on one machine, check that it works, and reproduce the evaluation graphs. Every command runs from the folder you cloned the repository into (the one that contains `infra/`). On Windows, run them in an **Ubuntu (WSL2) terminal**, not PowerShell, and clone the repository inside Ubuntu.

```bash
git clone <repository URL>
cd <repository folder>
```

## 1. Prerequisites (once)

| Need | Check with | Install |
|---|---|---|
| Docker with ≥ 6 GB of memory (the `lite` profile uses about 4.5 GB) | `docker run --rm hello-world` | Windows: WSL2 + Docker Engine or Docker Desktop. macOS: Docker Desktop |
| k3d ≥ 5.9 | `k3d version` | https://k3d.io/stable/#installation |
| kubectl | `kubectl version --client` | https://kubernetes.io/docs/tasks/tools/ |
| helm ≥ 3 | `helm version` | https://helm.sh/docs/intro/install/ |
| make, bash, python3 with venv, openssl | `make --version`, `python3 -m venv --help` | Ubuntu: `sudo apt-get install -y make python3-venv openssl` (macOS: already installed) |

**Windows (WSL2) from scratch:**
1. In an admin PowerShell, run `wsl --install -d Ubuntu-24.04`, reboot, and create the Linux user.
2. In Ubuntu, run `curl -fsSL https://get.docker.com | sudo sh` and `sudo usermod -aG docker $USER`.
3. In PowerShell, run `wsl --shutdown`, then reopen Ubuntu.
4. Install kubectl, k3d and helm from the links above, using the Linux instructions.

Ports used on this machine: 8080 (web), 8081 (Knative), 32100–32103 (Kafka). Close other programs using them.

## 2. Start everything

```bash
make -C infra up
```
This takes about 10–15 minutes the first time (it downloads images) and about 1–2 minutes after that. It is safe to run again. It ends by printing the URLs. The command waits for each component to be healthy and stops with an error if one isn't.

With 16 GB or more of memory available to Docker, `make -C infra up PROFILE=default` runs 3 Kafka brokers (replication factor 3) instead of 1. The broker-failure experiment is only meaningful in that profile.

## 3. Check it works

```bash
make -C infra smoke
```
Expected last line: `==> Smoke test passed`. The test publishes the 32 listings scraped from the three dummy stores to `listings.raw`, their 32 matched rows to `listings.normalized`, and one scrape request per store. It checks that:
- every record matches its topic's JSON Schema;
- every message can be read back unchanged, on the partition its key determines;
- each store's collector handled the scrape requests;
- `smoke-consumer` wrote all 32 listings to PostgreSQL;
- the Knative KafkaSource delivered all 32 matched rows to the scorer, which scales up from zero to receive them;
- every listing went through the normaliser, matcher and scorer into `risk_scores` (`risk_scores_rows: 32/32`).

Run it twice: the second run still shows `listings_rows: 32/32`, because the database writes are idempotent.

```bash
make -C infra status
```
This shows every pod, the Kafka topics with partitions and replication, the KEDA ScaledObject, the Knative service and source, and consumer-group lag (all 0 when idle).

In a browser:

| URL | What you should see |
|---|---|
| http://kafka-ui.localhost:8080 | Kafka UI: cluster `cdc`, the five topics and their messages |
| http://store-a.localhost:8080, http://store-b.localhost:8080, http://store-c.localhost:8080 | the three dummy shops |
| http://api.localhost:8080, http://app.localhost:8080 | placeholder JSON (gateway and frontend slots) |

## 4. Run the evaluation

```bash
make -C infra experiments    # about 30 min; writes infra/eval/results/*.csv
make -C infra graphs         # writes infra/eval/results/plots/*.png
```
Or run one at a time:

| Command | Claim tested | Output |
|---|---|---|
| `make -C infra exp-consumer-kill` | a consumer that crashes mid-batch (or is shut down) loses nothing and creates no duplicate rows; redelivered messages are absorbed by the upsert; time until its partitions are reassigned | `consumer_kill.csv` |
| `make -C infra exp-keda-burst` | KEDA scales consumers out on lag and the backlog drains | `keda_burst.csv`, `keda_burst_timeseries.csv` |
| `make -C infra exp-coldstart` | the Knative scorer scales to zero when idle; cold- vs warm-start latency | `knative_coldstart.csv` |
| `make -C infra exp-broker-kill` | a broker failure under load loses no acknowledged message; recovery time | `broker_kill.csv` |

Each script accepts options (`--count`, `--rate`, `--trials`, …), for example `make -C infra exp-keda-burst ARGS="--count 40000 --rate 2000"`. See `python3 infra/eval/<script>.py --help`.

## 5. Stop

```bash
make -C infra down
```
This deletes the cluster and all its data.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `make up` stops waiting for Kafka or Knative | Docker is short of memory. WSL2 gets half the machine's RAM by default, so on an 8 GB machine create `%UserProfile%\.wslconfig` containing `[wsl2]` and `memory=6GB`, then run `wsl --shutdown`. Run `make -C infra up` again. |
| `port is already allocated` | another program uses 8080, 8081 or 32100–32103; stop it, or use `HTTP_PORT=9080` for the web port |
| `*.localhost` doesn't open in the browser | use Chrome, Edge or Firefox, which resolve `*.localhost` to this machine |
| anything else | `make -C infra status`, then `kubectl -n <namespace> logs <pod>` |
