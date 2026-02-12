from __future__ import annotations

import inspect
import os
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.rate_limit import limiter
from app.core.caching import get_cache_service
from app.core.location_search import build_nearby_radius_steps
from app.core.utils import normalize_city

from .common import (
    CATEGORIES,
    PRICE_STORAGE_UNIT,
    CategoryResponse,
    OfferListResponse,
    OfferResponse,
    get_db,
    get_val,
    is_offer_active,
    logger,
    normalize_price,
)

router = APIRouter()

CATEGORY_ALIASES: dict[str, list[str]] = {
    "sweets": ["sweets", "snacks"],
}

# Keep in sync with app/core/webhook_helpers.py
CATEGORY_SYNONYMS: dict[str, set[str]] = {
    "dairy": {
        "dairy",
        "sut",
        "sut mahsulotlari",
        "молочные",
        "молочные продукты",
    },
    "bakery": {
        "bakery",
        "non",
        "pishiriq",
        "выпечка",
        "хлеб",
    },
    "meat": {
        "meat",
        "go'sht",
        "go'sht mahsulotlari",
        "мясные",
        "мясо",
        "мясо и рыба",
        "рыба",
        "baliq",
    },
    "fruits": {
        "fruits",
        "meva",
        "mevalar",
        "фрукты",
    },
    "vegetables": {
        "vegetables",
        "sabzavot",
        "sabzavotlar",
        "овощи",
    },
    "drinks": {
        "drinks",
        "ichimlik",
        "ichimliklar",
        "напитки",
    },
    "sweets": {
        "sweets",
        "snacks",
        "сладости",
        "снеки",
        "shirinliklar",
        "gaz. ovqatlar",
        "gaz ovqatlar",
    },
    "frozen": {
        "frozen",
        "muzlatilgan",
        "замороженное",
        "заморозка",
    },
    "other": {
        "other",
        "boshqa",
        "другое",
        "ready_food",
        "tayyor ovqat",
        "готовая еда",
        "cheese",
        "pishloq",
        "сыры",
    },
}

_CATEGORY_CANONICAL: dict[str, str] = {}
for key, values in CATEGORY_SYNONYMS.items():
    for value in values:
        _CATEGORY_CANONICAL[value] = key
    _CATEGORY_CANONICAL[key] = key
for key, aliases in CATEGORY_ALIASES.items():
    for alias in aliases:
        _CATEGORY_CANONICAL.setdefault(alias, key)

async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _db_call(db: Any, name: str, *args: Any, **kwargs: Any) -> Any:
    if not hasattr(db, name):
        return None
    result = getattr(db, name)(*args, **kwargs)
    return await _maybe_await(result)


