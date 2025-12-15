"""
Partner Panel API endpoints for Telegram Mini App
Simplified version using Database class with raw SQL
"""
import csv
import hashlib
import hmac
import io
import os
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

import pytz
from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile

from app.services.stats import PartnerTotals, Period, get_partner_stats
from app.services.unified_order_service import get_unified_order_service
from database_protocol import DatabaseProtocol

router = APIRouter(tags=["partner-panel"])

# Global database instance (set by api_server.py)
_db: DatabaseProtocol | None = None
_bot_token: str | None = None


def set_partner_db(db: DatabaseProtocol, bot_token: str = None):
    """Set database instance and bot token for partner panel."""
    global _db, _bot_token
    _db = db
    if bot_token:
        _bot_token = bot_token
    elif not _bot_token:
        _bot_token = os.getenv("BOT_TOKEN")


def get_db() -> DatabaseProtocol:
    """Get database instance."""
    if _db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    return _db


def get_partner_with_store(telegram_id: int) -> tuple[dict, dict]:
    """
    Get user and their store by telegram_id.
    A partner is defined by having a store (in stores table), not by role in users table.
    Returns (user, store) tuple.
    Raises HTTPException if user doesn't have a store.
    """
    import logging
    import traceback
    
    try:
        db = get_db()
        logging.info(f"🔍 Looking for user with telegram_id={telegram_id}")
        
        user = db.get_user(telegram_id)
        if not user:
            logging.error(f"❌ User not found: telegram_id={telegram_id}")
            raise HTTPException(status_code=403, detail="User not found")
        
        logging.info(f"✅ Found user: user_id={user.get('user_id')}, name={user.get('first_name')}")

        store = db.get_store_by_owner(user["user_id"])
        if not store:
            logging.error(f"❌ No store found for user_id={user['user_id']}")
            raise HTTPException(status_code=403, detail="Not a partner - no store found")
        
        logging.info(f"✅ Found store: store_id={store.get('store_id')}, name={store.get('name')}")
        return user, store
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ Error in get_partner_with_store: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


