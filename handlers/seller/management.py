"""Seller offer management handlers."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database_protocol import DatabaseProtocol
from handlers.common_states.states import EditOffer
from app.keyboards import main_menu_seller
from localization import get_text
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router()


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


def get_offer_field(offer: Any, field: str, default: Any = None) -> Any:
    """Extract field from offer tuple/dict."""
    if isinstance(offer, dict):
        return offer.get(field, default)
    if isinstance(offer, (tuple, list)):
        field_map = {
            "offer_id": 0, "store_id": 1, "title": 2, "description": 3,
            "original_price": 4, "discount_price": 5, "quantity": 6,
            "available_from": 7, "available_until": 8, "expiry_date": 9,
            "status": 10, "photo": 11, "created_at": 12, "unit": 13,
            "category": 14, "store_name": 15, "address": 16, "city": 17
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


@router.message(
    F.text.contains("🎫 Заказы") | F.text.contains("Заказы") | F.text.contains("Buyurtmalar")
)
async def seller_orders(message: types.Message) -> None:
    """Display seller's orders and bookings from all stores."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    stores = db.get_user_stores(message.from_user.id)

    if not stores:
        await message.answer(get_text(lang, "no_stores"))
        return

    # Collect all bookings and orders from all stores
    all_bookings = []
    all_orders = []
    
    for store in stores:
        store_id = get_store_field(store, "store_id")
        store_bookings = db.get_store_bookings(store_id)
        all_bookings.extend(store_bookings)
        
        try:
            store_orders = db.get_store_orders(store_id)
            all_orders.extend(store_orders)
        except Exception:
            pass

    if not all_bookings and not all_orders:
        await message.answer(
            "┌─────────────────────────┐\n"
            f"│  🎫 <b>{'ЗАКАЗЫ' if lang == 'ru' else 'BUYURTMALAR'}</b>  │\n"
            "└─────────────────────────┘\n\n"
            f"❌ {'Пока нет заказов' if lang == 'ru' else 'Hali buyurtmalar yo`q'}\n\n"
            f"💡 {'Когда клиенты сделают заказ, он появится здесь' if lang == 'ru' else 'Mijozlar buyurtma berganida, u bu yerda paydo bo`ladi'}",
            parse_mode="HTML"
        )
        return

    # Count by status - safe dict/tuple access
    pending_bookings = []
    confirmed_bookings = []
    completed_bookings = []
    cancelled_bookings = []
    
    for b in all_bookings:
        status = b.get('status') if isinstance(b, dict) else (b[3] if len(b) > 3 else None)
        if status == 'pending':
            pending_bookings.append(b)
        elif status == 'confirmed':
            confirmed_bookings.append(b)
        elif status == 'completed':
            completed_bookings.append(b)
        elif status == 'cancelled':
            cancelled_bookings.append(b)

    pending_orders = []
    confirmed_orders = []
    completed_orders = []
    cancelled_orders = []
    
    for o in all_orders:
        status = o.get('order_status') if isinstance(o, dict) else (o[10] if len(o) > 10 else None)
        if status in ['pending', 'preparing']:
            pending_orders.append(o)
        elif status in ['confirmed', 'delivering']:
            confirmed_orders.append(o)
        elif status == 'completed':
            completed_orders.append(o)
        elif status == 'cancelled':
            cancelled_orders.append(o)

    # Status filter buttons
    filter_kb = InlineKeyboardBuilder()
    filter_kb.button(text=f"⏳ Новые ({len(pending_bookings) + len(pending_orders)})", callback_data="seller_orders_pending")
    filter_kb.button(text=f"✅ Активные ({len(confirmed_bookings) + len(confirmed_orders)})", callback_data="seller_orders_active")
    filter_kb.button(text=f"🎉 Выполненные ({len(completed_bookings) + len(completed_orders)})", callback_data="seller_orders_completed")
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
        reply_markup=filter_kb.as_markup()
    )

    # Show first 5 pending items immediately
    items_to_show = (pending_bookings + pending_orders)[:5]
    
    for item in items_to_show:
        await _send_order_card(message, item, lang, is_booking=item in pending_bookings)
        await asyncio.sleep(0.1)


