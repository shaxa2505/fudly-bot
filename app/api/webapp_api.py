"""
FastAPI endpoints for Telegram Mini App.

Provides REST API for:
- Getting offers/products with filters
- Categories
- Stores
- Creating orders
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any
from urllib.parse import parse_qsl, unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from app.core.config import load_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["webapp"])

settings = load_settings()


# =============================================================================
# Pydantic Models
# =============================================================================


class OfferResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    original_price: float
    discount_price: float
    discount_percent: float
    quantity: int
    category: str
    store_id: int
    store_name: str
    store_address: str | None = None
    photo: str | None = None
    expiry_date: str | None = None


class StoreResponse(BaseModel):
    id: int
    name: str
    address: str | None = None
    city: str | None = None
    business_type: str
    rating: float = 0.0
    offers_count: int = 0


class CategoryResponse(BaseModel):
    id: str
    name: str
    emoji: str
    count: int = 0


class OrderItem(BaseModel):
    offer_id: int
    quantity: int


class CreateOrderRequest(BaseModel):
    items: list[OrderItem]
    user_id: int
    delivery_address: str | None = None
    phone: str | None = None
    comment: str | None = None


class OrderResponse(BaseModel):
    order_id: int
    status: str
    total: float
    items_count: int


# =============================================================================
# Telegram Init Data Validation
# =============================================================================


def validate_init_data(init_data: str, bot_token: str) -> dict[str, Any] | None:
    """
    Validate Telegram WebApp initData.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))

        if "hash" not in parsed:
            return None

        received_hash = parsed.pop("hash")

        # Create data check string
        data_check_arr = sorted([f"{k}={v}" for k, v in parsed.items()])
        data_check_string = "\n".join(data_check_arr)

        # Create secret key
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()

        # Calculate hash
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if calculated_hash != received_hash:
            logger.warning("Invalid initData hash")
            return None

        # Parse user data
        if "user" in parsed:
            parsed["user"] = json.loads(unquote(parsed["user"]))

        return parsed

    except Exception as e:
        logger.error(f"Error validating initData: {e}")
        return None


async def get_current_user(
    x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any] | None:
    """
    Dependency to validate Telegram initData and extract user.
    For development, allows requests without validation.
    """
    if not x_telegram_init_data:
        # Allow unauthenticated access for development/testing
        return {"id": 0, "first_name": "Guest"}

    bot_token = settings.bot_token
    validated = validate_init_data(x_telegram_init_data, bot_token)

    if not validated:
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    return validated.get("user", {"id": 0, "first_name": "Guest"})


# =============================================================================
# Database dependency (will be injected from main app)
# =============================================================================

_db_instance = None
_offer_service = None


def set_db_instance(db: Any, offer_service: Any = None):
    """Set database instance for API routes."""
    global _db_instance, _offer_service
    _db_instance = db
    _offer_service = offer_service


def get_db():
    """Get database instance."""
    if _db_instance is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    return _db_instance


def get_offer_service():
    """Get offer service instance."""
    return _offer_service


# =============================================================================
# Categories
# =============================================================================

CATEGORIES = [
    {"id": "all", "name": "Все", "emoji": "🔥"},
    {"id": "dairy", "name": "Молочные", "emoji": "🥛"},
    {"id": "bakery", "name": "Выпечка", "emoji": "🍞"},
    {"id": "meat", "name": "Мясо", "emoji": "🥩"},
    {"id": "fruits", "name": "Фрукты", "emoji": "🍎"},
    {"id": "vegetables", "name": "Овощи", "emoji": "🥕"},
    {"id": "drinks", "name": "Напитки", "emoji": "🥤"},
    {"id": "sweets", "name": "Сладости", "emoji": "🍰"},
    {"id": "frozen", "name": "Заморозка", "emoji": "🧊"},
    {"id": "other", "name": "Другое", "emoji": "📦"},
]


@router.get("/categories", response_model=list[CategoryResponse])
async def get_categories(
    city: str = Query("Ташкент", description="City to filter by"), db=Depends(get_db)
):
    """Get list of product categories with counts."""
    result = []

    for cat in CATEGORIES:
        count = 0
        if cat["id"] != "all":
            try:
                # Count offers in this category
                offers = (
                    db.get_offers_by_category(cat["id"], city)
                    if hasattr(db, "get_offers_by_category")
                    else []
                )
                count = len(offers) if offers else 0
            except Exception:
                count = 0
        else:
            # Count all offers
            try:
                count = db.count_hot_offers(city) if hasattr(db, "count_hot_offers") else 0
            except Exception:
                count = 0

        result.append(
            CategoryResponse(id=cat["id"], name=cat["name"], emoji=cat["emoji"], count=count)
        )

    return result


# =============================================================================
# Offers
# =============================================================================


