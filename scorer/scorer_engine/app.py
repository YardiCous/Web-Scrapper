"""
HTTP entry point. A Knative KafkaSource delivers each `listings.normalised`
message as a CloudEvent POSTed to `/` (Knative Serving scales on HTTP
concurrency, not Kafka lag, so KafkaSource is the bridge).

Status codes drive delivery semantics:
  202  scored (and saved, unless running without DATABASE_URL)
  400  invalid message: not retryable, so KafkaSource sends it to the deadLetterSink
  503  database/transient failure: KafkaSource retries, giving at-least-once delivery

Each message carries its cluster's price statistics, so scoring needs no
lookups and the service is stateless apart from the database write.
"""

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import ValidationError

from . import signals, store
from .combiner import combine
from .models import Listing

log = logging.getLogger("scorer")

SCORED = Counter("scorer_scored_total", "Listings scored", ["band"])
UPSERTS = Counter("scorer_upserts_total", "risk_scores writes", ["result"])  # changed / noop
ERRORS = Counter("scorer_errors_total", "Failed messages", ["kind"])
LATENCY = Histogram("scorer_processing_seconds", "Time to score and save one listing")

state = {"pool": None}


@asynccontextmanager
async def lifespan(app):
    if os.environ.get("DATABASE_URL"):
        from psycopg_pool import ConnectionPool
        state["pool"] = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=10, open=True)
    else:
        log.warning("DATABASE_URL not set: dry run, scores are returned but not saved")
    yield
    if state["pool"] is not None:
        state["pool"].close()


app = FastAPI(title="scorer", lifespan=lifespan)
app.mount("/metrics", make_asgi_app())


def _unwrap(body):
    """Binary-mode CloudEvents carry the listing as the body; structured mode wraps it in `data`."""
    if isinstance(body, dict) and "specversion" in body and "data" in body:
        return body["data"]
    return body


@app.post("/")
async def receive(request: Request):
    start = time.perf_counter()
    try:
        listing = Listing.model_validate(_unwrap(await request.json()))
    except (ValidationError, ValueError) as e:
        ERRORS.labels("invalid").inc()
        return JSONResponse({"error": "invalid listing", "detail": str(e)}, status_code=400)

    sig, facts = signals.compute(listing)
    result = combine(sig, facts)
    SCORED.labels(result.band).inc()

    saved = None
    if state["pool"] is not None:
        try:
            with state["pool"].connection() as conn:
                saved = store.upsert(conn, listing, result, store.input_hash(listing))
        except Exception:
            ERRORS.labels("db").inc()
            log.exception("upsert failed for %s", listing.listing_id)
            return JSONResponse({"error": "database unavailable"}, status_code=503)
        UPSERTS.labels("changed" if saved else "noop").inc()

    LATENCY.observe(time.perf_counter() - start)
    return JSONResponse(
        {"listing_id": listing.listing_id, "saved": saved, **vars(result)}, status_code=202
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok", "db": state["pool"] is not None}
