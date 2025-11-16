"""Inline keyboards for common flows."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from localization import get_text


def offer_keyboard(offer_id: int, lang: str = 'ru') -> InlineKeyboardMarkup:
    """Basic offer keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, 'book'), callback_data=f"book_{offer_id}")
    builder.button(text=get_text(lang, 'details'), callback_data=f"details_{offer_id}")
    builder.adjust(1)
    return builder.as_markup()


def filters_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    """Filters keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💰 По цене" if lang == 'ru' else "💰 Narx bo'yicha", 
        callback_data="filter_price"
    )
    builder.button(
        text="📂 По категории" if lang == 'ru' else "📂 Kategoriya bo'yicha", 
        callback_data="filter_category"
    )
    builder.button(
        text="⭐ По рейтингу" if lang == 'ru' else "⭐ Reyting bo'yicha", 
        callback_data="filter_rating"
    )
    builder.button(
        text="❌ Сбросить" if lang == 'ru' else "❌ Tozalash", 
        callback_data="filter_reset"
    )
    builder.adjust(1)
    return builder.as_markup()


def rating_filter_keyboard() -> InlineKeyboardMarkup:
    """Rating filter keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐⭐⭐⭐ 4+ звезды", callback_data="rating_4")
    builder.button(text="⭐⭐⭐ 3+ звезды", callback_data="rating_3")
    builder.button(text="⭐⭐ 2+ звезды", callback_data="rating_2")
    builder.button(text="⭐ 1+ звезда", callback_data="rating_1")
    builder.button(text="❌ Без фильтра", callback_data="rating_0")
    builder.adjust(1)
    return builder.as_markup()
