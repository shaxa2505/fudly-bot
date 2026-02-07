from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from .common import get_db, get_val, logger, normalize_price
from app.core.utils import normalize_city

router = APIRouter()


class SearchOfferItem(BaseModel):
    id: int
    title: str
    store_id: int | None = None
    store_name: str | None = None
    discount_price: float = 0
    original_price: float = 0
    photo: str | None = None
    photo_url: str | None = None
    category: str | None = None


class SearchStoreItem(BaseModel):
    id: int
    name: str
    address: str | None = None
    rating: float = 0
    category: str | None = None
    photo: str | None = None


class SearchResponse(BaseModel):
    query: str
    offers: list[SearchOfferItem] = Field(default_factory=list)
    stores: list[SearchStoreItem] = Field(default_factory=list)


@router.get("/search", response_model=SearchResponse)
async def search_all(
    query: str = Query(..., min_length=2, description="Search query"),
    city: str | None = Query(None, description="City filter"),
    region: str | None = Query(None, description="Region filter"),
    district: str | None = Query(None, description="District filter"),
    limit_offers: int = Query(5, ge=1, le=20),
    limit_stores: int = Query(5, ge=1, le=20),
    offset_offers: int = Query(0, ge=0),
    offset_stores: int = Query(0, ge=0),
    db=Depends(get_db),
):
    """Unified search endpoint for offers + stores."""
    try:
        normalized_city = normalize_city(city) if city else None
        normalized_region = normalize_city(region) if region else None
        normalized_district = normalize_city(district) if district else None

        offers_raw: list[Any] = []
        stores_raw: list[Any] = []
        if hasattr(db, "search_offers"):
            offers_raw = db.search_offers(
                query,
                city=normalized_city,
                region=normalized_region,
                district=normalized_district,
                limit=limit_offers,
                offset=offset_offers,
            ) or []
        if hasattr(db, "search_stores"):
            stores_raw = db.search_stores(
                query,
                city=normalized_city,
                region=normalized_region,
                district=normalized_district,
                limit=limit_stores,
                offset=offset_stores,
            ) or []

        offers = [
            SearchOfferItem(
                id=int(get_val(o, "offer_id", 0) or get_val(o, "id", 0) or 0),
                title=get_val(o, "title", "Mahsulot"),
                store_id=int(get_val(o, "store_id", 0) or 0) or None,
                store_name=get_val(o, "store_name") or get_val(o, "name"),
                discount_price=normalize_price(get_val(o, "discount_price", 0)),
                original_price=normalize_price(get_val(o, "original_price", 0)),
                photo=get_val(o, "photo") or get_val(o, "photo_id"),
                photo_url=get_val(o, "photo_url"),
                category=get_val(o, "category"),
            )
            for o in offers_raw
        ]

        stores = [
            SearchStoreItem(
                id=int(get_val(s, "store_id", 0) or get_val(s, "id", 0) or 0),
                name=get_val(s, "name", "Do'kon"),
                address=get_val(s, "address"),
                rating=float(get_val(s, "rating", 0) or 0),
                category=get_val(s, "category"),
                photo=get_val(s, "photo") or get_val(s, "photo_id"),
            )
            for s in stores_raw
        ]

        return SearchResponse(query=query, offers=offers, stores=stores)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Search endpoint failed: %s", exc)
        return SearchResponse(query=query, offers=[], stores=[])
