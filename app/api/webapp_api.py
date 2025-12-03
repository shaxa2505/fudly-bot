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
    delivery_enabled: bool = False
    delivery_price: float | None = None
    min_order_amount: float | None = None
    photo_url: str | None = None


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


class FavoriteRequest(BaseModel):
    offer_id: int


class CartItem(BaseModel):
    offer_id: int
    quantity: int
    title: str
    price: float
    photo: str | None = None


class CartResponse(BaseModel):
    items: list[CartItem]
    total: float
    items_count: int


class FilterParams(BaseModel):
    min_price: float | None = None
    max_price: float | None = None
    min_discount: float | None = None
    max_distance: float | None = None  # km
    sort_by: str = "discount"  # discount, price_asc, price_desc, new


class LocationRequest(BaseModel):
    latitude: float
    longitude: float


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
    Guest access only allowed in development mode.
    """
    import os

    if not x_telegram_init_data:
        # SECURITY: Only allow guest access in development mode
        if os.getenv("ALLOW_GUEST_ACCESS", "false").lower() in ("true", "1", "yes"):
            logger.warning("Guest access allowed - DEVELOPMENT MODE ONLY")
            return {"id": 0, "first_name": "Guest"}
        else:
            raise HTTPException(status_code=401, detail="Authentication required")

    bot_token = settings.bot_token
    validated = validate_init_data(x_telegram_init_data, bot_token)

    if not validated:
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    return validated.get("user")


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

        # Apply filters
        if min_price is not None:
            offers = [o for o in offers if o.discount_price >= min_price]
        if max_price is not None:
            offers = [o for o in offers if o.discount_price <= max_price]
        if min_discount is not None:
            offers = [o for o in offers if o.discount_percent >= min_discount]

        # Apply sorting
        if sort_by == "discount":
            offers.sort(key=lambda x: x.discount_percent, reverse=True)
        elif sort_by == "price_asc":
            offers.sort(key=lambda x: x.discount_price)
        elif sort_by == "price_desc":
            offers.sort(key=lambda x: x.discount_price, reverse=True)
        elif sort_by == "new":
            offers.sort(key=lambda x: x.id, reverse=True)

        # Apply pagination after filtering
        offers = offers[offset : offset + limit]

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
                    delivery_enabled=bool(get_val(store, "delivery_enabled", False)),
                    delivery_price=float(get_val(store, "delivery_price", 0) or 0)
                    if get_val(store, "delivery_price")
                    else None,
                    min_order_amount=float(get_val(store, "min_order_amount", 0) or 0)
                    if get_val(store, "min_order_amount")
                    else None,
                    photo_url=get_val(
                        store, "photo"
                    ),  # Telegram file_id stored, will be None for now
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
    """Create a new order from Mini App and notify partner."""

    from aiogram import Bot

    try:
        # Use user_id from request or from Telegram auth
        user_id = order.user_id or user.get("id", 0)

        if user_id == 0:
            raise HTTPException(status_code=400, detail="User ID required")

        # Get bot instance from global settings
        bot_instance = None
        try:
            bot_instance = Bot(token=settings.bot_token)
        except Exception as e:
            logger.warning(f"Could not create bot instance: {e}")

        # Process each offer separately (create booking per offer)
        created_bookings = []

        for item in order.items:
            offer = db.get_offer(item.offer_id) if hasattr(db, "get_offer") else None
            if not offer:
                continue

            def get_val(obj, key, default=None):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            price = float(get_val(offer, "discount_price", 0) or 0)
            total = price * item.quantity
            store_id = get_val(offer, "store_id")
            offer_title = get_val(offer, "title", "Товар")

            # Create booking using create_booking method
            try:
                if hasattr(db, "create_booking"):
                    booking_id = db.create_booking(
                        user_id=user_id,
                        offer_id=item.offer_id,
                        quantity=item.quantity,
                        pickup_date="2024-01-01 00:00",  # Will be updated by partner
                        comment=order.comment or "",
                    )

                    created_bookings.append(
                        {
                            "booking_id": booking_id,
                            "offer_id": item.offer_id,
                            "quantity": item.quantity,
                            "total": total,
                            "offer_title": offer_title,
                        }
                    )

                    # Notify partner about new booking
                    if bot_instance and store_id:
                        store = db.get_store(store_id) if hasattr(db, "get_store") else None
                        if store:
                            owner_id = get_val(store, "owner_id")
                            if owner_id:
                                await notify_partner_webapp_order(
                                    bot=bot_instance,
                                    db=db,
                                    owner_id=owner_id,
                                    booking_id=booking_id,
                                    offer_title=offer_title,
                                    quantity=item.quantity,
                                    total=total,
                                    user_id=user_id,
                                    delivery_address=order.delivery_address,
                                    phone=order.phone,
                                    photo=get_val(offer, "photo"),
                                )

            except Exception as e:
                logger.error(f"Error creating booking for offer {item.offer_id}: {e}")
                continue

        if bot_instance:
            await bot_instance.session.close()

        # Return first booking as order_id (or 0 if none created)
        order_id = created_bookings[0]["booking_id"] if created_bookings else 0
        total_amount = sum(b["total"] for b in created_bookings)
        total_items = sum(b["quantity"] for b in created_bookings)

        return OrderResponse(
            order_id=order_id, status="pending", total=total_amount, items_count=total_items
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


async def notify_partner_webapp_order(
    bot,
    db,
    owner_id: int,
    booking_id: int,
    offer_title: str,
    quantity: int,
    total: float,
    user_id: int,
    delivery_address: str | None,
    phone: str | None,
    photo: str | None,
):
    """Send notification to partner about new webapp order."""
    import html

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    partner_lang = db.get_user_language(owner_id) if hasattr(db, "get_user_language") else "uz"
    user = db.get_user(user_id) if hasattr(db, "get_user") else None

    def get_user_val(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default) if obj else default

    customer_name = get_user_val(user, "first_name", "Клиент")
    customer_phone = phone or get_user_val(user, "phone", "Не указан")

    def _esc(val):
        return html.escape(str(val)) if val else ""

    if partner_lang == "uz":
        text = (
            f"🔔 <b>Yangi buyurtma (Mini App)!</b>\n\n"
            f"📦 {_esc(offer_title)} × {quantity}\n"
            f"💰 {int(total):,} so'm\n"
            f"👤 {_esc(customer_name)}\n"
            f"📱 Tel: <code>{_esc(customer_phone)}</code>\n"
        )
        if delivery_address:
            text += f"🏠 Manzil: {_esc(delivery_address)}\n"
        else:
            text += "🏪 O'zi olib ketadi\n"
        confirm_text = "✅ Tasdiqlash"
        reject_text = "❌ Rad etish"
    else:
        text = (
            f"🔔 <b>Новый заказ (Mini App)!</b>\n\n"
            f"📦 {_esc(offer_title)} × {quantity}\n"
            f"💰 {int(total):,} сум\n"
            f"👤 {_esc(customer_name)}\n"
            f"📱 Тел: <code>{_esc(customer_phone)}</code>\n"
        )
        if delivery_address:
            text += f"🏠 Адрес: {_esc(delivery_address)}\n"
        else:
            text += "🏪 Самовывоз\n"
        confirm_text = "✅ Подтвердить"
        reject_text = "❌ Отклонить"

    kb = InlineKeyboardBuilder()
    kb.button(text=confirm_text, callback_data=f"partner_confirm_{booking_id}")
    kb.button(text=reject_text, callback_data=f"partner_reject_{booking_id}")
    kb.adjust(2)

    try:
        if photo:
            try:
                await bot.send_photo(
                    owner_id,
                    photo=photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
                return
            except Exception:
                pass

        await bot.send_message(owner_id, text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        logger.error(f"Failed to notify partner {owner_id}: {e}")


# =============================================================================
# Health check
# =============================================================================


# =============================================================================
# Favorites
# =============================================================================


@router.get("/favorites", response_model=list[OfferResponse])
async def get_favorites(db=Depends(get_db), user: dict = Depends(get_current_user)):
    """Get user's favorite offers."""
    try:
        user_id = user.get("id", 0)
        if user_id == 0:
            return []

        # Get favorites from database
        if hasattr(db, "get_user_favorite_offers"):
            favorite_ids = db.get_user_favorite_offers(user_id)
        else:
            favorite_ids = []

        offers = []
        for offer_id in favorite_ids:
            try:
                offer = db.get_offer(offer_id) if hasattr(db, "get_offer") else None
                if offer:

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
                logger.warning(f"Error loading favorite offer {offer_id}: {e}")
                continue

        return offers

    except Exception as e:
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

        # Add to database
        if hasattr(db, "add_user_favorite"):
            db.add_user_favorite(user_id, request.offer_id)

        return {"status": "ok", "offer_id": request.offer_id}

    except HTTPException:
        raise
    except Exception as e:
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

        # Remove from database
        if hasattr(db, "remove_user_favorite"):
            db.remove_user_favorite(user_id, request.offer_id)

        return {"status": "ok", "offer_id": request.offer_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing favorite: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# Cart (Session-based, stored in localStorage on client)
# =============================================================================


@router.get("/cart/calculate")
async def calculate_cart(
    offer_ids: str = Query(
        ..., description="Comma-separated offer IDs with quantities (id:qty,id:qty)"
    ),
    db=Depends(get_db),
):
    """Calculate cart total and get current prices."""
    try:
        items = []
        total = 0.0
        items_count = 0

        # Parse offer_ids string: "1:2,3:1,5:3" -> [(1,2), (3,1), (5,3)]
        for item_str in offer_ids.split(","):
            if ":" not in item_str:
                continue
            offer_id_str, qty_str = item_str.split(":")
            offer_id = int(offer_id_str)
            quantity = int(qty_str)

            offer = db.get_offer(offer_id) if hasattr(db, "get_offer") else None
            if offer:

                def get_val(obj, key, default=None):
                    if isinstance(obj, dict):
                        return obj.get(key, default)
                    return getattr(obj, key, default)

                price = float(get_val(offer, "discount_price", 0) or 0)
                items.append(
                    CartItem(
                        offer_id=offer_id,
                        quantity=quantity,
                        title=get_val(offer, "title", ""),
                        price=price,
                        photo=get_val(offer, "photo"),
                    )
                )
                total += price * quantity
                items_count += quantity

        return CartResponse(items=items, total=total, items_count=items_count)

    except Exception as e:
        logger.error(f"Error calculating cart: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# Location & Distance
# =============================================================================


@router.post("/stores/nearby")
async def get_nearby_stores(
    location: LocationRequest,
    radius_km: float = Query(5.0, description="Search radius in kilometers"),
    db=Depends(get_db),
):
    """Get stores near user's location."""
    try:
        # Get all stores
        raw_stores = db.get_all_stores() if hasattr(db, "get_all_stores") else []

        if not raw_stores:
            return []

        # Calculate distances (simplified - real implementation would use PostGIS or similar)
        stores_with_distance = []

        for store in raw_stores:

            def get_val(obj, key, default=None):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            # Mock distance calculation - replace with real geospatial query
            # For now, random distance for demo
            import random

            distance = random.uniform(0.5, 10.0)

            if distance <= radius_km:
                store_data = StoreResponse(
                    id=get_val(store, "id", 0),
                    name=get_val(store, "name", ""),
                    address=get_val(store, "address"),
                    city=get_val(store, "city"),
                    business_type=get_val(store, "business_type", "supermarket"),
                    rating=float(get_val(store, "rating", 0) or 0),
                    offers_count=int(get_val(store, "offers_count", 0) or 0),
                )
                stores_with_distance.append(
                    {"store": store_data, "distance_km": round(distance, 2)}
                )

        # Sort by distance
        stores_with_distance.sort(key=lambda x: x["distance_km"])

        return stores_with_distance

    except Exception as e:
        logger.error(f"Error getting nearby stores: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# Search with suggestions
# =============================================================================


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

        # Get recent popular searches or product titles
        suggestions = []

        # Search in offer titles
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

    except Exception as e:
        logger.error(f"Error getting search suggestions: {e}")
        return []


# =============================================================================
# Statistics
# =============================================================================


@router.get("/stats/hot-deals")
async def get_hot_deals_stats(city: str = Query("Ташкент"), db=Depends(get_db)):
    """Get statistics about hot deals."""
    try:
        stats = {
            "total_offers": 0,
            "total_stores": 0,
            "avg_discount": 0.0,
            "max_discount": 0.0,
            "categories_count": len(CATEGORIES) - 1,  # exclude "all"
        }

        # Get offers
        if hasattr(db, "get_hot_offers"):
            offers = db.get_hot_offers(city, limit=1000)
            if offers:
                stats["total_offers"] = len(offers)

                discounts = []
                for offer in offers:

                    def get_val(obj, key, default=None):
                        if isinstance(obj, dict):
                            return obj.get(key, default)
                        return getattr(obj, key, default)

                    discount = float(get_val(offer, "discount_percent", 0) or 0)
                    discounts.append(discount)

                if discounts:
                    stats["avg_discount"] = round(sum(discounts) / len(discounts), 1)
                    stats["max_discount"] = round(max(discounts), 1)

        # Get stores count
        if hasattr(db, "get_all_stores"):
            stores = db.get_all_stores(city)
            if stores:
                stats["total_stores"] = len(stores)

        return stats

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {
            "total_offers": 0,
            "total_stores": 0,
            "avg_discount": 0.0,
            "max_discount": 0.0,
            "categories_count": len(CATEGORIES) - 1,
        }


# =============================================================================
# Health check
# =============================================================================


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "fudly-webapp-api", "version": "2.0"}
