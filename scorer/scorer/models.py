"""
Pydantic models for messages on `listings.normalised` (key = cluster_id).

Currency conversion happens upstream in the normaliser, so `price` is already
in the common currency by the time it reaches the scorer.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class Seller(BaseModel):
    id: str
    created_at: Optional[date] = None
    sales: Optional[int] = Field(default=None, ge=0)
    rating: Optional[float] = None
    is_official: Optional[bool] = None


class Review(BaseModel):
    text: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    ts: Optional[datetime] = None


class Listing(BaseModel):
    listing_id: str
    platform: str
    cluster_id: str
    title: str
    price: float = Field(gt=0)
    currency: str
    seller: Seller
    reviews: list[Review] = []
    fetched_at: datetime
