"""Normaliser adapter: listings.raw -> listings.cleaned, using Gordon's normalise_record() as is.
Output key is the brand (the matcher's blocking key); listings with no recognised brand share one key.
Synthetic listings from infra's load generator stop here: they exist to load the listing-store."""
from shared.listings import UNBRANDED
from .pipeline import normalise_record

from shared.kafka_worker import run as run_worker


def handle(_key, raw):
    if raw.get("synthetic"):
        return []
    rec = normalise_record(raw)
    rec["scraped_at"] = raw.get("scraped_at")
    return [(rec["brand"] or UNBRANDED, rec)]


def run():
    return run_worker(handle)


if __name__ == "__main__":
    raise SystemExit(run())