async def _send_order_card(message: types.Message, order: Any, lang: str, is_booking: bool = True) -> None:
    """Send order/booking card with action buttons."""
    if is_booking:
        # Booking fields
        booking_id = order.get('booking_id') if isinstance(order, dict) else order[0]
        offer_title = order.get('title') if isinstance(order, dict) else (order[4] if len(order) > 4 else 'Товар')
        user_name = order.get('first_name', 'Клиент') if isinstance(order, dict) else (order[5] if len(order) > 5 else 'Клиент')
        phone = order.get('phone', 'Не указан') if isinstance(order, dict) else (order[7] if len(order) > 7 else 'Не указан')
        quantity = order.get('quantity', 1) if isinstance(order, dict) else (order[6] if len(order) > 6 else 1)
        status = order.get('status', 'pending') if isinstance(order, dict) else (order[3] if len(order) > 3 else 'pending')
        booking_code = order.get('booking_code', '') if isinstance(order, dict) else (order[8] if len(order) > 8 else '')
        created_at = order.get('created_at') if isinstance(order, dict) else (order[9] if len(order) > 9 else None)
        
        status_emoji = {"pending": "⏳", "confirmed": "✅", "completed": "🎉", "cancelled": "❌"}.get(status, "📦")
        
        text = f"{status_emoji} <b>{'САМОВЫВОЗ' if lang == 'ru' else 'OLIB KETISH'}</b>\n\n"
        text += f"📦 {offer_title}\n"
        text += f"🔢 {'Количество' if lang == 'ru' else 'Miqdor'}: <b>{quantity}</b>\n\n"
        text += f"👤 {user_name}\n"
        text += f"📱 <code>{phone}</code>\n"
        text += f"🎫 {'Код' if lang == 'ru' else 'Kod'}: <code>{booking_code}</code>\n"
        if created_at:
            text += f"🕐 {created_at}\n"
        
        builder = InlineKeyboardBuilder()
        if status == "pending":
            builder.button(text="✅ Подтвердить" if lang == "ru" else "✅ Tasdiqlash", callback_data=f"confirm_booking_{booking_id}")
            builder.button(text="❌ Отменить" if lang == "ru" else "❌ Bekor qilish", callback_data=f"cancel_booking_{booking_id}")
            builder.adjust(2)
        elif status == "confirmed":
            builder.button(text="🎉 Выдано" if lang == "ru" else "🎉 Berildi", callback_data=f"complete_booking_{booking_id}")
            builder.button(text="❌ Отменить" if lang == "ru" else "❌ Bekor qilish", callback_data=f"cancel_booking_{booking_id}")
            builder.adjust(2)
    else:
        # Order fields (delivery)
        order_id = order.get('order_id') if isinstance(order, dict) else order[0]
        user_name = order.get('user_name', 'Клиент') if isinstance(order, dict) else 'Клиент'
        quantity = order.get('quantity', 1) if isinstance(order, dict) else (order[9] if len(order) > 9 else 1)
        address = order.get('delivery_address', 'Не указан') if isinstance(order, dict) else (order[4] if len(order) > 4 else 'Не указан')
        status = order.get('order_status', 'pending') if isinstance(order, dict) else (order[10] if len(order) > 10 else 'pending')
        
        status_emoji = {"pending": "⏳", "confirmed": "✅", "preparing": "👨‍🍳", "delivering": "🚚", "completed": "🎉", "cancelled": "❌"}.get(status, "📦")
        
        text = f"{status_emoji} <b>{'ДОСТАВКА' if lang == 'ru' else 'YETKAZIB BERISH'}</b>\n\n"
        text += f"📦 {'Заказ' if lang == 'ru' else 'Buyurtma'} #{order_id}\n"
        text += f"🔢 {quantity} {'шт' if lang == 'ru' else 'dona'}\n\n"
        text += f"👤 {user_name}\n"
        text += f"📍 {address}\n"
        
        builder = InlineKeyboardBuilder()
        if status == "pending":
            builder.button(text="✅ Принять" if lang == "ru" else "✅ Qabul qilish", callback_data=f"confirm_order_{order_id}")
            builder.button(text="❌ Отменить" if lang == "ru" else "❌ Bekor qilish", callback_data=f"cancel_order_{order_id}")
            builder.adjust(2)
    
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


