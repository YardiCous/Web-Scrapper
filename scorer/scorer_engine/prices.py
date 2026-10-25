"""
Where the scorer gets the other prices in a listing's cluster.

InMemoryPrices serves the demo and tests from loaded fixtures. DbPrices is
the target: it needs the normaliser to give `listings` a cluster_id and a
text listing key first.
"""

from typing import Iterable, Protocol

from .models import Listing


class ClusterPriceSource(Protocol):
    def others(self, cluster_id: str, listing_id: str) -> list[float]:
        """Prices of every other listing in the cluster."""


class InMemoryPrices:
    def __init__(self, listings: Iterable[Listing] = ()):
        self._clusters: dict[str, dict[str, float]] = {}
        for l in listings:
            self.add(l)

    def add(self, listing: Listing):
        self._clusters.setdefault(listing.cluster_id, {})[listing.listing_id] = listing.price

    def others(self, cluster_id, listing_id):
        cluster = self._clusters.get(cluster_id, {})
        return sorted(p for lid, p in cluster.items() if lid != listing_id)


class DbPrices:
    """TODO: SELECT price FROM listings WHERE cluster_id=%s AND listing_id<>%s"""

    def __init__(self, pool):
        self.pool = pool

    def others(self, cluster_id, listing_id):
        raise NotImplementedError("listings has no cluster_id yet (waiting on the normaliser)")
