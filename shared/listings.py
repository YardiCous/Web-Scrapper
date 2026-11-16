"""Listing identifiers and result selection shared across service boundaries."""

UNBRANDED = "unbranded"


def listing_id(listing):
    return f"{listing['source_platform']}:{listing['source_listing_id']}"


def rows_for_url(rows, url):
    canonical = url.strip().rstrip("/")
    target = next((r for r in rows if r["product_url"].strip().rstrip("/") == canonical), None)
    if target is None:
        return []
    members = [r for r in rows if r["cluster_id"] == target["cluster_id"]]
    members.sort(key=lambda r: r["listing_id"] != target["listing_id"])
    return members
