"""
Heuristic counterfeit-risk signals.

Each signal is a pure function returning a float in [0, 1] (higher = riskier)
or None when there is not enough data to compute it. None is deliberately
different from 0: the combiner skips missing signals instead of treating them
as evidence of a genuine listing.
"""

import math
import re
from datetime import timedelta
from statistics import median
from typing import Optional, Sequence

from datasketch import MinHash, MinHashLSH

from . import config
from .models import Listing
from .sentiment import NEGATIVE, Sentiment, default as default_sentiment

SIGNALS = tuple(config.WEIGHTS)


def _clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


# --------------------------------------------------------------------------- #
# Price and seller
# --------------------------------------------------------------------------- #
def price_dev(price: float, others: Sequence[float]) -> Optional[float]:
    """
    Robust z-score of how far *below* the cluster median this price is,
    using the median absolute deviation of the other listings' prices.
    z = 0.6745 * (median - price) / MAD; risk = clip(z / 3.5).
    MAD is floored at PRICE_MAD_FLOOR * median: with a handful of prices, two
    near-identical ones make MAD tiny and a 2% discount look extreme.
    With MAD = 0 (floor disabled, identical prices) z falls back to
    (median - price) / median * 10. Dearer-than-median listings score 0.
    """
    if len(others) < config.MIN_CLUSTER_PRICES:
        return None
    med = median(others)
    if med <= 0:
        return None
    mad = max(median(abs(p - med) for p in others), config.PRICE_MAD_FLOOR * med)
    if mad > 0:
        z = 0.6745 * (med - price) / mad
    else:
        z = (med - price) / med * 10
    return _clip(z / config.PRICE_Z_CAP)


def seller_age(age_days: Optional[int]) -> Optional[float]:
    if age_days is None:
        return None
    return math.exp(-max(age_days, 0) / config.SELLER_AGE_SCALE_DAYS)


def seller_volume(sales: Optional[int]) -> Optional[float]:
    if sales is None:
        return None
    return 1.0 / (1.0 + math.log1p(sales))


def official(is_official: Optional[bool]) -> Optional[float]:
    if is_official is None:
        return None
    return 1.0 if is_official else 0.0


def title_kw(title: str) -> float:
    return 1.0 if config.TITLE_KW_RE.search(title or "") else 0.0


# --------------------------------------------------------------------------- #
# Reviews
# --------------------------------------------------------------------------- #
def _shingles(text, k):
    text = re.sub(r"\s+", " ", text.lower()).strip()
    if len(text) <= k:
        return {text}
    return {text[i : i + k] for i in range(len(text) - k + 1)}


def dup_reviews(texts: Sequence[Optional[str]]) -> Optional[float]:
    """
    Fraction of reviews (of at least DUP_MIN_LEN chars) that have a
    near-duplicate among the others: char shingles -> MinHash -> LSH at
    DUP_THRESHOLD estimated Jaccard similarity.
    """
    eligible = [t.strip() for t in texts if t and len(t.strip()) >= config.DUP_MIN_LEN]
    if len(eligible) < config.MIN_REVIEWS_DUP:
        return None
    lsh = MinHashLSH(threshold=config.DUP_THRESHOLD, num_perm=config.DUP_PERMS)
    hashes = []
    for i, text in enumerate(eligible):
        m = MinHash(num_perm=config.DUP_PERMS, seed=1)
        for s in _shingles(text, config.DUP_SHINGLE):
            m.update(s.encode("utf-8"))
        lsh.insert(i, m)
        hashes.append(m)
    duplicated = sum(
        1 for i, m in enumerate(hashes) if any(j != i for j in lsh.query(m))
    )
    return duplicated / len(eligible)


def burst(timestamps: Sequence) -> Optional[float]:
    """Largest share of reviews posted inside any BURST_WINDOW_HOURS window."""
    ts = sorted(t for t in timestamps if t is not None)
    if len(ts) < config.MIN_REVIEWS_BURST:
        return None
    window = timedelta(hours=config.BURST_WINDOW_HOURS)
    best, lo = 0, 0
    for hi in range(len(ts)):
        while ts[hi] - ts[lo] > window:
            lo += 1
        best = max(best, hi - lo + 1)
    return best / len(ts)


def neg_share(texts: Sequence[Optional[str]], labels: Sequence[str]) -> Optional[float]:
    """Share of reviews that read as negative or mention fakes/counterfeits."""
    pairs = [(t, l) for t, l in zip(texts, labels) if t]
    if len(pairs) < config.MIN_REVIEWS_NEG:
        return None
    neg = sum(1 for t, l in pairs if l == NEGATIVE or config.NEG_KW_RE.search(t))
    return neg / len(pairs)


def mismatch(
    ratings: Sequence[Optional[int]], labels: Sequence[str]
) -> Optional[float]:
    """Share of rated reviews that give 4-5 stars while the text is negative."""
    pairs = [(r, l) for r, l in zip(ratings, labels) if r is not None]
    if len(pairs) < config.MIN_RATED_MISMATCH:
        return None
    return sum(1 for r, l in pairs if r >= 4 and l == NEGATIVE) / len(pairs)


# --------------------------------------------------------------------------- #
# All signals for one listing
# --------------------------------------------------------------------------- #
def compute(
    listing: Listing,
    cluster_prices: Sequence[float],
    sentiment: Sentiment = default_sentiment,
):
    """
    Return (signals, facts). `cluster_prices` are the *other* listings' prices
    in the same cluster. `facts` holds the raw numbers the reason templates quote.
    """
    texts = [r.text for r in listing.reviews]
    labels = sentiment.classify(texts) if texts else []

    age_days = None
    if listing.seller.created_at is not None:
        age_days = (listing.fetched_at.date() - listing.seller.created_at).days

    signals = {
        "price_dev": price_dev(listing.price, cluster_prices),
        "seller_age": seller_age(age_days),
        "seller_volume": seller_volume(listing.seller.sales),
        "official": official(listing.seller.is_official),
        "title_kw": title_kw(listing.title),
        "dup_reviews": dup_reviews(texts),
        "burst": burst([r.ts for r in listing.reviews]),
        "neg_share": neg_share(texts, labels),
        "mismatch": mismatch([r.rating for r in listing.reviews], labels),
    }

    facts = {"age_days": age_days, "sales": listing.seller.sales}
    if cluster_prices:
        med = median(cluster_prices)
        facts["cluster_median"] = med
        facts["pct_below_median"] = (med - listing.price) / med * 100 if med else None
    kw = config.TITLE_KW_RE.search(listing.title or "")
    facts["title_keyword"] = kw.group(0) if kw else None
    return signals, facts
