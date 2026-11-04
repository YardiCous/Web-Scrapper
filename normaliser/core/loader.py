# Loads the REAL scraped JSON files
import json

def read_json_any_encoding(path):
    for encoding in ("utf-8", "utf-16"):
        try:
            with open(path, "r", encoding=encoding) as f:
                return json.load(f)
        except (UnicodeError, UnicodeDecodeError):
            continue
    raise ValueError(f"Could not read {path} as utf-8 or utf-16")


def adapt_record(raw):
    # Map one raw scraped record into the common format.
    return {
        "source_platform": raw["source_platform"],
        "source_listing_id": raw.get("source_listing_id") or raw["sku"],
        "title": raw["title"],
        "price": float(raw["price"]),
        "currency": raw["currency"],
        "seller_id": raw["seller_id"],
        "seller_name": raw["seller_name"],
        "selling_since": raw["selling_since"],
        "rating": float(raw["rating"]),
        "review_count": int(raw["review_count"]),
        "reviews": raw["reviews"],
        "product_url": raw["product_url"],
    }


def load_real_listings(paths):
    listings = []
    for path in paths:
        raw_records = read_json_any_encoding(path)
        listings.extend(adapt_record(r) for r in raw_records)
    return listings


if __name__ == "__main__":
    from core.paths import REAL_DATA_PATHS
    paths = REAL_DATA_PATHS
    listings = load_real_listings(paths)
    print(f"Loaded {len(listings)} real listings")
    print("First listing:", listings[0]["source_platform"], "-", listings[0]["title"])
    print("  price:", listings[0]["price"], type(listings[0]["price"]))
