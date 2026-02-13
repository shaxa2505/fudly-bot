from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.cart_storage import CartItem as StorageCartItem
from app.core.cart_storage import cart_storage
from app.core.order_math import calc_items_total, calc_quantity

from .common import (
    CartItem as CalcCartItem,
    CartResponse,
    get_current_user,
    get_db,
    get_val,
    is_offer_active,
    logger,
    normalize_price,
)

router = APIRouter()


class CartStateRequestItem(BaseModel):
    offer_id: int
    quantity: float = Field(..., gt=0)


class CartStateRequest(BaseModel):
    items: list[CartStateRequestItem] = Field(default_factory=list)


class CartStateOffer(BaseModel):
    id: int
    title: str
    description: str | None = None
    discount_price: float
    original_price: float
    quantity: float
    unit: str = "piece"
    store_id: int
    store_name: str = ""
    store_address: str | None = None
    photo: str | None = None
    delivery_enabled: bool = False
    delivery_price: float | None = None
    available_from: Any | None = None
    available_until: Any | None = None
    pickup_time: str | None = None


class CartStateItem(BaseModel):
    offer_id: int
    quantity: float
    offer: CartStateOffer


class CartStateResponse(BaseModel):
    items: list[CartStateItem]
    total: float
    items_count: float


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _db_call(db: Any, name: str, *args: Any, **kwargs: Any) -> Any:
    if not hasattr(db, name):
        return None
    return await _maybe_await(getattr(db, name)(*args, **kwargs))


def _require_user_id(user: dict[str, Any]) -> int:
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def _build_offer_payload(offer: Any, store: Any | None = None) -> CartStateOffer:
    delivery_enabled = bool(
        get_val(offer, "delivery_enabled", get_val(store, "delivery_enabled", False))
    )
    delivery_price_raw = get_val(offer, "delivery_price", get_val(store, "delivery_price", None))
    delivery_price = normalize_price(delivery_price_raw) if delivery_price_raw is not None else None
    photo = get_val(offer, "photo") or get_val(offer, "photo_id")
    pickup_time = get_val(offer, "pickup_time")

    return CartStateOffer(
        id=int(get_val(offer, "id", 0) or get_val(offer, "offer_id", 0) or 0),
        title=str(get_val(offer, "title", "Mahsulot") or "Mahsulot"),
        description=get_val(offer, "description"),
        discount_price=normalize_price(get_val(offer, "discount_price", 0)),
        original_price=normalize_price(get_val(offer, "original_price", 0)),
        quantity=float(get_val(offer, "quantity", 0) or 0),
        unit=str(get_val(offer, "unit", "piece") or "piece"),
        store_id=int(get_val(offer, "store_id", 0) or 0),
        store_name=str(
            get_val(offer, "store_name")
            or get_val(offer, "name")
            or get_val(store, "name", "")
            or ""
        ),
        store_address=get_val(offer, "store_address")
        or get_val(offer, "address")
        or get_val(store, "address"),
        photo=str(photo) if photo else None,
        delivery_enabled=delivery_enabled,
        delivery_price=delivery_price,
        available_from=get_val(offer, "available_from"),
        available_until=get_val(offer, "available_until"),
        pickup_time=str(pickup_time) if pickup_time else None,
    )


def _build_storage_item(
    offer: Any,
    store: Any | None,
    quantity: float,
    *,
    added_at: float | None = None,
) -> StorageCartItem | None:
    store_id = int(get_val(offer, "store_id", 0) or 0)
    if store_id <= 0:
        return None

    try:
        max_quantity = float(get_val(offer, "quantity", 0) or 0)
    except (TypeError, ValueError):
        return None
    if max_quantity <= 0:
        return None

    try:
        safe_qty = float(quantity)
    except (TypeError, ValueError):
        return None
    if safe_qty <= 0:
        return None
    safe_qty = min(safe_qty, max_quantity)

    price = int(normalize_price(get_val(offer, "discount_price", 0)))
    original_price = int(normalize_price(get_val(offer, "original_price", price) or price))
    if price <= 0:
        price = max(0, original_price)
    if original_price <= 0:
        original_price = max(0, price)

    delivery_enabled = bool(
        get_val(offer, "delivery_enabled", get_val(store, "delivery_enabled", False))
    )
    delivery_price = int(
        normalize_price(
            get_val(offer, "delivery_price", get_val(store, "delivery_price", 0) or 0) or 0
        )
    )

    item_kwargs = {
        "offer_id": int(get_val(offer, "id", 0) or get_val(offer, "offer_id", 0) or 0),
        "store_id": store_id,
        "title": str(get_val(offer, "title", "") or ""),
        "price": int(price),
        "original_price": int(original_price),
        "quantity": float(safe_qty),
        "max_quantity": float(max_quantity),
        "store_name": str(
            get_val(offer, "store_name")
            or get_val(offer, "name")
            or get_val(store, "name", "")
            or ""
        ),
        "store_address": str(
            get_val(offer, "store_address")
            or get_val(offer, "address")
            or get_val(store, "address", "")
            or ""
        ),
        "photo": get_val(offer, "photo") or get_val(offer, "photo_id"),
        "unit": str(get_val(offer, "unit", "piece") or "piece"),
        "expiry_date": str(get_val(offer, "expiry_date", "") or ""),
        "delivery_enabled": delivery_enabled,
        "delivery_price": delivery_price,
    }
    if added_at is not None:
        item_kwargs["added_at"] = float(added_at)
    return StorageCartItem(**item_kwargs)


