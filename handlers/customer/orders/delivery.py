"""Order and delivery handlers."""
from __future__ import annotations

import os
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.utils import get_offer_field, get_store_field
from app.keyboards import cancel_keyboard, main_menu_customer, main_menu_seller
from database_protocol import DatabaseProtocol
from handlers.common.states import OrderDelivery
from handlers.common.utils import is_main_menu_button
from localization import get_text
from logging_config import logger

router = Router()

# Get admin ID from environment
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


def setup_dependencies(
    database: DatabaseProtocol, bot_instance: Any, view_mode_dict: dict[int, str]
) -> None:
    """Setup module dependencies."""
    # This function is kept for backward compatibility but does nothing now
    # Dependencies are injected via middleware
    pass


def can_proceed(user_id: int, action: str) -> bool:
    """Rate limiting check - placeholder."""
    # TODO: Implement actual rate limiting
    return True


def get_appropriate_menu(user_id: int, lang: str) -> Any:
    """Get appropriate menu based on user view mode."""
    from handlers.common import user_view_mode

    if user_view_mode and user_view_mode.get(user_id) == "seller":
        return main_menu_seller(lang)
    return main_menu_customer(lang)


@router.callback_query(F.data.startswith("order_delivery_"))
async def order_delivery_start(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Start delivery order - request quantity."""
    assert callback.from_user is not None
    # callback.message may be an InaccessibleMessage in some contexts; keep a local safe reference
    msg = callback.message if isinstance(callback.message, types.Message) else None
    lang = db.get_user_language(callback.from_user.id)

    if not can_proceed(callback.from_user.id, "order_start"):
        await callback.answer(get_text(lang, "operation_cancelled"), show_alert=True)
        return

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)

    if not offer or get_offer_field(offer, "quantity", 0) <= 0:
        await callback.answer(get_text(lang, "no_offers"), show_alert=True)
        return

    store_id = get_offer_field(offer, "store_id")
    store = db.get_store(store_id)
    if not store:
        await callback.answer("❌ Магазин не найден", show_alert=True)
        return

    delivery_enabled = get_store_field(store, "delivery_enabled", 0)
    if not delivery_enabled:
        await callback.answer(
            "❌ "
            + (
                "Доставка недоступна для этого магазина"
                if lang == "ru"
                else "Ushbu do'kon uchun yetkazib berish mavjud emas"
            ),
            show_alert=True,
        )
        return

    # Check min_order_amount upfront for single item
    min_order_amount = get_store_field(store, "min_order_amount", 0)
    discount_price = get_offer_field(offer, "discount_price", 0)

    if min_order_amount > 0 and discount_price < min_order_amount:
        currency = "сум" if lang == "ru" else "so'm"
        await callback.answer(
            f"❌ {'Минимальный заказ для доставки' if lang == 'ru' else 'Yetkazib berish uchun minimal buyurtma'}: {min_order_amount:,} {currency}",
            show_alert=True,
        )
        return

    await state.update_data(offer_id=offer_id, store_id=store_id)
    await state.set_state(OrderDelivery.quantity)

    unit_ru = "шт"
    unit_uz = "dona"
    currency_ru = "сум"
    currency_uz = "so'm"
    quantity_available = get_offer_field(offer, "quantity", 0)
    discount_price = get_offer_field(offer, "discount_price", 0)
    title = get_offer_field(offer, "title", "")

    # Build quantity selection keyboard
    qty_kb = InlineKeyboardBuilder()

    # Generate smart quantity buttons based on available quantity
    qty_buttons = _generate_quantity_buttons(quantity_available)

    for qty in qty_buttons:
        qty_kb.button(text=str(qty), callback_data=f"order_qty_{offer_id}_{qty}")

    # Add custom input button
    custom_text = "✏️ Ввести вручную" if lang == "ru" else "✏️ Qo'lda kiritish"
    qty_kb.button(text=custom_text, callback_data=f"order_qty_custom_{offer_id}")

    # Arrange buttons: up to 5 per row, custom button on separate row
    if len(qty_buttons) <= 5:
        qty_kb.adjust(len(qty_buttons), 1)
    else:
        qty_kb.adjust(5, len(qty_buttons) - 5, 1)

    if msg:
        await msg.answer(
            f"🍽 <b>{title}</b>\n\n"
            f"📦 {'Доступно' if lang == 'ru' else 'Mavjud'}: {quantity_available} {unit_ru if lang == 'ru' else unit_uz}\n"
            f"💰 {'Цена за 1 шт' if lang == 'ru' else '1 dona narxi'}: {int(discount_price):,} {currency_ru if lang == 'ru' else currency_uz}\n\n"
            f"{'Выберите количество:' if lang == 'ru' else 'Miqdorni tanlang:'}",
            parse_mode="HTML",
            reply_markup=qty_kb.as_markup(),
        )
    else:
        # Fallback to a short alert if the full message cannot be posted to the callback message
        await callback.answer(
            get_text(lang, "please_open_chat")
            if callable(get_text)
            else "Please open the chat to continue",
            show_alert=True,
        )
    await callback.answer()


def _generate_quantity_buttons(max_qty: int) -> list[int]:
    """Generate smart quantity button values based on available quantity."""
    if max_qty <= 0:
        return [1]

    if max_qty <= 5:
        # Show all: 1, 2, 3, 4, 5
        return list(range(1, max_qty + 1))
    elif max_qty <= 10:
        # Show: 1, 2, 3, 5, max
        buttons = [1, 2, 3, 5]
        if max_qty not in buttons:
            buttons.append(max_qty)
        return [b for b in buttons if b <= max_qty]
    elif max_qty <= 20:
        # Show: 1, 2, 3, 5, 10, max
        buttons = [1, 2, 3, 5, 10]
        if max_qty not in buttons:
            buttons.append(max_qty)
        return [b for b in buttons if b <= max_qty]
    elif max_qty <= 50:
        # Show: 1, 2, 5, 10, 20, max
        buttons = [1, 2, 5, 10, 20]
        if max_qty not in buttons:
            buttons.append(max_qty)
        return [b for b in buttons if b <= max_qty]
    else:
        # Show: 1, 5, 10, 20, 50, max
        buttons = [1, 5, 10, 20, 50]
        if max_qty not in buttons:
            buttons.append(max_qty)
        return [b for b in buttons if b <= max_qty]


@router.callback_query(F.data.startswith("order_qty_custom_"))
async def order_qty_custom(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Handle custom quantity input request."""
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[3])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    offer = db.get_offer(offer_id)
    quantity_available = get_offer_field(offer, "quantity", 0) if offer else 0

    await state.set_state(OrderDelivery.quantity)

    if callback.message and hasattr(callback.message, "edit_text"):
        await callback.message.edit_text(
            f"{'Введите количество вручную' if lang == 'ru' else 'Miqdorni qo`lda kiriting'} (1-{quantity_available}):",
            parse_mode="HTML",
        )

    await callback.answer()


