"""
Partner Panel API endpoints for Telegram Mini App
Handles product CRUD, CSV import, orders, stats, and settings
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime, timedelta
import csv
import io
import hashlib
import hmac
import urllib.parse

from app.services.stats import get_partner_stats, Period
from database_protocol import DatabaseProtocol


router = APIRouter(prefix="/api/partner", tags=["partner-panel"])


# Telegram WebApp authentication
def verify_telegram_webapp_data(init_data: str, bot_token: str) -> dict:
    """
    Verify Telegram WebApp initData signature
    Returns user data if valid, raises HTTPException if invalid
    """
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data))
        data_check_string_parts = []
        
        for key in sorted(parsed.keys()):
            if key != 'hash':
                data_check_string_parts.append(f"{key}={parsed[key]}")
        
        data_check_string = '\n'.join(data_check_string_parts)
        secret_key = hmac.new("WebAppData".encode(), bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash != parsed.get('hash'):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse user data
        import json
        user_data = json.loads(parsed.get('user', '{}'))
        return user_data
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


# Global database instance (set by api_server.py)
_db: DatabaseProtocol | None = None


def set_db(db: DatabaseProtocol):
    """Set database instance."""
    global _db
    _db = db


def get_db() -> DatabaseProtocol:
    """Get database instance."""
    if _db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    return _db


async def get_current_partner(authorization: str) -> dict:
    """
    Extract partner from Telegram WebApp auth header
    Expected format: "tma <initData>"
    """
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(status_code=401, detail="Missing authorization")
    
    init_data = authorization[4:]  # Remove "tma " prefix
    
    # Get bot token from environment (you'll need to pass this)
    import os
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Bot token not configured")
    
    user_data = verify_telegram_webapp_data(init_data, bot_token)
    telegram_id = user_data.get('id')
    
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Invalid user data")
    
    # Fetch user from database
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if not user or user.role != 'seller':
        raise HTTPException(status_code=403, detail="Not a partner")
    
    return user


# Profile endpoint
@router.get("/profile")
async def get_profile(
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_session)
):
    """Get partner profile with store info"""
    result = await db.execute(
        select(Store).where(Store.owner_id == partner.user_id)
    )
    store = result.scalar_one_or_none()
    
    return {
        "name": partner.name,
        "city": partner.city or "Ташкент",
        "store": {
            "name": store.name if store else None,
            "address": store.address if store else None,
            "phone": store.phone if store else None,
            "description": store.description if store else None,
            "store_id": store.store_id if store else None
        } if store else None
    }


# Products CRUD
@router.get("/products")
async def list_products(
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = Query(None, regex="^(active|inactive|all)$")
):
    """List all products for partner"""
    query = select(Offer).where(Offer.seller_id == partner.user_id)
    
    if status and status != 'all':
        query = query.where(Offer.status == status)
    
    result = await db.execute(query.order_by(Offer.created_at.desc()))
    offers = result.scalars().all()
    
    return [
        {
            "offer_id": o.offer_id,
            "title": o.title,
            "category": o.category,
            "original_price": o.original_price,
            "discount_price": o.discount_price,
            "quantity": o.quantity,
            "unit": o.unit,
            "expiry_date": o.expiry_date.isoformat() if o.expiry_date else None,
            "description": o.description,
            "photo_id": o.photo_id,
            "status": o.status
        }
        for o in offers
    ]


@router.post("/products")
async def create_product(
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_session),
    title: str = Form(...),
    category: str = Form(...),
    original_price: int = Form(0),
    discount_price: int = Form(...),
    quantity: int = Form(...),
    unit: str = Form("шт"),
    expiry_date: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None)
):
    """Create new product"""
    # Handle photo upload if provided
    photo_id = None
    if photo:
        # In production, upload to Telegram via bot.send_photo() and get file_id
        # For now, store filename or implement S3/CDN upload
        photo_id = f"placeholder_{photo.filename}"
    
    # Parse expiry date
    expiry = None
    if expiry_date:
        try:
            expiry = datetime.fromisoformat(expiry_date)
        except ValueError:
            pass
    
    # Get store_id
    store_result = await db.execute(
        select(Store.store_id).where(Store.owner_id == partner.user_id)
    )
    store_id = store_result.scalar_one_or_none()
    
    new_offer = Offer(
        seller_id=partner.user_id,
        store_id=store_id,
        title=title,
        category=category,
        original_price=original_price if original_price > 0 else None,
        discount_price=discount_price,
        quantity=quantity,
        unit=unit,
        expiry_date=expiry,
        description=description,
        photo_id=photo_id,
        status='active',
        created_at=datetime.utcnow()
    )
    
    db.add(new_offer)
    await db.commit()
    await db.refresh(new_offer)
    
    return {"offer_id": new_offer.offer_id, "status": "created"}


@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_session),
    title: str = Form(...),
    category: str = Form(...),
    original_price: int = Form(0),
    discount_price: int = Form(...),
    quantity: int = Form(...),
    unit: str = Form("шт"),
    expiry_date: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None)
):
    """Update existing product"""
    # Verify ownership
    result = await db.execute(
        select(Offer).where(
            and_(
                Offer.offer_id == product_id,
                Offer.seller_id == partner.user_id
            )
        )
    )
    offer = result.scalar_one_or_none()
    
    if not offer:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Handle photo
    if photo:
        offer.photo_id = f"placeholder_{photo.filename}"
    
    # Update fields
    offer.title = title
    offer.category = category
    offer.original_price = original_price if original_price > 0 else None
    offer.discount_price = discount_price
    offer.quantity = quantity
    offer.unit = unit
    offer.description = description
    
    if expiry_date:
        try:
            offer.expiry_date = datetime.fromisoformat(expiry_date)
        except ValueError:
            pass
    
    await db.commit()
    
    return {"offer_id": offer.offer_id, "status": "updated"}


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_session)
):
    """Delete product (soft delete by setting status to inactive)"""
    result = await db.execute(
        select(Offer).where(
            and_(
                Offer.offer_id == product_id,
                Offer.seller_id == partner.user_id
            )
        )
    )
    offer = result.scalar_one_or_none()
    
    if not offer:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Soft delete
    offer.status = 'inactive'
    await db.commit()
    
    return {"offer_id": product_id, "status": "deleted"}


# CSV Import
@router.post("/products/import")
async def import_products_csv(
    file: UploadFile = File(...),
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_session)
):
    """
    Import products from CSV file
    Expected columns: title,category,original_price,discount_price,quantity,unit,expiry_date,description
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be CSV")
    
    # Get store_id
    store_result = await db.execute(
        select(Store.store_id).where(Store.owner_id == partner.user_id)
    )
    store_id = store_result.scalar_one_or_none()
    
    # Read CSV
    content = await file.read()
    text = content.decode('utf-8-sig')  # Handle BOM
    reader = csv.DictReader(io.StringIO(text))
    
    imported = 0
    errors = []
    
    for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is 1)
        try:
            # Parse expiry date
            expiry = None
            if row.get('expiry_date'):
                try:
                    expiry = datetime.fromisoformat(row['expiry_date'])
                except ValueError:
                    pass
            
            # Create offer
            new_offer = Offer(
                seller_id=partner.user_id,
                store_id=store_id,
                title=row['title'],
                category=row.get('category', 'other'),
                original_price=int(row.get('original_price', 0)) or None,
                discount_price=int(row['discount_price']),
                quantity=int(row.get('quantity', 1)),
                unit=row.get('unit', 'шт'),
                expiry_date=expiry,
                description=row.get('description'),
                status='active',
                created_at=datetime.utcnow()
            )
            
            db.add(new_offer)
            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    await db.commit()
    
    return {
        "imported": imported,
        "errors": errors if errors else None
    }


