"""
Идеальная реализация Buyurtmalarim (Мои заказы).

Функционал:
1. Показ активных заказов с прогрессом
2. Детальный просмотр заказа (товары, цены, адрес)
3. Действия: Получил, Позвонить курьеру, Проблема
4. История заказов с фильтрами
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import WebAppInfo

from app.core.utils import UZB_TZ, get_uzb_time, to_uzb_datetime
from app.core.sanitize import sanitize_phone
from app.core.order_math import calc_delivery_fee, calc_items_total, parse_cart_items
from app.core.units import calc_total_price
from app.domain.order import PaymentStatus
from app.integrations.payment_service import get_payment_service
from app.domain.order_labels import normalize_order_status, status_emoji, status_label
from app.services.unified_order_service import (
    NotificationTemplates,
    OrderStatus,
    get_unified_order_service,
    init_unified_order_service,
)
from handlers.common.utils import fix_mojibake_text, is_my_orders_button
from localization import get_text

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

router = Router(name="my_orders")

# Module dependencies
db: Any = None
bot: Any = None
cart_storage: Any = None


def setup_dependencies(database: Any, bot_instance: Any, cart_storage_instance: Any = None) -> None:
    """Setup module dependencies."""
    global db, bot, cart_storage
    db = database
    bot = bot_instance
    cart_storage = cart_storage_instance


def _t(lang: str, ru: str, uz: str) -> str:
    """Translate helper."""
    return ru if lang == "ru" else uz


def _normalize_status(status: str | None) -> str:
    """Normalize legacy statuses to the fulfillment-only order_status model."""
    return normalize_order_status(status)


def _get_status_info(status: str, is_delivery: bool, lang: str) -> tuple[str, str]:
    """Get status emoji and text."""
    status_norm = _normalize_status(status)
    order_type = "delivery" if is_delivery else "pickup"
    return status_emoji(status_norm), status_label(status_norm, lang, order_type)


def _format_price(amount: int | float, lang: str) -> str:
    """Format price with currency."""
    currency = get_text(lang, "currency")
    return f"{int(amount):,} {currency}".replace(",", " ")


def _fmt(lines: list[str]) -> str:
    """Join lines and fix mojibake (cp1251-decoded UTF-8) if present."""
    return fix_mojibake_text("\n".join(lines))


def _format_ready_until(updated_at: Any) -> str | None:
    try:
        hours = int(os.environ.get("PICKUP_READY_EXPIRY_HOURS", "2"))
    except Exception:
        hours = 2
    if hours <= 0:
        return None

    base_time = to_uzb_datetime(updated_at) or get_uzb_time()
    ready_until = base_time + timedelta(hours=hours)
    return ready_until.strftime("%H:%M")


def _ready_minutes_left(updated_at: Any) -> int | None:
    try:
        hours = int(os.environ.get("PICKUP_READY_EXPIRY_HOURS", "2"))
    except Exception:
        hours = 2
    if hours <= 0:
        return None

    base_time = to_uzb_datetime(updated_at) or get_uzb_time()

    ready_until = base_time + timedelta(hours=hours)
    now = get_uzb_time()
    minutes_left = int((ready_until - now).total_seconds() // 60)
    return minutes_left


def _format_phone_display(raw_phone: str | None) -> str:
    if not raw_phone:
        return ""
    sanitized = sanitize_phone(raw_phone)
    digits = "".join(filter(str.isdigit, sanitized))
    if digits.startswith("998") and len(digits) == 12:
        return f"+998 {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:12]}"
    if sanitized.startswith("+") and digits:
        return f"+{digits}"
    return sanitized or str(raw_phone)


def _format_phone_link(raw_phone: str | None) -> str:
    if not raw_phone:
        return ""
    phone = sanitize_phone(raw_phone)
    return (
        phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if phone
        else ""
    )


def _safe_caption(text: str, limit: int = 1000) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _get_existing_customer_message_id(entity_type: str, entity_id: int) -> int | None:
    if not db:
        return None
    try:
        if entity_type == "order" and hasattr(db, "get_order"):
            entity = db.get_order(entity_id)
        elif entity_type == "booking" and hasattr(db, "get_booking"):
            entity = db.get_booking(entity_id)
        else:
            return None
    except Exception:
        return None

    if not entity:
        return None
    if isinstance(entity, dict):
        return entity.get("customer_message_id")
    return getattr(entity, "customer_message_id", None)


async def _maybe_transfer_customer_card(
    *,
    user_id: int,
    entity_type: str,
    entity_id: int,
    current_message_id: int | None = None,
) -> bool:
    if not bot:
        return False

    existing_message_id = _get_existing_customer_message_id(entity_type, entity_id)
    if not existing_message_id:
        return False
    if current_message_id and int(existing_message_id) == int(current_message_id):
        return False

    # Avoid breaking grouped cart cards (shared customer_message_id).
    if entity_type == "order" and hasattr(db, "get_orders_by_customer_message_id"):
        try:
            grouped = db.get_orders_by_customer_message_id(int(existing_message_id))
            if grouped and len(grouped) > 1:
                return False
        except Exception:
            pass

    # Move the canonical card to the current message to avoid duplicates.
    try:
        if entity_type == "order" and hasattr(db, "set_order_customer_message_id"):
            db.set_order_customer_message_id(int(entity_id), int(current_message_id or 0))
        elif entity_type == "booking" and hasattr(db, "set_booking_customer_message_id"):
            db.set_booking_customer_message_id(int(entity_id), int(current_message_id or 0))
    except Exception:
        return False

    try:
        await bot.delete_message(chat_id=int(user_id), message_id=int(existing_message_id))
    except Exception:
        pass
    return True


def _build_open_app_keyboard(
    lang: str, order_id: int, store_phone: str | None = None
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    if store_phone:
        tel_link = _format_phone_link(store_phone)
        if tel_link:
            kb.button(text=get_text(lang, "contact_store_button"), url=f"tel:{tel_link}")
    webapp_url = os.getenv("WEBAPP_URL", "").strip()
    if webapp_url:
        kb.button(
            text=get_text(lang, "btn_open_order_app"),
            web_app=WebAppInfo(url=f"{webapp_url.rstrip('/')}/order/{order_id}"),
        )
    kb.button(text=get_text(lang, "btn_back_menu"), callback_data="back_to_menu")
    kb.adjust(1)
    return kb


# =============================================================================
# MY ORDERS MAIN HANDLER
# =============================================================================


@router.message(F.text.func(is_my_orders_button))
async def my_orders_handler(message: types.Message) -> None:
    """
    Главный экран "Мои заказы".
    Показывает активные заказы с кнопками детализации.
    """
    if not db:
        lang_code = (message.from_user.language_code or "ru") if message.from_user else "ru"
        if lang_code.startswith("uz"):
            text = "Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring."
        else:
            text = "Сервис временно недоступен. Попробуйте позже."
        await message.answer(text)
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    # Получаем bookings (самовывоз) и orders (доставка)
    try:
        bookings = db.get_user_bookings(user_id) or []
    except Exception as exc:
        logger.warning("Failed to load bookings for user %s: %s", user_id, exc)
        bookings = []
    try:
        orders = db.get_user_orders(user_id) or []
    except Exception as exc:
        logger.warning("Failed to load orders for user %s: %s", user_id, exc)
        orders = []

    if not bookings and not orders:
        await _show_empty_orders(message, lang)
        return

    active_statuses = {"pending", "preparing", "ready", "delivering"}

    # Разделяем по статусам (legacy bookings + unified orders)
    active_bookings = [
        b for b in bookings if _normalize_status(_get_field(b, "status")) in active_statuses
    ]

    active_pickup_orders = []
    active_delivery_orders = []
    for o in orders:
        raw_status = _get_field(o, "order_status", 10)
        status = _normalize_status(raw_status)
        if status not in active_statuses:
            continue

        order_type = _get_field(o, "order_type") or ("delivery" if _get_field(o, "delivery_address") else "pickup")
        if order_type == "delivery":
            active_delivery_orders.append(o)
        else:
            active_pickup_orders.append(o)

    active_total = len(active_bookings) + len(active_pickup_orders) + len(active_delivery_orders)

    # Счётчики для summary
    total_completed = len([b for b in bookings if _normalize_status(_get_field(b, "status")) == "completed"]) + len(
        [o for o in orders if _normalize_status(_get_field(o, "order_status", 10)) == "completed"]
    )
    total_cancelled = len(
        [
            b
            for b in bookings
            if _normalize_status(_get_field(b, "status")) in ("cancelled", "rejected")
        ]
    ) + len(
        [
            o
            for o in orders
            if _normalize_status(_get_field(o, "order_status", 10)) in ("cancelled", "rejected")
        ]
    )

    kb = InlineKeyboardBuilder()
    text_lines = []

    # ═══════════════════════════════════════════════════════════════════
    # АКТИВНЫЕ ЗАКАЗЫ
    # ═══════════════════════════════════════════════════════════════════
    if active_bookings or active_pickup_orders or active_delivery_orders:
        title = _t(lang, "Активные заказы и бронирования", "Faol buyurtmalar va bronlar")
        text_lines.append(f"<b>{title}</b> ({active_total})\n")
        status_label = _t(lang, "Статус", "Holat")

        # Показываем legacy bookings (самовывоз из таблицы bookings)
        for booking in active_bookings[:5]:
            booking_id = _get_field(booking, "booking_id")
            store_name = _get_field(booking, "name") or "Магазин"  # name в dict, не store_name
            status = _normalize_status(_get_field(booking, "status"))
            # Вычисляем total из quantity × discount_price
            quantity = _get_field(booking, "quantity") or 1
            discount_price = _get_field(booking, "discount_price") or 0
            total = calc_total_price(discount_price, quantity)

            emoji, status_text = _get_status_info(status, False, lang)

            text_lines.append(f"<b>#{booking_id}</b> • {store_name}")
            text_lines.append(f"{emoji} {status_text}")
            text_lines.append(_format_price(total, lang))
            text_lines.append("")

            kb.button(
                text=f"#{booking_id} ➡️",
                callback_data=f"myorder_detail_b_{booking_id}",
            )

        # Показываем pickup orders из таблицы orders (новый самовывоз)
        for order in active_pickup_orders[:5]:
            order_id = _get_field(order, "order_id", 0)
            store_id = _get_field(order, "store_id")
            store = db.get_store(store_id) if store_id and hasattr(db, "get_store") else None
            store_name = (
                store.get("name")
                if isinstance(store, dict)
                else getattr(store, "name", None)
                if store
                else None
            ) or "Магазин"

            status = _normalize_status(_get_field(order, "order_status", 10))
            total = _get_field(order, "total_price", 5) or 0
            emoji, status_text = _get_status_info(status, False, lang)

            text_lines.append(f"<b>#{order_id}</b> • {store_name}")
            text_lines.append(f"{emoji} {status_text}")
            text_lines.append(_format_price(total, lang))
            text_lines.append("")

            kb.button(
                text=f"#{order_id} ➡️",
                callback_data=f"myorder_detail_o_{order_id}",
            )

        # Показываем delivery orders (доставка)
        for order in active_delivery_orders[:5]:
            order_id = _get_field(order, "order_id", 0)
            store_id = _get_field(order, "store_id")
            store = db.get_store(store_id) if store_id and hasattr(db, "get_store") else None
            store_name = (
                store.get("name")
                if isinstance(store, dict)
                else getattr(store, "name", None)
                if store
                else None
            ) or "Магазин"

            status = _normalize_status(_get_field(order, "order_status", 10))
            total = _get_field(order, "total_price", 5) or 0
            emoji, status_text = _get_status_info(status, True, lang)

            text_lines.append(f"<b>#{order_id}</b> • {store_name}")
            text_lines.append(f"{emoji} {status_text}")
            text_lines.append(_format_price(total, lang))
            text_lines.append("")

            kb.button(
                text=f"#{order_id} ➡️",
                callback_data=f"myorder_detail_o_{order_id}",
            )

        kb.adjust(1)  # По одной кнопке в ряд
    else:
        # Нет активных
        no_active = _t(lang, "Активных заказов нет.", "Faol buyurtmalar yo'q.")
        text_lines.append(f"<b>{no_active}</b>\n")

    # ═══════════════════════════════════════════════════════════════════
    # SUMMARY + ИСТОРИЯ
    # ═══════════════════════════════════════════════════════════════════
    text_lines.append("")
    text_lines.append(f"<b>{_t(lang, 'История', 'Tarix')}</b>")

    completed_label = _t(lang, "Завершено", "Yakunlangan")
    cancelled_label = _t(lang, "Отменено", "Bekor qilingan")
    text_lines.append(f"{completed_label}: <b>{total_completed}</b>")
    text_lines.append(f"{cancelled_label}: <b>{total_cancelled}</b>")

    # Кнопки фильтров истории
    kb.button(
        text=f"{_t(lang, 'Завершённые', 'Yakunlangan')} ({total_completed})",
        callback_data="myorders_history_completed",
    )

    if total_cancelled > 0:
        kb.button(
            text=f"{_t(lang, 'Отменённые', 'Bekor qilingan')} ({total_cancelled})",
            callback_data="myorders_history_cancelled",
        )

    kb.adjust(1)

    await message.answer(_fmt(text_lines), parse_mode="HTML", reply_markup=kb.as_markup())


async def _show_empty_orders(message: types.Message, lang: str) -> None:
    """Показать пустой экран заказов."""
    title = _t(lang, "Заказы и бронирования", "Buyurtmalar va bronlar")
    empty_text = _t(
        lang,
        "У вас пока нет заказов и бронирований",
        "Sizda hali buyurtmalar va bronlar yo'q",
    )
    hint = _t(
        lang,
        "Откройте «🥗 Еда со скидкой» — там товары со скидками до 70%",
        "“🥗 Chegirmali taomlar” bo'limini sinab ko'ring — u yerda 70% gacha chegirmalar",
    )

    kb = InlineKeyboardBuilder()
    kb.button(
        text=_t(lang, "Открыть раздел", "Bo'limni ochish"), callback_data="hot_offers"
    )

    await message.answer(
        f"<b>{title}</b>\n\n{empty_text}\n\n{hint}",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


# =============================================================================
# ORDER DETAIL VIEW
# =============================================================================


@router.callback_query(F.data.startswith("myorder_detail_"))
async def order_detail_handler(callback: types.CallbackQuery) -> None:
    """
    Детальный просмотр заказа.
    Показывает: товары, цены, статус, адрес/код, кнопки действий.
    """
    if not db or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Parse: myorder_detail_b_123 или myorder_detail_o_123
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer(_t(lang, "Ошибка", "Xatolik"))
        return

    order_type = parts[2]  # 'b' = booking, 'o' = order
    try:
        order_id = int(parts[3])
    except ValueError:
        await callback.answer(_t(lang, "Ошибка", "Xatolik"))
        return

    # If Mini App is available, keep bot as navigation only.
    if order_type != "b":
        webapp_url = os.getenv("WEBAPP_URL", "").strip()
        if webapp_url:
            hint = get_text(lang, "order_card_updated_hint")
            kb = _build_open_app_keyboard(lang, order_id)
            try:
                await callback.message.edit_text(
                    _fmt([hint]), parse_mode="HTML", reply_markup=kb.as_markup()
                )
            except Exception:
                await callback.message.answer(
                    _fmt([hint]), parse_mode="HTML", reply_markup=kb.as_markup()
                )
            await callback.answer()
            return

    if order_type == "b":
        await _show_booking_detail(callback, order_id, lang)
    else:
        await _show_order_detail(callback, order_id, lang)

    await callback.answer()


async def _show_booking_detail(callback: types.CallbackQuery, booking_id: int, lang: str) -> None:
    """Загрузка карточки брони (упрощённый fallback)."""
    user_id = callback.from_user.id

    query = """
                SELECT
                    b.booking_id,
                    b.status,
                    b.booking_code,
                    b.created_at,
                    b.updated_at,
                    COALESCE(b.quantity, 1) as quantity,
                    s.name as store_name,
                    s.address as store_address,
                    COALESCE(b.store_phone, s.phone) as store_phone,
                    off.title as offer_title,
                    off.discount_price,
                    off.original_price,
                    off.unit
                FROM bookings b
                LEFT JOIN offers off ON b.offer_id = off.offer_id
                LEFT JOIN stores s ON off.store_id = s.store_id
                WHERE b.booking_id = %s AND b.user_id = %s
            """
    fallback_query = """
                SELECT
                    b.booking_id,
                    b.status,
                    b.booking_code,
                    b.created_at,
                    b.updated_at,
                    COALESCE(b.quantity, 1) as quantity,
                    s.name as store_name,
                    s.address as store_address,
                    s.phone as store_phone,
                    off.title as offer_title,
                    off.discount_price,
                    off.original_price,
                    off.unit
                FROM bookings b
                LEFT JOIN offers off ON b.offer_id = off.offer_id
                LEFT JOIN stores s ON off.store_id = s.store_id
                WHERE b.booking_id = %s AND b.user_id = %s
            """
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, (booking_id, user_id))
            except Exception as e:
                if "store_phone" in str(e):
                    cursor.execute(fallback_query, (booking_id, user_id))
                else:
                    raise
            booking = cursor.fetchone()
    except Exception as e:
        logger.error(f"Failed to get booking {booking_id}: {e}")
        await callback.message.answer(_t(lang, "Не удалось загрузить", "Yuklab bo'lmadi"))
        return

    if not booking:
        await callback.message.answer(_t(lang, "Заказ не найден", "Buyurtma topilmadi"))
        return

    if hasattr(booking, "get"):
        data = booking
    else:
        quantity = booking[5] or 1
        discount_price = booking[10] or 0
        data = {
            "booking_id": booking[0],
            "status": booking[1],
            "booking_code": booking[2],
            "created_at": booking[3],
            "updated_at": booking[4],
            "quantity": quantity,
            "store_name": booking[6],
            "store_address": booking[7],
            "store_phone": booking[8],
            "offer_title": booking[9],
            "discount_price": discount_price,
            "original_price": booking[11],
            "unit": booking[12],
            "total_price": calc_total_price(discount_price, quantity),
        }

    status = _normalize_status(data.get("status", "pending"))
    total = int(data.get("total_price") or 0)
    currency = get_text(lang, "currency")
    ready_until = _format_ready_until(data.get("updated_at")) if status == "ready" else None

    card = NotificationTemplates.customer_status_update(
        lang=lang,
        order_id=int(data["booking_id"]),
        status=status,
        order_type="pickup",
        store_name=str(data.get("store_name") or ""),
        store_address=data.get("store_address"),
        pickup_code=data.get("booking_code"),
        total=total,
        delivery_price=0,
        currency=currency,
        ready_until=ready_until,
    )

    lines = [card]
    store_phone_raw = data.get("store_phone")
    formatted_phone = _format_phone_display(store_phone_raw)
    if formatted_phone:
        lines.append("")
        lines.append(get_text(lang, "contact_store_line"))
        lines.append(formatted_phone)

    if status == "ready":
        minutes_left = _ready_minutes_left(data.get("updated_at"))
        if minutes_left is not None and 0 < minutes_left <= 30:
            lines.append("")
            lines.append(get_text(lang, "contact_store_late_notice"))

    kb = _build_open_app_keyboard(lang, int(data["booking_id"]), store_phone_raw)

    await _maybe_transfer_customer_card(
        user_id=user_id,
        entity_type="booking",
        entity_id=int(data["booking_id"]),
        current_message_id=callback.message.message_id if callback.message else None,
    )

    try:
        await callback.message.edit_text(_fmt(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(_fmt(lines), parse_mode="HTML", reply_markup=kb.as_markup())


async def _show_order_detail(callback: types.CallbackQuery, order_id: int, lang: str) -> None:
    """Загрузка карточки заказа (упрощённый fallback)."""
    user_id = callback.from_user.id

    query = """
                SELECT
                    o.order_id,
                    o.store_id,
                    o.order_type,
                    o.order_status,
                    o.payment_method,
                    o.payment_status,
                    o.pickup_code,
                    o.delivery_address,
                    o.total_price,
                    o.created_at,
                    o.updated_at,
                    o.quantity,
                    s.name as store_name,
                    s.address as store_address,
                    COALESCE(o.store_phone, s.phone) as store_phone,
                    off.title as offer_title,
                    off.discount_price,
                    off.original_price,
                    off.unit,
                    o.is_cart_order,
                    o.cart_items,
                    o.delivery_price,
                    o.item_title,
                    o.item_price,
                    o.item_original_price
                FROM orders o
                LEFT JOIN stores s ON o.store_id = s.store_id
                LEFT JOIN offers off ON o.offer_id = off.offer_id
                WHERE o.order_id = %s AND o.user_id = %s
            """
    fallback_query = """
                SELECT
                    o.order_id,
                    o.store_id,
                    o.order_type,
                    o.order_status,
                    o.payment_method,
                    o.payment_status,
                    o.pickup_code,
                    o.delivery_address,
                    o.total_price,
                    o.created_at,
                    o.updated_at,
                    o.quantity,
                    s.name as store_name,
                    s.address as store_address,
                    s.phone as store_phone,
                    off.title as offer_title,
                    off.discount_price,
                    off.original_price,
                    off.unit,
                    o.is_cart_order,
                    o.cart_items,
                    o.delivery_price,
                    o.item_title,
                    o.item_price,
                    o.item_original_price
                FROM orders o
                LEFT JOIN stores s ON o.store_id = s.store_id
                LEFT JOIN offers off ON o.offer_id = off.offer_id
                WHERE o.order_id = %s AND o.user_id = %s
            """
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, (order_id, user_id))
            except Exception as e:
                if "store_phone" in str(e):
                    cursor.execute(fallback_query, (order_id, user_id))
                else:
                    raise
            order = cursor.fetchone()
    except Exception as e:
        logger.error(f"Failed to get order {order_id}: {e}")
        await callback.message.answer(_t(lang, "Не удалось загрузить", "Yuklab bo'lmadi"))
        return

    if not order:
        await callback.message.answer(_t(lang, "Заказ не найден", "Buyurtma topilmadi"))
        return

    if hasattr(order, "get"):
        data = order
    else:
        data = {
            "order_id": order[0],
            "store_id": order[1],
            "order_type": order[2],
            "order_status": order[3],
            "payment_method": order[4],
            "payment_status": order[5],
            "pickup_code": order[6],
            "delivery_address": order[7],
            "total_price": order[8],
            "created_at": order[9],
            "updated_at": order[10],
            "quantity": order[11],
            "store_name": order[12],
            "store_address": order[13],
            "store_phone": order[14],
            "offer_title": order[15],
            "discount_price": order[16],
            "original_price": order[17],
            "unit": order[18],
            "is_cart_order": order[19] if len(order) > 19 else False,
            "cart_items": order[20] if len(order) > 20 else None,
            "delivery_price": order[21] if len(order) > 21 else None,
            "item_title": order[22] if len(order) > 22 else None,
            "item_price": order[23] if len(order) > 23 else None,
            "item_original_price": order[24] if len(order) > 24 else None,
        }

    raw_status = data.get("order_status", "pending")
    status = _normalize_status(raw_status)
    order_type = data.get("order_type") or ("delivery" if data.get("delivery_address") else "pickup")
    is_delivery = order_type in ("delivery", "taxi")
    is_cart = data.get("is_cart_order")
    cart_items_json = data.get("cart_items")

    items_total = 0
    if is_cart and cart_items_json:
        items = parse_cart_items(cart_items_json)
        if items:
            items_total = calc_items_total(items)
        else:
            items_total = int(data.get("total_price") or 0)
    else:
        qty = data.get("quantity", 1)
        price = data.get("item_price")
        if price is None:
            price = data.get("discount_price", 0)
        items_total = calc_total_price(price or 0, qty)

    total_price = int(data.get("total_price") or 0)
    delivery_fee = 0
    if is_delivery:
        delivery_fee = calc_delivery_fee(
            total_price,
            items_total,
            delivery_price=data.get("delivery_price"),
            order_type=order_type,
        )
    total_value = total_price if total_price > 0 else items_total
    currency = get_text(lang, "currency")
    ready_until = _format_ready_until(data.get("updated_at")) if (not is_delivery and status == "ready") else None

    card = NotificationTemplates.customer_status_update(
        lang=lang,
        order_id=int(data["order_id"]),
        status=status,
        order_type="delivery" if is_delivery else "pickup",
        store_name=str(data.get("store_name") or ""),
        store_address=data.get("store_address"),
        delivery_address=data.get("delivery_address"),
        pickup_code=data.get("pickup_code"),
        total=total_value,
        delivery_price=int(data.get("delivery_price") or 0),
        currency=currency,
        ready_until=ready_until,
    )

    lines = [card]
    store_phone_raw = data.get("store_phone")
    formatted_phone = _format_phone_display(store_phone_raw)
    if formatted_phone:
        lines.append("")
        lines.append(get_text(lang, "contact_store_line"))
        lines.append(formatted_phone)

    if not is_delivery and status == "ready":
        minutes_left = _ready_minutes_left(data.get("updated_at"))
        if minutes_left is not None and 0 < minutes_left <= 30:
            lines.append("")
            lines.append(get_text(lang, "contact_store_late_notice"))

    kb = _build_open_app_keyboard(lang, int(data["order_id"]), store_phone_raw)

    await _maybe_transfer_customer_card(
        user_id=user_id,
        entity_type="order",
        entity_id=int(data["order_id"]),
        current_message_id=callback.message.message_id if callback.message else None,
    )

    try:
        await callback.message.edit_text(_fmt(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(_fmt(lines), parse_mode="HTML", reply_markup=kb.as_markup())


# =============================================================================
# ORDER ACTIONS
# =============================================================================


@router.callback_query(F.data.startswith("myorder_received_"))
async def order_received_handler(callback: types.CallbackQuery) -> None:
    """Клиент подтвердил получение заказа."""
    if not db or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer(_t(lang, "Ошибка", "Xatolik"))
        return

    order_type = parts[2]  # 'b' or 'o'
    try:
        order_id = int(parts[3])
    except ValueError:
        await callback.answer(_t(lang, "Ошибка", "Xatolik"))
        return

    try:
        entity = None
        if order_type == "b":
            entity = db.get_booking(order_id) if hasattr(db, "get_booking") else None
        else:
            entity = db.get_order(order_id) if hasattr(db, "get_order") else None

        if not entity:
            await callback.answer(_t(lang, "Заказ не найден", "Buyurtma topilmadi"), show_alert=True)
            return

        entity_user_id = entity.get("user_id") if hasattr(entity, "get") else _get_field(entity, 2)
        if entity_user_id != user_id:
            await callback.answer(_t(lang, "Доступ запрещен", "Ruxsat yo'q"), show_alert=True)
            return

        service = get_unified_order_service()
        if not service and callback.bot:
            service = init_unified_order_service(db, callback.bot)
        if not service:
            await callback.answer(_t(lang, "Ошибка", "Xatolik"), show_alert=True)
            return

        entity_type = "booking" if order_type == "b" else "order"
        success = await service.complete_order(order_id, entity_type)
        if not success:
            await callback.answer(_t(lang, "Ошибка", "Xatolik"), show_alert=True)
            return

        await callback.answer(
            _t(lang, "Спасибо! Заказ завершён.", "Rahmat! Buyurtma yakunlandi."),
            show_alert=True,
        )

        # Показываем экран рейтинга
        kb = InlineKeyboardBuilder()
        kb.button(text="⭐⭐⭐⭐⭐", callback_data=f"myorder_rate_{order_type}_{order_id}_5")
        kb.button(text="⭐⭐⭐⭐", callback_data=f"myorder_rate_{order_type}_{order_id}_4")
        kb.button(text="⭐⭐⭐", callback_data=f"myorder_rate_{order_type}_{order_id}_3")
        kb.button(
            text=_t(lang, "Пропустить", "O'tkazib yuborish"), callback_data="myorders_back"
        )
        kb.adjust(1)

        await callback.message.edit_text(
            f"<b>{_t(lang, 'Оцените заказ', 'Buyurtmani baholang')}</b>\n\n"
            f"{_t(lang, 'Как вам качество товаров и обслуживание?', 'Mahsulotlar sifati va xizmat qanday bo''ldi?')}",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )

    except Exception as e:
        logger.error(f"Failed to complete order {order_id}: {e}")
        await callback.answer(_t(lang, "Ошибка", "Xatolik"), show_alert=True)


@router.callback_query(F.data.startswith("myorder_rate_"))
async def order_rate_handler(callback: types.CallbackQuery) -> None:
    """Клиент оценил заказ."""
    if not db or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Parse: myorder_rate_o_123_5
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer()
        return

    try:
        order_type = parts[2]
        order_id = int(parts[3])
        rating = int(parts[4])
    except (ValueError, IndexError):
        await callback.answer()
        return

    # Сохраняем рейтинг (если есть такая функция)
    try:
        if hasattr(db, "add_order_rating"):
            db.add_order_rating(order_id, user_id, rating)
    except Exception as e:
        logger.warning(f"Failed to save rating: {e}")

    await callback.answer(_t(lang, "Спасибо за оценку!", "Baholaganingiz uchun rahmat!"))

    # Возвращаемся к списку заказов
    await callback.message.delete()


@router.callback_query(F.data.startswith("myorder_problem_"))
async def order_problem_handler(callback: types.CallbackQuery) -> None:
    """Клиент сообщает о проблеме с заказом."""
    if not db or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer()
        return

    order_type = parts[2]
    try:
        order_id = int(parts[3])
    except ValueError:
        await callback.answer()
        return

    # Показываем опции проблем
    kb = InlineKeyboardBuilder()

    problems = [
        ("late", _t(lang, "Долгая доставка", "Uzoq yetkazish")),
        ("wrong", _t(lang, "Неправильный заказ", "Noto'g'ri buyurtma")),
        ("quality", _t(lang, "Качество товара", "Mahsulot sifati")),
        ("other", _t(lang, "Другое", "Boshqa")),
    ]

    for code, text in problems:
        kb.button(text=text, callback_data=f"myorder_report_{order_type}_{order_id}_{code}")

    kb.button(
        text=_t(lang, "Назад", "Orqaga"),
        callback_data=f"myorder_detail_{order_type}_{order_id}",
    )
    kb.adjust(1)

    await callback.message.edit_text(
        f"<b>{_t(lang, 'Выберите тип проблемы', 'Muammo turini tanlang')}</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("myorder_report_"))
async def order_report_handler(callback: types.CallbackQuery) -> None:
    """Сохранение жалобы на заказ."""
    if not db or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Parse: myorder_report_o_123_late
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer()
        return

    try:
        order_type = parts[2]
        order_id = int(parts[3])
        problem_code = parts[4]
    except (ValueError, IndexError):
        await callback.answer()
        return

    # Логируем жалобу (можно добавить таблицу complaints)
    logger.info(
        f"User {user_id} reported problem '{problem_code}' for order {order_type}_{order_id}"
    )

    # Уведомление админу
    try:
        admin_ids = db.get_admin_ids() if hasattr(db, "get_admin_ids") else []
        for admin_id in admin_ids[:3]:  # Max 3 admins
            try:
                await bot.send_message(
                    admin_id,
                    f"<b>Жалоба на заказ #{order_id}</b>\n\n"
                    f"Пользователь: {user_id}\n"
                    f"Тип: {'Доставка' if order_type == 'o' else 'Самовывоз'}\n"
                    f"Проблема: {problem_code}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    except Exception:
        pass

    await callback.answer(
        _t(
            lang,
            "Жалоба отправлена. Мы свяжемся с вами!",
            "Shikoyat yuborildi. Siz bilan bog'lanamiz!",
        ),
        show_alert=True,
    )

    # Возвращаемся к списку
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("myorder_cancel_o_"))
async def order_cancel_handler(callback: types.CallbackQuery) -> None:
    """Отмена заказа пользователем."""
    if not db or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(_t(lang, "Ошибка", "Xatolik"))
        return

    # Проверяем статус - можно отменить только pending
    try:
        order = db.get_order(order_id)
        if not order:
            await callback.answer(_t(lang, "Заказ не найден", "Buyurtma topilmadi"))
            return

        if hasattr(order, "get"):
            raw_status = order.get("order_status") or order.get("status")
        else:
            raw_status = _get_field(order, 10)
        status = _normalize_status(raw_status)
        payment_method = (
            order.get("payment_method") if hasattr(order, "get") else _get_field(order, 9)
        )
        payment_status_raw = (
            order.get("payment_status") if hasattr(order, "get") else _get_field(order, 11)
        )
        normalized_payment_status = PaymentStatus.normalize(
            payment_status_raw,
            payment_method=payment_method,
        )
        if normalized_payment_status == PaymentStatus.CONFIRMED:
            await callback.answer(
                get_text(lang, "paid_order_cancel_blocked"),
                show_alert=True,
            )
            return
        if status != "pending":
            await callback.answer(
                _t(
                    lang,
                    "Заказ уже обрабатывается, отменить нельзя",
                    "Buyurtma qayta ishlanmoqda, bekor qilib bo'lmaydi",
                ),
                show_alert=True,
            )
            return

        service = get_unified_order_service()
        if not service:
            await callback.answer(_t(lang, "Ошибка", "Xatolik"), show_alert=True)
            return

        success = await service.cancel_order(order_id, "order")
        if not success:
            await callback.answer(_t(lang, "Ошибка", "Xatolik"), show_alert=True)
            return

        await callback.answer(_t(lang, "Заказ отменён", "Buyurtma bekor qilindi"), show_alert=True)

        # Удаляем сообщение и возвращаемся
        try:
            await callback.message.delete()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Failed to cancel order {order_id}: {e}")
        await callback.answer(_t(lang, "Ошибка", "Xatolik"), show_alert=True)


# =============================================================================
# HISTORY
# =============================================================================


@router.callback_query(F.data.startswith("myorders_history_"))
async def orders_history_handler(callback: types.CallbackQuery) -> None:
    """Показать историю заказов по фильтру."""
    if not db or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    status_filter = callback.data.replace("myorders_history_", "")

    # Получаем заказы с нужным статусом
    bookings = db.get_user_bookings(user_id) or []
    try:
        orders = db.get_user_orders(user_id) or []
    except Exception:
        orders = []

    # Фильтруем
    if status_filter == "cancelled":
        filtered_bookings = [
            b
            for b in bookings
            if _normalize_status(_get_field(b, "status")) in ("cancelled", "rejected")
        ]
        filtered_orders = [
            o
            for o in orders
            if _normalize_status(_get_field(o, "order_status", 10)) in ("cancelled", "rejected")
        ]
    else:
        filtered_bookings = [
            b for b in bookings if _normalize_status(_get_field(b, "status")) == status_filter
        ]
        filtered_orders = [
            o for o in orders if _normalize_status(_get_field(o, "order_status", 10)) == status_filter
        ]

    if not filtered_bookings and not filtered_orders:
        await callback.answer(_t(lang, "Нет заказов", "Buyurtmalar yo'q"))
        return

    lines = []
    title = (
        _t(lang, "Завершённые заказы", "Yakunlangan buyurtmalar")
        if status_filter == "completed"
        else _t(lang, "Отменённые заказы", "Bekor qilingan buyurtmalar")
    )
    lines.append(f"<b>{title}</b>\n")

    kb = InlineKeyboardBuilder()

    # Bookings
    for b in filtered_bookings[:10]:
        booking_id = _get_field(b, "booking_id")
        store_name = _get_field(b, "name") or "Магазин"  # name в dict, не store_name
        # Вычисляем total
        quantity = _get_field(b, "quantity") or 1
        discount_price = _get_field(b, "discount_price") or 0
        total = calc_total_price(discount_price, quantity)

        lines.append(f"<b>#{booking_id}</b> • {store_name}")
        lines.append(f"   {_t(lang, 'Самовывоз', 'Olib ketish')} • {_format_price(total, lang)}")
        lines.append("")

        kb.button(
            text=f"{_t(lang, 'Повторить', 'Qayta')} #{booking_id}",
            callback_data=f"repeat_order_b_{booking_id}",
        )

    # Orders (pickup + delivery in orders table)
    for o in filtered_orders[:10]:
        order_id = _get_field(o, "order_id", 0)
        store_id = _get_field(o, "store_id")
        store = db.get_store(store_id) if store_id and hasattr(db, "get_store") else None
        store_name = (
            store.get("name")
            if isinstance(store, dict)
            else getattr(store, "name", None)
            if store
            else None
        ) or "Магазин"
        total = _get_field(o, "total_price", 5) or 0
        order_type = _get_field(o, "order_type") or ("delivery" if _get_field(o, "delivery_address") else "pickup")

        lines.append(f"<b>#{order_id}</b> • {store_name}")
        if order_type == "delivery":
            lines.append(
                f"   {_t(lang, 'Доставка', 'Yetkazish')} • {_format_price(total, lang)}"
            )
        else:
            lines.append(
                f"   {_t(lang, 'Самовывоз', 'Olib ketish')} • {_format_price(total, lang)}"
            )
        lines.append("")

        kb.button(
            text=f"{_t(lang, 'Повторить', 'Qayta')} #{order_id}",
            callback_data=f"repeat_order_o_{order_id}",
        )

    kb.button(text=_t(lang, "Назад", "Orqaga"), callback_data="myorders_back")
    kb.adjust(1)

    try:
        await callback.message.edit_text(_fmt(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(_fmt(lines), parse_mode="HTML", reply_markup=kb.as_markup())

    await callback.answer()


@router.callback_query(F.data == "myorders_back")
async def myorders_back_handler(callback: types.CallbackQuery) -> None:
    """Вернуться к списку заказов."""
    if not db:
        await callback.answer()
        return

    # Создаём фейковый message для вызова главного хендлера
    # Удаляем текущее сообщение и отправляем новое
    try:
        await callback.message.delete()
    except Exception:
        pass

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Создаём новое сообщение через главный хендлер
    # Используем callback.message как base
    fake_message = callback.message
    fake_message.text = (
        "Заказы и бронирования" if lang == "ru" else "Buyurtmalar va bronlar"
    )

    await my_orders_handler(fake_message)
    await callback.answer()


# =============================================================================
# HELPERS
# =============================================================================


def _get_field(obj: Any, key: str | int, default: Any = None) -> Any:
    """Universal field getter for dict or tuple."""
    if hasattr(obj, "get"):
        return obj.get(key, default)
    elif isinstance(key, int) and isinstance(obj, (list, tuple)):
        return obj[key] if len(obj) > key else default
    return default

