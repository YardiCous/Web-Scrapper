"""
The user pastes ONE product URL and gets
back that listing plus the same product on the other platforms.
"""

import json
import sys

from normaliser.core.loader import read_json_any_encoding
from normaliser.core.paths import OUTPUT_DIR, REAL_DATA_PATHS
from normaliser.core.pipeline import normalise_and_match, rows_for_url

CARTLANE = "https://paegnium.github.io/dummysite/?product={}"
TAO = "https://paegnium.github.io/dummysite2/products/{}.html"
LAZORA = "https://paegnium.github.io/dummysite3/#product-{}"

# (name, sku on both sites, expected cluster median in SGD)
MATCHED = [
    ("Apple MacBook Pro 14", "78", 1788.74),
    ("Nike Air Jordan 1", "88", 145.12),
    ("Puma Future Rider", "90", 97.86),
    ("Table Lamp", "47", 53.99),
]
OUTPUT_FILE = OUTPUT_DIR / "single_url_result.json"


def ids(rows):
    return [r["listing_id"] for r in rows]


def main():
    ok_all = True

    def check(label, cond, detail=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'OK' if cond else 'FAIL':4}] {label} {detail}")

    raw = [r for path in REAL_DATA_PATHS for r in read_json_any_encoding(path)]
    rows = normalise_and_match(raw)          # the full pipeline, run once on the whole scrape

    print("=" * 60)
    print("PRODUCTS FOUND ON TWO PLATFORMS (try the URL from each side)")
    print("=" * 60)
    for name, sku, median in MATCHED:
        c_url, t_url = CARTLANE.format(sku), TAO.format(sku)
        from_c, from_t = rows_for_url(rows, c_url), rows_for_url(rows, t_url)
        check(f"{name}: Cartlane URL -> Cartlane first, then Tao Market",
              ids(from_c) == [f"Cartlane:{sku}", f"Tao Market:{sku}"], f"(got {ids(from_c)})")
        check(f"{name}: Tao Market URL -> Tao Market first, then Cartlane",
              ids(from_t) == [f"Tao Market:{sku}", f"Cartlane:{sku}"], f"(got {ids(from_t)})")
        check(f"{name}: both sides report the same cluster and median {median}",
              bool(from_c) and bool(from_t)
              and {r["cluster_id"] for r in from_c + from_t} == {f"Cartlane:{sku}"}
              and {r["cluster_price_median_sgd"] for r in from_c + from_t} == {median})

    print("\n" + "=" * 60)
    print("PRODUCTS FOUND ON ONE PLATFORM ONLY")
    print("=" * 60)
    singles = [
        ("Cartlane Lunch Box", CARTLANE.format("65"), ["Cartlane:65"]),
        ("Lazora backpack (URL ends in #product-1)", LAZORA.format("1"), ["Lazora:lazora-1"]),
        ("Tao Market AirPods (must NOT pull in AirPods Max)", TAO.format("100"), ["Tao Market:100"]),
        ("Tao Market AirPods Max", TAO.format("101"), ["Tao Market:101"]),
    ]
    for label, url, expected in singles:
        got = rows_for_url(rows, url)
        check(f"{label}: 1 row, cluster_size 1", ids(got) == expected and got[0]["cluster_size"] == 1, f"(got {ids(got)})")

    print("\n" + "=" * 60)
    print("URL HANDLING")
    print("=" * 60)
    url = CARTLANE.format("78")
    check("unknown URL -> []", rows_for_url(rows, CARTLANE.format("9999")) == [])
    check("empty string -> []", rows_for_url(rows, "") == [])
    check("spaces around the pasted URL are ignored", ids(rows_for_url(rows, f"  {url}  ")) == ids(rows_for_url(rows, url)))
    check("a trailing slash is ignored", ids(rows_for_url(rows, url + "/")) == ids(rows_for_url(rows, url)))
    urls = [r["product_url"] for r in rows]
    check("no two listings share a URL", len(set(urls)) == len(urls))

    print("\n" + "=" * 60)
    print("EVERY LISTING URL (all 32)")
    print("=" * 60)
    by_cluster = {}
    for r in rows:
        by_cluster.setdefault(r["cluster_id"], []).append(r["listing_id"])
    problems = []
    for r in raw:
        got = rows_for_url(rows, r["product_url"])
        if not got:
            problems.append((r["product_url"], "not found")); continue
        if got[0]["product_url"] != r["product_url"]:
            problems.append((r["product_url"], "pasted listing is not first"))
        if len({g["cluster_id"] for g in got}) != 1 or len(got) != got[0]["cluster_size"]:
            problems.append((r["product_url"], "rows are not exactly one cluster"))
        if sorted(ids(got)) != sorted(by_cluster[got[0]["cluster_id"]]):
            problems.append((r["product_url"], "cluster members differ from the full output"))
    check("each URL returns its listing first plus exactly its own cluster", not problems, f"({problems[:2]})" if problems else "")

    print("\n" + "=" * 60)
    print("WHY THE WHOLE SCRAPE IS NEEDED")
    print("=" * 60)
    cartlane_only = normalise_and_match([r for r in raw if r["source_platform"] == "Cartlane"])
    alone = rows_for_url(cartlane_only, CARTLANE.format("78"))
    check("scraping only Cartlane: the MacBook has no match (cluster_size 1)",
          len(alone) == 1 and alone[0]["cluster_size"] == 1, f"(got {ids(alone)})")

    print("\n" + "=" * 60)
    print("EXPORT")
    print("=" * 60)
    result = rows_for_url(rows, CARTLANE.format("78"))
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        check("result file reloads identical", json.load(f) == result)
    print(f"Wrote {len(result)} rows for {CARTLANE.format('78')} to {OUTPUT_FILE}")

    print("\n" + "=" * 60)
    print("RESULT:", "ALL CHECKS PASSED" if ok_all else "SOME CHECKS FAILED -- see [FAIL] above")
    print("=" * 60)
    return ok_all


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
