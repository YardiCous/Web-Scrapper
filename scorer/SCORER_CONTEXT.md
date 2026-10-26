# Scorer Context — Online Retail Item Authenticity Checker (CSC3104 Group 1)

Handoff notes from planning in Claude chat. Treat as the agreed design; verify against the actual repo before assuming any file exists.

## Project in one paragraph
Cloud-native system that collects listings + reviews from Shopee, TikTok Shop and Taobao (via RapidAPI / Just One API), matches the same product across platforms (attribute extraction + character shingles + MinHash/LSH, hash-partitioned normalisers), and gives each listing an explainable counterfeit-risk score plus cross-platform price comparison. Stack: containerised per-platform collectors on Kubernetes → Kafka (keyed by product/cluster) → normaliser/matcher → **scorer (Knative, scale-to-zero)** → PostgreSQL → REST gateway + React frontend. KEDA autoscales collectors/normalisers on consumer lag. At-least-once Kafka + idempotent Postgres upserts; optimistic concurrency on product clusters.

## Coursework constraints that matter for the scorer
- Must use containers/Kubernetes. Marks reward concurrency handling, serverless, fault handling, and **quantitative evaluation** with graphs.
- Progress presentation: Tue 29 Oct 2026. Final submission: Sun 15 Nov 2026 (code, ≤6-page IEEE/ACM article, testing instructions PDF, 10–15 min video).
- No sophisticated GUI expected; focus on the distributed/cloud-native behaviour.

## Scorer: what it does
Consumes normalised listings, computes heuristic signals (each 0–1, higher = riskier, or `None` if not computable), combines them with a logistic function into a score + band + top-3 human-readable reasons, upserts into `risk_scores`.

## Input message (topic `listings.normalised`, key = cluster_id)
This is the normaliser's actual output (supersedes the originally agreed shape; real sample in `fixtures/normaliser_cartlane_78.json`, older-format samples in `fixtures/sample_store_a.json` and `fixtures/normalised_output.json`):
```json
{
  "cluster_id": "Cartlane:78", "cluster_size": 2,
  "cluster_platforms": ["Cartlane", "Tao Market"],
  "cluster_price_median_sgd": 1788.74, "cluster_price_min_sgd": 877.49, "cluster_price_max_sgd": 2699.99,
  "listing_id": "Cartlane:78", "source_platform": "Cartlane", "source_listing_id": "78",
  "title": "Apple MacBook Pro 14 Inch Space Grey", "brand": "apple",
  "price_sgd": 877.49, "seller_id": "cartlane-001", "seller_name": "Cartlane", "seller_age_days": 18,
  "rating": 4.7, "review_count": 3,
  "reviews": [{"text": "Very happy with my purchase!", "rating": 5, "review_date": "2025-04-30"}],
  "product_url": "https://paegnium.github.io/dummysite/?product=78"
}
```
Prices are in SGD; currency conversion and cluster statistics are the normaliser's job. Validated by `scorer_engine/models.py` (Listing / Review); unknown fields are ignored. The model also accepts optional `seller_sales`, `seller_is_official` and `fetched_at`, which the normaliser does not send yet; without them `seller_volume` and `official` are `None`.

## Output table
```sql
CREATE TABLE risk_scores (
  listing_id TEXT PRIMARY KEY, cluster_id TEXT NOT NULL,
  score REAL NOT NULL, band TEXT NOT NULL, coverage REAL NOT NULL,
  contributions JSONB NOT NULL, reasons JSONB NOT NULL,
  model_version TEXT NOT NULL, input_hash TEXT NOT NULL,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON risk_scores (cluster_id);
```

