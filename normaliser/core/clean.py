"""
Cleaning pass.

Takes a raw listing dict and adds derived fields that the rest of the pipeline needs,
without throwing away the original fields.

New fields that was added:
  price_sgd        : price converted to SGD
  seller_age_days   : how long the seller has been active, as a number
  clean_title        : lowercased title with punctuation stripped
"""

import re
from datetime import date

# Fixed conversion rates
CURRENCY_TO_SGD = {
    "SGD": 1.0,
    "USD": 1.35,
    "CNY": 0.19,
}


def to_sgd(price, currency):
    rate = CURRENCY_TO_SGD.get(currency)
    if rate is None:
        raise ValueError(f"No conversion rate for currency: {currency}")
    return round(price * rate, 2)


def compute_seller_age_days(selling_since_str, as_of=None):
    # selling_since_str is an ISO date like '2021-03-01'.
    selling_since = date.fromisoformat(selling_since_str)
    as_of = as_of or date.today()
    return (as_of - selling_since).days


def clean_title(title):
    # Lowercase, strip punctuation, collapse whitespace.
    text = title.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)   # drop punctuation
    text = re.sub(r"\s+", " ", text).strip()   # collapse whitespace
    return text


def clean_listing(listing):
    # Return a NEW dict: the original fields plus the derived ones.
    cleaned = dict(listing)  # copy, don't mutate the input
    cleaned["price_sgd"] = to_sgd(listing["price"], listing["currency"])
    cleaned["seller_age_days"] = compute_seller_age_days(listing["selling_since"])
    cleaned["clean_title"] = clean_title(listing["title"])
    return cleaned


def clean_all(listings):
    return [clean_listing(l) for l in listings]


if __name__ == "__main__":
    from core.loader import load_real_listings
    from core.paths import REAL_DATA_PATHS as DATA_PATHS

    raw = load_real_listings(DATA_PATHS)
    cleaned = clean_all(raw)

    # Print a few examples to sanity-check the conversions by eye.
    for item in cleaned[:3]:
        print(item["source_platform"], "|", item["title"])
        print("  price:", item["price"], item["currency"], "->", item["price_sgd"], "SGD")
        print("  seller_age_days:", item["seller_age_days"])
        print("  clean_title:", item["clean_title"])
        print()