@router.message(
    F.text.contains("Мои товары") | F.text.contains("Mening mahsulotlarim")
)
async def my_offers(message: types.Message) -> None:
    """Display seller's offers with management buttons."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    stores = db.get_user_stores(message.from_user.id)

    logger.info(f"my_offers: user {message.from_user.id}, stores count: {len(stores)}")

    if not stores:
        await message.answer(get_text(lang, "no_stores"))
        return

    all_offers = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        store_name = get_store_field(store, "name", "Магазин")
        offers = db.get_store_offers(store_id)
        logger.info(f"Store {store_id} ({store_name}), offers count: {len(offers)}")
        all_offers.extend(offers)

    logger.info(f"Total offers: {len(all_offers)}")

    if not all_offers:
        await message.answer(
            "📦 <b>" + ("Ваши товары" if lang == 'ru' else "Sizning mahsulotlaringiz") + "</b>\n\n"
            "❌ " + get_text(lang, "no_offers_yet") + "\n\n"
            "💡 " + ("Нажмите ➕ Добавить чтобы создать первый товар" if lang == 'ru' else "➕ Qo'shish tugmasini bosing"),
            parse_mode="HTML"
        )
        return

    # Count active and inactive
    active_count = sum(1 for o in all_offers if (o.get('status') if isinstance(o, dict) else o[10]) == 'active')
    inactive_count = len(all_offers) - active_count

    # Filter menu
    filter_kb = InlineKeyboardBuilder()
    filter_kb.button(text=f"✅ Активные ({active_count})", callback_data="filter_offers_active")
    filter_kb.button(text=f"❌ Неактивные ({inactive_count})", callback_data="filter_offers_inactive")
    filter_kb.button(text=f"📋 Все ({len(all_offers)})", callback_data="filter_offers_all")
    filter_kb.adjust(2, 1)

    await message.answer(
        "┌─────────────────────────┐\n"
        f"│  📦 <b>{'ВАШИ ТОВАРЫ' if lang == 'ru' else 'MAHSULOTLARINGIZ'}</b>  │\n"
        "└─────────────────────────┘\n\n"
        f"✅ Активных: <b>{active_count}</b>\n"
        f"❌ Неактивных: <b>{inactive_count}</b>\n"
        f"📊 Всего: <b>{len(all_offers)}</b>",
        parse_mode="HTML",
        reply_markup=filter_kb.as_markup()
    )

    # Show first 10 offers
    for offer in all_offers[:10]:
        await _send_offer_card(message, offer, lang)
        await asyncio.sleep(0.1)

    if len(all_offers) > 10:
        await message.answer(
            f"ℹ️ {'Показано первые 10 товаров из' if lang == 'ru' else 'Birinchi 10 ta mahsulot'} {len(all_offers)}\n"
            f"{'Используйте фильтры выше для поиска' if lang == 'ru' else 'Qidirish uchun filtrlardan foydalaning'}"
        )


async def _send_offer_card(message: types.Message, offer: Any, lang: str) -> None:
    """Send single offer card with management buttons."""
    # Safe field extraction
    offer_id = offer.get('offer_id') if isinstance(offer, dict) else offer[0]
    title = offer.get('title') if isinstance(offer, dict) else (offer[2] if len(offer) > 2 else 'Без названия')
    original_price = int(offer.get('original_price', 0) if isinstance(offer, dict) else (offer[4] if len(offer) > 4 else 0))
    discount_price = int(offer.get('discount_price', 0) if isinstance(offer, dict) else (offer[5] if len(offer) > 5 else 0))
    quantity = offer.get('quantity', 0) if isinstance(offer, dict) else (offer[6] if len(offer) > 6 else 0)
    status = offer.get('status', 'active') if isinstance(offer, dict) else (offer[10] if len(offer) > 10 else "active")
    photo = offer.get('photo') if isinstance(offer, dict) else (offer[11] if len(offer) > 11 else None)
    unit = offer.get('unit', 'шт') if isinstance(offer, dict) else (offer[13] if len(offer) > 13 and offer[13] else 'шт')
    available_from = offer.get('available_from') if isinstance(offer, dict) else (offer[7] if len(offer) > 7 else None)
    available_until = offer.get('available_until') if isinstance(offer, dict) else (offer[8] if len(offer) > 8 else None)
    expiry_date = offer.get('expiry_date') if isinstance(offer, dict) else (offer[9] if len(offer) > 9 else None)

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
    if expiry_date and db:
        expiry_info = db.get_time_remaining(expiry_date)
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
        builder.adjust(2, 2, 1)
    else:
        builder.button(
            text="✅ Активировать" if lang == "ru" else "✅ Faollashtirish",
            callback_data=f"activate_offer_{offer_id}",
        )
        builder.button(
            text="🗑 Удалить" if lang == "ru" else "🗑 O'chirish",
            callback_data=f"delete_offer_{offer_id}",
        )
        builder.adjust(2)

    if photo:
        try:
            await message.answer_photo(
                photo=photo,
                caption=text,
                parse_mode="HTML",
                reply_markup=builder.as_markup(),
            )
        except Exception:
            await message.answer(
                text, parse_mode="HTML", reply_markup=builder.as_markup()
            )
    else:
        await message.answer(
            text, parse_mode="HTML", reply_markup=builder.as_markup()
        )


# Filter handlers for "Мои товары"
@router.callback_query(F.data.startswith("filter_offers_"))
async def filter_offers(callback: types.CallbackQuery) -> None:
    """Filter offers by status."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    filter_type = callback.data.split("_")[-1]  # active, inactive, all
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_stores(callback.from_user.id)

    if not stores:
        await callback.answer(get_text(lang, "no_stores"), show_alert=True)
        return

    all_offers = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        offers = db.get_store_offers(store_id)
        all_offers.extend(offers)

    # Apply filter
    if filter_type == "active":
        filtered = [o for o in all_offers if (o.get('status') if isinstance(o, dict) else o[10]) == 'active']
        title = "✅ Активные товары"
    elif filter_type == "inactive":
        filtered = [o for o in all_offers if (o.get('status') if isinstance(o, dict) else o[10]) != 'active']
        title = "❌ Неактивные товары"
    else:
        filtered = all_offers
        title = "📋 Все товары"

    if not filtered:
        await callback.answer(f"{'Нет товаров в этой категории' if lang == 'ru' else 'Bu kategoriyada mahsulot yo`q'}", show_alert=True)
        return

    await callback.answer()
    
    await callback.message.answer(
        f"<b>{title}</b>\n\n"
        f"{'Найдено' if lang == 'ru' else 'Topildi'}: <b>{len(filtered)}</b>",
        parse_mode="HTML"
    )

    for offer in filtered[:10]:
        await _send_offer_card(callback.message, offer, lang)
        await asyncio.sleep(0.1)

    if len(filtered) > 10:
        await callback.message.answer(
            f"ℹ️ {'Показано первые 10 из' if lang == 'ru' else 'Birinchi 10 ta'} {len(filtered)}"
        )


