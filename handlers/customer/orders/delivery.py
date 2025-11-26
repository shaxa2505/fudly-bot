"""Order and delivery handlers."""
from __future__ import annotations

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
        # Fallback to a short alert if the full message cannot be posted to the callback message
        await callback.answer(
            get_text(lang, "please_open_chat")
            if callable(get_text)
            else "Please open the chat to continue",
            show_alert=True,
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
        quantity = int(message.text)
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
    await state.update_data(payment_method="card")
    await state.set_state(OrderDelivery.payment_proof)
    logger.info(f"💳 Waiting for payment screenshot from user {message.from_user.id}")

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

    if not payment_card:
        await message.answer(
            "❌ "
            + (
                "Платёжные реквизиты временно недоступны. Попробуйте позже."
                if lang == "ru"
                else "To'lov rekvizitlari vaqtincha mavjud emas. Keyinroq urinib ko'ring."
            ),
            reply_markup=get_appropriate_menu(message.from_user.id, lang),
        )
        await state.clear()
        return

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
        text="✅ " + ("Подтвердить оплату" if lang == "ru" else "To'lovni tasdiqlash"),
        callback_data=f"confirm_payment_{order_id}",
    )
    notification_kb.button(
        text="❌ " + ("Отклонить" if lang == "ru" else "Rad etish"),
        callback_data=f"reject_payment_{order_id}",
    )
    notification_kb.adjust(2)

    # Labels for multilingual support (to avoid f-string escaping issues)
    payment_ru = "Оплата"
    payment_uz = "To'lov"
    payment_method_ru = "Перевод на карту"
    payment_method_uz = "Kartaga o'tkazma"
    screenshot_ru = "Скриншот оплаты выше"
    screenshot_uz = "To'lov skrinsho yuqorida"

    # Notify store owner
    if not owner_id:
        logger.error(
            f"NOTIFY_ORDER_OWNER: owner_id is None for store_id={store_id}, order={order_id}"
        )
    else:
        try:
            logger.info(
                f"NOTIFY_ORDER_OWNER: order={order_id} owner={owner_id} photo_present={bool(photo_id)}"
            )
            await bot.send_photo(
                chat_id=owner_id,
                photo=photo_id,
                caption=f"🔔 <b>{'Новый заказ с доставкой!' if lang == 'ru' else 'Yangi buyurtma yetkazib berish bilan!'}</b>\n\n"
                f"🏪 {store_name}\n"
                f"🍽 {offer_title}\n"
                f"📦 {'Количество' if lang == 'ru' else 'Miqdor'}: {quantity} {unit_ru if lang == 'ru' else unit_uz}\n"
                f"👤 {message.from_user.first_name}\n"
                f"📱 {'Телефон' if lang == 'ru' else 'Telefon'}: <code>{customer_phone}</code>\n"
                f"📍 {'Адрес' if lang == 'ru' else 'Manzil'}: {address}\n"
                f"💰 {payment_ru if lang == 'ru' else payment_uz}: {payment_method_ru if lang == 'ru' else payment_method_uz}\n"
                f"💵 {'Сумма' if lang == 'ru' else 'Summa'}: {(offer_price * quantity) + delivery_price:,} {currency_ru if lang == 'ru' else currency_uz}\n\n"
                f"📸 {screenshot_ru if lang == 'ru' else screenshot_uz}",
                parse_mode="HTML",
                reply_markup=notification_kb.as_markup(),
            )
            logger.info(f"NOTIFY_ORDER_OWNER: sent photo to owner={owner_id} for order={order_id}")
        except Exception as e:
            logger.error(
                f"NOTIFY_ORDER_OWNER: failed to send to owner={owner_id} order={order_id} error={e}"
            )

    total_amount = (offer_price * quantity) + delivery_price
    user = db.get_user_model(message.from_user.id)
    user_role = user.role if user else "customer"
    menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)

    # Uzbek text without apostrophes in f-string
    waiting_msg_ru = "Ожидайте подтверждения оплаты от магазина"
    waiting_msg_uz = "Do'kon dan to'lovni tasdiqlashni kuting"

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
