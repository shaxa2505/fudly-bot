"""
РРґРµР°Р»СЊРЅР°СЏ СЂРµР°Р»РёР·Р°С†РёСЏ Buyurtmalarim (РњРѕРё Р·Р°РєР°Р·С‹).

Р¤СѓРЅРєС†РёРѕРЅР°Р»:
1. РџРѕРєР°Р· Р°РєС‚РёРІРЅС‹С… Р·Р°РєР°Р·РѕРІ СЃ РїСЂРѕРіСЂРµСЃСЃРѕРј
2. Р”РµС‚Р°Р»СЊРЅС‹Р№ РїСЂРѕСЃРјРѕС‚СЂ Р·Р°РєР°Р·Р° (С‚РѕРІР°СЂС‹, С†РµРЅС‹, Р°РґСЂРµСЃ)
3. Р”РµР№СЃС‚РІРёСЏ: РџРѕР»СѓС‡РёР», РџРѕР·РІРѕРЅРёС‚СЊ РєСѓСЂСЊРµСЂСѓ, РџСЂРѕР±Р»РµРјР°
4. РСЃС‚РѕСЂРёСЏ Р·Р°РєР°Р·РѕРІ СЃ С„РёР»СЊС‚СЂР°РјРё
"""
from __future__ import annotations

import json
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.unified_order_service import OrderStatus, get_unified_order_service
from handlers.common.utils import is_my_orders_button

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
    "pending": {"emoji": "рџџЎ", "ru": "РћР¶РёРґР°РµС‚ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ", "uz": "Tasdiqlanishi kutilmoqda"},
    "preparing": {"emoji": "рџ‘ЁвЂЌрџЌі", "ru": "Р“РѕС‚РѕРІРёС‚СЃСЏ", "uz": "Tayyorlanmoqda"},
    "ready": {"emoji": "рџ“¦", "ru": "Р“РѕС‚РѕРІ", "uz": "Tayyor"},
    "delivering": {"emoji": "рџљљ", "ru": "РљСѓСЂСЊРµСЂ РІ РїСѓС‚Рё", "uz": "Kuryer yo'lda"},
    "completed": {"emoji": "вњ…", "ru": "Р—Р°РІРµСЂС€С‘РЅ", "uz": "Yakunlangan"},
    "rejected": {"emoji": "вќЊ", "ru": "РћС‚РєР»РѕРЅС‘РЅ", "uz": "Rad etilgan"},
    "cancelled": {"emoji": "вќЊ", "ru": "РћС‚РјРµРЅС‘РЅ", "uz": "Bekor qilingan"},
}

BOOKING_STATUSES = {
    "pending": {"emoji": "рџџЎ", "ru": "РћР¶РёРґР°РµС‚", "uz": "Kutilmoqda"},
    "preparing": {"emoji": "рџ‘ЁвЂЌрџЌі", "ru": "Р“РѕС‚РѕРІРёС‚СЃСЏ", "uz": "Tayyorlanmoqda"},
    "ready": {"emoji": "рџ“¦", "ru": "Р“РѕС‚РѕРІ", "uz": "Tayyor"},
    "completed": {"emoji": "вњ…", "ru": "Р—Р°РІРµСЂС€С‘РЅ", "uz": "Yakunlangan"},
    "rejected": {"emoji": "вќЊ", "ru": "РћС‚РєР»РѕРЅС‘РЅ", "uz": "Rad etilgan"},
    "cancelled": {"emoji": "вќЊ", "ru": "РћС‚РјРµРЅС‘РЅ", "uz": "Bekor qilingan"},
}


def _normalize_status(status: str | None) -> str:
    """Normalize legacy statuses to the fulfillment-only order_status model."""
    if not status:
        return OrderStatus.PENDING
    try:
        return OrderStatus.normalize(str(status))
    except Exception:
        return str(status)


def _get_status_info(status: str, is_delivery: bool, lang: str) -> tuple[str, str]:
    """Get status emoji and text."""
    statuses = ORDER_STATUSES if is_delivery else BOOKING_STATUSES
    status_norm = _normalize_status(status)
    info = statuses.get(status_norm, {"emoji": "вќ“", "ru": status_norm, "uz": status_norm})
    return info["emoji"], info.get(lang, info["ru"])


def _format_price(amount: int | float, lang: str) -> str:
    """Format price with currency."""
    currency = "СЃСѓРј" if lang == "ru" else "so'm"
    return f"{int(amount):,} {currency}".replace(",", " ")


# =============================================================================
# MY ORDERS MAIN HANDLER
# =============================================================================


