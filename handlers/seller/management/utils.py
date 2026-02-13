"""Shared utilities for seller management handlers."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.units import effective_order_unit, unit_label
from app.core.units import format_quantity as core_format_quantity
from app.core.utils import calc_discount_percent, to_uzb_datetime
from localization import get_text

if TYPE_CHECKING:
    from database_protocol import DatabaseProtocol

logger = logging.getLogger(__name__)

# Telegram message limit
TELEGRAM_MESSAGE_LIMIT = 4096

# Category labels for display
CATEGORY_LABELS = {
    "bakery": {"ru": "Выпечка", "uz": "Pishiriq"},
    "dairy": {"ru": "Молочные", "uz": "Sut mahsulotlari"},
    "meat": {"ru": "Мясные", "uz": "Go'sht mahsulotlari"},
    "fruits": {"ru": "Фрукты", "uz": "Mevalar"},
    "vegetables": {"ru": "Овощи", "uz": "Sabzavotlar"},
    "drinks": {"ru": "Напитки", "uz": "Ichimliklar"},
    "snacks": {"ru": "Снеки", "uz": "Gaz. ovqatlar"},
    "frozen": {"ru": "Замороженное", "uz": "Muzlatilgan"},
    "sweets": {"ru": "Сладости", "uz": "Shirinliklar"},
    "other": {"ru": "Другое", "uz": "Boshqa"},
}

UNIT_DISPLAY_UZ = {
    "шт": "dona",
    "уп": "dona",
    "кг": "kg",
    "г": "g",
    "л": "l",
    "мл": "ml",
}

UNIT_NORMALIZATION = {
    "piece": "шт",
    "pcs": "шт",
    "pc": "шт",
    "unit": "шт",
    "units": "шт",
    "шт.": "шт",
    "уп": "шт",
    "уп.": "шт",
    "up": "шт",
    "kg": "кг",
    "g": "г",
    "gr": "г",
    "l": "л",
    "ml": "мл",
}

# Module-level dependencies (set by setup_dependencies)
db: DatabaseProtocol | None = None
bot: Any | None = None


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


def get_db() -> DatabaseProtocol:
    """Get database instance, raise if not set."""
    if db is None:
        raise RuntimeError("Database not initialized")
    return db


def get_bot() -> Any:
    """Get bot instance."""
    return bot


def truncate_text(text: str, max_length: int = TELEGRAM_MESSAGE_LIMIT, suffix: str = "...") -> str:
    """
    Truncate text to fit Telegram's message limit.
    Tries to preserve HTML tags if present.
    """
    if len(text) <= max_length:
        return text

    # Leave room for suffix
    truncate_at = max_length - len(suffix)

    # Try to find a good break point (newline or space)
    break_point = text.rfind("\n", 0, truncate_at)
    if break_point < truncate_at * 0.5:  # If newline is too early, try space
        break_point = text.rfind(" ", 0, truncate_at)
    if break_point < truncate_at * 0.5:  # If space is too early, just cut
        break_point = truncate_at

    return text[:break_point] + suffix


async def safe_send_message(
    message: types.Message, text: str, parse_mode: str = "HTML", reply_markup: Any = None, **kwargs
) -> types.Message | None:
    """
    Safely send a message, truncating if too long.
    Returns the sent message or None if failed.
    """
    try:
        safe_text = truncate_text(text)
        return await message.answer(
            safe_text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs
        )
    except Exception as e:
        if "MESSAGE_TOO_LONG" in str(e):
            # Emergency truncation
            safe_text = truncate_text(text, 3500)  # More aggressive
            try:
                return await message.answer(
                    safe_text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs
                )
            except Exception as e2:
                logger.error(f"Failed to send even truncated message: {e2}")
        else:
            logger.error(f"Failed to send message: {e}")
        return None


async def safe_edit_message(
    message: types.Message, text: str, parse_mode: str = "HTML", reply_markup: Any = None, **kwargs
) -> types.Message | None:
    """
    Safely edit a message, truncating if too long.
    Returns the edited message or None if failed.
    """
    try:
        safe_text = truncate_text(text)
        return await message.edit_text(
            safe_text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs
        )
    except Exception as e:
        if "MESSAGE_TOO_LONG" in str(e):
            # Emergency truncation
            safe_text = truncate_text(text, 3500)
            try:
                return await message.edit_text(
                    safe_text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs
                )
            except Exception as e2:
                logger.error(f"Failed to edit even truncated message: {e2}")
        else:
            logger.error(f"Failed to edit message: {e}")
        return None


def get_offer_field(offer: Any, field: str, default: Any = None) -> Any:
    """Extract field from offer tuple/dict."""
    if isinstance(offer, dict):
        if field in offer:
            return offer.get(field, default)
        if field == "photo":
            return offer.get("photo_id", default)
        if field == "photo_id":
            return offer.get("photo", default)
        return default
    if isinstance(offer, (tuple, list)):
        field_map = {
            "offer_id": 0,
            "store_id": 1,
            "title": 2,
            "description": 3,
            "original_price": 4,
            "discount_price": 5,
            "quantity": 6,
            "available_from": 7,
            "available_until": 8,
            "expiry_date": 9,
            "status": 10,
            "photo": 11,
            "created_at": 12,
            "unit": 13,
            "category": 14,
            "store_name": 15,
            "address": 16,
            "city": 17,
        }
        idx = field_map.get(field)
        if idx is not None and len(offer) > idx:
            return offer[idx]
    return default


def get_store_field(store: Any, field: str, default: Any = None) -> Any:
    """Extract field from store tuple/dict."""
    if isinstance(store, dict):
        return store.get(field, default)
    field_map = {
        "store_id": 0,
        "owner_id": 1,
        "name": 2,
        "city": 3,
        "address": 4,
        "description": 5,
        "status": 6,
        "category": 7,
        "phone": 8,
        "rating": 9,
    }
    idx = field_map.get(field)
    if idx is not None and isinstance(store, (tuple, list)) and idx < len(store):
        return store[idx]
    return default


def get_booking_field(booking: Any, field: str, default: Any = None) -> Any:
    """Extract field from booking tuple/dict."""
    if isinstance(booking, dict):
        return booking.get(field, default)
    field_map = {
        "booking_id": 0,
        "store_id": 1,
        "offer_id": 2,
        "user_id": 3,
        "status": 4,
        "quantity": 5,
        "first_name": 6,
        "phone": 7,
        "booking_code": 8,
        "created_at": 9,
    }
    idx = field_map.get(field)
    if idx is not None and isinstance(booking, (tuple, list)) and idx < len(booking):
        return booking[idx]
    return default


def get_category_label(category: str | None, lang: str) -> str:
    """Return localized category label."""
    if not category:
        category = "other"
    labels = CATEGORY_LABELS.get(category, CATEGORY_LABELS["other"])
    return labels["ru"] if lang == "ru" else labels["uz"]


def get_category_labels(category: str | None) -> tuple[str, str]:
    """Return both RU and UZ labels for category."""
    if not category:
        category = "other"
    labels = CATEGORY_LABELS.get(category, CATEGORY_LABELS["other"])
    return labels["ru"], labels["uz"]


def normalize_unit_value(unit: str | None) -> str:
    """Normalize unit to supported display values."""
    if not unit:
        return "шт"
    raw = str(unit).strip().lower()
    normalized = UNIT_NORMALIZATION.get(raw)
    if normalized:
        return normalized
    if raw in {"шт", "кг", "г", "л", "мл"}:
        return raw
    return "шт"


def display_unit(unit: str | None, lang: str) -> str:
    """Return unit display label."""
    unit_value = effective_order_unit(unit)
    return unit_label(unit_value, lang)


def format_quantity(value: Any, unit: str | None, lang: str) -> str:
    """Format quantity with unit for display."""
    unit_value = effective_order_unit(unit)
    qty_str = core_format_quantity(value, unit_value, lang)
    return f"{qty_str} {unit_label(unit_value, lang)}"


def parse_expiry_date(value: Any) -> date | None:
    """Parse expiry date into date."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if "T" in raw:
            raw = raw.split("T", 1)[0]
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
    return None