@router.get("/offers", response_model=list[OfferResponse])
async def get_offers(
    city: str = Query("Ташкент", description="City to filter by"),
    category: str = Query("all", description="Category filter"),
    store_id: int | None = Query(None, description="Store ID filter"),
    search: str | None = Query(None, description="Search query"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get list of offers with filters."""
    try:
        offers = []

        # Get offers based on filters
        if store_id:
            raw_offers = db.get_store_offers(store_id) if hasattr(db, "get_store_offers") else []
        elif search:
            raw_offers = db.search_offers(search, city) if hasattr(db, "search_offers") else []
        elif category and category != "all":
            raw_offers = (
                db.get_offers_by_category(category, city)
                if hasattr(db, "get_offers_by_category")
                else []
            )
        else:
            raw_offers = (
                db.get_hot_offers(city, limit=limit, offset=offset)
                if hasattr(db, "get_hot_offers")
                else []
            )

        if not raw_offers:
            raw_offers = []

        # Convert to response format
        for offer in raw_offers:
            try:
                # Handle both dict and object access
                def get_val(obj, key, default=None):
                    if isinstance(obj, dict):
                        return obj.get(key, default)
                    return getattr(obj, key, default)

                offers.append(
                    OfferResponse(
                        id=get_val(offer, "id", 0),
                        title=get_val(offer, "title", "Без названия"),
                        description=get_val(offer, "description"),
                        original_price=float(get_val(offer, "original_price", 0) or 0),
                        discount_price=float(get_val(offer, "discount_price", 0) or 0),
                        discount_percent=float(get_val(offer, "discount_percent", 0) or 0),
                        quantity=int(get_val(offer, "quantity", 0) or 0),
                        category=get_val(offer, "category", "other") or "other",
                        store_id=int(get_val(offer, "store_id", 0) or 0),
                        store_name=get_val(offer, "store_name", "") or "",
                        store_address=get_val(offer, "store_address"),
                        photo=get_val(offer, "photo"),
                        expiry_date=str(get_val(offer, "expiry_date", ""))
                        if get_val(offer, "expiry_date")
                        else None,
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing offer: {e}")
                continue

        return offers

    except Exception as e:
        logger.error(f"Error getting offers: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/offers/{offer_id}", response_model=OfferResponse)
async def get_offer(offer_id: int, db=Depends(get_db)):
    """Get single offer by ID."""
    try:
        offer = db.get_offer(offer_id) if hasattr(db, "get_offer") else None

        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")

        def get_val(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        return OfferResponse(
            id=get_val(offer, "id", 0),
            title=get_val(offer, "title", "Без названия"),
            description=get_val(offer, "description"),
            original_price=float(get_val(offer, "original_price", 0) or 0),
            discount_price=float(get_val(offer, "discount_price", 0) or 0),
            discount_percent=float(get_val(offer, "discount_percent", 0) or 0),
            quantity=int(get_val(offer, "quantity", 0) or 0),
            category=get_val(offer, "category", "other") or "other",
            store_id=int(get_val(offer, "store_id", 0) or 0),
            store_name=get_val(offer, "store_name", "") or "",
            store_address=get_val(offer, "store_address"),
            photo=get_val(offer, "photo"),
            expiry_date=str(get_val(offer, "expiry_date", ""))
            if get_val(offer, "expiry_date")
            else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting offer {offer_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# Stores
# =============================================================================


@router.get("/stores", response_model=list[StoreResponse])
async def get_stores(
    city: str = Query("Ташкент", description="City to filter by"),
    business_type: str | None = Query(None, description="Business type filter"),
    db=Depends(get_db),
):
    """Get list of stores."""
    try:
        if business_type:
            raw_stores = (
                db.get_stores_by_business_type(business_type, city)
                if hasattr(db, "get_stores_by_business_type")
                else []
            )
        else:
            raw_stores = db.get_all_stores(city) if hasattr(db, "get_all_stores") else []

        if not raw_stores:
            raw_stores = []

        stores = []
        for store in raw_stores:

            def get_val(obj, key, default=None):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            stores.append(
                StoreResponse(
                    id=get_val(store, "id", 0),
                    name=get_val(store, "name", ""),
                    address=get_val(store, "address"),
                    city=get_val(store, "city"),
                    business_type=get_val(store, "business_type", "supermarket"),
                    rating=float(get_val(store, "rating", 0) or 0),
                    offers_count=int(get_val(store, "offers_count", 0) or 0),
                )
            )

        return stores

    except Exception as e:
        logger.error(f"Error getting stores: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# Orders
# =============================================================================


@router.post("/orders", response_model=OrderResponse)
async def create_order(
    order: CreateOrderRequest, db=Depends(get_db), user: dict = Depends(get_current_user)
):
    """Create a new order from Mini App."""
    try:
        # Use user_id from request or from Telegram auth
        user_id = order.user_id or user.get("id", 0)

        if user_id == 0:
            raise HTTPException(status_code=400, detail="User ID required")

        # Calculate total
        total = 0.0
        items_count = 0

        for item in order.items:
            offer = db.get_offer(item.offer_id) if hasattr(db, "get_offer") else None
            if offer:

                def get_val(obj, key, default=None):
                    if isinstance(obj, dict):
                        return obj.get(key, default)
                    return getattr(obj, key, default)

                price = float(get_val(offer, "discount_price", 0) or 0)
                total += price * item.quantity
                items_count += item.quantity

        # Create booking in database
        # This depends on your booking system
        order_id = 0
        if hasattr(db, "create_booking"):
            booking = db.create_booking(
                user_id=user_id,
                items=[(item.offer_id, item.quantity) for item in order.items],
                total=total,
                delivery_address=order.delivery_address,
                phone=order.phone,
                comment=order.comment,
            )
            order_id = (
                booking.get("id", 0) if isinstance(booking, dict) else getattr(booking, "id", 0)
            )

        return OrderResponse(
            order_id=order_id, status="pending", total=total, items_count=items_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# Health check
# =============================================================================


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "fudly-webapp-api"}