@router.message(F.text.func(is_my_orders_button))
async def my_orders_handler(message: types.Message) -> None:
    """
    Р“Р»Р°РІРЅС‹Р№ СЌРєСЂР°РЅ "РњРѕРё Р·Р°РєР°Р·С‹".
    РџРѕРєР°Р·С‹РІР°РµС‚ Р°РєС‚РёРІРЅС‹Рµ Р·Р°РєР°Р·С‹ СЃ РєРЅРѕРїРєР°РјРё РґРµС‚Р°Р»РёР·Р°С†РёРё.
    """
    if not db:
        lang_code = (message.from_user.language_code or "ru") if message.from_user else "ru"
        if lang_code.startswith("uz"):
            text = "вќЊ Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring."
        else:
            text = "вќЊ РЎРµСЂРІРёСЃ РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РџРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ."
        await message.answer(text)
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    # РџРѕР»СѓС‡Р°РµРј bookings (СЃР°РјРѕРІС‹РІРѕР·) Рё orders (РґРѕСЃС‚Р°РІРєР°)
    bookings = db.get_user_bookings(user_id) or []
    try:
        orders = db.get_user_orders(user_id) or []
    except Exception:
        orders = []

    if not bookings and not orders:
        await _show_empty_orders(message, lang)
        return

    active_statuses = {"pending", "preparing", "ready", "delivering"}

    # Р Р°Р·РґРµР»СЏРµРј РїРѕ СЃС‚Р°С‚СѓСЃР°Рј (legacy bookings + unified orders)
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

    # РЎС‡С‘С‚С‡РёРєРё РґР»СЏ summary
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

    # в•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђ
    # РђРљРўРР’РќР«Р• Р—РђРљРђР—Р«
    # в•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђ
    if active_bookings or active_pickup_orders or active_delivery_orders:
        title = _t(lang, "рџ”Ґ РђРєС‚РёРІРЅС‹Рµ Р·Р°РєР°Р·С‹", "рџ”Ґ Faol buyurtmalar")
        text_lines.append(f"<b>{title}</b>\n")

        # РџРѕРєР°Р·С‹РІР°РµРј legacy bookings (СЃР°РјРѕРІС‹РІРѕР· РёР· С‚Р°Р±Р»РёС†С‹ bookings)
        for booking in active_bookings[:5]:
            booking_id = _get_field(booking, "booking_id")
            store_name = _get_field(booking, "name") or "РњР°РіР°Р·РёРЅ"  # name РІ dict, РЅРµ store_name
            status = _normalize_status(_get_field(booking, "status"))
            pickup_code = _get_field(booking, "booking_code")
            # Р’С‹С‡РёСЃР»СЏРµРј total РёР· quantity Г— discount_price
            quantity = _get_field(booking, "quantity") or 1
            discount_price = _get_field(booking, "discount_price") or 0
            total = quantity * discount_price

            emoji, status_text = _get_status_info(status, False, lang)

            text_lines.append(f"{emoji} <b>#{booking_id}</b> вЂў {store_name}")
            text_lines.append(
                f"   рџЏЄ {_t(lang, 'РЎР°РјРѕРІС‹РІРѕР·', 'Olib ketish')} вЂў {_format_price(total, lang)}"
            )
            if pickup_code:
                text_lines.append(f"   рџЋ« {_t(lang, 'РљРѕРґ', 'Kod')}: <code>{pickup_code}</code>")
            text_lines.append(f"   рџ“Љ {status_text}")
            text_lines.append("")

            # РљРЅРѕРїРєР° РґРµС‚Р°Р»РёР·Р°С†РёРё
            store_name_str = str(store_name) if store_name else "РњР°РіР°Р·РёРЅ"
            kb.button(
                text=f"рџ‘Ѓ #{booking_id} {store_name_str[:15]}",
                callback_data=f"myorder_detail_b_{booking_id}",
            )

        # РџРѕРєР°Р·С‹РІР°РµРј pickup orders РёР· С‚Р°Р±Р»РёС†С‹ orders (РЅРѕРІС‹Р№ СЃР°РјРѕРІС‹РІРѕР·)
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
            ) or "РњР°РіР°Р·РёРЅ"

            status = _normalize_status(_get_field(order, "order_status", 10))
            total = _get_field(order, "total_price", 5) or 0
            pickup_code = _get_field(order, "pickup_code")

            emoji, status_text = _get_status_info(status, False, lang)

            text_lines.append(f"{emoji} <b>#{order_id}</b> вЂў {store_name}")
            text_lines.append(
                f"   рџЏЄ {_t(lang, 'РЎР°РјРѕРІС‹РІРѕР·', 'Olib ketish')} вЂў {_format_price(total, lang)}"
            )
            if pickup_code:
                text_lines.append(f"   рџЋ« {_t(lang, 'РљРѕРґ', 'Kod')}: <code>{pickup_code}</code>")
            text_lines.append(f"   рџ“Љ {status_text}")
            text_lines.append("")

            store_name_str = str(store_name) if store_name else "РњР°РіР°Р·РёРЅ"
            kb.button(
                text=f"рџ‘Ѓ #{order_id} {store_name_str[:15]}",
                callback_data=f"myorder_detail_o_{order_id}",
            )

        # РџРѕРєР°Р·С‹РІР°РµРј delivery orders (РґРѕСЃС‚Р°РІРєР°)
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
            ) or "РњР°РіР°Р·РёРЅ"

            status = _normalize_status(_get_field(order, "order_status", 10))
            total = _get_field(order, "total_price", 5) or 0
            address = _get_field(order, "delivery_address", 4) or ""

            emoji, status_text = _get_status_info(status, True, lang)

            text_lines.append(f"{emoji} <b>#{order_id}</b> вЂў {store_name}")
            text_lines.append(
                f"   рџљљ {_t(lang, 'Р”РѕСЃС‚Р°РІРєР°', 'Yetkazish')} вЂў {_format_price(total, lang)}"
            )
            if address:
                short_addr = address[:30] + "..." if len(address) > 30 else address
                text_lines.append(f"   рџ“Ќ {short_addr}")
            text_lines.append(f"   рџ“Љ {status_text}")
            text_lines.append("")

            # РљРЅРѕРїРєР° РґРµС‚Р°Р»РёР·Р°С†РёРё
            store_name_str = str(store_name) if store_name else "РњР°РіР°Р·РёРЅ"
            kb.button(
                text=f"рџ‘Ѓ #{order_id} {store_name_str[:15]}",
                callback_data=f"myorder_detail_o_{order_id}",
            )

        kb.adjust(1)  # РџРѕ РѕРґРЅРѕР№ РєРЅРѕРїРєРµ РІ СЂСЏРґ
    else:
        # РќРµС‚ Р°РєС‚РёРІРЅС‹С…
        no_active = _t(lang, "вњ… Р’СЃРµ Р·Р°РєР°Р·С‹ РІС‹РїРѕР»РЅРµРЅС‹!", "вњ… Barcha buyurtmalar bajarildi!")
        text_lines.append(f"<b>{no_active}</b>\n")

    # в•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђ
    # SUMMARY + РРЎРўРћР РРЇ
    # в•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђ
    text_lines.append("в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ")

    completed_label = _t(lang, "Р—Р°РІРµСЂС€С‘РЅРЅС‹С…", "Yakunlangan")
    cancelled_label = _t(lang, "РћС‚РјРµРЅС‘РЅРЅС‹С…", "Bekor qilingan")
    text_lines.append(f"вњ… {completed_label}: <b>{total_completed}</b>")
    text_lines.append(f"вќЊ {cancelled_label}: <b>{total_cancelled}</b>")

    # РљРЅРѕРїРєРё С„РёР»СЊС‚СЂРѕРІ РёСЃС‚РѕСЂРёРё
    kb.button(
        text=f"вњ… {_t(lang, 'РСЃС‚РѕСЂРёСЏ Р·Р°РєР°Р·РѕРІ', 'Buyurtmalar tarixi')} ({total_completed})",
        callback_data="myorders_history_completed",
    )

    if total_cancelled > 0:
        kb.button(
            text=f"вќЊ {_t(lang, 'РћС‚РјРµРЅС‘РЅРЅС‹Рµ', 'Bekor qilingan')} ({total_cancelled})",
            callback_data="myorders_history_cancelled",
        )

    kb.adjust(1)

    await message.answer("\n".join(text_lines), parse_mode="HTML", reply_markup=kb.as_markup())


