"""Booking handlers: create bookings, manage bookings, ratings."""
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.cache import CacheManager
from database_protocol import DatabaseProtocol
from handlers.common_states.states import BookOffer, OrderDelivery
from keyboards import cancel_keyboard
from localization import get_text
from logging_config import logger


# Rate limiting placeholder
def can_proceed(user_id: int, action: str) -> bool:
    """Rate limiting check - placeholder."""
    return True

# This will be imported from bot.py
router = Router()


# Helper functions (will be passed as dependencies)
def get_user_field(user: any, field: str, default: any = None) -> any:
    """Extract field from user tuple/dict."""
    if isinstance(user, dict):
        return user.get(field, default)
    # Tuple access - needs mapping
    return default


def get_store_field(store: any, field: str, default: any = None) -> any:
    """Extract field from store tuple/dict."""
    if isinstance(store, dict):
        return store.get(field, default)
    return default


def get_offer_field(offer: any, field: str, default: any = None) -> any:
    """Extract field from offer tuple/dict."""
    if isinstance(offer, dict):
        return offer.get(field, default)
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
bot: any = None  # Bot instance
METRICS: dict | None = None


def setup_dependencies(
    database: DatabaseProtocol,
    cache_manager: CacheManager,
    bot_instance: any,
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
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
    # Rate limit booking start
    if not can_proceed(callback.from_user.id, "book_start"):
        await callback.answer(get_text(lang, "operation_cancelled"), show_alert=True)
        return
    
    offer_id = int(callback.data.split("_")[1])
    offer = db.get_offer(offer_id)
    
    if not offer or offer[6] <= 0:
        await callback.answer(get_text(lang, "no_offers"), show_alert=True)
        return
    
    # Save offer_id to state
    await state.update_data(offer_id=offer_id)
    await state.set_state(BookOffer.quantity)
    
    # Ask for quantity
    await callback.message.answer(
        f"🍽 <b>{offer[2]}</b>\n\n"
        f"📦 Доступно: {offer[6]} шт.\n"
        f"💰 Цена за 1 шт: {int(offer[5]):,} сум\n\n"
        f"Сколько вы хотите забронировать? (1-{offer[6]})",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(lang),
    )
    await callback.answer()


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
    
    try:
        quantity = int(message.text)
        if quantity < 1:
            await message.answer("❌ Количество должно быть больше 0")
            return
        
        data = await state.get_data()
        offer_id = data["offer_id"]
        offer = db.get_offer(offer_id)
        
        if not offer or offer[6] < quantity:
            await message.answer(f"❌ Доступно только {offer[6] if offer else 0} шт.")
            return
        
        # Try to atomically book item and create booking
        ok, booking_id, code = db.create_booking_atomic(
            offer_id, message.from_user.id, quantity
        )
        if not ok or booking_id is None or code is None:
            await message.answer(
                "❌ К сожалению, выбранное количество уже недоступно. Обновите список предложений."
            )
            await state.clear()
            return
        
        try:
            METRICS["bookings_created"] += 1
        except Exception:
            pass
        
        await state.clear()
        
        # Notify partner with inline quick actions
        store = db.get_store(offer[1])
        if store:
            partner_lang = db.get_user_language(store[1])
            # Get customer phone for partner
            customer = db.get_user(message.from_user.id)
            customer_phone = get_user_field(customer, "phone", "Не указан")
            
            # Create inline keyboard for quick actions
            notification_kb = InlineKeyboardBuilder()
            notification_kb.button(text="✅ Выдано", callback_data=f"complete_booking_{booking_id}")
            notification_kb.button(text="❌ Отменить", callback_data=f"cancel_booking_{booking_id}")
            notification_kb.adjust(2)
            
            owner_id = get_store_field(store, "owner_id")
            store_name = get_store_field(store, "name", "Магазин")
            offer_title = (
                offer[2]
                if isinstance(offer, tuple) and len(offer) > 2
                else (
                    offer.get("title", "Товар")
                    if isinstance(offer, dict)
                    else "Товар"
                )
            )
            try:
                await bot.send_message(
                    owner_id,
                    f"🔔 <b>Новое бронирование!</b>\n\n"
                    f"🏪 {store_name}\n"
                    f"🍽 {offer_title}\n"
                    f"📦 Количество: {quantity} шт.\n"
                    f"👤 {message.from_user.first_name}\n"
                    f"📱 Телефон: <code>{customer_phone}</code>\n"
                    f"🎫 <code>{code}</code>\n"
                    f"💰 {int(get_offer_field(offer, 'discount_price', 0) * quantity):,} сум",
                    parse_mode="HTML",
                    reply_markup=notification_kb.as_markup(),
                )
            except Exception:
                pass
        
        total_price = int(offer[5] * quantity)
        
        # Show booking confirmation to customer
        await message.answer(
            f"✅ <b>Бронирование создано!</b>\n\n"
            f"🍽 {offer[2]}\n"
            f"📦 Количество: {quantity} шт.\n"
            f"💰 Итого: {total_price:,} сум\n"
            f"🎫 Код: <code>{code}</code>\n\n"
            f"📍 Забрать можно по адресу:\n{offer[16] if len(offer) > 16 else 'Адрес не указан'}",
            parse_mode="HTML",
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
)
async def my_bookings(message: types.Message) -> None:
    """Show user's bookings."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    bookings = db.get_user_bookings(message.from_user.id)
    
    if not bookings:
        await message.answer(
            get_text(lang, "no_bookings"),
            reply_markup=get_bookings_filter_keyboard(lang),
        )
        return
    
    # Filter active bookings
    active = [b for b in bookings if b[7] == "active"]
    
    if not active:
        await message.answer(
            get_text(lang, "no_active_bookings"),
            reply_markup=get_bookings_filter_keyboard(lang),
        )
        return
    
    text = f"🛒 <b>{get_text(lang, 'my_bookings')}</b>\n\n"
    
    for booking in active[:10]:  # Show max 10
        booking_id = booking[0]
        offer = db.get_offer(booking[2])
        if not offer:
            continue
        
        quantity = booking[3]
        code = booking[6]
        total = int(offer[5] * quantity)
        
        text += (
            f"🍽 <b>{offer[2]}</b>\n"
            f"📦 {quantity} шт. × {int(offer[5]):,} = {total:,} сум\n"
            f"🎫 <code>{code}</code>\n"
            f"📅 {booking[5]}\n\n"
        )
    
    await message.answer(
        text, parse_mode="HTML", reply_markup=get_bookings_filter_keyboard(lang)
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
        booking_id = booking[0]
        offer = db.get_offer(booking[2])
        if not offer:
            continue
        
        quantity = booking[3]
        code = booking[6]
        total = int(offer[5] * quantity)
        
        text += (
            f"🍽 <b>{offer[2]}</b>\n"
            f"📦 {quantity} шт. × {int(offer[5]):,} = {total:,} сум\n"
            f"🎫 <code>{code}</code>\n"
            f"📅 {booking[5]}\n\n"
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
    booking_id = int(callback.data.split("_")[2])
    
    # Check if booking exists and belongs to user
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return
    
    # Cancel booking
    success = db.cancel_booking(booking_id)
    if success:
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
    booking_id = int(callback.data.split("_")[2])
    
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
    booking_id = int(callback.data.split("_")[2])
    
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