@router.callback_query(F.data.startswith("order_qty_"))
async def order_qty_selected(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Handle quantity button selection."""
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    # Skip if it's custom input
    if "custom" in callback.data:
        return

    lang = db.get_user_language(callback.from_user.id)

    try:
        parts = callback.data.split("_")
        offer_id = int(parts[2])
        quantity = int(parts[3])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_qty callback: {callback.data}, error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    # Validate quantity
    data = await state.get_data()
    store_id = data.get("store_id")

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer("❌ Товар не найден", show_alert=True)
        return

    offer_quantity = get_offer_field(offer, "quantity", 0)
    if quantity > offer_quantity:
        await callback.answer(
            f"❌ {'Доступно только' if lang == 'ru' else 'Faqat mavjud'}: {offer_quantity}",
            show_alert=True,
        )
        return

    # Save quantity and proceed to address
    await state.update_data(quantity=quantity, offer_id=offer_id, store_id=store_id)
    await state.set_state(OrderDelivery.address)

    msg = callback.message
    if msg and hasattr(msg, "edit_text"):
        await msg.edit_text(
            f"✅ {'Количество' if lang == 'ru' else 'Miqdor'}: {quantity}",
            parse_mode="HTML",
        )

        example_ru = "Пример: ул. Амира Темура 15, квартира 25"
        example_uz = "Misol: Amir Temur ko'chasi 15, xonadon 25"

        await msg.answer(
            f"📍 {'Укажите адрес доставки' if lang == 'ru' else 'Yetkazib berish manzilini kiriting'}:\n\n"
            f"{example_ru if lang == 'ru' else example_uz}",
            reply_markup=cancel_keyboard(lang),
        )

    await callback.answer()


@router.message(OrderDelivery.quantity)
async def order_delivery_quantity(
    message: types.Message, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Process quantity and request delivery address."""
    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    text = (message.text or "").strip()
    text_lower = text.lower()

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(text):
        await state.clear()
        return

    # Check for cancellation
    cancel_texts = ["отмена", "bekor", "❌"]
    if any(c in text_lower for c in cancel_texts) or text_lower.startswith("/"):
        await state.clear()
        cancelled_text = "❌ Операция отменена" if lang == "ru" else "❌ Bekor qilindi"
        await message.answer(cancelled_text, reply_markup=main_menu_customer(lang))
        return

    try:
        if not message.text:
            await message.answer("❌ " + ("Введите число!" if lang == "ru" else "Raqam kiriting!"))
            return
        quantity = int(message.text.strip())
        if quantity < 1:
            await message.answer(
                "❌ "
                + (
                    "Количество должно быть больше 0"
                    if lang == "ru"
                    else "Miqdor 0 dan katta bo'lishi kerak"
                )
            )
            return

        data = await state.get_data()
        offer_id = data["offer_id"]
        store_id = data["store_id"]
        offer = db.get_offer(offer_id)

        offer_quantity = get_offer_field(offer, "quantity", 0)
        if not offer or offer_quantity < quantity:
            await message.answer(
                f"❌ {'Доступно только' if lang == 'ru' else 'Faqat mavjud'} {offer_quantity} {'шт' if lang == 'ru' else 'dona'}"
            )
            return

        store = db.get_store(store_id)
        min_order_amount = get_store_field(store, "min_order_amount", 0)
        discount_price = get_offer_field(offer, "discount_price", 0)
        order_amount = discount_price * quantity

        if min_order_amount > 0 and order_amount < min_order_amount:
            currency_ru = "сум"
            currency_uz = "so'm"
            await message.answer(
                f"❌ {'Минимальная сумма заказа' if lang == 'ru' else 'Minimal buyurtma summasi'}: {min_order_amount:,} {currency_ru if lang == 'ru' else currency_uz}\n"
                f"{'Ваш заказ' if lang == 'ru' else 'Sizning buyurtmangiz'}: {order_amount:,} {currency_ru if lang == 'ru' else currency_uz}\n\n"
                f"{'Пожалуйста, увеличьте количество или выберите другой товар' if lang == 'ru' else 'Iltimos, miqdorni oshiring yoki boshqa mahsulot tanlang'}"
            )
            return

        await state.update_data(quantity=quantity)
        await state.set_state(OrderDelivery.address)

        example_ru = "Пример: ул. Амира Темура 15, квартира 25"
        example_uz = "Misol: Amir Temur ko'chasi 15, xonadon 25"
        await message.answer(
            f"📍 {'Укажите адрес доставки' if lang == 'ru' else 'Yetkazib berish manzilini kiriting'}:\n\n"
            f"{example_ru if lang == 'ru' else example_uz}",
            reply_markup=cancel_keyboard(lang),
        )

    except ValueError:
        await message.answer("❌ " + ("Введите число!" if lang == "ru" else "Raqam kiriting!"))


@router.message(OrderDelivery.address)
async def order_delivery_address(
    message: types.Message, state: FSMContext, db: DatabaseProtocol, bot: Any
) -> None:
    """Process delivery address and request payment."""
    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    text = (message.text or "").strip()
    text_lower = text.lower()

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(text):
        await state.clear()
        # Don't respond - let the main menu handler process this
        return

    # Check for cancel
    cancel_texts = ["отмена", "bekor", "❌"]
    if any(c in text_lower for c in cancel_texts) or text_lower.startswith("/"):
        await state.clear()
        cancelled_text = "❌ Операция отменена" if lang == "ru" else "❌ Bekor qilindi"
        await message.answer(cancelled_text, reply_markup=main_menu_customer(lang))
        return

    address = text
    if len(address) < 10:
        await message.answer(
            "❌ "
            + (
                "Пожалуйста, укажите полный адрес доставки"
                if lang == "ru"
                else "Iltimos, to'liq manzilni kiriting"
            )
        )
        return

    await state.update_data(address=address)
    
    # Show payment method selection
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    payment_kb = InlineKeyboardBuilder()
    payment_kb.button(
        text="💳 Click orqali to'lash" if lang == "uz" else "💳 Оплата через Click",
        callback_data="pay_method_click"
    )
    payment_kb.button(
        text="🏦 Karta orqali o'tkazma" if lang == "uz" else "🏦 Перевод на карту",
        callback_data="pay_method_card"
    )
    payment_kb.adjust(1)
    
    await state.set_state(OrderDelivery.payment_method_select)
    
    await message.answer(
        "💰 " + (
            "To'lov usulini tanlang:" if lang == "uz" else "Выберите способ оплаты:"
        ),
        reply_markup=payment_kb.as_markup()
    )


@router.callback_query(F.data == "pay_method_click", OrderDelivery.payment_method_select)
async def handle_click_payment(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle Click payment selection - send Telegram invoice."""
    await callback.answer()
    
    data = await state.get_data()
    lang = db.get_user_language(callback.from_user.id) or "uz"
    
    # Get order details
    offer_id = data.get("offer_id")
    quantity = data.get("quantity", 1)
    store_id = data.get("store_id")
    
    offer = db.get_offer(offer_id)
    if not offer:
        await callback.message.edit_text("❌ Mahsulot topilmadi")
        await state.clear()
        return
    
    # Get prices
    discount_price = int(get_offer_field(offer, "discount_price", 0))
    title = get_offer_field(offer, "title", "Товар")
    
    store = db.get_store(store_id)
    delivery_price = int(get_store_field(store, "delivery_price", 15000)) if store else 15000
    
    total_amount = (discount_price * quantity) + delivery_price
    
    # Create booking first
    booking_code = f"D{callback.from_user.id % 10000:04d}{offer_id % 1000:03d}"
    
    try:
        booking_id = db.create_booking(
            user_id=callback.from_user.id,
            offer_id=offer_id,
            quantity=quantity,
            booking_code=booking_code,
            status="pending",
            payment_method="click",
            delivery_address=data.get("address"),
            delivery_cost=delivery_price,
        )
    except Exception as e:
        logger.error(f"Failed to create booking: {e}")
        # Try simpler version
        booking_id = offer_id  # Use offer_id as fallback
    
    # Send Telegram invoice
    from handlers.customer.payments import send_payment_invoice_for_booking
    
    try:
        await callback.message.delete()
        
        invoice_msg = await send_payment_invoice_for_booking(
            user_id=callback.from_user.id,
            booking_id=booking_id,
            offer_title=title,
            quantity=quantity,
            unit_price=discount_price,
            delivery_cost=delivery_price,
        )
        
        if invoice_msg:
            logger.info(f"✅ Click invoice sent for order {booking_id}")
            await state.clear()
        else:
            # Fallback to card payment
            await callback.message.answer(
                "⚠️ Click to'lovi vaqtincha ishlamayapti. Karta orqali to'lang.",
            )
            await state.update_data(payment_method="card")
            await state.set_state(OrderDelivery.payment_proof)
            await _show_card_payment(callback.message, state, lang)
            
    except Exception as e:
        logger.error(f"Error sending Click invoice: {e}")
        await callback.message.answer(
            "❌ Xatolik. Karta orqali to'lashga o'ting.",
        )
        await state.update_data(payment_method="card") 
        await state.set_state(OrderDelivery.payment_proof)
        await _show_card_payment(callback.message, state, lang)


@router.callback_query(F.data == "pay_method_card", OrderDelivery.payment_method_select)
async def handle_card_payment(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle card payment selection - show card details."""
    await callback.answer()
    
    lang = db.get_user_language(callback.from_user.id) or "uz"
    
    await state.update_data(payment_method="card")
    await state.set_state(OrderDelivery.payment_proof)
    
    await callback.message.delete()
    await _show_card_payment(callback.message, state, lang)


async def _show_card_payment(message: types.Message, state: FSMContext, lang: str) -> None:
    """Show card payment details."""
    data = await state.get_data()
    store_id = data.get("store_id")

    # First try to get store-specific payment card
    payment_card = None
    payment_instructions = None

    if store_id:
        try:
            store_payment = db.get_payment_card(store_id)
            if store_payment:
                payment_card = store_payment
                payment_instructions = (
                    store_payment.get("payment_instructions")
                    if isinstance(store_payment, dict)
                    else None
                )
                logger.info(f"💳 Using store {store_id} payment card")
        except Exception as e:
            logger.warning(f"Failed to get store payment card: {e}")

    # Fallback to platform payment card
    if not payment_card:
        payment_card = db.get_platform_payment_card()
        logger.info("💳 Using platform payment card")

    # Default payment card if not configured (same as API fallback)
    if not payment_card:
        payment_card = {
            "card_number": "8600 1234 5678 9012",
            "card_holder": "FUDLY",
            "payment_instructions": "Chekni yuklashni unutmang!",
        }
        logger.info("💳 Using default platform payment card")

    # Handle different payment_card formats:
    # - dict: {"card_number": "...", "card_holder": "...", "payment_instructions": "..."}
    # - tuple: (id, card_number, card_holder, ...)
    # - str: just the card number
    if isinstance(payment_card, dict):
        card_number = payment_card.get("card_number", "")
        card_holder = payment_card.get("card_holder", "—")
        if not payment_instructions:
            payment_instructions = payment_card.get("payment_instructions")
    elif isinstance(payment_card, (tuple, list)) and len(payment_card) > 1:
        card_number = payment_card[1] if len(payment_card) > 1 else payment_card[0]
        card_holder = payment_card[2] if len(payment_card) > 2 else "—"
    else:
        # String format - just the card number
        card_number = str(payment_card)
        card_holder = "—"

    store = db.get_store(store_id)
    delivery_price = get_store_field(store, "delivery_price", 10000)
    offer = db.get_offer(data["offer_id"])
    quantity = data["quantity"]
    discount_price = get_offer_field(offer, "discount_price", 0)
    total_amount = (discount_price * quantity) + delivery_price

    currency_ru = "сум"
    currency_uz = "so'm"
    transfer_ru = "Переведите сумму на карту"
    transfer_uz = "Kartaga pul o'tkazing"
    screenshot_ru = "После перевода отправьте скриншот чека"
    screenshot_uz = "O'tkazmadan keyin chek skrinshotini yuboring"

    # Build payment message
    msg = (
        f"💳 {transfer_ru if lang == 'ru' else transfer_uz}:\n\n"
        f"💰 {'Сумма' if lang == 'ru' else 'Summa'}: <b>{total_amount:,} {currency_ru if lang == 'ru' else currency_uz}</b>\n"
        f"💳 {'Номер карты' if lang == 'ru' else 'Karta raqami'}: <code>{card_number}</code>\n"
        f"👤 {'Получатель' if lang == 'ru' else 'Qabul qiluvchi'}: {card_holder}\n\n"
        f"📝 {'Стоимость товаров' if lang == 'ru' else 'Mahsulotlar narxi'}: {discount_price * quantity:,} {currency_ru if lang == 'ru' else currency_uz}\n"
        f"🚚 {'Доставка' if lang == 'ru' else 'Yetkazib berish'}: {delivery_price:,} {currency_ru if lang == 'ru' else currency_uz}\n"
    )

    # Add payment instructions if available
    if payment_instructions:
        msg += f"\n📋 <i>{payment_instructions}</i>\n"

    msg += f"\n{screenshot_ru if lang == 'ru' else screenshot_uz}"

    await message.answer(msg, parse_mode="HTML", reply_markup=cancel_keyboard(lang))


@router.message(OrderDelivery.payment_proof, F.photo)
async def order_payment_proof(
    message: types.Message, state: FSMContext, db: DatabaseProtocol, bot: Any
) -> None:
    """Process payment screenshot and create order."""
    assert message.from_user is not None
    logger.info(f"📸 Payment screenshot received from user {message.from_user.id}")

    lang = db.get_user_language(message.from_user.id)

    if not can_proceed(message.from_user.id, "order_confirm"):
        await message.answer(get_text(lang, "operation_cancelled"))
        return

    data = await state.get_data()

    required_keys = ["offer_id", "store_id", "quantity", "address"]
    missing_keys = [key for key in required_keys if key not in data]

    if missing_keys:
        logger.error(f"❌ Missing data for user {message.from_user.id}: {missing_keys}")
        await message.answer(
            "❌ "
            + (
                "Данные заказа потеряны. Пожалуйста, начните оформление заново из каталога."
                if lang == "ru"
                else "Buyurtma ma'lumotlari yo'qoldi. Iltimos, katalogdan qayta boshlang."
            ),
            reply_markup=get_appropriate_menu(message.from_user.id, lang),
        )
        await state.clear()
        return

    offer_id = data["offer_id"]
    store_id = data["store_id"]
    quantity = data["quantity"]
    address = data["address"]

    offer = db.get_offer(offer_id)
    store = db.get_store(store_id)

    owner_id = get_store_field(store, "owner_id")
    store_name = get_store_field(store, "name", "Магазин")
    delivery_price = get_store_field(store, "delivery_price", 10000)

    offer_title = get_offer_field(offer, "title", "")
    offer_price = get_offer_field(offer, "discount_price", 0)
    offer_quantity = get_offer_field(offer, "quantity", 0)

    # Extract highest-resolution photo id
    photo_id = message.photo[-1].file_id

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

    db.update_payment_status(order_id, "pending", photo_id)
    await state.clear()

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
        text="✅ Подтвердить оплату",
        callback_data=f"admin_confirm_payment_{order_id}",
    )
    notification_kb.button(
        text="❌ Отклонить",
        callback_data=f"admin_reject_payment_{order_id}",
    )
    notification_kb.adjust(2)

    # Labels for multilingual support (to avoid f-string escaping issues)
    payment_ru = "Оплата"
    payment_uz = "To'lov"
    payment_method_ru = "Перевод на карту"
    payment_method_uz = "Kartaga o'tkazma"
    screenshot_ru = "Скриншот оплаты выше"
    screenshot_uz = "To'lov skrinsho yuqorida"

    total_amount = (offer_price * quantity) + delivery_price

    # Send payment confirmation request to ADMIN instead of store owner
    if ADMIN_ID <= 0:
        logger.error(f"ADMIN_ID not configured! Cannot process payment for order {order_id}")
        await message.answer(
            "❌ Системная ошибка. Обратитесь к администратору.",
            reply_markup=get_appropriate_menu(message.from_user.id, lang),
        )
        await state.clear()
        return

    try:
        logger.info(
            f"NOTIFY_ADMIN: order={order_id} admin={ADMIN_ID} photo_present={bool(photo_id)}"
        )
        await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_id,
            caption=(
                f"💳 <b>Новый чек на подтверждение!</b>\n\n"
                f"📦 Заказ #{order_id}\n"
                f"🏪 Магазин: {store_name}\n"
                f"👤 Владелец магазина ID: <code>{owner_id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🍽 {offer_title}\n"
                f"📦 Количество: {quantity} шт\n"
                f"💵 Сумма: <b>{total_amount:,} сум</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 Клиент: {message.from_user.first_name}\n"
                f"📱 Телефон: <code>{customer_phone}</code>\n"
                f"📍 Адрес: {address}\n\n"
                f"📸 Скриншот оплаты выше ☝️"
            ),
            parse_mode="HTML",
            reply_markup=notification_kb.as_markup(),
        )
        logger.info(
            f"NOTIFY_ADMIN: sent payment confirmation request to admin for order={order_id}"
        )
    except Exception as e:
        logger.error(f"NOTIFY_ADMIN: failed to send to admin={ADMIN_ID} order={order_id} error={e}")

    user = db.get_user_model(message.from_user.id)
    user_role = user.role if user else "customer"
    menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)

    # Updated waiting message - now waiting for admin confirmation
    waiting_msg_ru = "⏳ Ожидайте подтверждения оплаты администратором"
    waiting_msg_uz = "⏳ Administrator tomonidan to'lovni tasdiqlashni kuting"

    await message.answer(
        f"✅ <b>{'Заказ оформлен!' if lang == 'ru' else 'Buyurtma qabul qilindi!'}</b>\n\n"
        f"📦 {'Заказ' if lang == 'ru' else 'Buyurtma'} #{order_id}\n"
        f"🍽 {offer_title}\n"
        f"📦 {'Количество' if lang == 'ru' else 'Miqdor'}: {quantity} {unit_ru if lang == 'ru' else unit_uz}\n"
        f"📍 {'Адрес доставки' if lang == 'ru' else 'Yetkazib berish manzili'}: {address}\n"
        f"💰 {payment_ru if lang == 'ru' else payment_uz}: {payment_method_ru if lang == 'ru' else payment_method_uz}\n"
        f"💵 {'Итого' if lang == 'ru' else 'Jami'}: <b>{total_amount:,} {currency_ru if lang == 'ru' else currency_uz}</b>\n\n"
        f"{waiting_msg_ru if lang == 'ru' else waiting_msg_uz}",
        parse_mode="HTML",
    )
    await message.answer("✅ " + ("Готово!" if lang == "ru" else "Tayyor!"), reply_markup=menu)