def get_offer_quantity_value(offer: Any) -> float:
    """Safely extract offer quantity as float."""
    raw = get_offer_field(offer, "quantity", 0) or 0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def get_offer_expiry_days(offer: Any) -> int | None:
    """Return days until expiry (can be negative)."""
    expiry = parse_expiry_date(get_offer_field(offer, "expiry_date"))
    if not expiry:
        return None
    return (expiry - date.today()).days


def get_offer_discount_percent(offer: Any) -> int:
    """Calculate offer discount percent."""
    original_price = get_offer_field(offer, "original_price", 0) or 0
    discount_price = get_offer_field(offer, "discount_price", 0) or 0
    try:
        original_price = float(original_price)
        discount_price = float(discount_price)
    except (TypeError, ValueError):
        return 0
    if original_price <= 0 or discount_price < 0 or original_price <= discount_price:
        return 0
    return int(calc_discount_percent(original_price, discount_price))


def get_offer_effective_status(offer: Any) -> str:
    """Derive effective status based on quantity and expiry."""
    status = str(get_offer_field(offer, "status", "active") or "").lower()
    qty = get_offer_quantity_value(offer)
    days_left = get_offer_expiry_days(offer)
    expired = days_left is not None and days_left < 0
    if status == "active" and qty > 0 and not expired:
        return "active"
    return "inactive"


