# CLAUDE.md — Group 1: Online Retail Item Authenticity & Price Checker

Context file for Claude when working in this repository. Read this first.

## Project at a glance

- **Module:** CSC3104 Cloud and Distributed Computing (University of Glasgow / SIT), 2026–2027. Project is worth 30% of the module.
- **What we're building:** A cloud-native distributed system that collects product listings and reviews from multiple e-commerce platforms (Shopee, TikTok Shop, Taobao), matches the same product across platforms, compares prices, and assigns each listing an explainable **counterfeit-risk score**.
- **Claimed originality (must be defended in the report):** No existing tool combines *cross-platform product matching*, *price comparison* and an *explainable counterfeit-risk score* for these marketplaces in a *scalable, fault-tolerant* architecture. Google Shopping / iPrice / Keepa only compare prices (merchant feeds or single platform); marketplace badges and brand programmes are per-platform; Fakespot was shut down by Mozilla in July 2025; ReviewMeta is single-platform; academic work (opinion-spam detection, MinHash/LSH product matching) is usually evaluated offline rather than as an elastic service.
- **Hard requirement from the brief:** the system MUST use containers and/or Kubernetes. Code must be containerised and actually tested — "it worked at home" is not accepted.

## Architecture

Pipeline, each stage a separately deployable service on Kubernetes:

1. **Ingestion (collectors)** — one containerised collector per platform, each its own Kubernetes Deployment so it can be updated and scaled independently. Data comes via unified scraping APIs (Just One API / RapidAPI Marketplace) rather than raw scraping, so no merchant accounts are needed. Raw listings and reviews are published to Kafka, **keyed by product key**.
2. **Normalisation & matching** — consumes raw topics, maps everything to a common schema.
   - Extract language-independent attributes (brand, model number).
   - Translate remaining title text; reduce multilingual titles to **character shingles**.
   - **MinHash + LSH blocking** to generate candidate pairs (avoids O(n²) comparison).
   - Verify candidates with string similarity, then merge into **product clusters**.
   - Work is spread over normaliser replicas by **hash-partitioning on the product key**.
3. **Scoring** — sentiment analysis on reviews, combined with heuristic signals into a probabilistic risk score **with human-readable explanations**. Signals include:
   - price below cluster/market median (price deviation)
   - seller age
   - review sentiment
   - duplicated / near-duplicated review text
   - Deployed on **Knative** so it scales to zero when idle and scales up under load.
4. **Storage** — PostgreSQL for products, listings, clusters and scores.
5. **API & frontend** — gateway service fronting a REST API; React frontend where a user pastes a product URL and sees cross-platform prices and risk scores. The brief says a sophisticated GUI is NOT expected — keep the frontend minimal and spend effort on the distributed parts.

### Distributed-systems mechanisms (these earn the marks — don't drop them)

| Concern | Mechanism |
|---|---|
| Throughput / large data | Kafka topics partitioned by product key |
| Elastic scaling | **KEDA** autoscales collectors and normalisers on Kafka **consumer lag** |
| Serverless | Knative for the scoring service (scale-to-zero) |
| Freshness | **Fixed-TTL refresh**: scheduled job (e.g. Kubernetes CronJob) re-crawls only listings whose `last_seen` exceeds a configurable TTL |
| No lost records | Kafka **at-least-once** delivery (commit offsets only after successful processing) |
| No duplicate records | **Idempotent PostgreSQL upserts** (`INSERT … ON CONFLICT … DO UPDATE` on natural keys) |
| Concurrent cluster updates | **Optimistic concurrency control** on product clusters (version column; retry on conflict) |

## Engineering conventions

- Every service has its own `Dockerfile` and Kubernetes manifests (or Helm chart). Prefer a local cluster (kind / minikube / k3d) that the marker can reproduce.
- Services must be **stateless**; all state lives in Kafka or PostgreSQL so replicas can be killed and rescheduled.
- All consumers must be **idempotent** — assume any message can arrive twice.
- Never hard-code API keys; use Kubernetes Secrets / environment variables. Keep a `.env.example`, never commit real keys.
- Make TTLs, LSH parameters (bands, rows, shingle size), similarity thresholds and score weights **configurable** — the evaluation will sweep them.
- Expose metrics (e.g. Prometheus) from each service: messages processed, consumer lag, processing latency, upsert conflicts, OCC retries. These feed the evaluation graphs.
- Include fault-injection scripts (kill pods, restart brokers, replay messages) — we need to *demonstrate* correctness under failure, not just claim it.
- Cache/record sample API responses as test fixtures so the system can be demoed and tested without live API quota.
- Write in British English in docs and the report.

## Evaluation plan (needed for the article — quantitative evidence is heavily weighted)

Aim to produce graphs for:
- **Matching quality:** precision/recall of cross-platform matching on a hand-labelled set; LSH candidate reduction vs. brute-force pairwise.
- **Scalability:** throughput and end-to-end latency vs. number of replicas; KEDA scale-up/scale-down timeline under a load burst.
- **Serverless:** Knative cold-start latency vs. warm latency.
- **Correctness under failure:** zero lost / zero duplicate records after pod kills and message replays; OCC conflict and retry counts under concurrent updates.
- **Freshness / cost:** crawl volume with TTL refresh vs. naive full re-crawl.
- **Risk score:** sanity check on known-genuine (official stores) vs. suspicious listings; show example explanations.

## Deliverables checklist (final submission)

- [ ] Source code packaged as a Docker image, or a GitHub repo URL (include launch scripts and test data)
- [ ] Article `GROUP01.pdf` — IEEE or ACM proceedings format, ~3,000 words, ≤6 pages
- [ ] Testing instructions `GROUP01_INSTRUCTIONS.pdf` — explicit, step-by-step for the marker
- [ ] Video presentation, 10–15 minutes (xSite upload or URL)
- [ ] Peer evaluation (each member, individually)

### Article required sections
Abstract (≤200 words) · Introduction & motivation · System Design (with diagrams, justified choices) · Implementation (concurrency, client–server communication, fault/failure handling, what didn't work) · Evaluation (quantitative, graphs) · Related Work (critical comparison — say what others don't do that we do) · Conclusions & future work · Numbered references (only works cited).

## Marking weights (to prioritise effort)

| Component | Weight | What markers look for |
|---|---|---|
| Proposal | 17% | Done |
| Progress presentation | 15% | Progress made; each member explains their contribution |
| Implementation | 25% | Working advertised functionality, originality, challenge level, advanced features (concurrency control, serverless, callbacks) |
| Video presentation | 18% | Implementation, functionality, design justification |
| Article | 25% | Originality argument vs. related work, quantitative evaluation |

Final marks are adjusted by peer evaluation.

## Scope guidance for Claude

- When suggesting work, favour things that strengthen **distributed/cloud-native behaviour and measurable evaluation** over UI polish.
- The risk score identifies *indicators* of counterfeits — never describe it as guaranteeing authenticity.
- If a feature threatens the final deadline, propose a smaller version that still demonstrates the same distributed mechanism, and note the cut so it can go in the report's "missing functionality" discussion.
- Keep this file updated as design decisions change (record the decision and the reason).

@scorer/SCORER_CONTEXT.md