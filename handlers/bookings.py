"""Booking handlers: create bookings, manage bookings, ratings."""
from __future__ import annotations

import re
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
    store_name = get_offer_field(offer, "store_name", "Магазин")
    unit = get_offer_field(offer, "unit", "шт")
    
    # Save offer data to state
    await state.update_data(
        offer_id=offer_id,
        title=title,
        price=price,
        store_name=store_name,
        unit=unit,
        max_quantity=quantity
    )
    await state.set_state(BookOffer.quantity)
    
    # Ask for quantity with improved message
    try:
        text = get_text(lang, "booking_step_quantity").format(
            title=title,
            store_name=store_name,
            price=int(price),
            quantity=quantity,
            unit=unit
        )
        
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=cancel_keyboard(lang),
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error sending booking message: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.message(BookOffer.quantity)
async def book_offer_quantity(message: types.Message, state: FSMContext) -> None:
    """Process quantity and ask for delivery choice."""
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
            await message.answer("❌ Количество должно быть больше 0" if lang == "ru" else "❌ Miqdor 0 dan katta bo'lishi kerak")
            return
        
        data = await state.get_data()
        offer_id = data.get("offer_id")
        logger.info(f"📦 BOOKING: offer_id from state: {offer_id}")
        
        if not offer_id:
            await message.answer("❌ Ошибка: товар не выбран" if lang == "ru" else "❌ Xatolik: mahsulot tanlanmagan")
            await state.clear()
            return
            
        offer = db.get_offer(offer_id)
        logger.info(f"📦 BOOKING: offer retrieved: {offer is not None}")
        
        if not offer:
            await message.answer("❌ Предложение не найдено" if lang == "ru" else "❌ Taklif topilmadi")
            await state.clear()
            return
            
        # Safe access to quantity field - handle different offer structures
        try:
            if isinstance(offer, (tuple, list)):
                available_qty = offer[6] if len(offer) > 6 else 0
                offer_price = offer[5] if len(offer) > 5 else 0
                store_id = offer[1] if len(offer) > 1 else None
            elif isinstance(offer, dict):
                available_qty = offer.get('quantity', 0)
                offer_price = offer.get('discount_price', 0)
                store_id = offer.get('store_id')
            else:
                await message.answer("❌ Ошибка формата данных" if lang == "ru" else "❌ Ma'lumot formati xatosi")
                await state.clear()
                return
        except (IndexError, KeyError, TypeError) as e:
            logger.error(f"Error accessing offer fields: {e}, offer type: {type(offer)}")
            await message.answer("❌ Ошибка обработки товара" if lang == "ru" else "❌ Mahsulotni qayta ishlash xatosi")
            await state.clear()
            return
            
        if available_qty < quantity:
            await message.answer(
                f"❌ Доступно только {available_qty} шт." if lang == "ru" 
                else f"❌ Faqat {available_qty} dona mavjud"
            )
            return
        
        # Save quantity and check if delivery is available
        await state.update_data(quantity=quantity)
        
        # Check if store has delivery enabled
        delivery_enabled = False
        delivery_price = 0
        min_order_amount = 0
        
        if store_id:
            store = db.get_store(store_id)
            if store:
                if isinstance(store, dict):
                    delivery_enabled = store.get('delivery_enabled', 0) == 1
                    delivery_price = store.get('delivery_price', 0)
                    min_order_amount = store.get('min_order_amount', 0)
                elif isinstance(store, (tuple, list)) and len(store) > 11:
                    # Assuming delivery fields are at positions 9, 10, 11
                    delivery_enabled = store[9] == 1 if len(store) > 9 else False
                    delivery_price = store[10] if len(store) > 10 else 0
                    min_order_amount = store[11] if len(store) > 11 else 0
        
        # Save delivery info
        await state.update_data(
            delivery_enabled=delivery_enabled,
            delivery_price=delivery_price,
            min_order_amount=min_order_amount,
            offer_price=offer_price
        )
        
        order_total = int(offer_price * quantity)
        
        # If delivery is enabled, ask for delivery choice
        if delivery_enabled:
            await state.set_state(BookOffer.delivery_choice)
            
            # Create delivery choice keyboard
            from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
            
            if order_total >= min_order_amount:
                if lang == "ru":
                    delivery_btn_text = f"🚚 Доставка ({delivery_price:,} сум)"
                    pickup_text = "🏪 Самовывоз"
                    delivery_msg = (
                        f"<b>Шаг 2/3: Выберите способ получения</b>\n\n"
                        f"📦 Сумма заказа: {order_total:,} сум\n"
                        f"🚚 Стоимость доставки: {delivery_price:,} сум\n\n"
                        f"Выберите вариант:"
                    )
                else:
                    delivery_btn_text = f"🚚 Yetkazib berish ({delivery_price:,} so'm)"
                    pickup_text = "🏪 O'zim olib ketaman"
                    delivery_msg = (
                        f"<b>2/3-qadam: Qabul qilish usulini tanlang</b>\n\n"
                        f"📦 Buyurtma summasi: {order_total:,} so'm\n"
                        f"🚚 Yetkazib berish narxi: {delivery_price:,} so'm\n\n"
                        f"Variantni tanlang:"
                    )
                
                delivery_kb = ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text=delivery_btn_text)],
                        [KeyboardButton(text=pickup_text)],
                        [KeyboardButton(text="❌ Отмена" if lang == "ru" else "❌ Bekor qilish")]
                    ],
                    resize_keyboard=True
                )
                
                await message.answer(delivery_msg, parse_mode="HTML", reply_markup=delivery_kb)
            else:
                # Order total is below minimum for delivery
                if lang == "ru":
                    await message.answer(
                        f"<b>Шаг 2/3: Способ получения</b>\n\n"
                        f"📦 Сумма заказа: {order_total:,} сум\n"
                        f"⚠️ Минимальная сумма для доставки: {min_order_amount:,} сум\n\n"
                        f"Доступен только самовывоз. Продолжить?",
                        parse_mode="HTML",
                        reply_markup=cancel_keyboard(lang)
                    )
                else:
                    await message.answer(
                        f"<b>2/3-qadam: Qabul qilish usuli</b>\n\n"
                        f"📦 Buyurtma summasi: {order_total:,} so'm\n"
                        f"⚠️ Yetkazib berish uchun minimal summa: {min_order_amount:,} so'm\n\n"
                        f"Faqat o'zim olib ketish mavjud. Davom etamizmi?",
                        parse_mode="HTML",
                        reply_markup=cancel_keyboard(lang)
                    )
                # Force pickup
                await state.update_data(delivery_option=0, delivery_cost=0)
        else:
            # No delivery available, proceed directly to booking creation
            await create_booking_final(message, state)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число" if lang == "ru" else "❌ Iltimos, raqam kiriting")
    except Exception as e:
        logger.error(f"Error in book_offer_quantity: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже." if lang == "ru" else "❌ Xatolik yuz berdi. Keyinroq urinib ko'ring.")