@router.message(OrderDelivery.payment_proof)
async def order_payment_proof_invalid(
    message: types.Message, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Handle non-photo messages in payment proof state."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    text = (message.text or "").strip()
    text_lower = text.lower()

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(text):
        await state.clear()
        return

    # Check for cancel
    cancel_texts = ["отмена", "bekor", "❌"]
    if any(c in text_lower for c in cancel_texts) or text_lower.startswith("/"):
        await state.clear()
        cancelled_text = "❌ Операция отменена" if lang == "ru" else "❌ Bekor qilindi"
        await message.answer(cancelled_text, reply_markup=main_menu_customer(lang))
        return

    logger.warning(f"❌ User {message.from_user.id} sent {message.content_type} instead of photo")

    await message.answer(
        "❌ "
        + (
            "Пожалуйста, отправьте скриншот чека (фото)"
            if lang == "ru"
            else "Iltimos, chek skrinshotini (rasm) yuboring"
        ),
        reply_markup=cancel_keyboard(lang),
    )


# NOTE: confirm_order_ and cancel_order_ handlers removed - they are handled by
# handlers/seller/order_management.py which is registered before this router.
# Only cancel_order_customer_ (for customers) remains here.


@router.callback_query(F.data.startswith("cancel_order_customer_"))
async def cancel_order_customer(
    callback: types.CallbackQuery, db: DatabaseProtocol, bot: Any
) -> None:
    """Cancel order by customer."""
    if not db or not bot:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)

    # Helper for dict/tuple - defined first before usage
    def get_order_field(o, field, index=0):
        return o.get(field) if isinstance(o, dict) else (o[index] if len(o) > index else None)

    try:
        order_id = int(callback.data.split("_")[3])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer(
            "❌ " + ("Заказ не найден" if lang == "ru" else "Buyurtma topilmadi"),
            show_alert=True,
        )
        return

    if get_order_field(order, "user_id", 1) != callback.from_user.id:
        await callback.answer(
            "❌ " + ("Это не ваш заказ" if lang == "ru" else "Bu sizning buyurtmangiz emas"),
            show_alert=True,
        )
        return

    order_status = get_order_field(order, "status", 3)
    if order_status not in ["pending", "confirmed"]:
        await callback.answer(
            "❌ "
            + ("Заказ уже обработан" if lang == "ru" else "Buyurtma allaqachon qayta ishlangan"),
            show_alert=True,
        )
        return

    db.update_order_status(order_id, "cancelled")

    offer_id = get_order_field(order, "offer_id", 2)
    quantity = get_order_field(order, "quantity", 4)
    offer = db.get_offer(offer_id)
    if offer:
        try:
            db.increment_offer_quantity_atomic(offer_id, int(quantity))
        except Exception as e:
            logger.error(f"Failed to restore quantity for offer {offer_id}: {e}")

    await callback.message.edit_text(
        callback.message.text
        + f"\n\n❌ {'Заказ отменён' if lang == 'ru' else 'Buyurtma bekor qilindi'}",
        parse_mode="HTML",
    )

    store = db.get_store(order[2])
    if store:
        seller_lang = db.get_user_language(get_store_field(store, "owner_id"))
        try:
            await bot.send_message(
                get_store_field(store, "owner_id"),
                f"ℹ️ <b>{'Клиент отменил заказ' if seller_lang == 'ru' else 'Mijoz buyurtmani bekor qildi'}</b>\n\n"
                f"📦 {'Заказ' if seller_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
                f"👤 {callback.from_user.first_name}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to notify seller {get_store_field(store, 'owner_id')}: {e}")

    await callback.answer()


