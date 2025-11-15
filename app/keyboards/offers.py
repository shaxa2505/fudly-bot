"""Inline keyboards for offer browsing flows."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def hot_offers_pagination_keyboard(lang: str, has_more: bool, next_offset: int) -> InlineKeyboardMarkup | None:
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Обновить" всегда слева
    refresh_text = "Обновить" if lang == "ru" else "Yangilash"
    builder.button(text=refresh_text, callback_data="hot_offers_refresh")
    
    # Кнопка "Далее" справа (если есть ещё товары)
    if has_more:
        next_text = "Далее →" if lang == "ru" else "Keyingi →"
        builder.button(text=next_text, callback_data=f"hot_offers_next_{next_offset}")
        builder.adjust(2)  # Две кнопки в ряд
    else:
        builder.adjust(1)  # Только "Обновить"
    
    return builder.as_markup() if builder.export() else None


def store_card_keyboard(lang: str, store_id: int, offers_count: int, ratings_count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    products = "🛍 Все товары" if lang == "ru" else "🛍 Barcha mahsulotlar"
    reviews = "⭐ Отзывы" if lang == "ru" else "⭐ Sharhlar"
    back = "◀️ Назад" if lang == "ru" else "◀️ Orqaga"
    builder.button(text=f"{products} ({offers_count})", callback_data=f"store_offers_{store_id}")
    builder.button(text=f"{reviews} ({ratings_count})", callback_data=f"store_reviews_{store_id}")
    builder.button(text=back, callback_data="back_to_places")
    builder.adjust(1)
    return builder.as_markup()


def offer_details_keyboard(lang: str, offer_id: int, store_id: int, delivery_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    pickup = "Забронировать" if lang == "ru" else "Bron qilish"
    builder.button(text=pickup, callback_data=f"book_{offer_id}")
    if delivery_enabled:
        delivery = "Заказать с доставкой" if lang == "ru" else "Yetkazib berish"
        builder.button(text=delivery, callback_data=f"order_delivery_{offer_id}")
    about = "О магазине" if lang == "ru" else "Do'kon haqida"
    builder.button(text=about, callback_data=f"store_info_{store_id}")
    builder.adjust(1)
    return builder.as_markup()


def offer_quick_keyboard(lang: str, offer_id: int, store_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    book = "🛒 Забронировать" if lang == "ru" else "🛒 Bron qilish"
    about = "🏪 О магазине" if lang == "ru" else "🏪 Do'kon haqida"
    builder.button(text=book, callback_data=f"book_{offer_id}")
    builder.button(text=about, callback_data=f"store_info_{store_id}")
    builder.adjust(1)
    return builder.as_markup()


def store_offers_keyboard(
    lang: str,
    store_id: int,
    has_more: bool,
    next_offset: int | None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_more and next_offset is not None:
        next_text = "➡️ Показать ещё 20" if lang == "ru" else "➡️ Yana 20 ta"
        builder.button(text=next_text, callback_data=f"store_offers_next_{store_id}_{next_offset}")
    back = "◀️ К магазину" if lang == "ru" else "◀️ Do'konga qaytish"
    builder.button(text=back, callback_data=f"back_to_store_{store_id}")
    builder.adjust(1)
    return builder.as_markup()


def store_reviews_keyboard(lang: str, store_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    back = "◀️ К магазину" if lang == "ru" else "◀️ Do'konga qaytish"
    builder.button(text=back, callback_data=f"back_to_store_{store_id}")
    builder.adjust(1)
    return builder.as_markup()


def back_to_hot_keyboard(lang: str, has_more: bool) -> InlineKeyboardMarkup | None:
    builder = InlineKeyboardBuilder()
    if has_more:
        next_text = "➡️ Показать ещё 20" if lang == "ru" else "➡️ Yana 20 ta ko'rsatish"
        builder.button(text=next_text, callback_data="hot_offers_next_20")
    builder.adjust(1)
    return builder.as_markup() if builder.export() else None