async def _show_empty_orders(message: types.Message, lang: str) -> None:
    """РџРѕРєР°Р·Р°С‚СЊ РїСѓСЃС‚РѕР№ СЌРєСЂР°РЅ Р·Р°РєР°Р·РѕРІ."""
    title = _t(lang, "рџ“‹ РњРѕРё Р·Р°РєР°Р·С‹", "рџ“‹ Mening buyurtmalarim")
    empty_text = _t(lang, "РЈ РІР°СЃ РїРѕРєР° РЅРµС‚ Р·Р°РєР°Р·РѕРІ", "Sizda hali buyurtmalar yo'q")
    hint = _t(
        lang,
        "РџРѕРїСЂРѕР±СѓР№С‚Рµ СЂР°Р·РґРµР» РђРєС†РёРё вЂ” С‚Р°Рј С‚РѕРІР°СЂС‹ СЃРѕ СЃРєРёРґРєР°РјРё РґРѕ 70%",
        "Aksiyalar bo'limini sinab ko'ring вЂ” u yerda 70% gacha chegirmalar",
    )

    kb = InlineKeyboardBuilder()
    kb.button(
        text=f"рџ”Ґ {_t(lang, 'РЎРјРѕС‚СЂРµС‚СЊ Р°РєС†РёРё', 'Aksiyalarni ko''rish')}", callback_data="hot_offers"
    )

    await message.answer(
        f"<b>{title}</b>\n\n{empty_text}\n\nрџ’Ў {hint}",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


# =============================================================================
# ORDER DETAIL VIEW
# =============================================================================


@router.callback_query(F.data.startswith("myorder_detail_"))
async def order_detail_handler(callback: types.CallbackQuery) -> None:
    """
    Р”РµС‚Р°Р»СЊРЅС‹Р№ РїСЂРѕСЃРјРѕС‚СЂ Р·Р°РєР°Р·Р°.
    РџРѕРєР°Р·С‹РІР°РµС‚: С‚РѕРІР°СЂС‹, С†РµРЅС‹, СЃС‚Р°С‚СѓСЃ, Р°РґСЂРµСЃ/РєРѕРґ, РєРЅРѕРїРєРё РґРµР№СЃС‚РІРёР№.
    """
    if not db or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Parse: myorder_detail_b_123 РёР»Рё myorder_detail_o_123
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("вќЊ Error")
        return

    order_type = parts[2]  # 'b' = booking, 'o' = order
    try:
        order_id = int(parts[3])
    except ValueError:
        await callback.answer("вќЊ Error")
        return

    if order_type == "b":
        await _show_booking_detail(callback, order_id, lang)
    else:
        await _show_order_detail(callback, order_id, lang)

    await callback.answer()


async def _show_booking_detail(callback: types.CallbackQuery, booking_id: int, lang: str) -> None:
    """РџРѕРєР°Р·Р°С‚СЊ РґРµС‚Р°Р»Рё Р±СЂРѕРЅРёСЂРѕРІР°РЅРёСЏ (СЃР°РјРѕРІС‹РІРѕР·)."""
    user_id = callback.from_user.id

    # РџРѕР»СѓС‡Р°РµРј РґРµС‚Р°Р»Рё Р±СЂРѕРЅРёСЂРѕРІР°РЅРёСЏ
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
        await callback.message.answer(_t(lang, "вќЊ РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё", "вќЊ Yuklab bo'lmadi"))
        return

    if not booking:
        await callback.message.answer(_t(lang, "вќЊ Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ", "вќЊ Buyurtma topilmadi"))
        return

    # РџР°СЂСЃРёРј РґР°РЅРЅС‹Рµ
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
            "total_price": quantity * discount_price,  # Р’С‹С‡РёСЃР»СЏРµРј
        }

    status = data.get("status", "pending")
    emoji, status_text = _get_status_info(status, False, lang)

    # Р¤РѕСЂРјРёСЂСѓРµРј С‚РµРєСЃС‚
    lines = []
    lines.append(f"<b>рџЏЄ {_t(lang, 'РЎР°РјРѕРІС‹РІРѕР·', 'Olib ketish')} #{data['booking_id']}</b>")
    lines.append(f"{emoji} <b>{status_text}</b>")
    lines.append("")

    # РњР°РіР°Р·РёРЅ
    lines.append(f"рџ“Ќ <b>{data.get('store_name', 'РњР°РіР°Р·РёРЅ')}</b>")
    if data.get("store_address"):
        lines.append(f"   {data['store_address']}")
    lines.append("")

    # РўРѕРІР°СЂС‹
    lines.append(f"<b>рџ“¦ {_t(lang, 'РўРѕРІР°СЂС‹', 'Mahsulotlar')}:</b>")

    # Bookings РІСЃРµРіРґР° РѕРґРёРЅРѕС‡РЅС‹Р№ С‚РѕРІР°СЂ (РЅРµ РєРѕСЂР·РёРЅР°)
    title = data.get("offer_title", "РўРѕРІР°СЂ") or "РўРѕРІР°СЂ"
    qty = data.get("quantity") or 1
    price = data.get("discount_price") or 0
    total = data.get("total_price") or (price * qty)
    lines.append(f"   вЂў {title} Г— {qty} = {_format_price(price * qty, lang)}")

    lines.append("")
    lines.append(f"рџ’° <b>{_t(lang, 'РС‚РѕРіРѕ', 'Jami')}:</b> {_format_price(total, lang)}")

    # РљРѕРґ РїРѕР»СѓС‡РµРЅРёСЏ
    if data.get("booking_code") and status in ("confirmed", "preparing"):
        lines.append("")
        lines.append(f"рџЋ« <b>{_t(lang, 'РљРѕРґ РїРѕР»СѓС‡РµРЅРёСЏ', 'Olish kodi')}:</b>")
        lines.append(f"<code>{data['booking_code']}</code>")
        lines.append(
            f"<i>{_t(lang, 'РџРѕРєР°Р¶РёС‚Рµ РєРѕРґ РїСЂРё РїРѕР»СѓС‡РµРЅРёРё', 'Olishda kodni ko''rsating')}</i>"
        )

    # РљРЅРѕРїРєРё РґРµР№СЃС‚РІРёР№
    kb = InlineKeyboardBuilder()

    if status in ("confirmed", "preparing"):
        # РђРєС‚РёРІРЅС‹Р№ Р·Р°РєР°Р·
        kb.button(
            text=f"вњ… {_t(lang, 'РџРѕР»СѓС‡РёР» Р·Р°РєР°Р·', 'Buyurtmani oldim')}",
            callback_data=f"myorder_received_b_{booking_id}",
        )

        # РџРѕРєР°Р·С‹РІР°РµРј С‚РµР»РµС„РѕРЅ РјР°РіР°Р·РёРЅР° РІ С‚РµРєСЃС‚Рµ РІРјРµСЃС‚Рѕ РєРЅРѕРїРєРё (Telegram РЅРµ РїРѕРґРґРµСЂР¶РёРІР°РµС‚ tel: URL)
        if data.get("store_phone"):
            lines.append("")
            lines.append(f"рџ“ћ <b>{_t(lang, 'РўРµР»РµС„РѕРЅ РјР°РіР°Р·РёРЅР°', 'Do''kon telefoni')}:</b>")
            lines.append(f"<code>{data['store_phone']}</code>")

        kb.button(
            text=f"вќ— {_t(lang, 'РџСЂРѕР±Р»РµРјР°', 'Muammo')}",
            callback_data=f"myorder_problem_b_{booking_id}",
        )

    elif status == "pending":
        kb.button(
            text=f"вќЊ {_t(lang, 'РћС‚РјРµРЅРёС‚СЊ', 'Bekor qilish')}",
            callback_data=f"cancel_booking_{booking_id}",
        )

    kb.button(text=f"в¬…пёЏ {_t(lang, 'РќР°Р·Р°Рґ', 'Orqaga')}", callback_data="myorders_back")

    kb.adjust(1)

    try:
        await callback.message.edit_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup()
        )
    except Exception:
        await callback.message.answer(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup()
        )