# Orders
@router.get("/orders")
async def list_orders(
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = Query(None)
):
    """List orders for partner's products"""
    query = select(Booking, Offer, User).join(
        Offer, Booking.offer_id == Offer.offer_id
    ).join(
        User, Booking.customer_id == User.user_id
    ).where(
        Offer.seller_id == partner.user_id
    )
    
    if status and status != 'all':
        query = query.where(Booking.status == status)
    
    result = await db.execute(query.order_by(Booking.created_at.desc()))
    rows = result.all()
    
    return [
        {
            "booking_id": booking.booking_id,
            "offer_title": offer.title,
            "quantity": booking.quantity,
            "price": offer.discount_price,
            "status": booking.status,
            "created_at": booking.created_at.isoformat(),
            "customer_name": customer.name,
            "customer_phone": customer.phone
        }
        for booking, offer, customer in rows
    ]


@router.post("/orders/{order_id}/confirm")
async def confirm_order(
    order_id: int,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_session)
):
    """Confirm order"""
    result = await db.execute(
        select(Booking, Offer).join(
            Offer, Booking.offer_id == Offer.offer_id
        ).where(
            and_(
                Booking.booking_id == order_id,
                Offer.seller_id == partner.user_id
            )
        )
    )
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    
    booking, offer = row
    booking.status = 'confirmed'
    await db.commit()
    
    return {"booking_id": order_id, "status": "confirmed"}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_session)
):
    """Cancel order"""
    result = await db.execute(
        select(Booking, Offer).join(
            Offer, Booking.offer_id == Offer.offer_id
        ).where(
            and_(
                Booking.booking_id == order_id,
                Offer.seller_id == partner.user_id
            )
        )
    )
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    
    booking, offer = row
    booking.status = 'cancelled'
    await db.commit()
    
    return {"booking_id": order_id, "status": "cancelled"}


