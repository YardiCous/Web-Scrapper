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
def price_dev(
    price: float, cluster_median: Optional[float], cluster_size: int
) -> Optional[float]:
    """
    How far *below* the cluster median this price is, as a share of the median:
    risk = clip(discount / PRICE_FULL_RISK_DISCOUNT), so with the default 0.35
    a listing 35% or more below the median scores 1.0.
    Dearer-than-median listings score 0.

    The normaliser sends the cluster median (this listing included), not the
    individual prices, so a robust z-score (MAD) can't be computed here.
    """
    if cluster_size < config.MIN_CLUSTER_SIZE or not cluster_median or cluster_median <= 0:
        return None
    discount = (cluster_median - price) / cluster_median
    return _clip(discount / config.PRICE_FULL_RISK_DISCOUNT)


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
def compute(listing: Listing, sentiment: Sentiment = default_sentiment):
    """
    Return (signals, facts). Everything needed is in the message itself,
    including the cluster's median price. `facts` holds the raw numbers the
    reason templates quote.
    """
    texts = [r.text for r in listing.reviews]
    labels = sentiment.classify(texts) if texts else []
    med = listing.cluster_price_median_sgd

    signals = {
        "price_dev": price_dev(listing.price_sgd, med, listing.cluster_size),
        "seller_age": seller_age(listing.seller_age_days),
        "seller_volume": seller_volume(listing.seller_sales),
        "official": official(listing.seller_is_official),
        "title_kw": title_kw(listing.title),
        "dup_reviews": dup_reviews(texts),
        "burst": burst([r.date for r in listing.reviews]),
        "neg_share": neg_share(texts, labels),
        "mismatch": mismatch([r.rating for r in listing.reviews], labels),
    }

    facts = {"age_days": listing.seller_age_days, "sales": listing.seller_sales}
    if med:
        facts["cluster_median"] = med
        facts["pct_below_median"] = (med - listing.price_sgd) / med * 100
    kw = config.TITLE_KW_RE.search(listing.title or "")
    facts["title_keyword"] = kw.group(0) if kw else None
    return signals, facts