async def _show_order_detail(callback: types.CallbackQuery, order_id: int, lang: str) -> None:
    """РџРѕРєР°Р·Р°С‚СЊ РґРµС‚Р°Р»Рё Р·Р°РєР°Р·Р° (orders table: pickup РёР»Рё delivery)."""
    user_id = callback.from_user.id

    # РџРѕР»СѓС‡Р°РµРј РґРµС‚Р°Р»Рё Р·Р°РєР°Р·Р°
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
                    o.cart_items
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
        await callback.message.answer(_t(lang, "вќЊ РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё", "вќЊ Yuklab bo'lmadi"))
        return

    if not order:
        await callback.message.answer(_t(lang, "вќЊ Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ", "вќЊ Buyurtma topilmadi"))
        return

    # РџР°СЂСЃРёРј РґР°РЅРЅС‹Рµ (SQL РІРѕР·РІСЂР°С‰Р°РµС‚ tuple, РЅСѓР¶РµРЅ dict)
    # SELECT: order_id[0], order_type[1], order_status[2], pickup_code[3], delivery_address[4], total_price[5],
    #         created_at[6], quantity[7], store_name[8], store_address[9], store_phone[10], offer_title[11],
    #         discount_price[12], original_price[13], unit[14], is_cart_order[15], cart_items[16]
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
        }

    raw_status = data.get("order_status", "pending")
    status = _normalize_status(raw_status)
    order_type = data.get("order_type") or ("delivery" if data.get("delivery_address") else "pickup")
    is_delivery = order_type == "delivery"
    emoji, status_text = _get_status_info(status, is_delivery, lang)

    # Р¤РѕСЂРјРёСЂСѓРµРј С‚РµРєСЃС‚
    lines = []
    if is_delivery:
        lines.append(f"<b>рџљљ {_t(lang, 'Р”РѕСЃС‚Р°РІРєР°', 'Yetkazish')} #{data['order_id']}</b>")
    else:
        lines.append(f"<b>рџЏЄ {_t(lang, 'РЎР°РјРѕРІС‹РІРѕР·', 'Olib ketish')} #{data['order_id']}</b>")
    lines.append(f"{emoji} <b>{status_text}</b>")
    lines.append("")

    if is_delivery:
        # РђРґСЂРµСЃ РґРѕСЃС‚Р°РІРєРё
        if data.get("delivery_address"):
            lines.append(f"рџ“Ќ <b>{_t(lang, 'РђРґСЂРµСЃ РґРѕСЃС‚Р°РІРєРё', 'Yetkazish manzili')}:</b>")
            lines.append(f"   {data['delivery_address']}")
            lines.append("")
    else:
        pickup_code = data.get("pickup_code")
        if pickup_code:
            lines.append(f"рџЋ« <b>{_t(lang, 'РљРѕРґ', 'Kod')}:</b> <code>{pickup_code}</code>")
            lines.append("")

    # РњР°РіР°Р·РёРЅ
    lines.append(f"рџЏЄ <b>{data.get('store_name', 'РњР°РіР°Р·РёРЅ')}</b>")
    lines.append("")

    # РўРѕРІР°СЂС‹
    lines.append(f"<b>рџ“¦ {_t(lang, 'РўРѕРІР°СЂС‹', 'Mahsulotlar')}:</b>")

    is_cart = data.get("is_cart_order")
    cart_items_json = data.get("cart_items")

    subtotal = 0
    if is_cart and cart_items_json:
        try:
            items = (
                json.loads(cart_items_json) if isinstance(cart_items_json, str) else cart_items_json
            )
            for item in items:
                title = item.get("title", "РўРѕРІР°СЂ")
                qty = item.get("quantity", 1)
                price = item.get("price", 0)
                item_total = price * qty
                subtotal += item_total
                lines.append(f"   вЂў {title} Г— {qty} = {_format_price(item_total, lang)}")
        except Exception:
            lines.append(f"   вЂў {_t(lang, 'РљРѕСЂР·РёРЅР° С‚РѕРІР°СЂРѕРІ', 'Savat')}")
            subtotal = data.get("total_price", 0) - (data.get("delivery_fee", 0) or 0)
    else:
        title = data.get("offer_title", "РўРѕРІР°СЂ")
        qty = data.get("quantity", 1)
        price = data.get("discount_price", 0)
        subtotal = price * qty
        lines.append(f"   вЂў {title} Г— {qty} = {_format_price(subtotal, lang)}")

    # РС‚РѕРіРё
    lines.append("")
    lines.append(f"рџ’° {_t(lang, 'РўРѕРІР°СЂС‹', 'Mahsulotlar')}: {_format_price(subtotal, lang)}")

    total_price = data.get("total_price") or 0
    delivery_fee = 0
    if is_delivery:
        try:
            delivery_fee = max(0, int(total_price) - int(subtotal))
        except Exception:
            delivery_fee = 0
        if delivery_fee > 0:
            lines.append(f"рџљљ {_t(lang, 'Р”РѕСЃС‚Р°РІРєР°', 'Yetkazish')}: {_format_price(delivery_fee, lang)}")

    total = total_price or (subtotal + delivery_fee)
    lines.append(f"<b>рџ’µ {_t(lang, 'РС‚РѕРіРѕ', 'Jami')}: {_format_price(total, lang)}</b>")

    # РљСѓСЂСЊРµСЂ
    if status == "delivering" and data.get("courier_phone"):
        lines.append("")
        lines.append(f"рџЏЌ <b>{_t(lang, 'РљСѓСЂСЊРµСЂ', 'Kuryer')}:</b>")
        lines.append(f"   рџ“± {data['courier_phone']}")

    # РљРЅРѕРїРєРё РґРµР№СЃС‚РІРёР№
    kb = InlineKeyboardBuilder()

    if is_delivery and status == "delivering":
        kb.button(
            text=f"вњ… {_t(lang, 'РџРѕР»СѓС‡РёР» Р·Р°РєР°Р·', 'Buyurtmani oldim')}",
            callback_data=f"myorder_received_o_{order_id}",
        )

        # РџРѕРєР°Р·С‹РІР°РµРј С‚РµР»РµС„РѕРЅ РјР°РіР°Р·РёРЅР° РґР»СЏ СЃРІСЏР·Рё РїСЂРё РґРѕСЃС‚Р°РІРєРµ
        if data.get("store_phone"):
            lines.append("")
            lines.append(f"рџ“ћ <b>{_t(lang, 'РўРµР»РµС„РѕРЅ РјР°РіР°Р·РёРЅР°', 'Do''kon telefoni')}:</b>")
            lines.append(f"<code>{data['store_phone']}</code>")

        kb.button(
            text=f"вќ— {_t(lang, 'РџСЂРѕР±Р»РµРјР° СЃ Р·Р°РєР°Р·РѕРј', 'Buyurtma muammosi')}",
            callback_data=f"myorder_problem_o_{order_id}",
        )

    elif status in ("pending", "preparing", "ready"):
        # РџРѕРєР°Р·С‹РІР°РµРј С‚РµР»РµС„РѕРЅ РјР°РіР°Р·РёРЅР° РІ С‚РµРєСЃС‚Рµ
        if data.get("store_phone"):
            lines.append("")
            lines.append(f"рџ“ћ <b>{_t(lang, 'РўРµР»РµС„РѕРЅ РјР°РіР°Р·РёРЅР°', 'Do''kon telefoni')}:</b>")
            lines.append(f"<code>{data['store_phone']}</code>")

        if status == "pending":
            kb.button(
                text=f"вќЊ {_t(lang, 'РћС‚РјРµРЅРёС‚СЊ', 'Bekor qilish')}",
                callback_data=f"myorder_cancel_o_{order_id}",
            )
        elif not is_delivery and status == "ready":
            kb.button(
                text=f"вњ… {_t(lang, 'РџРѕР»СѓС‡РёР» Р·Р°РєР°Р·', 'Buyurtmani oldim')}",
                callback_data=f"myorder_received_o_{order_id}",
            )

    kb.button(text=f"в¬…пёЏ {_t(lang, 'РќР°Р·Р°Рґ', 'Orqaga')}", callback_data="myorders_back")

    kb.adjust(1)

    try:
        await callback.message.edit_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup()
        )
    except Exception:
        await callback.message.answer(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup()
        )


