"""Seller order management handlers - order list, filtering, actions."""
from __future__ import annotations

import asyncio
from typing import Any

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from localization import get_text
from logging_config import logger

from .utils import get_db, get_store_field, send_order_card

router = Router()


@router.message(F.text.contains("🎫 Заказы продавца") | F.text.contains("Buyurtmalar (sotuvchi)"))
async def seller_orders(message: types.Message) -> Any:
    """Display seller's orders and bookings from all stores. Only for sellers WITH stores."""
    db = get_db()

    # Check if user has stores - if not, don't handle this message
    try:
        stores = db.get_user_stores(message.from_user.id)
        if not stores:
            raise ValueError("No stores")
    except Exception as e:
        logger.debug(f"seller_orders skipped: {e}")
        raise

    lang = db.get_user_language(message.from_user.id)

    # Collect all bookings and orders from all stores
    all_bookings = []
    all_orders = []

    for store in stores:
        store_id = get_store_field(store, "store_id")
        store_bookings = db.get_store_bookings(store_id)
        if store_bookings:
            all_bookings.extend(store_bookings)

        # Get delivery orders
        store_orders = db.get_store_orders(store_id)
        if store_orders:
            all_orders.extend(store_orders)

    if not all_bookings and not all_orders:
        await message.answer(
            "┌─────────────────────────┐\n"
            f"│  🎫 <b>{'ЗАКАЗЫ' if lang == 'ru' else 'BUYURTMALAR'}</b>  │\n"
            "└─────────────────────────┘\n\n"
            f"❌ {'Пока нет заказов' if lang == 'ru' else 'Hali buyurtmalar yo`q'}\n\n"
            f"💡 {'Когда клиенты сделают заказ, он появится здесь' if lang == 'ru' else 'Mijozlar buyurtma berganida, u bu yerda paydo bo`ladi'}",
            parse_mode="HTML",
        )
        return

    # Count by status
    pending_bookings = []
    confirmed_bookings = []
    completed_bookings = []
    cancelled_bookings = []

    for b in all_bookings:
        status = b.get("status") if isinstance(b, dict) else (b[3] if len(b) > 3 else None)
        if status == "pending":
            pending_bookings.append(b)
        elif status == "confirmed":
            confirmed_bookings.append(b)
        elif status == "completed":
            completed_bookings.append(b)
        elif status == "cancelled":
            cancelled_bookings.append(b)

    pending_orders = []
    confirmed_orders = []
    completed_orders = []
    cancelled_orders = []

    for o in all_orders:
        status = o.get("order_status") if isinstance(o, dict) else (o[10] if len(o) > 10 else None)
        if status in ["pending", "preparing"]:
            pending_orders.append(o)
        elif status in ["confirmed", "delivering"]:
            confirmed_orders.append(o)
        elif status == "completed":
            completed_orders.append(o)
        elif status == "cancelled":
            cancelled_orders.append(o)

    # Status filter buttons
    filter_kb = InlineKeyboardBuilder()
    filter_kb.button(
        text=f"⏳ Новые ({len(pending_bookings) + len(pending_orders)})",
        callback_data="seller_orders_pending",
    )
    filter_kb.button(
        text=f"✅ Активные ({len(confirmed_bookings) + len(confirmed_orders)})",
        callback_data="seller_orders_active",
    )
    filter_kb.button(
        text=f"🎉 Выполненные ({len(completed_bookings) + len(completed_orders)})",
        callback_data="seller_orders_completed",
    )
    filter_kb.adjust(2, 1)

    await message.answer(
        "┌─────────────────────────┐\n"
        f"│  🎫 <b>{'ЗАКАЗЫ' if lang == 'ru' else 'BUYURTMALAR'}</b>  │\n"
        "└─────────────────────────┘\n\n"
        f"📋 <b>{'САМОВЫВОЗ (БРОНИ)' if lang == 'ru' else 'OLIB KETISH'}</b>\n"
        f"⏳ Новые: <b>{len(pending_bookings)}</b>\n"
        f"✅ Подтверждённые: <b>{len(confirmed_bookings)}</b>\n"
        f"🎉 Выполненные: <b>{len(completed_bookings)}</b>\n"
        f"❌ Отменённые: <b>{len(cancelled_bookings)}</b>\n\n"
        f"🚚 <b>{'ДОСТАВКА' if lang == 'ru' else 'YETKAZIB BERISH'}</b>\n"
        f"⏳ Новые: <b>{len(pending_orders)}</b>\n"
        f"✅ В процессе: <b>{len(confirmed_orders)}</b>\n"
        f"🎉 Выполненные: <b>{len(completed_orders)}</b>\n"
        f"❌ Отменённые: <b>{len(cancelled_orders)}</b>\n\n"
        f"{'Выберите фильтр для просмотра:' if lang == 'ru' else 'Ko`rish uchun filtrni tanlang:'}",
        parse_mode="HTML",
        reply_markup=filter_kb.as_markup(),
    )

    # Show first 5 pending items immediately
    items_to_show = (pending_bookings + pending_orders)[:5]

    for item in items_to_show:
        await send_order_card(message, item, lang, is_booking=item in pending_bookings)
        await asyncio.sleep(0.1)


