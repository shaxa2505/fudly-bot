"""Booking utilities - shared helpers for booking handlers."""
from typing import Any, Optional
from aiogram import types
from logging_config import logger

# Import shared field extractors from central utils
from app.core.utils import (
    get_store_field,
    get_offer_field,
    get_booking_field,
)

# Re-export for backward compatibility
__all__ = [
    'safe_edit_reply_markup',
    'safe_answer_or_send', 
    'can_proceed',
    'get_store_field',
    'get_offer_field',
    'get_booking_field',
    'get_user_safe',
    'format_booking_code',
    'calculate_total',
]


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


# NOTE: get_store_field, get_offer_field, get_booking_field are now imported
# from app.core.utils - removed duplicate definitions


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
