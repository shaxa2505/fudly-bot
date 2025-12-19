from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .common import FavoriteRequest, OfferResponse, get_current_user, get_db, get_val, logger

router = APIRouter()


@router.get("/favorites", response_model=list[OfferResponse])
async def get_favorites(db=Depends(get_db), user: dict = Depends(get_current_user)):
    """Get user's favorite offers."""
    try:
        user_id = user.get("id", 0)
        if user_id == 0:
            return []

        if hasattr(db, "get_user_favorite_offers"):
            favorite_ids = db.get_user_favorite_offers(user_id)
        else:
            favorite_ids = []

        offers: list[OfferResponse] = []
        for offer_id in favorite_ids:
            try:
                offer = db.get_offer(offer_id) if hasattr(db, "get_offer") else None
                if offer:
                    store = (
                        db.get_store(get_val(offer, "store_id")) if hasattr(db, "get_store") else None
                    )
                    offers.append(
                        OfferResponse(
                            id=int(get_val(offer, "id", 0) or get_val(offer, "offer_id", 0) or 0),
                            title=get_val(offer, "title", "Без названия"),
                            description=get_val(offer, "description"),
                            original_price=float(get_val(offer, "original_price", 0) or 0),
                            discount_price=float(get_val(offer, "discount_price", 0) or 0),
                            discount_percent=float(get_val(offer, "discount_percent", 0) or 0),
                            quantity=int(get_val(offer, "quantity", 0) or 0),
                            unit=get_val(offer, "unit", "шт") or "шт",
                            category=get_val(offer, "category", "other") or "other",
                            store_id=int(get_val(offer, "store_id", 0) or 0),
                            store_name=get_val(offer, "store_name")
                            or (get_val(store, "name") if store else "")
                            or "",
                            store_address=get_val(offer, "store_address")
                            or get_val(offer, "address")
                            or (get_val(store, "address") if store else None),
                            photo=get_val(offer, "photo") or get_val(offer, "photo_id"),
                            expiry_date=str(get_val(offer, "expiry_date", ""))
                            if get_val(offer, "expiry_date")
                            else None,
                        )
                    )
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"Error loading favorite offer {offer_id}: {e}")
                continue

        return offers

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting favorites: {e}")
        return []


@router.post("/favorites/add")
async def add_favorite(
    request: FavoriteRequest, db=Depends(get_db), user: dict = Depends(get_current_user)
):
    """Add offer to favorites."""
    try:
        user_id = user.get("id", 0)
        if user_id == 0:
            raise HTTPException(status_code=401, detail="Authentication required")

        if hasattr(db, "add_user_favorite"):
            db.add_user_favorite(user_id, request.offer_id)

        return {"status": "ok", "offer_id": request.offer_id}

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error adding favorite: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/favorites/remove")
async def remove_favorite(
    request: FavoriteRequest, db=Depends(get_db), user: dict = Depends(get_current_user)
):
    """Remove offer from favorites."""
    try:
        user_id = user.get("id", 0)
        if user_id == 0:
            raise HTTPException(status_code=401, detail="Authentication required")

        if hasattr(db, "remove_user_favorite"):
            db.remove_user_favorite(user_id, request.offer_id)

        return {"status": "ok", "offer_id": request.offer_id}

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error removing favorite: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
