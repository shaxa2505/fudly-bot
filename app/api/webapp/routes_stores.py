from __future__ import annotations

import os
import inspect
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from .common import LocationRequest, StoreResponse, get_db, get_val, logger, normalize_price
from app.core.geocoding import geocode_store_address, geocoding_enabled
from app.core.utils import normalize_city

router = APIRouter()

_MAX_GEOCODE_PER_REQUEST = max(0, int(os.getenv("FUDLY_STORE_GEOCODE_LIMIT", "8") or 0))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _db_call(db: Any, name: str, *args: Any, **kwargs: Any) -> Any:
    if not hasattr(db, name):
        return None
    result = getattr(db, name)(*args, **kwargs)
    return await _maybe_await(result)


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".")
        if not cleaned:
            return None
        value = cleaned
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_coords(store: Any) -> tuple[float | None, float | None]:
    lat = _parse_float(
        get_val(store, "latitude")
        or get_val(store, "lat")
        or get_val(store, "coord_lat")
        or get_val(store, "coordLat")
        or get_val(store, "y")
    )
    lon = _parse_float(
        get_val(store, "longitude")
        or get_val(store, "lon")
        or get_val(store, "lng")
        or get_val(store, "long")
        or get_val(store, "coord_lon")
        or get_val(store, "coordLon")
        or get_val(store, "x")
    )
    return lat, lon


def _is_missing_coord(value: float | None) -> bool:
    return value is None or value == 0.0