def verify_telegram_webapp(authorization: str) -> int:
    """
    Verify Telegram WebApp auth and return telegram_id.
    Supports multiple auth methods:
    1. Standard Telegram WebApp signature verification
    2. URL-based auth (uid passed by bot in WebApp URL)
    3. Dev mode bypass for local development
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization")

    # Development mode bypass - ONLY works in non-production environment
    if authorization.startswith("dev_"):
        environment = os.getenv("ENVIRONMENT", "production").lower()
        if environment in ("development", "dev", "local", "test"):
            try:
                return int(authorization.split("_")[1])
            except:
                raise HTTPException(status_code=401, detail="Invalid dev auth format")
        else:
            raise HTTPException(status_code=401, detail="Dev auth not allowed in production")

    # Production: verify Telegram signature
    if not authorization.startswith("tma "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    init_data = authorization[4:]
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data))
        import logging

        logging.info(f"🔍 Parsed init_data keys: {list(parsed.keys())}")

        # Check if this is URL-based auth (uid passed by bot in WebApp URL)
        # Simple format: uid=123456
        if "uid" in parsed:
            try:
                user_id = int(parsed.get("uid", 0))
                if user_id > 0:
                    logging.info(f"✅ URL-based auth: user_id={user_id}")
                    return user_id
                else:
                    raise ValueError("uid must be positive")
            except (ValueError, TypeError) as e:
                logging.error(f"❌ Invalid uid format: {parsed.get('uid')} - {e}")
                raise HTTPException(status_code=401, detail=f"Invalid uid in URL: {e}")

        # Check if this is unsigned data (from initDataUnsafe)
        # Only allow if ALLOW_UNSAFE_AUTH is set (for debugging)
        if "hash" not in parsed:
            allow_unsafe = os.getenv("ALLOW_UNSAFE_AUTH", "").lower() == "true"
            if allow_unsafe:
                import json

                user_data = json.loads(parsed.get("user", "{}"))
                user_id = int(user_data.get("id", 0))
                if user_id > 0:
                    import logging

                    logging.warning(f"⚠️ UNSAFE AUTH: user_id={user_id} (no signature)")
                    return user_id
            raise HTTPException(status_code=401, detail="Missing signature hash")

        data_check_string_parts = []

        for key in sorted(parsed.keys()):
            if key != "hash":
                data_check_string_parts.append(f"{key}={parsed[key]}")

        data_check_string = "\n".join(data_check_string_parts)
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if calculated_hash != parsed.get("hash"):
            raise HTTPException(status_code=401, detail="Invalid signature")

        import json

        user_data = json.loads(parsed.get("user", "{}"))
        return int(user_data.get("id", 0))
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")


# Profile endpoint
@router.get("/profile")
async def get_profile(authorization: str = Header(None)):
    """Get partner profile"""
    import logging
    logging.info(f"📋 Profile request with auth: {authorization[:60] if authorization else 'None'}...")
    
    telegram_id = verify_telegram_webapp(authorization)
    logging.info(f"✅ Auth verified, telegram_id: {telegram_id}")
    
    user, store_info = get_partner_with_store(telegram_id)
    logging.info(f"✅ Got partner with store: {store_info.get('name') if store_info else 'None'}")

    return {
        "name": user.get("first_name") or user.get("username") or "Partner",
        "city": user.get("city") or "Ташкент",
        "store": {
            "name": store_info.get("name"),
            "address": store_info.get("address"),
            "phone": store_info.get("phone"),
            "description": store_info.get("description"),
            "store_id": store_info.get("store_id"),
        }
        if store_info
        else None,
    }


# Products endpoints
@router.get("/products")
async def list_products(authorization: str = Header(None), status: Optional[str] = None):
    """List partner's products"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    db = get_db()

    offers = db.get_offers_by_store(store["store_id"])

    # Filter by status if provided
    if status and status != "all":
        offers = [o for o in offers if o.get("status") == status]

    return [
        {
            "offer_id": o["offer_id"],
            "title": o["title"],
            "category": o.get("category"),
            "original_price": o.get("original_price"),
            "discount_price": o["discount_price"],
            "quantity": o["quantity"],
            "unit": o.get("unit", "шт"),
            "expiry_date": o.get("expiry_date"),
            "description": o.get("description"),
            "photo_id": o.get("photo_id"),
            "status": o.get("status", "active"),
        }
        for o in offers
    ]


