"""Inline keyboards for offer browsing flows."""
from __future__ import annotations

from typing import Sequence, Any

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def hot_offers_compact_keyboard(
    lang: str, offers: Sequence[Any], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """Compact keyboard for hot offers with item buttons and pagination."""
    builder = InlineKeyboardBuilder()
    
    # Add buttons for each offer (max 5)
    for idx, offer in enumerate(offers[:5], start=1):
        offer_id = offer.id if hasattr(offer, 'id') else offer.get('offer_id', 0)
        title = offer.title if hasattr(offer, 'title') else offer.get('title', 'Товар')
        short_title = title[:12] + ".." if len(title) > 12 else title
        builder.button(text=f"{idx}. {short_title}", callback_data=f"hot_offer_{offer_id}")
    
    # Adjust offer buttons: 2 per row for 5 items = 2+2+1
    if len(offers) == 5:
        builder.adjust(2, 2, 1)
    elif len(offers) == 4:
        builder.adjust(2, 2)
    elif len(offers) == 3:
        builder.adjust(2, 1)
    elif len(offers) == 2:
        builder.adjust(2)
    else:
        builder.adjust(1)
    
    # Pagination row
    nav_builder = InlineKeyboardBuilder()
    if page > 0:
        nav_builder.button(text="◀️", callback_data=f"hot_page_{page - 1}")
    nav_builder.button(text=f"{page + 1}/{total_pages}", callback_data="hot_noop")
    if page < total_pages - 1:
        nav_builder.button(text="▶️", callback_data=f"hot_page_{page + 1}")
    
    # Refresh button
    refresh_text = "🔄" if lang == "ru" else "🔄"
    nav_builder.button(text=refresh_text, callback_data="hot_offers_refresh")
    
    # Adjust nav: pagination buttons + refresh
    if page > 0 and page < total_pages - 1:
        nav_builder.adjust(3, 1)  # ◀️ 1/5 ▶️ then 🔄
    elif page > 0 or page < total_pages - 1:
        nav_builder.adjust(2, 1)  # ◀️ 1/5 or 1/5 ▶️ then 🔄
    else:
        nav_builder.adjust(1, 1)  # Just 1/1 then 🔄
    
    # Combine keyboards
    builder.attach(nav_builder)
    
    return builder.as_markup()


def hot_offers_pagination_keyboard(
    lang: str, has_more: bool, next_offset: int
) -> InlineKeyboardMarkup | None:
    builder = InlineKeyboardBuilder()

    # Кнопка "Обновить" всегда слева
    refresh_text = "🔄 Обновить" if lang == "ru" else "🔄 Yangilash"
    builder.button(text=refresh_text, callback_data="hot_offers_refresh")

    # Кнопка "Далее" справа (если есть ещё товары)
    if has_more:
        next_text = "Далее ➡️" if lang == "ru" else "Keyingi ➡️"
        builder.button(text=next_text, callback_data=f"hot_offers_next_{next_offset}")
        builder.adjust(2)  # Две кнопки в ряд
    else:
        builder.adjust(1)  # Только "Обновить"

    return builder.as_markup() if builder.export() else None


def store_card_keyboard(
    lang: str, store_id: int, offers_count: int, ratings_count: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    products = "🛍 Посмотреть товары" if lang == "ru" else "🛍 Mahsulotlarni ko'rish"
    back = "◀️ Назад" if lang == "ru" else "◀️ Orqaga"

    # Показывать количество только если товары есть
    if offers_count > 0:
        button_text = f"{products} ({offers_count})"
    else:
        button_text = products

    builder.button(text=button_text, callback_data=f"store_offers_{store_id}")
    builder.button(text=back, callback_data="back_to_places")
    builder.adjust(1)
    return builder.as_markup()


def offer_details_keyboard(
    lang: str, offer_id: int, store_id: int, delivery_enabled: bool
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Inline buttons: Заказать и О магазине (menu keeps delivery/pickup choice)
    pickup = "✅ Заказать" if lang == "ru" else "✅ Buyurtma"
    builder.button(text=pickup, callback_data=f"book_{offer_id}")
    about = "🏪 О магазине" if lang == "ru" else "🏪 Do'kon haqida"
    builder.button(text=about, callback_data=f"store_info_{store_id}")
    builder.adjust(2)
    return builder.as_markup()


def offer_quick_keyboard(
    lang: str, offer_id: int, store_id: int, delivery_enabled: bool = False
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    pickup = "✅ Заказать" if lang == "ru" else "✅ Buyurtma"
    builder.button(text=pickup, callback_data=f"book_{offer_id}")
    about = "🏪 О магазине" if lang == "ru" else "🏪 Do'kon haqida"
    builder.button(text=about, callback_data=f"store_info_{store_id}")
    builder.adjust(2)
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


def store_list_keyboard(
    lang: str,
    stores: list,
) -> InlineKeyboardMarkup:
    """Keyboard with inline buttons for store selection."""
    builder = InlineKeyboardBuilder()
    for idx, store in enumerate(stores, 1):
        # store can be StoreSummary object or dict
        store_id = store.id if hasattr(store, 'id') else store.get('store_id', idx)
        store_name = store.name if hasattr(store, 'name') else store.get('name', f'Store {idx}')
        # Truncate long names
        display_name = store_name[:25] + "..." if len(store_name) > 25 else store_name
        builder.button(text=f"{idx}. {display_name}", callback_data=f"select_store_{store_id}")
    back = "◀️ Назад" if lang == "ru" else "◀️ Orqaga"
    builder.button(text=back, callback_data="back_to_places")
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
