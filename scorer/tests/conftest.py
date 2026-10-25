import pytest

from scorer_engine.models import Listing

# The normaliser's sample output (fixtures/sample_store_a.json).
SAMPLE = {
    "cluster_id": "store_a:A-1001", "cluster_size": 3,
    "cluster_platforms": ["store_a", "store_b", "store_c"],
    "cluster_price_median_sgd": 445.5, "cluster_price_min_sgd": 399.0, "cluster_price_max_sgd": 449.0,
    "listing_id": "store_a:A-1001", "source_platform": "store_a",
    "title": "Sony WH-1000XM5 Wireless Noise Cancelling Headphones", "brand": "sony",
    "price_sgd": 449.0, "seller_name": "AudioHub SG", "seller_age_days": 2064,
    "rating": 4.7, "review_count": 230,
    "reviews": [{"text": "Great noise cancellation, worth the price.", "rating": 5, "date": "2026-09-01"}],
    "product_url": "https://store-a.mock/items/A-1001",
}


@pytest.fixture
def sample():
    return dict(SAMPLE)


@pytest.fixture
def make_listing():
    def _make(**overrides):
        return Listing.model_validate({**SAMPLE, **overrides})
    return _make
