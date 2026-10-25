# Scorer

Counterfeit-risk scorer. The design is in [SCORER_CONTEXT.md](SCORER_CONTEXT.md). All commands below run from this `scorer/` folder.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

pytest                                                   # unit tests (DB tests skip without DATABASE_URL)
python -m scorer_engine.cli fixtures/*.json             # score table
python -m scorer_engine.cli --json fixtures/synthetic_suspects.json   # full detail
```

Every file in `fixtures/` is normaliser output (one listing object or a list):

| File | Contents |
|---|---|
| `normalised_output.json` | 22 listings from the normaliser (store_a/b/c) |
| `sample_store_a.json` | the normaliser's single sample listing |
| `dummy_sites.json` | 32 Cartlane/Tao/Lazora listings, converted once from the scrapers' raw output |
| `synthetic_suspects.json` | 9 **synthetic** listings (official / reseller / suspect) so every signal fires |

The scorer trusts the `cluster_*` fields, so if you edit a price, update that cluster's statistics too.

## With PostgreSQL

Start the database from the repo root first: `docker compose up -d db`.

```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/listings
psql "$DATABASE_URL" -f sql/risk_scores.sql
python -m scorer_engine.cli --save fixtures/*.json
python -m scorer_engine.cli --save fixtures/*.json      # 2nd run: all unchanged
pytest tests/test_store.py                               # replay x50 = no-op; moved median rescores
```

## As a container

```bash
docker build -t scorer:v1 .
docker run --rm -p 8080:8080 -e DATABASE_URL=postgresql://user:password@host.docker.internal:5432/listings scorer:v1
curl -i -X POST localhost:8080/ -H 'content-type: application/json' -H 'ce-type: listing.normalised' \
     -d @fixtures/sample_store_a.json
curl localhost:8080/metrics/
```

The endpoint returns three status codes:
- `202`: the listing was scored.
- `400`: the message is invalid. KafkaSource does not retry it and sends it to the dead-letter sink.
- `503`: the database failed. KafkaSource retries it.

Every weight, threshold and parameter in `scorer/config.py` can be overridden with an environment variable, e.g. `SCORER_W_PRICE_DEV=3`.
