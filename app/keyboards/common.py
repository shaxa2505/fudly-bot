"""Common keyboards used across the bot."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from localization import get_text
from app.core.units import format_quantity, normalize_unit, unit_label


def language_keyboard() -> InlineKeyboardMarkup:
    """Language selection keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Русский", callback_data="lang_ru")
    builder.button(text="O'zbekcha", callback_data="lang_uz")
    builder.adjust(2)
    return builder.as_markup()


def cancel_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Cancel keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=get_text(lang, "cancel"))
    return builder.as_markup(resize_keyboard=True)


def phone_request_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Phone number request keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=get_text(lang, "share_phone"), request_contact=True)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def city_keyboard(lang: str = "ru", allow_cancel: bool = True) -> ReplyKeyboardMarkup:
    """City selection keyboard.

    Args:
        lang: Interface language
        allow_cancel: Show cancel button (False for mandatory registration)
    """
    from localization import get_cities

    cities = get_cities(lang)
    builder = ReplyKeyboardBuilder()
    for city in cities:
        builder.button(text=city)

    if allow_cancel:
        builder.button(text=get_text(lang, "cancel"))
        builder.adjust(2, 2, 2, 2, 1)
    else:
        builder.adjust(2, 2, 2, 2)

    return builder.as_markup(resize_keyboard=True)


def city_inline_keyboard(lang: str = "ru", allow_cancel: bool = True) -> InlineKeyboardMarkup:
    """City selection inline keyboard.

    Args:
        lang: Interface language
        allow_cancel: Show cancel button
    """
    from localization import get_cities

    cities = get_cities(lang)
    builder = InlineKeyboardBuilder()
    for idx, city in enumerate(cities):
        builder.button(text=city, callback_data=f"reg_city_{idx}")
    if allow_cancel:
        builder.button(text=get_text(lang, "cancel"), callback_data="reg_cancel")
    builder.adjust(1)
    return builder.as_markup()


def category_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Category selection keyboard."""
    from localization import get_categories

    categories = get_categories(lang)
    builder = ReplyKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat)
    builder.button(text=get_text(lang, "cancel"))
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def category_inline_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Category selection inline keyboard for partner registration."""
    from localization import get_categories

    categories = get_categories(lang)
    # Category IDs for callback_data
    category_ids = {
        "Супермаркет": "supermarket",
        "Ресторан": "restaurant",
        "Пекарня": "bakery",
        "Кафе": "cafe",
        "Кондитерская": "confectionery",
        "Фастфуд": "fastfood",
        "Supermarket": "supermarket",
        "Restaurant": "restaurant",
        "Nonvoyxona": "bakery",
        "Kafe": "cafe",
        "Qandolatchilik": "confectionery",
        "Fastfud": "fastfood",
    }

    builder = InlineKeyboardBuilder()
    for cat in categories:
        cat_id = category_ids.get(cat, cat.lower())
        builder.button(text=cat, callback_data=f"reg_cat_{cat_id}")
    builder.button(text=get_text(lang, "cancel"), callback_data="reg_cancel")
    builder.adjust(2)
    return builder.as_markup()


def units_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Units of measurement keyboard."""
    builder = ReplyKeyboardBuilder()
    units = ["шт", "кг", "г", "л", "мл", "упак", "м", "см"]
    for unit in units:
        builder.button(text=unit)
    builder.adjust(4, 4)
    return builder.as_markup(resize_keyboard=True)


def product_categories_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Product categories keyboard with inline buttons for offer creation."""
    builder = InlineKeyboardBuilder()

    # Use same 8 categories as in the customer view
    categories = {
        "bakery": "🥐 Выпечка" if lang == "ru" else "🥐 Pishiriq",
        "dairy": "🥛 Молочные" if lang == "ru" else "🥛 Sut mahsulotlari",
        "meat": "🥩 Мясные" if lang == "ru" else "🥩 Go'sht",
        "fruits": "🍎 Фрукты" if lang == "ru" else "🍎 Mevalar",
        "vegetables": "🥦 Овощи" if lang == "ru" else "🥦 Sabzavotlar",
        "drinks": "🥤 Напитки" if lang == "ru" else "🥤 Ichimliklar",
        "snacks": "🍿 Снеки" if lang == "ru" else "🍿 Gaz. ovqatlar",
        "frozen": "❄️ Замороженное" if lang == "ru" else "❄️ Muzlatilgan",
        "sweets": "🍰 Сладости" if lang == "ru" else "🍰 Shirinliklar",
        "other": "📦 Другое" if lang == "ru" else "📦 Boshqa",
    }

    for cat_id, cat_name in categories.items():
        builder.button(text=cat_name, callback_data=f"product_cat_{cat_id}")

    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_store")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)  # 2 buttons per row
    return builder.as_markup()


