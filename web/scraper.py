"""
Scraper for the three dummy storefronts:

  Cartlane    https://paegnium.github.io/dummysite/    (?product=<id>)
  Tao Market  https://paegnium.github.io/dummysite2/   (products/<id>.html)
  Lazora      https://paegnium.github.io/dummysite3/   (#product-<id>)

python scraper.py --save https://paegnium.github.io/dummysite/ https://paegnium.github.io/dummysite2/ https://paegnium.github.io/dummysite3/
^ saves all listings and reviews to the database!!, can edit accordingly to save only specific urls
"""

import json
import re
import sys
from datetime import date
from decimal import Decimal
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qs

import requests
from bs4 import BeautifulSoup

TIMEOUT = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; listings-scraper/1.0)"}


class ScrapeError(Exception):
    """Raised when a URL can't be scraped (not a supported page, product missing, etc.)."""


# --------------------------------------------------------------------------- #
# SKU
# --------------------------------------------------------------------------- #
# Platforms whose product ids come from the same upstream catalogue (DummyJSON),
# so the same id means the same product on each of them.
SHARED_ID_PLATFORMS = {"Cartlane", "Tao Market"}


def make_sku(product):
    """
    The sites have no SKU field, but listings.sku is NOT NULL.

    Cartlane and Tao Market reuse the same product ids for the same items
    (78 = MacBook Pro, 47 = Table Lamp, 90 = Puma trainers, 88 = Air Jordan 1),
    so the bare id lets the same product be matched across those two sites.

    Lazora numbers its products 1-8 from a different catalogue, so its id 7
    (a snow jacket) is not Tao Market's id 7 (a perfume). Its SKUs are
    prefixed to stop false matches.

    Change this if the team decides on a different scheme.
    """
    platform = product["source_platform"]
    if platform in SHARED_ID_PLATFORMS:
        return str(product["id"])
    slug = re.sub(r"[^a-z0-9]+", "-", platform.lower()).strip("-")
    return f"{slug}-{product['id']}"


