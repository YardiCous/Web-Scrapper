"""
Score fixture files offline, or save the scores to PostgreSQL.

    python -m scorer_engine.cli fixtures/raw/*.json fixtures/synthetic_suspects.json
    python -m scorer_engine.cli --save fixtures/raw/*.json fixtures/synthetic_suspects.json
    python -m scorer_engine.cli --json ...          # full results as JSON
"""

import argparse
import glob
import json
import os
import sys

from fixtures import adapter

from . import signals
from .combiner import combine
from .prices import InMemoryPrices


def score_all(listings):
    prices = InMemoryPrices(listings)
    out = []
    for l in listings:
        others = prices.others(l.cluster_id, l.listing_id)
        sig, facts = signals.compute(l, others)
        out.append((l, others, combine(sig, facts)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--save", action="store_true", help="upsert into risk_scores (DATABASE_URL)")
    ap.add_argument("--json", action="store_true", help="print full results as JSON")
    args = ap.parse_args(argv)

    paths = [p for pattern in args.files for p in (glob.glob(pattern) or [pattern])]
    listings = [l for p in paths for l in adapter.load(p)]
    results = score_all(listings)

    if args.json:
        print(json.dumps([{"listing_id": l.listing_id, "cluster_id": l.cluster_id, **vars(r)}
                          for l, _, r in results], indent=2, ensure_ascii=False))
    else:
        for l, _, r in sorted(results, key=lambda x: (x[0].cluster_id, -x[2].score)):
            reasons = "; ".join(x["text"] for x in r.reasons) or "-"
            print(f"{l.cluster_id:<18} {l.listing_id:<24} {l.price:>8.2f}  "
                  f"{r.score:.2f} {r.band:<6} cov={r.coverage:.2f}  {reasons}")

    if args.save:
        import psycopg
        from . import store
        changed = 0
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            for l, others, r in results:
                changed += store.upsert(conn, l, r, store.input_hash(l, others))
        print(f"saved {len(results)} score(s): {changed} inserted/updated, "
              f"{len(results) - changed} unchanged", file=sys.stderr)


if __name__ == "__main__":
    main()
