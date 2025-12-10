"""Seller order management - unified with new notification system.

Shows all orders/bookings in ONE message with inline pagination.
Uses UnifiedOrderService for status changes and notifications.
"""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.unified_order_service import get_unified_order_service
from localization import get_text
from logging_config import logger

from .utils import get_db, get_store_field

router = Router()


def _get_field(entity: Any, field: str, default: Any = None) -> Any:
    """Safely get field from dict or object."""
    if isinstance(entity, dict):
        return entity.get(field, default)
    return getattr(entity, field, default)


def _format_order_line(item: Any, is_booking: bool, lang: str, idx: int) -> str:
    """Format single order/booking as one line for list."""
    if is_booking:
        booking_id = _get_field(item, "booking_id") or (
            item[0] if isinstance(item, (list, tuple)) else 0
        )
        status = _get_field(item, "status") or (
            item[3] if isinstance(item, (list, tuple)) and len(item) > 3 else "pending"
        )
        title = _get_field(item, "title") or "Товар"
        quantity = _get_field(item, "quantity") or 1

        status_emoji = {
            "pending": "⏳",
            "confirmed": "✅",
            "preparing": "👨‍🍳",
            "completed": "🎉",
            "cancelled": "❌",
        }.get(status, "📦")
        return f"{idx}. {status_emoji} 🏪 #{booking_id} • {title[:20]} ×{quantity}"
    else:
        order_id = _get_field(item, "order_id") or (
            item[0] if isinstance(item, (list, tuple)) else 0
        )
        status = _get_field(item, "order_status") or (
            item[10] if isinstance(item, (list, tuple)) and len(item) > 10 else "pending"
        )
        title = _get_field(item, "title") or "Товар"
        quantity = _get_field(item, "quantity") or 1

        status_emoji = {
            "pending": "⏳",
            "preparing": "👨‍🍳",
            "ready": "📦",
            "delivering": "🚚",
            "completed": "🎉",
            "cancelled": "❌",
        }.get(status, "📦")
        return f"{idx}. {status_emoji} 🚚 #{order_id} • {title[:20]} ×{quantity}"


def _build_list_text(bookings: list, orders: list, lang: str, filter_type: str = "all") -> str:
    """Build orders list text."""
    lines = []

    if filter_type == "pending":
        header = "⏳ YANGI BUYURTMALAR" if lang == "uz" else "⏳ НОВЫЕ ЗАКАЗЫ"
    elif filter_type == "active":
        header = "✅ FAOL BUYURTMALAR" if lang == "uz" else "✅ АКТИВНЫЕ ЗАКАЗЫ"
    elif filter_type == "completed":
        header = "🎉 BAJARILGAN" if lang == "uz" else "🎉 ВЫПОЛНЕННЫЕ"
    else:
        header = "🎫 BUYURTMALAR" if lang == "uz" else "🎫 ЗАКАЗЫ"

    lines.append(f"<b>{header}</b>")
    lines.append("")

    pickup_label = "Olib ketish" if lang == "uz" else "Самовывоз"
    delivery_label = "Yetkazish" if lang == "uz" else "Доставка"
    lines.append(f"🏪 {pickup_label}: <b>{len(bookings)}</b>")
    lines.append(f"🚚 {delivery_label}: <b>{len(orders)}</b>")
    lines.append("─" * 25)

    idx = 1
    for b in bookings[:5]:
        lines.append(_format_order_line(b, True, lang, idx))
        idx += 1

    for o in orders[:5]:
        lines.append(_format_order_line(o, False, lang, idx))
        idx += 1

    if not bookings and not orders:
        empty = "Buyurtmalar yo'q" if lang == "uz" else "Заказов нет"
        lines.append(f"\n<i>{empty}</i>")
    else:
        hint = "Tanlang:" if lang == "uz" else "Выберите:"
        lines.append(f"\n<i>👆 {hint}</i>")

    return "\n".join(lines)


