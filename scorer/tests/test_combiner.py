import math

import pytest

from scorer_engine import config
from scorer_engine.combiner import band, combine


def _sig(x):
    return 1 / (1 + math.exp(-x))


def test_no_signals_gives_bias_only():
    r = combine({k: None for k in config.WEIGHTS})
    assert r.score == pytest.approx(_sig(config.BIAS), abs=1e-4)
    assert r.coverage == 0.0
    assert r.reasons == []


def test_missing_is_not_zero():
    # A missing signal is skipped; it shows up only as lower coverage.
    a = combine({"price_dev": 1.0, "seller_age": None})
    b = combine({"price_dev": 1.0, "seller_age": 0.0})
    assert a.score == b.score
    assert a.coverage < b.coverage
    assert "seller_age" not in a.contributions and b.contributions["seller_age"] == 0.0


def test_score_formula_and_contributions():
    r = combine({"price_dev": 1.0, "title_kw": 1.0, "official": 0.0})
    assert r.contributions == {"price_dev": 2.5, "title_kw": 2.0, "official": 0.0}
    assert r.score == pytest.approx(_sig(config.BIAS + 4.5), abs=1e-4)
    assert r.coverage == pytest.approx(3 / len(config.WEIGHTS), abs=1e-4)


def test_official_store_pulls_score_down():
    risky = combine({"seller_age": 1.0, "official": 0.0})
    official = combine({"seller_age": 1.0, "official": 1.0})
    assert official.score < risky.score


def test_reasons_top_three_ordered_and_thresholded():
    r = combine(
        {"price_dev": 1.0, "title_kw": 1.0, "neg_share": 1.0, "dup_reviews": 1.0, "burst": 0.2},
        {"pct_below_median": 58.0, "title_keyword": "replica"},
    )
    assert [x["signal"] for x in r.reasons] == ["price_dev", "title_kw", "neg_share"]
    assert r.reasons[0]["text"] == "Price 58% below the cross-platform median"
    assert "replica" in r.reasons[1]["text"]


def test_small_contributions_give_no_reasons():
    r = combine({"burst": 0.3})  # 0.8 * 0.3 = 0.24 <= 0.3
    assert r.reasons == []


def test_seller_age_reason_text():
    r = combine({"seller_age": 0.9}, {"age_days": 21})
    assert r.reasons[0]["text"] == "Shop is only 21 days old"


@pytest.mark.parametrize("score,expected", [(0.7, "high"), (0.69, "medium"), (0.4, "medium"), (0.39, "low")])
def test_bands(score, expected):
    assert band(score) == expected