@router.post("/products")
async def create_product(
    authorization: str = Header(None),
    title: str = Form(...),
    category: str = Form("other"),
    original_price: int = Form(0),
    discount_price: int = Form(...),
    quantity: int = Form(...),
    unit: str = Form("шт"),
    expiry_date: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    photo_id: Optional[str] = Form(None),
):
    """Create new product"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    db = get_db()

    # Parse expiry date
    expiry = None
    if expiry_date:
        try:
            expiry = datetime.fromisoformat(expiry_date)
        except ValueError:
            pass

    # Create offer using add_offer
    now = datetime.now().isoformat()
    until = (datetime.now() + timedelta(days=7)).isoformat()

    offer_id = db.add_offer(
        store_id=store["store_id"],
        title=title,
        description=description or title,
        original_price=original_price if original_price > 0 else None,
        discount_price=discount_price,
        quantity=quantity,
        available_from=now,
        available_until=until,
        expiry_date=expiry.isoformat() if expiry else None,
        unit=unit,
        category=category,
        photo_id=photo_id,
    )

    return {"offer_id": offer_id, "status": "created"}


@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    authorization: str = Header(None),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    original_price: Optional[int] = Form(None),
    discount_price: Optional[int] = Form(None),
    quantity: Optional[int] = Form(None),
    unit: Optional[str] = Form(None),
    expiry_date: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    photo_id: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
):
    """Update product (supports partial updates for quick actions)"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    db = get_db()

    # Verify ownership
    offer = db.get_offer(product_id)
    if not offer or offer.get("store_id") != store["store_id"]:
        raise HTTPException(status_code=404, detail="Product not found")

    # Build update dynamically for partial updates
    update_fields = []
    update_values = []

    if title is not None:
        update_fields.append("title = %s")
        update_values.append(title)

    if category is not None:
        update_fields.append("category = %s")
        update_values.append(category)

    if original_price is not None:
        update_fields.append("original_price = %s")
        update_values.append(original_price if original_price > 0 else None)

    if discount_price is not None:
        update_fields.append("discount_price = %s")
        update_values.append(discount_price)

    if quantity is not None:
        update_fields.append("quantity = %s")
        update_values.append(quantity)
        # Auto-update status based on quantity
        if quantity <= 0 and status is None:
            update_fields.append("status = %s")
            update_values.append("inactive")

    if unit is not None:
        update_fields.append("unit = %s")
        update_values.append(unit)

    if expiry_date is not None:
        expiry = None
        if expiry_date:
            try:
                expiry = datetime.fromisoformat(expiry_date).isoformat()
            except ValueError:
                pass
        update_fields.append("expiry_date = %s")
        update_values.append(expiry)

    if description is not None:
        update_fields.append("description = %s")
        update_values.append(description)

    if photo_id is not None:
        update_fields.append("photo_id = %s")
        update_values.append(photo_id)

    if status is not None:
        update_fields.append("status = %s")
        update_values.append(status)

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Execute update
    with db.get_connection() as conn:
        cursor = conn.cursor()
        query = f"UPDATE offers SET {', '.join(update_fields)} WHERE offer_id = %s"
        update_values.append(product_id)
        cursor.execute(query, tuple(update_values))

    return {"offer_id": product_id, "status": "updated"}


@router.delete("/products/{product_id}")
async def delete_product(product_id: int, authorization: str = Header(None)):
    """Delete product (soft delete)"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    db = get_db()

    # Verify ownership
    offer = db.get_offer(product_id)
    if not offer or offer["store_id"] != store["store_id"]:
        raise HTTPException(status_code=404, detail="Product not found")

    # Soft delete
    db.deactivate_offer(product_id)

    return {"offer_id": product_id, "status": "deleted"}


@router.post("/products/import")
async def import_csv(file: UploadFile = File(...), authorization: str = Header(None)):
    """Import products from CSV"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    db = get_db()

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be CSV")

    store_id = store["store_id"]

    # Read CSV
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            expiry = None
            if row.get("expiry_date"):
                try:
                    expiry = datetime.fromisoformat(row["expiry_date"])
                except ValueError:
                    pass

            now = datetime.now().isoformat()
            until = (datetime.now() + timedelta(days=7)).isoformat()

            db.add_offer(
                store_id=store_id,
                title=row["title"],
                description=row.get("description", row["title"]),
                original_price=int(row.get("original_price", 0)) or None,
                discount_price=int(row["discount_price"]),
                quantity=int(row.get("quantity", 1)),
                available_from=now,
                available_until=until,
                expiry_date=expiry.isoformat() if expiry else None,
                unit=row.get("unit", "шт"),
                category=row.get("category", "other"),
            )
            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    return {"imported": imported, "errors": errors if errors else None}


