"""Offer and store routes for webhook Mini App API."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from typing import Any

from aiohttp import web

from app.core.location_search import build_nearby_radius_steps
from app.core.utils import normalize_city
from app.core.webhook_api_utils import add_cors_headers
from app.core.webhook_helpers import (
    _is_offer_active,
    expand_category_filter,
    get_offer_value,
    get_photo_url,
    offer_to_dict,
    store_to_dict,
)
from logging_config import logger


def build_offer_store_handlers(bot: Any, db: Any):
    async def api_offers(request: web.Request) -> web.Response:
        """GET /api/v1/offers - List offers."""

        def _parse_float(value: str | None) -> float | None:
            if value is None or value == "":
                return None
            try:
                return float(value)
            except ValueError:
                return None

        city = request.query.get("city", "")  # Empty = all cities
        region = request.query.get("region") or None
        district = request.query.get("district") or None
        category = request.query.get("category", "all")
        category_filter = expand_category_filter(category)
        store_id = request.query.get("store_id")
        search = request.query.get("search")
        limit = int(request.query.get("limit", "50"))
        offset = int(request.query.get("offset", "0"))
        sort_by = request.query.get("sort_by")
        min_price = _parse_float(request.query.get("min_price"))
        max_price = _parse_float(request.query.get("max_price"))
        min_discount = _parse_float(request.query.get("min_discount"))
        lat = _parse_float(request.query.get("lat") or request.query.get("latitude"))
        lon = _parse_float(request.query.get("lon") or request.query.get("longitude"))
        max_distance_km = _parse_float(request.query.get("max_distance_km"))
        include_meta = str(request.query.get("include_meta", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        price_unit = os.getenv("PRICE_STORAGE_UNIT", "sums").lower()
        if price_unit == "kopeks":
            if min_price is not None:
                min_price *= 100
            if max_price is not None:
                max_price *= 100

        city = city.strip() if isinstance(city, str) else city
        city = city or None
        region = region.strip() if isinstance(region, str) else region
        region = region or None
        district = district.strip() if isinstance(district, str) else district
        district = district or None

        city = normalize_city(city) if city else None
        region = normalize_city(region) if region else None
        district = normalize_city(district) if district else None

        logger.info(f"API /offers request: city={city}, category={category}, limit={limit}")

        try:
            raw_offers: list[Any] = []
            location_strategy: str | None = None
            used_radius_km: float | None = None
            used_fallback = False
            selected_scope_for_count: tuple[str | None, str | None, str | None] | None = None

            if store_id:
                if hasattr(db, "get_store_offers"):
                    raw_offers = db.get_store_offers(int(store_id)) or []
                    logger.info(f"get_store_offers({store_id}) returned {len(raw_offers)} items")
                location_strategy = "store"
            elif search:
                if hasattr(db, "search_offers"):

                    def _search_scoped(
                        city_scope: str | None,
                        region_scope: str | None,
                        district_scope: str | None,
                    ) -> list[Any]:
                        return (
                            db.search_offers(
                                search,
                                city_scope,
                                limit=limit,
                                offset=offset,
                                region=region_scope,
                                district=district_scope,
                                min_price=min_price,
                                max_price=max_price,
                                min_discount=min_discount,
                                category=category_filter,
                                sort_by=sort_by,
                            )
                            or []
                        )

                    raw_offers = _search_scoped(city, region, district)
                    if not raw_offers:
                        scopes: list[tuple[str | None, str | None, str | None]] = []
                        if district:
                            scopes.append((None, region, district))
                        if region:
                            scopes.append((None, region, None))
                        if city:
                            scopes.append((city, None, None))
                            if not region:
                                scopes.append((None, city, None))
                        scopes.append((None, None, None))

                        seen: set[tuple[str | None, str | None, str | None]] = set()
                        for scope in scopes:
                            if scope in seen:
                                continue
                            seen.add(scope)
                            raw_offers = _search_scoped(*scope)
                            if raw_offers:
                                break
                    logger.info(f"search_offers returned {len(raw_offers)} items")
                location_strategy = "search"
            else:

                def _fetch_scoped_offers(
                    city_scope: str | None, region_scope: str | None, district_scope: str | None
                ) -> list[Any]:
                    if category_filter:
                        if hasattr(db, "get_offers_by_city_and_category"):
                            return (
                                db.get_offers_by_city_and_category(
                                    city_scope,
                                    category_filter,
                                    limit=limit,
                                    offset=offset,
                                    region=region_scope,
                                    district=district_scope,
                                    sort_by=sort_by,
                                    min_price=min_price,
                                    max_price=max_price,
                                    min_discount=min_discount,
                                )
                                or []
                            )
                        if hasattr(db, "get_hot_offers"):
                            all_offers = (
                                db.get_hot_offers(
                                    city_scope,
                                    limit=100,
                                    offset=0,
                                    region=region_scope,
                                    district=district_scope,
                                    sort_by=sort_by,
                                    min_price=min_price,
                                    max_price=max_price,
                                    min_discount=min_discount,
                                )
                                or []
                            )
                            if isinstance(category_filter, (list, tuple)):
                                return [
                                    o
                                    for o in all_offers
                                    if get_offer_value(o, "category") in category_filter
                                ][:limit]
                            return [
                                o
                                for o in all_offers
                                if get_offer_value(o, "category") == category_filter
                            ][:limit]
                        return []
                    if hasattr(db, "get_hot_offers"):
                        return (
                            db.get_hot_offers(
                                city_scope,
                                limit=limit,
                                offset=offset,
                                region=region_scope,
                                district=district_scope,
                                sort_by=sort_by,
                                min_price=min_price,
                                max_price=max_price,
                                min_discount=min_discount,
                            )
                            or []
                        )
                    return []

                def _fetch_nearby_offers() -> tuple[list[Any], float | None]:
                    if lat is None or lon is None or not hasattr(db, "get_nearby_offers"):
                        return [], None
                    for radius_km in build_nearby_radius_steps(max_distance_km):
                        nearby = (
                            db.get_nearby_offers(
                                latitude=lat,
                                longitude=lon,
                                limit=limit,
                                offset=offset,
                                category=category_filter,
                                sort_by=sort_by,
                                min_price=min_price,
                                max_price=max_price,
                                min_discount=min_discount,
                                max_distance_km=radius_km,
                            )
                            or []
                        )
                        if nearby:
                            return nearby, radius_km
                    return [], None

                nearby_attempted = False
                nearby_found = False
                scoped_found = False
                has_precise_location = lat is not None and lon is not None
                if has_precise_location:
                    nearby_attempted = True
                    raw_offers, used_radius_km = _fetch_nearby_offers()
                    nearby_found = bool(raw_offers)
                    if nearby_found:
                        location_strategy = "nearby"

                scopes: list[tuple[str | None, str | None, str | None]] = []
                if district:
                    scopes.append((None, region, district))
                if region:
                    scopes.append((None, region, None))
                if city:
                    scopes.append((city, None, None))
                    if not region:
                        scopes.append((None, city, None))
                if not scopes:
                    scopes.append((None, None, None))

                seen: set[tuple[str | None, str | None, str | None]] = set()
                for scope in scopes:
                    if scope in seen:
                        continue
                    seen.add(scope)
                    if raw_offers:
                        break
                    raw_offers = _fetch_scoped_offers(*scope)
                    if raw_offers:
                        scoped_found = True
                        selected_scope_for_count = scope
                        location_strategy = "scope"
                        break

                if not raw_offers and not has_precise_location:
                    nearby_attempted = True
                    raw_offers, used_radius_km = _fetch_nearby_offers()
                    nearby_found = bool(raw_offers)
                    if nearby_found:
                        location_strategy = "nearby"

                if scoped_found and has_precise_location and nearby_attempted and not nearby_found:
                    used_fallback = True

            # Convert offers with photo URLs (parallel loading)
            async def load_offer_with_photo(o: Any) -> dict:
                photo_id = get_offer_value(o, "photo_id")
                photo_url = await get_photo_url(bot, photo_id) if photo_id else None
                return offer_to_dict(o, photo_url)

            offers = await asyncio.gather(*[load_offer_with_photo(o) for o in raw_offers])

            logger.info(f"Returning {len(offers)} offers")
            if include_meta:
                total = None
                if not store_id and not search:
                    if (
                        location_strategy == "nearby"
                        and lat is not None
                        and lon is not None
                        and used_radius_km is not None
                        and hasattr(db, "count_nearby_offers")
                    ):
                        total = int(
                            db.count_nearby_offers(
                                latitude=lat,
                                longitude=lon,
                                max_distance_km=used_radius_km,
                                category=category_filter,
                                min_price=min_price,
                                max_price=max_price,
                                min_discount=min_discount,
                            )
                            or 0
                        )
                    elif location_strategy != "nearby" and hasattr(db, "count_offers_by_filters"):
                        count_city = city
                        count_region = region
                        count_district = district
                        if location_strategy == "scope" and selected_scope_for_count is not None:
                            count_city, count_region, count_district = selected_scope_for_count
                        total = int(
                            db.count_offers_by_filters(
                                city=count_city,
                                region=count_region,
                                district=count_district,
                                category=category_filter,
                                min_price=min_price,
                                max_price=max_price,
                                min_discount=min_discount,
                            )
                            or 0
                        )
                    if total is not None and total == 0 and offers:
                        total = None
                has_more = len(offers) == limit
                if total is not None:
                    has_more = len(offers) > 0 and (offset + len(offers) < total)
                next_offset = offset + len(offers) if has_more else None
                payload = {
                    "items": offers,
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                    "has_more": has_more,
                    "next_offset": next_offset,
                    "location_strategy": location_strategy,
                    "used_radius_km": used_radius_km,
                    "used_fallback": used_fallback,
                }
                return add_cors_headers(web.json_response(payload))
            return add_cors_headers(web.json_response(offers))

        except Exception as e:
            logger.error(f"API offers error: {e}", exc_info=True)
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_offer_detail(request: web.Request) -> web.Response:
        """GET /api/v1/offers/{offer_id} - Get single offer."""
        offer_id = int(request.match_info["offer_id"])

        try:
            offer = None
            if hasattr(db, "get_offer"):
                offer = db.get_offer(offer_id)

            if not offer:
                return add_cors_headers(web.json_response({"error": "Not found"}, status=404))
            if not _is_offer_active(offer):
                return add_cors_headers(web.json_response({"error": "Not found"}, status=404))

            # Convert photo_id to URL
            photo_id = get_offer_value(offer, "photo_id")
            photo_url = await get_photo_url(bot, photo_id) if photo_id else None

            return add_cors_headers(web.json_response(offer_to_dict(offer, photo_url)))

        except Exception as e:
            logger.error(f"API offer detail error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_flash_deals(request: web.Request) -> web.Response:
        """GET /api/v1/flash-deals - High discount or expiring soon offers."""
        city = request.query.get("city")
        region = request.query.get("region") or None
        district = request.query.get("district") or None
        limit_raw = request.query.get("limit", "10")
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        normalized_city = normalize_city(city) if city else None
        normalized_region = normalize_city(region) if region else None
        normalized_district = normalize_city(district) if district else None
        try:
            raw_offers = (
                db.get_hot_offers(
                    normalized_city,
                    limit=100,
                    offset=0,
                    region=normalized_region,
                    district=normalized_district,
                )
                if hasattr(db, "get_hot_offers")
                else []
            )
            if (
                not raw_offers
                and normalized_city
                and (normalized_region or normalized_district)
                and hasattr(db, "get_hot_offers")
            ):
                raw_offers = db.get_hot_offers(normalized_city, limit=100, offset=0)
            if not raw_offers:
                raw_offers = []

            today = datetime.now().date()
            max_expiry = today + timedelta(days=7)
            filtered: list[tuple[Any, float, str | None]] = []

            for offer in raw_offers:
                try:
                    discount = float(get_offer_value(offer, "discount_percent", 0) or 0)
                    if not discount:
                        original_price = float(get_offer_value(offer, "original_price", 0) or 0)
                        discount_price = float(get_offer_value(offer, "discount_price", 0) or 0)
                        if (
                            original_price
                            and original_price > 0
                            and discount_price >= 0
                            and original_price > discount_price
                        ):
                            discount = round(
                                (1.0 - (discount_price / original_price)) * 100.0, 1
                            )

                    expiry_str = get_offer_value(offer, "expiry_date")
                    is_expiring_soon = False
                    if expiry_str:
                        try:
                            expiry = datetime.fromisoformat(str(expiry_str).split("T")[0]).date()
                            is_expiring_soon = today <= expiry <= max_expiry
                        except (ValueError, AttributeError):
                            pass

                    if discount >= 20 or is_expiring_soon:
                        filtered.append((offer, discount, expiry_str))
                except Exception as exc:
                    logger.warning("Flash deals filter error: %s", exc)
                    continue

            filtered.sort(key=lambda item: (-item[1], str(item[2] or "9999")))
            selected = filtered[:limit]

            async def load_offer_with_photo(item: tuple[Any, float, str | None]) -> dict:
                offer, discount, _expiry = item
                photo_id = get_offer_value(offer, "photo_id") or get_offer_value(offer, "photo")
                photo_url = await get_photo_url(bot, photo_id) if photo_id else None
                offer_dict = offer_to_dict(offer, photo_url)
                if discount and not offer_dict.get("discount_percent"):
                    offer_dict["discount_percent"] = discount
                return offer_dict

            offers = await asyncio.gather(*[load_offer_with_photo(item) for item in selected])
            return add_cors_headers(web.json_response(offers))

        except Exception as e:
            logger.error(f"API flash deals error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_stores(request: web.Request) -> web.Response:
        """GET /api/v1/stores - List stores."""

        def _parse_float(value: str | None) -> float | None:
            if value is None or value == "":
                return None
            try:
                return float(value)
            except ValueError:
                return None

        city = request.query.get("city", "")  # Empty = all cities
        region = request.query.get("region") or None
        district = request.query.get("district") or None
        business_type = request.query.get("business_type")
        lat = _parse_float(request.query.get("lat") or request.query.get("latitude"))
        lon = _parse_float(request.query.get("lon") or request.query.get("longitude"))
        city = city.strip() if isinstance(city, str) else city
        city = city or None
        region = region.strip() if isinstance(region, str) else region
        region = region or None
        district = district.strip() if isinstance(district, str) else district
        district = district or None

        city = normalize_city(city) if city else None
        region = normalize_city(region) if region else None
        district = normalize_city(district) if district else None

        try:
            raw_stores: list[Any] = []

            # Get stores from database with offers count
            if hasattr(db, "get_stores_by_location"):

                def _fetch_scoped_stores(
                    city_scope: str | None, region_scope: str | None, district_scope: str | None
                ) -> list[Any]:
                    return db.get_stores_by_location(
                        city=city_scope,
                        region=region_scope,
                        district=district_scope,
                        business_type=business_type,
                    )

                scopes: list[tuple[str | None, str | None, str | None]] = []
                if district:
                    scopes.append((None, region, district))
                if region:
                    scopes.append((None, region, None))
                if city:
                    scopes.append((city, None, None))
                    if not region:
                        scopes.append((None, city, None))
                if not scopes:
                    scopes.append((None, None, None))

                seen: set[tuple[str | None, str | None, str | None]] = set()
                for scope in scopes:
                    if scope in seen:
                        continue
                    seen.add(scope)
                    raw_stores = _fetch_scoped_stores(*scope) or []
                    if raw_stores:
                        break

                if (
                    not raw_stores
                    and lat is not None
                    and lon is not None
                    and hasattr(db, "get_nearby_stores")
                ):
                    raw_stores = (
                        db.get_nearby_stores(
                            latitude=lat,
                            longitude=lon,
                            business_type=business_type,
                            limit=200,
                            offset=0,
                        )
                        or []
                    )
            elif hasattr(db, "get_connection"):
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    base_query = """
                        SELECT s.*, COALESCE(oc.offer_count, 0) as offers_count
                        FROM stores s
                        LEFT JOIN (
                            SELECT store_id, COUNT(*) as offer_count
                            FROM offers
                            WHERE status = 'active'
                            GROUP BY store_id
                        ) oc ON s.store_id = oc.store_id
                        WHERE (s.status = 'active' OR s.status = 'approved')
                    """
                    if city:
                        cursor.execute(base_query + " AND s.city = %s", (city,))
                    else:
                        cursor.execute(base_query)
                    columns = [desc[0] for desc in cursor.description]
                    raw_stores = [dict(zip(columns, row)) for row in cursor.fetchall()]

            # Convert stores with photo URLs (parallel loading)
            async def load_store_with_photo(s: Any) -> dict:
                photo_id = get_offer_value(s, "photo")
                photo_url = await get_photo_url(bot, photo_id) if photo_id else None
                return store_to_dict(s, photo_url)

            stores = await asyncio.gather(*[load_store_with_photo(s) for s in raw_stores])

            logger.info(f"API /stores: returning {len(stores)} stores")
            return add_cors_headers(web.json_response(stores))

        except Exception as e:
            logger.error(f"API stores error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_store_detail(request: web.Request) -> web.Response:
        """GET /api/v1/stores/{store_id} - Store details."""
        store_id_raw = request.match_info.get("store_id")
        try:
            store_id = int(store_id_raw)
        except (TypeError, ValueError):
            return add_cors_headers(web.json_response({"error": "Invalid store_id"}, status=400))

        try:
            store = db.get_store(store_id) if hasattr(db, "get_store") else None
            if not store:
                return add_cors_headers(web.json_response({"error": "Store not found"}, status=404))

            offers_count = int(get_offer_value(store, "offers_count", 0) or 0)
            if offers_count == 0 and hasattr(db, "get_store_offers"):
                try:
                    offers_count = len(db.get_store_offers(store_id) or [])
                except Exception:
                    offers_count = 0

            rating = float(
                get_offer_value(store, "avg_rating", 0) or get_offer_value(store, "rating", 0) or 0
            )
            if rating == 0.0 and hasattr(db, "get_store_average_rating"):
                try:
                    rating = float(db.get_store_average_rating(store_id) or 0)
                except Exception:
                    rating = 0.0

            photo_id = get_offer_value(store, "photo")
            photo_url = await get_photo_url(bot, photo_id) if photo_id else None
            store_dict = store_to_dict(store, photo_url)
            store_dict["offers_count"] = offers_count
            store_dict["rating"] = rating

            region = get_offer_value(store, "region")
            if region is not None:
                store_dict["region"] = region
            district = get_offer_value(store, "district")
            if district is not None:
                store_dict["district"] = district

            return add_cors_headers(web.json_response(store_dict))

        except Exception as e:
            logger.error(f"API store detail error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    return api_offers, api_offer_detail, api_flash_deals, api_stores, api_store_detail
