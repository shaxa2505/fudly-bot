from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from .common import (
    CATEGORIES,
    CategoryResponse,
    OfferResponse,
    get_current_user,
    get_db,
    get_val,
    logger,
    normalize_price,
)
from app.core.utils import normalize_city

router = APIRouter()


def _calc_discount_percent(original_price: float, discount_price: float) -> float:
    try:
        if original_price and original_price > 0 and discount_price >= 0 and original_price > discount_price:
            return float(round((1.0 - (discount_price / original_price)) * 100.0, 1))
    except Exception:  # pragma: no cover - defensive
        pass
    return 0.0


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
        quantity=int(get_val(offer, "quantity", 0) or 0),
        unit=get_val(offer, "unit", "dona") or "dona",
        category=get_val(offer, "category", "other") or "other",
        store_id=store_id,
        store_name=store_name,
        store_address=store_address,
        photo=photo,
        expiry_date=expiry_date,
    )


@router.get("/categories", response_model=list[CategoryResponse])
async def get_categories(
    city: str = Query("Toshkent", description="City to filter by"),
    db=Depends(get_db),
):
    """Get list of product categories with counts."""
    result: list[CategoryResponse] = []
    normalized_city = normalize_city(city)

    for cat in CATEGORIES:
        count = 0
        if cat["id"] != "all":
            try:
                offers = (
                    db.get_offers_by_category(cat["id"], normalized_city)
                    if hasattr(db, "get_offers_by_category")
                    else []
                )
                count = len(offers) if offers else 0
            except Exception:  # pragma: no cover - defensive
                count = 0
        else:
            try:
                count = (
                    db.count_hot_offers(normalized_city) if hasattr(db, "count_hot_offers") else 0
                )
            except Exception:  # pragma: no cover - defensive
                count = 0

        result.append(
            CategoryResponse(id=cat["id"], name=cat["name"], emoji=cat["emoji"], count=count)
        )

    return result