async def _resolve_missing_coords(raw_stores: list[Any], db) -> None:
    if not geocoding_enabled() or _MAX_GEOCODE_PER_REQUEST <= 0:
        return

    candidates: list[Any] = []
    for store in raw_stores:
        lat, lon = _extract_coords(store)
        if _is_missing_coord(lat) or _is_missing_coord(lon):
            candidates.append(store)

    if not candidates:
        return

    for store in candidates[:_MAX_GEOCODE_PER_REQUEST]:
        address = get_val(store, "address")
        city = get_val(store, "city")
        if not address and not city:
            continue

        result = await geocode_store_address(address, city)
        if not result:
            continue

        lat = result.get("latitude")
        lon = result.get("longitude")
        if lat is None or lon is None:
            continue

        if isinstance(store, dict):
            store["latitude"] = lat
            store["longitude"] = lon
        else:
            setattr(store, "latitude", lat)
            setattr(store, "longitude", lon)

        store_id = int(get_val(store, "id", 0) or get_val(store, "store_id", 0) or 0)
        if store_id and hasattr(db, "update_store_location"):
            try:
                await _db_call(
                    db,
                    "update_store_location",
                    store_id,
                    lat,
                    lon,
                    region=result.get("region"),
                    district=result.get("district"),
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to persist store coords: %s", exc)


@router.get("/stores", response_model=list[StoreResponse])
async def get_stores(
    city: str | None = Query(None, description="City to filter by"),
    region: str | None = Query(None, description="Region filter"),
    district: str | None = Query(None, description="District filter"),
    lat: float | None = Query(None, description="Latitude for nearby fallback"),
    lon: float | None = Query(None, description="Longitude for nearby fallback"),
    latitude: float | None = Query(None, description="Latitude (alias)"),
    longitude: float | None = Query(None, description="Longitude (alias)"),
    business_type: str | None = Query(None, description="Business type filter"),
    resolve_coords: bool = Query(False, description="Resolve missing coordinates via geocoding"),
    db=Depends(get_db),
):
    """Get list of stores."""
    try:
        normalized_city = normalize_city(city) if city else None
        normalized_city = normalized_city or None
        region = region or None
        district = district or None
        lat_val = lat if lat is not None else latitude
        lon_val = lon if lon is not None else longitude

        raw_stores: list[Any] = []

        async def _fetch_scoped_stores(
            city_scope: str | None, region_scope: str | None, district_scope: str | None
        ) -> list[Any]:
            if hasattr(db, "get_stores_by_location"):
                return await _db_call(
                    db,
                    "get_stores_by_location",
                    city=city_scope,
                    region=region_scope,
                    district=district_scope,
                    business_type=business_type,
                )
            if city_scope and hasattr(db, "get_stores_by_city"):
                return await _db_call(db, "get_stores_by_city", city_scope)
            return []

        scopes: list[tuple[str | None, str | None, str | None]] = []
        if district:
            scopes.append((None, region, district))
        if region:
            scopes.append((None, region, None))
        if normalized_city:
            scopes.append((normalized_city, None, None))
            if not region:
                scopes.append((None, normalized_city, None))
        if not scopes:
            scopes.append((None, None, None))

        seen: set[tuple[str | None, str | None, str | None]] = set()
        seen_ids: set[int] = set()
        for scope in scopes:
            if scope in seen:
                continue
            seen.add(scope)
            scoped_stores = await _fetch_scoped_stores(*scope) or []
            if not scoped_stores:
                continue
            for store in scoped_stores:
                store_id = int(get_val(store, "id", 0) or get_val(store, "store_id", 0) or 0)
                if store_id and store_id in seen_ids:
                    continue
                if store_id:
                    seen_ids.add(store_id)
                raw_stores.append(store)

        if (
            not raw_stores
            and lat_val is not None
            and lon_val is not None
            and hasattr(db, "get_nearby_stores")
        ):
            raw_stores = await _db_call(db, "get_nearby_stores",
                latitude=lat_val,
                longitude=lon_val,
                business_type=business_type,
                limit=200,
                offset=0,
            )

        if not raw_stores:
            raw_stores = []

        if resolve_coords and raw_stores:
            await _resolve_missing_coords(raw_stores, db)

        stores: list[StoreResponse] = []
        for store in raw_stores:
            lat_val, lon_val = _extract_coords(store)
            stores.append(
                StoreResponse(
                    id=int(get_val(store, "id", 0) or get_val(store, "store_id", 0) or 0),
                    name=get_val(store, "name", ""),
                    address=get_val(store, "address"),
                    city=get_val(store, "city"),
                    region=get_val(store, "region"),
                    district=get_val(store, "district"),
                    latitude=lat_val,
                    longitude=lon_val,
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
                    working_hours=get_val(store, "working_hours"),
                )
            )

        return stores

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting stores: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/stores/{store_id}", response_model=StoreResponse)
async def get_store(
    store_id: int,
    resolve_coords: bool = Query(False, description="Resolve missing coordinates via geocoding"),
    db=Depends(get_db),
):
    """Get store details by ID."""
    try:
        store = await _db_call(db, "get_store", store_id) if hasattr(db, "get_store") else None
        if not store:
            raise HTTPException(status_code=404, detail="Store not found")

        offers_count = int(get_val(store, "offers_count", 0) or 0)
        if offers_count == 0 and hasattr(db, "get_store_offers"):
            try:
                offers_count = len((await _db_call(db, "get_store_offers", store_id)) or [])
            except Exception:  # pragma: no cover - defensive
                offers_count = 0

        rating = float(get_val(store, "avg_rating", 0) or get_val(store, "rating", 0) or 0)
        if rating == 0.0 and hasattr(db, "get_store_average_rating"):
            try:
                rating = float((await _db_call(db, "get_store_average_rating", store_id)) or 0)
            except Exception:  # pragma: no cover - defensive
                rating = 0.0

        if resolve_coords:
            await _resolve_missing_coords([store], db)

        lat_val, lon_val = _extract_coords(store)

        return StoreResponse(
            id=int(get_val(store, "id", 0) or get_val(store, "store_id", 0) or 0),
            name=get_val(store, "name", ""),
            address=get_val(store, "address"),
            city=get_val(store, "city"),
            region=get_val(store, "region"),
            district=get_val(store, "district"),
            latitude=lat_val,
            longitude=lon_val,
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
            working_hours=get_val(store, "working_hours"),
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

        reviews = await _db_call(db, "get_store_ratings", store_id) or []

        average_rating = 0.0
        total_reviews = len(reviews)
        if hasattr(db, "get_store_rating_summary"):
            try:
                average_rating, total_reviews = await _db_call(
                    db, "get_store_rating_summary", store_id
                )
            except Exception:  # pragma: no cover - defensive
                average_rating = 0.0
                total_reviews = len(reviews)
        elif hasattr(db, "get_store_average_rating"):
            try:
                average_rating = float(
                    (await _db_call(db, "get_store_average_rating", store_id)) or 0.0
                )
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
        if hasattr(db, "get_nearby_stores"):
            raw_stores = await _db_call(db, "get_nearby_stores",
                latitude=location.latitude,
                longitude=location.longitude,
                max_distance_km=radius_km,
                limit=200,
                offset=0,
            )

        if not raw_stores:
            return []

        stores_with_distance: list[dict[str, Any]] = []

        for store in raw_stores:
            distance = get_val(store, "distance_km")
            lat_val, lon_val = _extract_coords(store)
            store_data = StoreResponse(
                id=int(get_val(store, "id", 0) or get_val(store, "store_id", 0) or 0),
                name=get_val(store, "name", ""),
                address=get_val(store, "address"),
                city=get_val(store, "city"),
                region=get_val(store, "region"),
                district=get_val(store, "district"),
                latitude=lat_val,
                longitude=lon_val,
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
                working_hours=get_val(store, "working_hours"),
            )
            stores_with_distance.append(
                {"store": store_data, "distance_km": round(float(distance), 2) if distance is not None else None}
            )

        stores_with_distance.sort(key=lambda x: x["distance_km"] or 0.0)

        return stores_with_distance

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting nearby stores: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