# Stats
@router.get("/stats")
async def get_stats(
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_session),
    period: str = Query("today", regex="^(today|week|month|all)$")
):
    """Get partner statistics"""
    period_enum = Period[period.upper()]
    
    # Get store_id
    store_result = await db.execute(
        select(Store.store_id).where(Store.owner_id == partner.user_id)
    )
    store_id = store_result.scalar_one_or_none()
    
    stats = await get_partner_stats(
        db=db,
        partner_id=partner.user_id,
        period=period_enum,
        tz="Asia/Tashkent",
        store_id=store_id
    )
    
    # Count active products
    active_count = await db.execute(
        select(func.count(Offer.offer_id)).where(
            and_(
                Offer.seller_id == partner.user_id,
                Offer.status == 'active'
            )
        )
    )
    active_products = active_count.scalar() or 0
    
    return {
        "period": period,
        "totals": {
            "revenue": stats.revenue,
            "orders": stats.orders,
            "items_sold": stats.items_sold,
            "avg_ticket": stats.avg_ticket,
            "active_products": active_products
        }
    }


# Store settings
@router.put("/store")
async def update_store(
    settings: dict,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_session)
):
    """Update store settings"""
    result = await db.execute(
        select(Store).where(Store.owner_id == partner.user_id)
    )
    store = result.scalar_one_or_none()
    
    if not store:
        # Create store if doesn't exist
        store = Store(
            owner_id=partner.user_id,
            name=settings.get('name', 'Мой магазин'),
            address=settings.get('address'),
            phone=settings.get('phone'),
            description=settings.get('description'),
            created_at=datetime.utcnow()
        )
        db.add(store)
    else:
        # Update existing
        if 'name' in settings:
            store.name = settings['name']
        if 'address' in settings:
            store.address = settings['address']
        if 'phone' in settings:
            store.phone = settings['phone']
        if 'description' in settings:
            store.description = settings['description']
    
    await db.commit()
    
    return {"status": "updated"}