## Signals (signals.py — unit-test each)
| Key | Definition | Min data |
|---|---|---|
| price_dev | discount = (cluster_median − price)/cluster_median; risk = clip(discount/0.35, 0, 1). Only cheaper-than-median counts. *(Originally a robust MAD z-score; changed because the normaliser sends the median, not the prices; see Decisions.)* | cluster_size ≥3 (incl. self) and a median |
| seller_age | exp(−seller_age_days/180) | seller_age_days present |
| seller_volume | 1/(1+ln(1+sales)) | seller_sales present (not sent yet) |
| official | 1.0 if official/mall store else 0.0 (negative weight) | seller_is_official present (not sent yet) |
| title_kw | 1.0 if title matches `replica|1:1|\bAAA\b|mirror|\bOEM\b|高仿|复刻|原单|super ?copy` (case-insens.) | always |
| dup_reviews | Fraction of reviews (len ≥15) with a near-duplicate: char 5-shingles, MinHash 64 perms, LSH threshold 0.8 (datasketch) | ≥5 reviews |
| burst | Max share of reviews inside any 48 h window | ≥10 timestamped reviews |
| neg_share | Share of reviews with sentiment=negative OR matching `fake|not original|counterfeit|假货|假的|palsu|tiruan` | ≥3 reviews |
| mismatch | Share of rated reviews with rating ≥4 but sentiment negative | ≥3 rated reviews |

## Sentiment
- Model: `cardiffnlp/twitter-xlm-roberta-base-sentiment` (multilingual; labels negative/neutral/positive). Spot-check ~30 real reviews first.
- Load once at import; batch (32); truncation max_length=128.
- Download weights at image build time so cold starts don't download.
- Preferred: separate `sentiment` Knative service called over HTTP (independent scaling; good evaluation material). Fallback: inside scorer with min-scale 1 for demos.

## Combiner (v1 hand weights)
```python
MODEL_VERSION = "v1-handweights"
WEIGHTS = {"price_dev": 2.5, "title_kw": 2.0, "neg_share": 1.8, "dup_reviews": 1.5,
           "seller_age": 1.2, "mismatch": 1.0, "burst": 0.8, "seller_volume": 0.6,
           "official": -2.5}
BIAS = -2.0
```
- score = sigmoid(BIAS + Σ wᵢ·sᵢ) over available signals only (missing ≠ 0).
- coverage = available signals / total signals; low coverage → API shows "Limited data".
- contributions = wᵢ·sᵢ; reasons = top 3 positive contributions > 0.3, templated text (e.g. "Price 58% below the cross-platform median", "Shop is only 21 days old").
- Bands: high ≥0.7, medium ≥0.4, else low.
- v2 weights later from logistic regression on labelled data.

## Service design
- FastAPI, `POST /` receives CloudEvents from a Knative **KafkaSource** (Knative Serving scales on HTTP, not Kafka lag — this bridge is a deliberate design point).
- No price lookups: cluster statistics arrive in each message, so the scorer only writes to PostgreSQL.
- input_hash = sha256(canonical listing JSON incl. cluster stats, excluding fetched_at) → score updates when the median moves, duplicates are no-ops.
- Idempotent upsert: `ON CONFLICT (listing_id) DO UPDATE ... WHERE input_hash IS DISTINCT FROM EXCLUDED.input_hash OR model_version IS DISTINCT FROM EXCLUDED.model_version`.
- Return 202 on success; raise (non-2xx) on failure so KafkaSource retries. Validation failures → `deliverySpec.deadLetterSink`.
- Use psycopg_pool in final version. DATABASE_URL from a Kubernetes Secret.
- Knative Service annotations: min-scale "0", max-scale "10", target "10"; containerConcurrency 20; requests cpu 500m / mem 1Gi.
- KafkaSource: consumerGroup `scorer`, topic `listings.normalised`, sink = scorer ksvc.
- **Rescoring:** Kubernetes CronJob every minute selects listings whose cluster `updated_at` > their `computed_at` (or never scored) and re-publishes them to `listings.normalised`. Natural debounce; counts as a housekeeping task.

## Evaluation plan
Quality (labelled set):
- ~300 listings across 3–4 fake-prone product types, stratified by platform and price; labels fake/genuine/unsure with evidence column; two labellers on 50 → Cohen's kappa.
- 70/30 split; ROC-AUC, precision/recall/F1 at 0.5; per-signal ablation; v1 vs v2 weights; 3–4 worked explanation examples incl. a false positive.
- Avoid circularity: report with/without title_kw where keywords were labelling evidence.

