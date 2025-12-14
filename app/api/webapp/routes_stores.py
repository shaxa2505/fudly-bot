from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from .common import LocationRequest, StoreResponse, get_db, get_val, logger

router = APIRouter()


@router.get("/stores", response_model=list[StoreResponse])
async def get_stores(
    city: str = Query("Ташкент", description="City to filter by"),
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
            raw_stores = db.get_stores_by_city(city) if hasattr(db, "get_stores_by_city") else []

        if not raw_stores:
            raw_stores = []

        stores: list[StoreResponse] = []
        for store in raw_stores:
            stores.append(
                StoreResponse(
                    id=get_val(store, "id", 0),
                    name=get_val(store, "name", ""),
                    address=get_val(store, "address"),
                    city=get_val(store, "city"),
                    business_type=get_val(store, "business_type", "supermarket"),
                    rating=float(get_val(store, "rating", 0) or 0),
                    offers_count=int(get_val(store, "offers_count", 0) or 0),
                    delivery_enabled=bool(get_val(store, "delivery_enabled", False)),
                    delivery_price=float(get_val(store, "delivery_price", 0) or 0)
                    if get_val(store, "delivery_price")
                    else None,
                    min_order_amount=float(get_val(store, "min_order_amount", 0) or 0)
                    if get_val(store, "min_order_amount")
                    else None,
                    photo_url=get_val(store, "photo"),
                )
            )

        return stores

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting stores: {e}")
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
                    id=get_val(store, "id", 0),
                    name=get_val(store, "name", ""),
                    address=get_val(store, "address"),
                    city=get_val(store, "city"),
                    business_type=get_val(store, "business_type", "supermarket"),
                    rating=float(get_val(store, "rating", 0) or 0),
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
