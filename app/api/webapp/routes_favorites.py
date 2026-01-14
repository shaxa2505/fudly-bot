from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .common import (
    FavoriteRequest,
    StoreResponse,
    get_current_user,
    get_db,
    get_val,
    is_offer_active,
    logger,
    normalize_price,
)

router = APIRouter()


def _to_store_response(store: object) -> StoreResponse:
    return StoreResponse(
        id=int(get_val(store, "id", 0) or get_val(store, "store_id", 0) or 0),
        name=get_val(store, "name", ""),
        address=get_val(store, "address"),
        city=get_val(store, "city"),
        region=get_val(store, "region"),
        district=get_val(store, "district"),
        business_type=get_val(store, "business_type") or get_val(store, "category") or "supermarket",
        rating=float(get_val(store, "avg_rating", 0) or get_val(store, "rating", 0) or 0),
        offers_count=int(get_val(store, "offers_count", 0) or 0),
        delivery_enabled=bool(get_val(store, "delivery_enabled", False)),
        delivery_price=normalize_price(get_val(store, "delivery_price", 0))
        if get_val(store, "delivery_price")
        else None,
        min_order_amount=normalize_price(get_val(store, "min_order_amount", 0))
        if get_val(store, "min_order_amount")
        else None,
        photo_url=get_val(store, "photo") or get_val(store, "photo_url"),
    )


def _resolve_store_id(request: FavoriteRequest, db: object) -> int:
    if request.store_id:
        return int(request.store_id)
    if not request.offer_id:
        raise HTTPException(status_code=400, detail="store_id or offer_id is required")
    offer = db.get_offer(request.offer_id) if hasattr(db, "get_offer") else None
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    store_id = int(get_val(offer, "store_id", 0) or 0)
    if not store_id:
        raise HTTPException(status_code=404, detail="Store not found")
    return store_id


@router.get("/favorites", response_model=list[StoreResponse])
async def get_favorites(db=Depends(get_db), user: dict = Depends(get_current_user)):
    """Get user's favorite stores."""
    try:
        user_id = user.get("id", 0)
        if user_id == 0:
            return []

        stores: list[StoreResponse] = []
        seen_ids: set[int] = set()

        if hasattr(db, "get_favorites"):
            raw_favorites = db.get_favorites(user_id) or []
            for store in raw_favorites:
                store_id = int(get_val(store, "store_id", 0) or get_val(store, "id", 0) or 0)
                if not store_id or store_id in seen_ids:
                    continue
                seen_ids.add(store_id)
                stores.append(_to_store_response(store))
        elif hasattr(db, "get_user_favorite_offers"):
            favorite_ids = db.get_user_favorite_offers(user_id) or []
            for offer_id in favorite_ids:
                try:
                    offer = db.get_offer(offer_id) if hasattr(db, "get_offer") else None
                    if not offer or not is_offer_active(offer):
                        continue
                    store_id = int(get_val(offer, "store_id", 0) or 0)
                    if not store_id or store_id in seen_ids:
                        continue
                    store = db.get_store(store_id) if hasattr(db, "get_store") else None
                    if not store:
                        continue
                    seen_ids.add(store_id)
                    stores.append(_to_store_response(store))
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning(f"Error loading favorite store from offer {offer_id}: {e}")
                    continue

        return stores

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting favorites: {e}")
        return []


@router.post("/favorites/add")
async def add_favorite(
    request: FavoriteRequest, db=Depends(get_db), user: dict = Depends(get_current_user)
):
    """Add store to favorites."""
    try:
        user_id = user.get("id", 0)
        if user_id == 0:
            raise HTTPException(status_code=401, detail="Authentication required")

        store_id = _resolve_store_id(request, db)
        if hasattr(db, "add_to_favorites"):
            db.add_to_favorites(user_id, store_id)
        elif hasattr(db, "add_favorite"):
            db.add_favorite(user_id, store_id)

        return {"status": "ok", "store_id": store_id}

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error adding favorite: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/favorites/remove")
async def remove_favorite(
    request: FavoriteRequest, db=Depends(get_db), user: dict = Depends(get_current_user)
):
    """Remove store from favorites."""
    try:
        user_id = user.get("id", 0)
        if user_id == 0:
            raise HTTPException(status_code=401, detail="Authentication required")

        store_id = _resolve_store_id(request, db)
        if hasattr(db, "remove_from_favorites"):
            db.remove_from_favorites(user_id, store_id)
        elif hasattr(db, "remove_favorite"):
            db.remove_favorite(user_id, store_id)

        return {"status": "ok", "store_id": store_id}

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error removing favorite: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