def _get_cache_ttl(env_name: str, default: int) -> int:
    raw = os.getenv(env_name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def expand_category_filter(category: str | None) -> list[str] | None:
    if not category:
        return None
    normalized = str(category).strip().lower()
    if not normalized or normalized == "all":
        return None
    canonical = _CATEGORY_CANONICAL.get(normalized, normalized)
    values: set[str] = {canonical, normalized}
    values.update(CATEGORY_SYNONYMS.get(canonical, set()))
    for alias in CATEGORY_ALIASES.get(canonical, []):
        values.add(alias)
        values.update(CATEGORY_SYNONYMS.get(alias, set()))
    return sorted(values)


def _calc_discount_percent(original_price: float, discount_price: float) -> float:
    try:
        if original_price and original_price > 0 and discount_price >= 0 and original_price > discount_price:
            return float(round((1.0 - (discount_price / original_price)) * 100.0, 1))
    except Exception:  # pragma: no cover - defensive
        pass
    return 0.0


def _to_storage_price(price: float | None) -> float | None:
    if price is None:
        return None
    try:
        amount = float(price)
    except (TypeError, ValueError):
        return None
    if PRICE_STORAGE_UNIT == "kopeks":
        return amount * 100
    return amount


def _to_offer_response(offer: Any, store_fallback: dict | None = None) -> OfferResponse:
    offer_id = int(get_val(offer, "id", 0) or get_val(offer, "offer_id", 0) or 0)
    store_id = int(get_val(offer, "store_id", 0) or 0)

    title = get_val(offer, "title", "Mahsulot")
    description = get_val(offer, "description")

    original_price = normalize_price(get_val(offer, "original_price", 0))
    discount_price = normalize_price(get_val(offer, "discount_price", 0))

    discount_percent_val = get_val(offer, "discount_percent")
    discount_percent = float(discount_percent_val or 0)
    if not discount_percent:
        discount_percent = _calc_discount_percent(original_price, discount_price)

    store_name = (
        get_val(offer, "store_name")
        or get_val(offer, "name")
        or (get_val(store_fallback, "name") if store_fallback else "")
        or ""
    )
    store_address = (
        get_val(offer, "store_address")
        or get_val(offer, "address")
        or (get_val(store_fallback, "address") if store_fallback else None)
    )
    store_rating = float(
        get_val(offer, "store_rating")
        or get_val(offer, "avg_rating")
        or get_val(offer, "rating")
        or (get_val(store_fallback, "rating") if store_fallback else 0)
        or 0
    )
    delivery_enabled = bool(
        get_val(offer, "delivery_enabled", get_val(store_fallback, "delivery_enabled", False))
    )
    delivery_price = get_val(offer, "delivery_price", get_val(store_fallback, "delivery_price"))
    min_order_amount = get_val(
        offer, "min_order_amount", get_val(store_fallback, "min_order_amount")
    )

    photo = get_val(offer, "photo") or get_val(offer, "photo_id")

    expiry_raw = get_val(offer, "expiry_date")
    expiry_date = str(expiry_raw) if expiry_raw else None

    return OfferResponse(
        id=offer_id,
        title=title,
        description=description,
        original_price=original_price,
        discount_price=discount_price,
        discount_percent=discount_percent,
        quantity=float(get_val(offer, "quantity", 0) or 0),
        unit=get_val(offer, "unit", "dona") or "dona",
        category=get_val(offer, "category", "other") or "other",
        store_id=store_id,
        store_name=store_name,
        store_address=store_address,
        store_rating=store_rating,
        delivery_enabled=delivery_enabled,
        delivery_price=delivery_price,
        min_order_amount=min_order_amount,
        photo=photo,
        expiry_date=expiry_date,
        available_from=get_val(offer, "available_from"),
        available_until=get_val(offer, "available_until"),
    )


@router.get("/categories", response_model=list[CategoryResponse])
async def get_categories(
    city: str | None = Query(None, description="City to filter by"),
    region: str | None = Query(None, description="Region filter"),
    district: str | None = Query(None, description="District filter"),
    db=Depends(get_db),
):
    """Get list of product categories with counts."""
    result: list[CategoryResponse] = []
    normalized_city = normalize_city(city) if city else None
    normalized_region = normalize_city(region) if region else None
    normalized_district = normalize_city(district) if district else None
    cache_ttl = _get_cache_ttl("WEBAPP_CACHE_CATEGORIES_TTL", 60)
    cache_key = None
    cache = None
    if cache_ttl > 0:
        cache = get_cache_service(os.getenv("REDIS_URL"))
        cache_key = (
            f"webapp:categories:{normalized_city or ''}:{normalized_region or ''}:{normalized_district or ''}"
        )
        cached = await cache.get(cache_key)
        if cached is not None:
            return cached

    async def _count_for_scope(
        category_filter: list[str] | None,
        city_scope: str | None,
        region_scope: str | None,
        district_scope: str | None,
    ) -> int:
        if hasattr(db, "count_offers_by_filters"):
            return int(
                (await _db_call(
                    db,
                    "count_offers_by_filters",
                    city=city_scope,
                    region=region_scope,
                    district=district_scope,
                    category=category_filter,
                ))
                or 0
            )
        if category_filter:
            if hasattr(db, "get_offers_by_city_and_category"):
                offers = await _db_call(
                    db,
                    "get_offers_by_city_and_category",
                    city=city_scope,
                    category=category_filter,
                    region=region_scope,
                    district=district_scope,
                    limit=1000,
                    offset=0,
                )
                return len(offers) if offers else 0
            if hasattr(db, "get_offers_by_category"):
                if isinstance(category_filter, (list, tuple)):
                    offers = []
                    for item in category_filter:
                        offers.extend(
                            (await _db_call(db, "get_offers_by_category", item, city_scope)) or []
                        )
                    return len(offers)
                offers = await _db_call(db, "get_offers_by_category", category_filter, city_scope) or []
                return len(offers)
            return 0
        if hasattr(db, "count_hot_offers"):
            return (
                (await _db_call(
                    db,
                    "count_hot_offers",
                    city_scope,
                    region=region_scope,
                    district=district_scope,
                ))
                or 0
            )
        return 0

    scopes: list[tuple[str | None, str | None, str | None]] = []
    if normalized_district:
        scopes.append((None, normalized_region, normalized_district))
    if normalized_region:
        scopes.append((None, normalized_region, None))
    if normalized_city:
        scopes.append((normalized_city, None, None))
        if not normalized_region:
            scopes.append((None, normalized_city, None))
    if not scopes:
        scopes.append((None, None, None))

    if hasattr(db, "count_offers_by_category_grouped"):
        counts_map: dict[str, int] = {}
        total_count = 0
        for city_scope, region_scope, district_scope in scopes:
            try:
                counts_map = (
                    await _db_call(
                        db,
                        "count_offers_by_category_grouped",
                        city=city_scope,
                        region=region_scope,
                        district=district_scope,
                    )
                ) or {}
            except Exception:  # pragma: no cover - defensive
                counts_map = {}
            total_count = sum(counts_map.values()) if counts_map else 0
            if total_count:
                break

        for cat in CATEGORIES:
            if cat["id"] == "all":
                count = total_count
            else:
                category_filter = expand_category_filter(cat["id"]) or []
                count = sum(counts_map.get(item, 0) for item in category_filter)
            result.append(
                CategoryResponse(id=cat["id"], name=cat["name"], emoji=cat["emoji"], count=count)
            )
    else:
        for cat in CATEGORIES:
            count = 0
            category_filter = expand_category_filter(cat["id"])
            try:
                for city_scope, region_scope, district_scope in scopes:
                    count = await _count_for_scope(
                        category_filter if cat["id"] != "all" else None,
                        city_scope,
                        region_scope,
                        district_scope,
                    )
                    if count:
                        break
            except Exception:  # pragma: no cover - defensive
                count = 0

            result.append(
                CategoryResponse(id=cat["id"], name=cat["name"], emoji=cat["emoji"], count=count)
            )

    if cache and cache_key and cache_ttl > 0:
        await cache.set(cache_key, result, ttl=cache_ttl)

    return result


@router.get("/offers", response_model=list[OfferResponse] | OfferListResponse)
@limiter.limit("60/minute")
async def get_offers(
    request: Request,
    city: str | None = Query(None, description="City to filter by"),
    region: str | None = Query(None, description="Region filter"),
    district: str | None = Query(None, description="District filter"),
    lat: float | None = Query(None, description="Latitude for nearby fallback"),
    lon: float | None = Query(None, description="Longitude for nearby fallback"),
    latitude: float | None = Query(None, description="Latitude (alias)"),
    longitude: float | None = Query(None, description="Longitude (alias)"),
    max_distance_km: float | None = Query(
        None, ge=0, le=100, description="Max distance in km for nearby offers fallback"
    ),
    category: str = Query("all", description="Category filter"),
    store_id: int | None = Query(None, description="Store ID filter"),
    search: str | None = Query(None, description="Search query"),
    min_price: float | None = Query(None, description="Minimum price filter"),
    max_price: float | None = Query(None, description="Maximum price filter"),
    min_discount: float | None = Query(None, description="Minimum discount percent"),
    sort_by: str | None = Query(None, description="Sort by: urgent, discount, price_asc, price_desc, new"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_meta: bool = Query(False, description="Include response metadata"),
    db=Depends(get_db),
):
    """Get list of offers with advanced filters and sorting."""
    try:
        normalized_city = normalize_city(city) if city else None
        normalized_city = normalized_city or None
        region = normalize_city(region) if region else None
        district = normalize_city(district) if district else None
        category_filter = expand_category_filter(category)
        lat_val = lat if lat is not None else latitude
        lon_val = lon if lon is not None else longitude
        offers: list[OfferResponse] = []
        store_fallback: dict | None = None

        storage_min_price = _to_storage_price(min_price)
        storage_max_price = _to_storage_price(max_price)

        raw_offers: list[Any] = []
        sort_key = sort_by or "urgent"
        apply_filters = True
        apply_sort = True
        apply_slice = True
        nearby_radius_steps = build_nearby_radius_steps(max_distance_km)

        cache_ttl = _get_cache_ttl(
            "WEBAPP_CACHE_SEARCH_TTL" if search else "WEBAPP_CACHE_OFFERS_TTL",
            15 if search else 30,
        )
        cache_key = None
        cache = None
        if cache_ttl > 0 and not (lat_val is not None and lon_val is not None):
            cache = get_cache_service(os.getenv("REDIS_URL"))
            cache_key = (
                "webapp:offers:"
                f"{search or ''}:{normalized_city or ''}:{region or ''}:{district or ''}:"
                f"{category_filter or ''}:{store_id or ''}:{sort_key}:"
                f"{storage_min_price or ''}:{storage_max_price or ''}:{min_discount or ''}:"
                f"{limit}:{offset}:{int(include_meta)}"
            )
            cached = await cache.get(cache_key)
            if cached is not None:
                return cached
        if store_id:
            raw_offers = (
                await _db_call(
                    db,
                    "get_store_offers",
                    store_id,
                    limit=limit,
                    offset=offset,
                    sort_by=sort_key,
                    min_price=storage_min_price,
                    max_price=storage_max_price,
                    min_discount=min_discount,
                )
                if hasattr(db, "get_store_offers")
                else []
            )
            if hasattr(db, "get_store"):
                store_fallback = await _db_call(db, "get_store", store_id)
            apply_filters = False
            apply_sort = False
            apply_slice = False
        elif search:
            async def _search_scoped(
                city_scope: str | None, region_scope: str | None, district_scope: str | None
            ) -> list[Any]:
                return (
                    await _db_call(
                        db,
                        "search_offers",
                        search,
                        city_scope,
                        limit=limit,
                        offset=offset,
                        region=region_scope,
                        district=district_scope,
                        min_price=storage_min_price,
                        max_price=storage_max_price,
                        min_discount=min_discount,
                        category=category_filter,
                        sort_by=sort_key,
                    )
                    if hasattr(db, "search_offers")
                    else []
                )

            raw_offers = await _search_scoped(normalized_city, region, district)
            if not raw_offers and hasattr(db, "search_offers"):
                scopes: list[tuple[str | None, str | None, str | None]] = []
                if district:
                    scopes.append((None, region, district))
                if region:
                    scopes.append((None, region, None))
                if normalized_city:
                    scopes.append((normalized_city, None, None))
                    if not region:
                        scopes.append((None, normalized_city, None))
                scopes.append((None, None, None))

                seen: set[tuple[str | None, str | None, str | None]] = set()
                for scope in scopes:
                    if scope in seen:
                        continue
                    seen.add(scope)
                    raw_offers = await _search_scoped(*scope)
                    if raw_offers:
                        break

            apply_filters = False
            apply_sort = False
            apply_slice = False
        else:
            async def _fetch_nearby_offers() -> tuple[list[Any], float | None]:
                if lat_val is None or lon_val is None or not hasattr(db, "get_nearby_offers"):
                    return [], None

                for radius_km in nearby_radius_steps:
                    nearby = await _db_call(
                        db,
                        "get_nearby_offers",
                        latitude=lat_val,
                        longitude=lon_val,
                        limit=limit,
                        offset=offset,
                        category=category_filter,
                        sort_by=sort_key,
                        min_price=storage_min_price,
                        max_price=storage_max_price,
                        min_discount=min_discount,
                        max_distance_km=radius_km,
                    )
                    if nearby:
                        return nearby, radius_km
                return [], None

            async def _fetch_scoped_offers(
                city_scope: str | None, region_scope: str | None, district_scope: str | None
            ) -> list[Any]:
                if category_filter:
                    if hasattr(db, "get_offers_by_city_and_category"):
                        offers_by_city = await _db_call(
                            db,
                            "get_offers_by_city_and_category",
                            city=city_scope,
                            category=category_filter,
                            limit=limit,
                            offset=offset,
                            region=region_scope,
                            district=district_scope,
                            sort_by=sort_key,
                            min_price=storage_min_price,
                            max_price=storage_max_price,
                            min_discount=min_discount,
                        )
                        if (
                            not offers_by_city
                            and city_scope
                            and not region_scope
                            and not district_scope
                            and hasattr(db, "resolve_geo_location")
                        ):
                            resolved_geo = await _db_call(
                                db,
                                "resolve_geo_location",
                                region=None,
                                district=city_scope,
                                city=city_scope,
                            )
                            resolved_region = get_val(resolved_geo, "region_name_ru")
                            resolved_district = get_val(resolved_geo, "district_name_ru")
                            if resolved_region or resolved_district:
                                offers_by_city = await _db_call(
                                    db,
                                    "get_offers_by_city_and_category",
                                    city=None,
                                    category=category_filter,
                                    limit=limit,
                                    offset=offset,
                                    region=resolved_region,
                                    district=resolved_district,
                                    sort_by=sort_key,
                                    min_price=storage_min_price,
                                    max_price=storage_max_price,
                                    min_discount=min_discount,
                                )
                        return offers_by_city or []
                    if hasattr(db, "get_offers_by_category") and city_scope:
                        if isinstance(category_filter, (list, tuple)):
                            combined: list[Any] = []
                            for item in category_filter:
                                combined.extend(
                                    (await _db_call(db, "get_offers_by_category", item, city_scope)) or []
                                )
                            return combined
                        return await _db_call(db, "get_offers_by_category", category_filter, city_scope)
                    return []
                if hasattr(db, "get_hot_offers"):
                    return await _db_call(
                        db,
                        "get_hot_offers",
                        city_scope,
                        limit=limit,
                        offset=offset,
                        region=region_scope,
                        district=district_scope,
                        sort_by=sort_key,
                        min_price=storage_min_price,
                        max_price=storage_max_price,
                        min_discount=min_discount,
                    )
                return []

            has_precise_location = lat_val is not None and lon_val is not None
            if has_precise_location:
                raw_offers, _ = await _fetch_nearby_offers()

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
            for scope in scopes:
                if scope in seen:
                    continue
                seen.add(scope)
                if raw_offers:
                    break
                raw_offers = await _fetch_scoped_offers(*scope)
                if raw_offers:
                    break

            if not raw_offers and not has_precise_location:
                raw_offers, _ = await _fetch_nearby_offers()

            apply_filters = False
            apply_sort = False
            apply_slice = False

        if not raw_offers:
            raw_offers = []

        for offer in raw_offers:
            try:
                original_price_sums = normalize_price(get_val(offer, "original_price", 0))
                discount_price_sums = normalize_price(get_val(offer, "discount_price", 0))
                store_rating = float(
                    get_val(offer, "store_rating")
                    or get_val(offer, "avg_rating")
                    or get_val(offer, "rating")
                    or (get_val(store_fallback, "rating") if store_fallback else 0)
                    or 0
                )

                offers.append(
                    OfferResponse(
                        id=int(get_val(offer, "id", 0) or get_val(offer, "offer_id", 0) or 0),
                        title=get_val(offer, "title", "Mahsulot"),
                        description=get_val(offer, "description"),
                        original_price=original_price_sums,
                        discount_price=discount_price_sums,
                        discount_percent=float(get_val(offer, "discount_percent", 0) or 0)
                        or _calc_discount_percent(original_price_sums, discount_price_sums),
                        quantity=float(get_val(offer, "quantity", 0) or 0),
                        unit=get_val(offer, "unit", "dona") or "dona",
                        category=get_val(offer, "category", "other") or "other",
                        store_id=int(get_val(offer, "store_id", 0) or 0),
                        store_name=get_val(offer, "store_name")
                        or get_val(offer, "name")
                        or (get_val(store_fallback, "name") if store_fallback else "")
                        or "",
                        store_address=get_val(offer, "store_address")
                        or get_val(offer, "address")
                        or (get_val(store_fallback, "address") if store_fallback else None),
                        store_rating=store_rating,
                        delivery_enabled=bool(
                            get_val(
                                offer,
                                "delivery_enabled",
                                get_val(store_fallback, "delivery_enabled", False),
                            )
                        ),
                        delivery_price=get_val(
                            offer, "delivery_price", get_val(store_fallback, "delivery_price")
                        ),
                        min_order_amount=get_val(
                            offer, "min_order_amount", get_val(store_fallback, "min_order_amount")
                        ),
                        photo=get_val(offer, "photo") or get_val(offer, "photo_id"),
                        expiry_date=str(get_val(offer, "expiry_date", ""))
                        if get_val(offer, "expiry_date")
                        else None,
                        available_from=get_val(offer, "available_from"),
                        available_until=get_val(offer, "available_until"),
                    )
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"Error parsing offer: {e}")
                continue

        if apply_filters:
            if min_price is not None:
                offers = [o for o in offers if o.discount_price >= min_price]
            if max_price is not None:
                offers = [o for o in offers if o.discount_price <= max_price]
            if min_discount is not None:
                offers = [o for o in offers if o.discount_percent >= min_discount]

        if apply_sort:
            if sort_by == "urgent":
                offers.sort(
                    key=lambda x: (
                        # 1) истекает раньше — выше
                        x.expiry_date or "9999-12-31",
                        # 2) меньший остаток — выше
                        x.quantity or 0,
                        # 3) большая скидка — выше
                        -(x.discount_percent or 0),
                    )
                )
            elif sort_by == "discount":
                offers.sort(key=lambda x: x.discount_percent, reverse=True)
            elif sort_by == "price_asc":
                offers.sort(key=lambda x: x.discount_price)
            elif sort_by == "price_desc":
                offers.sort(key=lambda x: x.discount_price, reverse=True)
            elif sort_by == "new":
                offers.sort(key=lambda x: x.id, reverse=True)

        if apply_slice:
            offers = offers[offset : offset + limit]

        offers_payload: list[dict[str, Any]] | None = None
        if cache and cache_key and cache_ttl > 0:
            offers_payload = [o.model_dump() for o in offers]

        if include_meta:
            total: int | None = None
            if not store_id and not search and hasattr(db, "count_offers_by_filters"):
                total = int(
                    (await _db_call(
                        db,
                        "count_offers_by_filters",
                        city=normalized_city,
                        region=region,
                        district=district,
                        category=category_filter,
                        min_price=storage_min_price,
                        max_price=storage_max_price,
                        min_discount=min_discount,
                    ))
                    or 0
                )
            if total == 0 and offers:
                total = None
            has_more = (
                len(offers) > 0 and (offset + len(offers) < total)
                if total is not None
                else (len(offers) == limit)
            )
            next_offset = offset + len(offers) if has_more else None
            response = OfferListResponse(
                items=offers,
                total=total,
                offset=offset,
                limit=limit,
                has_more=has_more,
                next_offset=next_offset,
            )
            if cache and cache_key and cache_ttl > 0:
                await cache.set(cache_key, response.model_dump(), ttl=cache_ttl)
            return response

        if cache and cache_key and cache_ttl > 0 and offers_payload is not None:
            await cache.set(cache_key, offers_payload, ttl=cache_ttl)
        return offers

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting offers: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/offers/{offer_id}", response_model=OfferResponse)
async def get_offer(offer_id: int, db=Depends(get_db)):
    """Get single offer by ID."""
    try:
        offer = (
            await _db_call(db, "get_offer", offer_id) if hasattr(db, "get_offer") else None
        )

        if not offer or not is_offer_active(offer):
            raise HTTPException(status_code=404, detail="Offer not found")

        store_fallback = (
            await _db_call(db, "get_store", get_val(offer, "store_id"))
            if hasattr(db, "get_store")
            else None
        )

        original_price_sums = normalize_price(get_val(offer, "original_price", 0))
        discount_price_sums = normalize_price(get_val(offer, "discount_price", 0))
        store_rating = float(
            get_val(offer, "store_rating")
            or get_val(offer, "avg_rating")
            or get_val(offer, "rating")
            or (get_val(store_fallback, "rating") if store_fallback else 0)
            or 0
        )

        return OfferResponse(
            id=int(get_val(offer, "id", 0) or get_val(offer, "offer_id", 0) or 0),
            title=get_val(offer, "title", "Mahsulot"),
            description=get_val(offer, "description"),
            original_price=original_price_sums,
            discount_price=discount_price_sums,
            discount_percent=float(get_val(offer, "discount_percent", 0) or 0)
            or _calc_discount_percent(original_price_sums, discount_price_sums),
            quantity=float(get_val(offer, "quantity", 0) or 0),
            unit=get_val(offer, "unit", "dona") or "dona",
            category=get_val(offer, "category", "other") or "other",
            store_id=int(get_val(offer, "store_id", 0) or 0),
            store_name=get_val(offer, "store_name")
            or get_val(offer, "name")
            or (get_val(store_fallback, "name") if store_fallback else "")
            or "",
            store_address=get_val(offer, "store_address")
            or get_val(offer, "address")
            or (get_val(store_fallback, "address") if store_fallback else None),
            store_rating=store_rating,
            delivery_enabled=bool(
                get_val(offer, "delivery_enabled", get_val(store_fallback, "delivery_enabled", False))
            ),
            delivery_price=get_val(offer, "delivery_price", get_val(store_fallback, "delivery_price")),
            min_order_amount=get_val(
                offer, "min_order_amount", get_val(store_fallback, "min_order_amount")
            ),
            photo=get_val(offer, "photo") or get_val(offer, "photo_id"),
            expiry_date=str(get_val(offer, "expiry_date", ""))
            if get_val(offer, "expiry_date")
            else None,
            available_from=get_val(offer, "available_from"),
            available_until=get_val(offer, "available_until"),
        )

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting offer {offer_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/flash-deals", response_model=list[OfferResponse])
async def get_flash_deals(
    city: str | None = Query(None, description="City to filter by"),
    region: str | None = Query(None, description="Region filter"),
    district: str | None = Query(None, description="District filter"),
    limit: int = Query(10, ge=1, le=50),
    db=Depends(get_db),
):
    """Get flash deals - high discount items expiring soon."""
    try:
        normalized_city = normalize_city(city) if city else None
        region = normalize_city(region) if region else None
        district = normalize_city(district) if district else None
        raw_offers = (
            await _db_call(
                db,
                "get_hot_offers",
                normalized_city,
                limit=100,
                offset=0,
                region=region,
                district=district,
            )
            if hasattr(db, "get_hot_offers")
            else []
        )

        # Fallback: if filters by region/district return nothing, retry by city only
        if not raw_offers and normalized_city and (region or district) and hasattr(db, "get_hot_offers"):
            raw_offers = await _db_call(db, "get_hot_offers", normalized_city, limit=100, offset=0)

        if not raw_offers:
            raw_offers = []

        offers: list[OfferResponse] = []
        today = datetime.now().date()
        max_expiry = today + timedelta(days=7)

        for offer in raw_offers:
            try:
                discount = float(get_val(offer, "discount_percent", 0) or 0)
                expiry_str = get_val(offer, "expiry_date")

                is_high_discount = discount >= 20
                is_expiring_soon = False

                if expiry_str:
                    try:
                        expiry = datetime.fromisoformat(str(expiry_str).split("T")[0]).date()
                        is_expiring_soon = today <= expiry <= max_expiry
                    except (ValueError, AttributeError):  # pragma: no cover - parsing safety
                        pass

                if is_high_discount or is_expiring_soon:
                    original_price_sums = normalize_price(get_val(offer, "original_price", 0))
                    discount_price_sums = normalize_price(get_val(offer, "discount_price", 0))
                    store_rating = float(
                        get_val(offer, "store_rating")
                        or get_val(offer, "avg_rating")
                        or get_val(offer, "rating")
                        or 0
                    )

                    offers.append(
                        OfferResponse(
                            id=int(get_val(offer, "id", 0) or get_val(offer, "offer_id", 0) or 0),
                            title=get_val(offer, "title", "Mahsulot"),
                            description=get_val(offer, "description"),
                            original_price=original_price_sums,
                            discount_price=discount_price_sums,
                            discount_percent=discount,
                            quantity=float(get_val(offer, "quantity", 0) or 0),
                            unit=get_val(offer, "unit", "dona") or "dona",
                            category=get_val(offer, "category", "other") or "other",
                            store_id=int(get_val(offer, "store_id", 0) or 0),
                            store_name=get_val(offer, "store_name") or get_val(offer, "name") or "",
                            store_address=get_val(offer, "store_address") or get_val(offer, "address"),
                            store_rating=store_rating,
                            photo=get_val(offer, "photo") or get_val(offer, "photo_id"),
                            expiry_date=str(expiry_str) if expiry_str else None,
                            available_from=get_val(offer, "available_from"),
                            available_until=get_val(offer, "available_until"),
                        )
                    )
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"Error parsing flash deal offer: {e}")
                continue

        offers.sort(key=lambda x: (-x.discount_percent, x.expiry_date or "9999"))

        return offers[:limit]

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting flash deals: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