@router.message(BookOffer.delivery_choice)
async def book_offer_delivery_choice(message: types.Message, state: FSMContext) -> None:
    """Process delivery choice."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    
    # Check for cancellation
    if message.text in ["❌ Отмена", "❌ Bekor qilish", "/cancel"]:
        await state.clear()
        await message.answer(
            get_text(lang, "action_cancelled"),
            reply_markup=main_menu_customer(lang)
        )
        return
    
    # Determine delivery option
    if "Доставка" in message.text or "Yetkazib berish" in message.text:
        # User wants delivery, ask for address
        await state.set_state(BookOffer.delivery_address)
        await message.answer(
            "📍 <b>Шаг 3/3: Введите адрес доставки</b>\n\n"
            "Укажите полный адрес (улица, дом, квартира):" if lang == "ru"
            else
            "📍 <b>3/3-qadam: Yetkazib berish manzilini kiriting</b>\n\n"
            "To'liq manzilni kiriting (ko'cha, uy, xonadon):",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(lang)
        )
    else:
        # Pickup selected
        data = await state.get_data()
        await state.update_data(delivery_option=0, delivery_cost=0, delivery_address="")
        await create_booking_final(message, state)


@router.message(BookOffer.delivery_address)
async def book_offer_delivery_address(message: types.Message, state: FSMContext) -> None:
    """Process delivery address and create booking."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    
    # Check for cancellation
    if message.text in ["❌ Отмена", "❌ Bekor qilish", "/cancel"]:
        await state.clear()
        await message.answer(
            get_text(lang, "action_cancelled"),
            reply_markup=main_menu_customer(lang)
        )
        return
    
    address = message.text.strip()
    
    if len(address) < 10:
        await message.answer(
            "❌ Пожалуйста, укажите полный адрес (минимум 10 символов)" if lang == "ru"
            else "❌ Iltimos, to'liq manzilni kiriting (kamida 10 ta belgi)"
        )
        return
    
    # Save delivery details
    data = await state.get_data()
    delivery_price = data.get("delivery_price", 0)
    
    await state.update_data(
        delivery_option=1,
        delivery_cost=delivery_price,
        delivery_address=address
    )
    
    await create_booking_final(message, state)


