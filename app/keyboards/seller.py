"""Seller/Partner-specific keyboards."""
from __future__ import annotations

from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from localization import get_text


def main_menu_seller(lang: str = 'ru') -> ReplyKeyboardMarkup:
    """Simplified partner menu: Add, Products, Orders, Today, Profile."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=get_text(lang, 'add_item'))
    builder.button(text=get_text(lang, 'my_items'))
    builder.button(text=get_text(lang, 'orders'))
    builder.button(text=get_text(lang, 'today_stats'))
    builder.button(text=get_text(lang, 'profile'))
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def offer_manage_keyboard(offer_id: int, lang: str = 'ru') -> InlineKeyboardMarkup:
    """Offer management keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, 'duplicate'), callback_data=f"duplicate_{offer_id}")
    builder.button(text=get_text(lang, 'delete'), callback_data=f"delete_offer_{offer_id}")
    builder.adjust(2)
    return builder.as_markup()


def store_keyboard(store_id: int) -> InlineKeyboardMarkup:
    """Store management keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data=f"store_stats_{store_id}")
    builder.button(text="📋 Предложения", callback_data=f"store_offers_{store_id}")
    builder.adjust(2)
    return builder.as_markup()


def moderation_keyboard(store_id: int) -> InlineKeyboardMarkup:
    """Store moderation keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"approve_store_{store_id}")
    builder.button(text="❌ Отклонить", callback_data=f"reject_store_{store_id}")
    builder.adjust(2)
    return builder.as_markup()
