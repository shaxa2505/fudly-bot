from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query

from .common import CATEGORIES, get_db, get_val, logger
from app.core.utils import normalize_city
from app.core.caching import get_cache_service

router = APIRouter()


def _get_cache_ttl(env_name: str, default: int) -> int:
    raw = os.getenv(env_name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


@router.get("/search/suggestions")
async def get_search_suggestions(
    query: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(5, ge=1, le=10),
    city: str | None = Query(None, description="City filter"),
    region: str | None = Query(None, description="Region filter"),
    district: str | None = Query(None, description="District filter"),
    db=Depends(get_db),
):
    """Get search suggestions for autocomplete."""
    try:
        if not query or len(query) < 2:
            return []

        suggestions: list[str] = []
        normalized_city = normalize_city(city) if city else None
        normalized_region = normalize_city(region) if region else None
        normalized_district = normalize_city(district) if district else None
        cache_ttl = _get_cache_ttl("WEBAPP_CACHE_SUGGESTIONS_TTL", 30)
        cache_key = None
        cache = None
        if cache_ttl > 0:
            cache = get_cache_service(os.getenv("REDIS_URL"))
            cache_key = (
                "webapp:suggest:"
                f"{query.strip().lower()}:{normalized_city or ''}:{normalized_region or ''}:"
                f"{normalized_district or ''}:{limit}"
            )
            cached = await cache.get(cache_key)
            if cached is not None:
                return cached

        if hasattr(db, "get_search_suggestions"):
            suggestions = (
                db.get_search_suggestions(
                    query,
                    limit=limit,
                    city=normalized_city,
                    region=normalized_region,
                    district=normalized_district,
                )
                or []
            )
        elif hasattr(db, "get_offer_suggestions"):
            suggestions = (
                db.get_offer_suggestions(
                    query,
                    limit=limit,
                    city=normalized_city,
                    region=normalized_region,
                    district=normalized_district,
                )
                or []
            )
        elif hasattr(db, "search_offers"):
            offers = db.search_offers(
                query,
                limit=limit * 2,
                city=normalized_city,
                region=normalized_region,
                district=normalized_district,
            )
            if offers:
                titles = list(
                    {
                        o.get("title", "") if isinstance(o, dict) else getattr(o, "title", "")
                        for o in offers
                    }
                )
                suggestions.extend(titles[:limit])

        result = suggestions[:limit]
        if cache and cache_key and cache_ttl > 0:
            await cache.set(cache_key, result, ttl=cache_ttl)
        return result

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting search suggestions: {e}")
        return []


@router.get("/stats/hot-deals")
async def get_hot_deals_stats(city: str | None = Query(None), db=Depends(get_db)):
    """Get statistics about hot deals."""
    try:
        normalized_city = normalize_city(city)
        cache_ttl = _get_cache_ttl("WEBAPP_CACHE_STATS_TTL", 60)
        cache_key = None
        cache = None
        if cache_ttl > 0:
            cache = get_cache_service(os.getenv("REDIS_URL"))
            cache_key = f"webapp:stats_hot:{normalized_city or ''}"
            cached = await cache.get(cache_key)
            if cached is not None:
                return cached
        stats = {
            "total_offers": 0,
            "total_stores": 0,
            "avg_discount": 0.0,
            "max_discount": 0.0,
            "categories_count": len(CATEGORIES) - 1,
        }

        if hasattr(db, "get_hot_offers"):
            offers = db.get_hot_offers(normalized_city, limit=1000)
            if offers:
                stats["total_offers"] = len(offers)

                discounts: list[float] = []
                for offer in offers:
                    discount = float(get_val(offer, "discount_percent", 0) or 0)
                    discounts.append(discount)

                if discounts:
                    stats["avg_discount"] = round(sum(discounts) / len(discounts), 1)
                    stats["max_discount"] = round(max(discounts), 1)

        if hasattr(db, "get_stores_by_city"):
            stores = db.get_stores_by_city(normalized_city)
            if stores:
                stats["total_stores"] = len(stores)

        if cache and cache_key and cache_ttl > 0:
            await cache.set(cache_key, stats, ttl=cache_ttl)
        return stats

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting stats: {e}")
        return {
            "total_offers": 0,
            "total_stores": 0,
            "avg_discount": 0.0,
            "max_discount": 0.0,
            "categories_count": len(CATEGORIES) - 1,
        }


@router.get("/health")
async def health_check():
    """Health check endpoint for webapp API."""
    return {"status": "ok", "service": "fudly-webapp-api", "version": "2.0"}
