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

from aiogram import types as _ai_types

from handlers.bookings_utils import (
    _safe_edit_reply_markup,
    _safe_answer_or_send,
    can_proceed,
    get_store_field,
    get_offer_field,
    get_booking_field,
    get_bookings_filter_keyboard,
)

# This will be imported from bot.py
router = Router()


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
    assert callback.from_user is not None
    
    lang = db.get_user_language(callback.from_user.id)
    
    # Rate limit booking start
    if not can_proceed(callback.from_user.id, "book_start"):
        await callback.answer(get_text(lang, "operation_cancelled"), show_alert=True)
        return
    
    try:
        raw = callback.data or ""
        parts = raw.split("_")
        offer_id = int(parts[1]) if len(parts) > 1 else None
        if offer_id is None:
            raise ValueError("missing offer id")
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
    
    # Ask for quantity (backwards-compatible short prompt + detailed card)
    try:
        short_prompt = get_text(lang, "booking_how_many").format(max_qty=quantity)
        # Some clients/tests expect the shorter phrasing without the polite 'вы'
        short_prompt_simple = short_prompt.replace("вы ", "")
        detailed = get_text(lang, "booking_step_quantity").format(
            title=title,
            store_name=store_name,
            price=int(price),
            quantity=quantity,
            unit=unit,
        )

        # Send short prompt first to match legacy UX/tests, then detailed card
        await _safe_answer_or_send(callback.message, callback.from_user.id, short_prompt_simple, reply_markup=cancel_keyboard(lang))
        await _safe_answer_or_send(callback.message, callback.from_user.id, detailed, parse_mode="HTML", reply_markup=cancel_keyboard(lang))
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
    
    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    
    # Rate limit booking confirm
    if not can_proceed(message.from_user.id, "book_confirm"):
        await message.answer(get_text(lang, "operation_cancelled"))
        return
    
    # Normalize incoming text safely
    raw_text = message.text or ""

    # Check for cancellation
    if raw_text in ["❌ Отмена", "❌ Bekor qilish", "/cancel"]:
        await state.clear()
        await message.answer(
            get_text(lang, "action_cancelled"),
            reply_markup=main_menu_customer(lang)
        )
        return

    try:
        logger.info(f"📦 BOOKING: User {message.from_user.id} entered quantity: {raw_text}")
        
        try:
            quantity = int(raw_text)
        except Exception:
            raise ValueError
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

            # Ensure min_order_amount is an int for comparison
            try:
                min_order_amount = int(min_order_amount or 0)
            except Exception:
                min_order_amount = 0

            if order_total >= min_order_amount:
                if lang == "ru":
                    delivery_btn_text = f"🚚 Доставка ({delivery_price:,} сум)"
                    pickup_text = "🏪 Самовывоз"
                    delivery_msg = (
                        f"📦 Сумма заказа: {order_total:,} сум\n"
                        f"🚚 Стоимость доставки: {delivery_price:,} сум\n\n"
                        f"Выберите вариант:"
                    )
                else:
                    delivery_btn_text = f"🚚 Yetkazib berish ({delivery_price:,} so'm)"
                    pickup_text = "🏪 O'zim olib ketaman"
                    delivery_msg = (
                        f"📦 Buyurtma summasi: {order_total:,} so'm\n"
                        f"🚚 Yetkazib berish narxi: {delivery_price:,} so'm\n\n"
                        f"Variantni tanlang:"
                    )

                from aiogram.utils.keyboard import InlineKeyboardBuilder

                # Build inline buttons for delivery / pickup to avoid text matching and
                # allow removing buttons after selection.
                ikb = InlineKeyboardBuilder()
                ikb.button(text=delivery_btn_text, callback_data="choose_delivery")
                ikb.button(text=pickup_text, callback_data="choose_pickup")
                ikb.button(text=("❌ Отмена" if lang == "ru" else "❌ Bekor qilish"), callback_data="choose_cancel")
                ikb.adjust(2, 1)

                await message.answer(delivery_msg, parse_mode="HTML", reply_markup=ikb.as_markup())
                # Wait for user's callback (inline). Do not proceed to booking yet.
                return
            else:
                # Order total is below minimum for delivery — show inline confirmation for pickup
                # (better UX than free-text). We'll set delivery_option to pickup and wait
                # for user's inline confirmation.
                from aiogram.utils.keyboard import InlineKeyboardBuilder

                confirm_kb = InlineKeyboardBuilder()
                yes_text = "Да" if lang == 'ru' else "Ha"
                no_text = "Нет" if lang == 'ru' else "Yo'q"
                confirm_kb.button(text=yes_text, callback_data="confirm_pickup_yes")
                confirm_kb.button(text=no_text, callback_data="confirm_pickup_no")
                confirm_kb.adjust(2)

                if lang == "ru":
                    msg = (
                        f"📦 Сумма заказа: {order_total:,} сум\n"
                        f"⚠️ Минимальная сумма для доставки: {min_order_amount:,} сум\n\n"
                        f"Доступен только самовывоз. Продолжить?"
                    )
                else:
                    msg = (
                        f"📦 Buyurtma summasi: {order_total:,} so'm\n"
                        f"⚠️ Yetkazib berish uchun minimal summa: {min_order_amount:,} so'm\n\n"
                        f"Faqat o'zim olib ketish mavjud. Davom etamizmi?"
                    )

                # Force pickup in state now; create_booking_final will be called when user confirms
                await state.update_data(delivery_option=0, delivery_cost=0)
                await message.answer(msg, parse_mode="HTML", reply_markup=confirm_kb.as_markup())
                # Wait for the inline confirmation callback before creating the booking
                return
        else:
            # No delivery available, proceed directly to booking creation
            await create_booking_final(message, state)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число" if lang == "ru" else "❌ Iltimos, raqam kiriting")
    except Exception as e:
        logger.error(f"Error in book_offer_quantity: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже." if lang == "ru" else "❌ Xatolik yuz berdi. Keyinroq urinib ko'ring.")

    # No implicit pickup fallback here — user must explicitly choose pickup or delivery address.


