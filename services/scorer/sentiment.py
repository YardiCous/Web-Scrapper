"""
Review sentiment behind a small protocol, so the v1 keyword classifier can be
swapped for the multilingual transformer (cardiffnlp/twitter-xlm-roberta-base-sentiment,
ideally as its own Knative service) without touching signals.py.
"""

from typing import Optional, Protocol, Sequence

from . import config

NEGATIVE, NEUTRAL, POSITIVE = "negative", "neutral", "positive"


class Sentiment(Protocol):
    def classify(self, texts: Sequence[Optional[str]]) -> list[str]:
        """Return one of negative/neutral/positive per text, in order."""


class KeywordSentiment:
    """
    v1 stand-in: negative if the text matches the counterfeit/complaint regex
    or a small list of generic complaint phrases; positive on obvious praise.
    """

    _NEG_EXTRA = (
        "waste of money", "would not recommend", "not recommend", "poor quality",
        "broke", "disappointed", "terrible", "awful", "bad quality", "refund",
    )
    _POS = (
        "excellent", "great", "happy", "satisfied", "impressed", "love",
        "recommend", "perfect", "good",
    )

    def classify(self, texts):
        out = []
        for t in texts:
            low = (t or "").lower()
            if config.NEG_KW_RE.search(low) or any(p in low for p in self._NEG_EXTRA):
                out.append(NEGATIVE)
            elif any(p in low for p in self._POS):
                out.append(POSITIVE)
            else:
                out.append(NEUTRAL)
        return out


class HttpSentiment:
    """Client for the future `sentiment` Knative service (not deployed yet)."""

    def __init__(self, url: str):
        self.url = url

    def classify(self, texts):
        raise NotImplementedError("sentiment service not deployed yet; use KeywordSentiment")


default = KeywordSentiment()