@router.get("/offers", response_model=list[OfferResponse])
async def get_offers(
    city: str = Query("Toshkent", description="City to filter by"),
    region: str | None = Query(None, description="Region filter"),
    district: str | None = Query(None, description="District filter"),
    category: str = Query("all", description="Category filter"),
    store_id: int | None = Query(None, description="Store ID filter"),
    search: str | None = Query(None, description="Search query"),
    min_price: float | None = Query(None, description="Minimum price filter"),
    max_price: float | None = Query(None, description="Maximum price filter"),
    min_discount: float | None = Query(None, description="Minimum discount percent"),
    sort_by: str = Query("discount", description="Sort by: discount, price_asc, price_desc, new"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get list of offers with advanced filters and sorting."""
    try:
        _ = user  # explicitly mark dependency as used
        normalized_city = normalize_city(city)
        offers: list[OfferResponse] = []
        store_fallback: dict | None = None

        apply_slice = True
        if store_id:
            raw_offers = db.get_store_offers(store_id) if hasattr(db, "get_store_offers") else []
            if hasattr(db, "get_store"):
                store_fallback = db.get_store(store_id)
        elif search:
            raw_offers = (
                db.search_offers(search, normalized_city) if hasattr(db, "search_offers") else []
            )
        elif category and category != "all":
            if hasattr(db, "get_offers_by_city_and_category"):
                raw_offers = db.get_offers_by_city_and_category(
                    city=normalized_city, category=category, region=region, district=district
                )
            elif hasattr(db, "get_offers_by_category"):
                raw_offers = db.get_offers_by_category(category, normalized_city)
            else:
                raw_offers = []
        else:
            raw_offers = (
                db.get_hot_offers(
                    normalized_city, limit=limit, offset=offset, region=region, district=district
                )
                if hasattr(db, "get_hot_offers")
                else []
            )
            apply_slice = False

        if not raw_offers:
            raw_offers = []

        for offer in raw_offers:
            try:
                original_price_sums = normalize_price(get_val(offer, "original_price", 0))
                discount_price_sums = normalize_price(get_val(offer, "discount_price", 0))

                offers.append(
                    OfferResponse(
                        id=int(get_val(offer, "id", 0) or get_val(offer, "offer_id", 0) or 0),
                        title=get_val(offer, "title", "Mahsulot"),
                        description=get_val(offer, "description"),
                        original_price=original_price_sums,
                        discount_price=discount_price_sums,
                        discount_percent=float(get_val(offer, "discount_percent", 0) or 0)
                        or _calc_discount_percent(original_price_sums, discount_price_sums),
                        quantity=int(get_val(offer, "quantity", 0) or 0),
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
                        photo=get_val(offer, "photo") or get_val(offer, "photo_id"),
                        expiry_date=str(get_val(offer, "expiry_date", ""))
                        if get_val(offer, "expiry_date")
                        else None,
                    )
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"Error parsing offer: {e}")
                continue

        if min_price is not None:
            offers = [o for o in offers if o.discount_price >= min_price]
        if max_price is not None:
            offers = [o for o in offers if o.discount_price <= max_price]
        if min_discount is not None:
            offers = [o for o in offers if o.discount_percent >= min_discount]

        if sort_by == "discount":
            offers.sort(key=lambda x: x.discount_percent, reverse=True)
        elif sort_by == "price_asc":
            offers.sort(key=lambda x: x.discount_price)
        elif sort_by == "price_desc":
            offers.sort(key=lambda x: x.discount_price, reverse=True)
        elif sort_by == "new":
            offers.sort(key=lambda x: x.id, reverse=True)

        if apply_slice:
            offers = offers[offset : offset + limit]

        return offers

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting offers: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/offers/{offer_id}", response_model=OfferResponse)
async def get_offer(offer_id: int, db=Depends(get_db)):
    """Get single offer by ID."""
    try:
        offer = db.get_offer(offer_id) if hasattr(db, "get_offer") else None

        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")

        store_fallback = (
            db.get_store(get_val(offer, "store_id")) if hasattr(db, "get_store") else None
        )

        original_price_sums = normalize_price(get_val(offer, "original_price", 0))
        discount_price_sums = normalize_price(get_val(offer, "discount_price", 0))

        return OfferResponse(
            id=int(get_val(offer, "id", 0) or get_val(offer, "offer_id", 0) or 0),
            title=get_val(offer, "title", "Mahsulot"),
            description=get_val(offer, "description"),
            original_price=original_price_sums,
            discount_price=discount_price_sums,
            discount_percent=float(get_val(offer, "discount_percent", 0) or 0)
            or _calc_discount_percent(original_price_sums, discount_price_sums),
            quantity=int(get_val(offer, "quantity", 0) or 0),
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
            photo=get_val(offer, "photo") or get_val(offer, "photo_id"),
            expiry_date=str(get_val(offer, "expiry_date", ""))
            if get_val(offer, "expiry_date")
            else None,
        )

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting offer {offer_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/flash-deals", response_model=list[OfferResponse])
async def get_flash_deals(
    city: str = Query("Toshkent", description="City to filter by"),
    region: str | None = Query(None, description="Region filter"),
    district: str | None = Query(None, description="District filter"),
    limit: int = Query(10, ge=1, le=50),
    db=Depends(get_db),
):
    """Get flash deals - high discount items expiring soon."""
    try:
        normalized_city = normalize_city(city)
        raw_offers = (
            db.get_hot_offers(
                normalized_city, limit=100, offset=0, region=region, district=district
            )
            if hasattr(db, "get_hot_offers")
            else []
        )

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

                    offers.append(
                        OfferResponse(
                            id=int(get_val(offer, "id", 0) or get_val(offer, "offer_id", 0) or 0),
                            title=get_val(offer, "title", "Mahsulot"),
                            description=get_val(offer, "description"),
                            original_price=original_price_sums,
                            discount_price=discount_price_sums,
                            discount_percent=discount,
                            quantity=int(get_val(offer, "quantity", 0) or 0),
                            unit=get_val(offer, "unit", "dona") or "dona",
                            category=get_val(offer, "category", "other") or "other",
                            store_id=int(get_val(offer, "store_id", 0) or 0),
                            store_name=get_val(offer, "store_name") or get_val(offer, "name") or "",
                            store_address=get_val(offer, "store_address") or get_val(offer, "address"),
                            photo=get_val(offer, "photo") or get_val(offer, "photo_id"),
                            expiry_date=str(expiry_str) if expiry_str else None,
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
