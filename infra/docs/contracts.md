# Message contracts

Every Kafka message has a UTF-8 string key and a UTF-8 JSON value. JSON Schemas (draft 2020-12) are in [`../schemas/`](../schemas/). `make smoke` validates the sample records against them, publishes them and reads them back. Schemas marked **proposed** need the named teammate's confirmation.

## Topics

| Topic | Partitions | Key | Written by | Read by (consumer group) | Schema |
|---|---|---|---|---|---|
| `scrape.requests` | 3 | `source_platform` | gateway (Yu Da), TTL refresh CronJob | collectors (`cdc.collector.<platform>`) | [scrape.requests](../schemas/scrape.requests.schema.json) **proposed** |
| `listings.raw` | 6 | `<source_platform>:<source_listing_id>` | collectors (JJ) | normaliser (`cdc.normaliser`) | [listings.raw](../schemas/listings.raw.schema.json) |
| `listings.cleaned` | 6 | `brand` (blocking key) | normaliser (Gordon) | matcher (`cdc.matcher`) | [listings.cleaned](../schemas/listings.cleaned.schema.json) **proposed** |
| `listings.normalized` | 6 | `cluster_id` | matcher (Gordon) | scorer, via Knative KafkaSource (`cdc.scorer`) | [listings.normalized](../schemas/listings.normalized.schema.json) |
| `listings.dlq` | 1 | the failed message's key | any service | people, via Kafka UI | original value plus `dlq-*` headers |

Replication: RF 3 with `min.insync.replicas=2` in the default profile, RF 1 in the lite profile. Topics exist only as KafkaTopic resources in `k8s/base/kafka/topics.yaml`; auto-creation is off, so a typo in a topic name fails instead of creating a new topic.

## Connecting

| Client runs in | Bootstrap servers |
|---|---|
| a pod in the cluster | `cdc-kafka-bootstrap.kafka.svc:9092` (also `KAFKA_BOOTSTRAP_SERVERS` in the `cdc-env` ConfigMap) |
| the machine running the k3d cluster | `localhost:32100` (local testing only; not reachable from other machines) |

Plaintext, no authentication. The cluster is only reachable from your own machine.

## Rules for every producer and consumer

1. **Producers** use `acks=all` and idempotence. **In Python with `confluent-kafka` (librdkafka) also set `"partitioner": "murmur2_random"`.** librdkafka's default hashes keys differently from Java and `kafka-python`, so the same key would land on a different partition and per-key ordering breaks. `kafka-python` and Java already use murmur2.
2. **Consumer groups** are named `cdc.<service>`, for example `cdc.normaliser`, `cdc.matcher`, `cdc.collector.store_a`, `cdc.scorer`. Replicas of one service share its group; that is how KEDA's extra replicas split the partitions. Never reuse another service's group.
3. **At-least-once:** turn auto-commit off and commit offsets only after the work is done (row written, message produced). A crash then means a redelivery, never a loss.
4. **Expect duplicates.** Redeliveries after a crash or rebalance are normal. Every write must be idempotent: upsert by natural key (`listing_id`, `cluster_id`) and never blind-insert or increment.
5. **Ordering** holds within a partition, so per key, and nowhere else.
6. **Poison messages:** after a few retries, produce the original key and value to `listings.dlq` with headers `dlq-error`, `dlq-service`, `dlq-source-topic`, `dlq-source-partition` and `dlq-source-offset`. Then commit and carry on; don't block the partition.
7. **Collectors:** `scrape.requests` is keyed by platform name over 3 partitions, so two platforms can share a partition. Each collector therefore uses its own group `cdc.collector.<store>`, reads all partitions and skips requests for other platforms, instead of relying on owning a partition.

## Who runs what

The pipeline services run the team's code unchanged, through thin Kafka adapters in [`../../adapters/`](../../adapters/) (one image; `SERVICE_NAME` picks the role):

| Slot | Team code it runs | Adapter |
|---|---|---|
| `collector-store-a/b/c` | `web/scraper.py` `scrape()` | `adapters/collector.py`: one request in, one `listings.raw` message per listing out |
| `normaliser` | `normaliser/core/pipeline.py` `normalise_record()` | `adapters/normaliser.py` |
| `matcher` | `normaliser/core` `find_matches()`, `build_clusters()`, `to_scoring_rows()` | `adapters/matcher.py`: re-clusters each brand it touches; saves `clusters` with the version check |
| `scorer` (Knative) | `scorer/` as is (its own Dockerfile) | none: the KafkaSource POSTs each `listings.normalized` message to it |

Platforms keep the names the scraper reports: `Cartlane` (store-a, dummysite), `Tao Market` (store-b, dummysite2) and `Lazora` (store-c, dummysite3). A `listing_id` is `<source_platform>:<sku>`, for example `Cartlane:78`, as in the normaliser and scorer.

## Payloads