@router.message(BookOffer.delivery_address)
async def book_offer_delivery_address(message: types.Message, state: FSMContext) -> None:
    """Process delivery address and create booking."""
    if not db:
        await message.answer("System error")
        return
    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    
    # Check for cancellation
    if message.text in ["❌ Отмена", "❌ Bekor qilish", "/cancel"]:
        await state.clear()
        await message.answer(
            get_text(lang, "action_cancelled"),
            reply_markup=main_menu_customer(lang)
        )
        return
    
    raw_addr = message.text or ""
    address = raw_addr.strip()
    
    if len(address) < 10:
        await message.answer(
            "❌ Пожалуйста, укажите полный адрес (минимум 10 символов)" if lang == "ru"
            else "❌ Iltimos, to'liq manzilni kiriting (kamida 10 ta belgi)"
        )
        return
    
    # Move user into the OrderDelivery flow (use `orders` handlers) instead of
    # creating a booking in `bookings` table. We preserve quantity and offer_id
    # already stored in the state and set the order address + move to payment_proof.
    try:
        data = await state.get_data()
        delivery_price = data.get("delivery_price", 0)
        offer_id = data.get("offer_id")
        quantity = data.get("quantity")

        # Ensure we have required fields
        if not offer_id or not quantity:
            await message.answer(get_text(lang, "error"))
            await state.clear()
            return

        store_id = None
        offer = db.get_offer(offer_id)
        if offer:
            store_id = get_offer_field(offer, "store_id")

        # Prepare state data for OrderDelivery handlers
        from handlers.common_states.states import OrderDelivery as _OrderDelivery

        await state.update_data(
            offer_id=offer_id,
            store_id=store_id,
            quantity=quantity,
            address=address,
            delivery_price=delivery_price,
        )
        # Move to order payment proof step (orders handler will create order on photo)
        await state.set_state(_OrderDelivery.payment_proof)

        if lang == 'ru':
            prompt = (
                "📸 Пожалуйста, отправьте фото чека или подтверждение оплаты для доставки\n\n"
                "Если вы оплатили картой/онлайн, пришлите фото квитанции."
            )
        else:
            prompt = (
                "📸 Iltimos, yetkazib berish uchun to'lov kvitansiyasi yoki chek rasmini yuboring\n\n"
                "Agar onlayn to'lov qilgan bo'lsangiz, kvitansiya rasmini yuboring."
            )

        await message.answer(prompt, reply_markup=cancel_keyboard(lang))
    except Exception as e:
        logger.error(f"Error switching to OrderDelivery flow: {e}")
        await message.answer(get_text(lang, "error"))
        await state.clear()


