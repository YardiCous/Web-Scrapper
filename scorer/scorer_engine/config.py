"""
This is where the scoring parameters are defined.  They are used in scorer/scorer_engine/combiner.py and scorer/scorer_engine/signals.py.

Numeric values can be overridden with environment variables, e.g.
SCORER_W_PRICE_DEV=3.0, SCORER_BIAS=-1.5, SCORER_MIN_REVIEWS_DUP=4.
"""

import os
import re

# Used when changing default values to using environment variables
def _num(name, default, cast=float):
    raw = os.environ.get(name)
    return default if raw in (None, "") else cast(raw)

MODEL_VERSION = os.environ.get("SCORER_MODEL_VERSION", "v1-handweights")

# --- combiner ---------------------------------------------------------------
_DEFAULT_WEIGHTS = {
    "price_dev": 2.5, "title_kw": 2.0, "neg_share": 1.8, "dup_reviews": 1.5,
    "seller_age": 1.2, "mismatch": 1.0, "burst": 0.8, "seller_volume": 0.6,
    "official": -2.5,
}
WEIGHTS = {k: _num(f"SCORER_W_{k.upper()}", v) for k, v in _DEFAULT_WEIGHTS.items()}
BIAS = _num("SCORER_BIAS", -2.0)

BAND_HIGH = _num("SCORER_BAND_HIGH", 0.7)
BAND_MEDIUM = _num("SCORER_BAND_MEDIUM", 0.4)
REASON_MIN_CONTRIBUTION = _num("SCORER_REASON_MIN", 0.3)
MAX_REASONS = _num("SCORER_MAX_REASONS", 3, int)

# --- minimum data per signal -------------------------------------------------
MIN_CLUSTER_PRICES = _num("SCORER_MIN_CLUSTER_PRICES", 3, int)
MIN_REVIEWS_DUP = _num("SCORER_MIN_REVIEWS_DUP", 5, int)
MIN_REVIEWS_BURST = _num("SCORER_MIN_REVIEWS_BURST", 10, int)
MIN_REVIEWS_NEG = _num("SCORER_MIN_REVIEWS_NEG", 3, int)
MIN_RATED_MISMATCH = _num("SCORER_MIN_RATED_MISMATCH", 3, int)

# --- signal parameters -------------------------------------------------------
PRICE_Z_CAP = _num("SCORER_PRICE_Z_CAP", 3.5)
PRICE_MAD_FLOOR = _num("SCORER_PRICE_MAD_FLOOR", 0.05)  # fraction of the median; 0 disables
SELLER_AGE_SCALE_DAYS = _num("SCORER_SELLER_AGE_SCALE", 180.0)
BURST_WINDOW_HOURS = _num("SCORER_BURST_WINDOW_HOURS", 48.0)

DUP_MIN_LEN = _num("SCORER_DUP_MIN_LEN", 15, int)
DUP_SHINGLE = _num("SCORER_DUP_SHINGLE", 5, int)
DUP_PERMS = _num("SCORER_DUP_PERMS", 64, int)
DUP_THRESHOLD = _num("SCORER_DUP_THRESHOLD", 0.8)

TITLE_KW_RE = re.compile(
    r"replica|1:1|\bAAA\b|mirror|\bOEM\b|高仿|复刻|原单|super ?copy", re.IGNORECASE
)
NEG_KW_RE = re.compile(
    r"fake|not original|counterfeit|假货|假的|palsu|tiruan", re.IGNORECASE
)

# --- stub adapter (delete with fixtures/adapter.py once the normaliser exists)
SGD_TO_USD = _num("SCORER_SGD_TO_USD", 0.77)
