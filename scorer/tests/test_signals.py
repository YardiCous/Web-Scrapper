import math
from datetime import datetime, timedelta, timezone

import pytest

from scorer_engine import config, signals
from scorer_engine.sentiment import NEGATIVE, NEUTRAL, POSITIVE

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


# ---- price_dev --------------------------------------------------------------
def test_price_dev_needs_min_cluster_size():
    assert signals.price_dev(10, 100, cluster_size=2) is None


def test_price_dev_needs_a_median():
    assert signals.price_dev(10, None, cluster_size=5) is None
    assert signals.price_dev(10, 0, cluster_size=5) is None


def test_price_dev_dearer_than_median_is_zero():
    assert signals.price_dev(150, 100, cluster_size=3) == 0.0


def test_price_dev_far_below_median_saturates():
    assert signals.price_dev(20, 100, cluster_size=3) == 1.0
    assert signals.price_dev(65, 100, cluster_size=3) == pytest.approx(1.0)  # exactly 35% below


def test_price_dev_proportional_to_discount():
    # 10% below the median -> 0.10 / 0.35
    assert signals.price_dev(90, 100, cluster_size=3) == pytest.approx(0.10 / 0.35)


def test_price_dev_full_risk_discount_configurable(monkeypatch):
    monkeypatch.setattr(config, "PRICE_FULL_RISK_DISCOUNT", 0.5)
    assert signals.price_dev(75, 100, cluster_size=3) == pytest.approx(0.5)


# ---- seller -------------------------------------------------------------------
def test_seller_age():
    assert signals.seller_age(None) is None
    assert signals.seller_age(0) == 1.0
    assert signals.seller_age(180) == pytest.approx(math.exp(-1))
    assert signals.seller_age(-5) == 1.0  # clock skew clamps to "brand new"


def test_seller_volume():
    assert signals.seller_volume(None) is None
    assert signals.seller_volume(0) == 1.0
    assert signals.seller_volume(10_000) < signals.seller_volume(10) < 1.0


def test_official():
    assert signals.official(None) is None
    assert signals.official(True) == 1.0
    assert signals.official(False) == 0.0


@pytest.mark.parametrize("title", [
    "AirPods 1:1 copy", "Jordan AAA grade", "OEM factory", "mirror quality bag",
    "Super Copy watch", "supercopy", "高仿 包包", "Replica",
])
def test_title_kw_hits(title):
    assert signals.title_kw(title) == 1.0


@pytest.mark.parametrize("title", ["Apple AirPods Pro 2", "AAAA batteries", "OEMs welcome"])
def test_title_kw_misses(title):
    assert signals.title_kw(title) == 0.0


def test_title_kw_known_false_positive():
    # The agreed regex has no word boundary on "mirror"; worth a line in the report.
    assert signals.title_kw("Sony mirrorless camera") == 1.0


# ---- reviews ------------------------------------------------------------------
def test_dup_reviews_none_below_min():
    assert signals.dup_reviews(["this is a long enough review"] * 4) is None


def test_dup_reviews_ignores_short_texts():
    assert signals.dup_reviews(["Good"] * 10) is None


def test_dup_reviews_all_duplicates():
    assert signals.dup_reviews(["Amazing product exactly like the original!!"] * 6) == 1.0


def test_dup_reviews_all_distinct():
    texts = [
        "Battery life is excellent, lasts a full day.",
        "Screen is great but the cable is a bit short.",
        "Arrived well packed and the serial checked out.",
        "Delivery took longer than promised, product fine.",
        "Second one bought from this shop, still happy.",
    ]
    assert signals.dup_reviews(texts) == 0.0


def test_dup_reviews_partial():
    dup = "Best shoes ever, same as store, five stars!"
    texts = [dup, dup, dup,
             "Sole came off after a week of light use.",
             "Colour is darker than the photos suggest."]
    assert signals.dup_reviews(texts) == pytest.approx(3 / 5)


def test_burst_none_below_min():
    assert signals.burst([T0] * 9) is None


def test_burst_all_in_window():
    assert signals.burst([T0 + timedelta(hours=i) for i in range(10)]) == 1.0


def test_burst_spread_out():
    assert signals.burst([T0 + timedelta(days=5 * i) for i in range(10)]) == pytest.approx(0.1)


def test_burst_window_edge_inclusive():
    ts = [T0 + timedelta(hours=48 * i) for i in range(10)]  # each pair exactly 48 h apart
    assert signals.burst(ts) == pytest.approx(0.2)


def test_burst_ignores_missing_timestamps():
    assert signals.burst([None] * 20) is None


def test_neg_share():
    assert signals.neg_share(["a", "b"], [NEGATIVE, NEGATIVE]) is None
    texts = ["fine", "It is FAKE", "lovely", "Not original"]
    labels = [NEUTRAL, NEUTRAL, POSITIVE, POSITIVE]  # keyword hits count even if the model disagrees
    assert signals.neg_share(texts, labels) == 0.5


def test_mismatch():
    assert signals.mismatch([5, 5], [NEGATIVE, NEGATIVE]) is None
    ratings = [5, 4, 1, 5]
    labels = [NEGATIVE, NEGATIVE, NEGATIVE, POSITIVE]
    assert signals.mismatch(ratings, labels) == 0.5


# ---- compute ------------------------------------------------------------------
def test_compute_missing_data_is_none_not_zero(make_listing):
    l = make_listing(cluster_size=1, cluster_price_median_sgd=None, seller_age_days=None)
    sig, _ = signals.compute(l)
    assert sig["price_dev"] is None
    assert sig["seller_age"] is None
    assert sig["seller_volume"] is None  # normaliser doesn't send sales
    assert sig["official"] is None       # ...or an official-store flag
    assert sig["title_kw"] == 0.0
    assert set(sig) == set(config.WEIGHTS)


def test_compute_facts(make_listing):
    l = make_listing(price_sgd=50, cluster_price_median_sgd=100, seller_age_days=21)
    sig, facts = signals.compute(l)
    assert facts["age_days"] == 21
    assert facts["pct_below_median"] == pytest.approx(50)
    assert sig["price_dev"] == 1.0


def test_compute_normaliser_sample(make_listing):
    # 449 vs median 445.5: dearer than median; 5.6-year-old shop; one positive review.
    sig, _ = signals.compute(make_listing())
    assert sig["price_dev"] == 0.0
    assert sig["seller_age"] < 0.001
    assert sig["dup_reviews"] is sig["burst"] is sig["neg_share"] is None
