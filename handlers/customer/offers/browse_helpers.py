"""
Browse helpers - utility functions for offer browsing.

Extracted from browse.py for better maintainability.
Contains text formatters, validation helpers, and common utilities.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import types

from localization import get_text

if TYPE_CHECKING:
    from aiogram.fsm.context import FSMContext

    from app.services.offer_service import OfferListItem


def callback_message(callback: types.CallbackQuery) -> types.Message | None:
    """Return callback's message when accessible."""
    message = callback.message
    return message if isinstance(message, types.Message) else None


def no_stores_text(lang: str, business_type: str) -> str:
    """Generate 'no stores found' message for business type."""
    names = {
        "supermarket": get_text(lang, "supermarkets"),
        "restaurant": get_text(lang, "restaurants"),
        "bakery": get_text(lang, "bakeries"),
        "cafe": get_text(lang, "cafes"),
        "pharmacy": get_text(lang, "pharmacies"),
        "delivery": "🚚 Доставка" if lang == "ru" else "🚚 Yetkazish",
    }
    no_stores = (
        "В этой категории пока нет магазинов с активными предложениями"
        if lang == "ru"
        else "Bu kategoriyada hali do'konlar yo'q"
    )
    return f"😔 {names.get(business_type, business_type)}\n\n{no_stores}"


def invalid_number_text(lang: str, subject: str) -> str:
    """Generate 'invalid number' error message."""
    base = (
        "Пожалуйста, введите корректный номер"
        if lang == "ru"
        else "Iltimos, to'g'ri raqam kiriting"
    )
    return f"× {base}"


def range_text(lang: str, max_value: int, subject: str) -> str:
    """Generate 'number out of range' error message."""
    if lang == "ru":
        return f"❌ Номер должен быть от 1 до {max_value}"
    return f"❌ Raqam 1 dan {max_value} gacha bo'lishi kerak"


def format_hot_offers_header(lang: str, city: str, page: int, total_pages: int, total: int) -> str:
    """Format header for hot offers list."""
    header = "АКЦИИ" if lang == "ru" else "AKSIYALAR"
    items_word = "mahsulot" if lang == "uz" else "товаров"
    page_word = "Стр." if lang == "ru" else "Sah."
    text = f"🔥 <b>{header}</b> | 📍 {city}\n"
    text += f"{page_word} {page + 1}/{total_pages} ({total} {items_word})\n"
    text += "─" * 28 + "\n\n"
    return text


def format_offer_line(
    lang: str,
    idx: int,
    title: str,
    original_price: float,
    discount_price: float,
) -> str:
    """Format single offer line for list view."""
    currency = "so'm" if lang == "uz" else "сум"
    title = title[:25] + ".." if len(title) > 25 else title

    # Safe discount calculation - handle edge cases, use round() for proper rounding
    discount_pct = 0
    if original_price and discount_price and original_price > discount_price:
        discount_pct = min(99, max(0, round((1 - discount_price / original_price) * 100)))

    lines = [f"<b>{idx}.</b> {title}"]
    if discount_pct > 0:
        lines.append(
            f"    <s>{int(original_price) // 100:,}</s> → <b>{int(discount_price) // 100:,}</b> {currency} <i>(-{discount_pct}%)</i>"
        )
    else:
        lines.append(f"    💰 <b>{int(discount_price) // 100:,}</b> {currency}")
    return "\n".join(lines)


def format_store_offers_header(
    lang: str,
    store_name: str,
    category: str,
    page: int,
    total_pages: int,
    total: int,
) -> str:
    """Format header for store offers list."""
    category_title = (
        category.replace("_", " ").title()
        if category != "all"
        else ("Все категории" if lang == "ru" else "Barcha toifalar")
    )

    text = f"🏪 <b>{store_name}</b> | 📂 {category_title}\n"
    text += f"{'Стр.' if lang == 'ru' else 'Sah.'} {page + 1}/{total_pages} ({total} {'махсулот' if lang == 'uz' else 'товаров'})\n"
    text += "─" * 28 + "\n\n"
    return text


def format_offer_card_text(
    lang: str,
    title: str,
    description: str | None,
    original_price: float,
    discount_price: float,
    quantity: int,
    expiry_date: str | None,
    store_name: str,
    store_address: str | None,
    delivery_enabled: bool,
    delivery_price: int,
) -> str:
    """Format offer card text for detail view."""
    currency = "so'm" if lang == "uz" else "сум"

    lines = [f"🏷 <b>{title}</b>"]
    if description:
        lines.append(f"<i>{description[:100]}</i>")
    lines.append("")

    # Price
    if original_price and original_price > discount_price:
        discount_pct = round((1 - discount_price / original_price) * 100)
        lines.append(
            f"<s>{int(original_price) // 100:,}</s> → <b>{int(discount_price) // 100:,} {currency}</b> (-{discount_pct}%)"
        )
    else:
        lines.append(f"💰 <b>{int(discount_price) // 100:,} {currency}</b>")

    stock_label = "В наличии" if lang == "ru" else "Mavjud"
    lines.append(f"📦 {stock_label}: {quantity} шт")

    if expiry_date:
        lines.append(f"📅 Годен до: {expiry_date}")

    lines.append("")
    lines.append(f"🏪 {store_name}")
    if store_address:
        lines.append(f"📍 {store_address}")
    if delivery_enabled:
        lines.append(f"🚚 Доставка: {int(delivery_price) // 100:,} {currency}")

    return "\n".join(lines)


# Category mapping for filtering
CATEGORY_MAP = {
    "bakery": "bakery",
    "dairy": "dairy",
    "meat": "meat",
    "fruits": "fruits",
    "vegetables": "vegetables",
    "drinks": "drinks",
    "snacks": "snacks",
    "frozen": "frozen",
}


def normalize_db_category(category: str) -> str:
    """Map display category to database category value."""
    return CATEGORY_MAP.get(category, category)
