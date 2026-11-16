# Scorer service

This folder owns the risk model, HTTP application, CLI, dependencies and Dockerfile. Run commands from the repository root.

```bash
pip install -r services/scorer/requirements.txt
python -m services.scorer.cli data/samples/normalised_output.json
python -m services.scorer.cli --json data/samples/normalised_output.json
docker build -f services/scorer/Dockerfile -t cdc-scorer .
```

The HTTP app is `services.scorer.app:app`. Kubernetes KafkaSource delivers one matched listing to `POST /`; Docker Compose's gateway calls the same endpoint directly. The scorer calculates risk and writes `risk_scores` when `DATABASE_URL` is configured. It performs no normalisation or matching.

- `202`: scored, including an idempotent database write when configured.
- `400`: invalid listing.
- `503`: database unavailable; event delivery can retry.

Database tables are defined centrally in `infra/k8s/base/data/schema.sql` and initialised on a fresh deployment. To save offline scores to an already initialised database, set `DATABASE_URL` and run:

```bash
python -m services.scorer.cli --save data/samples/normalised_output.json
```

Model weights and thresholds in `config.py` support environment overrides such as `SCORER_W_PRICE_DEV=3`. Historical design notes are in [SCORER_CONTEXT.md](SCORER_CONTEXT.md).
