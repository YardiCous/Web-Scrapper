"""
Test + export: runs the whole pipeline on the sample data, checks that the
output meets the contract the scorer relies on, and writes the result to
outputs/scorer_input.json.

Run from the project folder:   python -m tests.test_export_output

What it checks
  - one row per input listing, unique listing ids
  - every row has EXACTLY the agreed fields, with the right types
  - every review has text, rating and review_date
  - cluster fields are consistent: size, platforms, min/max/median recomputed
    from the member rows, same values on every row of a cluster,
    cluster_id = smallest listing id in the cluster
  - cluster counts match the matching test (4 multi, 24 singletons, 28 total)
  - the file written to disk loads back identical (valid, UTF-8 JSON)

If someone changes the output schema, this test fails. That is the point:
the scorer and the Kafka code depend on these field names.
"""

import json
import statistics
import sys

from normaliser.core.loader import read_json_any_encoding
from normaliser.core.paths import OUTPUT_DIR, REAL_DATA_PATHS
from normaliser.core.pipeline import normalise_and_match

NUM = (int, float)
EXPECTED_FIELDS = {
    "cluster_id": str,
    "cluster_size": int,
    "cluster_platforms": list,
    "cluster_price_median_sgd": NUM,
    "cluster_price_min_sgd": NUM,
    "cluster_price_max_sgd": NUM,
    "listing_id": str,
    "source_platform": str,
    "source_listing_id": str,
    "title": str,
    "brand": (str, type(None)),      # None when no known brand is found
    "price_sgd": NUM,
    "seller_id": str,
    "seller_name": str,
    "seller_age_days": int,
    "selling_since": str,
    "rating": NUM,
    "review_count": int,
    "reviews": list,
    "product_url": str,
}
CLUSTER_FIELDS = ["cluster_id", "cluster_size", "cluster_platforms", "cluster_price_median_sgd",
                  "cluster_price_min_sgd", "cluster_price_max_sgd"]

# Same ground truth as tests/test_real_data.py. Update if the sample data changes.
EXPECTED_MULTI = 4
EXPECTED_SINGLETONS = 24

OUTPUT_FILE = OUTPUT_DIR / "scorer_input.json"


def main():
    ok_all = True

    def check(label, cond, detail=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'OK' if cond else 'FAIL':4}] {label} {detail}")

    def finish():
        print("\n" + "=" * 60)
        print("RESULT:", "ALL CHECKS PASSED" if ok_all else "SOME CHECKS FAILED -- see [FAIL] above")
        print("=" * 60)
        return ok_all

    raw = [r for path in REAL_DATA_PATHS for r in read_json_any_encoding(path)]
    rows = normalise_and_match(raw)

    print("=" * 60)
    print("ROWS")
    print("=" * 60)
    check("one row per input listing", len(rows) == len(raw), f"(rows {len(rows)}, input {len(raw)})")
    ids = [r.get("listing_id") for r in rows]
    check("listing ids are unique", len(set(ids)) == len(ids))

    wrong_fields = [r.get("listing_id") for r in rows if set(r) != set(EXPECTED_FIELDS)]
    check("every row has exactly the agreed fields", not wrong_fields,
          f"(bad rows: {wrong_fields[:3]})" if wrong_fields else "")

    type_problems = []
    for r in rows:
        for name, typ in EXPECTED_FIELDS.items():
            if name in r and not isinstance(r[name], typ):
                type_problems.append((r.get("listing_id"), name, type(r[name]).__name__))
    check("every field has the right type", not type_problems, f"(first problems: {type_problems[:3]})" if type_problems else "")

    if wrong_fields or type_problems:
        print("\nThe row structure is wrong, so the remaining checks are skipped.")
        return finish()

    bad_reviews = [r["listing_id"] for r in rows
                   if not all({"text", "rating", "review_date"} <= set(rv) for rv in r["reviews"])]
    check("every review has text, rating, review_date", not bad_reviews, f"({bad_reviews[:3]})" if bad_reviews else "")
    check("all prices are positive", all(r["price_sgd"] > 0 for r in rows))

    print("\n" + "=" * 60)
    print("CLUSTERS")
    print("=" * 60)
    groups = {}
    for r in rows:
        groups.setdefault(r["cluster_id"], []).append(r)

    problems = []
    for cid, members in groups.items():
        prices = [m["price_sgd"] for m in members]
        first = members[0]
        if any({k: m[k] for k in CLUSTER_FIELDS} != {k: first[k] for k in CLUSTER_FIELDS} for m in members):
            problems.append((cid, "cluster fields differ between rows"))
        if first["cluster_size"] != len(members):
            problems.append((cid, "cluster_size wrong"))
        if first["cluster_platforms"] != sorted({m["source_platform"] for m in members}):
            problems.append((cid, "cluster_platforms wrong"))
        if first["cluster_price_min_sgd"] != min(prices) or first["cluster_price_max_sgd"] != max(prices):
            problems.append((cid, "min/max wrong"))
        if first["cluster_price_median_sgd"] != round(statistics.median(prices), 2):
            problems.append((cid, "median wrong"))
        if cid != min(m["listing_id"] for m in members):
            problems.append((cid, "cluster_id is not the smallest listing id"))
    check("cluster summaries match their member rows", not problems, f"({problems[:3]})" if problems else "")

    multi = [g for g in groups.values() if len(g) > 1]
    singles = [g for g in groups.values() if len(g) == 1]
    check("multi-listing clusters", len(multi) == EXPECTED_MULTI, f"(got {len(multi)}, expected {EXPECTED_MULTI})")
    check("singleton clusters", len(singles) == EXPECTED_SINGLETONS, f"(got {len(singles)}, expected {EXPECTED_SINGLETONS})")

    print("\n" + "=" * 60)
    print("EXPORT")
    print("=" * 60)
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        reloaded = json.load(f)
    check("file reloads identical (valid UTF-8 JSON)", reloaded == rows)
    print(f"Wrote {len(rows)} rows in {len(groups)} clusters to {OUTPUT_FILE}")

    return finish()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
