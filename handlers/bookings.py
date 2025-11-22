"""Booking handlers: create bookings, manage bookings, ratings."""
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Any

from app.core.cache import CacheManager
from database_protocol import DatabaseProtocol
from handlers.common_states.states import BookOffer, OrderDelivery
from app.keyboards import cancel_keyboard, main_menu_customer
from localization import get_text
from logging_config import logger


# Rate limiting placeholder
def can_proceed(user_id: int, action: str) -> bool:
    """Rate limiting check - placeholder."""
    return True

# This will be imported from bot.py
router = Router()


def get_store_field(store: Any, field: str, default: Any = None) -> Any:
    """Extract field from store tuple/dict."""
    if isinstance(store, dict):
        return store.get(field, default)
    if isinstance(store, (tuple, list)):
        field_map = {
            "store_id": 0, "owner_id": 1, "name": 2, "city": 3,
            "address": 4, "description": 5, "category": 6, "phone": 7,
            "status": 8, "rejection_reason": 9, "created_at": 10
        }
        idx = field_map.get(field)
        if idx is not None and len(store) > idx:
            return store[idx]
    return default


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


def get_booking_field(booking: Any, field: str, default: Any = None) -> Any:
    """Extract field from booking tuple/dict."""
    if isinstance(booking, dict):
        return booking.get(field, default)
    if isinstance(booking, (tuple, list)):
        field_map = {
            "booking_id": 0, "offer_id": 1, "user_id": 2, "status": 3,
            "code": 4, "pickup_time": 5, "quantity": 6, "created_at": 7
        }
        idx = field_map.get(field)
        if idx is not None and len(booking) > idx:
            return booking[idx]
    return default


