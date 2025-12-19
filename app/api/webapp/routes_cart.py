from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .common import CartItem, CartResponse, get_db, get_val, logger

router = APIRouter()


@router.get("/cart/calculate")
async def calculate_cart(
    offer_ids: str = Query(
        ..., description="Comma-separated offer IDs with quantities (id:qty,id:qty)"
    ),
    db=Depends(get_db),
):
    """Calculate cart total and get current prices."""
    try:
        items: list[CartItem] = []
        total = 0.0
        items_count = 0

        for item_str in offer_ids.split(","):
            if ":" not in item_str:
                continue
            offer_id_str, qty_str = item_str.split(":")
            offer_id = int(offer_id_str)
            quantity = int(qty_str)

            offer = db.get_offer(offer_id) if hasattr(db, "get_offer") else None
            if offer:
                price = float(get_val(offer, "discount_price", 0) or 0)
                items.append(
                    CartItem(
                        offer_id=offer_id,
                        quantity=quantity,
                        title=get_val(offer, "title", ""),
                        price=price,
                        photo=get_val(offer, "photo") or get_val(offer, "photo_id"),
                    )
                )
                total += price * quantity
                items_count += quantity

        return CartResponse(items=items, total=total, items_count=items_count)

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error calculating cart: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
