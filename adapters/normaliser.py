"""Normaliser adapter: listings.raw -> listings.cleaned, using Gordon's normalise_record() as is.
Output key is the brand (the matcher's blocking key); listings with no recognised brand share one key.
Synthetic listings from infra's load generator stop here: they exist to load the smoke-consumer."""
from normaliser.core.match import listing_id
from normaliser.core.pipeline import normalise_record

from .worker import run as run_worker

UNBRANDED = "unbranded"


def handle(_key, raw):
    if raw.get("synthetic"):
        return []
    rec = normalise_record(raw)
    rec["listing_id"] = listing_id(rec)
    rec["scraped_at"] = raw.get("scraped_at")
    return [(rec["brand"] or UNBRANDED, rec)]


def run():
    return run_worker(handle)
