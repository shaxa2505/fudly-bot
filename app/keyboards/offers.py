"""Inline keyboards for offer browsing flows."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.constants import OFFERS_PER_PAGE, STORES_PER_PAGE
from localization import get_text


def hot_entry_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Entry keyboard for the main 'Магазины и акции' button."""
    builder = InlineKeyboardBuilder()
    deals = "Акции" if lang == "ru" else "Aksiyalar"
    stores = "Магазины" if lang == "ru" else "Do'konlar"
    change_city = "Сменить город" if lang == "ru" else "Shaharni almashtirish"

    builder.button(text=deals, callback_data="hot_entry_offers")
    builder.button(text=stores, callback_data="hot_entry_stores")
    builder.button(text=change_city, callback_data="profile_change_city")
    builder.adjust(2, 1)
    return builder.as_markup()


def hot_offers_compact_keyboard(
    lang: str,
    offers: Sequence[Any],
    page: int,
    total_pages: int,
    show_entry_back: bool = False,
) -> InlineKeyboardMarkup:
    """Compact keyboard for hot offers with item buttons and pagination."""
    builder = InlineKeyboardBuilder()

    # Add one action button per offer - keep label short and clean
    action = "✅ Применить" if lang == "ru" else "✅ Qo'llash"
    for offer in offers:
        offer_id = offer.id if hasattr(offer, "id") else offer.get("offer_id", 0)
        title = offer.title if hasattr(offer, "title") else offer.get("title", "")
        short_title = title[:24] + ".." if len(title) > 26 else title
        builder.button(
            text=f"{action} - {short_title}",
            callback_data=f"hot_offer_{offer_id}",
        )

    # Adjust offer buttons: 1 per row for better readability
    builder.adjust(1)

    # Pagination row - only prev/next and refresh
    nav_builder = InlineKeyboardBuilder()
    if page > 0:
        nav_builder.button(text="Назад" if lang == "ru" else "Oldingi", callback_data=f"hot_page_{page - 1}")
    if page < total_pages - 1:
        nav_builder.button(text="Далее" if lang == "ru" else "Keyingi", callback_data=f"hot_page_{page + 1}")

    # Refresh button
    nav_builder.button(text="Обновить" if lang == "ru" else "Yangilash", callback_data="hot_offers_refresh")

    # Adjust nav: pagination buttons + refresh
    if page > 0 and page < total_pages - 1:
        nav_builder.adjust(3)  # ◀️ ▶️ 🔄
    elif page > 0 or page < total_pages - 1:
        nav_builder.adjust(2)  # ◀️ 🔄 or ▶️ 🔄
    else:
        nav_builder.adjust(1)  # Just 🔄

    # Combine keyboards
    builder.attach(nav_builder)

    if show_entry_back:
        back_builder = InlineKeyboardBuilder()
        back_builder.button(text=get_text(lang, "back"), callback_data="hot_entry_back")
        back_builder.adjust(1)
        builder.attach(back_builder)

    return builder.as_markup()


# NOTE: hot_offers_pagination_keyboard removed - using hot_offers_compact_keyboard now


