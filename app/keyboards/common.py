"""Common keyboards used across the bot."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from localization import get_text


def language_keyboard() -> InlineKeyboardMarkup:
    """Language selection keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🇷🇺 Русский", callback_data="lang_ru")
    builder.button(text="🇺🇿 O'zbekcha", callback_data="lang_uz")
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
        builder.button(text=f"📍 {city}")

    if allow_cancel:
        builder.button(text=get_text(lang, "cancel"))
        builder.adjust(2, 2, 2, 2, 1)
    else:
        builder.adjust(2, 2, 2, 2)

    return builder.as_markup(resize_keyboard=True)


def city_inline_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """City selection inline keyboard for partner registration."""
    from localization import get_cities

    cities = get_cities(lang)
    builder = InlineKeyboardBuilder()
    for city in cities:
        builder.button(text=f"📍 {city}", callback_data=f"reg_city_{city}")
    builder.button(text=get_text(lang, "cancel"), callback_data="reg_cancel")
    builder.adjust(1)
    return builder.as_markup()


def category_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Category selection keyboard."""
    from localization import get_categories

    categories = get_categories(lang)
    builder = ReplyKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"▫️ {cat}")
    builder.button(text=f"❌ {get_text(lang, 'cancel')}")
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
        builder.button(text=f"▫️ {cat}", callback_data=f"reg_cat_{cat_id}")
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
        "bakery": "🥖 Выпечка" if lang == "ru" else "🥖 Pishiriq",
        "dairy": "🥛 Молочные" if lang == "ru" else "🥛 Sut mahsulotlari",
        "meat": "🥩 Мясные" if lang == "ru" else "🥩 Go'sht mahsulotlari",
        "fruits": "🍎 Фрукты" if lang == "ru" else "🍎 Mevalar",
        "vegetables": "🥬 Овощи" if lang == "ru" else "🥬 Sabzavotlar",
        "drinks": "🥤 Напитки" if lang == "ru" else "🥤 Ichimliklar",
        "snacks": "🍿 Снеки" if lang == "ru" else "🍿 Gaz. ovqatlar",
        "frozen": "🧊 Замороженное" if lang == "ru" else "🧊 Muzlatilgan",
    }

    for cat_id, cat_name in categories.items():
        builder.button(text=cat_name, callback_data=f"product_cat_{cat_id}")

    builder.button(text=get_text(lang, "cancel"), callback_data="create_cancel")
    builder.adjust(2)  # 2 buttons per row
    return builder.as_markup()
