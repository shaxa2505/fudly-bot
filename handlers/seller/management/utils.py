"""Shared utilities for seller management handlers."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

if TYPE_CHECKING:
    from database_protocol import DatabaseProtocol

logger = logging.getLogger(__name__)

# Telegram message limit
TELEGRAM_MESSAGE_LIMIT = 4096

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
        return offer.get(field, default)
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


async def send_offer_card(message: types.Message, offer: Any, lang: str) -> None:
    """Send single offer card with management buttons."""
    database = get_db()

    # Safe field extraction
    offer_id = get_offer_field(offer, "offer_id")
    title = get_offer_field(offer, "title", "Без названия")
    original_price = int(get_offer_field(offer, "original_price", 0))
    discount_price = int(get_offer_field(offer, "discount_price", 0))
    quantity = get_offer_field(offer, "quantity", 0)
    status = get_offer_field(offer, "status", "active")
    photo = get_offer_field(offer, "photo")
    unit = get_offer_field(offer, "unit", "шт") or "шт"
    available_from = get_offer_field(offer, "available_from")
    available_until = get_offer_field(offer, "available_until")
    expiry_date = get_offer_field(offer, "expiry_date")

    discount_percent = int((1 - discount_price / original_price) * 100) if original_price > 0 else 0

    # Build card
    status_emoji = "✅" if status == "active" else "❌"
    text = f"{status_emoji} <b>{title}</b>\n\n"

    # Price box
    text += "┌─────────────────┐\n"
    text += f"│ <s>{original_price:,}</s> ➜ <b>{discount_price:,}</b> сум │\n"
    text += f"│ 💥 Скидка <b>-{discount_percent}%</b>  │\n"
    text += "└─────────────────┘\n\n"

    # Stock
    stock_emoji = "🟢" if quantity > 10 else "🟡" if quantity > 0 else "🔴"
    text += f"{stock_emoji} Остаток: <b>{quantity}</b> {unit}\n"

    # Time
    if available_from and available_until:
        text += f"🕐 {available_from} - {available_until}\n"

    # Expiry
    if expiry_date:
        expiry_info = database.get_time_remaining(expiry_date)
        if expiry_info:
            text += f"⏰ {expiry_info}\n"

    # Management buttons
    builder = InlineKeyboardBuilder()

    if status == "active":
        builder.button(text="➕ +1", callback_data=f"qty_add_{offer_id}")
        builder.button(text="➖ -1", callback_data=f"qty_sub_{offer_id}")
        builder.button(
            text="📝 Изменить" if lang == "ru" else "📝 Tahrirlash",
            callback_data=f"edit_offer_{offer_id}",
        )
        builder.button(
            text="🔄 Продлить" if lang == "ru" else "🔄 Uzaytirish",
            callback_data=f"extend_offer_{offer_id}",
        )
        builder.button(
            text="❌ Снять" if lang == "ru" else "❌ O'chirish",
            callback_data=f"deactivate_offer_{offer_id}",
        )
        builder.button(
            text="🔙 Назад" if lang == "ru" else "🔙 Orqaga",
            callback_data="back_to_offers_menu",
        )
        builder.adjust(2, 2, 1, 1)
    else:
        builder.button(
            text="✅ Активировать" if lang == "ru" else "✅ Faollashtirish",
            callback_data=f"activate_offer_{offer_id}",
        )
        builder.button(
            text="🗑 Удалить" if lang == "ru" else "🗑 O'chirish",
            callback_data=f"delete_offer_{offer_id}",
        )
        builder.button(
            text="🔙 Назад" if lang == "ru" else "🔙 Orqaga",
            callback_data="back_to_offers_menu",
        )
        builder.adjust(2, 1)

    if photo:
        try:
            await message.answer_photo(
                photo=photo,
                caption=text,
                parse_mode="HTML",
                reply_markup=builder.as_markup(),
            )
        except Exception:
            await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


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
                        f"• {item.get('title', 'Товар')} × {item.get('quantity', 1)}"
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
                items_text += f"\n💰 Цена за ед.: <b>{int(unit_price):,}</b>"
            items_text += f"\n🔢 {'Количество' if lang == 'ru' else 'Miqdor'}: <b>{quantity}</b>"

        status_emoji = {
            "pending": "⏳",
            "confirmed": "✅",
            "completed": "🎉",
            "cancelled": "❌",
        }.get(status, "📦")

        text = f"{status_emoji} <b>{'САМОВЫВОЗ' if lang == 'ru' else 'OLIB KETISH'}</b>\n\n"
        text += f"🏬 <b>{store_name}</b>\n"
        if store_address:
            text += f"📍 {store_address}\n"
        text += f"🛒 <b>{'Товары:' if lang == 'ru' else 'Mahsulotlar:'}</b>\n{items_text}\n"
        if total_price is not None:
            text += f"🧾 Итого: <b>{total_price:,}</b>\n"
        text += "\n"
        text += f"👤 {user_name}\n"
        text += f"📱 <code>{phone}</code>\n"
        text += f"🎫 {'Код' if lang == 'ru' else 'Kod'}: <code>{booking_code}</code>\n"
        if created_at:
            text += f"🕐 {created_at}\n"

        builder = InlineKeyboardBuilder()
        builder.button(text="👁️ Подробнее", callback_data=f"seller_view_o_{booking_id}")
        builder.button(text="📞 Контакт", callback_data=f"contact_customer_o_{booking_id}")
        if status == "pending":
            # Use order_ prefix since pickup orders live in orders.
            builder.button(
                text="✅ Подтвердить" if lang == "ru" else "✅ Tasdiqlash",
                callback_data=f"order_confirm_{booking_id}",
            )
            builder.button(
                text="❌ Отменить" if lang == "ru" else "❌ Bekor qilish",
                callback_data=f"order_reject_{booking_id}",
            )
            builder.adjust(2, 2)
        elif status == "confirmed":
            builder.button(
                text="🎉 Выдано" if lang == "ru" else "🎉 Berildi",
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
                    [f"• {item['title']} × {item['quantity']}" for item in cart_items]
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
            offer = database.get_offer(offer_id) if offer_id else None
            offer_title = get_offer_field(offer, "title", "Товар") if offer else "Товар"
            offer_price = int(get_offer_field(offer, "discount_price", 0)) if offer else 0
            items_text = f"• {offer_title} × {quantity}"
            total_price = offer_price * int(quantity)

        status_emoji = {
            "pending": "⏳",
            "confirmed": "✅",
            "preparing": "👨‍🍳",
            "delivering": "🚚",
            "completed": "🎉",
            "cancelled": "❌",
        }.get(status, "📦")

        payment_emoji = "✅" if payment_status == "confirmed" else "⏳"
        payment_text = "Оплачено" if payment_status == "confirmed" else "Ожидает подтверждения"
        if lang != "ru":
            payment_text = "To'langan" if payment_status == "confirmed" else "Tasdiqlash kutilmoqda"

        text = f"{status_emoji} <b>{'ДОСТАВКА' if lang == 'ru' else 'YETKAZIB BERISH'}</b>\n\n"
        text += f"📦 {'Заказ' if lang == 'ru' else 'Buyurtma'} #{order_id}\n"
        text += f"🛒 <b>{'Товары:' if lang == 'ru' else 'Mahsulotlar:'}</b>\n{items_text}\n"
        if total_price > 0:
            text += f"💰 {'Сумма' if lang == 'ru' else 'Summa'}: {total_price:,} {'сум' if lang == 'ru' else 'so`m'}\n"
        text += f"\n👤 {user_name}\n"
        text += f"📱 <code>{user_phone}</code>\n"
        text += f"📍 {address}\n\n"
        text += f"💳 {payment_emoji} {payment_text}\n"

        builder = InlineKeyboardBuilder()

        # Buttons depend on status
        if status == "pending" and payment_status == "pending":
            # Waiting for payment confirmation
            builder.button(
                text="✅ Подтвердить оплату" if lang == "ru" else "✅ To'lovni tasdiqlash",
                callback_data=f"confirm_payment_{order_id}",
            )
            builder.button(
                text="❌ Отклонить" if lang == "ru" else "❌ Rad etish",
                callback_data=f"reject_payment_{order_id}",
            )
            builder.adjust(2)
        elif status == "preparing":
            # Payment confirmed, preparing order
            builder.button(
                text="🚕 Передать курьеру" if lang == "ru" else "🚕 Kuryerga topshirish",
                callback_data=f"handover_courier_{order_id}",
            )
            builder.adjust(1)
        elif status == "delivering":
            # Order is being delivered - no actions needed
            builder.button(
                text="📍 В пути" if lang == "ru" else "📍 Yo'lda",
                callback_data="noop",
            )
            builder.adjust(1)

    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


async def update_offer_message(callback: types.CallbackQuery, offer_id: int, lang: str) -> None:
    """Update offer message with new data."""
    database = get_db()

    offer = database.get_offer(offer_id)
    if not offer:
        return

    # Safe field extraction
    title = get_offer_field(offer, "title", "Товар")
    original_price = int(get_offer_field(offer, "original_price", 0))
    discount_price = int(get_offer_field(offer, "discount_price", 0))
    quantity = get_offer_field(offer, "quantity", 0)
    status = get_offer_field(offer, "status", "active")
    unit = get_offer_field(offer, "unit", "шт") or "шт"
    available_from = get_offer_field(offer, "available_from", "")
    available_until = get_offer_field(offer, "available_until", "")
    expiry_date = get_offer_field(offer, "expiry_date")

    discount_percent = int((1 - discount_price / original_price) * 100) if original_price > 0 else 0

    status_emoji = "✅" if status == "active" else "❌"
    text = f"{status_emoji} <b>{title}</b>\n\n"

    # Price box
    text += "┌─────────────────┐\n"
    text += f"│ <s>{original_price:,}</s> ➜ <b>{discount_price:,}</b> сум │\n"
    text += f"│ 💥 Скидка <b>-{discount_percent}%</b>  │\n"
    text += "└─────────────────┘\n\n"

    # Stock
    stock_emoji = "🟢" if quantity > 10 else "🟡" if quantity > 0 else "🔴"
    text += f"{stock_emoji} Остаток: <b>{quantity}</b> {unit}\n"

    # Time
    if available_from and available_until:
        text += f"🕐 {available_from} - {available_until}\n"

    # Expiry
    if expiry_date:
        expiry_info = database.get_time_remaining(expiry_date)
        if expiry_info:
            text += f"⏰ {expiry_info}\n"

    builder = InlineKeyboardBuilder()

    if status == "active":
        builder.button(text="➕ +1", callback_data=f"qty_add_{offer_id}")
        builder.button(text="➖ -1", callback_data=f"qty_sub_{offer_id}")
        builder.button(
            text="📝 Изменить" if lang == "ru" else "📝 Tahrirlash",
            callback_data=f"edit_offer_{offer_id}",
        )
        builder.button(
            text="🔄 Продлить" if lang == "ru" else "🔄 Uzaytirish",
            callback_data=f"extend_offer_{offer_id}",
        )
        builder.button(
            text="❌ Снять" if lang == "ru" else "❌ O'chirish",
            callback_data=f"deactivate_offer_{offer_id}",
        )
        builder.button(
            text="🔙 Назад" if lang == "ru" else "🔙 Orqaga",
            callback_data="back_to_offers_menu",
        )
        builder.adjust(2, 2, 1, 1)
    else:
        builder.button(
            text="✅ Активировать" if lang == "ru" else "✅ Faollashtirish",
            callback_data=f"activate_offer_{offer_id}",
        )
        builder.button(
            text="🗑 Удалить" if lang == "ru" else "🗑 O'chirish",
            callback_data=f"delete_offer_{offer_id}",
        )
        builder.button(
            text="🔙 Назад" if lang == "ru" else "🔙 Orqaga",
            callback_data="back_to_offers_menu",
        )
        builder.adjust(2, 1)

    # Get offer photo
    photo = get_offer_field(database.get_offer(offer_id), "photo")

    try:
        if photo:
            # Offer has photo - send as photo message
            await callback.message.answer_photo(
                photo=photo,
                caption=text,
                parse_mode="HTML",
                reply_markup=builder.as_markup(),
            )
        else:
            # No photo - send as text
            await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
        # Try to delete the list message
        try:
            await callback.message.delete()
        except Exception:
            pass
    except Exception:
        # Fallback: try to edit current message
        try:
            await callback.message.edit_text(
                text, parse_mode="HTML", reply_markup=builder.as_markup()
            )
        except Exception:
            pass
