"""Collector adapter: scrape.requests -> listings.raw, using the team's scraper (web/scraper.py) as is.

Every collector reads the whole topic in its own consumer group and keeps only the requests for its
own platform. FETCH_FROM ("<public prefix>=<in-cluster prefix>") makes it fetch the page from the
in-cluster copy of the store; the listing keeps its public product_url.
"""
import os
from datetime import date, datetime, timezone
from decimal import Decimal

from cdc_tools.common import connect_db
from scraper import ScrapeError, scrape

from .worker import Reject, run as run_worker

PLATFORM = os.environ["COLLECTOR_PLATFORM"]   # "Cartlane", "Tao Market" or "Lazora", as the scraper reports it
FETCH_FROM = os.environ.get("FETCH_FROM", "")
completed = []


def _fetch_url(url):
    public, _, local = FETCH_FROM.partition("=")
    return local + url[len(public):] if public and url.startswith(public) else url


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def handle(_key, request):
    if request.get("source_platform") != PLATFORM:
        return []
    try:
        listings = scrape(_fetch_url(request["product_url"]))
    except ScrapeError as e:
        if request.get("request_id"):
            completed.append((request["request_id"], [], str(e)[:500]))
        raise Reject(e) from e
    if not listings:
        if request.get("request_id"):
            completed.append((request["request_id"], [], "No products found"))
        raise Reject("No products found")
    scraped_at = datetime.now(timezone.utc).isoformat()
    out = []
    for listing in listings:
        raw = {k: _plain(v) for k, v in listing.items()}
        raw["reviews"] = [{k: _plain(v) for k, v in r.items()} for r in listing["reviews"]]
        raw["source_listing_id"] = listing["sku"]
        raw["scraped_at"] = scraped_at
        out.append((f"{raw['source_platform']}:{raw['source_listing_id']}", raw))
    if request.get("request_id"):
        completed.append((request["request_id"], [key for key, _ in out], None))
    return out


def after_publish():
    """Record completion only after raw listings (or their rejection) reach Kafka."""
    if not completed:
        return
    with connect_db() as conn:
        for request_id, ids, error in completed:
            conn.execute("""INSERT INTO collection_runs (request_id, source_platform, listing_ids, error)
                            VALUES (%s, %s, %s, %s) ON CONFLICT (request_id, source_platform)
                            DO UPDATE SET listing_ids = EXCLUDED.listing_ids, error = EXCLUDED.error,
                                          completed_at = now()""", (request_id, PLATFORM, ids, error))
    completed.clear()


def run():
    return run_worker(handle, after_publish=after_publish)