def _build_keyboard(
    bookings: list, orders: list, lang: str, filter_type: str = "all"
) -> InlineKeyboardBuilder:
    """Build keyboard with order buttons and filters."""
    kb = InlineKeyboardBuilder()

    for b in bookings[:5]:
        booking_id = _get_field(b, "booking_id") or (b[0] if isinstance(b, (list, tuple)) else 0)
        status = _get_field(b, "status") or "pending"
        emoji = {"pending": "⏳", "confirmed": "✅", "preparing": "👨‍🍳"}.get(status, "📦")
        kb.button(text=f"{emoji} 🏪#{booking_id}", callback_data=f"seller_view_b_{booking_id}")

    for o in orders[:5]:
        order_id = _get_field(o, "order_id") or (o[0] if isinstance(o, (list, tuple)) else 0)
        status = _get_field(o, "order_status") or "pending"
        emoji = {"pending": "⏳", "preparing": "👨‍🍳", "delivering": "🚚"}.get(status, "📦")
        kb.button(text=f"{emoji} 🚚#{order_id}", callback_data=f"seller_view_o_{order_id}")

    kb.adjust(2)

    filter_row = []
    new_label = "⏳ Yangi" if lang == "uz" else "⏳ Новые"
    active_label = "✅ Faol" if lang == "uz" else "✅ Активные"
    done_label = "🎉 Tayyor" if lang == "uz" else "🎉 Готовые"

    if filter_type != "pending":
        filter_row.append(("seller_filter_pending", new_label))
    if filter_type != "active":
        filter_row.append(("seller_filter_active", active_label))
    if filter_type != "completed":
        filter_row.append(("seller_filter_completed", done_label))

    for cb, text in filter_row:
        kb.button(text=text, callback_data=cb)

    kb.adjust(2, 3)

    refresh = "🔄 Yangilash" if lang == "uz" else "🔄 Обновить"
    kb.button(text=refresh, callback_data="seller_orders_refresh")
    kb.adjust(2, 3, 1)

    return kb


def _filter_by_status(items: list, statuses: list, is_booking: bool) -> list:
    """Filter items by status."""
    result = []
    for item in items:
        if is_booking:
            status = _get_field(item, "status") or (
                item[3] if isinstance(item, (list, tuple)) and len(item) > 3 else None
            )
        else:
            status = _get_field(item, "order_status") or (
                item[10] if isinstance(item, (list, tuple)) and len(item) > 10 else None
            )
        if status in statuses:
            result.append(item)
    return result


def _get_all_orders(db, user_id: int) -> tuple[list, list]:
    """Get all bookings and orders for seller's stores."""
    stores = db.get_user_accessible_stores(user_id) or []

    all_bookings = []
    all_orders = []

    for store in stores:
        store_id = get_store_field(store, "store_id")
        if not store_id:
            continue

        bookings = db.get_store_bookings(store_id) or []
        all_bookings.extend(bookings)

        orders = db.get_store_orders(store_id) or []
        all_orders.extend(orders)

    return all_bookings, all_orders


# =============================================================================
# MAIN VIEW
# =============================================================================