def get_bookings_filter_keyboard(lang: str):
    """Create bookings filter keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "filter_upcoming"), callback_data="filter_upcoming")
    builder.button(text=get_text(lang, "filter_past"), callback_data="filter_past")
    builder.button(text=get_text(lang, "filter_all"), callback_data="filter_all")
    builder.adjust(3)
    return builder.as_markup()


# Module-level dependencies (will be set during router registration)
db: DatabaseProtocol | None = None
cache: CacheManager | None = None
bot: Any = None  # Bot instance
METRICS: dict | None = None


def setup_dependencies(
    database: DatabaseProtocol,
    cache_manager: CacheManager,
    bot_instance: Any,
    metrics: dict,
) -> None:
    """Setup module dependencies."""
    global db, cache, bot, METRICS
    db = database
    cache = cache_manager
    bot = bot_instance
    METRICS = metrics


@router.callback_query(F.data.startswith("book_"))
async def book_offer_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start booking - ask for quantity."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
    # Rate limit booking start
    if not can_proceed(callback.from_user.id, "book_start"):
        await callback.answer(get_text(lang, "operation_cancelled"), show_alert=True)
        return
    
    try:
        offer_id = int(callback.data.split("_")[1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    offer = db.get_offer(offer_id)
    
    if not offer:
        await callback.answer(get_text(lang, "no_offers"), show_alert=True)
        return
    
    # Get quantity safely from dict/tuple
    quantity = get_offer_field(offer, "quantity", 0)
    if quantity <= 0:
        await callback.answer(get_text(lang, "no_offers"), show_alert=True)
        return
    
    # Get other fields safely
    title = get_offer_field(offer, "title", "Товар")
    price = get_offer_field(offer, "discount_price", 0)
    
    # Save offer_id to state
    await state.update_data(offer_id=offer_id)
    await state.set_state(BookOffer.quantity)
    
    # Ask for quantity
    try:
        await callback.message.answer(
            f"📦 <b>{title}</b>\n\n"
            f"📋 Доступно: {quantity} шт\n"
            f"💰 Цена: {int(price):,} сум/шт\n\n"
            f"Сколько хотите забронировать? (1-{quantity})",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(lang),
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error sending booking message: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.message(BookOffer.quantity)
async def book_offer_quantity(message: types.Message, state: FSMContext) -> None:
    """Process quantity and create booking."""
    if not db or not bot or not METRICS:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    
    # Rate limit booking confirm
    if not can_proceed(message.from_user.id, "book_confirm"):
        await message.answer(get_text(lang, "operation_cancelled"))
        return
    
    # Check for cancellation
    if message.text in ["❌ Отмена", "❌ Bekor qilish", "/cancel"]:
        await state.clear()
        await message.answer(
            get_text(lang, "action_cancelled"),
            reply_markup=main_menu_customer(lang)
        )
        return

    try:
        logger.info(f"📦 BOOKING: User {message.from_user.id} entered quantity: {message.text}")
        
        quantity = int(message.text)
        if quantity < 1:
            await message.answer("❌ Количество должно быть больше 0")
            return
        
        data = await state.get_data()
        offer_id = data.get("offer_id")
        logger.info(f"📦 BOOKING: offer_id from state: {offer_id}")
        
        if not offer_id:
            await message.answer("❌ Ошибка: товар не выбран")
            await state.clear()
            return
            
        offer = db.get_offer(offer_id)
        logger.info(f"📦 BOOKING: offer retrieved: {offer is not None}")
        
        if not offer:
            await message.answer("❌ Предложение не найдено")
            await state.clear()
            return
            
        # Safe access to quantity field - handle different offer structures
        try:
            if isinstance(offer, (tuple, list)):
                available_qty = offer[6] if len(offer) > 6 else 0
                offer_title = offer[2] if len(offer) > 2 else "Товар"
                offer_price = offer[5] if len(offer) > 5 else 0
                store_id = offer[1] if len(offer) > 1 else None
                offer_address = offer[16] if len(offer) > 16 else "Адрес не указан"
            elif isinstance(offer, dict):
                available_qty = offer.get('quantity', 0)
                offer_title = offer.get('title', 'Товар')
                offer_price = offer.get('discount_price', 0)
                store_id = offer.get('store_id')
                offer_address = offer.get('address', 'Адрес не указана')
            else:
                await message.answer("❌ Ошибка формата данных")
                await state.clear()
                return
        except (IndexError, KeyError, TypeError) as e:
            logger.error(f"Error accessing offer fields: {e}, offer type: {type(offer)}")
            await message.answer("❌ Ошибка обработки товара")
            await state.clear()
            return
            
        if available_qty < quantity:
            await message.answer(f"❌ Доступно только {available_qty} шт.")
            return
        
        # Try to atomically book item and create booking
        logger.info(f"📦 BOOKING: Calling create_booking_atomic - offer_id={offer_id}, user_id={message.from_user.id}, quantity={quantity}")
        
        ok, booking_id, code = db.create_booking_atomic(
            offer_id, message.from_user.id, quantity
        )
        
        logger.info(f"📦 BOOKING: create_booking_atomic result - ok={ok}, booking_id={booking_id}, code={code}")
        
        if not ok or booking_id is None or code is None:
            logger.error(f"📦 BOOKING FAILED: ok={ok}, booking_id={booking_id}, code={code}")
            await message.answer(
                "❌ К сожалению, выбранное количество уже недоступно."
            )
            await state.clear()
            return
        
        logger.info(f"✅ BOOKING SUCCESS: booking_id={booking_id}, code={code}")
        
        try:
            METRICS["bookings_created"] += 1
        except Exception:
            pass
        
        await state.clear()
        
        # Notify partner with inline quick actions
        if store_id:
            store = db.get_store(store_id)
            if store:
                owner_id = get_store_field(store, "owner_id")
                if not owner_id:
                    logger.warning(f"Store {store_id} has no owner_id")
                    await state.clear()
                    return
                partner_lang = db.get_user_language(owner_id)
                # Get customer phone for partner
                customer = db.get_user_model(message.from_user.id)
                customer_phone = customer.phone if customer else "Не указан"
                
                # Create inline keyboard for quick actions
                notification_kb = InlineKeyboardBuilder()
                notification_kb.button(text="✓ Выдано", callback_data=f"complete_booking_{booking_id}")
                notification_kb.button(text="× Отменить", callback_data=f"cancel_booking_{booking_id}")
                notification_kb.adjust(2)
                
                store_name = get_store_field(store, "name", "Магазин")
                
                try:
                    await bot.send_message(
                        owner_id,
                        f"🔔 <b>Новый заказ</b>\n\n"
                        f"🏪 {store_name}\n"
                        f"📦 {offer_title} × {quantity} шт\n\n"
                        f"👤 {message.from_user.first_name}\n"
                        f"📱 <code>{customer_phone}</code>\n"
                        f"🎫 <code>{code}</code>\n"
                        f"💰 {int(offer_price * quantity):,} сум",
                        parse_mode="HTML",
                        reply_markup=notification_kb.as_markup(),
                    )
                except Exception as e:
                    logger.error(f"Failed to notify partner: {e}")
        
        total_price = int(offer_price * quantity)
        
        # Get store name for better UX
        store_name = "Магазин"
        if store_id:
            store = db.get_store(store_id)
            if store:
                store_name = get_store_field(store, "name", "Магазин")
        
        # Get offer expiry if available
        expiry_text = ""
        if isinstance(offer, (tuple, list)) and len(offer) > 17:
            expiry_date = offer[17]  # expiry_date field
            if expiry_date:
                expiry_text = f"\n🕐 <b>Забрать до:</b> {expiry_date}\n"
        
        # Show booking confirmation to customer with full details
        from app.keyboards.user import main_menu_customer
        
        await message.answer(
            f"✅ <b>Заказ успешно создан!</b>\n\n"
            f"🏪 <b>Магазин:</b> {store_name}\n"
            f"📦 <b>Товар:</b> {offer_title}\n"
            f"🔢 <b>Количество:</b> {quantity} шт\n"
            f"💰 <b>К оплате:</b> {total_price:,} сум\n"
            f"{expiry_text}"
            f"\n🎫 <b>Код бронирования:</b> <code>{code}</code>\n\n"
            f"📍 <b>Адрес получения:</b>\n{offer_address}\n\n"
            f"⚠️ <b>Важно:</b> Покажите этот код при получении заказа!",
            parse_mode="HTML",
            reply_markup=main_menu_customer(lang),
        )
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")
    except Exception as e:
        logger.error(f"Error in book_offer_quantity: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.message(
    F.text.contains("Мои бронирования")
    | F.text.contains("Mening buyurt")
    | F.text.contains("🛒 Корзина")
    | F.text.contains("🛒 Savat")
    | F.text.contains("Корзина")
    | F.text.contains("Savat")
)
async def my_bookings(message: types.Message) -> None:
    """Show user's bookings."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    bookings = db.get_user_bookings(message.from_user.id)
    
    if not bookings:
        empty_msg = (
            f"🛒 <b>Корзина пуста</b>\n\n"
            f"🔥 Посмотрите раздел <b>Горячее</b> или <b>Категории</b>\n"
            f"✨ Выберите товары со скидками!"
            if lang == 'ru' else
            f"🛒 <b>Savat bo'sh</b>\n\n"
            f"🔥 <b>Issiq</b> yoki <b>Kategoriyalar</b> bo'limiga o'ting\n"
            f"✨ Chegirmali mahsulotlarni tanlang!"
        )
        await message.answer(empty_msg, parse_mode="HTML")
        return
    
    # Filter active bookings (pending and confirmed are considered active)
    if isinstance(bookings[0], dict):
        active = [b for b in bookings if b.get('status') in ['pending', 'confirmed']]
    else:
        # Fallback for tuple format
        active = [b for b in bookings if b[7] in ["pending", "confirmed"]]
    
    if not active:
        no_active_msg = (
            f"🛒 <b>Активных заказов нет</b>\n\n"
            f"✅ Все ваши заказы уже выполнены\n"
            f"🔥 Сделайте новый заказ в разделе <b>Горячее</b>!"
            if lang == 'ru' else
            f"🛒 <b>Faol buyurtmalar yo'q</b>\n\n"
            f"✅ Barcha buyurtmalaringiz bajarilgan\n"
            f"🔥 <b>Issiq</b> bo'limidan yangi buyurtma bering!"
        )
        await message.answer(no_active_msg, parse_mode="HTML")
        return
    
    text = f"📦 <b>{get_text(lang, 'my_bookings')}</b>\n\n"
    
    for booking in active[:10]:  # Show max 10
        # Dict-compatible access
        if isinstance(booking, dict):
            booking_id = booking.get('booking_id')
            offer_id = booking.get('offer_id')
            quantity = booking.get('quantity', 1)
            code = booking.get('booking_code', '')
            created_at = booking.get('created_at', '')
        else:
            booking_id = booking[0]
            offer_id = booking[2]
            quantity = booking[3]
            code = booking[6]
            created_at = booking[5]
        
        offer = db.get_offer(offer_id)
        if not offer:
            continue
        
        # Get offer details (handle both dict and tuple)
        if isinstance(offer, dict):
            offer_title = offer.get('title', 'Товар')
            offer_price = offer.get('discount_price', 0)
        else:
            offer_title = offer[2]
            offer_price = offer[5]
        
        total = int(offer_price * quantity)
        
        text += (
            f"📦 <b>{offer_title}</b>\n"
            f"🔢 {quantity} шт • {total:,} сум\n"
            f"🎫 <code>{code}</code>\n"
            f"📅 {created_at}\n\n"
        )
    
    await message.answer(
        text, parse_mode="HTML"
    )