Systems:
- Cold start (from zero pods to row written), median/p95 over 10 runs, with and without sentiment model.
- Load ramp 10/50/100/200 msg/s via producer script: pods over time, throughput, end-to-end latency (computed_at − fetched_at).
- Time to scale back to zero.
- Duplicate replay ×1000 → one row, unchanged computed_at; kill a pod mid-load → no listing left unscored.

## Status / priorities (as of 25 Oct 2026)
Nothing confirmed built yet for the scorer. For the 29 Oct progress presentation:
1. Field-coverage audit of real API responses per platform (which seller/review fields exist) → table for the report.
2. signals.py with unit tests.
3. v1 combiner.
4. Scorer as a plain container writing to PostgreSQL.
Knative + KafkaSource, sentiment service, labelling and evaluation can be shown as next steps with YAML drafted.

## Built (25 Oct 2026)
Items 2–4 above are done: `scorer/scorer_engine/` package, 69 unit tests, CLI, FastAPI app, Dockerfile, `sql/risk_scores.sql`, and drafted `k8s/` YAML (ksvc, KafkaSource, Secret). Not yet verified against a live PostgreSQL or in Docker; `tests/test_store.py` runs once `DATABASE_URL` is set.

## Decisions (25 Oct 2026)
- **Scorer input = the normaliser's real output** (flat fields, SGD prices, cluster median/min/max/size in every message). *Why:* that is what the normaliser produces. Consequences: `prices.py` / `DbPrices` / `SCORER_PRICE_FIXTURES` removed (no lookups, service fully stateless); the image no longer contains fixtures.
- **`price_dev` = % below the cluster median** (`SCORER_PRICE_FULL_RISK_DISCOUNT`, default 0.35 → 35% below = 1.0), replacing the robust MAD z-score and the MAD floor. *Why:* MAD needs the individual prices; the message only carries median/min/max. The median includes the listing itself. If the normaliser later adds the cluster's price list, the robust z-score can come back. Mention in the report.
- **The scorer only reads normaliser output; it has no raw-data code.** Every file in `fixtures/` is in normaliser format. `fixtures/dummy_sites.json` was converted *once* from the scrapers' raw output (Cartlane/Tao share `c_<id>` clusters, same rule as `web/scraper.py:make_sku`; USD→SGD at 1.30; cluster stats computed over the dummy-site and synthetic listings together), after which the raw files and the conversion code were deleted. *Why:* currency, clustering and cluster statistics are the normaliser's job; the scorer trusts them.
- **Synthetic fixtures** (`fixtures/synthetic_suspects.json`, normaliser-format JSON, hand-edited; the original generator script was removed): 9 hand-designed listings (official / reseller / suspect) in clusters c_78, c_88, c_101. *Why:* the dummy sites give ≤2 prices per cluster and ≤3 generic reviews, so `price_dev`, `dup_reviews` and `burst` could never fire. Must be reported as synthetic.
- **Keyword sentiment in v1** (`sentiment.py`, behind a protocol). *Why:* small image, no cold-start model download for the demo; the XLM-R model / sentiment service is the next step.
- `risk_scores` is a new table; the existing `listings` table is untouched.
- Known false positive: the agreed title regex matches "mirror**less**" (no word boundary). Left as agreed; noted in tests.

## Decisions (26 Oct 2026)
- **Normaliser output updated:** reviews carry `review_date` (was `date`); new `seller_id` and `source_listing_id`; cluster ids are now `<platform>:<id>` (e.g. `Cartlane:78`). `Review.date` reads `review_date` and still accepts the legacy `date` key (pydantic `AliasChoices`). *Why:* unknown keys are ignored, so without the alias every review date was silently `None` and `burst` could never fire. All fixtures were switched to `review_date`; fixture cluster ids (`c_78` etc.) were left as they are because ids are opaque to the scorer. `seller_id` / `source_listing_id` are ignored for now.
