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
# Helper Functions
# =============================================================================


def get_val(obj: Any, key: str, default: Any = None) -> Any:
    """Universal getter for dict or object attributes."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


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
    unit: str = "шт"
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

# Photo URL cache (file_id -> url)
_photo_cache: dict[str, str] = {}


def get_photo_url_sync(file_id: str | None) -> str | None:
    """Convert Telegram file_id to photo URL (sync version for API).

    Telegram file_ids start with 'AgAC' for photos.
    If it's already a URL (http/https), return as-is.
    """
    if not file_id:
        return None

    # Already a URL
    if file_id.startswith(("http://", "https://")):
        return file_id

    # Check cache
    if file_id in _photo_cache:
        return _photo_cache[file_id]

    # It's a Telegram file_id - construct URL
    # Note: This URL will work for ~1 hour, Telegram file URLs expire
    try:
        bot_token = settings.bot_token
        if bot_token and file_id.startswith("AgAC"):
            # For photos, we need to use the Bot API getFile endpoint
            # But since this is sync, we'll return a proxy URL
            # that the frontend can use to fetch the photo
            url = f"https://api.telegram.org/file/bot{bot_token}/{file_id}"
            # Note: This won't work directly - file_id needs to be converted via getFile
            # For now, return None and let fallback image show
            return None
    except Exception:
        pass

    return None


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
                offers.append(
                    OfferResponse(
                        id=get_val(offer, "id", 0),
                        title=get_val(offer, "title", "Без названия"),
                        description=get_val(offer, "description"),
                        original_price=float(get_val(offer, "original_price", 0) or 0),
                        discount_price=float(get_val(offer, "discount_price", 0) or 0),
                        discount_percent=float(get_val(offer, "discount_percent", 0) or 0),
                        quantity=int(get_val(offer, "quantity", 0) or 0),
                        unit=get_val(offer, "unit", "шт") or "шт",
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

        return OfferResponse(
            id=get_val(offer, "id", 0),
            title=get_val(offer, "title", "Без названия"),
            description=get_val(offer, "description"),
            original_price=float(get_val(offer, "original_price", 0) or 0),
            discount_price=float(get_val(offer, "discount_price", 0) or 0),
            discount_percent=float(get_val(offer, "discount_percent", 0) or 0),
            quantity=int(get_val(offer, "quantity", 0) or 0),
            unit=get_val(offer, "unit", "шт") or "шт",
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


@router.get("/flash-deals", response_model=list[OfferResponse])
async def get_flash_deals(
    city: str = Query("Ташкент", description="City to filter by"),
    limit: int = Query(10, ge=1, le=50),
    db=Depends(get_db),
):
    """Get flash deals - high discount items expiring soon."""
    from datetime import datetime, timedelta

    try:
        # Get offers with high discounts
        raw_offers = (
            db.get_hot_offers(city, limit=100, offset=0)
            if hasattr(db, "get_hot_offers")
            else []
        )

        if not raw_offers:
            raw_offers = []

        offers = []
        today = datetime.now().date()
        max_expiry = today + timedelta(days=7)  # Within 7 days

        for offer in raw_offers:
            try:
                discount = float(get_val(offer, "discount_percent", 0) or 0)
                expiry_str = get_val(offer, "expiry_date")

                # Filter: discount >= 20% OR expiring within 7 days
                is_high_discount = discount >= 20
                is_expiring_soon = False

                if expiry_str:
                    try:
                        expiry = datetime.fromisoformat(str(expiry_str).split("T")[0]).date()
                        is_expiring_soon = today <= expiry <= max_expiry
                    except (ValueError, AttributeError):
                        pass

                if is_high_discount or is_expiring_soon:
                    offers.append(
                        OfferResponse(
                            id=get_val(offer, "id", 0),
                            title=get_val(offer, "title", "Без названия"),
                            description=get_val(offer, "description"),
                            original_price=float(get_val(offer, "original_price", 0) or 0),
                            discount_price=float(get_val(offer, "discount_price", 0) or 0),
                            discount_percent=discount,
                            quantity=int(get_val(offer, "quantity", 0) or 0),
                            unit=get_val(offer, "unit", "шт") or "шт",
                            category=get_val(offer, "category", "other") or "other",
                            store_id=int(get_val(offer, "store_id", 0) or 0),
                            store_name=get_val(offer, "store_name", "") or "",
                            store_address=get_val(offer, "store_address"),
                            photo=get_val(offer, "photo"),
                            expiry_date=str(expiry_str) if expiry_str else None,
                        )
                    )
            except Exception as e:
                logger.warning(f"Error parsing flash deal offer: {e}")
                continue

        # Sort by discount (highest first), then by expiry (soonest first)
        offers.sort(key=lambda x: (-x.discount_percent, x.expiry_date or "9999"))

        return offers[:limit]

    except Exception as e:
        logger.error(f"Error getting flash deals: {e}")
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
            raw_stores = db.get_stores_by_city(city) if hasattr(db, "get_stores_by_city") else []

        if not raw_stores:
            raw_stores = []

        stores = []
        for store in raw_stores:
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
# Photo URL Conversion
# =============================================================================


@router.get("/photo/{file_id:path}")
async def get_photo(file_id: str):
    """Convert Telegram file_id to actual photo URL.

    Returns redirect to Telegram file server or 404.
    """
    from aiogram import Bot

    if not file_id or len(file_id) < 10:
        raise HTTPException(status_code=404, detail="Invalid file_id")

    # Check cache first
    if file_id in _photo_cache:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url=_photo_cache[file_id])

    try:
        bot = Bot(token=settings.bot_token)
        try:
            file = await bot.get_file(file_id)
            if file and file.file_path:
                url = f"https://api.telegram.org/file/bot{settings.bot_token}/{file.file_path}"
                _photo_cache[file_id] = url
                from fastapi.responses import RedirectResponse

                return RedirectResponse(url=url)
        finally:
            await bot.session.close()
    except Exception as e:
        logger.debug(f"Could not get photo for {file_id[:20]}...: {e}")

    raise HTTPException(status_code=404, detail="Photo not found")


# =============================================================================
# Orders
# =============================================================================


@router.post("/orders", response_model=OrderResponse)
async def create_order(
    order: CreateOrderRequest, db=Depends(get_db), user: dict = Depends(get_current_user)
):
    """Create a new order from Mini App and notify partner."""

    from aiogram import Bot

    bot_instance = None  # Initialize outside try for finally block access

    try:
        # Use user_id from request or from Telegram auth
        user_id = order.user_id or user.get("id", 0)

        if user_id == 0:
            raise HTTPException(status_code=400, detail="User ID required")

        # Get bot instance from global settings
        try:
            bot_instance = Bot(token=settings.bot_token)
        except Exception as e:
            logger.warning(f"Could not create bot instance: {e}")

        # Determine if this is delivery or pickup based on delivery_address
        is_delivery = bool(order.delivery_address and order.delivery_address.strip())

        # CHECK MIN_ORDER_AMOUNT for delivery (Quick Win #2)
        if is_delivery:
            # Calculate total first
            total_check = 0
            for item in order.items:
                offer = db.get_offer(item.offer_id) if hasattr(db, "get_offer") else None
                if offer:
                    price = float(get_val(offer, "discount_price", 0) or 0)
                    total_check += price * item.quantity
                    store_id_check = get_val(offer, "store_id")
            
            # Check min order for first store (simplified for now)
            if order.items:
                first_offer = db.get_offer(order.items[0].offer_id) if hasattr(db, "get_offer") else None
                if first_offer:
                    store_id_check = get_val(first_offer, "store_id")
                    store_check = db.get_store(store_id_check) if hasattr(db, "get_store") else None
                    if store_check:
                        min_order = get_val(store_check, "min_order_amount", 0)
                        if min_order > 0 and total_check < min_order:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Minimum order amount: {min_order}. Your total: {total_check}"
                            )

        # Process each offer separately
        created_items = []

        for item in order.items:
            offer = db.get_offer(item.offer_id) if hasattr(db, "get_offer") else None
            if not offer:
                continue

            price = float(get_val(offer, "discount_price", 0) or 0)
            total = price * item.quantity
            store_id = get_val(offer, "store_id")
            offer_title = get_val(offer, "title", "Товар")

            try:
                if is_delivery and hasattr(db, "create_order"):
                    # Create delivery ORDER
                    store = db.get_store(store_id) if hasattr(db, "get_store") else None
                    delivery_price = get_val(store, "delivery_price", 15000) if store else 15000

                    order_id = db.create_order(
                        user_id=user_id,
                        store_id=store_id,
                        offer_id=item.offer_id,
                        quantity=item.quantity,
                        order_type="delivery",
                        delivery_address=order.delivery_address,
                        delivery_price=delivery_price,
                        payment_method="card",
                    )

                    if order_id:
                        created_items.append(
                            {
                                "id": order_id,
                                "type": "order",
                                "offer_id": item.offer_id,
                                "quantity": item.quantity,
                                "total": total + delivery_price,
                                "offer_title": offer_title,
                                "store_id": store_id,
                            }
                        )
                        logger.info(f"✅ Created delivery ORDER {order_id} for user {user_id}")

                elif hasattr(db, "create_booking_atomic"):
                    # Create pickup BOOKING (atomic to prevent race conditions)
                    ok, booking_id, booking_code = db.create_booking_atomic(
                        offer_id=item.offer_id,
                        user_id=user_id,
                        quantity=item.quantity,
                    )

                    if ok and booking_id:
                        created_items.append(
                            {
                                "id": booking_id,
                                "type": "booking",
                                "offer_id": item.offer_id,
                                "quantity": item.quantity,
                                "total": total,
                                "offer_title": offer_title,
                                "store_id": store_id,
                            }
                        )
                        logger.info(f"✅ Created pickup BOOKING {booking_id} for user {user_id}")

                # Notify partner about new order/booking
                if bot_instance and store_id and created_items:
                    last_item = created_items[-1]
                    store = db.get_store(store_id) if hasattr(db, "get_store") else None
                    if store:
                        owner_id = get_val(store, "owner_id")
                        if owner_id:
                            await notify_partner_webapp_order(
                                bot=bot_instance,
                                db=db,
                                owner_id=owner_id,
                                booking_id=last_item["id"],
                                offer_title=offer_title,
                                quantity=item.quantity,
                                total=last_item["total"],
                                user_id=user_id,
                                delivery_address=order.delivery_address if is_delivery else None,
                                phone=order.phone,
                                photo=get_val(offer, "photo"),
                                is_delivery=is_delivery,
                            )

            except Exception as e:
                logger.error(f"Error creating order for offer {item.offer_id}: {e}")
                continue

        # Return first item as order_id (or 0 if none created)
        order_id = created_items[0]["id"] if created_items else 0
        total_amount = sum(b["total"] for b in created_items)
        total_items = sum(b["quantity"] for b in created_items)

        # QUICK WIN #1: Send confirmation to customer
        if bot_instance and created_items and user_id:
            try:
                customer_lang = db.get_user_language(user_id) if hasattr(db, "get_user_language") else "ru"
                currency = "so'm" if customer_lang == "uz" else "сум"
                
                # Build confirmation message
                if customer_lang == "uz":
                    order_type_uz = "🚚 Yetkazish" if is_delivery else "🏪 O'zi olib ketadi"
                    confirm_msg = f"✅ <b>Buyurtma qabul qilindi!</b>\n\n"
                    confirm_msg += f"📦 #{order_id}\n"
                    confirm_msg += f"{order_type_uz}\n\n"
                    confirm_msg += "<b>Mahsulotlar:</b>\n"
                    for item in created_items:
                        confirm_msg += f"• {item['offer_title']} × {item['quantity']}\n"
                    confirm_msg += f"\n💰 <b>Jami: {int(total_amount):,} {currency}</b>\n\n"
                    if is_delivery and order.delivery_address:
                        confirm_msg += f"📍 {order.delivery_address}\n\n"
                    confirm_msg += "⏳ Sotuvchi tasdiqlashini kutamiz..."
                else:
                    order_type_ru = "🚚 Доставка" if is_delivery else "🏪 Самовывоз"
                    confirm_msg = f"✅ <b>Заказ оформлен!</b>\n\n"
                    confirm_msg += f"📦 #{order_id}\n"
                    confirm_msg += f"{order_type_ru}\n\n"
                    confirm_msg += "<b>Товары:</b>\n"
                    for item in created_items:
                        confirm_msg += f"• {item['offer_title']} × {item['quantity']}\n"
                    confirm_msg += f"\n💰 <b>Итого: {int(total_amount):,} {currency}</b>\n\n"
                    if is_delivery and order.delivery_address:
                        confirm_msg += f"📍 {order.delivery_address}\n\n"
                    confirm_msg += "⏳ Ожидаем подтверждения продавца..."
                
                await bot_instance.send_message(user_id, confirm_msg, parse_mode="HTML")
                logger.info(f"✅ Sent order confirmation to customer {user_id}")
            except Exception as e:
                logger.warning(f"Failed to send confirmation to customer: {e}")

        # QUICK WIN #4: Structured logging
        logger.info(
            f"ORDER_CREATED: id={order_id}, user={user_id}, type={'delivery' if is_delivery else 'pickup'}, "
            f"total={int(total_amount)}, items={total_items}, source=webapp_api"
        )

        return OrderResponse(
            order_id=order_id, status="pending", total=total_amount, items_count=total_items
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        # Always close bot session to prevent resource leaks
        if bot_instance:
            try:
                await bot_instance.session.close()
            except Exception:
                pass


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
    is_delivery: bool = False,
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

    # Build beautiful notification card (unified with bot style)
    currency = "so'm" if partner_lang == "uz" else "сум"
    unit_label = "dona" if partner_lang == "uz" else "шт"

    if partner_lang == "uz":
        text = (
            f"🔔 <b>YANGI BUYURTMA (Mini App)!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Miqdor: <b>{quantity}</b> {unit_label}\n"
            f"💰 Jami: <b>{int(total):,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Xaridor:</b>\n"
            f"   Ism: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
        )
        if is_delivery:
            text += "\n🚚 <b>Yetkazib berish</b>\n"
            if delivery_address:
                text += f"   📍 {_esc(delivery_address)}\n"
        else:
            text += "\n🏪 <b>O'zi olib ketadi</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━"
        confirm_text = "✅ Tasdiqlash"
        reject_text = "❌ Rad etish"
    else:
        text = (
            f"🔔 <b>НОВЫЙ ЗАКАЗ (Mini App)!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Количество: <b>{quantity}</b> {unit_label}\n"
            f"💰 Итого: <b>{int(total):,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Покупатель:</b>\n"
            f"   Имя: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
        )
        if is_delivery:
            text += "\n🚚 <b>Доставка</b>\n"
            if delivery_address:
                text += f"   📍 {_esc(delivery_address)}\n"
        else:
            text += "\n🏪 <b>Самовывоз</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━"
        confirm_text = "✅ Подтвердить"
        reject_text = "❌ Отклонить"

    # Use unified callback_data (QUICK WIN #3: unified pattern for ALL orders)
    kb = InlineKeyboardBuilder()
    # Always use partner_confirm_order_ / partner_reject_order_ for consistency
    kb.button(text=confirm_text, callback_data=f"partner_confirm_order_{booking_id}")
    kb.button(text=reject_text, callback_data=f"partner_reject_order_{booking_id}")
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
                    offers.append(
                        OfferResponse(
                            id=get_val(offer, "id", 0),
                            title=get_val(offer, "title", "Без названия"),
                            description=get_val(offer, "description"),
                            original_price=float(get_val(offer, "original_price", 0) or 0),
                            discount_price=float(get_val(offer, "discount_price", 0) or 0),
                            discount_percent=float(get_val(offer, "discount_percent", 0) or 0),
                            quantity=int(get_val(offer, "quantity", 0) or 0),
                            unit=get_val(offer, "unit", "шт") or "шт",
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
        # Get all stores (using get_stores_by_city with no filter returns all)
        # Note: get_all_stores doesn't exist, using get_stores_by_city
        raw_stores = []
        if hasattr(db, "get_stores_by_city"):
            # Try common cities or get all by iterating
            for city in ["Ташкент", "Tashkent", "Самарканд", "Бухара"]:
                try:
                    stores = db.get_stores_by_city(city)
                    if stores:
                        raw_stores.extend(stores)
                except Exception:
                    continue

        if not raw_stores:
            return []

        # Calculate distances (simplified - real implementation would use PostGIS or similar)
        stores_with_distance = []

        for store in raw_stores:
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
                    discount = float(get_val(offer, "discount_percent", 0) or 0)
                    discounts.append(discount)

                if discounts:
                    stats["avg_discount"] = round(sum(discounts) / len(discounts), 1)
                    stats["max_discount"] = round(max(discounts), 1)

        # Get stores count
        if hasattr(db, "get_stores_by_city"):
            stores = db.get_stores_by_city(city)
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
