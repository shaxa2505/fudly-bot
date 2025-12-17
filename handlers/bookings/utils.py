"""Booking utilities - shared helpers for booking handlers."""
from typing import Any

from aiogram import types

# Import shared field extractors from central utils
from app.core.utils import (
    get_booking_field,
    get_offer_field,
    get_store_field,
)
from logging_config import logger

# Re-export for backward compatibility
__all__ = [
    "safe_edit_reply_markup",
    "safe_answer_or_send",
    "can_proceed",
    "get_store_field",
    "get_offer_field",
    "get_booking_field",
    "get_user_safe",
    "get_user_field",
    "format_booking_code",
    "calculate_total",
    "format_price",
]


def format_price(amount_in_kopeks: int | float, lang: str = "ru") -> str:
    """
    Format price from kopeks (stored in DB) to human-readable format.
    
    Args:
        amount_in_kopeks: Price in kopeks (1 sum = 100 kopeks)
        lang: Language code ('uz' or 'ru')
    
    Returns:
        Formatted price string like "35 000 сум" or "35 000 so'm"
    
    Example:
        >>> format_price(3500000, "ru")
        '35 000 сум'
        >>> format_price(3500000, "uz")
        '35 000 so'm'
    """
    if not amount_in_kopeks and amount_in_kopeks != 0:
        amount_in_kopeks = 0
    
    # Convert kopeks to sums
    amount_in_sums = int(amount_in_kopeks) // 100
    
    # Format with spaces as thousand separators
    formatted = f"{amount_in_sums:,}".replace(",", " ")
    
    # Add currency suffix
    currency = "so'm" if lang == "uz" else "сум"
    return f"{formatted} {currency}"


async def safe_edit_reply_markup(message: types.Message | None, reply_markup: Any = None) -> None:
    """Safely edit message reply markup."""
    try:
        if message and hasattr(message, "edit_reply_markup"):
            await message.edit_reply_markup(reply_markup=reply_markup)
    except Exception as e:
        logger.debug(f"Could not edit reply markup: {e}")


async def safe_answer_or_send(
    message: types.Message | None, user_id: int, text: str, bot: Any = None, **kwargs
) -> None:
    """Safely answer via message or send directly via bot."""
    try:
        if message and hasattr(message, "answer"):
            await message.answer(text, **kwargs)
        elif bot:
            await bot.send_message(user_id, text, **kwargs)
        else:
            logger.error("No message or bot available to send response")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")


def can_proceed(user_id: int, operation: str) -> bool:
    """Check if user can proceed with operation.

    Note: Rate limiting is now implemented at middleware level (see app.middlewares.rate_limit).
    This function is kept for backwards compatibility and additional business logic checks.
    """
    return True


# NOTE: get_store_field, get_offer_field, get_booking_field are now imported
# from app.core.utils - removed duplicate definitions


def get_user_safe(db: Any, user_id: int) -> dict | None:
    """Safely get user dict from database."""
    try:
        # Try get_user first (returns dict)
        user = db.get_user(user_id)
        if user:
            return user
        # Fallback to get_user_model
        model = db.get_user_model(user_id)
        if model and hasattr(model, "model_dump"):
            return model.model_dump()
        elif model and hasattr(model, "__dict__"):
            return model.__dict__
        return None
    except Exception as e:
        logger.debug(f"get_user_safe failed for {user_id}: {e}")
        return None


def get_user_field(user: Any, field: str, default: Any = None) -> Any:
    """Get field from user (dict or model)."""
    if user is None:
        return default
    if isinstance(user, dict):
        return user.get(field, default)
    return getattr(user, field, default)


def format_booking_code(code: str | None, booking_id: int | None = None) -> str:
    """Format booking code for display, with fallback to booking_id."""
    if code:
        return code
    if booking_id:
        return str(booking_id)
    return "---"


def calculate_total(price: float, quantity: int, delivery_cost: int = 0) -> int:
    """Calculate total order amount."""
    return int(price * quantity) + delivery_cost