def store_card_keyboard(
    lang: str,
    store_id: int,
    offers_count: int,
    ratings_count: int,
    back_callback: str = "back_to_places",
    back_text: str | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    products = "Товары" if lang == "ru" else "Mahsulotlar"
    if back_text:
        back = back_text
    elif back_callback == "back_to_store_list":
        back = "К списку магазинов" if lang == "ru" else "Do'konlar ro'yxati"
    else:
        back = "Назад" if lang == "ru" else "Orqaga"

    # Показывать количество только если товары есть
    if offers_count > 0:
        button_text = f"{products} ({offers_count})"
    else:
        button_text = products

    builder.button(text=button_text, callback_data=f"store_offers_{store_id}")
    builder.button(text=back, callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def offer_details_keyboard(
    lang: str, offer_id: int, store_id: int, delivery_enabled: bool
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Add to cart button (primary action)
    cart = "🛒 В корзину" if lang == "ru" else "🛒 Savatga qo'shish"
    builder.button(text=cart, callback_data=f"add_to_cart_{offer_id}")

    # Quick order button (skip cart) - clearer text
    order = "⚡ Быстрый заказ" if lang == "ru" else "⚡ Tez buyurtma"
    builder.button(text=order, callback_data=f"book_{offer_id}")

    builder.adjust(2)
    return builder.as_markup()


def offer_details_with_back_keyboard(
    lang: str,
    offer_id: int,
    store_id: int,
    delivery_enabled: bool,
    back_callback: str = "back_to_hot",
    back_text: str | None = None,
) -> InlineKeyboardMarkup:
    """Offer card keyboard - simplified to 2 main actions + back."""
    builder = InlineKeyboardBuilder()

    # Main action: Add to cart (most common)
    cart = "🛒 В корзину" if lang == "ru" else "🛒 Savatga qo'shish"
    builder.button(text=cart, callback_data=f"add_to_cart_{offer_id}")

    # Quick order button - clearer text
    order = "⚡ Быстрый заказ" if lang == "ru" else "⚡ Tez buyurtma"
    builder.button(text=order, callback_data=f"book_{offer_id}")

    # Back button - full width
    back = back_text or ("Назад к списку" if lang == "ru" else "Ro'yxatga qaytish")
    builder.button(text=back, callback_data=back_callback)

    builder.adjust(2, 1)  # 2 buttons top row, 1 bottom
    return builder.as_markup()


def offer_details_search_keyboard(
    lang: str, offer_id: int, store_id: int, delivery_enabled: bool
) -> InlineKeyboardMarkup:
    """Offer card keyboard for search results with back to search list."""
    builder = InlineKeyboardBuilder()

    # Main action: Add to cart
    cart = "🛒 В корзину" if lang == "ru" else "🛒 Savatga qo'shish"
    builder.button(text=cart, callback_data=f"add_to_cart_{offer_id}")

    # Quick order
    order = "⚡ Быстрый заказ" if lang == "ru" else "⚡ Tez buyurtma"
    builder.button(text=order, callback_data=f"book_{offer_id}")

    # Back to search results
    back = "Назад к результатам" if lang == "ru" else "Natijalarga qaytish"
    builder.button(text=back, callback_data="back_to_search_results")

    builder.adjust(2, 1)
    return builder.as_markup()


def offer_quick_keyboard(
    lang: str, offer_id: int, store_id: int, delivery_enabled: bool = False
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Add to cart - main action
    cart = "🛒 В корзину" if lang == "ru" else "🛒 Savatga qo'shish"
    builder.button(text=cart, callback_data=f"add_to_cart_{offer_id}")

    # Quick order - skip cart
    order = "⚡ Быстрый заказ" if lang == "ru" else "⚡ Tez buyurtma"
    builder.button(text=order, callback_data=f"book_{offer_id}")

    builder.adjust(2)
    return builder.as_markup()


def offer_in_cart_keyboard(lang: str, source: str = "generic") -> InlineKeyboardMarkup:
    """Keyboard for offer card after item has been added to cart.

    Source controls where the back button sends the user:
    - "hot" -> back to hot offers list
    - "search" -> back to search results
    - other -> back to main menu
    """
    builder = InlineKeyboardBuilder()

    # Open cart
    open_cart = "🛒 Открыть корзину" if lang == "ru" else "🛒 Savatni ochish"
    builder.button(text=open_cart, callback_data="view_cart")

    # Context-aware back
    if source == "hot":
        back_text = "⬅️ Назад к акциям" if lang == "ru" else "⬅️ Aksiyalarga qaytish"
        back_data = "back_to_hot"
    elif source == "search":
        back_text = "⬅️ Назад к результатам" if lang == "ru" else "⬅️ Natijalarga qaytish"
        back_data = "back_to_search_results"
    else:
        back_text = "⬅️ Назад" if lang == "ru" else "⬅️ Orqaga"
        back_data = "back_to_menu"

    builder.button(text=back_text, callback_data=back_data)
    builder.adjust(1, 1)
    return builder.as_markup()


def store_offers_keyboard(
    lang: str,
    store_id: int,
    has_more: bool,
    next_offset: int | None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_more and next_offset is not None:
        next_text = "Показать ещё 20" if lang == "ru" else "Yana 20 ta"
        builder.button(text=next_text, callback_data=f"store_offers_next_{store_id}_{next_offset}")
    back = "К магазину" if lang == "ru" else "Do'konga qaytish"
    builder.button(text=back, callback_data=f"back_to_store_{store_id}")
    builder.adjust(1)
    return builder.as_markup()


def store_offers_compact_keyboard(
    lang: str,
    offers: Sequence[Any],
    store_id: int,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Compact keyboard for store offers with item buttons and pagination (like hot offers)."""
    builder = InlineKeyboardBuilder()

    # Add one action button per offer
    action = "🔎 Открыть" if lang == "ru" else "🔎 Ochish"
    for offer in offers:
        offer_id = offer.id if hasattr(offer, "id") else offer.get("offer_id", 0)
        title = offer.title if hasattr(offer, "title") else offer.get("title", "Товар")
        short_title = title[:24] + ".." if len(title) > 26 else title
        builder.button(
            text=f"{action} - {short_title}", callback_data=f"store_offer_{store_id}_{offer_id}"
        )

    # One button per row for cleaner scan
    builder.adjust(1)

    # Pagination row - only prev/next and back
    nav_builder = InlineKeyboardBuilder()
    if page > 0:
        nav_builder.button(
            text="Назад" if lang == "ru" else "Oldingi",
            callback_data=f"store_offers_page_{store_id}_{page - 1}",
        )
    if page < total_pages - 1:
        nav_builder.button(
            text="Далее" if lang == "ru" else "Keyingi",
            callback_data=f"store_offers_page_{store_id}_{page + 1}",
        )

    # Back button
    back = "К магазину" if lang == "ru" else "Do'konga"
    nav_builder.button(text=back, callback_data=f"back_to_store_{store_id}")

    # Adjust nav: pagination buttons + back
    nav_count = 1  # back always
    if page > 0:
        nav_count += 1
    if page < total_pages - 1:
        nav_count += 1
    nav_builder.adjust(nav_count)

    # Combine keyboards
    builder.attach(nav_builder)

    return builder.as_markup()


def store_list_keyboard(
    lang: str,
    stores: list,
    page: int = 0,
    per_page: int = STORES_PER_PAGE,
) -> InlineKeyboardMarkup:
    """Compact keyboard for store selection with pagination (like hot offers)."""
    builder = InlineKeyboardBuilder()

    total = len(stores)
    start_idx = page * per_page
    page_stores = stores[start_idx : start_idx + per_page]

    action = "🗂 Открыть каталог" if lang == "ru" else "🗂 Katalogni ochish"
    # Store buttons - one per row
    for idx, store in enumerate(page_stores, start_idx + 1):
        store_id = store.id if hasattr(store, "id") else store.get("store_id", idx)
        store_name = store.name if hasattr(store, "name") else store.get("name", f"Store {idx}")
        short_name = store_name[:22] + ".." if len(store_name) > 24 else store_name
        builder.button(
            text=f"{action} - {short_name}", callback_data=f"select_store_{store_id}"
        )

    # One per row for clarity
    builder.adjust(1)

    # Pagination row
    nav_row = []
    if page > 0:
        prev_text = "Назад" if lang == "ru" else "Oldingi"
        builder.button(text=prev_text, callback_data=f"stores_page_{page - 1}")
        nav_row.append(1)

    # Page indicator
    total_pages = (total + per_page - 1) // per_page
    if total_pages > 1:
        builder.button(text=f"{page + 1}/{total_pages}", callback_data="stores_noop")
        nav_row.append(1)

    if start_idx + per_page < total:
        next_text = "Далее" if lang == "ru" else "Keyingi"
        builder.button(text=next_text, callback_data=f"stores_page_{page + 1}")
        nav_row.append(1)

    # Back button
    back = "К категориям" if lang == "ru" else "Toifalarga"
    builder.button(text=back, callback_data="back_to_places")

    # Final adjust: store buttons (1 col), then nav row, then back
    rows = [1] * len(page_stores)
    if nav_row:
        rows.append(sum(nav_row))
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def store_reviews_keyboard(lang: str, store_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    back = "К магазину" if lang == "ru" else "Do'konga qaytish"
    builder.button(text=back, callback_data=f"back_to_store_{store_id}")
    builder.adjust(1)
    return builder.as_markup()


# NOTE: back_to_hot_keyboard removed - not used, use offer_details_with_back_keyboard instead


def search_results_compact_keyboard(
    lang: str, offers: Sequence[Any], page: int, total_pages: int, query: str
) -> InlineKeyboardMarkup:
    """Simple keyboard for search results - just clickable items."""
    builder = InlineKeyboardBuilder()

    # Simple item buttons - one per row
    action = "🔎 Открыть" if lang == "ru" else "🔎 Ochish"
    for offer in offers:
        offer_id = offer.id if hasattr(offer, "id") else offer.get("offer_id", 0)
        title = offer.title if hasattr(offer, "title") else offer.get("title", "Товар")
        short_title = title[:26] + ".." if len(title) > 26 else title
        btn_text = f"{action} - {short_title}"
        builder.button(text=btn_text, callback_data=f"search_select_{offer_id}")

    # Pagination (only if needed)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            ("Назад" if lang == "ru" else "Oldingi", f"search_page_{page - 1}")
        )
    if total_pages > 1:
        nav_buttons.append((f"{page + 1}/{total_pages}", "search_noop"))
    if page < total_pages - 1:
        nav_buttons.append(
            ("Далее" if lang == "ru" else "Keyingi", f"search_page_{page + 1}")
        )

    for text, cb in nav_buttons:
        builder.button(text=text, callback_data=cb)

    # Adjust: each item is 1 button, navigation row at the end
    items_count = len(offers)
    if nav_buttons:
        builder.adjust(*([1] * items_count), len(nav_buttons))
    else:
        builder.adjust(1)

    return builder.as_markup()