# =============================================================================
# ORDER ACTIONS
# =============================================================================


@router.callback_query(F.data.startswith("myorder_received_"))
async def order_received_handler(callback: types.CallbackQuery) -> None:
    """РљР»РёРµРЅС‚ РїРѕРґС‚РІРµСЂРґРёР» РїРѕР»СѓС‡РµРЅРёРµ Р·Р°РєР°Р·Р°."""
    if not db or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("вќЊ Error")
        return

    order_type = parts[2]  # 'b' or 'o'
    try:
        order_id = int(parts[3])
    except ValueError:
        await callback.answer("вќЊ Error")
        return

    try:
        entity = None
        if order_type == "b":
            entity = db.get_booking(order_id) if hasattr(db, "get_booking") else None
        else:
            entity = db.get_order(order_id) if hasattr(db, "get_order") else None

        if not entity:
            await callback.answer(_t(lang, "вќЊ Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ", "вќЊ Buyurtma topilmadi"), show_alert=True)
            return

        entity_user_id = entity.get("user_id") if hasattr(entity, "get") else _get_field(entity, 2)
        if entity_user_id != user_id:
            await callback.answer(_t(lang, "вќЊ Р”РѕСЃС‚СѓРї Р·Р°РїСЂРµС‰РµРЅ", "вќЊ Ruxsat yo'q"), show_alert=True)
            return

        service = get_unified_order_service()
        if not service:
            await callback.answer(_t(lang, "вќЊ РћС€РёР±РєР°", "вќЊ Xatolik"), show_alert=True)
            return

        entity_type = "booking" if order_type == "b" else "order"
        success = await service.complete_order(order_id, entity_type)
        if not success:
            await callback.answer(_t(lang, "вќЊ РћС€РёР±РєР°", "вќЊ Xatolik"), show_alert=True)
            return

        await callback.answer(
            _t(lang, "вњ… РЎРїР°СЃРёР±Рѕ! Р—Р°РєР°Р· Р·Р°РІРµСЂС€С‘РЅ", "вњ… Rahmat! Buyurtma yakunlandi"),
            show_alert=True,
        )

        # РџРѕРєР°Р·С‹РІР°РµРј СЌРєСЂР°РЅ СЂРµР№С‚РёРЅРіР°
        kb = InlineKeyboardBuilder()
        kb.button(text="в­ђв­ђв­ђв­ђв­ђ", callback_data=f"myorder_rate_{order_type}_{order_id}_5")
        kb.button(text="в­ђв­ђв­ђв­ђ", callback_data=f"myorder_rate_{order_type}_{order_id}_4")
        kb.button(text="в­ђв­ђв­ђ", callback_data=f"myorder_rate_{order_type}_{order_id}_3")
        kb.button(
            text=f"в¬…пёЏ {_t(lang, 'РџСЂРѕРїСѓСЃС‚РёС‚СЊ', 'O''tkazib yuborish')}", callback_data="myorders_back"
        )
        kb.adjust(1)

        await callback.message.edit_text(
            f"<b>{_t(lang, 'РћС†РµРЅРёС‚Рµ Р·Р°РєР°Р·', 'Buyurtmani baholang')}</b>\n\n"
            f"{_t(lang, 'РљР°Рє РІР°Рј РєР°С‡РµСЃС‚РІРѕ С‚РѕРІР°СЂРѕРІ Рё РѕР±СЃР»СѓР¶РёРІР°РЅРёРµ?', 'Mahsulotlar sifati va xizmat qanday bo''ldi?')}",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )

    except Exception as e:
        logger.error(f"Failed to complete order {order_id}: {e}")
        await callback.answer(_t(lang, "вќЊ РћС€РёР±РєР°", "вќЊ Xatolik"), show_alert=True)