# Order filter handlers
@router.callback_query(F.data == "seller_orders_pending")
async def filter_orders_pending(callback: types.CallbackQuery) -> None:
    """Show pending orders/bookings."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_stores(callback.from_user.id)
    
    pending_items = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        bookings = db.get_store_bookings(store_id) or []
        pending_items.extend([b for b in bookings if (b.get('status') if isinstance(b, dict) else (b[3] if len(b) > 3 else None)) == 'pending'])
    
    await callback.answer()
    await callback.message.answer(f"⏳ {'Новые заказы' if lang == 'ru' else 'Yangi buyurtmalar'}: <b>{len(pending_items)}</b>", parse_mode="HTML")
    
    for item in pending_items[:10]:
        await _send_order_card(callback.message, item, lang, is_booking=True)
        await asyncio.sleep(0.1)


@router.callback_query(F.data == "seller_orders_active")
async def filter_orders_active(callback: types.CallbackQuery) -> None:
    """Show active orders/bookings."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_stores(callback.from_user.id)
    
    active_items = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        bookings = db.get_store_bookings(store_id) or []
        active_items.extend([b for b in bookings if (b.get('status') if isinstance(b, dict) else (b[3] if len(b) > 3 else None)) == 'confirmed'])
    
    await callback.answer()
    await callback.message.answer(f"✅ {'Активные заказы' if lang == 'ru' else 'Faol buyurtmalar'}: <b>{len(active_items)}</b>", parse_mode="HTML")
    
    for item in active_items[:10]:
        await _send_order_card(callback.message, item, lang, is_booking=True)
        await asyncio.sleep(0.1)


