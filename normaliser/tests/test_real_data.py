"""
Test: does the pipeline produce the correct result on the REAL scraped
data (cartlane.json, Tao_Market.json, Lazora.json)?

Ground truth was found by manually reading all 32 titles across the 3
files. There are exactly 4 true cross-platform matches (all between
Cartlane and Tao Market -- Lazora's catalogue doesn't overlap with
either):

  - "Table Lamp"                                  (exact title match)
  - "Puma Future Rider Trainers"                   (exact title match)
  - "Nike Air Jordan 1 Red And Black"               (exact title match)
  - "Apple MacBook Pro 14 Inch Space Grey"
      <-> "Apple MacBook Pro 14-inch"               (near match)

Expected result: 4 matched clusters (size 2 each) + 24 singletons
                = 28 clusters total, from 32 listings.

Run from the normaliser/ folder:  python -m tests.test_real_data
Run this after any change to clean.py/extract.py/match.py/cluster.py
to make sure nothing regressed.
"""

from normaliser.core.loader import load_real_listings
from normaliser.core.clean import clean_all
from normaliser.core.extract import extract_all
from normaliser.core.match import find_matches, listing_id
from normaliser.core.cluster import build_clusters
from normaliser.core.paths import REAL_DATA_PATHS


# Each expected match named by a keyword that appears in its canonical title.
EXPECTED_MATCHES = ["table lamp", "puma", "nike", "macbook"]
EXPECTED_TOTAL_LISTINGS = 32
EXPECTED_MULTI_CLUSTERS = 4
EXPECTED_SINGLETONS = 24


def run_pipeline():
    raw = load_real_listings(REAL_DATA_PATHS)
    cleaned = clean_all(raw)
    enriched = extract_all(cleaned)
    matches = find_matches(enriched)
    clusters = build_clusters(enriched, matches)
    return raw, clusters


def check(label, actual, expected):
    ok = actual == expected
    print(f"[{'OK' if ok else 'FAIL':4}] {label}: got {actual}, expected {expected}")
    return ok


def main():
    raw, clusters = run_pipeline()
    multi = [c for c in clusters if c["num_listings"] > 1]
    singles = [c for c in clusters if c["num_listings"] == 1]

    print("=" * 60)
    print("BASIC COUNTS")
    print("=" * 60)
    all_ok = True
    all_ok &= check("total listings loaded", len(raw), EXPECTED_TOTAL_LISTINGS)
    all_ok &= check("multi-listing clusters", len(multi), EXPECTED_MULTI_CLUSTERS)
    all_ok &= check("singleton clusters", len(singles), EXPECTED_SINGLETONS)
    all_ok &= check("total clusters", len(clusters), EXPECTED_MULTI_CLUSTERS + EXPECTED_SINGLETONS)

    print("\n" + "=" * 60)
    print("EXPECTED MATCHES -- did each one actually form?")
    print("=" * 60)
    found_titles = [c["canonical_title"].lower() for c in multi]
    for keyword in EXPECTED_MATCHES:
        matched = [t for t in found_titles if keyword in t]
        ok = len(matched) == 1
        all_ok &= ok
        print(f"[{'OK' if ok else 'FAIL':4}] '{keyword}' -> "
              f"{matched if matched else 'NOT FOUND as a multi-listing cluster'}")

    print("\n" + "=" * 60)
    print("UNEXPECTED MATCHES -- any cluster we did NOT predict?")
    print("=" * 60)
    unexpected = [c for c in multi
                  if not any(k in c["canonical_title"].lower() for k in EXPECTED_MATCHES)]
    if unexpected:
        all_ok = False
        for c in unexpected:
            print(f"[FAIL] Unexpected match: '{c['canonical_title']}' "
                  f"({c['num_listings']} listings, {c['platforms']})")
    else:
        print("[OK  ] No unexpected matches.")

    print("\n" + "=" * 60)
    print("ALL MATCHED CLUSTERS (detail)")
    print("=" * 60)
    for c in multi:
        print(f"\n[{c['brand']}] {c['canonical_title']}")
        print(f"  platforms={c['platforms']}  "
              f"price SGD {c['price_min_sgd']}-{c['price_max_sgd']} (median {c['price_median_sgd']})")
        for m in c["listings"]:
            print(f"    - {m['source_platform']:12} {m['price_sgd']:>8.2f} SGD  '{m['title']}'")

    print("\n" + "=" * 60)
    print("RESULT:", "ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED -- see [FAIL] above")
    print("=" * 60)


if __name__ == "__main__":
    main()
