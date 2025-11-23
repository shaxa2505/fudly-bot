"""Helper utilities for bookings handlers (extracted for clarity)."""
from __future__ import annotations

from typing import Any
from aiogram import types as _ai_types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from types import SimpleNamespace

from app.core.cache import CacheManager
from localization import get_text


async def _safe_edit_reply_markup(msg_like, **kwargs) -> None:
    """Edit reply markup if message is accessible (Message), otherwise ignore."""
    if isinstance(msg_like, _ai_types.Message):
        try:
            await msg_like.edit_reply_markup(**kwargs)
        except Exception:
            pass


async def _safe_answer_or_send(msg_like, user_id: int, text: str, **kwargs) -> None:
    """Try to answer via message.answer, fallback to bot.send_message.

    Note: the calling module provides the `bot` instance and will perform the
    fallback send if necessary.
    """
    if isinstance(msg_like, _ai_types.Message):
        try:
            await msg_like.answer(text, **kwargs)
            return
        except Exception:
            pass


# Rate limiting placeholder
def can_proceed(user_id: int, action: str) -> bool:
    """Rate limiting check - placeholder."""
    return True


def get_store_field(store: Any, field: str, default: Any = None) -> Any:
    """Extract field from store tuple/dict."""
    if isinstance(store, dict):
        return store.get(field, default)
    if isinstance(store, (tuple, list)):
        field_map = {
            "store_id": 0, "owner_id": 1, "name": 2, "city": 3,
            "address": 4, "description": 5, "category": 6, "phone": 7,
            "status": 8, "rejection_reason": 9, "created_at": 10
        }
        idx = field_map.get(field)
        if idx is not None and len(store) > idx:
            return store[idx]
    return default


def get_offer_field(offer: Any, field: str, default: Any = None) -> Any:
    """Extract field from offer tuple/dict."""
    if isinstance(offer, dict):
        return offer.get(field, default)
    if isinstance(offer, (tuple, list)):
        field_map = {
            "offer_id": 0, "store_id": 1, "title": 2, "description": 3,
            "original_price": 4, "discount_price": 5, "quantity": 6,
            "available_from": 7, "available_until": 8, "expiry_date": 9,
            "status": 10, "photo": 11, "created_at": 12, "unit": 13,
            "category": 14, "store_name": 15, "address": 16, "city": 17
        }
        idx = field_map.get(field)
        if idx is not None and len(offer) > idx:
            return offer[idx]
    return default


def get_booking_field(booking: Any, field: str, default: Any = None) -> Any:
    """Extract field from booking tuple/dict."""
    if isinstance(booking, dict):
        # Support common aliases returned by different DB layers
        if field == 'code':
            return booking.get('code') or booking.get('booking_code') or booking.get('bookingCode') or default
        # Fallback to direct get for other fields
        return booking.get(field, default)
    if isinstance(booking, (tuple, list)):
        field_map = {
            "booking_id": 0, "offer_id": 1, "user_id": 2, "status": 3,
            "code": 4, "pickup_time": 5, "quantity": 6, "created_at": 7
        }
        idx = field_map.get(field)
        if idx is not None and len(booking) > idx:
            return booking[idx]
    return default


def get_bookings_filter_keyboard(lang: str):
    """Create bookings filter keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "filter_upcoming"), callback_data="filter_upcoming")
    builder.button(text=get_text(lang, "filter_past"), callback_data="filter_past")
    builder.button(text=get_text(lang, "filter_all"), callback_data="filter_all")
    builder.adjust(3)
    return builder.as_markup()


def get_user_safe(db, user_id: int) -> SimpleNamespace:
    """Return a lightweight user-like object with safe attributes.

    Tries `db.get_user_model` (Pydantic model). If conversion fails or is
    unavailable, falls back to `db.get_user` (dict) and ensures minimal
    attributes exist so handlers can continue.
    """
    try:
        user_model = db.get_user_model(user_id)
        if user_model:
            return SimpleNamespace(
                user_id=user_model.user_id,
                username=getattr(user_model, 'username', None),
                first_name=getattr(user_model, 'first_name', '') or '',
                phone=getattr(user_model, 'phone', None),
                city=getattr(user_model, 'city', 'Ташкент'),
                language=getattr(user_model, 'language', 'ru'),
            )
    except Exception:
        pass

    # Fallback to raw dict
    try:
        row = db.get_user(user_id)
        if row:
            first = row.get('first_name') if isinstance(row, dict) else (row[2] if len(row) > 2 else '')
            phone = row.get('phone') if isinstance(row, dict) else (row[3] if len(row) > 3 else None)
            username = row.get('username') if isinstance(row, dict) else (row[1] if len(row) > 1 else None)
            city = row.get('city') if isinstance(row, dict) else (row[4] if len(row) > 4 else 'Ташкент')
            language = row.get('language') if isinstance(row, dict) else (row[5] if len(row) > 5 else 'ru')
            return SimpleNamespace(
                user_id=user_id,
                username=username,
                first_name=first or (username or ''),
                phone=phone,
                city=city or 'Ташкент',
                language=language or 'ru',
            )
    except Exception:
        pass

    # Ultimate fallback
    return SimpleNamespace(user_id=user_id, username=None, first_name='', phone=None, city='Ташкент', language='ru')