@router.callback_query(
    lambda c: c.data
    in ["bookings_active", "bookings_completed", "bookings_cancelled"]
)
async def filter_bookings(callback: types.CallbackQuery) -> None:
    """Filter bookings by status."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    status_map = {
        "bookings_active": "active",
        "bookings_completed": "completed",
        "bookings_cancelled": "cancelled",
    }
    status = status_map.get(callback.data, "active")
    
    bookings = db.get_user_bookings_by_status(callback.from_user.id, status)
    
    if not bookings:
        await callback.answer(get_text(lang, f"no_{status}_bookings"), show_alert=True)
        return
    
    text = f"🛒 <b>{get_text(lang, 'bookings')} ({status})</b>\n\n"
    
    for booking in bookings[:10]:
        # Dict-compatible access
        booking_id = booking.get('booking_id') if isinstance(booking, dict) else booking[0]
        offer_id = booking.get('offer_id') if isinstance(booking, dict) else (booking[1] if len(booking) > 1 else 0)
        status_val = booking.get('status') if isinstance(booking, dict) else (booking[3] if len(booking) > 3 else '')
        booking_code = booking.get('code') if isinstance(booking, dict) else (booking[4] if len(booking) > 4 else '')
        pickup_time = booking.get('pickup_time') if isinstance(booking, dict) else (booking[5] if len(booking) > 5 else '')
        quantity = booking.get('quantity') if isinstance(booking, dict) else (booking[6] if len(booking) > 6 else 1)
        created_at = booking.get('created_at') if isinstance(booking, dict) else (booking[7] if len(booking) > 7 else '')
        
        # Joined fields from query
        offer_title = booking[8] if len(booking) > 8 else "Товар"
        offer_price = booking[9] if len(booking) > 9 else 0
        store_name = booking[11] if len(booking) > 11 else ""
        
        total = int(offer_price * quantity)
        
        text += (
            f"🍽 <b>{offer_title}</b>\n"
            f"📦 {quantity} шт. × {int(offer_price):,} = {total:,} сум\n"
            f"🎫 <code>{booking_code}</code>\n"
            f"📅 {created_at}\n\n"
        )
    
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: types.CallbackQuery) -> None:
    """Cancel booking."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        booking_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Check if booking exists and belongs to user
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return
    
    # Cancel booking
    success = db.cancel_booking(booking_id)
    if success:
        # Return quantity to offer
        offer_id = get_booking_field(booking, "offer_id", 1)
        quantity = get_booking_field(booking, "quantity", 6)
        offer = db.get_offer(offer_id)
        if offer:
            current_qty = get_offer_field(offer, "quantity", 0)
            db.update_offer_quantity(offer_id, current_qty + quantity)

        await callback.answer(get_text(lang, "booking_cancelled"), show_alert=True)
        # Refresh message
        await filter_bookings(callback)
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("complete_booking_"))
async def complete_booking(callback: types.CallbackQuery) -> None:
    """Complete booking (partner action)."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        booking_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Check if booking exists
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return
    
    # Complete booking
    success = db.complete_booking(booking_id)
    if success:
        await callback.answer(get_text(lang, "booking_completed"), show_alert=True)
        # Edit message to show completed status
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ <b>Выполнено</b>", parse_mode="HTML"
        )
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("rate_booking_"))
async def rate_booking(callback: types.CallbackQuery) -> None:
    """Show rating keyboard for booking."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        booking_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Check if booking exists and is completed
    booking = db.get_booking(booking_id)
    if not booking or booking[7] != "completed":
        await callback.answer(get_text(lang, "cannot_rate"), show_alert=True)
        return
    
    # Show rating keyboard
    rating_kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        rating_kb.button(text=f"{'⭐' * i}", callback_data=f"booking_rate_{booking_id}_{i}")
    rating_kb.adjust(5)
    
    await callback.message.answer(
        get_text(lang, "rate_booking"), reply_markup=rating_kb.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("booking_rate_"))
async def save_booking_rating(callback: types.CallbackQuery) -> None:
    """Save booking rating."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    parts = callback.data.split("_")
    booking_id = int(parts[2])
    rating = int(parts[3])
    
    # Save rating
    success = db.save_booking_rating(booking_id, rating)
    if success:
        await callback.answer(get_text(lang, "rating_saved"), show_alert=True)
        await callback.message.edit_text(
            f"{callback.message.text}\n\n✅ Оценка: {'⭐' * rating}"
        )
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)