@router.callback_query(F.data == "seller_orders_pending")
async def filter_orders_pending(callback: types.CallbackQuery) -> None:
    """Show pending orders/bookings."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_stores(callback.from_user.id)

    pending_bookings = []
    pending_orders = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        # Bookings (pickups)
        bookings = db.get_store_bookings(store_id) or []
        for b in bookings:
            status = b.get("status") if isinstance(b, dict) else (b[3] if len(b) > 3 else None)
            if status == "pending":
                pending_bookings.append(b)
        # Delivery orders
        orders = db.get_store_orders(store_id) or []
        for o in orders:
            status = (
                o.get("order_status") if isinstance(o, dict) else (o[10] if len(o) > 10 else None)
            )
            if status in ["pending", "preparing"]:
                pending_orders.append(o)

    await callback.answer()

    if not pending_bookings and not pending_orders:
        await callback.message.edit_text(
            f"⏳ {'Новых заказов нет' if lang == 'ru' else 'Yangi buyurtmalar yo`q'}",
            parse_mode="HTML",
        )
        return

    await callback.message.edit_text(
        f"⏳ {'Новые заказы' if lang == 'ru' else 'Yangi buyurtmalar'}:\n"
        f"📋 {'Самовывоз' if lang == 'ru' else 'Olib ketish'}: <b>{len(pending_bookings)}</b>\n"
        f"🚚 {'Доставка' if lang == 'ru' else 'Yetkazib berish'}: <b>{len(pending_orders)}</b>",
        parse_mode="HTML",
    )

    # Show bookings first
    for item in pending_bookings[:5]:
        await send_order_card(callback.message, item, lang, is_booking=True)
        await asyncio.sleep(0.1)

    # Then show delivery orders
    for item in pending_orders[:5]:
        await send_order_card(callback.message, item, lang, is_booking=False)
        await asyncio.sleep(0.1)


@router.callback_query(F.data == "seller_orders_active")
async def filter_orders_active(callback: types.CallbackQuery) -> None:
    """Show active orders/bookings."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_stores(callback.from_user.id)

    active_bookings = []
    active_orders = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        # Bookings (pickups)
        bookings = db.get_store_bookings(store_id) or []
        for b in bookings:
            status = b.get("status") if isinstance(b, dict) else (b[3] if len(b) > 3 else None)
            if status == "confirmed":
                active_bookings.append(b)
        # Delivery orders
        orders = db.get_store_orders(store_id) or []
        for o in orders:
            status = (
                o.get("order_status") if isinstance(o, dict) else (o[10] if len(o) > 10 else None)
            )
            if status in ["confirmed", "delivering"]:
                active_orders.append(o)

    await callback.answer()

    if not active_bookings and not active_orders:
        await callback.message.edit_text(
            f"✅ {'Активных заказов нет' if lang == 'ru' else 'Faol buyurtmalar yo`q'}",
            parse_mode="HTML",
        )
        return

    await callback.message.edit_text(
        f"✅ {'Активные заказы' if lang == 'ru' else 'Faol buyurtmalar'}:\n"
        f"📋 {'Самовывоз' if lang == 'ru' else 'Olib ketish'}: <b>{len(active_bookings)}</b>\n"
        f"🚚 {'Доставка' if lang == 'ru' else 'Yetkazib berish'}: <b>{len(active_orders)}</b>",
        parse_mode="HTML",
    )

    for item in active_bookings[:5]:
        await send_order_card(callback.message, item, lang, is_booking=True)
        await asyncio.sleep(0.1)

    for item in active_orders[:5]:
        await send_order_card(callback.message, item, lang, is_booking=False)
        await asyncio.sleep(0.1)


