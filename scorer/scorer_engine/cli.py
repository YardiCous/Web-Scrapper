"""
Score files of normaliser output offline, or save the scores to PostgreSQL.
Each file holds one listing object or a list of them.

    python -m scorer_engine.cli fixtures/*.json
    python -m scorer_engine.cli --save fixtures/*.json
    python -m scorer_engine.cli --json ...          # full results as JSON
"""

import argparse
import glob
import json
import os
import sys
from pathlib import Path

from . import signals
from .combiner import combine
from .models import Listing


def load(paths):
    """Read normaliser-output files (a path or a list of paths) as Listings."""
    if isinstance(paths, (str, Path)):
        paths = [paths]
    listings = []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        listings += [Listing.model_validate(x) for x in items]
    return listings


def score_all(listings):
    out = []
    for l in listings:
        sig, facts = signals.compute(l)
        out.append((l, combine(sig, facts)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--save", action="store_true", help="upsert into risk_scores (DATABASE_URL)")
    ap.add_argument("--json", action="store_true", help="print full results as JSON")
    args = ap.parse_args(argv)

    paths = [p for pattern in args.files for p in (glob.glob(pattern) or [pattern])]
    results = score_all(load(paths))

    if args.json:
        print(json.dumps([{"listing_id": l.listing_id, "cluster_id": l.cluster_id, **vars(r)}
                          for l, r in results], indent=2, ensure_ascii=False))
    else:
        for l, r in sorted(results, key=lambda x: (x[0].cluster_id, -x[1].score)):
            reasons = "; ".join(x["text"] for x in r.reasons) or "-"
            print(f"{l.cluster_id:<18} {l.listing_id:<24} {l.price_sgd:>8.2f}  "
                  f"{r.score:.2f} {r.band:<6} cov={r.coverage:.2f}  {reasons}")

    if args.save:
        import psycopg
        from . import store
        changed = 0
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            for l, r in results:
                changed += store.upsert(conn, l, r, store.input_hash(l))
        print(f"saved {len(results)} score(s): {changed} inserted/updated, "
              f"{len(results) - changed} unchanged", file=sys.stderr)


if __name__ == "__main__":
    main()