@router.callback_query(F.data.startswith("myorder_rate_"))
async def order_rate_handler(callback: types.CallbackQuery) -> None:
    """РљР»РёРµРЅС‚ РѕС†РµРЅРёР» Р·Р°РєР°Р·."""
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

    # РЎРѕС…СЂР°РЅСЏРµРј СЂРµР№С‚РёРЅРі (РµСЃР»Рё РµСЃС‚СЊ С‚Р°РєР°СЏ С„СѓРЅРєС†РёСЏ)
    try:
        if hasattr(db, "add_order_rating"):
            db.add_order_rating(order_id, user_id, rating)
    except Exception as e:
        logger.warning(f"Failed to save rating: {e}")

    await callback.answer(_t(lang, "вњ… РЎРїР°СЃРёР±Рѕ Р·Р° РѕС†РµРЅРєСѓ!", "вњ… Baholaganingiz uchun rahmat!"))

    # Р’РѕР·РІСЂР°С‰Р°РµРјСЃСЏ Рє СЃРїРёСЃРєСѓ Р·Р°РєР°Р·РѕРІ
    await callback.message.delete()


@router.callback_query(F.data.startswith("myorder_problem_"))
async def order_problem_handler(callback: types.CallbackQuery) -> None:
    """РљР»РёРµРЅС‚ СЃРѕРѕР±С‰Р°РµС‚ Рѕ РїСЂРѕР±Р»РµРјРµ СЃ Р·Р°РєР°Р·РѕРј."""
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

    # РџРѕРєР°Р·С‹РІР°РµРј РѕРїС†РёРё РїСЂРѕР±Р»РµРј
    kb = InlineKeyboardBuilder()

    problems = [
        ("late", _t(lang, "вЏ° Р”РѕР»РіР°СЏ РґРѕСЃС‚Р°РІРєР°", "вЏ° Uzoq yetkazish")),
        ("wrong", _t(lang, "вќЊ РќРµРїСЂР°РІРёР»СЊРЅС‹Р№ Р·Р°РєР°Р·", "вќЊ Noto'g'ri buyurtma")),
        ("quality", _t(lang, "рџ‘Ћ РљР°С‡РµСЃС‚РІРѕ С‚РѕРІР°СЂР°", "рџ‘Ћ Mahsulot sifati")),
        ("other", _t(lang, "рџ’¬ Р”СЂСѓРіРѕРµ", "рџ’¬ Boshqa")),
    ]

    for code, text in problems:
        kb.button(text=text, callback_data=f"myorder_report_{order_type}_{order_id}_{code}")

    kb.button(
        text=f"в¬…пёЏ {_t(lang, 'РќР°Р·Р°Рґ', 'Orqaga')}",
        callback_data=f"myorder_detail_{order_type}_{order_id}",
    )
    kb.adjust(1)

    await callback.message.edit_text(
        f"<b>{_t(lang, 'Р’С‹Р±РµСЂРёС‚Рµ С‚РёРї РїСЂРѕР±Р»РµРјС‹', 'Muammo turini tanlang')}</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("myorder_report_"))
async def order_report_handler(callback: types.CallbackQuery) -> None:
    """РЎРѕС…СЂР°РЅРµРЅРёРµ Р¶Р°Р»РѕР±С‹ РЅР° Р·Р°РєР°Р·."""
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

    # Р›РѕРіРёСЂСѓРµРј Р¶Р°Р»РѕР±Сѓ (РјРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ С‚Р°Р±Р»РёС†Сѓ complaints)
    logger.info(
        f"User {user_id} reported problem '{problem_code}' for order {order_type}_{order_id}"
    )

    # РЈРІРµРґРѕРјР»РµРЅРёРµ Р°РґРјРёРЅСѓ
    try:
        admin_ids = db.get_admin_ids() if hasattr(db, "get_admin_ids") else []
        for admin_id in admin_ids[:3]:  # Max 3 admins
            try:
                await bot.send_message(
                    admin_id,
                    f"вљ пёЏ <b>Р–Р°Р»РѕР±Р° РЅР° Р·Р°РєР°Р· #{order_id}</b>\n\n"
                    f"РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ: {user_id}\n"
                    f"РўРёРї: {'Р”РѕСЃС‚Р°РІРєР°' if order_type == 'o' else 'РЎР°РјРѕРІС‹РІРѕР·'}\n"
                    f"РџСЂРѕР±Р»РµРјР°: {problem_code}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    except Exception:
        pass

    await callback.answer(
        _t(
            lang,
            "вњ… Р–Р°Р»РѕР±Р° РѕС‚РїСЂР°РІР»РµРЅР°. РњС‹ СЃРІСЏР¶РµРјСЃСЏ СЃ РІР°РјРё!",
            "вњ… Shikoyat yuborildi. Siz bilan bog'lanamiz!",
        ),
        show_alert=True,
    )

    # Р’РѕР·РІСЂР°С‰Р°РµРјСЃСЏ Рє СЃРїРёСЃРєСѓ
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("myorder_cancel_o_"))
async def order_cancel_handler(callback: types.CallbackQuery) -> None:
    """РћС‚РјРµРЅР° Р·Р°РєР°Р·Р° РїРѕР»СЊР·РѕРІР°С‚РµР»РµРј."""
    if not db or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("вќЊ Error")
        return

    # РџСЂРѕРІРµСЂСЏРµРј СЃС‚Р°С‚СѓСЃ - РјРѕР¶РЅРѕ РѕС‚РјРµРЅРёС‚СЊ С‚РѕР»СЊРєРѕ pending
    try:
        order = db.get_order(order_id)
        if not order:
            await callback.answer(_t(lang, "вќЊ Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ", "вќЊ Buyurtma topilmadi"))
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
                    "вљ пёЏ Р—Р°РєР°Р· СѓР¶Рµ РѕР±СЂР°Р±Р°С‚С‹РІР°РµС‚СЃСЏ, РѕС‚РјРµРЅРёС‚СЊ РЅРµР»СЊР·СЏ",
                    "вљ пёЏ Buyurtma qayta ishlanmoqda, bekor qilib bo'lmaydi",
                ),
                show_alert=True,
            )
            return

        service = get_unified_order_service()
        if not service:
            await callback.answer(_t(lang, "вќЊ РћС€РёР±РєР°", "вќЊ Xatolik"), show_alert=True)
            return

        success = await service.cancel_order(order_id, "order")
        if not success:
            await callback.answer(_t(lang, "вќЊ РћС€РёР±РєР°", "вќЊ Xatolik"), show_alert=True)
            return

        await callback.answer(
            _t(lang, "вњ… Р—Р°РєР°Р· РѕС‚РјРµРЅС‘РЅ", "вњ… Buyurtma bekor qilindi"), show_alert=True
        )

        # РЈРґР°Р»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ Рё РІРѕР·РІСЂР°С‰Р°РµРјСЃСЏ
        try:
            await callback.message.delete()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Failed to cancel order {order_id}: {e}")
        await callback.answer(_t(lang, "вќЊ РћС€РёР±РєР°", "вќЊ Xatolik"), show_alert=True)