# Orders endpoints
@router.get("/orders")
async def list_orders(authorization: str = Header(None), status: Optional[str] = None):
    """List partner's orders (both bookings and orders)"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    db = get_db()

    # Get both bookings (pickup) and orders (delivery)
    bookings = db.get_store_bookings(store["store_id"])
    orders = db.get_store_orders(store["store_id"])

    result = []

    # Process bookings (pickup orders)
    for booking in bookings:
        # Handle both dict and tuple formats
        if isinstance(booking, dict):
            booking_id = booking.get("booking_id")
            offer_id = booking.get("offer_id")
            user_id = booking.get("user_id")
            booking_status = booking.get("status")
            quantity = booking.get("quantity", 1)
            created_at = booking.get("created_at")
            customer_name = booking.get("first_name", "Unknown")
            customer_phone = booking.get("phone")
        else:
            # Tuple format: booking_id, offer_id, user_id, status, booking_code, pickup_time, quantity, created_at, title, first_name, username, phone
            booking_id = booking[0]
            offer_id = booking[1]
            user_id = booking[2]
            booking_status = booking[3]
            quantity = booking[6] if len(booking) > 6 else 1
            created_at = booking[7] if len(booking) > 7 else None
            customer_name = booking[9] if len(booking) > 9 else "Unknown"
            customer_phone = booking[11] if len(booking) > 11 else None

        # Filter by status if requested
        if status and status != "all" and booking_status != status:
            continue

        # Get offer info
        offer = db.get_offer(offer_id) if offer_id else None

        result.append(
            {
                "order_id": booking_id,
                "type": "booking",  # Distinguish from delivery orders
                "offer_title": offer.get("title") if offer else "Unknown",
                "quantity": quantity,
                "price": offer.get("discount_price") * quantity if offer else 0,
                "order_type": "pickup",
                "status": booking_status,
                "delivery_address": None,
                "created_at": str(created_at) if created_at else None,
                "customer_name": customer_name,
                "customer_phone": customer_phone,
            }
        )

    # Process orders (both pickup and delivery from orders table)
    for order in orders:
        # Handle both dict and tuple formats
        if isinstance(order, dict):
            order_id = order.get("order_id")
            offer_id = order.get("offer_id")
            user_id = order.get("user_id")
            order_status = order.get("order_status")
            order_type = order.get("order_type", "delivery")
            quantity = order.get("quantity", 1)
            total_price = order.get("total_price", 0)
            delivery_address = order.get("delivery_address")
            created_at = order.get("created_at")
            customer_name = order.get("full_name", "Unknown")
            customer_phone = order.get("phone")
        else:
            # Tuple format varies, try to extract what we can
            order_id = order[0]
            user_id = order[1]
            store_id = order[2]
            offer_id = order[3]
            quantity = order[4]
            order_type = order[5]
            order_status = order[6] if len(order) > 6 else "pending"
            total_price = order[7] if len(order) > 7 else 0
            delivery_address = order[8] if len(order) > 8 else None
            created_at = order[11] if len(order) > 11 else None
            customer_name = order[-2] if len(order) > 14 else "Unknown"
            customer_phone = order[-1] if len(order) > 15 else None

        # Filter by status if requested
        if status and status != "all" and order_status != status:
            continue

        # Get offer and customer info
        offer = db.get_offer(offer_id) if offer_id else None

        # Determine entity type for API - 'booking' for pickup, 'order' for delivery
        entity_type = "booking" if order_type == "pickup" else "order"

        result.append(
            {
                "order_id": order_id,
                "type": entity_type,  # 'booking' for pickup, 'order' for delivery
                "offer_title": offer.get("title") if offer else "Unknown",
                "quantity": quantity,
                "price": total_price,
                "order_type": order_type,  # 'pickup' or 'delivery'
                "status": order_status,
                "delivery_address": delivery_address,
                "created_at": str(created_at) if created_at else None,
                "customer_name": customer_name,
                "customer_phone": customer_phone,
            }
        )

    # Sort by created_at descending
    result.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    return result


@router.post("/orders/{order_id}/confirm")
async def confirm_order(
    order_id: int,
    order_type: str = "booking",  # For legacy compatibility, but we determine from DB
    authorization: str = Header(None),
):
    """Confirm order (booking or delivery order) with notifications"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    db = get_db()
    unified_service = get_unified_order_service()

    # First try to find in bookings table
    booking = db.get_booking(order_id)
    if booking:
        # Verify it's partner's order via store
        offer_id = booking.get("offer_id") if isinstance(booking, dict) else booking[1]
        offer = db.get_offer(offer_id)
        if not offer or offer.get("store_id") != store["store_id"]:
            raise HTTPException(status_code=403, detail="Not your order")

        # Use unified service to update status with notifications
        await unified_service.confirm_order(order_id, "booking")
        return {"order_id": order_id, "status": "confirmed", "type": "booking"}

    # Try orders table
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Verify it's partner's order
    order_store_id = order.get("store_id") if isinstance(order, dict) else order[2]
    if order_store_id != store["store_id"]:
        raise HTTPException(status_code=403, detail="Not your order")

    # entity_type='order' for orders table (regardless of pickup/delivery)
    # UnifiedOrderService will determine actual order_type from DB
    await unified_service.confirm_order(order_id, "order")

    # Return type based on order_type for frontend
    db_order_type = (
        order.get("order_type")
        if isinstance(order, dict)
        else (order[5] if len(order) > 5 else "delivery")
    )
    frontend_type = "booking" if db_order_type == "pickup" else "order"

    return {"order_id": order_id, "status": "confirmed", "type": frontend_type}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    order_type: str = "booking",  # For legacy compatibility, but we determine from DB
    authorization: str = Header(None),
):
    """Cancel order (booking or delivery order) with notifications"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    db = get_db()
    unified_service = get_unified_order_service()

    # First try to find in bookings table
    booking = db.get_booking(order_id)
    if booking:
        # Verify it's partner's order via store
        offer_id = booking.get("offer_id") if isinstance(booking, dict) else booking[1]
        offer = db.get_offer(offer_id)
        if not offer or offer.get("store_id") != store["store_id"]:
            raise HTTPException(status_code=403, detail="Not your order")

        # Use unified service to cancel with notifications
        await unified_service.cancel_order(order_id, "booking")
        return {"order_id": order_id, "status": "cancelled", "type": "booking"}

    # Try orders table
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Verify it's partner's order
    order_store_id = order.get("store_id") if isinstance(order, dict) else order[2]
    if order_store_id != store["store_id"]:
        raise HTTPException(status_code=403, detail="Not your order")

    # entity_type='order' for orders table (regardless of pickup/delivery)
    await unified_service.cancel_order(order_id, "order")

    # Return type based on order_type for frontend
    db_order_type = (
        order.get("order_type")
        if isinstance(order, dict)
        else (order[5] if len(order) > 5 else "delivery")
    )
    frontend_type = "booking" if db_order_type == "pickup" else "order"

    return {"order_id": order_id, "status": "cancelled", "type": frontend_type}


@router.post("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    authorization: str = Header(None),
    status: str = Query(...),
    order_type: str = Query("booking"),  # For legacy compatibility, but we determine from DB
):
    """Update order status (ready, delivering, etc) with notifications"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    db = get_db()
    unified_service = get_unified_order_service()

    # First try to find in bookings table
    booking = db.get_booking(order_id)
    if booking:
        # Verify it's partner's order via store
        offer_id = booking.get("offer_id") if isinstance(booking, dict) else booking[1]
        offer = db.get_offer(offer_id)
        if not offer or offer.get("store_id") != store["store_id"]:
            raise HTTPException(status_code=403, detail="Not your order")

        # Use unified service based on status
        if status == "ready":
            await unified_service.mark_ready(order_id, "booking")
        elif status == "completed":
            await unified_service.complete_order(order_id, "booking")
        else:
            db.update_booking_status(order_id, status)
        return {"order_id": order_id, "status": status, "type": "booking"}

    # Try orders table
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Verify it's partner's order
    order_store_id = order.get("store_id") if isinstance(order, dict) else order[2]
    if order_store_id != store["store_id"]:
        raise HTTPException(status_code=403, detail="Not your order")

    # entity_type='order' for orders table (regardless of pickup/delivery)
    # UnifiedOrderService will read order_type from DB to handle correctly
    if status == "ready":
        await unified_service.mark_ready(order_id, "order")
    elif status == "delivering":
        await unified_service.start_delivery(order_id)
    elif status == "completed":
        await unified_service.complete_order(order_id, "order")
    else:
        db.update_order_status(order_id, status)

    # Return type based on order_type for frontend
    db_order_type = (
        order.get("order_type")
        if isinstance(order, dict)
        else (order[5] if len(order) > 5 else "delivery")
    )
    frontend_type = "booking" if db_order_type == "pickup" else "order"

    return {"order_id": order_id, "status": status, "type": frontend_type}


