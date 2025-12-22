from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from .common import LocationRequest, StoreResponse, get_db, get_val, logger, normalize_price

router = APIRouter()


@router.get("/stores", response_model=list[StoreResponse])
async def get_stores(
    city: str = Query("Ташкент", description="City to filter by"),
    region: str | None = Query(None, description="Region filter"),
    district: str | None = Query(None, description="District filter"),
    business_type: str | None = Query(None, description="Business type filter"),
    db=Depends(get_db),
):
    """Get list of stores."""
    try:
        if business_type:
            raw_stores = (
                db.get_stores_by_business_type(business_type, city)
                if hasattr(db, "get_stores_by_business_type")
                else []
            )
        else:
            if hasattr(db, "get_stores_by_location"):
                raw_stores = db.get_stores_by_location(city=city, region=region, district=district)
            else:
                raw_stores = db.get_stores_by_city(city) if hasattr(db, "get_stores_by_city") else []

        if not raw_stores:
            raw_stores = []

        stores: list[StoreResponse] = []
        for store in raw_stores:
            stores.append(
                StoreResponse(
                    id=int(get_val(store, "id", 0) or get_val(store, "store_id", 0) or 0),
                    name=get_val(store, "name", ""),
                    address=get_val(store, "address"),
                    city=get_val(store, "city"),
                    region=get_val(store, "region"),
                    district=get_val(store, "district"),
                    business_type=get_val(store, "business_type")
                    or get_val(store, "category")
                    or "supermarket",
                    rating=float(get_val(store, "avg_rating", 0) or get_val(store, "rating", 0) or 0),
                    offers_count=int(get_val(store, "offers_count", 0) or 0),
                    delivery_enabled=bool(get_val(store, "delivery_enabled", False)),
                    delivery_price=normalize_price(get_val(store, "delivery_price", 0))
                    if get_val(store, "delivery_price")
                    else None,
                    min_order_amount=normalize_price(get_val(store, "min_order_amount", 0))
                    if get_val(store, "min_order_amount")
                    else None,
                    photo_url=get_val(store, "photo"),
                )
            )

        return stores

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting stores: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/stores/{store_id}", response_model=StoreResponse)
async def get_store(store_id: int, db=Depends(get_db)):
    """Get store details by ID."""
    try:
        store = db.get_store(store_id) if hasattr(db, "get_store") else None
        if not store:
            raise HTTPException(status_code=404, detail="Store not found")

        offers_count = int(get_val(store, "offers_count", 0) or 0)
        if offers_count == 0 and hasattr(db, "get_store_offers"):
            try:
                offers_count = len(db.get_store_offers(store_id) or [])
            except Exception:  # pragma: no cover - defensive
                offers_count = 0

        rating = float(get_val(store, "avg_rating", 0) or get_val(store, "rating", 0) or 0)
        if rating == 0.0 and hasattr(db, "get_store_average_rating"):
            try:
                rating = float(db.get_store_average_rating(store_id) or 0)
            except Exception:  # pragma: no cover - defensive
                rating = 0.0

        return StoreResponse(
            id=int(get_val(store, "id", 0) or get_val(store, "store_id", 0) or 0),
            name=get_val(store, "name", ""),
            address=get_val(store, "address"),
            city=get_val(store, "city"),
            region=get_val(store, "region"),
            district=get_val(store, "district"),
            business_type=get_val(store, "business_type") or get_val(store, "category") or "supermarket",
            rating=rating,
            offers_count=offers_count,
            delivery_enabled=bool(get_val(store, "delivery_enabled", False)),
            delivery_price=normalize_price(get_val(store, "delivery_price", 0))
            if get_val(store, "delivery_price")
            else None,
            min_order_amount=normalize_price(get_val(store, "min_order_amount", 0))
            if get_val(store, "min_order_amount")
            else None,
            photo_url=get_val(store, "photo"),
        )
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting store {store_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/stores/{store_id}/reviews")
async def get_store_reviews(store_id: int, db=Depends(get_db)):
    """Get store reviews and rating summary."""
    try:
        if not hasattr(db, "get_store_ratings"):
            return {"reviews": [], "average_rating": 0.0, "total_reviews": 0}

        reviews = db.get_store_ratings(store_id) or []

        average_rating = 0.0
        total_reviews = len(reviews)
        if hasattr(db, "get_store_rating_summary"):
            try:
                average_rating, total_reviews = db.get_store_rating_summary(store_id)
            except Exception:  # pragma: no cover - defensive
                average_rating = 0.0
                total_reviews = len(reviews)
        elif hasattr(db, "get_store_average_rating"):
            try:
                average_rating = float(db.get_store_average_rating(store_id) or 0.0)
            except Exception:  # pragma: no cover - defensive
                average_rating = 0.0

        return {
            "reviews": reviews,
            "average_rating": float(average_rating or 0.0),
            "total_reviews": int(total_reviews or 0),
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting store reviews {store_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/stores/nearby")
async def get_nearby_stores(
    location: LocationRequest,
    radius_km: float = Query(5.0, description="Search radius in kilometers"),
    db=Depends(get_db),
):
    """Get stores near user's location.

    NOTE: Distance calculation is currently mocked and should be
    replaced with a real geospatial implementation (e.g. PostGIS).
    """
    try:
        raw_stores: list[Any] = []
        if hasattr(db, "get_stores_by_city"):
            for city in ["Ташкент", "Tashkent", "Самарканд", "Бухара"]:
                try:
                    stores = db.get_stores_by_city(city)
                    if stores:
                        raw_stores.extend(stores)
                except Exception:  # pragma: no cover - defensive
                    continue

        if not raw_stores:
            return []

        stores_with_distance: list[dict[str, Any]] = []

        for store in raw_stores:
            import random

            distance = random.uniform(0.5, 10.0)

            if distance <= radius_km:
                store_data = StoreResponse(
                    id=int(get_val(store, "id", 0) or get_val(store, "store_id", 0) or 0),
                    name=get_val(store, "name", ""),
                    address=get_val(store, "address"),
                    city=get_val(store, "city"),
                    business_type=get_val(store, "business_type")
                    or get_val(store, "category")
                    or "supermarket",
                    rating=float(get_val(store, "avg_rating", 0) or get_val(store, "rating", 0) or 0),
                    offers_count=int(get_val(store, "offers_count", 0) or 0),
                )
                stores_with_distance.append(
                    {"store": store_data, "distance_km": round(distance, 2)}
                )

        stores_with_distance.sort(key=lambda x: x["distance_km"])

        _ = location  # keep parameter for future real implementation
        return stores_with_distance

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting nearby stores: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
