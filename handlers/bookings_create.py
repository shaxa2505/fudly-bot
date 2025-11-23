"""Booking creation logic."""
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Optional

from app.keyboards import main_menu_customer
from localization import get_text
from logging_config import logger

from handlers.bookings_utils import (
    _safe_answer_or_send,
    get_store_field,
    get_offer_field,
    get_booking_field,
    get_user_safe,
)
from handlers.common import get_uzb_time
from handlers.common_states.states import BookOffer

# Dependencies
db = None
bot = None
METRICS = None


def setup_dependencies(database, bot_instance, metrics):
    """Setup module dependencies."""
    global db, bot, METRICS
    db = database
    bot = bot_instance
    METRICS = metrics


async def create_booking_final(message: types.Message, state: FSMContext) -> None:
    """Create final booking."""
    if not db or not bot:
        await message.answer("System error")
        return
        
    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    
    data = await state.get_data()
    offer_id = data.get("offer_id")
    quantity = data.get("quantity")
    # Optional pickup info collected earlier in the flow
    pickup_time = data.get("pickup_time")
    pickup_address = data.get("pickup_address")
    
    if not offer_id or not quantity:
        await message.answer("❌ Ошибка: данные не найдены" if lang == "ru" else "❌ Xatolik: ma'lumotlar topilmadi")
        await state.clear()
        return
    
    offer = db.get_offer(offer_id)
    if not offer:
        await message.answer("❌ Предложение не найдено" if lang == "ru" else "❌ Taklif topilmadi")
        await state.clear()
        return
    
    # Check active bookings limit
    if not check_booking_limit(message.from_user.id, lang):
        await state.clear()
        return
    
    # If user chose pickup but didn't pick a slot yet, prompt for slots
    delivery_choice = data.get("delivery_choice")
    if delivery_choice == 'pickup' and not pickup_time:
        # Generate quick slots and ask user to pick one
        slots = generate_pickup_slots(count=6, step_minutes=15)
        kb = InlineKeyboardBuilder()
        for ts in slots:
            # callback contains epoch seconds for simplicity
            epoch = int(ts.timestamp())
            label = ts.strftime('%H:%M, %d.%m')
            kb.button(text=label, callback_data=f"select_pickup_{epoch}")
        kb.button(text=("❌ Отменить" if lang == 'ru' else "❌ Bekor qilish"), callback_data="noop")
        kb.adjust(2)
        # Set FSM to pickup_time state so callback is allowed
        await state.set_state(BookOffer.pickup_time)
        await message.answer(get_text(lang, 'choose_pickup_time') or ("Выберите время самовывоза:" if lang == 'ru' else "Olib ketish vaqtini tanlang:"), reply_markup=kb.as_markup())
        return

    # Create booking atomically (pass optional pickup info)
    ok, booking_id, code = db.create_booking_atomic(
        offer_id,
        message.from_user.id,
        quantity,
        pickup_time=pickup_time,
        pickup_address=pickup_address,
    )
    
    if not ok or not booking_id:
        await message.answer("❌ К сожалению, выбранное количество уже недоступно." if lang == "ru" else "❌ Afsuski, tanlangan miqdor mavjud emas.")
        await state.clear()
        return
    
    logger.info(f"✅ BOOKING SUCCESS: booking_id={booking_id}, code={code}")
    
    if METRICS:
        METRICS["bookings_created"] = METRICS.get("bookings_created", 0) + 1
    
    await state.clear()
    
    # Notify partner and customer
    await notify_partner(booking_id, offer, quantity, code, message.from_user, pickup_time, pickup_address)
    await notify_customer(message, booking_id, offer, quantity, code, lang, pickup_time, pickup_address)
    
    await message.answer("✅ " + ("Готово!" if lang == "ru" else "Tayyor!"), reply_markup=main_menu_customer(lang))


def check_booking_limit(user_id: int, lang: str) -> bool:
    """Check if user has reached booking limit."""
    try:
        active_bookings = db.get_user_bookings(user_id) or []
        active_count = 0
        
        for booking in active_bookings:
            status = get_booking_field(booking, 'status')
            if status in ['active', 'pending', 'confirmed']:
                active_count += 1
        
        max_allowed = 3  # Default limit
        
        if active_count >= max_allowed:
            if lang == 'uz':
                message = f"❌ Sizda allaqachon {active_count} faol bron mavjud (maksimum {max_allowed})."
            else:
                message = f"❌ У вас уже {active_count} активных бронирований (максимум {max_allowed})."
            
            # Send via bot since we don't have message context
            from bot import bot as global_bot
            global_bot.send_message(user_id, message)
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error checking booking limit: {e}")
        return True


