"""
Pydantic models for the normaliser's output (topic `listings.normalised`,
key = cluster_id). Prices are already converted to SGD and the cluster's
price statistics travel with every message, so the scorer needs no lookups.

Unknown extra fields are ignored, so the normaliser can add fields freely.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Review(BaseModel):
    text: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    date: Optional[datetime] = None  # "2026-09-01" or a full ISO timestamp

    @field_validator("date")
    @classmethod
    def _assume_utc(cls, v):
        # Date-only strings parse as naive datetimes; make every value
        # timezone-aware so they can be compared with each other.
        if v is not None and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v


class Listing(BaseModel):
    # --- cluster (computed by the normaliser/matcher) -----------------------
    cluster_id: str
    cluster_size: int = Field(default=1, ge=1)  # listings in the cluster, this one included
    cluster_platforms: list[str] = []
    cluster_price_median_sgd: Optional[float] = None
    cluster_price_min_sgd: Optional[float] = None
    cluster_price_max_sgd: Optional[float] = None

    # --- the listing ---------------------------------------------------------
    listing_id: str
    source_platform: str
    title: str
    brand: Optional[str] = None
    price_sgd: float = Field(gt=0)
    seller_name: Optional[str] = None
    seller_age_days: Optional[int] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    reviews: list[Review] = []
    product_url: Optional[str] = None

    # --- not sent by the normaliser yet; signals return None without them ---
    seller_sales: Optional[int] = Field(default=None, ge=0)
    seller_is_official: Optional[bool] = None
    fetched_at: Optional[datetime] = None