@router.callback_query(F.data == "seller_orders_completed")
async def filter_orders_completed(callback: types.CallbackQuery) -> None:
    """Show completed orders/bookings."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_stores(callback.from_user.id)

    completed_items = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        bookings = db.get_store_bookings(store_id) or []
        for b in bookings:
            status = b.get("status") if isinstance(b, dict) else (b[3] if len(b) > 3 else None)
            if status == "completed":
                completed_items.append(b)

    await callback.answer()

    if not completed_items:
        await callback.message.edit_text(
            f"🎉 {'Выполненных заказов нет' if lang == 'ru' else 'Bajarilgan buyurtmalar yo`q'}",
            parse_mode="HTML",
        )
        return

    await callback.message.edit_text(
        f"🎉 {'Выполненные заказы' if lang == 'ru' else 'Bajarilgan buyurtmalar'}: <b>{len(completed_items)}</b>",
        parse_mode="HTML",
    )

    for item in completed_items[:10]:
        await send_order_card(callback.message, item, lang, is_booking=True)
        await asyncio.sleep(0.1)


@router.callback_query(F.data.startswith("booking_details_seller_"))
async def booking_details_seller(callback: types.CallbackQuery) -> None:
    """Show extended booking details to seller."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        booking_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(
            "❌ " + ("Бронь не найдена" if lang == "ru" else "Bron topilmadi"), show_alert=True
        )
        return

    user_id = (
        booking.get("user_id")
        if isinstance(booking, dict)
        else (booking[2] if len(booking) > 2 else None)
    )
    user = db.get_user(user_id) if user_id else None
    customer = (
        user.get("first_name") if isinstance(user, dict) and user.get("first_name") else "Клиент"
    )
    phone = (
        user.get("phone")
        if isinstance(user, dict)
        else (booking.get("phone") if isinstance(booking, dict) else "")
    )
    quantity = (
        booking.get("quantity")
        if isinstance(booking, dict)
        else (booking[6] if len(booking) > 6 else 1)
    )
    code = (
        booking.get("booking_code")
        if isinstance(booking, dict)
        else (booking[8] if len(booking) > 8 else "")
    )
    created = (
        booking.get("created_at")
        if isinstance(booking, dict)
        else (booking[9] if len(booking) > 9 else None)
    )

    store_id = (
        booking.get("store_id")
        if isinstance(booking, dict)
        else (booking[3] if len(booking) > 3 else None)
    )
    store = db.get_store(store_id) if store_id else None
    store_name = get_store_field(store, "name", "Магазин")
    store_address = get_store_field(store, "address", "")

    text = f"📋 <b>{'Детали брони' if lang == 'ru' else 'Bron tafsilotlari'}</b>\n\n"
    text += f"🏬 <b>{store_name}</b>\n"
    if store_address:
        text += f"📍 {store_address}\n"
    text += f"👤 {customer}\n"
    text += f"📱 {phone}\n"
    text += f"🔢 {'Количество' if lang == 'ru' else 'Miqdor'}: <b>{quantity}</b>\n"
    text += f"🎫 {'Код' if lang == 'ru' else 'Kod'}: <code>{code}</code>\n"
    if created:
        text += f"🕐 {created}\n"

    await callback.answer()
    await callback.message.answer(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("contact_customer_"))