# =============================================================================
# HISTORY
# =============================================================================


@router.callback_query(F.data.startswith("myorders_history_"))
async def orders_history_handler(callback: types.CallbackQuery) -> None:
    """РџРѕРєР°Р·Р°С‚СЊ РёСЃС‚РѕСЂРёСЋ Р·Р°РєР°Р·РѕРІ РїРѕ С„РёР»СЊС‚СЂСѓ."""
    if not db or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    status_filter = callback.data.replace("myorders_history_", "")

    # РџРѕР»СѓС‡Р°РµРј Р·Р°РєР°Р·С‹ СЃ РЅСѓР¶РЅС‹Рј СЃС‚Р°С‚СѓСЃРѕРј
    bookings = db.get_user_bookings(user_id) or []
    try:
        orders = db.get_user_orders(user_id) or []
    except Exception:
        orders = []

    # Р¤РёР»СЊС‚СЂСѓРµРј
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
        await callback.answer(_t(lang, "рџ“­ РќРµС‚ Р·Р°РєР°Р·РѕРІ", "рџ“­ Buyurtmalar yo'q"))
        return

    lines = []
    title = (
        _t(lang, "Р—Р°РІРµСЂС€С‘РЅРЅС‹Рµ Р·Р°РєР°Р·С‹", "Yakunlangan buyurtmalar")
        if status_filter == "completed"
        else _t(lang, "РћС‚РјРµРЅС‘РЅРЅС‹Рµ Р·Р°РєР°Р·С‹", "Bekor qilingan buyurtmalar")
    )
    lines.append(f"<b>рџ“‹ {title}</b>\n")

    kb = InlineKeyboardBuilder()

    # Bookings
    for b in filtered_bookings[:10]:
        booking_id = _get_field(b, "booking_id")
        store_name = _get_field(b, "name") or "РњР°РіР°Р·РёРЅ"  # name РІ dict, РЅРµ store_name
        # Р’С‹С‡РёСЃР»СЏРµРј total
        quantity = _get_field(b, "quantity") or 1
        discount_price = _get_field(b, "discount_price") or 0
        total = quantity * discount_price

        emoji = "вњ…" if status_filter == "completed" else "вќЊ"
        lines.append(f"{emoji} <b>#{booking_id}</b> вЂў {store_name}")
        lines.append(f"   рџЏЄ {_t(lang, 'РЎР°РјРѕРІС‹РІРѕР·', 'Olib ketish')} вЂў {_format_price(total, lang)}")
        lines.append("")

        kb.button(text=f"рџ”„ #{booking_id}", callback_data=f"repeat_order_b_{booking_id}")

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
        ) or "РњР°РіР°Р·РёРЅ"
        total = _get_field(o, "total_price", 5) or 0
        order_type = _get_field(o, "order_type") or ("delivery" if _get_field(o, "delivery_address") else "pickup")

        emoji = "вњ…" if status_filter == "completed" else "вќЊ"
        lines.append(f"{emoji} <b>#{order_id}</b> вЂў {store_name}")
        if order_type == "delivery":
            lines.append(
                f"   рџљљ {_t(lang, 'Р”РѕСЃС‚Р°РІРєР°', 'Yetkazish')} вЂў {_format_price(total, lang)}"
            )
        else:
            lines.append(
                f"   рџЏЄ {_t(lang, 'РЎР°РјРѕРІС‹РІРѕР·', 'Olib ketish')} вЂў {_format_price(total, lang)}"
            )
        lines.append("")

        kb.button(text=f"рџ”„ #{order_id}", callback_data=f"repeat_order_o_{order_id}")

    kb.button(text=f"в¬…пёЏ {_t(lang, 'РќР°Р·Р°Рґ', 'Orqaga')}", callback_data="myorders_back")
    kb.adjust(5, 1)  # 5 repeat buttons per row, then back

    try:
        await callback.message.edit_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup()
        )
    except Exception:
        await callback.message.answer(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup()
        )

    await callback.answer()