# --------------------------------------------------------------------------- #
# Fetching and finding the embedded JSON
# --------------------------------------------------------------------------- #
def _fetch(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ScrapeError(f"Could not fetch {url}: {e}") from e
    # Without a charset in the Content-Type header, requests assumes
    # ISO-8859-1 and mangles accented names ("FjÃ¤llrÃ¤ven"). The sites are UTF-8.
    if "charset" not in resp.headers.get("Content-Type", "").lower():
        resp.encoding = "utf-8"
    return resp.text


def _embedded_products(html):
    """Return the product list from script#product-data, or None if the page has none."""
    tag = BeautifulSoup(html, "html.parser").select_one("script#product-data")
    if tag is None or not tag.string:
        return None
    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError as e:
        raise ScrapeError(f"product-data JSON is malformed: {e}") from e
    if isinstance(data, dict) and "products" in data:
        data = data["products"]
    return data if isinstance(data, list) else [data]


def _requested_id(url):
    """Product id named in the URL, for sites that use ?product=N or #product-N."""
    parts = urlsplit(url)
    q = parse_qs(parts.query).get("product")
    if q:
        return q[0]
    m = re.fullmatch(r"product-(\w+)", parts.fragment)
    return m.group(1) if m else None


def _product_page_links(base_url):
    """
    Tao Market's home page loads its catalogue with JavaScript, so it has no
    embedded JSON. Its products/index.html lists links to every product page.
    """
    index_url = urljoin(base_url, "products/index.html")
    soup = BeautifulSoup(_fetch(index_url), "html.parser")
    links = []
    for a in soup.select("a[href]"):
        href = a["href"]
        if re.fullmatch(r"[\w-]+\.html", href) and href != "index.html":
            full = urljoin(index_url, href)
            if full not in links:
                links.append(full)
    return links


# --------------------------------------------------------------------------- #
# Normalising one product into the database's shape
# --------------------------------------------------------------------------- #
def _to_date(value):
    """'2025-04-30T09:41:02.053Z' or '2025-04-30' -> date(2025, 4, 30)."""
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def _to_decimal(value):
    return None if value is None else Decimal(str(value))


def _normalise(product):
    reviews = []
    for r in product.get("review") or []:
        rating = r.get("rating")
        if rating is None:
            continue  # reviews.rating is NOT NULL
        rating = int(round(float(rating)))
        if not 1 <= rating <= 5:
            continue  # reviews.rating has CHECK (rating BETWEEN 1 AND 5)
        reviews.append({
            "text": r.get("text"),
            "rating": rating,
            "review_date": _to_date(r.get("date")),
        })

    return {
        "sku": make_sku(product),
        "source_platform": product["source_platform"],
        "product_url": product["product_url"],
        "title": product.get("title"),
        "price": _to_decimal(product.get("price")),
        "currency": (product.get("currency") or "").upper()[:3] or None,
        "seller_id": product.get("seller_id"),
        "seller_name": product.get("seller_name"),
        "selling_since": _to_date(product.get("selling_since")),
        "rating": _to_decimal(product.get("rating")),
        "review_count": int(product.get("review_count") or 0),
        "reviews": reviews,
    }


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def scrape(url):
    """
    Scrape a product URL or storefront home page from any of the three sites.
    Returns a list of normalised listing dicts.
    """
    url = url.strip()
    wanted = _requested_id(url)

    # The #fragment never reaches the server, so fetch without it.
    parts = urlsplit(url)
    fetch_url = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    html = _fetch(fetch_url)
    products = _embedded_products(html)

    if products is None:
        # No embedded data on this page: try the Tao Market route of
        # following links from products/index.html.
        try:
            links = _product_page_links(fetch_url)
        except ScrapeError:
            links = []
        if not links:
            raise ScrapeError(f"No product data found at {url}")
        products = []
        for link in links:
            found = _embedded_products(_fetch(link))
            if found:
                products.extend(found)

    if wanted is not None:
        products = [p for p in products if str(p.get("id")) == wanted]
        if not products:
            raise ScrapeError(f"Product {wanted} not found at {url}")

    return [_normalise(p) for p in products]


# --------------------------------------------------------------------------- #
# Saving to Postgres
# --------------------------------------------------------------------------- #
_UPSERT_LISTING = """
    INSERT INTO listings (
        sku, source_platform, product_url, title, price, currency,
        seller_id, seller_name, selling_since, rating, review_count, scraped_at
    )
    VALUES (
        %(sku)s, %(source_platform)s, %(product_url)s, %(title)s, %(price)s, %(currency)s,
        %(seller_id)s, %(seller_name)s, %(selling_since)s, %(rating)s, %(review_count)s, now()
    )
    ON CONFLICT (source_platform, product_url) DO UPDATE SET
        sku           = EXCLUDED.sku,
        title         = EXCLUDED.title,
        price         = EXCLUDED.price,
        currency      = EXCLUDED.currency,
        seller_id     = EXCLUDED.seller_id,
        seller_name   = EXCLUDED.seller_name,
        selling_since = EXCLUDED.selling_since,
        rating        = EXCLUDED.rating,
        review_count  = EXCLUDED.review_count,
        scraped_at    = now()
    RETURNING id
"""

_INSERT_REVIEW = """
    INSERT INTO reviews (listing_id, text, rating, review_date)
    VALUES (%s, %s, %s, %s)
"""


def save_listings(listings, conn=None):
    """
    Save listings from scrape() into the `listings` and `reviews` tables.

    - A listing already in the table (same source_platform + product_url) is
      updated in place, keeping its id, rather than inserted again.
    - That listing's reviews are replaced with the freshly scraped ones.
    - Everything runs in one transaction: if anything fails, nothing is saved.

    Returns the listing ids, in the same order as the input.
    Pass `conn` to use an existing connection; otherwise db.get_conn() is used.
    """
    own_conn = conn is None
    if own_conn:
        import db  # imported here so scraping alone doesn't need a database or .env
        conn = db.get_conn()
    try:
        ids = []
        with conn:  # commits on success, rolls back on any exception
            with conn.cursor() as cur:
                for listing in listings:
                    cur.execute(_UPSERT_LISTING, listing)
                    listing_id = cur.fetchone()[0]
                    cur.execute("DELETE FROM reviews WHERE listing_id = %s", (listing_id,))
                    cur.executemany(_INSERT_REVIEW, [
                        (listing_id, r["text"], r["rating"], r["review_date"])
                        for r in listing["reviews"]
                    ])
                    ids.append(listing_id)
        return ids
    finally:
        if own_conn:
            conn.close()


# --------------------------------------------------------------------------- #
# Command line: python scraper.py [--save] <url> [<url> ...]
# --------------------------------------------------------------------------- #
def _json_default(o):
    if isinstance(o, (date, Decimal)):
        return str(o)
    raise TypeError(type(o))


if __name__ == "__main__":
    args = sys.argv[1:]
    save = "--save" in args
    urls = [a for a in args if a != "--save"]
    if not urls:
        print("Usage: python scraper.py [--save] <url> [<url> ...]")
        print("  without --save: print the scraped listings as JSON")
        print("  with --save:    save them to the database in DATABASE_URL")
        sys.exit(1)

    failed = False
    for url in urls:
        try:
            result = scrape(url)
        except ScrapeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            failed = True
            continue
        if save:
            ids = save_listings(result)
            print(f"Saved {len(ids)} listing(s), "
                  f"{sum(len(l['reviews']) for l in result)} review(s) from {url}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False, default=_json_default))
            print(f"# {len(result)} listing(s) from {url}", file=sys.stderr)
    sys.exit(1 if failed else 0)