async def contact_customer(callback: types.CallbackQuery) -> None:
    """Send customer contact info to seller."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        booking_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(
            "❌ " + ("Бронь не найдена" if lang == "ru" else "Bron topilmadi"), show_alert=True
        )
        return

    user_id = (
        booking.get("user_id")
        if isinstance(booking, dict)
        else (booking[2] if len(booking) > 2 else None)
    )
    user = db.get_user(user_id) if user_id else None

    phone = (
        user.get("phone")
        if isinstance(user, dict) and user.get("phone")
        else (booking.get("phone") if isinstance(booking, dict) else "Не указан")
    )
    pickup_addr = (
        booking.get("pickup_address")
        if isinstance(booking, dict)
        else (booking[4] if len(booking) > 4 else "")
    )

    text = f"📞 Контакт покупателя:\n{phone}\n"
    if pickup_addr:
        text += f"📍 Адрес получателя:\n{pickup_addr}\n"

    kb = InlineKeyboardBuilder()
    username = user.get("username") if isinstance(user, dict) else None
    if username:
        kb.button(text="✉️ Написать", url=f"https://t.me/{username}")
    elif user_id:
        kb.button(text="✉️ Написать", url=f"tg://user?id={user_id}")

    await callback.answer()
    # Check if we have any buttons by building the markup
    markup = kb.as_markup()
    if markup.inline_keyboard:
        await callback.message.answer(text, reply_markup=markup)
    else:
        await callback.message.answer(text)


@router.callback_query(F.data.startswith("confirm_booking_"))
async def confirm_booking_handler(callback: types.CallbackQuery) -> None:
    """Confirm a booking."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        booking_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    try:
        db.update_booking_status(booking_id, "confirmed")
        await callback.answer(
            f"✅ {'Бронь подтверждена' if lang == 'ru' else 'Bron tasdiqlandi'}", show_alert=True
        )

        if callback.message and callback.message.text:
            new_text = callback.message.text.replace("⏳", "✅")
            builder = InlineKeyboardBuilder()
            builder.button(
                text="🎉 Выдано" if lang == "ru" else "🎉 Berildi",
                callback_data=f"complete_booking_{booking_id}",
            )
            builder.button(
                text="❌ Отменить" if lang == "ru" else "❌ Bekor qilish",
                callback_data=f"cancel_booking_{booking_id}",
            )
            builder.adjust(2)
            await callback.message.edit_text(
                new_text, parse_mode="HTML", reply_markup=builder.as_markup()
            )
    except Exception as e:
        logger.error(f"Error confirming booking: {e}")
        await callback.answer(f"❌ {'Ошибка' if lang == 'ru' else 'Xatolik'}", show_alert=True)


# NOTE: complete_booking_ handler is in handlers/bookings/partner.py
# It handles ownership verification and customer notifications


@router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking_handler(callback: types.CallbackQuery) -> None:
    """Cancel a booking."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        booking_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer()
        return

    try:
        db.cancel_booking(booking_id)
        await callback.answer(
            f"❌ {'Бронь отменена' if lang == 'ru' else 'Bron bekor qilindi'}", show_alert=True
        )

        if callback.message and callback.message.text:
            new_text = callback.message.text.replace("✅", "❌").replace("⏳", "❌")
            new_text += f"\n\n<b>{'❌ ОТМЕНЕНО' if lang == 'ru' else '❌ BEKOR QILINDI'}</b>"
            await callback.message.edit_text(new_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error cancelling booking: {e}")
        await callback.answer(f"❌ {'Ошибка' if lang == 'ru' else 'Xatolik'}", show_alert=True)
