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
| your laptop (k3d) | `localhost:32100` |

Plaintext, no authentication. The cluster is only reachable from your own machine.

## Rules for every producer and consumer

1. **Producers** use `acks=all` and idempotence. **In Python with `confluent-kafka` (librdkafka) also set `"partitioner": "murmur2_random"`.** librdkafka's default hashes keys differently from Java and `kafka-python`, so the same key would land on a different partition and per-key ordering breaks. `kafka-python` and Java already use murmur2.
2. **Consumer groups** are named `cdc.<service>`, for example `cdc.normaliser`, `cdc.matcher`, `cdc.collector.store_a`, `cdc.scorer`. Replicas of one service share its group; that is how KEDA's extra replicas split the partitions. Never reuse another service's group.
3. **At-least-once:** turn auto-commit off and commit offsets only after the work is done (row written, message produced). A crash then means a redelivery, never a loss.
4. **Expect duplicates.** Redeliveries after a crash or rebalance are normal. Every write must be idempotent: upsert by natural key (`listing_id`, `cluster_id`) and never blind-insert or increment.
5. **Ordering** holds within a partition, so per key, and nowhere else.
6. **Poison messages:** after a few retries, produce the original key and value to `listings.dlq` with headers `dlq-error`, `dlq-service`, `dlq-source-topic`, `dlq-source-partition` and `dlq-source-offset`. Then commit and carry on; don't block the partition.
7. **Collectors:** with murmur2 over 3 partitions, `store_a`→0, `store_b`→1 and `store_c`→2, but a future `store_d` also hashes to 2. Each collector therefore uses its own group `cdc.collector.<platform>`, reads all partitions and skips keys for other platforms, instead of relying on owning a partition.

## Payloads

### `listings.raw`
One scraped listing. Extra fields are allowed and ignored.
```json
{"source_platform":"store_a","source_listing_id":"A-1001","title":"...","price":329.0,"currency":"USD",
 "seller_id":"sel_a_01","seller_name":"AudioHub SG","selling_since":"2021-02-01","rating":4.7,"review_count":230,
 "review":[{"text":"...","rating":5,"date":"2026-09-01T00:00:00Z"}],
 "product_url":"https://...","scraped_at":"2026-10-26T10:00:00Z"}
```
What the dummy sites give and what the collector (JJ) must do:

| Field | store_a = dummysite ("Cartlane") | store_b = dummysite2 ("Tao Market") | store_c = dummysite3 ("Lazora") |
|---|---|---|---|
| `source_platform` | site says `Cartlane`; emit `store_a` | `Tao Market` → `store_b` | `Lazora` → `store_c` |
| `source_listing_id` | not given; use the record's numeric `id` as a string | same | same |
| `currency` | USD | USD | SGD |
| `review[].date` | ISO timestamp | ISO timestamp | `YYYY-MM-DD` (schema accepts both) |
| `scraped_at` | not given; collector's UTC time | same | same |

All three sites embed their full catalogue as JSON in `<script id="product-data">` in the initial HTML; dummysite and dummysite2 also serve `products.json`. Their `product_url` values point at `paegnium.github.io`, while in the cluster the sites are served as `store-a`, `store-b` and `store-c` (Phase 2).

[`samples/raw_listings.json`](../samples/raw_listings.json) holds the 22 listings of Gordon's sample in raw form (price in SGD, `selling_since` = 2026-10-26 minus `seller_age_days`). It is test data for this topic, not real site output.

### `listings.cleaned` (proposed: Gordon)
`listings.normalized` without the `cluster_*` fields, plus `scraped_at`. Keyed by `brand` so one matcher replica sees every listing of a brand, which LSH blocking needs.

### `listings.normalized`
One message per listing, carrying its cluster's aggregates. The schema is derived from Gordon's sample, [`samples/normalised_output.json`](../samples/normalised_output.json). Notes:
- `listing_id` = `<source_platform>:<source_listing_id>` (the `listings.raw` key); `cluster_id` is a `listing_id` chosen by the matcher.
- Prices are in SGD; `reviews[].date` is `YYYY-MM-DD`.
- **Requested from Gordon:** pass `scraped_at` through. The database needs it for `last_seen_at` (TTL refresh) and to drop out-of-order updates.

### `scrape.requests` (proposed: JJ, Yu Da)
```json
{"request_id":"6f1c…","source_platform":"store_b","product_url":"https://…","source_listing_id":null,
 "reason":"user_request","requested_at":"2026-10-26T10:00:00Z"}
```
`reason` is `user_request` (gateway: a URL pasted by a user, `source_listing_id` may be null) or `ttl_refresh` (CronJob: re-crawl a listing older than the TTL).

### `listings.dlq`
The failed message's original key and value, unchanged, with the `dlq-*` headers above.

## Database (Postgres, namespace `data`)

From a pod: `postgres.data.svc:5432`, database `cdc`. Pods that load the `cdc-env` ConfigMap and the `postgres-credentials` Secret (see `templates/`) get the standard libpq variables (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`), so `psycopg.connect()` with no arguments works. The password is generated per machine by `make up` and is never committed. For a shell: `kubectl -n data exec -it postgres-0 -- psql -U cdc -d cdc`.

The tables are in [`k8s/base/data/schema.sql`](../k8s/base/data/schema.sql). Every statement must stay idempotent, because it reruns on each `make up`.

| Table | Key | Written by | Notes |
|---|---|---|---|
| `listings` | `listing_id` | first consumer of `listings.raw` (smoke-consumer today) | `last_seen_at` = newest `scraped_at`; the TTL refresh reads it |
| `clusters` | `cluster_id` | matcher (Gordon) | `version` for optimistic concurrency |
| `risk_scores` | `listing_id` (latest score) | scorer (Declan) | columns to be confirmed with Declan |
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
`risk_scores` works the same way, with `WHERE risk_scores.scored_at <= EXCLUDED.scored_at`.

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
| Gordon | `brand` as the `listings.cleaned` key; the `listings.cleaned` shape; adding `scraped_at` to `listings.normalized` |
| JJ | platform id mapping and `source_listing_id` rule above; `murmur2_random` partitioner; `scrape.requests` shape |
| Yu Da | `scrape.requests` shape; a 4th store's key shares partition 2 with `store_c` (fine with rule 7); the cache table |
| Declan | `risk_scores` columns, `band` values, one row per listing (latest) vs history |
