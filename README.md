# Online Retail Item Authenticity & Price Checker

Paste a Cartlane, Tao Market or Lazora product URL to compare matching listings across platforms. The application converts prices to SGD, matches products and calculates explained counterfeit-risk scores.

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
  storefront/      dummy shop image
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

## Run with Docker Compose

Requires Docker Engine or Docker Desktop with WSL integration enabled.

```bash
cp env.example .env       # first setup only; keep an existing .env
# Set PostgreSQL credentials in .env.
docker compose up --build -d
```

Open http://localhost:5000 and try:

- Cartlane: `https://paegnium.github.io/dummysite/?product=78`
- Tao Market: `https://paegnium.github.io/dummysite2/products/78.html`
- Lazora: `https://paegnium.github.io/dummysite3/#product-7`

Compose runs separate frontend, gateway, collector, normaliser, matcher and scorer containers, plus PostgreSQL. Each search follows this flow:

```text
Browser → Frontend → Gateway → Three collectors
                            → Normaliser → Matcher → Scorer
                            → Saved results → Frontend
```

The selected collector retrieves the submitted product; the other two retrieve their catalogues for comparison. Collectors save raw listings and reviews. The gateway sends those listings to the normaliser and matcher, asks the scorer to persist scores, then saves the completed search. A storefront URL returns that platform's catalogue and matching products.

```bash
docker compose logs -f frontend gateway normaliser matcher scorer
docker compose down      # retains the pgdata volume
```

`init.sql` links to `infra/k8s/base/data/schema.sql`. PostgreSQL creates the complete schema on its first start with an empty volume. Deployment assumes a fresh database; there is no migration service.

## Run with Kubernetes

Requires Docker, k3d, kubectl, Helm, Make, Python and OpenSSL. Follow the [deployment instructions](infra/docs/deployment.md).

```bash
make -C infra up
```

Open http://app.localhost:8080. The same service folders supply the Kubernetes images, with collectors, normaliser and matcher running Kafka workers:

```text
Frontend → Gateway → scrape.requests → Collectors → listings.raw
                                                     ├→ Listing storage → PostgreSQL
                                                     └→ Normaliser → listings.cleaned
                                                                       → Matcher → listings.normalized
                                                                                     → KafkaSource → Scorer → PostgreSQL
```

The frontend polls the gateway for durable search progress. The gateway waits for all three collections and fresh scores, then saves and returns the comparison. KEDA scales workers on consumer lag; Knative scales the scorer to zero when idle; a TTL CronJob refreshes stale listings. Searches time out after 300 seconds by default.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker compose up --build -d gateway
python -m services.frontend.app
```

The local frontend listens on port 5000 and calls the gateway on port 8500. For individual service development, install `services/<name>/requirements.txt` and run that service's entry point from the repository root.

| Service | Host port | URL override |
|---|---|---|
| Frontend | 5000 | — |
| Gateway | 8500 | `GATEWAY_URL` on the frontend |
| Collectors | 8101–8103 | `COLLECTOR_CARTLANE_URL`, `COLLECTOR_TAO_URL`, `COLLECTOR_LAZORA_URL` |
| Normaliser | 8300 | `NORMALISER_URL` |
| Matcher | 8400 | `MATCHER_URL` |
| Scorer | 8200 | `SCORER_URL` |

Containers listen on port 8080. The collector image defaults to HTTP; Kubernetes starts its Kafka worker explicitly. The gateway reads `DATABASE_URL` from `.env` locally; containers receive PostgreSQL settings through environment variables.

## API

`POST /api/searches` accepts `{"url":"https://paegnium.github.io/dummysite/?product=78"}` and returns `request_id`, `status`, `listings` and `error`. The `Location` header identifies `GET /api/searches/<request_id>`. Kafka searches return 202 while pending; HTTP searches return completed results synchronously. The frontend renders saved results at `/searches/<request_id>`.

The normaliser accepts `POST /normalise` and the matcher accepts `POST /match`, each with a `{"listings": [...]}` body and response. The scorer accepts one matched listing at `POST /`. HTTP services expose process health at `/healthz`; the frontend and gateway also expose dependency health at `/health`.

[Architecture](infra/docs/architecture.md) · [Message contracts](infra/docs/contracts.md) · [Infrastructure commands](infra/README.md)

Risk scores describe available indicators and do not guarantee authenticity. SGD conversion uses fixed demonstration exchange rates.
