"""
  normalise_record(raw)        raw scraped dict -> cleaned + brand-tagged listing
  to_scoring_rows(cluster)     cluster dict -> flat per-listing rows for the scorer
  normalise_and_match(raws)    whole batch in one call (monolith baseline / tests)
"""

from normaliser.core.loader import adapt_record
from normaliser.core.clean import clean_listing
from normaliser.core.extract import extract_attributes
from normaliser.core.match import find_matches, listing_id
from normaliser.core.cluster import build_clusters


def normalise_record(raw):
    """
    One raw scraped record -> enriched listing (adds price_sgd,
    seller_age_days, clean_title, brand).
    """
    return extract_attributes(clean_listing(adapt_record(raw)))


def stable_cluster_id(members):
    """
    Smallest listing id in the cluster. Unlike a union-find root it does
    not depend on processing order, so batch and streaming agree.
    """
    return min(listing_id(m) for m in members)


def to_scoring_rows(cluster):
    rows = []
    for m in cluster["listings"]:
        rows.append({
            "cluster_id": cluster["cluster_id"],
            "cluster_size": cluster["num_listings"],
            "cluster_platforms": cluster["platforms"],
            "cluster_price_median_sgd": cluster["price_median_sgd"],
            "cluster_price_min_sgd": cluster["price_min_sgd"],
            "cluster_price_max_sgd": cluster["price_max_sgd"],

            "listing_id": listing_id(m),
            "source_platform": m["source_platform"],
            "source_listing_id": m["source_listing_id"],
            "title": m["title"],
            "brand": m["brand"],
            "price_sgd": m["price_sgd"],
            "seller_id": m["seller_id"],
            "seller_name": m["seller_name"],
            "seller_age_days": m["seller_age_days"],
            "selling_since": m["selling_since"],
            "rating": m["rating"],
            "review_count": m["review_count"],
            "reviews": m["reviews"],
            "product_url": m["product_url"],
        })
    return rows


def normalise_and_match(raw_records):
    # Batch path: all raw records in, scoring rows out.
    listings = [normalise_record(r) for r in raw_records]
    matches = find_matches(listings)
    clusters = build_clusters(listings, matches)
    rows = []
    for c in clusters:
        c["cluster_id"] = stable_cluster_id(c["listings"])
        rows.extend(to_scoring_rows(c))
    return rows


def _same_url(a, b):
    # Tolerates spaces around the pasted URL and a trailing slash.
    return a.strip().rstrip("/") == b.strip().rstrip("/")


def rows_for_url(rows, url):
    """
    The user pastes ONE product URL. Given the rows from normalise_and_match
    return the rows of the cluster that contains the pasted listing
    Returns [] if no listing has that URL.
    """
    target = next((r for r in rows if _same_url(r["product_url"], url)), None)
    if target is None:
        return []
    members = [r for r in rows if r["cluster_id"] == target["cluster_id"]]
    # sort is stable: the pasted listing (False) goes first, the rest keep their order
    members.sort(key=lambda r: r["listing_id"] != target["listing_id"])
    return members