@router.message(BookOffer.delivery_receipt, F.photo)
async def book_offer_delivery_receipt_photo(message: types.Message, state: FSMContext) -> None:
    """Receive photo for delivery payment proof and create booking."""
    if not db:
        await message.answer("System error")
        return
    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    # Get the highest-quality photo file_id
    photo = None
    if message.photo:
        photo = message.photo[-1].file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith('image/'):
        photo = message.document.file_id

    if not photo:
        await message.answer(
            "❌ Пожалуйста, отправьте фото (фото/документ с изображением)" if lang == 'ru' else "❌ Iltimos, rasm yuboring"
        )
        return

    logger.info(f"📷 Received delivery payment proof from user {message.from_user.id}: file_id={photo}")

    # Create an `orders` record (use orders flow) instead of a booking in `bookings`.
    try:
        data = await state.get_data()
        offer_id = data.get("offer_id")
        quantity = data.get("quantity")
        address = data.get("delivery_address") or data.get("address")

        if not offer_id or not quantity or not address:
            await message.answer(get_text(lang, "error"))
            await state.clear()
            return

        offer = db.get_offer(offer_id)
        store_id = get_offer_field(offer, "store_id") if offer else None
        store = db.get_store(store_id) if store_id else None
        delivery_price = get_store_field(store, "delivery_price", 0)

        # Create order
        order_id = db.create_order(
            user_id=message.from_user.id,
            store_id=store_id,
            offer_id=offer_id,
            quantity=quantity,
            order_type="delivery",
            delivery_address=address,
            delivery_price=delivery_price,
            payment_method="card",
        )

        if not order_id:
            await message.answer(
                "❌ " + ("Ошибка создания заказа" if lang == "ru" else "Buyurtma yaratishda xatolik")
            )
            await state.clear()
            return

        # Update payment status with the photo id
        try:
            db.update_payment_status(order_id, "pending", photo)
        except Exception:
            pass

        # Decrement offer quantity atomically
        try:
            db.increment_offer_quantity_atomic(offer_id, -int(quantity))
        except Exception as e:
            logger.error(f"Failed to decrement offer {offer_id} by {quantity}: {e}")

        customer = db.get_user_model(message.from_user.id)
        customer_phone = customer.phone if customer else "Не указан"

        currency_ru = "сум"
        currency_uz = "so'm"
        unit_ru = "шт"
        unit_uz = "dona"

        notification_kb = InlineKeyboardBuilder()
        notification_kb.button(
            text="✅ " + ("Подтвердить оплату" if lang == "ru" else "To'lovni tasdiqlash"),
            callback_data=f"confirm_payment_{order_id}",
        )
        notification_kb.button(
            text="❌ " + ("Отклонить" if lang == "ru" else "Rad etish"),
            callback_data=f"reject_payment_{order_id}",
        )
        notification_kb.adjust(2)

        # Send photo + notification to owner
        owner_id = get_store_field(store, "owner_id") if store else None
        store_name = get_store_field(store, "name", "Магазин") if store else "Магазин"
        offer_title = get_offer_field(offer, "title", "") if offer else ""

        try:
            if owner_id:
                # Build caption safely to avoid nested-quote f-string issues
                caption_lines = []
                caption_lines.append(
                    f"🔔 <b>{'Новый заказ с доставкой!' if lang == 'ru' else 'Yangi buyurtma yetkazib berish bilan!'}</b>"
                )
                caption_lines.append("")
                caption_lines.append(f"🏪 {store_name}")
                caption_lines.append(f"🍽 {offer_title}")
                caption_lines.append(f"📦 {'Количество' if lang == 'ru' else 'Miqdor'}: {quantity} {unit_ru if lang == 'ru' else unit_uz}")
                caption_lines.append(f"👤 {message.from_user.first_name}")
                caption_lines.append(f"📱 {'Телефон' if lang == 'ru' else 'Telefon'}: <code>{customer_phone}</code>")
                caption_lines.append(f"📍 {'Адрес' if lang == 'ru' else 'Manzil'}: {address}")
                caption_lines.append(
                    f"💰 {'Итого' if lang == 'ru' else 'Jami'}: {(get_offer_field(offer, 'discount_price', 0) * int(quantity)) + delivery_price:,} {currency_ru if lang == 'ru' else currency_uz}"
                )
                caption_lines.append("")
                caption_lines.append(
                    "📸 " + ("Скриншот оплаты выше" if lang == 'ru' else "To'lov skrinsho yuqorida")
                )
                caption_text = "\n".join(caption_lines)

                await bot.send_photo(
                    chat_id=owner_id,
                    photo=photo,
                    caption=caption_text,
                    parse_mode="HTML",
                    reply_markup=notification_kb.as_markup(),
                )
        except Exception as e:
            logger.error(f"Failed to notify owner about order {order_id}: {e}")

        # Inform customer
        total_amount = (get_offer_field(offer, "discount_price", 0) * int(quantity)) + delivery_price
        confirm_text = 'Ожидайте подтверждения оплаты от магазина' if lang == 'ru' else "Do'kon dan to'lovni tasdiqlashni kuting"

        await message.answer(
            f"✅ <b>{'Заказ оформлен!' if lang == 'ru' else 'Buyurtma qabul qilindi!'}</b>\n\n"
            f"📦 {'Заказ' if lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"🍽 {offer_title}\n"
            f"📦 {'Количество' if lang == 'ru' else 'Miqdor'}: {quantity} {unit_ru if lang == 'ru' else unit_uz}\n"
            f"📍 {'Адрес доставки' if lang == 'ru' else 'Yetkazib berish manzili'}: {address}\n"
            f"💵 {'Итого' if lang == 'ru' else 'Jami'}: <b>{total_amount:,} {currency_ru if lang == 'ru' else currency_uz}</b>\n\n"
            f"{confirm_text}",
            parse_mode="HTML",
        )

        await state.clear()

    except Exception as e:
        logger.error(f"Error creating order from delivery receipt: {e}")
        await message.answer(get_text(lang, "error"))
        await state.clear()

@router.message(BookOffer.delivery_receipt)
async def book_offer_delivery_receipt_fallback(message: types.Message, state: FSMContext) -> None:
    """Fallback when user sends non-photo during receipt step."""
    assert message.from_user is not None
    lang = 'ru'
    try:
        lang = db.get_user_language(message.from_user.id)
    except Exception:
        pass

    await message.answer(
        "❗ Пожалуйста, отправьте фото чека или нажмите ❌ Отмена" if lang == 'ru' else "❗ Iltimos, kvitansiya rasmini yuboring yoki ❌ Bekor qilish tugmasini bosing",
        reply_markup=cancel_keyboard(lang)
    )