@router.callback_query(F.data == "seller_orders_completed")
async def filter_orders_completed(callback: types.CallbackQuery) -> None:
    """Show completed orders/bookings."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_stores(callback.from_user.id)
    
    completed_items = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        bookings = db.get_store_bookings(store_id) or []
        completed_items.extend([b for b in bookings if (b.get('status') if isinstance(b, dict) else (b[3] if len(b) > 3 else None)) == 'completed'])
    
    await callback.answer()
    await callback.message.answer(f"🎉 {'Выполненные заказы' if lang == 'ru' else 'Bajarilgan buyurtmalar'}: <b>{len(completed_items)}</b>", parse_mode="HTML")
    
    for item in completed_items[:10]:
        await _send_order_card(callback.message, item, lang, is_booking=True)
        await asyncio.sleep(0.1)


# Order action handlers
@router.callback_query(F.data.startswith("confirm_booking_"))
async def confirm_booking_handler(callback: types.CallbackQuery) -> None:
    """Confirm a booking."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    booking_id = int(callback.data.split("_")[2])
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        db.update_booking_status(booking_id, "confirmed")
        await callback.answer(f"✅ {'Бронь подтверждена' if lang == 'ru' else 'Bron tasdiqlandi'}", show_alert=True)
        
        # Update message
        if callback.message and callback.message.text:
            new_text = callback.message.text.replace("⏳", "✅")
            builder = InlineKeyboardBuilder()
            builder.button(text="🎉 Выдано" if lang == "ru" else "🎉 Berildi", callback_data=f"complete_booking_{booking_id}")
            builder.button(text="❌ Отменить" if lang == "ru" else "❌ Bekor qilish", callback_data=f"cancel_booking_{booking_id}")
            builder.adjust(2)
            await callback.message.edit_text(new_text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error confirming booking: {e}")
        await callback.answer(f"❌ {'Ошибка' if lang == 'ru' else 'Xatolik'}", show_alert=True)


@router.callback_query(F.data.startswith("complete_booking_"))
async def complete_booking_handler(callback: types.CallbackQuery) -> None:
    """Mark booking as completed."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    booking_id = int(callback.data.split("_")[2])
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        db.complete_booking(booking_id)
        await callback.answer(f"🎉 {'Заказ выполнен!' if lang == 'ru' else 'Buyurtma bajarildi!'}", show_alert=True)
        
        # Update message
        if callback.message and callback.message.text:
            new_text = callback.message.text.replace("✅", "🎉").replace("⏳", "🎉")
            new_text += f"\n\n<b>{'✅ ВЫДАНО' if lang == 'ru' else '✅ BERILDI'}</b>"
            await callback.message.edit_text(new_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error completing booking: {e}")
        await callback.answer(f"❌ {'Ошибка' if lang == 'ru' else 'Xatolik'}", show_alert=True)


@router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking_handler(callback: types.CallbackQuery) -> None:
    """Cancel a booking."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    booking_id = int(callback.data.split("_")[2])
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        db.cancel_booking(booking_id)
        await callback.answer(f"❌ {'Бронь отменена' if lang == 'ru' else 'Bron bekor qilindi'}", show_alert=True)
        
        # Update message
        if callback.message and callback.message.text:
            new_text = callback.message.text.replace("✅", "❌").replace("⏳", "❌")
            new_text += f"\n\n<b>{'❌ ОТМЕНЕНО' if lang == 'ru' else '❌ BEKOR QILINDI'}</b>"
            await callback.message.edit_text(new_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error cancelling booking: {e}")
        await callback.answer(f"❌ {'Ошибка' if lang == 'ru' else 'Xatolik'}", show_alert=True)


@router.callback_query(F.data.startswith("qty_add_"))
async def quantity_add(callback: types.CallbackQuery) -> None:
    """Increase offer quantity by 1."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    # Safe field access
    offer_store_id = offer.get('store_id') if isinstance(offer, dict) else (offer[1] if len(offer) > 1 else None)
    current_quantity = offer.get('quantity') if isinstance(offer, dict) else (offer[6] if len(offer) > 6 else 0)

    user_stores = db.get_user_stores(callback.from_user.id)
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    new_quantity = current_quantity + 1
    db.update_offer_quantity(offer_id, new_quantity)

    await update_offer_message(callback, offer_id, lang)
    await callback.answer(f"✅ +1 (теперь {new_quantity})")


@router.callback_query(F.data.startswith("qty_sub_"))
async def quantity_subtract(callback: types.CallbackQuery) -> None:
    """Decrease offer quantity by 1."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    # Safe field access
    offer_store_id = offer.get('store_id') if isinstance(offer, dict) else (offer[1] if len(offer) > 1 else None)
    current_quantity = offer.get('quantity') if isinstance(offer, dict) else (offer[6] if len(offer) > 6 else 0)

    user_stores = db.get_user_stores(callback.from_user.id)
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    new_quantity = max(0, current_quantity - 1)
    db.update_offer_quantity(offer_id, new_quantity)

    await update_offer_message(callback, offer_id, lang)

    if new_quantity == 0:
        await callback.answer(
            "⚠️ Количество 0 - товар снят с продажи", show_alert=True
        )
    else:
        await callback.answer(f"✅ -1 (теперь {new_quantity})")


@router.callback_query(F.data.startswith("extend_offer_"))
async def extend_offer(callback: types.CallbackQuery) -> None:
    """Extend offer expiry date."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    today = datetime.now()

    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"Сегодня {today.strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_0",
    )
    builder.button(
        text=f"Завтра {(today + timedelta(days=1)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_1",
    )
    builder.button(
        text=f"+2 дня {(today + timedelta(days=2)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_2",
    )
    builder.button(
        text=f"+3 дня {(today + timedelta(days=3)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_3",
    )
    builder.button(
        text=f"Неделя {(today + timedelta(days=7)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_7",
    )
    builder.button(text="❌ Отмена", callback_data="cancel_extend")
    builder.adjust(2, 2, 1, 1)

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer("📅 Выберите новый срок годности")


@router.callback_query(F.data.startswith("setexp_"))
async def set_expiry(callback: types.CallbackQuery) -> None:
    """Set new expiry date."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    parts = callback.data.split("_")
    offer_id = int(parts[1])
    days_add = int(parts[2])

    new_expiry = (datetime.now() + timedelta(days=days_add)).strftime("%Y-%m-%d")

    db.update_offer_expiry(offer_id, new_expiry)

    await update_offer_message(callback, offer_id, lang)
    await callback.answer(f"✅ Срок продлён до {new_expiry}")


@router.callback_query(F.data == "cancel_extend")
async def cancel_extend(callback: types.CallbackQuery) -> None:
    """Cancel expiry extension."""
    await callback.answer("❌ Отменено")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("deactivate_offer_"))
async def deactivate_offer(callback: types.CallbackQuery) -> None:
    """Deactivate offer."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    db.deactivate_offer(offer_id)

    await update_offer_message(callback, offer_id, lang)
    await callback.answer("✅ Товар снят с продажи")


@router.callback_query(F.data.startswith("activate_offer_"))
async def activate_offer(callback: types.CallbackQuery) -> None:
    """Activate offer."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    db.activate_offer(offer_id)

    await update_offer_message(callback, offer_id, lang)
    await callback.answer("✅ Товар активирован")


@router.callback_query(F.data.startswith("delete_offer_"))
async def delete_offer(callback: types.CallbackQuery) -> None:
    """Delete offer."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    db.delete_offer(offer_id)

    await callback.message.delete()
    await callback.answer("🗑 Товар удалён")


@router.callback_query(F.data.startswith("edit_offer_"))
async def edit_offer(callback: types.CallbackQuery) -> None:
    """Show offer edit menu."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.button(
        text="💰 Изменить цену" if lang == "ru" else "💰 Narxni o'zgartirish",
        callback_data=f"edit_price_{offer_id}",
    )
    kb.button(
        text="📦 Изменить количество" if lang == "ru" else "📦 Sonini o'zgartirish",
        callback_data=f"edit_quantity_{offer_id}",
    )
    kb.button(
        text="🕐 Изменить время" if lang == "ru" else "🕐 Vaqtni o'zgartirish",
        callback_data=f"edit_time_{offer_id}",
    )
    kb.button(
        text="📝 Изменить описание" if lang == "ru" else "📝 Tavsifni o'zgartirish",
        callback_data=f"edit_description_{offer_id}",
    )
    kb.button(
        text="🔙 Назад" if lang == "ru" else "🔙 Orqaga",
        callback_data=f"back_to_offer_{offer_id}",
    )
    kb.adjust(1)

    try:
        await callback.message.edit_reply_markup(reply_markup=kb.as_markup())
    except Exception:
        await callback.answer(get_text(lang, "edit_unavailable"), show_alert=True)

    await callback.answer()