### `listings.raw`
One listing exactly as `web/scraper.py` returns it, with numbers as numbers, plus `source_listing_id` (= `sku`) and `scraped_at` (the collector's UTC time). Extra fields are allowed and ignored.
```json
{"sku":"78","source_platform":"Cartlane","source_listing_id":"78","title":"Apple MacBook Pro 14 Inch Space Grey",
 "price":649.99,"currency":"USD","seller_id":"cartlane-001","seller_name":"Cartlane","selling_since":"2026-10-08",
 "rating":4.7,"review_count":3,"reviews":[{"text":"Very happy with my purchase!","rating":5,"review_date":"2025-04-30"}],
 "product_url":"https://paegnium.github.io/dummysite/?product=78","scraped_at":"2026-11-11T00:00:00Z"}
```
The collectors fetch pages from the in-cluster copies of the stores (`FETCH_FROM`), while `product_url` keeps the public `paegnium.github.io` address. [`samples/raw_listings.json`](../samples/raw_listings.json) is the 32 listings in `normaliser/data` in this form.

### `listings.cleaned`
The raw fields plus what `normalise_record()` adds: `price_sgd`, `seller_age_days`, `clean_title`, `brand`, and the adapter's `listing_id`. Keyed by `brand` (or `unbranded`) so one matcher replica sees every listing of a brand. Matching per brand gives the same clusters as the normaliser's batch run over all listings.

### `listings.normalized`
One message per listing with its cluster's price statistics: the rows of `to_scoring_rows()`, which is what the scorer's `Listing` model reads. `cluster_id` is the smallest `listing_id` in the cluster. [`samples/normalised_output.json`](../samples/normalised_output.json) is the normaliser's batch output for the 32 sample listings.

### `scrape.requests` (proposed: JJ, Yu Da)
```json
{"request_id":"6f1c…","source_platform":"Tao Market","product_url":"https://paegnium.github.io/dummysite2/products/78.html",
 "source_listing_id":null,"reason":"user_request","requested_at":"2026-11-11T10:00:00Z"}
```
`reason` is `user_request` (gateway: a URL pasted by a user, `source_listing_id` may be null) or `ttl_refresh` (CronJob: re-crawl a listing older than the TTL).

### `listings.dlq`
The failed message's original key and value, unchanged, with the `dlq-*` headers above.

## Database (Postgres, namespace `data`)

From a pod: `postgres.data.svc:5432`, database `cdc`. Pods that load the `cdc-env` ConfigMap and the `postgres-credentials` Secret (see `templates/`) get the standard libpq variables (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`), so `psycopg.connect()` with no arguments works. They also get `DATABASE_URL` (`postgresql://cdc:…@postgres.data.svc:5432/cdc`) for code that takes one connection string, like the scorer. The password is generated per machine by `make up` and is never committed. For a shell: `kubectl -n data exec -it postgres-0 -- psql -U cdc -d cdc`.

The tables are in [`k8s/base/data/schema.sql`](../k8s/base/data/schema.sql). Every statement must stay idempotent, because it reruns on each `make up`.

| Table | Key | Written by | Notes |
|---|---|---|---|
| `listings` | `listing_id` | first consumer of `listings.raw` (smoke-consumer today) | `last_seen_at` = newest `scraped_at`; the TTL refresh reads it |
| `matcher_listings` | `listing_id` | matcher | every cleaned listing seen, so any replica can re-cluster a brand |
| `clusters` | `cluster_id` | matcher | `version` for optimistic concurrency |
| `risk_scores` | `listing_id` (latest score) | scorer (Declan) | same columns as `scorer/sql/risk_scores.sql` |
| cache table | | gateway (Yu Da) | not created here; add it to `schema.sql` |

**Idempotent upsert.** A redelivered message rewrites the same values, and an older version that arrives late is skipped:
```sql
INSERT INTO listings AS l (listing_id, source_platform, source_listing_id, product_url, payload, last_seen_at)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (listing_id) DO UPDATE
SET product_url = EXCLUDED.product_url, payload = EXCLUDED.payload,
    last_seen_at = EXCLUDED.last_seen_at, updated_at = now()
WHERE l.last_seen_at <= EXCLUDED.last_seen_at;
```
`risk_scores` uses a content hash instead of a timestamp. The scorer's upsert only writes when `input_hash` or `model_version` changed (`WHERE risk_scores.input_hash IS DISTINCT FROM EXCLUDED.input_hash OR …`), so a replayed message is a no-op.

**Optimistic concurrency on `clusters`.** Two matcher replicas may update the same cluster; the `version` check makes the second writer notice and retry instead of overwriting:
```sql
INSERT INTO clusters (cluster_id, brand) VALUES ($1, $2) ON CONFLICT (cluster_id) DO NOTHING;   -- create if new
SELECT version, member_listing_ids FROM clusters WHERE cluster_id = $1;                          -- read: version = n
UPDATE clusters                                                                                  -- write if still n
SET member_listing_ids = $2, platforms = $3, size = $4, price_median_sgd = $5,
    version = version + 1, updated_at = now()
WHERE cluster_id = $1 AND version = $6;          -- $6 = n
-- 0 rows updated: another writer won. Re-read and retry (bounded, e.g. 5 attempts).
```

## Still to confirm

| Who | What |
|---|---|
| Gordon | The matcher adapter re-clusters a whole brand per batch: fine for the dummy sites, but it grows with the brand. Listings with no known brand are matched among themselves only. |
| Wylie / Yu Da | `feature/collector-containers` (HTTP collectors behind the Flask site) is not merged here. The site could publish to `scrape.requests` and read results from Postgres instead. `scrape.requests` shape; the cache table |
| Team | Topic name: `listings.normalized` here; the scorer's docs say `listings.normalised`. Only the KafkaSource names the topic, so the scorer code needs no change. |
| Team | One `listings` table: `init.sql` (docker-compose: `id`, `sku`, `reviews` table) differs from the one here; in the cluster only this one exists |
