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
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.unified_order_service import OrderStatus, get_unified_order_service
from handlers.common.utils import fix_mojibake_text, is_my_orders_button

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


# =============================================================================
# STATUS CONFIGS
# =============================================================================

ORDER_STATUSES = {
    "pending": {"emoji": "•", "ru": "Ожидает подтверждения", "uz": "Tasdiqlanishi kutilmoqda"},
    "preparing": {"emoji": "•", "ru": "Готовится", "uz": "Tayyorlanmoqda"},
    "ready": {"emoji": "•", "ru": "Готов", "uz": "Tayyor"},
    "delivering": {"emoji": "•", "ru": "Курьер в пути", "uz": "Kuryer yo'lda"},
    "completed": {"emoji": "•", "ru": "Завершён", "uz": "Yakunlangan"},
    "rejected": {"emoji": "•", "ru": "Отклонён", "uz": "Rad etilgan"},
    "cancelled": {"emoji": "•", "ru": "Отменён", "uz": "Bekor qilingan"},
}

BOOKING_STATUSES = {
    "pending": {"emoji": "•", "ru": "Ожидает", "uz": "Kutilmoqda"},
    "preparing": {"emoji": "•", "ru": "Готовится", "uz": "Tayyorlanmoqda"},
    "ready": {"emoji": "•", "ru": "Готов", "uz": "Tayyor"},
    "completed": {"emoji": "•", "ru": "Завершён", "uz": "Yakunlangan"},
    "rejected": {"emoji": "•", "ru": "Отклонён", "uz": "Rad etilgan"},
    "cancelled": {"emoji": "•", "ru": "Отменён", "uz": "Bekor qilingan"},
}


def _normalize_status(status: str | None) -> str:
    """Normalize legacy statuses to the fulfillment-only order_status model."""
    if not status:
        return OrderStatus.PENDING
    status_str = str(status).strip().lower()
    if status_str == "active":
        return OrderStatus.PENDING
    try:
        return OrderStatus.normalize(status_str)
    except Exception:
        return status_str


def _get_status_info(status: str, is_delivery: bool, lang: str) -> tuple[str, str]:
    """Get status emoji and text."""
    statuses = ORDER_STATUSES if is_delivery else BOOKING_STATUSES
    status_norm = _normalize_status(status)
    info = statuses.get(status_norm, {"emoji": "•", "ru": status_norm, "uz": status_norm})
    return info["emoji"], info.get(lang, info["ru"])


def _format_price(amount: int | float, lang: str) -> str:
    """Format price with currency."""
    currency = "сум" if lang == "ru" else "so'm"
    return f"{int(amount):,} {currency}".replace(",", " ")


