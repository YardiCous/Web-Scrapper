"""Collector adapter: scrape.requests -> listings.raw, using the team's scraper (web/scraper.py) as is.

Every collector reads the whole topic in its own consumer group and keeps only the requests for its
own platform. FETCH_FROM ("<public prefix>=<in-cluster prefix>") makes it fetch the page from the
in-cluster copy of the store; the listing keeps its public product_url.
"""
import os
from datetime import date, datetime, timezone
from decimal import Decimal

from scraper import ScrapeError, scrape

from .worker import Reject, run as run_worker

PLATFORM = os.environ["COLLECTOR_PLATFORM"]   # "Cartlane", "Tao Market" or "Lazora", as the scraper reports it
FETCH_FROM = os.environ.get("FETCH_FROM", "")


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
        raise Reject(e) from e
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for listing in listings:
        raw = {k: _plain(v) for k, v in listing.items()}
        raw["reviews"] = [{k: _plain(v) for k, v in r.items()} for r in listing["reviews"]]
        raw["source_listing_id"] = listing["sku"]
        raw["scraped_at"] = scraped_at
        out.append((f"{raw['source_platform']}:{raw['source_listing_id']}", raw))
    return out


def run():
    return run_worker(handle)