@router.callback_query(F.data == "myorders_back")
async def myorders_back_handler(callback: types.CallbackQuery) -> None:
    """Р’РµСЂРЅСѓС‚СЊСЃСЏ Рє СЃРїРёСЃРєСѓ Р·Р°РєР°Р·РѕРІ."""
    if not db:
        await callback.answer()
        return

    # РЎРѕР·РґР°С‘Рј С„РµР№РєРѕРІС‹Р№ message РґР»СЏ РІС‹Р·РѕРІР° РіР»Р°РІРЅРѕРіРѕ С…РµРЅРґР»РµСЂР°
    # РЈРґР°Р»СЏРµРј С‚РµРєСѓС‰РµРµ СЃРѕРѕР±С‰РµРЅРёРµ Рё РѕС‚РїСЂР°РІР»СЏРµРј РЅРѕРІРѕРµ
    try:
        await callback.message.delete()
    except Exception:
        pass

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # РЎРѕР·РґР°С‘Рј РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ С‡РµСЂРµР· РіР»Р°РІРЅС‹Р№ С…РµРЅРґР»РµСЂ
    # РСЃРїРѕР»СЊР·СѓРµРј callback.message РєР°Рє base
    fake_message = callback.message
    fake_message.text = "рџ“‹ РњРѕРё Р·Р°РєР°Р·С‹" if lang == "ru" else "рџ“‹ Buyurtmalarim"

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