def discount_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Quick discount selection keyboard."""
    builder = InlineKeyboardBuilder()
    discounts = [20, 30, 40, 50, 60, 70]
    for d in discounts:
        label = f"{d}%"
        builder.button(text=label, callback_data=f"discount_{d}")
    builder.button(text="✍️ Другая" if lang == "ru" else "✍️ Boshqa", callback_data="discount_custom")
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_price")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(3, 3, 3)
    return builder.as_markup()


def quantity_keyboard(lang: str = "ru", unit: str = "шт") -> InlineKeyboardMarkup:
    """Quick quantity selection keyboard (unit-aware)."""
    builder = InlineKeyboardBuilder()

    unit_type = normalize_unit(unit)
    unit_text = unit_label(unit_type, lang)

    if unit_type == "piece":
        quantities = [5, 10, 20, 50, 100]
    elif unit_type in {"kg", "l"}:
        quantities = [0.5, 1, 2, 5]
    elif unit_type == "g":
        quantities = [200, 500, 1000]
    else:
        quantities = [250, 500, 1000]

    for q in quantities:
        label = f"{format_quantity(q, unit_type, lang)} {unit_text}"
        builder.button(text=label, callback_data=f"quantity_{q}")

    builder.button(text="✍️ Другое" if lang == "ru" else "✍️ Boshqa", callback_data="quantity_custom")
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_unit")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def unit_type_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Unit type selection keyboard."""
    builder = InlineKeyboardBuilder()

    piece_label = f"📦 {get_text(lang, 'unit_piece_title')} ({get_text(lang, 'unit_piece')})"
    kg_label = f"⚖️ {get_text(lang, 'unit_kg_title')} ({get_text(lang, 'unit_kg')})"
    g_label = f"⚖️ {get_text(lang, 'unit_g_title')} ({get_text(lang, 'unit_g')})"
    l_label = f"🧃 {get_text(lang, 'unit_l_title')} ({get_text(lang, 'unit_l')})"
    ml_label = f"🧃 {get_text(lang, 'unit_ml_title')} ({get_text(lang, 'unit_ml')})"

    builder.button(text=piece_label, callback_data="unit_type_piece")
    builder.button(text=kg_label, callback_data="unit_type_kg")
    builder.button(text=g_label, callback_data="unit_type_g")
    builder.button(text=l_label, callback_data="unit_type_l")
    builder.button(text=ml_label, callback_data="unit_type_ml")
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_discount")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def expiry_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Quick expiry date selection keyboard."""
    from datetime import datetime, timedelta

    builder = InlineKeyboardBuilder()
    today = datetime.now()

    dates = [
        ("Сегодня" if lang == "ru" else "Bugun", 0),
        ("Завтра" if lang == "ru" else "Ertaga", 1),
        ("+3 дня" if lang == "ru" else "+3 kun", 3),
        ("+7 дней" if lang == "ru" else "+7 kun", 7),
        ("+14 дней" if lang == "ru" else "+14 kun", 14),
    ]

    for label, days in dates:
        date = (today + timedelta(days=days)).strftime("%d.%m")
        builder.button(text=f"{label} ({date})", callback_data=f"expiry_{days}")

    builder.button(text="📅 Другая дата" if lang == "ru" else "📅 Boshqa sana", callback_data="expiry_custom")
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_quantity")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def photo_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Photo upload keyboard (no skip)."""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_expiry")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)
    return builder.as_markup()