async def _build_cart_state_response(user_id: int, db: Any) -> CartStateResponse:
    raw_items = cart_storage.get_cart(user_id)
    if not raw_items:
        return CartStateResponse(items=[], total=0, items_count=0)

    changed = False
    normalized_items: list[StorageCartItem] = []
    response_items: list[CartStateItem] = []
    calc_items: list[dict[str, int | float]] = []

    cart_store_id: int | None = None

    for raw_item in raw_items:
        offer = await _db_call(db, "get_offer", int(raw_item.offer_id))
        if not offer or not is_offer_active(offer):
            changed = True
            continue

        store_id = int(get_val(offer, "store_id", raw_item.store_id) or 0)
        store = await _db_call(db, "get_store", store_id) if store_id else None

        normalized_item = _build_storage_item(
            offer,
            store,
            raw_item.quantity,
            added_at=raw_item.added_at,
        )
        if not normalized_item:
            changed = True
            continue

        if cart_store_id is None:
            cart_store_id = normalized_item.store_id
        elif normalized_item.store_id != cart_store_id:
            changed = True
            continue

        if raw_item.to_dict() != normalized_item.to_dict():
            changed = True

        normalized_items.append(normalized_item)
        response_items.append(
            CartStateItem(
                offer_id=normalized_item.offer_id,
                quantity=float(normalized_item.quantity),
                offer=_build_offer_payload(offer, store),
            )
        )
        calc_items.append(
            {"price": int(normalized_item.price), "quantity": float(normalized_item.quantity)}
        )

    if changed:
        cart_storage.replace_cart(user_id, normalized_items)

    total = calc_items_total(calc_items)
    items_count = calc_quantity(calc_items)
    return CartStateResponse(items=response_items, total=total, items_count=items_count)


@router.get("/cart/state", response_model=CartStateResponse)
async def get_cart_state(
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get normalized cart state from shared bot storage."""
    user_id = _require_user_id(user)
    try:
        return await _build_cart_state_response(user_id, db)
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Error getting cart state for user %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/cart/state", response_model=CartStateResponse)
async def replace_cart_state(
    payload: CartStateRequest,
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Replace shared cart state (used to sync WebApp and bot carts)."""
    user_id = _require_user_id(user)

    try:
        if not payload.items:
            cart_storage.clear_cart(user_id)
            return CartStateResponse(items=[], total=0, items_count=0)

        items_by_offer: dict[int, StorageCartItem] = {}
        store_id_guard: int | None = None

        for req_item in payload.items:
            offer = await _db_call(db, "get_offer", int(req_item.offer_id))
            if not offer or not is_offer_active(offer):
                continue

            store_id = int(get_val(offer, "store_id", 0) or 0)
            store = await _db_call(db, "get_store", store_id) if store_id else None

            existing_qty = (
                float(items_by_offer[req_item.offer_id].quantity)
                if req_item.offer_id in items_by_offer
                else 0.0
            )
            next_qty = existing_qty + float(req_item.quantity)

            built_item = _build_storage_item(offer, store, next_qty)
            if not built_item:
                continue

            if store_id_guard is None:
                store_id_guard = built_item.store_id
            elif built_item.store_id != store_id_guard:
                raise HTTPException(
                    status_code=400,
                    detail="Only one store per cart is supported",
                )

            items_by_offer[built_item.offer_id] = built_item

        normalized_items = list(items_by_offer.values())
        if normalized_items:
            cart_storage.replace_cart(user_id, normalized_items)
        else:
            cart_storage.clear_cart(user_id)

        return await _build_cart_state_response(user_id, db)

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Error replacing cart state for user %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/cart/calculate", response_model=CartResponse)
async def calculate_cart(
    offer_ids: str = Query(
        ..., description="Comma-separated offer IDs with quantities (id:qty,id:qty)"
    ),
    db=Depends(get_db),
):
    """Calculate cart total and get current prices."""
    try:
        items: list[CalcCartItem] = []
        calc_items: list[dict[str, int | float]] = []

        for item_str in offer_ids.split(","):
            if ":" not in item_str:
                continue
            offer_id_str, qty_str = item_str.split(":")
            offer_id = int(offer_id_str)
            try:
                quantity = float(qty_str)
            except (TypeError, ValueError):
                continue
            if quantity <= 0:
                continue

            offer = await _db_call(db, "get_offer", offer_id)
            if offer and is_offer_active(offer):
                price = normalize_price(get_val(offer, "discount_price", 0))
                items.append(
                    CalcCartItem(
                        offer_id=offer_id,
                        quantity=quantity,
                        title=get_val(offer, "title", ""),
                        price=price,
                        photo=get_val(offer, "photo") or get_val(offer, "photo_id"),
                    )
                )
                calc_items.append({"price": price, "quantity": quantity})

        total = calc_items_total(calc_items)
        items_count = calc_quantity(calc_items)

        return CartResponse(items=items, total=total, items_count=items_count)

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error calculating cart: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
