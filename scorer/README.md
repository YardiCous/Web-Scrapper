# Scorer

Counterfeit-risk scorer. The design is in [SCORER_CONTEXT.md](SCORER_CONTEXT.md). All commands below run from this `scorer/` folder.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m scorer_engine.cli ../infra/samples/normalised_output.json
python -m scorer_engine.cli --json ../infra/samples/normalised_output.json
```

The CLI accepts normaliser output as one listing object or a list. Recorded sample rows are available in `../infra/samples/normalised_output.json`.

The scorer trusts the `cluster_*` fields, so if you edit a price, update that cluster's statistics too.

## With PostgreSQL

Start the database from the repo root first: `docker compose up -d db`.

```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/listings
psql "$DATABASE_URL" -f sql/risk_scores.sql
python -m scorer_engine.cli --save ../infra/samples/normalised_output.json
```

## As a container

```bash
docker build -t scorer:v1 .
docker run --rm -p 8080:8080 -e DATABASE_URL=postgresql://user:password@host.docker.internal:5432/listings scorer:v1
curl -i -X POST localhost:8080/ -H 'content-type: application/json' -H 'ce-type: listing.normalised' \
     -d @listing.json
curl localhost:8080/metrics/
```

Create `listing.json` containing one normalised listing before sending the request. The endpoint returns three status codes:
- `202`: the listing was scored.
- `400`: the message is invalid. KafkaSource does not retry it and sends it to the dead-letter sink.
- `503`: the database failed. KafkaSource retries it.

Every weight, threshold and parameter in `scorer/config.py` can be overridden with an environment variable, e.g. `SCORER_W_PRICE_DEV=3`.
