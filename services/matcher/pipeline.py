"""Product clusters and scoring rows produced from cleaned listings."""

from shared.listings import listing_id
from .core.match import find_matches
from .core.cluster import build_clusters


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
        if m.get("scraped_at"):
            rows[-1]["scraped_at"] = m["scraped_at"]
    return rows



def match_listings(listings):
    rows = []
    for cluster in build_clusters(listings, find_matches(listings)):
        cluster["cluster_id"] = stable_cluster_id(cluster["listings"])
        rows.extend(to_scoring_rows(cluster))
    return rows
