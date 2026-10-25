"""
v1 combiner: logistic function over the available signals with hand-set
weights, plus coverage, per-signal contributions and human-readable reasons.
"""

import math
from dataclasses import dataclass, field

from . import config


@dataclass
class ScoreResult:
    score: float
    band: str
    coverage: float
    contributions: dict
    reasons: list
    signals: dict = field(default_factory=dict)
    model_version: str = config.MODEL_VERSION


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def band(score):
    if score >= config.BAND_HIGH:
        return "high"
    if score >= config.BAND_MEDIUM:
        return "medium"
    return "low"


def _reason(key, value, facts):
    """Templated, human-readable explanation for one signal."""
    if key == "price_dev":
        pct = facts.get("pct_below_median")
        if pct is not None:
            return f"Price {pct:.0f}% below the cross-platform median"
        return "Price well below the cross-platform median"
    if key == "seller_age":
        days = facts.get("age_days")
        return f"Shop is only {days} days old" if days is not None else "Shop is very new"
    if key == "seller_volume":
        sales = facts.get("sales")
        return f"Seller has only {sales} recorded sales" if sales is not None else "Seller has few sales"
    if key == "title_kw":
        kw = facts.get("title_keyword")
        return f"Title contains the counterfeit keyword “{kw}”" if kw else "Title contains counterfeit keywords"
    if key == "dup_reviews":
        return f"{value:.0%} of reviews are near-duplicates of each other"
    if key == "burst":
        return f"{value:.0%} of reviews were posted within {config.BURST_WINDOW_HOURS:.0f} hours"
    if key == "neg_share":
        return f"{value:.0%} of reviews are negative or mention fakes"
    if key == "mismatch":
        return f"{value:.0%} of reviews give 4–5 stars but complain in the text"
    return key


def combine(signals: dict, facts: dict | None = None) -> ScoreResult:
    facts = facts or {}
    available = {k: v for k, v in signals.items() if v is not None and k in config.WEIGHTS}
    contributions = {k: round(config.WEIGHTS[k] * v, 4) for k, v in available.items()}
    score = _sigmoid(config.BIAS + sum(contributions.values()))
    coverage = len(available) / len(config.WEIGHTS)

    top = sorted(
        (k for k, c in contributions.items() if c > config.REASON_MIN_CONTRIBUTION),
        key=lambda k: contributions[k], reverse=True,
    )[:config.MAX_REASONS]
    reasons = [
        {"signal": k, "contribution": contributions[k], "text": _reason(k, available[k], facts)}
        for k in top
    ]
    return ScoreResult(
        score=round(score, 4), band=band(score), coverage=round(coverage, 4),
        contributions=contributions, reasons=reasons,
        signals={k: (None if v is None else round(v, 4)) for k, v in signals.items()},
    )
