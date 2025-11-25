"""Booking utilities - shared helpers for booking handlers."""
from typing import Any, Optional
from aiogram import types
from logging_config import logger


async def safe_edit_reply_markup(message: Optional[types.Message], reply_markup: Any = None) -> None:
    """Safely edit message reply markup."""
    try:
        if message and hasattr(message, 'edit_reply_markup'):
            await message.edit_reply_markup(reply_markup=reply_markup)
    except Exception as e:
        logger.debug(f"Could not edit reply markup: {e}")


async def safe_answer_or_send(
    message: Optional[types.Message], 
    user_id: int, 
    text: str, 
    bot: Any = None,
    **kwargs
) -> None:
    """Safely answer via message or send directly via bot."""
    try:
        if message and hasattr(message, 'answer'):
            await message.answer(text, **kwargs)
        elif bot:
            await bot.send_message(user_id, text, **kwargs)
        else:
            logger.error("No message or bot available to send response")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")


def can_proceed(user_id: int, operation: str) -> bool:
    """Check if user can proceed with operation (rate limiting placeholder)."""
    # TODO: Implement proper rate limiting with Redis
    return True


def get_store_field(store: Any, field: str, default: Any = None) -> Any:
    """Safely get field from store object (dict or tuple)."""
    if not store:
        return default
    
    if isinstance(store, dict):
        return store.get(field, default)
    elif isinstance(store, (tuple, list)):
        field_map = {
            'store_id': 0, 'owner_id': 1, 'name': 2, 'address': 3, 'phone': 4,
            'city': 5, 'category': 6, 'description': 7, 'status': 8,
            'delivery_enabled': 9, 'delivery_price': 10, 'min_order_amount': 11
        }
        idx = field_map.get(field)
        if idx is not None and len(store) > idx:
            return store[idx]
        return default
    
    return default


def get_offer_field(offer: Any, field: str, default: Any = None) -> Any:
    """Safely get field from offer object (dict or tuple)."""
    if not offer:
        return default
    
    if isinstance(offer, dict):
        return offer.get(field, default)
    elif isinstance(offer, (tuple, list)):
        field_map = {
            'offer_id': 0, 'store_id': 1, 'title': 2, 'description': 3, 
            'original_price': 4, 'discount_price': 5, 'quantity': 6, 
            'available_from': 7, 'available_until': 8, 'photo': 9,
            'is_active': 10, 'created_at': 11, 'unit': 12, 'category': 13,
            'expiry_date': 14, 'store_name': 15, 'address': 16
        }
        idx = field_map.get(field)
        if idx is not None and len(offer) > idx:
            return offer[idx]
        return default
    
    return default


def get_booking_field(booking: Any, field: str, default: Any = None) -> Any:
    """Safely get field from booking object (dict or tuple)."""
    if not booking:
        return default
    
    if isinstance(booking, dict):
        return booking.get(field, default)
    elif isinstance(booking, (tuple, list)):
        field_map = {
            'booking_id': 0, 'offer_id': 1, 'user_id': 2, 'status': 3,
            'code': 4, 'pickup_time': 5, 'quantity': 6, 'created_at': 7,
            'store_id': 8, 'delivery_option': 9, 'delivery_address': 10, 
            'delivery_cost': 11, 'payment_proof_photo_id': 12
        }
        idx = field_map.get(field)
        if idx is not None and len(booking) > idx:
            return booking[idx]
        return default
    
    return default


def get_user_safe(db: Any, user_id: int) -> Any:
    """Safely get user model from database."""
    try:
        return db.get_user_model(user_id)
    except Exception:
        return None


def format_booking_code(code: Optional[str], booking_id: Optional[int] = None) -> str:
    """Format booking code for display, with fallback to booking_id."""
    if code:
        return code
    if booking_id:
        return str(booking_id)
    return "---"


def calculate_total(price: float, quantity: int, delivery_cost: int = 0) -> int:
    """Calculate total order amount."""
    return int(price * quantity) + delivery_cost