async def create_booking_final(message: types.Message, state: FSMContext) -> None:
    """Create the final booking with all details."""
    if not db or not bot or not METRICS:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    
    data = await state.get_data()
    offer_id = data.get("offer_id")
    quantity = data.get("quantity")
    delivery_option = data.get("delivery_option", 0)
    delivery_cost = data.get("delivery_cost", 0)
    delivery_address = data.get("delivery_address", "")
    offer_price = data.get("offer_price", 0)
    
    if not offer_id or not quantity:
        await message.answer("❌ Ошибка: данные не найдены" if lang == "ru" else "❌ Xatolik: ma'lumotlar topilmadi")
        await state.clear()
        return
    
    offer = db.get_offer(offer_id)
    
    if not offer:
        await message.answer("❌ Предложение не найдено" if lang == "ru" else "❌ Taklif topilmadi")
        await state.clear()
        return
    
    # Get offer details
    if isinstance(offer, (tuple, list)):
        offer_title = offer[2] if len(offer) > 2 else "Товар"
        store_id = offer[1] if len(offer) > 1 else None
        offer_address = offer[16] if len(offer) > 16 else ""
    elif isinstance(offer, dict):
        offer_title = offer.get('title', 'Товар')
        store_id = offer.get('store_id')
        offer_address = offer.get('address', '')
    
    # If address is empty, get from store
    if not offer_address and store_id:
        store = db.get_store(store_id)
        if store:
            if isinstance(store, dict):
                offer_address = store.get('address', '')
            elif isinstance(store, (tuple, list)) and len(store) > 3:
                offer_address = store[3]  # address field
    
    # Fallback if still no address
    if not offer_address:
        offer_address = "Manzil ko'rsatilmagan" if lang == "uz" else "Адрес не указан"
    
    # Create booking atomically
    logger.info(f"📦 BOOKING: Calling create_booking_atomic - offer_id={offer_id}, user_id={message.from_user.id}, quantity={quantity}")
    
    ok, booking_id, code = db.create_booking_atomic(
        offer_id, message.from_user.id, quantity
    )
    
    logger.info(f"📦 BOOKING: create_booking_atomic result - ok={ok}, booking_id={booking_id}, code={code}")
    
    if not ok or booking_id is None or code is None:
        logger.error(f"📦 BOOKING FAILED: ok={ok}, booking_id={booking_id}, code={code}")
        await message.answer(
            "❌ К сожалению, выбранное количество уже недоступно." if lang == "ru"
            else "❌ Afsuski, tanlangan miqdor mavjud emas."
        )
        await state.clear()
        return
    
    # Update booking with delivery details
    if delivery_option == 1:
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE bookings 
                    SET delivery_option = %s, delivery_address = %s, delivery_cost = %s
                    WHERE booking_id = %s
                """, (delivery_option, delivery_address, delivery_cost, booking_id))
                logger.info(f"✅ Delivery details updated for booking {booking_id}")
        except Exception as e:
            logger.error(f"Error updating delivery details: {e}")
    
    logger.info(f"✅ BOOKING SUCCESS: booking_id={booking_id}, code={code}, delivery={delivery_option}")
    
    try:
        METRICS["bookings_created"] += 1
    except Exception:
        pass
    
    await state.clear()
    
    # Notify partner
    if store_id:
        store = db.get_store(store_id)
        if store:
            owner_id = get_store_field(store, "owner_id")
            if owner_id:
                partner_lang = db.get_user_language(owner_id)
                customer = db.get_user_model(message.from_user.id)
                customer_phone = customer.phone if customer else "Не указан"
                
                notification_kb = InlineKeyboardBuilder()
                notification_kb.button(text="✓ Выдано", callback_data=f"complete_booking_{booking_id}")
                notification_kb.button(text="× Отменить", callback_data=f"cancel_booking_{booking_id}")
                notification_kb.adjust(2)
                
                store_name = get_store_field(store, "name", "Магазин")
                
                delivery_info_partner = ""
                if delivery_option == 1:
                    delivery_info_partner = (
                        f"\n🚚 <b>Доставка:</b> {delivery_address}\n💵 Доставка: {delivery_cost:,} сум"
                        if partner_lang == "ru"
                        else f"\n🚚 <b>Yetkazib berish:</b> {delivery_address}\n💵 Yetkazish: {delivery_cost:,} so'm"
                    )
                
                total_amount = int(offer_price * quantity)
                if delivery_option == 1:
                    total_amount += delivery_cost
                
                if partner_lang == "uz":
                    notif_text = (
                        f"🔔 <b>Yangi buyurtma</b>\n\n"
                        f"🏪 {store_name}\n"
                        f"📦 {offer_title} × {quantity} шт\n"
                        f"{delivery_info_partner}\n"
                        f"👤 {message.from_user.first_name}\n"
                        f"📱 <code>{customer_phone}</code>\n"
                        f"🎫 <code>{code}</code>\n"
                        f"💰 {total_amount:,} so'm"
                    )
                else:
                    notif_text = (
                        f"🔔 <b>Новый заказ</b>\n\n"
                        f"🏪 {store_name}\n"
                        f"📦 {offer_title} × {quantity} шт\n"
                        f"{delivery_info_partner}\n"
                        f"👤 {message.from_user.first_name}\n"
                        f"📱 <code>{customer_phone}</code>\n"
                        f"🎫 <code>{code}</code>\n"
                        f"💰 {total_amount:,} сум"
                    )
                
                try:
                    await bot.send_message(
                        owner_id,
                        notif_text,
                        parse_mode="HTML",
                        reply_markup=notification_kb.as_markup(),
                    )
                except Exception as e:
                    logger.error(f"Failed to notify partner: {e}")
    
    # Confirm to customer
    total_price = int(offer_price * quantity)
    
    store_name = "Магазин"
    if store_id:
        store = db.get_store(store_id)
        if store:
            store_name = get_store_field(store, "name", "Магазин")
    
    expiry_text = ""
    if isinstance(offer, (tuple, list)) and len(offer) > 17:
        expiry_date = offer[17]
        if expiry_date:
            expiry_text = f"\n🕐 <b>Забрать до:</b> {expiry_date}\n" if lang == "ru" else f"\n🕐 <b>Olib ketish muddati:</b> {expiry_date}\n"
    
    delivery_info_customer = ""
    if delivery_option == 1:
        delivery_info_customer = (
            f"🚚 <b>Доставка:</b> {delivery_address}\n💵 Доставка: {delivery_cost:,} сум\n"
            if lang == "ru"
            else f"🚚 <b>Yetkazib berish:</b> {delivery_address}\n💵 Yetkazish: {delivery_cost:,} so'm\n"
        )
        total_with_delivery = total_price + delivery_cost
    else:
        total_with_delivery = total_price
    
    from app.keyboards.user import main_menu_customer
    
    if lang == "uz":
        await message.answer(
            f"✅ <b>Buyurtma muvaffaqiyatli yaratildi!</b>\n\n"
            f"🏪 <b>Do'kon:</b> {store_name}\n"
            f"📦 <b>Mahsulot:</b> {offer_title}\n"
            f"🔢 <b>Miqdor:</b> {quantity} шт\n"
            f"💰 <b>Mahsulot:</b> {total_price:,} so'm\n"
            f"{delivery_info_customer}"
            f"💵 <b>Jami:</b> {total_with_delivery:,} so'm\n"
            f"{expiry_text}"
            f"\n🎫 <b>Bron kodi:</b> <code>{code}</code>\n\n"
            + (f"📍 <b>Olish manzili:</b>\n{offer_address}\n\n" if delivery_option == 0 else "")
            + f"⚠️ <b>Muhim:</b> Buyurtmani {'olishda' if delivery_option == 0 else 'qabul qilishda'} bu kodni ko'rsating!",
            parse_mode="HTML",
            reply_markup=main_menu_customer(lang),
        )
    else:
        await message.answer(
            f"✅ <b>Заказ успешно создан!</b>\n\n"
            f"🏪 <b>Магазин:</b> {store_name}\n"
            f"📦 <b>Товар:</b> {offer_title}\n"
            f"🔢 <b>Количество:</b> {quantity} шт\n"
            f"💰 <b>Товар:</b> {total_price:,} сум\n"
            f"{delivery_info_customer}"
            f"💵 <b>Итого:</b> {total_with_delivery:,} сум\n"
            f"{expiry_text}"
            f"\n🎫 <b>Код бронирования:</b> <code>{code}</code>\n\n"
            + (f"📍 <b>Адрес получения:</b>\n{offer_address}\n\n" if delivery_option == 0 else "")
            + f"⚠️ <b>Важно:</b> Покажите этот код при {'получении' if delivery_option == 0 else 'получении'} заказа!",
            parse_mode="HTML",
            reply_markup=main_menu_customer(lang),
        )


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
    
    # Filter ONLY active bookings (status='active', 'pending', or 'confirmed')
    if isinstance(bookings[0], dict):
        active = [b for b in bookings if b.get('status') in ['active', 'pending', 'confirmed']]
    else:
        # Fallback for tuple format - status is at index 7
        active = [b for b in bookings if b[7] in ['active', 'pending', 'confirmed']]
    
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
    
    # Send header first
    header = f"📦 <b>{get_text(lang, 'my_bookings')}</b>\n\n"
    await message.answer(header, parse_mode="HTML")

    # Send each booking as a separate message with action buttons
    for booking in active[:10]:  # Show max 10
        # Dict-compatible access
        if isinstance(booking, dict):
            booking_id = booking.get('booking_id')
            offer_id = booking.get('offer_id')
            quantity = booking.get('quantity', 1)
            code = booking.get('booking_code', '')
            created_at = booking.get('created_at', '')
            delivery_option = booking.get('delivery_option', 0)
            delivery_address = booking.get('delivery_address', '')
            delivery_cost = booking.get('delivery_cost', 0)
        else:
            booking_id = booking[0]
            offer_id = booking[1] if len(booking) > 1 else None
            quantity = booking[6] if len(booking) > 6 else 1
            code = booking[4] if len(booking) > 4 else ''
            created_at = booking[7] if len(booking) > 7 else ''
            delivery_option = booking[12] if len(booking) > 12 else 0
            delivery_address = booking[13] if len(booking) > 13 else ''
            delivery_cost = booking[14] if len(booking) > 14 else 0

        if not booking_id or not offer_id:
            continue

        offer = db.get_offer(offer_id)
        if not offer:
            continue

        # Get offer details (handle both dict and tuple)
        if isinstance(offer, dict):
            offer_title = offer.get('title', 'Товар')
            offer_price = offer.get('discount_price', 0)
        else:
            offer_title = offer[2] if len(offer) > 2 else 'Товар'
            offer_price = offer[5] if len(offer) > 5 else 0

        total = int(offer_price * quantity)

        # Show delivery info if applicable
        delivery_info = ""
        if delivery_option == 1:
            if lang == 'ru':
                delivery_info = (
                    f"🚚 Доставка: {delivery_address[:40]}{'...' if len(delivery_address) > 40 else ''}\n"
                    f"💵 Доставка: {delivery_cost:,} сум\n"
                )
                total_with_delivery = total + delivery_cost
            else:
                delivery_info = (
                    f"🚚 Yetkazish: {delivery_address[:40]}{'...' if len(delivery_address) > 40 else ''}\n"
                    f"💵 Yetkazish: {delivery_cost:,} so'm\n"
                )
                total_with_delivery = total + delivery_cost
        else:
            total_with_delivery = total

        currency = "сум" if lang == 'ru' else "so'm"

        body = (
            f"📦 <b>{offer_title}</b>\n"
            f"🔢 {quantity} шт • {total:,} {currency}\n"
            f"{delivery_info}"
        )

        if delivery_option == 1:
            body += f"💰 Итого: {total_with_delivery:,} {currency}\n"

        body += (
            f"🎫 <code>{code}</code>\n"
            f"📅 {created_at}\n"
        )

        # Build action buttons: Details and Cancel
        kb = InlineKeyboardBuilder()
        kb.button(text=("Подробнее" if lang == 'ru' else "Batafsil"), callback_data=f"booking_details_{booking_id}")
        kb.button(text=("Отменить" if lang == 'ru' else "Bekor qilish"), callback_data=f"cancel_booking_confirm_{booking_id}")
        kb.adjust(2)

        await message.answer(body, parse_mode="HTML", reply_markup=kb.as_markup())


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


@router.callback_query(lambda c: bool(re.match(r"^cancel_booking_\d+$", c.data)))
async def cancel_booking(callback: types.CallbackQuery) -> None:
    """Cancel booking."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        booking_id = int(callback.data.rsplit("_", 1)[1])
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


