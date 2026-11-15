# Online Retail Item Authenticity & Price Checker

Paste a Cartlane, Tao Market or Lazora product URL to compare matching listings across platforms. The system normalises prices to SGD, matches products with MinHash/LSH and string similarity, and calculates an explained counterfeit-risk score from prices, seller age and reviews.

## Run with Docker Compose

Requires Docker Engine or Docker Desktop with WSL integration enabled for your distro.

```bash
cp env.example .env       # first setup only; keep an existing .env
# Edit the credentials if needed.
docker compose up --build -d
```

Open http://localhost:5000 and try:

- Cartlane: `https://paegnium.github.io/dummysite/?product=78`
- Tao Market: `https://paegnium.github.io/dummysite2/products/78.html`
- Lazora: `https://paegnium.github.io/dummysite3/#product-7`

A search asks the matching collector for the submitted product and the other two collectors for their catalogues. The website runs the shared normaliser/matcher, sends the resulting listings to the scorer, and renders matching listings with SGD prices, risk bands, explanations and signal coverage. A storefront URL returns that platform's catalogue and its matches. Collectors stay idle until a search arrives.

Compose runs PostgreSQL, three HTTP collectors, the HTTP scorer and the website. This is the HTTP baseline. The Kubernetes deployment below provides Kafka, KEDA and Knative.

```bash
docker compose logs -f web scorer collector-cartlane collector-tao collector-lazora
docker compose down      # retains the pgdata volume
```

`init.sql` links to the shared schema in `infra/k8s/base/data/schema.sql`. PostgreSQL creates all tables on its first start with an empty data volume. Both deployment paths assume a fresh database with this integrated schema.

## Run the distributed system

Requires Docker, k3d, kubectl, Helm, Make, Python and OpenSSL. See [step-by-step instructions](infra/docs/deployment.md).

```bash
make -C infra up
```

Open http://app.localhost:8080. The frontend calls the gateway, which publishes requests for all three platforms to Kafka. Collectors publish raw listings; the normaliser and matcher generate clusters; Knative delivers matched listings to the scorer. PostgreSQL holds search progress and results, so the browser can poll through gateway restarts. Results become ready when all three collections and their fresh scores are available. Searches time out after 300 seconds by default.

KEDA scales collectors, normaliser and matcher on consumer lag. Knative scales scoring to zero when idle. A TTL CronJob refreshes stale listings. Writes are idempotent, and Kafka workers commit input offsets after successful output delivery and database writes.

[Architecture](infra/docs/architecture.md) · [Message contracts](infra/docs/contracts.md) · [Infrastructure commands](infra/README.md)

## Run the website locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker compose up --build -d collector-cartlane collector-tao collector-lazora scorer
python -m web.app
```

The local app reads `DATABASE_URL` from `.env`, and uses collectors on ports 8101–8103 and the scorer on port 8200. Containers use the internal service names and PostgreSQL `PG*` variables. Override collector URLs with `COLLECTOR_CARTLANE_URL`, `COLLECTOR_TAO_URL`, `COLLECTOR_LAZORA_URL`, and scoring with `SCORER_URL`.

## API

`POST /api/searches` accepts `{"url":"https://paegnium.github.io/dummysite/?product=78"}`. It returns a search record with `request_id`, `status`, `listings` and `error`, and a `Location` header for `GET /api/searches/<request_id>`. Kafka searches return HTTP 202 while pending; the HTTP baseline returns completed results synchronously. `GET /searches/<request_id>` renders the saved result or progress page.

`GET /healthz` reports process health. `GET /health` checks database connectivity, or gateway connectivity on the separate frontend.

Risk scores describe indicators rather than guaranteeing authenticity. Currency conversion uses fixed demonstration rates. Matching quality and scoring are limited by the available listing and review data.