def offer_has_photo(offer: Any) -> bool:
    """Check if offer has photo."""
    return bool(get_offer_field(offer, "photo") or get_offer_field(offer, "photo_id"))


def normalize_expiry_value(expiry_date: Any) -> str | None:
    """Normalize expiry date to ISO string."""
    if not expiry_date:
        return None
    try:
        from datetime import date, datetime

        if isinstance(expiry_date, datetime):
            return expiry_date.strftime("%Y-%m-%d")
        if isinstance(expiry_date, date):
            return expiry_date.strftime("%Y-%m-%d")
    except Exception:
        pass
    return str(expiry_date)


def _format_money(value: Any) -> str:
    try:
        return f"{int(float(value)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def _pluralize_days_ru(days: int) -> str:
    if days % 10 == 1 and days % 100 != 11:
        return "день"
    if 2 <= days % 10 <= 4 and not (12 <= days % 100 <= 14):
        return "дня"
    return "дней"


def _format_days(days: int, lang: str) -> str:
    if lang == "ru":
        return f"{days} {_pluralize_days_ru(days)}"
    return f"{days} kun"


def _format_expiry_display(offer: Any, lang: str) -> str:
    days_left = get_offer_expiry_days(offer)
    if days_left is None:
        return get_text(lang, "seller_expiry_no")
    if days_left < 0:
        return get_text(lang, "seller_expiry_expired")
    return _format_days(days_left, lang)


def build_offer_card(offer: Any, lang: str) -> tuple[str, Any]:
    """Build offer card text and keyboard."""
    offer_id = get_offer_field(offer, "offer_id")
    title = get_offer_field(offer, "title", "Товар")
    original_price = get_offer_field(offer, "original_price", 0) or 0
    discount_price = get_offer_field(offer, "discount_price", 0) or 0
    unit = get_offer_field(offer, "unit", "шт") or "шт"
    category = get_offer_field(offer, "category", "other")
    quantity = get_offer_quantity_value(offer)
    available_from = get_offer_field(offer, "available_from")
    available_until = get_offer_field(offer, "available_until")

    status = get_offer_effective_status(offer)
    status_label = (
        get_text(lang, "seller_status_active")
        if status == "active"
        else get_text(lang, "seller_status_inactive")
    )

    discount_percent = get_offer_discount_percent(offer)
    order_unit = effective_order_unit(unit)
    unit_display = unit_label(order_unit, lang)
    currency = "сум" if lang == "ru" else "so'm"
    show_unit = order_unit != "piece"
    price_line = (
        f"{_format_money(original_price)} → {_format_money(discount_price)} (–{discount_percent}%)"
    )
    if show_unit:
        price_line += f" {currency} / {unit_display}"
    else:
        price_line += f" {currency}"

    text_parts = [
        f"<b>{title}</b>",
        f"{get_text(lang, 'label_status')}: {status_label}",
        "",
        f"{get_text(lang, 'label_price')}:",
        price_line,
        f"{get_text(lang, 'seller_label_category')}: {get_category_label(category, lang)}",
        f"{get_text(lang, 'seller_label_stock')}: {format_quantity(quantity, unit, lang)}",
        f"{get_text(lang, 'seller_label_expiry')}: {_format_expiry_display(offer, lang)}",
    ]

    if available_from and available_until:
        text_parts.append(
            f"{get_text(lang, 'seller_label_time')}: {available_from}–{available_until}"
        )

    text = "\n".join(text_parts)

    builder = InlineKeyboardBuilder()
    if status == "active":
        builder.button(text=get_text(lang, "seller_btn_add_stock"), callback_data=f"qty_add_{offer_id}")
        builder.button(text=get_text(lang, "seller_btn_sub_stock"), callback_data=f"qty_sub_{offer_id}")
        builder.button(text=get_text(lang, "seller_btn_edit"), callback_data=f"edit_offer_{offer_id}")
        builder.button(
            text=get_text(lang, "seller_btn_deactivate"), callback_data=f"deactivate_offer_{offer_id}"
        )
        builder.button(text=get_text(lang, "seller_items_back_btn"), callback_data="back_to_offers_menu")
        builder.adjust(2, 2, 1)
    else:
        builder.button(
            text=get_text(lang, "seller_btn_activate"), callback_data=f"activate_offer_{offer_id}"
        )
        builder.button(text=get_text(lang, "seller_btn_edit"), callback_data=f"edit_offer_{offer_id}")
        builder.button(text=get_text(lang, "seller_btn_delete"), callback_data=f"delete_offer_{offer_id}")
        builder.button(text=get_text(lang, "seller_items_back_btn"), callback_data="back_to_offers_menu")
        builder.adjust(2, 1, 1)

    return text, builder.as_markup()