@router.callback_query(F.data.startswith("edit_time_"))
async def edit_time_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start editing pickup time."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    await state.update_data(offer_id=offer_id)
    await state.set_state(EditOffer.available_from)

    await callback.message.answer(
        f"🕐 <b>Изменение времени забора</b>\n\n"
        f"Текущее время: {offer[7]} - {offer[8]}\n\n"
        f"{'Введите новое время начала (например: 18:00):' if lang == 'ru' else 'Yangi boshlanish vaqtini kiriting (masalan: 18:00):'}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EditOffer.available_from)
async def edit_time_from(message: types.Message, state: FSMContext) -> None:
    """Process start time."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)

    time_pattern = r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$"
    if not re.match(time_pattern, message.text.strip()):
        error_msg = (
            "❌ Неверный формат! Введите время в формате ЧЧ:ММ (например: 18:00)"
            if lang == "ru"
            else "❌ Noto'g'ri format! ЧЧ:ММ formatida vaqt kiriting (masalan: 18:00)"
        )
        await message.answer(error_msg)
        return

    await state.update_data(available_from=message.text.strip())
    await message.answer(
        f"{'Введите время окончания (например: 21:00):' if lang == 'ru' else 'Tugash vaqtini kiriting (masalan: 21:00):'}",
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.set_state(EditOffer.available_until)


@router.message(EditOffer.available_until)
async def edit_time_until(message: types.Message, state: FSMContext) -> None:
    """Complete time editing."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)

    time_pattern = r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$"
    if not re.match(time_pattern, message.text.strip()):
        error_msg = (
            "❌ Неверный формат! Введите время в формате ЧЧ:ММ (например: 21:00)"
            if lang == "ru"
            else "❌ Noto'g'ri format! ЧЧ:ММ formatida vaqt kiriting (masalan: 21:00)"
        )
        await message.answer(error_msg)
        return

    data = await state.get_data()
    offer_id = data["offer_id"]
    available_from = data["available_from"]
    available_until = message.text.strip()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE offers SET available_from = ?, available_until = ? WHERE offer_id = ?",
            (available_from, available_until, offer_id),
        )

    await message.answer(
        f"✅ {'Время забора обновлено!' if lang == 'ru' else 'Olib ketish vaqti yangilandi!'}\n\n"
        f"🕐 {available_from} - {available_until}",
        reply_markup=main_menu_seller(lang),
    )
    await state.clear()