# =============================================================================
# ADMIN PAYMENT CONFIRMATION HANDLERS
# =============================================================================


def _get_order_field(order: Any, field: str, index: int = 0) -> Any:
    """Helper to get field from order dict or tuple."""
    if isinstance(order, dict):
        return order.get(field)
    return order[index] if len(order) > index else None


@router.callback_query(F.data.startswith("admin_confirm_payment_"))
async def admin_confirm_payment(
    callback: types.CallbackQuery, db: DatabaseProtocol, bot: Any
) -> None:
    """Admin confirms payment - notify seller about new paid order."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Только для администратора", show_alert=True)
        return

    try:
        order_id = int(callback.data.split("_")[3])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_id in callback: {callback.data}, error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return

    # Update payment status to confirmed
    db.update_payment_status(order_id, "confirmed")
    db.update_order_status(order_id, "confirmed")

    # Get order details
    store_id = _get_order_field(order, "store_id", 2)
    offer_id = _get_order_field(order, "offer_id", 3)
    quantity = _get_order_field(order, "quantity", 4)
    address = _get_order_field(order, "delivery_address", 7)
    customer_id = _get_order_field(order, "user_id", 1)
    payment_photo_id = _get_order_field(order, "payment_proof_photo_id", 10)

    store = db.get_store(store_id)
    offer = db.get_offer(offer_id)
    customer = db.get_user_model(customer_id)

    owner_id = get_store_field(store, "owner_id") if store else None
    store_name = get_store_field(store, "name", "Магазин") if store else "Магазин"
    delivery_price = get_store_field(store, "delivery_price", 0) if store else 0

    offer_title = get_offer_field(offer, "title", "Товар") if offer else "Товар"
    offer_price = get_offer_field(offer, "discount_price", 0) if offer else 0

    customer_name = customer.first_name if customer else "Клиент"
    customer_phone = customer.phone if customer else "Не указан"

    total_amount = (offer_price * quantity) + delivery_price

    # Update admin message
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ <b>ОПЛАТА ПОДТВЕРЖДЕНА</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Notify store owner about confirmed payment WITH photo
    if owner_id:
        seller_lang = db.get_user_language(owner_id)

        order_caption = (
            f"🔔 <b>{'Новый оплаченный заказ!' if seller_lang == 'ru' else 'Yangi tolangan buyurtma!'}</b>\n\n"
            f"📦 {'Заказ' if seller_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"✅ <b>{'Оплата подтверждена' if seller_lang == 'ru' else 'Tolov tasdiqlandi'}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🍽 {offer_title}\n"
            f"📦 {'Количество' if seller_lang == 'ru' else 'Miqdor'}: {quantity} {'шт' if seller_lang == 'ru' else 'dona'}\n"
            f"💵 {'Сумма' if seller_lang == 'ru' else 'Summa'}: <b>{total_amount:,} {'сум' if seller_lang == 'ru' else 'som'}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 {'Клиент' if seller_lang == 'ru' else 'Mijoz'}: {customer_name}\n"
            f"📱 {'Телефон' if seller_lang == 'ru' else 'Telefon'}: <code>{customer_phone}</code>\n"
            f"📍 {'Адрес доставки' if seller_lang == 'ru' else 'Yetkazib berish manzili'}: {address}\n\n"
            f"🚚 {'Пожалуйста, организуйте доставку!' if seller_lang == 'ru' else 'Iltimos, yetkazib berishni tashkil qiling!'}"
        )

        try:
            # Send with payment proof photo if available
            if payment_photo_id:
                await bot.send_photo(
                    chat_id=owner_id,
                    photo=payment_photo_id,
                    caption=order_caption,
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    chat_id=owner_id,
                    text=order_caption,
                    parse_mode="HTML",
                )
            logger.info(f"Notified seller {owner_id} about confirmed payment for order {order_id}")
        except Exception as e:
            logger.error(f"Failed to notify seller {owner_id}: {e}")

    # Notify customer
    if customer_id:
        customer_lang = db.get_user_language(customer_id)
        try:
            await bot.send_message(
                chat_id=customer_id,
                text=(
                    f"✅ <b>{'Оплата подтверждена!' if customer_lang == 'ru' else 'To`lov tasdiqlandi!'}</b>\n\n"
                    f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
                    f"🍽 {offer_title}\n"
                    f"💵 {'Сумма' if customer_lang == 'ru' else 'Summa'}: {total_amount:,} {'сум' if customer_lang == 'ru' else 'so`m'}\n\n"
                    f"🚚 {'Магазин начал обработку вашего заказа. Ожидайте доставку!' if customer_lang == 'ru' else 'Do`kon buyurtmangizni qayta ishlashni boshladi. Yetkazib berishni kuting!'}"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")

    await callback.answer("✅ Оплата подтверждена!", show_alert=True)


@router.callback_query(F.data.startswith("admin_reject_payment_"))
async def admin_reject_payment(
    callback: types.CallbackQuery, db: DatabaseProtocol, bot: Any
) -> None:
    """Admin rejects payment - cancel order and notify customer."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Только для администратора", show_alert=True)
        return

    try:
        order_id = int(callback.data.split("_")[3])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_id in callback: {callback.data}, error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return

    # Update statuses
    db.update_payment_status(order_id, "rejected")
    db.update_order_status(order_id, "cancelled")

    # Restore offer quantity
    offer_id = _get_order_field(order, "offer_id", 3)
    quantity = _get_order_field(order, "quantity", 4)
    customer_id = _get_order_field(order, "user_id", 1)

    offer = db.get_offer(offer_id)
    if offer:
        try:
            db.increment_offer_quantity_atomic(offer_id, int(quantity))
        except Exception as e:
            logger.error(f"Failed to restore quantity for offer {offer_id}: {e}")

    # Update admin message
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ <b>ОПЛАТА ОТКЛОНЕНА</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Notify customer about rejected payment
    if customer_id:
        customer_lang = db.get_user_language(customer_id)
        offer_title = get_offer_field(offer, "title", "Товар") if offer else "Товар"
        try:
            await bot.send_message(
                chat_id=customer_id,
                text=(
                    f"❌ <b>{'Оплата не подтверждена' if customer_lang == 'ru' else 'To`lov tasdiqlanmadi'}</b>\n\n"
                    f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
                    f"🍽 {offer_title}\n\n"
                    f"{'Пожалуйста, проверьте правильность оплаты и попробуйте снова.' if customer_lang == 'ru' else 'Iltimos, to`lov to`g`riligini tekshiring va qayta urinib ko`ring.'}"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")

    await callback.answer("❌ Оплата отклонена", show_alert=True)