async def send_offer_card(message: types.Message, offer: Any, lang: str) -> None:
    """Send single offer card with management buttons."""
    text, markup = build_offer_card(offer, lang)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


async def send_order_card(
    message: types.Message, order: Any, lang: str, is_booking: bool = True
) -> None:
    """Send order/booking card with action buttons."""
    database = get_db()

    if is_booking:
        # Booking fields
        booking_id = get_booking_field(order, "booking_id") or (
            order[0] if isinstance(order, (list, tuple)) and len(order) > 0 else None
        )
        offer_title = (
            order.get("title")
            if isinstance(order, dict)
            else (order[4] if len(order) > 4 else "Товар")
        )
        user_name = (
            order.get("first_name", "Клиент")
            if isinstance(order, dict)
            else (order[5] if len(order) > 5 else "Клиент")
        )
        phone = (
            order.get("phone", "Не указан")
            if isinstance(order, dict)
            else (order[7] if len(order) > 7 else "Не указан")
        )
        quantity = (
            order.get("quantity", 1)
            if isinstance(order, dict)
            else (order[6] if len(order) > 6 else 1)
        )
        status = (
            order.get("status", "pending")
            if isinstance(order, dict)
            else (order[3] if len(order) > 3 else "pending")
        )
        booking_code = (
            order.get("booking_code", "")
            if isinstance(order, dict)
            else (order[8] if len(order) > 8 else "")
        )
        created_at = (
            order.get("created_at")
            if isinstance(order, dict)
            else (order[9] if len(order) > 9 else None)
        )

        # Try to enrich with store and price info
        store_id = (
            order.get("store_id")
            if isinstance(order, dict)
            else (order[1] if len(order) > 1 else None)
        )
        store = database.get_store(store_id) if store_id else None
        store_name = get_store_field(store, "name", "Магазин")
        store_address = get_store_field(store, "address", "")

        # Check if cart booking
        is_cart_booking = order.get("is_cart_booking", 0) if isinstance(order, dict) else 0
        cart_items_json = order.get("cart_items") if isinstance(order, dict) else None

        # Try to get offer/unit price or cart items
        if is_cart_booking and cart_items_json:
            import json

            try:
                cart_items = (
                    json.loads(cart_items_json)
                    if isinstance(cart_items_json, str)
                    else cart_items_json
                )
                items_text = "\n".join(
                    [
                        f"- {item.get('title', 'Товар')} x {item.get('quantity', 1)}"
                        for item in cart_items
                    ]
                )
                total_price = sum(
                    item.get("price", 0) * item.get("quantity", 1) for item in cart_items
                )
            except Exception:
                items_text = offer_title
                total_price = None
        else:
            # Single item booking
            offer_id = (
                order.get("offer_id")
                if isinstance(order, dict)
                else (order[2] if len(order) > 2 else None)
            )
            unit_price = None
            total_price = None
            try:
                if offer_id:
                    offer = database.get_offer(offer_id)
                    if offer:
                        unit_price = get_offer_field(offer, "discount_price")
                        if unit_price is not None:
                            total_price = int(unit_price) * int(quantity)
            except Exception:
                pass
            items_text = f"{offer_title}"
            if unit_price is not None:
                items_text += (
                    f"\n{'Цена за ед.' if lang == 'ru' else 'Bir dona narxi'}: <b>{int(unit_price):,}</b>"
                )
            items_text += f"\n{'Количество' if lang == 'ru' else 'Miqdor'}: <b>{quantity}</b>"

        status_label = {
            "pending": "Ожидает подтверждения" if lang == "ru" else "Tasdiqlash kutilmoqda",
            "confirmed": "Подтвержден" if lang == "ru" else "Tasdiqlandi",
            "completed": "Выдан" if lang == "ru" else "Berildi",
            "cancelled": "Отменен" if lang == "ru" else "Bekor qilingan",
        }.get(status, status)

        text = f"<b>{'Самовывоз' if lang == 'ru' else 'Olib ketish'}</b>\n\n"
        text += f"<b>{store_name}</b>\n"
        if store_address:
            text += f"{store_address}\n"
        text += f"<b>{'Товары' if lang == 'ru' else 'Mahsulotlar'}:</b>\n{items_text}\n"
        if total_price is not None:
            text += f"{'Итого' if lang == 'ru' else 'Jami'}: <b>{total_price:,}</b>\n"
        text += "\n"
        text += f"{'Клиент' if lang == 'ru' else 'Mijoz'}: {user_name}\n"
        text += f"{'Телефон' if lang == 'ru' else 'Telefon'}: <code>{phone}</code>\n"
        text += f"{'Код' if lang == 'ru' else 'Kod'}: <code>{booking_code}</code>\n"
        if created_at:
            created_dt = to_uzb_datetime(created_at)
            created_label = (
                created_dt.strftime("%Y-%m-%d %H:%M") if created_dt else str(created_at)
            )
            text += f"{'Дата' if lang == 'ru' else 'Sana'}: {created_label}\n"
        text += f"{'Статус' if lang == 'ru' else 'Holat'}: {status_label}\n"

        builder = InlineKeyboardBuilder()
        builder.button(text="Подробнее" if lang == "ru" else "Batafsil", callback_data=f"seller_view_o_{booking_id}")
        builder.button(text="Контакт" if lang == "ru" else "Aloqa", callback_data=f"contact_customer_o_{booking_id}")
        if status == "pending":
            # Use order_ prefix since pickup orders live in orders.
            builder.button(
                text="✅ Принять" if lang == "ru" else "✅ Qabul qilish",
                callback_data=f"order_confirm_{booking_id}",
            )
            builder.button(
                text="❌ Отклонить" if lang == "ru" else "❌ Rad etish",
                callback_data=f"order_reject_{booking_id}",
            )
            builder.adjust(2, 2)
        elif status == "confirmed":
            builder.button(
                text="✅ Выдано" if lang == "ru" else "✅ Berildi",
                callback_data=f"order_complete_{booking_id}",
            )
            builder.button(
                text="❌ Отменить" if lang == "ru" else "❌ Bekor qilish",
                callback_data=f"order_cancel_seller_{booking_id}",
            )
            builder.adjust(2, 2)
    else:
        # Order fields (delivery)
        order_id = order.get("order_id") if isinstance(order, dict) else order[0]
        user_id = (
            order.get("user_id")
            if isinstance(order, dict)
            else (order[1] if len(order) > 1 else None)
        )

        # Get user name from DB
        user_model = database.get_user_model(user_id) if user_id else None
        user_name = user_model.first_name if user_model and user_model.first_name else "Клиент"
        user_phone = user_model.phone if user_model and user_model.phone else "Не указан"

        quantity = (
            order.get("quantity", 1)
            if isinstance(order, dict)
            else (order[9] if len(order) > 9 else 1)
        )
        address = (
            order.get("delivery_address", "Не указан")
            if isinstance(order, dict)
            else (order[4] if len(order) > 4 else "Не указан")
        )
        status = (
            order.get("order_status", "pending")
            if isinstance(order, dict)
            else (order[10] if len(order) > 10 else "pending")
        )
        payment_status = (
            order.get("payment_status", "pending")
            if isinstance(order, dict)
            else (order[11] if len(order) > 11 else "pending")
        )

        # Check if cart order
        is_cart_order = order.get("is_cart_order", 0) if isinstance(order, dict) else 0
        cart_items_json = order.get("cart_items") if isinstance(order, dict) else None

        # Prefer snapshot fields when present
        item_title = order.get("item_title") if isinstance(order, dict) else None
        item_price = order.get("item_price") if isinstance(order, dict) else None

        # Get offer info or cart items
        if is_cart_order and cart_items_json:
            import json

            try:
                cart_items = (
                    json.loads(cart_items_json)
                    if isinstance(cart_items_json, str)
                    else cart_items_json
                )
                items_text = "\n".join(
                    [f"- {item['title']} x {item['quantity']}" for item in cart_items]
                )
                total_price = sum(
                    item.get("price", 0) * item.get("quantity", 1) for item in cart_items
                )
            except Exception:
                items_text = "Товары из корзины"
                total_price = 0
        else:
            # Single item order
            offer_id = (
                order.get("offer_id")
                if isinstance(order, dict)
                else (order[2] if len(order) > 2 else None)
            )
            offer = None
            if item_title is None or item_price is None:
                offer = database.get_offer(offer_id) if offer_id else None
            if item_title is None:
                item_title = get_offer_field(offer, "title", "Товар") if offer else "Товар"
            if item_price is None:
                item_price = int(get_offer_field(offer, "discount_price", 0)) if offer else 0
            items_text = f"- {item_title} x {quantity}"
            total_price = int(item_price or 0) * int(quantity)

        payment_text = "Оплачено" if payment_status == "confirmed" else "Ожидает подтверждения"
        if lang != "ru":
            payment_text = "To'langan" if payment_status == "confirmed" else "Tasdiqlash kutilmoqda"

        status_label = {
            "pending": "Новый" if lang == "ru" else "Yangi",
            "confirmed": "Подтвержден" if lang == "ru" else "Tasdiqlandi",
            "preparing": "Готовится" if lang == "ru" else "Tayyorlanmoqda",
            "delivering": "В пути" if lang == "ru" else "Yo'lda",
            "completed": "Завершен" if lang == "ru" else "Yakunlandi",
            "cancelled": "Отменен" if lang == "ru" else "Bekor qilingan",
        }.get(status, status)

        text = f"<b>{'Доставка' if lang == 'ru' else 'Yetkazib berish'}</b>\n\n"
        text += f"{'Заказ' if lang == 'ru' else 'Buyurtma'} #{order_id}\n"
        text += f"<b>{'Товары' if lang == 'ru' else 'Mahsulotlar'}:</b>\n{items_text}\n"
        if total_price > 0:
            text += f"{'Сумма' if lang == 'ru' else 'Summa'}: {total_price:,} {'сум' if lang == 'ru' else 'so`m'}\n"
        text += f"\n{'Клиент' if lang == 'ru' else 'Mijoz'}: {user_name}\n"
        text += f"{'Телефон' if lang == 'ru' else 'Telefon'}: <code>{user_phone}</code>\n"
        text += f"{'Адрес' if lang == 'ru' else 'Manzil'}: {address}\n"
        text += f"{'Статус' if lang == 'ru' else 'Holat'}: {status_label}\n"
        text += f"{'Оплата' if lang == 'ru' else 'To`lov'}: {payment_text}\n"

        builder = InlineKeyboardBuilder()

        # Buttons depend on status (unified order callbacks)
        if status == "pending":
            builder.button(
                text="✅ Принять" if lang == "ru" else "✅ Qabul qilish",
                callback_data=f"order_confirm_{order_id}",
            )
            builder.button(
                text="❌ Отклонить" if lang == "ru" else "❌ Rad etish",
                callback_data=f"order_reject_{order_id}",
            )
            builder.adjust(2)
        elif status == "preparing":
            builder.button(
                text="📦 Готов к передаче" if lang == "ru" else "📦 Topshirishga tayyor",
                callback_data=f"order_ready_{order_id}",
            )
            builder.adjust(1)
        elif status == "ready":
            builder.button(
                text="🚚 Передал курьеру" if lang == "ru" else "🚚 Kuryerga topshirdim",
                callback_data=f"order_delivering_{order_id}",
            )
            builder.adjust(1)
        elif status == "delivering":
            builder.button(
                text="✅ Доставлено" if lang == "ru" else "✅ Topshirildi",
                callback_data=f"order_complete_{order_id}",
            )
            builder.adjust(1)

    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


async def update_offer_message(callback: types.CallbackQuery, offer_id: int, lang: str) -> None:
    """Update offer message with new data."""
    database = get_db()

    offer = database.get_offer(offer_id)
    if not offer:
        return

    text, markup = build_offer_card(offer, lang)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        try:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)
            try:
                await callback.message.delete()
            except Exception:
                pass
        except Exception:
            pass