@router.message(F.text.contains("🎫 Заказы продавца") | F.text.contains("Buyurtmalar (sotuvchi)"))
async def seller_orders_main(message: types.Message, state: FSMContext) -> Any:
    """Main seller orders view - single message."""
    db = get_db()

    await state.clear()

    try:
        stores = db.get_user_accessible_stores(message.from_user.id)
        if not stores:
            raise ValueError("No stores")
    except Exception as e:
        # If seller has no accessible stores, show a friendly message instead of failing silently.
        logger.debug(f"seller_orders skipped: {e}")
        try:
            lang = db.get_user_language(message.from_user.id)
        except Exception:
            lang = "ru"

        if lang == "uz":
            text = (
                "Sizda hali tasdiqlangan do'kon yo'q.\n"
                "Hamkor sifatida buyurtmalarni boshqarish uchun profil bo'limida ro'yxatdan o'tishni yakunlang."
            )
        else:
            text = (
                "У вас пока нет одобренного магазина.\n"
                "Чтобы управлять заказами как партнёр, завершите регистрацию в разделе профиля."
            )

        await message.answer(text)
        return

    lang = db.get_user_language(message.from_user.id)
    all_bookings, all_orders = _get_all_orders(db, message.from_user.id)

    pending_bookings = _filter_by_status(all_bookings, ["pending"], True)
    pending_orders = _filter_by_status(all_orders, ["pending", "preparing"], False)

    text = _build_list_text(pending_bookings, pending_orders, lang, "pending")
    kb = _build_keyboard(pending_bookings, pending_orders, lang, "pending")

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "seller_orders_refresh")
async def seller_orders_refresh(callback: types.CallbackQuery) -> None:
    """Refresh orders list."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    all_bookings, all_orders = _get_all_orders(db, callback.from_user.id)
    pending_bookings = _filter_by_status(all_bookings, ["pending"], True)
    pending_orders = _filter_by_status(all_orders, ["pending", "preparing"], False)

    text = _build_list_text(pending_bookings, pending_orders, lang, "pending")
    kb = _build_keyboard(pending_bookings, pending_orders, lang, "pending")

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass

    await callback.answer("🔄")


# =============================================================================
# FILTERS
# =============================================================================


@router.callback_query(F.data == "seller_filter_pending")
async def seller_filter_pending(callback: types.CallbackQuery) -> None:
    """Show pending orders."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    all_bookings, all_orders = _get_all_orders(db, callback.from_user.id)
    filtered_bookings = _filter_by_status(all_bookings, ["pending"], True)
    filtered_orders = _filter_by_status(all_orders, ["pending", "preparing"], False)

    text = _build_list_text(filtered_bookings, filtered_orders, lang, "pending")
    kb = _build_keyboard(filtered_bookings, filtered_orders, lang, "pending")

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "seller_filter_active")
async def seller_filter_active(callback: types.CallbackQuery) -> None:
    """Show active orders."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    all_bookings, all_orders = _get_all_orders(db, callback.from_user.id)
    filtered_bookings = _filter_by_status(all_bookings, ["confirmed", "preparing"], True)
    filtered_orders = _filter_by_status(all_orders, ["confirmed", "ready", "delivering"], False)

    text = _build_list_text(filtered_bookings, filtered_orders, lang, "active")
    kb = _build_keyboard(filtered_bookings, filtered_orders, lang, "active")

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "seller_filter_completed")
async def seller_filter_completed(callback: types.CallbackQuery) -> None:
    """Show completed orders."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    all_bookings, all_orders = _get_all_orders(db, callback.from_user.id)
    filtered_bookings = _filter_by_status(all_bookings, ["completed"], True)
    filtered_orders = _filter_by_status(all_orders, ["completed"], False)

    text = _build_list_text(filtered_bookings, filtered_orders, lang, "completed")
    kb = _build_keyboard(filtered_bookings, filtered_orders, lang, "completed")

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


# =============================================================================
# VIEW BOOKING DETAIL
# =============================================================================


