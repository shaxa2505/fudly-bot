"""Booking utilities."""
from typing import Any, Optional
from aiogram import types
from database_protocol import DatabaseProtocol
from logging_config import logger


def _safe_edit_reply_markup(message: Optional[types.Message], reply_markup: Any) -> None:
    """Safely edit message reply markup."""
    try:
        if message and hasattr(message, 'edit_reply_markup'):
            message.edit_reply_markup(reply_markup=reply_markup)
    except Exception as e:
        logger.debug(f"Could not edit reply markup: {e}")


async def _safe_answer_or_send(message: Optional[types.Message], user_id: int, text: str, **kwargs) -> None:
    """Safely answer or send message."""
    try:
        if message and hasattr(message, 'answer'):
            await message.answer(text, **kwargs)
        else:
            from bot import bot
            await bot.send_message(user_id, text, **kwargs)
    except Exception as e:
        logger.error(f"Failed to send message: {e}")


def can_proceed(user_id: int, operation: str) -> bool:
    """Check if user can proceed with operation (rate limiting)."""
    # Simplified rate limiting - implement as needed
    return True


def get_store_field(store: Any, field: str, default: Any = None) -> Any:
    """Safely get field from store object."""
    if not store:
        return default
    
    if isinstance(store, dict):
        return store.get(field, default)
    elif isinstance(store, (tuple, list)):
        field_map = {
            'owner_id': 1, 'name': 2, 'address': 3, 'phone': 4,
            'delivery_enabled': 9, 'delivery_price': 10, 'min_order_amount': 11
        }
        idx = field_map.get(field)
        return store[idx] if idx and len(store) > idx else default
    
    return default


def get_offer_field(offer: Any, field: str, default: Any = None) -> Any:
    """Safely get field from offer object."""
    if not offer:
        return default
    
    if isinstance(offer, dict):
        return offer.get(field, default)
    elif isinstance(offer, (tuple, list)):
        field_map = {
            'store_id': 1, 'title': 2, 'description': 3, 'original_price': 4,
            'discount_price': 5, 'quantity': 6, 'unit': 7, 'address': 16
        }
        idx = field_map.get(field)
        return offer[idx] if idx and len(offer) > idx else default
    
    return default


def get_booking_field(booking: Any, field: str, default: Any = None) -> Any:
    """Safely get field from booking object."""
    if not booking:
        return default
    
    if isinstance(booking, dict):
        return booking.get(field, default)
    elif isinstance(booking, (tuple, list)):
        field_map = {
            'booking_id': 0, 'offer_id': 1, 'user_id': 2, 'status': 3,
            'code': 4, 'pickup_time': 5, 'quantity': 6, 'created_at': 7,
            'delivery_option': 8, 'delivery_address': 9, 'delivery_cost': 10
        }
        idx = field_map.get(field)
        return booking[idx] if idx and len(booking) > idx else default
    
    return default


def get_user_safe(db: DatabaseProtocol, user_id: int) -> Any:
    """Safely get user model."""
    try:
        return db.get_user_model(user_id)
    except Exception:
        return None