@router.callback_query(F.data == "confirm_pickup_yes")
async def confirm_pickup_yes(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User confirmed pickup (inline). Proceed with booking creation using stored FSM data."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    assert callback.from_user is not None
    await callback.answer()
    try:
        # Remove inline keyboard so buttons disappear (safe)
        await _safe_edit_reply_markup(callback.message, reply_markup=None)

        # callback.message is the message with the inline keyboard; ensure it's a real Message
        from aiogram import types as _ai_types
        if isinstance(callback.message, _ai_types.Message):
            await create_booking_final(callback.message, state)
        else:
            # Fallback: send a new message to the user and use it for replies
            try:
                if bot:
                    new_msg = await bot.send_message(callback.from_user.id, "Продолжаю обработку брони...")
                    await create_booking_final(new_msg, state)
                else:
                    # As a last resort, inform via callback answer
                    await callback.answer("Продолжаю обработку брони...", show_alert=True)
                    return
            except Exception:
                raise
    except Exception as e:
        logger.error(f"Error in confirm_pickup_yes: {e}")
        lang = db.get_user_language(callback.from_user.id) if db else 'ru'
        try:
            from aiogram import types as _ai_types
            if isinstance(callback.message, _ai_types.Message):
                await _safe_answer_or_send(callback.message, callback.from_user.id, "❌ Произошла ошибка. Попробуйте позже." if lang == 'ru' else "❌ Xatolik yuz berdi. Keyinroq urinib ko'ring.")
            else:
                await bot.send_message(callback.from_user.id, "❌ Произошла ошибка. Попробуйте позже.")
        except Exception:
            pass


@router.callback_query(F.data == "confirm_pickup_no")
async def confirm_pickup_no(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User declined pickup confirmation; clear state and show main menu."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    await state.clear()
    # Remove inline keyboard first (safe)
    await _safe_edit_reply_markup(callback.message, reply_markup=None)
    from app.keyboards.user import main_menu_customer
    try:
        await _safe_answer_or_send(callback.message, callback.from_user.id, get_text(lang, "action_cancelled"), reply_markup=main_menu_customer(lang))
    except Exception:
        pass
    await callback.answer()


async def create_booking_final(message: types.Message, state: FSMContext) -> None:
    """Create the final booking with all details."""
    if not db or not bot or not METRICS:
        await message.answer("System error")
        return
    assert message.from_user is not None
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
    
    # Get offer details (set defaults first to avoid unbound vars)
    offer_title = "Товар"
    store_id: int | None = None
    offer_address = ""
    if isinstance(offer, (tuple, list)):
        offer_title = offer[2] if len(offer) > 2 else offer_title
        store_id = offer[1] if len(offer) > 1 else store_id
        offer_address = offer[16] if len(offer) > 16 else offer_address
    elif isinstance(offer, dict):
        offer_title = offer.get('title', offer_title)
        store_id = offer.get('store_id')
        offer_address = offer.get('address', offer_address)
    
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
    # Check per-user active booking limit before attempting atomic create
    try:
        active_bookings = db.get_user_bookings(message.from_user.id) or []
        active_count = 0
        if isinstance(active_bookings, list):
            if len(active_bookings) > 0 and isinstance(active_bookings[0], dict):
                active_count = sum(1 for b in active_bookings if b.get('status') in ['active', 'pending', 'confirmed'])
            else:
                # tuple format: status at index 7 (fallback)
                active_count = sum(1 for b in active_bookings if (len(b) > 7 and b[7] in ['active', 'pending', 'confirmed']))
        else:
            active_count = 0
    except Exception:
        active_count = 0

    try:
        import os
        max_allowed = int(os.environ.get('MAX_ACTIVE_BOOKINGS_PER_USER', '3'))
    except Exception:
        max_allowed = 3

    if active_count >= max_allowed:
        # Localized message
        if lang == 'uz':
            await message.answer(
                f"❌ Sizda allaqachon {active_count} faol bron mavjud (maksimum {max_allowed}). Iltimos, avvalgi bronlarni bekor qiling yoki kuting.")
        else:
            await message.answer(
                f"❌ У вас уже {active_count} активных бронирований (максимум {max_allowed}). Пожалуйста, отмените предыдущие брони или подождите.")
        await state.clear()
        return

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
            payment_proof = data.get('payment_proof_photo_id')
            # Try to set payment proof via DB helper (both adapters)
            if payment_proof and db:
                try:
                    db.set_booking_payment_proof(booking_id, payment_proof)
                except Exception:
                    pass

            # Also update delivery_option/address/cost using existing connection if available
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE bookings 
                        SET delivery_option = %s, delivery_address = %s, delivery_cost = %s
                        WHERE booking_id = %s
                    """, (delivery_option, delivery_address, delivery_cost, booking_id))
                    logger.info(f"✅ Delivery details updated for booking {booking_id}")
            except Exception:
                # best-effort: ignore if adapter doesn't expose get_connection
                pass
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

                # Partner should confirm the booking first. Offer Confirm / Reject buttons.
                notification_kb = InlineKeyboardBuilder()
                notification_kb.button(text=("Подтвердить" if partner_lang == 'ru' else "Tasdiqlash"), callback_data=f"partner_confirm_{booking_id}")
                notification_kb.button(text=("Отклонить" if partner_lang == 'ru' else "Rad etish"), callback_data=f"partner_reject_{booking_id}")
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
                # Safe booking code display to avoid showing 'None'
                code_display = code if code else str(booking_id)

                # Try to fetch payment proof from DB (booking was updated earlier)
                try:
                    booking_db = db.get_booking(booking_id) or {}
                    payment_proof = get_booking_field(booking_db, 'payment_proof_photo_id', None)
                except Exception:
                    payment_proof = None

                if partner_lang == "uz":
                    notif_text = (
                        f"🔔 <b>Yangi buyurtma</b>\n\n"
                        f"🏪 {store_name}\n"
                        f"📦 {offer_title} × {quantity} шт\n"
                        f"{delivery_info_partner}\n"
                        f"👤 {message.from_user.first_name}\n"
                        f"📱 <code>{customer_phone}</code>\n"
                        f"🎫 <code>{code_display}</code>\n"
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
                        f"🎫 <code>{code_display}</code>\n"
                        f"💰 {total_amount:,} сум"
                    )

                try:
                    # If payment proof exists and looks like a Telegram file_id, send as photo with caption
                    if payment_proof and isinstance(payment_proof, str):
                        try:
                            await bot.send_photo(owner_id, payment_proof, caption=notif_text, parse_mode="HTML", reply_markup=notification_kb.as_markup())
                        except Exception:
                            # Fallback to text if send_photo fails
                            await _safe_answer_or_send(None, owner_id, notif_text, parse_mode="HTML", reply_markup=notification_kb.as_markup())
                    else:
                        await _safe_answer_or_send(None, owner_id, notif_text, parse_mode="HTML", reply_markup=notification_kb.as_markup())
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

    # Add generic auto-cancel notice based on booking duration config
    try:
        import os
        duration_hours = int(os.environ.get('BOOKING_DURATION_HOURS', '2'))
    except Exception:
        duration_hours = 2

    if lang == 'ru':
        auto_cancel_notice = f"\n⚠️ <b>Важно:</b> Бронь будет автоматически отменена через {duration_hours} часов, если вы не заберёте заказ."
    else:
        auto_cancel_notice = f"\n⚠️ <b>Diqqat:</b> Bron {duration_hours} soat ichida avtomatik bekor qilinadi, agar buyurtma olinmasa."
    
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
    
    # Inform customer that booking is pending partner confirmation (do not expose code yet)
    if lang == "uz":
        await message.answer(
            f"⏳ <b>Buyurtma yuborildi!</b>\n\n"
            f"🏪 <b>Do'kon:</b> {store_name}\n"
            f"📦 <b>Mahsulot:</b> {offer_title}\n"
            f"🔢 <b>Miqdor:</b> {quantity} шт\n"
            f"💰 <b>Mahsulot:</b> {total_price:,} so'm\n"
            f"{delivery_info_customer}"
            f"💵 <b>Jami:</b> {total_with_delivery:,} so'm\n\n"
            f"⚠️ <b>Diqqat:</b> Buyurtma sotuvchiga tasdiqlash uchun yuborildi. Kod va yakuniy ma'lumotlar sotuvchi tasdiqlagach yuboriladi.",
            parse_mode="HTML",
            reply_markup=main_menu_customer(lang),
        )
    else:
        await message.answer(
            f"⏳ <b>Заказ отправлен на подтверждение</b>\n\n"
            f"🏪 <b>Магазин:</b> {store_name}\n"
            f"📦 <b>Товар:</b> {offer_title}\n"
            f"🔢 <b>Количество:</b> {quantity} шт\n"
            f"💰 <b>Товар:</b> {total_price:,} сум\n"
            f"{delivery_info_customer}"
            f"💵 <b>Итого:</b> {total_with_delivery:,} сум\n\n"
            f"⚠️ <b>Важно:</b> Заказ отправлен продавцу на подтверждение. Код бронирования и финальная информация будут высланы после подтверждения.",
            parse_mode="HTML",
            reply_markup=main_menu_customer(lang),
        )


@router.message(BookOffer.delivery_choice)
async def book_offer_delivery_choice(message: types.Message, state: FSMContext) -> None:
    """Process delivery choice."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
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
    # This handler remains for backward compatibility if a reply keyboard/text option
    # is used. Prefer inline callbacks (choose_delivery / choose_pickup) which are
    # handled in dedicated callback handlers below.
    txt = (message.text or "")
    if any(k in txt for k in ["Доставка", "Yetkazib berish"]):
        # User wants delivery, ask for address
        await state.set_state(BookOffer.delivery_address)
        await message.answer(
            "📍 Введите адрес доставки\n\nУкажите полный адрес (улица, дом, квартира):" if lang == "ru"
            else "📍 Manzilni kiriting\n\nTo'liq manzilni kiriting (ko'cha, uy, xonadon):",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(lang)
        )
        return

    # Pickup selected (text)
    if any(k in txt for k in ["Самовывоз", "O'zim olib ketaman"]):
        data = await state.get_data()
        await state.update_data(delivery_option=0, delivery_cost=0, delivery_address="")
        await create_booking_final(message, state)


@router.callback_query(
    lambda c: (c.data or "") in ["bookings_active", "bookings_completed", "bookings_cancelled"]
)
async def filter_bookings(callback: types.CallbackQuery) -> None:
    """Filter bookings by status."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    status_map = {
        "bookings_active": "active",
        "bookings_completed": "completed",
        "bookings_cancelled": "cancelled",
    }
    status = status_map.get(callback.data or "", "active")
    
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
        booking_code_display = booking_code if booking_code else ''
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
            f"🎫 <code>{booking_code_display}</code>\n"
            f"📅 {created_at}\n\n"
        )
    
    # Use safe helper to edit existing message or send a new one
    await _safe_answer_or_send(callback.message, callback.from_user.id, text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "choose_delivery")
async def choose_delivery(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User chose delivery via inline button — ask for address."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    await callback.answer()
    lang = db.get_user_language(callback.from_user.id)
    # Remove inline keyboard (safe)
    await _safe_edit_reply_markup(callback.message, reply_markup=None)

    # Redirect to orders delivery flow instead of creating a booking in `bookings`.
    # We reuse the existing OrderDelivery FSM and handlers in `handlers/orders.py`.
    # Pull offer_id from the state (set earlier in booking start) and initialize order flow.
    try:
        data = await state.get_data()
        offer_id = data.get("offer_id")
        if not offer_id:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        offer = db.get_offer(offer_id)
        if not offer:
            await callback.answer(get_text(lang, "no_offers"), show_alert=True)
            return

        # Ensure store supports delivery
        store_id = get_offer_field(offer, "store_id")
        store = db.get_store(store_id) if store_id else None
        delivery_enabled = False
        if store:
            delivery_enabled = get_store_field(store, "delivery_enabled", 0) == 1

        if not delivery_enabled:
            await callback.answer(
                "❌ " + ("Доставка недоступна для этого магазина" if lang == "ru" else "Ushbu do'kon uchun yetkazib berish mavjud emas"),
                show_alert=True,
            )
            return

        # Initialize order state: store offer_id and store_id
        from handlers.common_states.states import OrderDelivery as _OrderDelivery

        # Preserve existing quantity if user already provided it in BookOffer.quantity
        data = await state.get_data()
        existing_quantity = data.get("quantity")

        await state.update_data(offer_id=offer_id, store_id=store_id)

        # If quantity already provided, skip asking for it again and ask for address
        if existing_quantity:
            await state.update_data(quantity=existing_quantity)
            await state.set_state(_OrderDelivery.address)

            if lang == 'ru':
                addr_prompt = (
                    "📍 Укажите адрес доставки:\n\nПример: ул. Амиры Темура 15, квартира 25"
                )
            else:
                addr_prompt = (
                    "📍 Yetkazib berish manzilini ko'rsating:\n\nMasalan: Amir Temur ko'chasi 15, kvartira 25"
                )

            from aiogram import types as _ai_types
            if isinstance(callback.message, _ai_types.Message):
                await callback.message.answer(addr_prompt, reply_markup=cancel_keyboard(lang))
            else:
                await callback.answer(get_text(lang, "please_open_chat") if hasattr(get_text, '__call__') else "Please open the chat to continue", show_alert=True)
            return

        # No existing quantity — proceed to ask quantity (order flow)
        await state.set_state(_OrderDelivery.quantity)

        # Send quantity prompt similar to orders.order_delivery_start
        from aiogram import types as _ai_types
        msg = callback.message if isinstance(callback.message, _ai_types.Message) else None

        unit_ru = "шт"
        unit_uz = "dona"
        currency_ru = "сум"
        currency_uz = "so'm"
        quantity_available = get_offer_field(offer, "quantity", 0)
        discount_price = get_offer_field(offer, "discount_price", 0)
        title = get_offer_field(offer, "title", "")

        if msg:
            await msg.answer(
                f"🍽 <b>{title}</b>\n\n"
                f"📦 {'Доступно' if lang == 'ru' else 'Mavjud'}: {quantity_available} {unit_ru if lang == 'ru' else unit_uz}\n"
                f"💰 {'Цена за 1 шт' if lang == 'ru' else '1 dona narxi'}: {int(discount_price):,} {currency_ru if lang == 'ru' else currency_uz}\n\n"
                f"{'Сколько вы хотите заказать?' if lang == 'ru' else 'Nechta buyurtma qilasiz?'} (1-{quantity_available})",
                parse_mode="HTML",
                reply_markup=cancel_keyboard(lang),
            )
        else:
            await callback.answer(get_text(lang, "please_open_chat") if hasattr(get_text, '__call__') else "Please open the chat to continue", show_alert=True)

    except Exception as e:
        logger.error(f"Error redirecting to order flow: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data == "choose_pickup")
async def choose_pickup(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User chose pickup via inline button — proceed to create booking."""
    if not db or not bot or not METRICS:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    await callback.answer()
    # Remove inline keyboard (safe)
    await _safe_edit_reply_markup(callback.message, reply_markup=None)

    # Set pickup option and create booking
    await state.update_data(delivery_option=0, delivery_cost=0, delivery_address="")
    try:
        from aiogram import types as _ai_types
        if isinstance(callback.message, _ai_types.Message):
            await create_booking_final(callback.message, state)
        else:
            new_msg = await bot.send_message(callback.from_user.id, "Продолжаю обработку брони...")
            await create_booking_final(new_msg, state)
    except Exception as e:
        logger.error(f"Error creating booking after pickup: {e}")
        lang = db.get_user_language(callback.from_user.id)
        try:
            from aiogram import types as _ai_types
            if isinstance(callback.message, _ai_types.Message):
                await _safe_answer_or_send(callback.message, callback.from_user.id, "❌ Произошла ошибка. Попробуйте позже." if lang == 'ru' else "❌ Xatolik yuz berdi. Keyinroq urinib ko'ring.")
            else:
                await bot.send_message(callback.from_user.id, "❌ Произошла ошибка. Попробуйте позже.")
        except Exception:
            pass


@router.callback_query(F.data == "choose_cancel")
async def choose_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User cancelled delivery choice via inline button."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    await callback.answer()
    await _safe_edit_reply_markup(callback.message, reply_markup=None)
    await state.clear()
    lang = db.get_user_language(callback.from_user.id)
    from app.keyboards.user import main_menu_customer
    try:
        await _safe_answer_or_send(callback.message, callback.from_user.id, get_text(lang, "action_cancelled"), reply_markup=main_menu_customer(lang))
    except Exception:
        pass


@router.callback_query(lambda c: bool(re.match(r"^cancel_booking_\d+$", (c.data or ""))))
async def cancel_booking(callback: types.CallbackQuery) -> None:
    """Cancel booking."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    assert callback.from_user is not None
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
        # Return quantity to offer (atomic increment to avoid race conditions)
        offer_id = get_booking_field(booking, "offer_id", 1)
        quantity = get_booking_field(booking, "quantity", 6)
        try:
            db.increment_offer_quantity_atomic(offer_id, int(quantity or 0))
        except Exception as e:
            logger.error(f"Failed to increment offer quantity for offer {offer_id}: {e}")

        await callback.answer(get_text(lang, "booking_cancelled"), show_alert=True)
        # Refresh message
        await filter_bookings(callback)
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("partner_confirm_"))
async def partner_confirm(callback: types.CallbackQuery) -> None:
    """Partner confirms a pending booking; set status to 'confirmed' and notify customer."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int((callback.data or "").rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    try:
        db.update_booking_status(booking_id, 'confirmed')
    except Exception as e:
        logger.error(f"Failed to update booking status to confirmed: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Mark reminder_sent to avoid worker sending reminders after partner confirmation
    try:
        if db:
            db.mark_reminder_sent(booking_id)
    except Exception:
        pass

    # Re-fetch booking to ensure we have the booking_code generated/stored by DB
    try:
        booking = db.get_booking(booking_id) or booking
    except Exception:
        # fallback to previously-read booking if re-fetch fails
        pass

    # Notify customer that partner confirmed
    user_id = get_booking_field(booking, 'user_id')
    code = get_booking_field(booking, 'code')
    # Fallback display for missing code: use a placeholder to avoid 'None' in messages
    code_display = code if code else str(booking_id)
    try:
        customer_lang = db.get_user_language(user_id) if user_id and db else 'ru'
        # Check if booking is delivery or pickup to vary the message
        delivery_opt = get_booking_field(booking, 'delivery_option', 0)
        if int(delivery_opt or 0) == 1:
            # For delivery: inform customer that seller confirmed and ask them to confirm receipt after delivery
            if customer_lang == 'ru':
                confirm_text = (
                    f"✅ Ваша бронь <code>{code_display}</code> подтверждена продавцом. Продавец оформил доставку. После получения заказа, пожалуйста, подтвердите получение кнопкой ниже."
                )
                confirm_btn_text = "Подтвердить получение"
            else:
                confirm_text = (
                    f"✅ Sizning broningiz <code>{code_display}</code> sotuvchi tomonidan tasdiqlandi. Sotuvchi yetkazib berishni boshlaydi. Buyurtmani olganingizdan so'ng, iltimos, quyidagi tugma orqali qabul qilganingizni tasdiqlang."
                )
                confirm_btn_text = "Qabul qildim"

            # Inline keyboard for customer to confirm receipt
            from aiogram.utils.keyboard import InlineKeyboardBuilder as _IKB
            cust_kb = _IKB()
            cust_kb.button(text=confirm_btn_text, callback_data=f"customer_received_{booking_id}")
            cust_kb.adjust(1)

            try:
                await bot.send_message(user_id, confirm_text, parse_mode='HTML', reply_markup=cust_kb.as_markup())
            except Exception:
                # Fallback without keyboard
                await bot.send_message(user_id, confirm_text, parse_mode='HTML')
        else:
            # Pickup: ask to pick up within booking duration (existing behavior)
            hours = int(__import__('os').environ.get('BOOKING_DURATION_HOURS','2'))
            if customer_lang == 'ru':
                confirm_text = (
                    f"✅ Ваша бронь <code>{code_display}</code> подтверждена продавцом. Пожалуйста, заберите заказ в течение {hours} часов. Код бронирования: <code>{code_display}</code>."
                )
            else:
                confirm_text = (
                    f"✅ Sizning broningiz <code>{code_display}</code> tasdiqlandi. Iltimos, buyurtmani {hours} soat ichida oling. Bron kodi: <code>{code_display}</code>."
                )
            try:
                await bot.send_message(user_id, confirm_text, parse_mode='HTML')
            except Exception:
                logger.error(f"Failed to notify customer about confirmation (pickup) for booking {booking_id}")
    except Exception as e:
        logger.error(f"Failed to notify customer about confirmation: {e}")

    # Edit partner message to show confirmed state and show complete/cancel buttons
    try:
        kb = InlineKeyboardBuilder()
        kb.button(text=("✓ Выдано" if lang == 'ru' else "🎉 Berildi"), callback_data=f"complete_booking_{booking_id}")
        kb.button(text=("× Отменить" if lang == 'ru' else "× Bekor qilish"), callback_data=f"cancel_booking_{booking_id}")
        kb.adjust(2)
        try:
            text_src = getattr(callback.message, 'text', '') or ''
            await _safe_answer_or_send(callback.message, callback.from_user.id, text_src + "\n\n✅ Подтвержена", parse_mode='HTML', reply_markup=kb.as_markup())
        except Exception:
            pass
    except Exception:
        pass

    await callback.answer(get_text(lang, "booking_confirmed") or ("Бронь подтверждена" if lang == 'ru' else "Bron tasdiqlandi"), show_alert=True)


@router.callback_query(F.data.startswith("partner_reject_"))
async def partner_reject(callback: types.CallbackQuery) -> None:
    """Partner rejects a pending booking; cancel it and notify customer."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int((callback.data or "").rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    # Cancel the booking (this will restore quantity)
    success = db.cancel_booking(booking_id)
    if success:
        user_id = get_booking_field(booking, 'user_id')
        try:
            customer_lang = db.get_user_language(user_id) if user_id and db else 'ru'
            cancel_text = (
                f"❌ Ваша бронь <code>{get_booking_field(booking,'code')}</code> отклонена продавцом. Средства/резерв возвращены." if customer_lang == 'ru'
                else f"❌ Sizning broningiz <code>{get_booking_field(booking,'code')}</code> sotuvchi tomonidan rad etildi. Rezerv bekor qilindi."
            )
            await bot.send_message(user_id, cancel_text, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Failed to notify customer about rejection: {e}")

        try:
            text_src = getattr(callback.message, 'text', '') or ''
            await _safe_answer_or_send(callback.message, callback.from_user.id, text_src + "\n\n❌ Отклонена", parse_mode='HTML')
        except Exception:
            pass

        await callback.answer(get_text(lang, "booking_rejected") or ("Бронь отклонена" if lang == 'ru' else "Bron rad etildi"), show_alert=True)
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("complete_booking_"))
async def complete_booking(callback: types.CallbackQuery) -> None:
    """Complete booking (partner action)."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        parts = (callback.data or "").split("_")
        booking_id = int(parts[2]) if len(parts) > 2 else 0
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
        # Ensure reminder won't be sent for completed bookings
        try:
            if db:
                db.mark_reminder_sent(booking_id)
        except Exception:
            pass
        await callback.answer(get_text(lang, "booking_completed"), show_alert=True)
        # Edit/send message to show completed status using safe helper
        try:
            text_src = getattr(callback.message, 'text', '') or ''
            await _safe_answer_or_send(callback.message, callback.from_user.id, text_src + "\n\n✅ <b>Выполнено</b>", parse_mode="HTML")
        except Exception:
            pass
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("customer_received_"))
async def customer_received(callback: types.CallbackQuery) -> None:
    """Customer confirms they received a delivered booking."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    try:
        booking_id = int((callback.data or "").rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in customer_received callback: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    user_id = get_booking_field(booking, 'user_id')
    if callback.from_user.id != user_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Complete booking
    success = db.complete_booking(booking_id)
    if success:
        # mark reminder sent to avoid further reminders
        try:
            if db:
                db.mark_reminder_sent(booking_id)
        except Exception:
            pass

        # Notify partner (store owner) that customer confirmed receipt
        try:
            store_id = get_booking_field(booking, 'store_id')
            if store_id:
                store = db.get_store(store_id)
                owner_id = get_store_field(store, 'owner_id') if store else None
                if owner_id:
                    try:
                        await bot.send_message(owner_id, f"Покупатель подтвердил получение заказа #{booking_id}.")
                    except Exception:
                        pass
        except Exception:
            pass

        # Acknowledge to customer
        try:
            await callback.answer(get_text(lang, 'booking_completed') or ("Бронь завершена" if lang == 'ru' else "Bron yakunlandi"), show_alert=True)
            try:
                text_src = getattr(callback.message, 'text', '') or ''
                await _safe_answer_or_send(callback.message, callback.from_user.id, text_src + "\n\n✅ Подтвержено получение. Спасибо!", parse_mode="HTML")
            except Exception:
                pass
        except Exception:
            pass
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("rate_booking_"))
async def rate_booking(callback: types.CallbackQuery) -> None:
    """Show rating keyboard for booking."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        parts = (callback.data or "").split("_")
        booking_id = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Check if booking exists and is completed
    booking = db.get_booking(booking_id)
    status_val = get_booking_field(booking, 'status') if booking else None
    if not booking or status_val != "completed":
        await callback.answer(get_text(lang, "cannot_rate"), show_alert=True)
        return
    
    # Show rating keyboard
    rating_kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        rating_kb.button(text=f"{'⭐' * i}", callback_data=f"booking_rate_{booking_id}_{i}")
    rating_kb.adjust(5)
    
    await _safe_answer_or_send(callback.message, callback.from_user.id, get_text(lang, "rate_booking"), reply_markup=rating_kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("booking_rate_"))
async def save_booking_rating(callback: types.CallbackQuery) -> None:
    """Save booking rating."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    parts = (callback.data or "").split("_")
    booking_id = int(parts[2]) if len(parts) > 2 else 0
    rating = int(parts[3]) if len(parts) > 3 else 0
    
    # Save rating
    success = db.save_booking_rating(booking_id, rating)
    if success:
        await callback.answer(get_text(lang, "rating_saved"), show_alert=True)
        try:
            text_src = getattr(callback.message, 'text', '') or ''
            await _safe_answer_or_send(callback.message, callback.from_user.id, text_src + f"\n\n✅ Оценка: {'⭐' * rating}")
        except Exception:
            pass
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("cancel_booking_confirm_"))
async def cancel_booking_confirm(callback: types.CallbackQuery) -> None:
    """Ask user to confirm cancellation (user flow)."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int((callback.data or "").rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid booking_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Ask confirmation with Yes/No
    confirm_kb = InlineKeyboardBuilder()
    confirm_kb.button(text=("Да, отменить" if lang == 'ru' else "Ha, bekor qilish"), callback_data=f"do_cancel_booking_{booking_id}")
    confirm_kb.button(text=("Нет" if lang == 'ru' else "Yo'q"), callback_data=f"noop_{booking_id}")
    confirm_kb.adjust(2)

    await _safe_answer_or_send(callback.message, callback.from_user.id, get_text(lang, "confirm_cancel_booking") or ("Вы уверены, что хотите отменить бронь?" if lang == 'ru' else "Bronni bekor qilmoqchimisiz?"), reply_markup=confirm_kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("do_cancel_booking_"))
async def do_cancel_booking(callback: types.CallbackQuery) -> None:
    """Perform user-initiated cancellation after confirmation."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int((callback.data or "").rsplit("_", 1)[-1])
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
        # Return quantity to offer (atomic increment to avoid race conditions)
        offer_id = get_booking_field(booking, "offer_id", 1)
        quantity = get_booking_field(booking, "quantity", 6)
        try:
            db.increment_offer_quantity_atomic(offer_id, int(quantity or 0))
        except Exception as e:
            logger.error(f"Failed to increment offer quantity for offer {offer_id}: {e}")

        await callback.answer(get_text(lang, "booking_cancelled"), show_alert=True)
        # Optionally edit the confirmation message
        try:
            # Use safe helper to edit existing message or send a new one
            await _safe_answer_or_send(callback.message, callback.from_user.id, get_text(lang, "booking_cancelled"))
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

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    try:
        store_id = int((callback.data or "").rsplit("_", 1)[-1])
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
    await _safe_answer_or_send(callback.message, callback.from_user.id, text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("noop_"))
async def noop_callback(callback: types.CallbackQuery) -> None:
    """No-op callback to close dialogs; simply answer to remove loading state."""
    try:
        await callback.answer()
    except Exception:
        # ignore errors answering no-op callbacks (e.g., if query already closed)
        pass


@router.callback_query(F.data.startswith("booking_details_"))
async def booking_details(callback: types.CallbackQuery) -> None:
    """Show booking details to the user."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int((callback.data or "").rsplit("_", 1)[-1])
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
    # Avoid showing literal 'None' if code is missing
    code_display = code if code else str(booking_id)
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
        + f"🎫 <code>{code_display}</code>\n"
        + f"📅 {created_at}"
    )

    # Action buttons: Cancel and Close (two buttons)
    kb = InlineKeyboardBuilder()
    kb.button(text=("Отменить" if lang == 'ru' else "Bekor qilish"), callback_data=f"cancel_booking_confirm_{booking_id}")
    kb.button(text=("Закрыть" if lang == 'ru' else "Yopish"), callback_data=f"noop_{booking_id}")
    kb.adjust(2)

    await _safe_answer_or_send(callback.message, callback.from_user.id, text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()