# Stats endpoint
@router.get("/stats")
async def get_stats(authorization: str = Header(None), period: str = "today"):
    """Get partner statistics"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    db = get_db()

    store_id = store["store_id"]

    # Calculate period
    tz = pytz.timezone("Asia/Tashkent")
    now = datetime.now(tz)

    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif period == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(hour=23, minute=59, second=59)
    elif period == "week":
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif period == "month":
        start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now

    period_obj = Period(start=start, end=end, tz="Asia/Tashkent")

    stats = get_partner_stats(
        db=db, partner_id=user["user_id"], period=period_obj, tz="Asia/Tashkent", store_id=store_id
    )

    # Count active products
    active_products = 0
    if store_id:
        offers = db.get_offers_by_store(store_id)
        active_products = len([o for o in offers if o.get("status") == "active"])

    return {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "revenue": float(stats.totals.revenue),
        "orders": stats.totals.orders,
        "items_sold": stats.totals.items_sold,
        "avg_ticket": float(stats.totals.avg_ticket) if stats.totals.avg_ticket else 0,
        "active_products": active_products,
    }


# Store settings
@router.put("/store")
async def update_store(settings: dict, authorization: str = Header(None)):
    """Update store settings"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    db = get_db()

    # Update existing store via SQL
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE stores
            SET name = %s, address = %s, phone = %s, description = %s
            WHERE store_id = %s
        """,
            (
                settings.get("name", store.get("name")),
                settings.get("address", store.get("address")),
                settings.get("phone", store.get("phone")),
                settings.get("description", store.get("description")),
                store["store_id"],
            ),
        )

    return {"status": "updated"}


# Photo upload endpoint
@router.post("/upload-photo")
async def upload_photo(photo: UploadFile = File(...), authorization: str = Header(None)):
    """
    Upload photo and get Telegram file_id.
    Sends photo to a special channel/chat via bot to get file_id.
    """
    import aiohttp

    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)

    # Read photo content
    content = await photo.read()

    # Check file size (max 10MB)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Photo too large (max 10MB)")

    # Check file type
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    if not _bot_token:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    # Send photo to user's chat to get file_id
    # We use the partner's own chat_id (telegram_id)
    try:
        async with aiohttp.ClientSession() as session:
            form_data = aiohttp.FormData()
            form_data.add_field("chat_id", str(telegram_id))
            form_data.add_field(
                "photo", content, filename=photo.filename, content_type=photo.content_type
            )
            form_data.add_field("caption", "📷 Фото товара загружено через панель партнера")

            async with session.post(
                f"https://api.telegram.org/bot{_bot_token}/sendPhoto", data=form_data
            ) as resp:
                result = await resp.json()

                if not result.get("ok"):
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to upload: {result.get('description', 'Unknown error')}",
                    )

                # Get the largest photo size (last in array)
                photos = result["result"].get("photo", [])
                if not photos:
                    raise HTTPException(status_code=500, detail="No photo in response")

                file_id = photos[-1]["file_id"]

                return {"file_id": file_id, "message": "Photo uploaded successfully"}
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")


# Get photo URL endpoint
@router.get("/photo/{file_id}")
async def get_photo_url(file_id: str):
    """Get direct URL for a Telegram photo by file_id"""
    import aiohttp

    if not _bot_token:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.telegram.org/bot{_bot_token}/getFile?file_id={file_id}"
            ) as resp:
                result = await resp.json()

                if not result.get("ok"):
                    raise HTTPException(status_code=404, detail="File not found")

                file_path = result["result"]["file_path"]
                photo_url = f"https://api.telegram.org/file/bot{_bot_token}/{file_path}"

                return {"url": photo_url}
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