@router.callback_query(F.data.startswith("seller_view_b_"))
async def seller_view_booking(callback: types.CallbackQuery) -> None:
    """View booking details with action buttons."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer("❌ Topilmadi" if lang == "uz" else "❌ Не найдено", show_alert=True)
        return

    status = _get_field(booking, "status") or "pending"
    quantity = _get_field(booking, "quantity") or 1
    booking_code = _get_field(booking, "booking_code") or ""
    user_id = _get_field(booking, "user_id")
    offer_id = _get_field(booking, "offer_id")

    offer = db.get_offer(offer_id) if offer_id else None
    title = _get_field(offer, "title") or "Товар"
    price = _get_field(offer, "discount_price") or 0

    customer = db.get_user_model(user_id) if user_id else None
    customer_name = customer.first_name if customer and customer.first_name else "Клиент"
    customer_phone = customer.phone if customer and customer.phone else "—"

    total = price * quantity
    currency = "so'm" if lang == "uz" else "сум"

    status_emoji = {
        "pending": "⏳",
        "confirmed": "✅",
        "preparing": "👨‍🍳",
        "completed": "🎉",
        "cancelled": "❌",
    }.get(status, "📦")
    status_text = {
        "pending": "Kutilmoqda" if lang == "uz" else "Ожидает",
        "confirmed": "Tasdiqlangan" if lang == "uz" else "Подтверждён",
        "preparing": "Tayyorlanmoqda" if lang == "uz" else "Готовится",
        "completed": "Bajarildi" if lang == "uz" else "Выполнен",
        "cancelled": "Bekor qilindi" if lang == "uz" else "Отменён",
    }.get(status, status)

    lines = [
        f"🏪 <b>{'OLIB KETISH' if lang == 'uz' else 'САМОВЫВОЗ'} #{booking_id}</b>",
        f"{status_emoji} <b>{status_text}</b>",
        "",
        f"📦 {title}",
        f"🔢 {'Miqdor' if lang == 'uz' else 'Кол-во'}: <b>{quantity}</b>",
        f"💰 {'Jami' if lang == 'uz' else 'Итого'}: <b>{total:,} {currency}</b>",
        "",
        f"👤 {customer_name}",
        f"📱 <code>{customer_phone}</code>",
    ]

    if booking_code:
        lines.append(f"🎫 {'Kod' if lang == 'uz' else 'Код'}: <code>{booking_code}</code>")

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()

    if status == "pending":
        kb.button(
            text="✅ Tasdiqlash" if lang == "uz" else "✅ Подтвердить",
            callback_data=f"booking_confirm_{booking_id}",
        )
        kb.button(
            text="❌ Rad etish" if lang == "uz" else "❌ Отклонить",
            callback_data=f"booking_reject_{booking_id}",
        )
    elif status in ["confirmed", "preparing"]:
        kb.button(
            text="🎉 Topshirildi" if lang == "uz" else "🎉 Выдано",
            callback_data=f"complete_booking_{booking_id}",
        )
        kb.button(
            text="❌ Bekor" if lang == "uz" else "❌ Отменить",
            callback_data=f"booking_cancel_seller_{booking_id}",
        )

    kb.button(
        text="📞 Aloqa" if lang == "uz" else "📞 Связаться",
        callback_data=f"contact_customer_b_{booking_id}",
    )
    kb.button(text="⬅️ Orqaga" if lang == "uz" else "⬅️ Назад", callback_data="seller_orders_refresh")
    kb.adjust(2, 1, 1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    await callback.answer()


# =============================================================================
# VIEW ORDER DETAIL
# =============================================================================


@router.callback_query(F.data.startswith("seller_view_o_"))
async def seller_view_order(callback: types.CallbackQuery) -> None:
    """View delivery order details with action buttons."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ Topilmadi" if lang == "uz" else "❌ Не найдено", show_alert=True)
        return

    status = _get_field(order, "order_status") or _get_field(order, "status") or "pending"
    quantity = _get_field(order, "quantity") or 1
    delivery_address = _get_field(order, "delivery_address") or ""
    total_price = _get_field(order, "total_price") or 0
    delivery_price = _get_field(order, "delivery_price") or 0
    user_id = _get_field(order, "user_id")
    offer_id = _get_field(order, "offer_id")

    offer = db.get_offer(offer_id) if offer_id else None
    title = _get_field(offer, "title") or "Товар"

    customer = db.get_user_model(user_id) if user_id else None
    customer_name = customer.first_name if customer and customer.first_name else "Клиент"
    customer_phone = customer.phone if customer and customer.phone else "—"

    currency = "so'm" if lang == "uz" else "сум"

    status_emoji = {
        "pending": "⏳",
        "preparing": "👨‍🍳",
        "ready": "📦",
        "delivering": "🚚",
        "completed": "🎉",
        "cancelled": "❌",
    }.get(status, "📦")
    status_text = {
        "pending": "Kutilmoqda" if lang == "uz" else "Ожидает",
        "preparing": "Tayyorlanmoqda" if lang == "uz" else "Готовится",
        "ready": "Tayyor" if lang == "uz" else "Готов",
        "delivering": "Yo'lda" if lang == "uz" else "В пути",
        "completed": "Yetkazildi" if lang == "uz" else "Доставлен",
        "cancelled": "Bekor qilindi" if lang == "uz" else "Отменён",
    }.get(status, status)

    lines = [
        f"🚚 <b>{'YETKAZISH' if lang == 'uz' else 'ДОСТАВКА'} #{order_id}</b>",
        f"{status_emoji} <b>{status_text}</b>",
        "",
        f"📦 {title} × {quantity}",
        f"💰 {'Jami' if lang == 'uz' else 'Итого'}: <b>{total_price:,} {currency}</b>",
    ]

    if delivery_price:
        lines.append(
            f"🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}"
        )

    lines.extend(
        [
            "",
            f"👤 {customer_name}",
            f"📱 <code>{customer_phone}</code>",
            f"📍 {delivery_address or '—'}",
        ]
    )

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()

    if status == "pending":
        kb.button(
            text="✅ Qabul qilish" if lang == "uz" else "✅ Принять",
            callback_data=f"order_confirm_{order_id}",
        )
        kb.button(
            text="❌ Rad etish" if lang == "uz" else "❌ Отклонить",
            callback_data=f"order_reject_{order_id}",
        )
    elif status == "preparing":
        kb.button(
            text="📦 Tayyor" if lang == "uz" else "📦 Готов",
            callback_data=f"order_ready_{order_id}",
        )
        kb.button(
            text="❌ Bekor" if lang == "uz" else "❌ Отменить",
            callback_data=f"order_cancel_seller_{order_id}",
        )
    elif status == "ready":
        kb.button(
            text="🚚 Yo'lga chiqdi" if lang == "uz" else "🚚 В пути",
            callback_data=f"order_delivering_{order_id}",
        )

    kb.button(
        text="📞 Aloqa" if lang == "uz" else "📞 Связаться",
        callback_data=f"contact_customer_o_{order_id}",
    )
    kb.button(text="⬅️ Orqaga" if lang == "uz" else "⬅️ Назад", callback_data="seller_orders_refresh")
    kb.adjust(2, 1, 1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    await callback.answer()


# =============================================================================
# CONTACT CUSTOMER
# =============================================================================


@router.callback_query(F.data.startswith("contact_customer_"))
async def contact_customer(callback: types.CallbackQuery) -> None:
    """Show customer contact info."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    parts = callback.data.split("_")
    entity_type = parts[2]  # 'b' or 'o'
    entity_id = int(parts[3])

    if entity_type == "b":
        entity = db.get_booking(entity_id)
    else:
        entity = db.get_order(entity_id)

    if not entity:
        await callback.answer("❌", show_alert=True)
        return

    user_id = _get_field(entity, "user_id")
    customer = db.get_user_model(user_id) if user_id else None

    if not customer:
        await callback.answer(
            "❌ Kontakt topilmadi" if lang == "uz" else "❌ Контакт не найден", show_alert=True
        )
        return

    phone = customer.phone or "—"
    name = customer.first_name or "Клиент"

    text = f"📞 <b>{'Mijoz kontakti' if lang == 'uz' else 'Контакт клиента'}</b>\n\n"
    text += f"👤 {name}\n"
    text += f"📱 <code>{phone}</code>"

    kb = InlineKeyboardBuilder()
    if customer.username:
        kb.button(text="✉️ Telegram", url=f"https://t.me/{customer.username}")
    elif user_id:
        kb.button(text="✉️ Telegram", url=f"tg://user?id={user_id}")

    kb.button(text="⬅️ Orqaga" if lang == "uz" else "⬅️ Назад", callback_data="seller_orders_refresh")
    kb.adjust(1)

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


# =============================================================================
# BOOKING ACTIONS (using UnifiedOrderService)
# =============================================================================


@router.callback_query(F.data.startswith("booking_confirm_"))
async def confirm_booking_handler(callback: types.CallbackQuery) -> None:
    """Confirm a pending booking via UnifiedOrderService."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer("❌ Topilmadi" if lang == "uz" else "❌ Не найдено", show_alert=True)
        return

    status = _get_field(booking, "status")
    if status != "pending":
        await callback.answer(
            "❌ Allaqachon ko'rib chiqilgan" if lang == "uz" else "❌ Уже обработано",
            show_alert=True,
        )
        return

    # Update via UnifiedOrderService
    service = get_unified_order_service()
    if not service:
        logger.error("UnifiedOrderService is not initialized for booking_confirm handler")
        await callback.answer(get_text(lang, "error") or "System error", show_alert=True)
        return

    try:
        await service.confirm_order(booking_id, "booking")
        await callback.answer("✅ Tasdiqlandi" if lang == "uz" else "✅ Подтверждено")

        # Refresh view
        await seller_orders_refresh(callback)
    except Exception as e:
        logger.error(f"confirm_booking error: {e}")
        await callback.answer(
            f"❌ Xatolik: {e}" if lang == "uz" else f"❌ Ошибка: {e}", show_alert=True
        )


@router.callback_query(F.data.startswith("booking_reject_"))
async def reject_booking_handler(callback: types.CallbackQuery) -> None:
    """Reject a pending booking via UnifiedOrderService."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer("❌ Topilmadi" if lang == "uz" else "❌ Не найдено", show_alert=True)
        return

    service = get_unified_order_service()
    if not service:
        logger.error("UnifiedOrderService is not initialized for booking_reject handler")
        await callback.answer(get_text(lang, "error") or "System error", show_alert=True)
        return

    try:
        await service.reject_order(booking_id, "booking", reason="Продавец отклонил")
        await callback.answer("❌ Rad etildi" if lang == "uz" else "❌ Отклонено")

        await seller_orders_refresh(callback)
    except Exception as e:
        logger.error(f"reject_booking error: {e}")
        await callback.answer(
            f"❌ Xatolik: {e}" if lang == "uz" else f"❌ Ошибка: {e}", show_alert=True
        )


@router.callback_query(F.data.startswith("booking_cancel_seller_"))
async def cancel_booking_seller_handler(callback: types.CallbackQuery) -> None:
    """Cancel active booking by seller."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    service = get_unified_order_service()
    if not service:
        logger.error("UnifiedOrderService is not initialized for booking_cancel_seller handler")
        await callback.answer(get_text(lang, "error") or "System error", show_alert=True)
        return

    try:
        await service.cancel_order(booking_id, "booking")
        await callback.answer("❌ Bekor qilindi" if lang == "uz" else "❌ Отменено")

        await seller_orders_refresh(callback)
    except Exception as e:
        logger.error(f"cancel_booking error: {e}")
        await callback.answer(
            f"❌ Xatolik: {e}" if lang == "uz" else f"❌ Ошибка: {e}", show_alert=True
        )


# =============================================================================
# ORDER ACTIONS (using UnifiedOrderService)
# =============================================================================


@router.callback_query(F.data.startswith("order_confirm_"))
async def confirm_order_handler(callback: types.CallbackQuery) -> None:
    """Confirm a pending order via UnifiedOrderService."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    service = get_unified_order_service()
    if not service:
        logger.error("UnifiedOrderService is not initialized for order_confirm handler")
        await callback.answer(get_text(lang, "error") or "System error", show_alert=True)
        return

    try:
        await service.confirm_order(order_id, "order")
        await callback.answer("✅ Qabul qilindi" if lang == "uz" else "✅ Принято")

        await seller_orders_refresh(callback)
    except Exception as e:
        logger.error(f"confirm_order error: {e}")
        await callback.answer(
            f"❌ Xatolik: {e}" if lang == "uz" else f"❌ Ошибка: {e}", show_alert=True
        )


@router.callback_query(F.data.startswith("order_reject_"))
async def reject_order_handler(callback: types.CallbackQuery) -> None:
    """Reject a pending order via UnifiedOrderService."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    service = get_unified_order_service()
    if not service:
        logger.error("UnifiedOrderService is not initialized for order_reject handler")
        await callback.answer(get_text(lang, "error") or "System error", show_alert=True)
        return

    try:
        await service.reject_order(order_id, "order", reason="Продавец отклонил")
        await callback.answer("❌ Rad etildi" if lang == "uz" else "❌ Отклонено")

        await seller_orders_refresh(callback)
    except Exception as e:
        logger.error(f"reject_order error: {e}")
        await callback.answer(
            f"❌ Xatolik: {e}" if lang == "uz" else f"❌ Ошибка: {e}", show_alert=True
        )


@router.callback_query(F.data.startswith("order_ready_"))
async def order_ready_handler(callback: types.CallbackQuery) -> None:
    """Mark order as ready for pickup/delivery."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    service = get_unified_order_service()
    if not service:
        logger.error("UnifiedOrderService is not initialized for order_ready handler")
        await callback.answer(get_text(lang, "error") or "System error", show_alert=True)
        return

    try:
        await service.mark_ready(order_id, "order")
        await callback.answer("📦 Tayyor!" if lang == "uz" else "📦 Готов!")

        await seller_orders_refresh(callback)
    except Exception as e:
        logger.error(f"order_ready error: {e}")
        await callback.answer(
            f"❌ Xatolik: {e}" if lang == "uz" else f"❌ Ошибка: {e}", show_alert=True
        )


@router.callback_query(F.data.startswith("order_delivering_"))
async def order_delivering_handler(callback: types.CallbackQuery) -> None:
    """Mark order as out for delivery."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    service = get_unified_order_service()
    if not service:
        logger.error("UnifiedOrderService is not initialized for order_delivering handler")
        await callback.answer(get_text(lang, "error") or "System error", show_alert=True)
        return

    try:
        await service.start_delivery(order_id)
        await callback.answer("🚚 Yo'lga chiqdi!" if lang == "uz" else "🚚 В пути!")

        await seller_orders_refresh(callback)
    except Exception as e:
        logger.error(f"order_delivering error: {e}")
        await callback.answer(
            f"❌ Xatolik: {e}" if lang == "uz" else f"❌ Ошибка: {e}", show_alert=True
        )


@router.callback_query(F.data.startswith("order_cancel_seller_"))
async def cancel_order_seller_handler(callback: types.CallbackQuery) -> None:
    """Cancel order by seller."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    service = get_unified_order_service()
    if not service:
        logger.error("UnifiedOrderService is not initialized for order_cancel_seller handler")
        await callback.answer(get_text(lang, "error") or "System error", show_alert=True)
        return

    try:
        await service.cancel_order(order_id, "order")
        await callback.answer("❌ Bekor qilindi" if lang == "uz" else "❌ Отменено")

        await seller_orders_refresh(callback)
    except Exception as e:
        logger.error(f"cancel_order error: {e}")
        await callback.answer(
            f"❌ Xatolik: {e}" if lang == "uz" else f"❌ Ошибка: {e}", show_alert=True
        )


# =============================================================================
# LEGACY HANDLERS (backward compatibility)
# =============================================================================


@router.callback_query(F.data == "seller_orders_pending")
async def legacy_filter_pending(callback: types.CallbackQuery) -> None:
    await seller_filter_pending(callback)


@router.callback_query(F.data == "seller_orders_active")
async def legacy_filter_active(callback: types.CallbackQuery) -> None:
    await seller_filter_active(callback)


@router.callback_query(F.data == "seller_orders_completed")
async def legacy_filter_completed(callback: types.CallbackQuery) -> None:
    await seller_filter_completed(callback)


@router.callback_query(F.data.startswith("booking_details_seller_"))
async def legacy_booking_details(callback: types.CallbackQuery) -> None:
    booking_id = callback.data.split("_")[-1]
    callback.data = f"seller_view_b_{booking_id}"
    await seller_view_booking(callback)