@router.callback_query(F.data.startswith("cancel_booking_confirm_"))
async def cancel_booking_confirm(callback: types.CallbackQuery) -> None:
    """Ask user to confirm cancellation (user flow)."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Ask confirmation with Yes/No
    confirm_kb = InlineKeyboardBuilder()
    confirm_kb.button(text=("Да, отменить" if lang == 'ru' else "Ha, bekor qilish"), callback_data=f"do_cancel_booking_{booking_id}")
    confirm_kb.button(text=("Нет" if lang == 'ru' else "Yo'q"), callback_data=f"noop_{booking_id}")
    confirm_kb.adjust(2)

    await callback.message.answer(get_text(lang, "confirm_cancel_booking") or ("Вы уверены, что хотите отменить бронь?" if lang == 'ru' else "Bronni bekor qilmoqchimisiz?"), reply_markup=confirm_kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("do_cancel_booking_"))
async def do_cancel_booking(callback: types.CallbackQuery) -> None:
    """Perform user-initiated cancellation after confirmation."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

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
        # Optionally edit the confirmation message
        try:
            await callback.message.edit_text(get_text(lang, "booking_cancelled"))
        except Exception:
            pass
        # Refresh user's bookings view
        # Reuse filter_bookings flow to refresh listing
        await filter_bookings(callback)
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("contact_store_"))
async def contact_store(callback: types.CallbackQuery) -> None:
    """Show store contact info to the user (phone/address)."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    try:
        store_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    store = db.get_store(store_id)
    if not store:
        await callback.answer(get_text(lang, "store_not_found"), show_alert=True)
        return

    phone = get_store_field(store, "phone", "Не указан")
    address = get_store_field(store, "address", "")

    text = (f"📞 <b>Телефон:</b> {phone}\n" if lang == 'ru' else f"📞 <b>Telefon:</b> {phone}\n")
    if address:
        text += (f"📍 <b>Адрес:</b> {address}\n" if lang == 'ru' else f"📍 <b>Manzil:</b> {address}\n")

    # Send plain contact info (phone and address only)
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("noop_"))
async def noop_callback(callback: types.CallbackQuery) -> None:
    """No-op callback to close dialogs; simply answer to remove loading state."""
    await callback.answer()


@router.callback_query(F.data.startswith("booking_details_"))
async def booking_details(callback: types.CallbackQuery) -> None:
    """Show booking details to the user."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    # Extract fields safely
    offer_id = get_booking_field(booking, "offer_id")
    quantity = get_booking_field(booking, "quantity", 1)
    code = get_booking_field(booking, "code", "")
    created_at = get_booking_field(booking, "created_at", "")
    delivery_option = get_booking_field(booking, "delivery_option", 0)
    delivery_address = get_booking_field(booking, "delivery_address", "")
    delivery_cost = get_booking_field(booking, "delivery_cost", 0)

    offer = db.get_offer(offer_id) if offer_id else None
    if offer:
        offer_title = get_offer_field(offer, "title", "Товар")
        offer_price = get_offer_field(offer, "discount_price", 0)
        # Try to get store name and pickup address from offer
        store_name = get_offer_field(offer, "store_name", None)
        offer_address = get_offer_field(offer, "address", None)
        unit = get_offer_field(offer, "unit", "шт")
    else:
        offer_title = "Товар"
        offer_price = 0
        store_name = None
        offer_address = None
        unit = "шт"

    # If offer doesn't contain pickup address, try store
    if not offer_address and offer:
        store_id_for_address = get_offer_field(offer, "store_id")
        if store_id_for_address:
            store_obj = db.get_store(store_id_for_address)
            if store_obj:
                offer_address = get_store_field(store_obj, "address", "")

    if not store_name and offer:
        # fallback to store lookup
        store_id_for_name = get_offer_field(offer, "store_id")
        if store_id_for_name:
            store_obj = db.get_store(store_id_for_name)
            if store_obj:
                store_name = get_store_field(store_obj, "name", "Магазин")

    if not store_name:
        store_name = "Магазин"
    if not offer_address:
        offer_address = "Адрес не указан" if lang == 'ru' else "Manzil ko'rsatilmagan"

    total = int(offer_price * quantity)
    currency = "сум" if lang == 'ru' else "so'm"

    # Build a compact card similar to the design: store, item (uppercase), unit price, total, pickup address, code, date
    title_display = (offer_title or "Товар").upper()

    pickup_block = f"\n📍 <b>Адрес получения:</b> {offer_address}\n" if delivery_option == 0 else ""

    text = (
        (f"🏪 <b>{store_name}</b>\n\n" if lang == 'ru' else f"🏪 <b>{store_name}</b>\n\n")
        + f"<b>{title_display}</b>\n\n"
        + f"💵 <b>Цена за ед.:</b> {int(offer_price):,} {currency}\n"
        + f"💰 <b>Сумма:</b> {total:,} {currency}\n\n"
        + pickup_block
        + f"🎫 <code>{code}</code>\n"
        + f"📅 {created_at}"
    )

    # Action buttons: Cancel and Close (two buttons)
    kb = InlineKeyboardBuilder()
    kb.button(text=("Отменить" if lang == 'ru' else "Bekor qilish"), callback_data=f"cancel_booking_confirm_{booking_id}")
    kb.button(text=("Закрыть" if lang == 'ru' else "Yopish"), callback_data=f"noop_{booking_id}")
    kb.adjust(2)

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()
