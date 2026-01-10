from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .common import CATEGORIES, get_db, get_val, logger
from app.core.utils import normalize_city

router = APIRouter()


@router.get("/search/suggestions")
async def get_search_suggestions(
    query: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(5, ge=1, le=10),
    db=Depends(get_db),
):
    """Get search suggestions for autocomplete."""
    try:
        if not query or len(query) < 2:
            return []

        suggestions: list[str] = []

        if hasattr(db, "search_offers"):
            offers = db.search_offers(query, limit=limit * 2)
            if offers:
                titles = list(
                    {
                        o.get("title", "") if isinstance(o, dict) else getattr(o, "title", "")
                        for o in offers
                    }
                )
                suggestions.extend(titles[:limit])

        return suggestions[:limit]

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting search suggestions: {e}")
        return []


@router.get("/stats/hot-deals")
async def get_hot_deals_stats(city: str | None = Query(None), db=Depends(get_db)):
    """Get statistics about hot deals."""
    try:
        normalized_city = normalize_city(city)
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
