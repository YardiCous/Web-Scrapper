# Distributed Online Retail Item Authenticity & Price Checker

This project describes a distributed online retail item authenticity and price checker using Docker and Kubernetes.

Paste a Cartlane, Tao Market or Lazora (dummy e-commerce websites hosted externally) product URL to compare matching listings across platforms. The application converts prices to SGD, matches products and calculates explained counterfeit-risk scores.

- Cartlane: `https://paegnium.github.io/dummysite/?product=78`
- Tao Market: `https://paegnium.github.io/dummysite2/products/78.html`
- Lazora: `https://paegnium.github.io/dummysite3/#product-7`

## Repository layout

```text
services/
  collector/       scraper, HTTP endpoint and Kafka worker
  normaliser/      normalisation logic, HTTP endpoint and Kafka worker
  matcher/         matching logic, HTTP endpoint and Kafka worker
  scorer/          risk scoring and persistence
  gateway/         search API and orchestration
  frontend/        browser pages, templates and styles
  storage/         Kafka listing persistence
  maintenance/     TTL refresh and load generation
shared/            database, Kafka, URL and listing helpers
data/              recorded listings and normalised sample rows
infra/
  k8s/             all Kubernetes manifests
  scripts/         build and deployment scripts
  schemas/         Kafka message contracts
  docs/            architecture and deployment documentation
  eval/            evaluation experiments
```

Every service has its own Dockerfile. See the [service map](services/README.md) for entry points and responsibilities.

## Run on Kubernetes (k3d) — main deployment

This is the full system: Kafka, KEDA autoscaling, the Knative scorer and the TTL refresh CronJob all run here, and every evaluation experiment uses it.

On Windows, run everything from the Ubuntu (WSL2) terminal inside a clone of the repository on the Ubuntu file system. On macOS and Linux, run it natively.

Requires Docker, k3d, kubectl, Helm, Make, Python and OpenSSL. Install them by following section 1 (Prerequisites) of the [deployment instructions](infra/docs/deployment.md), which also covers the evaluation experiments and troubleshooting. Then, from the repository root:

```bash
make -C infra up           # create the k3d cluster and deploy everything
make -C infra status       # pods, topics and consumer-group lag
```

Open [http://app.localhost:8080](http://app.localhost:8080) and paste one of the product URLs above.

To wind down:

```bash
make -C infra down         # delete the k3d cluster, including all its data
```

### Pipeline

Collectors, normaliser and matcher run as Kafka workers:

```text
Frontend → Gateway → scrape.requests → Collectors → listings.raw
                                                     ├→ Listing storage → PostgreSQL
                                                     └→ Normaliser → listings.cleaned
                                                                       → Matcher → listings.normalized
                                                                                     → KafkaSource → Scorer → PostgreSQL
```

The frontend polls the gateway for durable search progress. The gateway waits for all three collections and fresh scores, then saves and returns the comparison. KEDA scales workers on consumer lag; Knative scales the scorer to zero when idle; a TTL CronJob refreshes stale listings. Searches time out after 300 seconds by default.

Product websites are hosted externally; this application only collects their listings. The selected collector retrieves the submitted product; the other two retrieve their catalogues for comparison.

### Host ports

| Port | Purpose |
| --- | --- |
| 8080 | Traefik ingress: frontend and gateway at `app.localhost` |
| 8081 | Kourier (Knative ingress); Knative URLs end in `.knative.localhost` |
| 32100–32103 | Kafka external listener (bootstrap + one per broker), for load and replay scripts |

Close other programs using these ports before running `make -C infra up`.

## Lightweight demo: Docker Compose

Compose is a quick way to see the application working without a cluster, for example on plain Windows with Docker Desktop. **It is not the distributed system:** services call each other synchronously over HTTP, and there is no Kafka, KEDA, Knative or TTL refresh. Use the Kubernetes deployment above to see those mechanisms.

Requires Docker Desktop (on Windows, run from PowerShell in a clone on the Windows file system).

1. Start Docker Desktop and wait until the engine is running.
2. From the repository root, create the environment file (first setup only; keep an existing `.env`):

   ```powershell
   Copy-Item env.example .env
   ```

3. Open `.env` and set `POSTGRES_USER` and `POSTGRES_PASSWORD`, and use the same values in `DATABASE_URL`.
4. Build and start every container:

   ```powershell
   docker compose up --build -d
   docker compose ps          # all services should show "running" / "healthy"
   ```

5. Open [http://localhost:5000](http://localhost:5000) and paste one of the product URLs above.

Each search follows this flow:

```text
Browser → Frontend → Gateway → Three collectors
                            → Normaliser → Matcher → Scorer
                            → Saved results → Frontend
```

Collectors save raw listings and reviews. The gateway sends those listings to the normaliser and matcher, asks the scorer to persist scores, then saves the completed search.

```powershell
docker compose logs -f frontend gateway normaliser matcher scorer
docker compose down        # stop and remove the containers; keeps the pgdata volume
docker compose down -v     # also delete the pgdata volume (wipes the database)
```

Use `down -v` if you change the PostgreSQL credentials or the schema, since the database is only initialised on an empty volume. `init.sql` links to `infra/k8s/base/data/schema.sql`; PostgreSQL creates the complete schema on its first start with an empty volume. Deployment assumes a fresh database; there is no migration service.

Running Compose and the k3d cluster at the same time works (they use different ports) but uses a lot of CPU and memory; stop whichever you are not using.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker compose up --build -d gateway
python -m services.frontend.app
```

The local frontend listens on port 5000 and calls the gateway on port 8500. For individual service development, install `services/<name>/requirements.txt` and run that service's entry point from the repository root.

| Service | Compose host port | URL override |
| --- | --- | --- |
| Frontend | 5000 | — |
| Gateway | 8500 | `GATEWAY_URL` on the frontend |
| Collectors | 8101–8103 | `COLLECTOR_CARTLANE_URL`, `COLLECTOR_TAO_URL`, `COLLECTOR_LAZORA_URL` |
| Normaliser | 8300 | `NORMALISER_URL` |
| Matcher | 8400 | `MATCHER_URL` |
| Scorer | 8200 | `SCORER_URL` |
| PostgreSQL | 5432 | `DATABASE_URL` |

Containers listen on port 8080. The collector image defaults to HTTP; Kubernetes starts its Kafka worker explicitly. The gateway reads `DATABASE_URL` from `.env` locally; containers receive PostgreSQL settings through environment variables.

## API

`POST /api/searches` accepts `{"url":"https://paegnium.github.io/dummysite/?product=78"}` and returns `request_id`, `status`, `listings` and `error`. The `Location` header identifies `GET /api/searches/<request_id>`. Kafka searches (Kubernetes) return 202 while pending; HTTP searches (Compose) return completed results synchronously. The frontend renders saved results at `/searches/<request_id>`.

The normaliser accepts `POST /normalise` and the matcher accepts `POST /match`, each with a `{"listings": [...]}` body and response; these HTTP endpoints are used only by Compose. The scorer accepts one matched listing at `POST /` (called by the Knative KafkaSource on Kubernetes). HTTP services expose process health at `/healthz`; the frontend and gateway also expose dependency health at `/health`.

[Architecture](infra/docs/architecture.md) · [Message contracts](infra/docs/contracts.md) · [Infrastructure commands](infra/README.md)
