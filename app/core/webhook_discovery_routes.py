"""Discovery-related routes for webhook Mini App API (categories, search suggestions, stats)."""
from __future__ import annotations

from typing import Any

from aiohttp import web

from app.core.location_search import build_nearby_radius_steps
from app.core.utils import normalize_city
from app.core.webhook_api_utils import add_cors_headers
from app.core.webhook_helpers import API_CATEGORIES, expand_category_filter, get_offer_value
from logging_config import logger


def build_discovery_handlers(db: Any):
    async def api_categories(request: web.Request) -> web.Response:
        """GET /api/v1/categories - List categories."""
        def _parse_float(value: str | None) -> float | None:
            if value is None or value == "":
                return None
            try:
                return float(value)
            except ValueError:
                return None

        city = request.query.get("city", "")
        city = city.strip() if isinstance(city, str) else city
        city = city or None
        region = request.query.get("region", "")
        region = region.strip() if isinstance(region, str) else region
        region = region or None
        district = request.query.get("district", "")
        district = district.strip() if isinstance(district, str) else district
        district = district or None
        lat = _parse_float(request.query.get("lat") or request.query.get("latitude"))
        lon = _parse_float(request.query.get("lon") or request.query.get("longitude"))
        max_distance_km = _parse_float(request.query.get("max_distance_km"))
        normalized_city = normalize_city(city) if city else None
        normalized_region = normalize_city(region) if region else None
        normalized_district = normalize_city(district) if district else None
        nearby_radius_steps = build_nearby_radius_steps(max_distance_km)

        def _map_counts_to_payload(counts_map: dict[str, int]) -> list[dict[str, int | str]]:
            total_count = sum(int(value or 0) for value in counts_map.values())
            payload: list[dict[str, int | str]] = []
            for cat in API_CATEGORIES:
                if cat["id"] == "all":
                    count = total_count
                else:
                    category_filter = expand_category_filter(cat["id"]) or []
                    count = sum(int(counts_map.get(item, 0) or 0) for item in category_filter)
                payload.append(
                    {
                        "id": cat["id"],
                        "name": cat["name"],
                        "emoji": cat["emoji"],
                        "count": count,
                    }
                )
            return payload

        def _count_for_scope(
            category_filter: list[str] | None,
            city_scope: str | None,
            region_scope: str | None,
            district_scope: str | None,
        ) -> int:
            if hasattr(db, "count_offers_by_filters"):
                return int(
                    db.count_offers_by_filters(
                        city=city_scope,
                        region=region_scope,
                        district=district_scope,
                        category=category_filter,
                    )
                    or 0
                )
            if category_filter:
                if hasattr(db, "get_offers_by_city_and_category"):
                    offers = db.get_offers_by_city_and_category(
                        city=city_scope,
                        category=category_filter,
                        region=region_scope,
                        district=district_scope,
                        limit=1000,
                        offset=0,
                    ) or []
                    return len(offers)
                if hasattr(db, "get_offers_by_category"):
                    if isinstance(category_filter, (list, tuple)):
                        offers = []
                        for item in category_filter:
                            offers.extend(db.get_offers_by_category(item, city_scope) or [])
                        return len(offers)
                    offers = db.get_offers_by_category(category_filter, city_scope) or []
                    return len(offers)
                return 0
            if hasattr(db, "count_hot_offers"):
                return (
                    db.count_hot_offers(
                        city_scope,
                        region=region_scope,
                        district=district_scope,
                    )
                    or 0
                )
            return 0

        if (
            lat is not None
            and lon is not None
            and hasattr(db, "count_nearby_offers_by_category_grouped")
        ):
            for radius_km in nearby_radius_steps:
                try:
                    nearby_counts = (
                        db.count_nearby_offers_by_category_grouped(
                            latitude=lat,
                            longitude=lon,
                            max_distance_km=radius_km,
                        )
                        or {}
                    )
                except Exception:
                    nearby_counts = {}

                if sum(int(value or 0) for value in nearby_counts.values()) > 0:
                    return add_cors_headers(web.json_response(_map_counts_to_payload(nearby_counts)))

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

        result: list[dict[str, int | str]] = []
        if hasattr(db, "count_offers_by_category_grouped"):
            counts_map: dict[str, int] = {}
            for city_scope, region_scope, district_scope in scopes:
                try:
                    counts_map = (
                        db.count_offers_by_category_grouped(
                            city=city_scope,
                            region=region_scope,
                            district=district_scope,
                        )
                        or {}
                    )
                except Exception:
                    counts_map = {}
                if sum(int(value or 0) for value in counts_map.values()) > 0:
                    break
            result = _map_counts_to_payload(counts_map)
        else:
            for cat in API_CATEGORIES:
                count = 0
                category_filter = expand_category_filter(cat["id"])
                try:
                    for city_scope, region_scope, district_scope in scopes:
                        count = _count_for_scope(
                            category_filter if cat["id"] != "all" else None,
                            city_scope,
                            region_scope,
                            district_scope,
                        )
                        if count:
                            break
                except Exception:
                    pass

                result.append(
                    {
                        "id": cat["id"],
                        "name": cat["name"],
                        "emoji": cat["emoji"],
                        "count": count,
                    }
                )

        return add_cors_headers(web.json_response(result))

    async def api_search_suggestions(request: web.Request) -> web.Response:
        """GET /api/v1/search/suggestions - Search autocomplete suggestions."""
        query = request.query.get("query", "")
        city = request.query.get("city")
        region = request.query.get("region")
        district = request.query.get("district")
        limit_raw = request.query.get("limit", "5")
        try:
            limit = max(1, min(int(limit_raw), 10))
        except (TypeError, ValueError):
            limit = 5

        if not query or len(query) < 2:
            return add_cors_headers(web.json_response([]))

        city = city.strip() if isinstance(city, str) else city
        city = city or None
        region = region.strip() if isinstance(region, str) else region
        region = region or None
        district = district.strip() if isinstance(district, str) else district
        district = district or None

        normalized_city = normalize_city(city) if city else None
        normalized_region = normalize_city(region) if region else None
        normalized_district = normalize_city(district) if district else None
        fallback_scopes: list[tuple[str | None, str | None, str | None]] = []
        if normalized_district:
            fallback_scopes.append((None, normalized_region, normalized_district))
        if normalized_region:
            fallback_scopes.append((None, normalized_region, None))
        if normalized_city:
            fallback_scopes.append((normalized_city, None, None))
            if not normalized_region:
                fallback_scopes.append((None, normalized_city, None))
        fallback_scopes.append((None, None, None))
        suggestions: list[str] = []
        try:
            def _append_values(values: list[str]) -> bool:
                for value in values or []:
                    if value and value not in suggestions:
                        suggestions.append(value)
                        if len(suggestions) >= limit:
                            return True
                return False

            def _fill_from_scope(
                city_scope: str | None, region_scope: str | None, district_scope: str | None
            ) -> bool:
                if hasattr(db, "get_search_suggestions"):
                    values = (
                        db.get_search_suggestions(
                            query,
                            limit=limit,
                            city=city_scope,
                            region=region_scope,
                            district=district_scope,
                        )
                        or []
                    )
                    if _append_values(values):
                        return True
                elif hasattr(db, "get_offer_suggestions"):
                    values = (
                        db.get_offer_suggestions(
                            query,
                            limit=limit,
                            city=city_scope,
                            region=region_scope,
                            district=district_scope,
                        )
                        or []
                    )
                    if _append_values(values):
                        return True
                elif hasattr(db, "search_offers"):
                    offers = (
                        db.search_offers(
                            query,
                            city=city_scope,
                            limit=limit * 2,
                            region=region_scope,
                            district=district_scope,
                        )
                        or []
                    )
                    titles = {
                        get_offer_value(o, "title", "")
                        for o in offers
                        if get_offer_value(o, "title")
                    }
                    if _append_values(list(titles)[:limit]):
                        return True

                if len(suggestions) < limit and hasattr(db, "search_offers"):
                    offers = (
                        db.search_offers(
                            query,
                            city=city_scope,
                            limit=limit * 2,
                            region=region_scope,
                            district=district_scope,
                        )
                        or []
                    )
                    for offer in offers:
                        title = get_offer_value(offer, "title", "")
                        if title and title not in suggestions:
                            suggestions.append(title)
                            if len(suggestions) >= limit:
                                return True

                if len(suggestions) < limit and hasattr(db, "search_stores"):
                    stores = (
                        db.search_stores(
                            query,
                            city=city_scope,
                            limit=limit * 2,
                            region=region_scope,
                            district=district_scope,
                        )
                        or []
                    )
                    for store in stores:
                        name = get_offer_value(store, "name", "")
                        if name and name not in suggestions:
                            suggestions.append(name)
                            if len(suggestions) >= limit:
                                return True
                return len(suggestions) >= limit

            _fill_from_scope(normalized_city, normalized_region, normalized_district)

            if len(suggestions) < limit:
                seen_scopes: set[tuple[str | None, str | None, str | None]] = set()
                for scope in fallback_scopes:
                    if scope in seen_scopes:
                        continue
                    seen_scopes.add(scope)
                    if _fill_from_scope(*scope):
                        break
        except Exception as exc:
            logger.error("API search suggestions error: %s", exc)
            suggestions = []

        return add_cors_headers(web.json_response(suggestions[:limit]))

    async def api_hot_deals_stats(request: web.Request) -> web.Response:
        """GET /api/v1/stats/hot-deals - Stats for hot deals."""
        city = request.query.get("city")
        normalized_city = normalize_city(city) if city else None
        stats = {
            "total_offers": 0,
            "total_stores": 0,
            "avg_discount": 0.0,
            "max_discount": 0.0,
            "categories_count": len(API_CATEGORIES) - 1,
        }

        try:
            if hasattr(db, "get_hot_offers"):
                offers = db.get_hot_offers(normalized_city, limit=1000) or []
                stats["total_offers"] = len(offers)
                discounts: list[float] = []
                for offer in offers:
                    discount = float(get_offer_value(offer, "discount_percent", 0) or 0)
                    discounts.append(discount)
                if discounts:
                    stats["avg_discount"] = round(sum(discounts) / len(discounts), 1)
                    stats["max_discount"] = round(max(discounts), 1)

            if hasattr(db, "get_stores_by_city"):
                stores = db.get_stores_by_city(normalized_city)
                stats["total_stores"] = len(stores or [])
        except Exception as exc:
            logger.error("API hot deals stats error: %s", exc)

        return add_cors_headers(web.json_response(stats))

    return api_categories, api_search_suggestions, api_hot_deals_stats
