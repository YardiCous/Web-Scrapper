"""
Clustering.

Takes the verified pairs from match.py and merges them into product
clusters using union-find.

Every listing ends up in exactly one cluster, including listings that
matched nothing, which simply become a cluster of size 1.
"""

import statistics

from normaliser.core.match import listing_id


class UnionFind:
    # Standard union-find with path compression + union by rank.

    def __init__(self, ids):
        self.parent = {i: i for i in ids}
        self.rank = {i: 0 for i in ids}

    def find(self, x):
        # Path compression: point x directly at its grandparent each
        # time, which keeps future find() calls fast.
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return  # already in the same cluster
        if self.rank[root_a] < self.rank[root_b]:
            root_a, root_b = root_b, root_a
        self.parent[root_b] = root_a
        if self.rank[root_a] == self.rank[root_b]:
            self.rank[root_a] += 1


def build_clusters(listings, matches):
    """
    listings:  list of enriched listing dicts
    matches:   list of (id_a, id_b, similarity) from match.find_matches()

    Returns a list of cluster dicts, each with its member listings and
    a few summary fields.
    """
    ids = [listing_id(l) for l in listings]
    uf = UnionFind(ids)
    for id_a, id_b, _sim in matches:
        uf.union(id_a, id_b)

    by_id = {listing_id(l): l for l in listings}
    groups = {}
    for lid in ids:
        root = uf.find(lid)
        groups.setdefault(root, []).append(by_id[lid])

    clusters = []
    for root_id, members in groups.items():
        clusters.append(_summarise_cluster(root_id, members))

    # Biggest clusters first
    clusters.sort(key=lambda c: -c["num_listings"])
    return clusters


def _summarise_cluster(cluster_id, members):
    prices = [m["price_sgd"] for m in members]
    # The listing with the most reviews is a reasonable stand-in for "most representative" title
    canonical = max(members, key=lambda m: m["review_count"])
    brands = [m["brand"] for m in members if m["brand"]]

    return {
        "cluster_id": cluster_id,
        "brand": brands[0] if brands else None,
        "canonical_title": canonical["title"],
        "num_listings": len(members),
        "price_min_sgd": min(prices),
        "price_max_sgd": max(prices),
        "price_median_sgd": round(statistics.median(prices), 2),
        "platforms": sorted({m["source_platform"] for m in members}),
        "listings": members,
    }


if __name__ == "__main__":
    from core.loader import load_real_listings
    from core.paths import REAL_DATA_PATHS as DATA_PATHS
    from core.clean import clean_all
    from core.extract import extract_all
    from core.match import find_matches

    listings = extract_all(clean_all(load_real_listings(DATA_PATHS)))
    matches = find_matches(listings)
    clusters = build_clusters(listings, matches)

    multi = [c for c in clusters if c["num_listings"] > 1]
    singles = [c for c in clusters if c["num_listings"] == 1]
    print(f"{len(clusters)} clusters total "
          f"({len(multi)} multi-listing, {len(singles)} singletons)\n")

    for c in multi:
        print(f"[{c['brand']}] {c['canonical_title']}")
        print(f"  {c['num_listings']} listings on {c['platforms']}, "
              f"price SGD {c['price_min_sgd']}-{c['price_max_sgd']} "
              f"(median {c['price_median_sgd']})")