async def update_offer_message(
    callback: types.CallbackQuery, offer_id: int, lang: str
) -> None:
    """Update offer message with new data."""
    if not db:
        return

    offer = db.get_offer(offer_id)
    if not offer:
        return

    # Safe field extraction
    title = offer.get('title') if isinstance(offer, dict) else (offer[2] if len(offer) > 2 else 'Товар')
    original_price = int(offer.get('original_price', 0) if isinstance(offer, dict) else (offer[4] if len(offer) > 4 else 0))
    discount_price = int(offer.get('discount_price', 0) if isinstance(offer, dict) else (offer[5] if len(offer) > 5 else 0))
    quantity = offer.get('quantity', 0) if isinstance(offer, dict) else (offer[6] if len(offer) > 6 else 0)
    status = offer.get('status', 'active') if isinstance(offer, dict) else (offer[10] if len(offer) > 10 else 'active')
    unit = offer.get('unit', 'шт') if isinstance(offer, dict) else (offer[13] if len(offer) > 13 and offer[13] else 'шт')
    available_from = offer.get('available_from') if isinstance(offer, dict) else (offer[7] if len(offer) > 7 else '')
    available_until = offer.get('available_until') if isinstance(offer, dict) else (offer[8] if len(offer) > 8 else '')
    expiry_date = offer.get('expiry_date') if isinstance(offer, dict) else (offer[9] if len(offer) > 9 else None)

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
        expiry_info = db.get_time_remaining(expiry_date)
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
        builder.adjust(2, 2, 1)
    else:
        builder.button(
            text="✅ Активировать" if lang == "ru" else "✅ Faollashtirish",
            callback_data=f"activate_offer_{offer_id}",
        )
        builder.button(
            text="🗑 Удалить" if lang == "ru" else "🗑 O'chirish",
            callback_data=f"delete_offer_{offer_id}",
        )
        builder.adjust(2)

    try:
        await callback.message.edit_caption(
            caption=text, parse_mode="HTML", reply_markup=builder.as_markup()
        )
    except Exception:
        try:
            await callback.message.edit_text(
                text, parse_mode="HTML", reply_markup=builder.as_markup()
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("duplicate_"))
async def duplicate_offer(callback: types.CallbackQuery) -> None:
    """Duplicate offer."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    offer_id = int(callback.data.split("_")[1])
    offer = db.get_offer(offer_id)

    if offer:
        unit_val = get_offer_field(offer, "unit", "шт")
        if not unit_val or not isinstance(unit_val, str) or len(unit_val) > 5:
            unit_val = "шт"
        category_val = get_offer_field(offer, "category", "other") or "other"

        db.add_offer(
            store_id=get_offer_field(offer, "store_id"),
            title=get_offer_field(offer, "title"),
            description=get_offer_field(offer, "description"),
            original_price=get_offer_field(offer, "original_price"),
            discount_price=get_offer_field(offer, "discount_price"),
            quantity=get_offer_field(offer, "quantity"),
            available_from=get_offer_field(offer, "available_from"),
            available_until=get_offer_field(offer, "available_until"),
            photo_id=get_offer_field(offer, "photo"),
            expiry_date=get_offer_field(offer, "expiry_date"),
            unit=unit_val,
            category=category_val,
        )
        await callback.answer(get_text(lang, "duplicated"), show_alert=True)