async def notify_partner(
    booking_id: int,
    offer: any,
    quantity: int,
    code: str,
    user: types.User,
    pickup_time: Optional[str] = None,
    pickup_address: Optional[str] = None,
) -> None:
    """Notify store owner about new booking."""
    try:
        store_id = get_offer_field(offer, "store_id")
        if not store_id:
            return
            
        store = db.get_store(store_id)
        if not store:
            return
            
        owner_id = get_store_field(store, "owner_id")
        if not owner_id:
            return
            
        partner_lang = db.get_user_language(owner_id)
        customer = get_user_safe(db, user.id)
        customer_phone = getattr(customer, 'phone', None) or "Не указан"
        
        # Create notification keyboard
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ " + ("Подтвердить" if partner_lang == 'ru' else "Tasdiqlash"), 
                 callback_data=f"partner_confirm_{booking_id}")
        kb.button(text="❌ " + ("Отклонить" if partner_lang == 'ru' else "Rad etish"), 
                 callback_data=f"partner_reject_{booking_id}")
        kb.adjust(2)
        
        store_name = get_store_field(store, "name", "Магазин")
        offer_title = get_offer_field(offer, "title", "")
        offer_price = get_offer_field(offer, "discount_price", 0)
        total_amount = int(offer_price * quantity)
        code_display = code or str(booking_id)
        
        pickup_info_text = ""
        if pickup_time:
            pickup_info_text += f"\n⏰ {pickup_time}"
        if pickup_address:
            pickup_info_text += f"\n📍 {pickup_address}"

        if partner_lang == "uz":
            text = (f"🔔 <b>Yangi buyurtma</b>\n\n"
                   f"🏪 {store_name}\n"
                   f"📦 {offer_title} × {quantity} шт\n"
                   f"👤 {user.first_name}\n"
                   f"📱 <code>{customer_phone}</code>\n"
                   f"🎫 <code>{code_display}</code>\n"
                   f"💰 {total_amount:,} so'm"
                   f"{pickup_info_text}")
        else:
            text = (f"🔔 <b>Новый заказ</b>\n\n"
                   f"🏪 {store_name}\n"
                   f"📦 {offer_title} × {quantity} шт\n"
                   f"👤 {user.first_name}\n"
                   f"📱 <code>{customer_phone}</code>\n"
                   f"🎫 <code>{code_display}</code>\n"
                   f"💰 {total_amount:,} сум"
                   f"{pickup_info_text}")
        
        await _safe_answer_or_send(None, owner_id, text, parse_mode="HTML", reply_markup=kb.as_markup())
        
    except Exception as e:
        logger.error(f"Failed to notify partner: {e}")


async def notify_customer(
    message: types.Message,
    booking_id: int,
    offer: any,
    quantity: int,
    code: str,
    lang: str,
    pickup_time: Optional[str] = None,
    pickup_address: Optional[str] = None,
) -> None:
    """Notify customer about booking creation."""
    try:
        store_id = get_offer_field(offer, "store_id")
        store_name = "Магазин"
        
        if store_id:
            store = db.get_store(store_id)
            if store:
                store_name = get_store_field(store, "name", "Магазин")
        
        offer_title = get_offer_field(offer, "title", "")
        offer_price = get_offer_field(offer, "discount_price", 0)
        total_price = int(offer_price * quantity)
        pickup_info = ""
        if pickup_time:
            pickup_info += f"\n\n⏰ <b>Время получения:</b> {pickup_time}"
        if pickup_address:
            pickup_info += f"\n📍 <b>Адрес получения:</b> {pickup_address}"
        
        if lang == "uz":
            text = (f"⏳ <b>Buyurtma yuborildi!</b>\n\n"
                   f"🏪 <b>Do'kon:</b> {store_name}\n"
                   f"📦 <b>Mahsulot:</b> {offer_title}\n"
                   f"🔢 <b>Miqdor:</b> {quantity} шт\n"
                   f"💰 <b>Jami:</b> {total_price:,} so'm\n\n"
                   f"⚠️ <b>Diqqat:</b> Buyurtma sotuvchiga tasdiqlash uchun yuborildi."
                   f"{pickup_info}")
        else:
            text = (f"⏳ <b>Заказ отправлен на подтверждение</b>\n\n"
                   f"🏪 <b>Магазин:</b> {store_name}\n"
                   f"📦 <b>Товар:</b> {offer_title}\n"
                   f"🔢 <b>Количество:</b> {quantity} шт\n"
                   f"💰 <b>Итого:</b> {total_price:,} сум\n\n"
                   f"⚠️ <b>Важно:</b> Заказ отправлен продавцу на подтверждение."
                   f"{pickup_info}")
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Failed to notify customer: {e}")


def generate_pickup_slots(count: int = 6, step_minutes: int = 15):
    """Generate a list of datetime objects for nearest pickup slots in UZ timezone."""
    from datetime import timedelta

    now = get_uzb_time()
    # Round up to next step
    minute = (now.minute // step_minutes + 1) * step_minutes
    base = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute)
    slots = [base + timedelta(minutes=step_minutes * i) for i in range(count)]
    return slots