def _fmt(lines: list[str]) -> str:
    """Join lines and fix mojibake (cp1251-decoded UTF-8) if present."""
    return fix_mojibake_text("\n".join(lines))


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
        type_pickup = _t(lang, "Самовывоз", "Olib ketish")
        type_delivery = _t(lang, "Доставка", "Yetkazish")
        code_label = _t(lang, "Код", "Kod")
        address_label = _t(lang, "Адрес", "Manzil")

        # Показываем legacy bookings (самовывоз из таблицы bookings)
        for booking in active_bookings[:5]:
            booking_id = _get_field(booking, "booking_id")
            store_name = _get_field(booking, "name") or "Магазин"  # name в dict, не store_name
            status = _normalize_status(_get_field(booking, "status"))
            pickup_code = _get_field(booking, "booking_code")
            # Вычисляем total из quantity × discount_price
            quantity = _get_field(booking, "quantity") or 1
            discount_price = _get_field(booking, "discount_price") or 0
            total = quantity * discount_price

            emoji, status_text = _get_status_info(status, False, lang)

            text_lines.append(f"<b>#{booking_id}</b> • {store_name}")
            text_lines.append(f"   {type_pickup} • {_format_price(total, lang)}")
            if pickup_code:
                text_lines.append(f"   {code_label}: <code>{pickup_code}</code>")
            text_lines.append(f"   {status_label}: {status_text}")
            text_lines.append("")

            # Кнопка детализации
            store_name_str = str(store_name) if store_name else "Магазин"
            kb.button(
                text=f"{_t(lang, 'Детали', 'Batafsil')} #{booking_id}",
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
            pickup_code = _get_field(order, "pickup_code")

            emoji, status_text = _get_status_info(status, False, lang)

            text_lines.append(f"<b>#{order_id}</b> • {store_name}")
            text_lines.append(f"   {type_pickup} • {_format_price(total, lang)}")
            if pickup_code:
                text_lines.append(f"   {code_label}: <code>{pickup_code}</code>")
            text_lines.append(f"   {status_label}: {status_text}")
            text_lines.append("")

            store_name_str = str(store_name) if store_name else "Магазин"
            kb.button(
                text=f"{_t(lang, 'Детали', 'Batafsil')} #{order_id}",
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
            address = _get_field(order, "delivery_address", 4) or ""

            emoji, status_text = _get_status_info(status, True, lang)

            text_lines.append(f"<b>#{order_id}</b> • {store_name}")
            text_lines.append(f"   {type_delivery} • {_format_price(total, lang)}")
            if address:
                short_addr = address[:30] + "..." if len(address) > 30 else address
                text_lines.append(f"   {address_label}: {short_addr}")
            text_lines.append(f"   {status_label}: {status_text}")
            text_lines.append("")

            # Кнопка детализации
            store_name_str = str(store_name) if store_name else "Магазин"
            kb.button(
                text=f"{_t(lang, 'Детали', 'Batafsil')} #{order_id}",
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
        "Откройте «Акции и магазины» — там товары со скидками до 70%",
        "“Aksiyalar va do'konlar” bo'limini sinab ko'ring — u yerda 70% gacha chegirmalar",
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

    if order_type == "b":
        await _show_booking_detail(callback, order_id, lang)
    else:
        await _show_order_detail(callback, order_id, lang)

    await callback.answer()


async def _show_booking_detail(callback: types.CallbackQuery, booking_id: int, lang: str) -> None:
    """Показать детали бронирования (самовывоз)."""
    user_id = callback.from_user.id

    # Получаем детали бронирования
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    b.booking_id,
                    b.status,
                    b.booking_code,
                    b.created_at,
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
            """,
                (booking_id, user_id),
            )
            booking = cursor.fetchone()
    except Exception as e:
        logger.error(f"Failed to get booking {booking_id}: {e}")
        await callback.message.answer(_t(lang, "Ошибка загрузки", "Yuklab bo'lmadi"))
        return

    if not booking:
        await callback.message.answer(_t(lang, "Заказ не найден", "Buyurtma topilmadi"))
        return

    # Парсим данные
    if hasattr(booking, "get"):
        data = booking
    else:
        quantity = booking[4] or 1
        discount_price = booking[9] or 0
        data = {
            "booking_id": booking[0],
            "status": booking[1],
            "booking_code": booking[2],
            "created_at": booking[3],
            "quantity": quantity,
            "store_name": booking[5],
            "store_address": booking[6],
            "store_phone": booking[7],
            "offer_title": booking[8],
            "discount_price": discount_price,
            "original_price": booking[10],
            "unit": booking[11],
            "total_price": quantity * discount_price,  # Вычисляем
        }

    status = _normalize_status(data.get("status", "pending"))
    status_label = _t(lang, "Статус", "Holat")
    address_label = _t(lang, "Адрес", "Manzil")
    emoji, status_text = _get_status_info(status, False, lang)

    # Формируем текст
    lines = []
    lines.append(f"<b>{_t(lang, 'Самовывоз', 'Olib ketish')} #{data['booking_id']}</b>")
    lines.append(f"{status_label}: <b>{status_text}</b>")
    lines.append("")

    # Магазин
    lines.append(f"<b>{data.get('store_name', 'Магазин')}</b>")
    if data.get("store_address"):
        lines.append(f"{address_label}: {data['store_address']}")
    lines.append("")

    # Товары
    lines.append(f"<b>{_t(lang, 'Товары', 'Mahsulotlar')}:</b>")

    # Bookings всегда одиночный товар (не корзина)
    title = data.get("offer_title", "Товар") or "Товар"
    qty = data.get("quantity") or 1
    price = data.get("discount_price") or 0
    total = data.get("total_price") or (price * qty)
    lines.append(f"   • {title} × {qty} = {_format_price(price * qty, lang)}")

    lines.append("")
    lines.append(f"<b>{_t(lang, 'Итого', 'Jami')}:</b> {_format_price(total, lang)}")

    # Код получения
    if data.get("booking_code") and status in ("preparing", "ready"):
        lines.append("")
        lines.append(f"<b>{_t(lang, 'Код получения', 'Olish kodi')}:</b>")
        lines.append(f"<code>{data['booking_code']}</code>")
        lines.append(
            f"<i>{_t(lang, 'Покажите код при получении', 'Olishda kodni ko''rsating')}</i>"
        )

    # Кнопки действий
    kb = InlineKeyboardBuilder()

    if status in ("preparing", "ready"):
        # Активный заказ
        kb.button(
            text=_t(lang, "Получил заказ", "Buyurtmani oldim"),
            callback_data=f"myorder_received_b_{booking_id}",
        )

        # Показываем телефон магазина в тексте вместо кнопки (Telegram не поддерживает tel: URL)
        if data.get("store_phone"):
            lines.append("")
            lines.append(f"<b>{_t(lang, 'Телефон магазина', 'Do''kon telefoni')}:</b>")
            lines.append(f"<code>{data['store_phone']}</code>")

        kb.button(
            text=_t(lang, "Проблема", "Muammo"),
            callback_data=f"myorder_problem_b_{booking_id}",
        )

    elif status == "pending":
        kb.button(
            text=_t(lang, "Отменить", "Bekor qilish"),
            callback_data=f"cancel_booking_{booking_id}",
        )

    kb.button(text=_t(lang, "Назад", "Orqaga"), callback_data="myorders_back")

    kb.adjust(1)

    try:
        await callback.message.edit_text(_fmt(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(_fmt(lines), parse_mode="HTML", reply_markup=kb.as_markup())


async def _show_order_detail(callback: types.CallbackQuery, order_id: int, lang: str) -> None:
    """Показать детали заказа (orders table: pickup или delivery)."""
    user_id = callback.from_user.id

    # Получаем детали заказа
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    o.order_id,
                    o.order_type,
                    o.order_status,
                    o.pickup_code,
                    o.delivery_address,
                    o.total_price,
                    o.created_at,
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
            """,
                (order_id, user_id),
            )
            order = cursor.fetchone()
    except Exception as e:
        logger.error(f"Failed to get order {order_id}: {e}")
        await callback.message.answer(_t(lang, "Ошибка загрузки", "Yuklab bo'lmadi"))
        return

    if not order:
        await callback.message.answer(_t(lang, "Заказ не найден", "Buyurtma topilmadi"))
        return

    # Парсим данные (SQL возвращает tuple, нужен dict)
    # SELECT: order_id[0], order_type[1], order_status[2], pickup_code[3], delivery_address[4], total_price[5],
    #         created_at[6], quantity[7], store_name[8], store_address[9], store_phone[10], offer_title[11],
    #         discount_price[12], original_price[13], unit[14], is_cart_order[15], cart_items[16],
    #         delivery_price[17], item_title[18], item_price[19], item_original_price[20]
    if hasattr(order, "get"):
        data = order
    else:
        data = {
            "order_id": order[0],
            "order_type": order[1],
            "order_status": order[2],
            "pickup_code": order[3],
            "delivery_address": order[4],
            "total_price": order[5],
            "created_at": order[6],
            "quantity": order[7],
            "store_name": order[8],
            "store_address": order[9],
            "store_phone": order[10],
            "offer_title": order[11],
            "discount_price": order[12],
            "original_price": order[13],
            "unit": order[14],
            "is_cart_order": order[15] if len(order) > 15 else False,
            "cart_items": order[16] if len(order) > 16 else None,
            "delivery_price": order[17] if len(order) > 17 else None,
            "item_title": order[18] if len(order) > 18 else None,
            "item_price": order[19] if len(order) > 19 else None,
            "item_original_price": order[20] if len(order) > 20 else None,
        }

    raw_status = data.get("order_status", "pending")
    status = _normalize_status(raw_status)
    order_type = data.get("order_type") or ("delivery" if data.get("delivery_address") else "pickup")
    is_delivery = order_type == "delivery"
    status_label = _t(lang, "Статус", "Holat")
    emoji, status_text = _get_status_info(status, is_delivery, lang)

    # Формируем текст
    lines = []
    if is_delivery:
        lines.append(f"<b>{_t(lang, 'Доставка', 'Yetkazish')} #{data['order_id']}</b>")
    else:
        lines.append(f"<b>{_t(lang, 'Самовывоз', 'Olib ketish')} #{data['order_id']}</b>")
    lines.append(f"{status_label}: <b>{status_text}</b>")
    lines.append("")

    if is_delivery:
        # Адрес доставки
        if data.get("delivery_address"):
            lines.append(f"<b>{_t(lang, 'Адрес доставки', 'Yetkazish manzili')}:</b>")
            lines.append(f"{data['delivery_address']}")
            lines.append("")
    else:
        pickup_code = data.get("pickup_code")
        if pickup_code:
            lines.append(f"<b>{_t(lang, 'Код', 'Kod')}:</b> <code>{pickup_code}</code>")
            lines.append("")

    # Магазин
    lines.append(f"<b>{data.get('store_name', 'Магазин')}</b>")
    lines.append("")

    # Товары
    lines.append(f"<b>{_t(lang, 'Товары', 'Mahsulotlar')}:</b>")

    is_cart = data.get("is_cart_order")
    cart_items_json = data.get("cart_items")

    subtotal = 0
    if is_cart and cart_items_json:
        try:
            items = (
                json.loads(cart_items_json) if isinstance(cart_items_json, str) else cart_items_json
            )
            for item in items:
                title = item.get("title", "Товар")
                qty = item.get("quantity", 1)
                price = item.get("price", 0)
                item_total = price * qty
                subtotal += item_total
                lines.append(f"   • {title} × {qty} = {_format_price(item_total, lang)}")
        except Exception:
            lines.append(f"   • {_t(lang, 'Корзина товаров', 'Savat')}")
            subtotal = data.get("total_price", 0) - int(data.get("delivery_price") or 0)
    else:
        title = data.get("item_title") or data.get("offer_title", "Товар")
        qty = data.get("quantity", 1)
        price = data.get("item_price")
        if price is None:
            price = data.get("discount_price", 0)
        subtotal = int(price or 0) * int(qty or 1)
        lines.append(f"   • {title} × {qty} = {_format_price(subtotal, lang)}")

    # Итоги
    lines.append("")
    lines.append(f"{_t(lang, 'Товары', 'Mahsulotlar')}: {_format_price(subtotal, lang)}")

    total_price = data.get("total_price") or 0
    delivery_fee = 0
    if is_delivery:
        delivery_fee_raw = data.get("delivery_price")
        if delivery_fee_raw is None:
            try:
                delivery_fee = max(0, int(total_price) - int(subtotal))
            except Exception:
                delivery_fee = 0
        else:
            delivery_fee = int(delivery_fee_raw or 0)
        if delivery_fee > 0:
            lines.append(f"{_t(lang, 'Доставка', 'Yetkazish')}: {_format_price(delivery_fee, lang)}")

    total = total_price or (subtotal + delivery_fee)
    lines.append(f"<b>{_t(lang, 'Итого', 'Jami')}: {_format_price(total, lang)}</b>")

    # Курьер
    if status == "delivering" and data.get("courier_phone"):
        lines.append("")
        lines.append(f"<b>{_t(lang, 'Курьер', 'Kuryer')}:</b>")
        lines.append(f"{data['courier_phone']}")

    # Кнопки действий
    kb = InlineKeyboardBuilder()

    if is_delivery and status == "delivering":
        kb.button(
            text=_t(lang, "Получил заказ", "Buyurtmani oldim"),
            callback_data=f"myorder_received_o_{order_id}",
        )

        # Показываем телефон магазина для связи при доставке
        if data.get("store_phone"):
            lines.append("")
            lines.append(f"<b>{_t(lang, 'Телефон магазина', 'Do''kon telefoni')}:</b>")
            lines.append(f"<code>{data['store_phone']}</code>")

        kb.button(
            text=_t(lang, "Проблема с заказом", "Buyurtma muammosi"),
            callback_data=f"myorder_problem_o_{order_id}",
        )

    elif status in ("pending", "preparing", "ready"):
        # Показываем телефон магазина в тексте
        if data.get("store_phone"):
            lines.append("")
            lines.append(f"<b>{_t(lang, 'Телефон магазина', 'Do''kon telefoni')}:</b>")
            lines.append(f"<code>{data['store_phone']}</code>")

        if status == "pending":
            kb.button(
                text=_t(lang, "Отменить", "Bekor qilish"),
                callback_data=f"myorder_cancel_o_{order_id}",
            )
        elif not is_delivery and status == "ready":
            kb.button(
                text=_t(lang, "Получил заказ", "Buyurtmani oldim"),
                callback_data=f"myorder_received_o_{order_id}",
            )

    kb.button(text=_t(lang, "Назад", "Orqaga"), callback_data="myorders_back")

    kb.adjust(1)

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
        total = quantity * discount_price

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

