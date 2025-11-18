"""Order and delivery handlers."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database_protocol import DatabaseProtocol
from handlers.common_states.states import OrderDelivery
from app.keyboards import cancel_keyboard, main_menu_customer, main_menu_seller
from localization import get_text
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None
user_view_mode: dict[int, str] | None = None

router = Router()


def setup_dependencies(
    database: DatabaseProtocol, bot_instance: Any, view_mode_dict: dict[int, str]
) -> None:
    """Setup module dependencies."""
    global db, bot, user_view_mode
    db = database
    bot = bot_instance
    user_view_mode = view_mode_dict


def can_proceed(user_id: int, action: str) -> bool:
    """Rate limiting check - placeholder."""
    # TODO: Implement actual rate limiting
    return True


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
        "delivery_enabled": 10,
        "delivery_price": 11,
        "min_order_amount": 12,
    }
    idx = field_map.get(field)
    if idx is not None and isinstance(store, (tuple, list)) and idx < len(store):
        return store[idx]
    return default


def get_offer_field(offer: Any, field: str, default: Any = None) -> Any:
    """Extract field from offer tuple/dict."""
    if isinstance(offer, dict):
        return offer.get(field, default)
    field_map = {
        "offer_id": 0,
        "store_id": 1,
        "title": 2,
        "description": 3,
        "original_price": 4,
        "discount_price": 5,
        "quantity": 6,
        "available_from": 7,
        "available_until": 8,
        "expiry_date": 9,
        "status": 10,
        "photo": 11,
    }
    idx = field_map.get(field)
    if idx is not None and isinstance(offer, (tuple, list)) and idx < len(offer):
        return offer[idx]
    return default


def get_appropriate_menu(user_id: int, lang: str) -> Any:
    """Get appropriate menu based on user view mode."""
    if user_view_mode and user_view_mode.get(user_id) == "seller":
        return main_menu_seller(lang)
    return main_menu_customer(lang)


@router.callback_query(F.data.startswith("order_delivery_"))
async def order_delivery_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start delivery order - request quantity."""
    if not db:
        await callback.answer("System error")
        return

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

    await state.update_data(
        offer_id=offer_id, store_id=store_id
    )
    await state.set_state(OrderDelivery.quantity)

    unit_ru = "шт"
    unit_uz = "dona"
    currency_ru = "сум"
    currency_uz = "so'm"
    quantity_available = get_offer_field(offer, "quantity", 0)
    discount_price = get_offer_field(offer, "discount_price", 0)
    title = get_offer_field(offer, "title", "")

    await callback.message.answer(
        f"🍽 <b>{title}</b>\n\n"
        f"📦 {'Доступно' if lang == 'ru' else 'Mavjud'}: {quantity_available} {unit_ru if lang == 'ru' else unit_uz}\n"
        f"💰 {'Цена за 1 шт' if lang == 'ru' else '1 dona narxi'}: {int(discount_price):,} {currency_ru if lang == 'ru' else currency_uz}\n\n"
        f"{'Сколько вы хотите заказать?' if lang == 'ru' else 'Nechta buyurtma qilasiz?'} (1-{quantity_available})",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(lang),
    )
    await callback.answer()


@router.message(OrderDelivery.quantity)
async def order_delivery_quantity(message: types.Message, state: FSMContext) -> None:
    """Process quantity and request delivery address."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)

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
        await message.answer(
            "❌ " + ("Введите число!" if lang == "ru" else "Raqam kiriting!")
        )


@router.message(OrderDelivery.address)
async def order_delivery_address(message: types.Message, state: FSMContext) -> None:
    """Process delivery address and request payment."""
    if not db or not bot:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)

    address = message.text.strip()
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
    logger.info(
        f"💳 Waiting for payment screenshot from user {message.from_user.id}"
    )

    payment_card = db.get_platform_payment_card()

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

    card_number = payment_card[1]
    card_holder = payment_card[2]

    data = await state.get_data()
    store = db.get_store(data["store_id"])
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

    await message.answer(
        f"💳 {transfer_ru if lang == 'ru' else transfer_uz}:\n\n"
        f"💰 {'Сумма' if lang == 'ru' else 'Summa'}: <b>{total_amount:,} {currency_ru if lang == 'ru' else currency_uz}</b>\n"
        f"💳 {'Номер карты' if lang == 'ru' else 'Karta raqami'}: <code>{card_number}</code>\n"
        f"👤 {'Получатель' if lang == 'ru' else 'Qabul qiluvchi'}: {card_holder}\n\n"
        f"📝 {'Стоимость товаров' if lang == 'ru' else 'Mahsulotlar narxi'}: {discount_price * quantity:,} {currency_ru if lang == 'ru' else currency_uz}\n"
        f"🚚 {'Доставка' if lang == 'ru' else 'Yetkazib berish'}: {delivery_price:,} {currency_ru if lang == 'ru' else currency_uz}\n\n"
        f"{screenshot_ru if lang == 'ru' else screenshot_uz}",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(lang),
    )


@router.message(OrderDelivery.payment_proof, F.photo)
async def order_payment_proof(message: types.Message, state: FSMContext) -> None:
    """Process payment screenshot and create order."""
    if not db or not bot:
        await message.answer("System error")
        return

    logger.info(f"📸 Payment screenshot received from user {message.from_user.id}")

    lang = db.get_user_language(message.from_user.id)

    if not can_proceed(message.from_user.id, "order_confirm"):
        await message.answer(get_text(lang, "operation_cancelled"))
        return

    data = await state.get_data()

    required_keys = ["offer_id", "store_id", "quantity", "address"]
    missing_keys = [key for key in required_keys if key not in data]

    if missing_keys:
        logger.error(
            f"❌ Missing data for user {message.from_user.id}: {missing_keys}"
        )
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
            "❌ "
            + (
                "Ошибка создания заказа"
                if lang == "ru"
                else "Buyurtma yaratishda xatolik"
            )
        )
        await state.clear()
        return

    db.update_payment_status(order_id, "pending", photo_id)
    await state.clear()

    new_quantity = offer_quantity - quantity
    db.update_offer_quantity(offer_id, new_quantity)

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

    try:
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
        logger.info(f"✅ Order notification sent to owner {owner_id}")
    except Exception as e:
        logger.error(f"❌ Error sending order notification to {owner_id}: {e}")

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
    await message.answer(
        "✅ " + ("Готово!" if lang == "ru" else "Tayyor!"), reply_markup=menu
    )


@router.message(OrderDelivery.payment_proof)
async def order_payment_proof_invalid(message: types.Message, state: FSMContext) -> None:
    """Handle non-photo messages in payment proof state."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    logger.warning(
        f"❌ User {message.from_user.id} sent {message.content_type} instead of photo"
    )

    await message.answer(
        "❌ "
        + (
            "Пожалуйста, отправьте скриншот чека (фото)"
            if lang == "ru"
            else "Iltimos, chek skrinshotini (rasm) yuboring"
        ),
        reply_markup=cancel_keyboard(lang),
    )


@router.callback_query(F.data.startswith("confirm_payment_"))
async def confirm_payment(callback: types.CallbackQuery) -> None:
    """Confirm payment by seller."""
    if not db or not bot:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
    try:
        order_id = int(callback.data.split("_")[2])
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

    db.update_payment_status(order_id, "confirmed")
    db.update_order_status(order_id, "confirmed")

    payment_confirmed_text = (
        "Оплата подтверждена!" if lang == "ru" else "To'lov tasdiqlandi!"
    )
    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n✅ {payment_confirmed_text}"
    )

    customer_lang = db.get_user_language(order[1])
    confirmed_ru = "Оплата подтверждена!"
    confirmed_uz = "To'lov tasdiqlandi!"
    prep_ru = "Магазин начинает подготовку вашего заказа"
    prep_uz = "Do'kon buyurtmangizni tayyorlaydi"
    try:
        await bot.send_message(
            order[1],
            f"✅ <b>{confirmed_ru if customer_lang == 'ru' else confirmed_uz}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"{prep_ru if customer_lang == 'ru' else prep_uz}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {order[1]}: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(callback: types.CallbackQuery) -> None:
    """Reject payment by seller."""
    if not db or not bot:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
    try:
        order_id = int(callback.data.split("_")[2])
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

    db.update_payment_status(order_id, "pending")
    db.update_order_status(order_id, "cancelled")

    offer = db.get_offer(order[3])
    if offer:
        new_quantity = get_offer_field(offer, "quantity", 0) + order[4]
        db.update_offer_quantity(order[3], new_quantity)

    payment_rejected_text = (
        "Оплата отклонена, заказ отменён"
        if lang == "ru"
        else "To'lov rad etildi, buyurtma bekor qilindi"
    )
    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n❌ {payment_rejected_text}"
    )

    customer_lang = db.get_user_language(order[1])
    reject_title_ru = "Оплата не подтверждена"
    reject_title_uz = "To'lov tasdiqlanmadi"
    reject_msg_ru = "Магазин не смог подтвердить вашу оплату. Заказ отменён."
    reject_msg_uz = "Do'kon to'lovingizni tasdiqlay olmadi. Buyurtma bekor qilindi."
    reject_note_ru = "Пожалуйста, проверьте правильность перевода или свяжитесь с магазином"
    reject_note_uz = "Iltimos, o'tkazma to'g'riligini tekshiring yoki do'kon bilan bog'laning"
    try:
        await bot.send_message(
            order[1],
            f"❌ <b>{reject_title_ru if customer_lang == 'ru' else reject_title_uz}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"{reject_msg_ru if customer_lang == 'ru' else reject_msg_uz}\n"
            f"{reject_note_ru if customer_lang == 'ru' else reject_note_uz}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {order[1]}: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("confirm_order_"))
async def confirm_order(callback: types.CallbackQuery) -> None:
    """Confirm order by seller."""
    if not db or not bot:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
    try:
        order_id = int(callback.data.split("_")[2])
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

    db.update_order_status(order_id, "confirmed")

    await callback.message.edit_text(
        callback.message.text
        + f"\n\n✅ {'Заказ подтверждён!' if lang == 'ru' else 'Buyurtma tasdiqlandi!'}"
    )

    customer_lang = db.get_user_language(order[1])
    order_confirmed_ru = "Заказ подтверждён!"
    order_confirmed_uz = "Buyurtma tasdiqlandi!"
    prep_msg_ru = "Магазин начинает подготовку вашего заказа"
    prep_msg_uz = "Do'kon buyurtmangizni tayyorlaydi"
    try:
        await bot.send_message(
            order[1],
            f"✅ <b>{order_confirmed_ru if customer_lang == 'ru' else order_confirmed_uz}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"{prep_msg_ru if customer_lang == 'ru' else prep_msg_uz}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {order[1]}: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order(callback: types.CallbackQuery) -> None:
    """Cancel order by seller."""
    if not db or not bot:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
    try:
        order_id = int(callback.data.split("_")[2])
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

    db.update_order_status(order_id, "cancelled")

    offer = db.get_offer(order[3])
    if offer:
        new_quantity = get_offer_field(offer, "quantity", 0) + order[4]
        db.update_offer_quantity(order[3], new_quantity)

    await callback.message.edit_text(
        callback.message.text
        + f"\n\n❌ {'Заказ отменён' if lang == 'ru' else 'Buyurtma bekor qilindi'}"
    )

    customer_lang = db.get_user_language(order[1])
    cancel_ru = "Заказ отменён"
    cancel_uz = "Buyurtma bekor qilindi"
    cancel_msg_ru = "К сожалению, магазин отменил ваш заказ"
    cancel_msg_uz = "Afsuski, do'kon buyurtmangizni bekor qildi"
    try:
        await bot.send_message(
            order[1],
            f"❌ <b>{cancel_ru if customer_lang == 'ru' else cancel_uz}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"{cancel_msg_ru if customer_lang == 'ru' else cancel_msg_uz}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {order[1]}: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("cancel_order_customer_"))
async def cancel_order_customer(callback: types.CallbackQuery) -> None:
    """Cancel order by customer."""
    if not db or not bot:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    
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

    if order[1] != callback.from_user.id:
        await callback.answer(
            "❌ "
            + (
                "Это не ваш заказ"
                if lang == "ru"
                else "Bu sizning buyurtmangiz emas"
            ),
            show_alert=True,
        )
        return

    if order[10] not in ["pending", "confirmed"]:
        await callback.answer(
            "❌ "
            + (
                "Заказ нельзя отменить"
                if lang == "ru"
                else "Buyurtmani bekor qilib bo'lmaydi"
            ),
            show_alert=True,
        )
        return

    db.update_order_status(order_id, "cancelled")

    offer = db.get_offer(order[3])
    if offer:
        new_quantity = get_offer_field(offer, "quantity", 0) + order[4]
        db.update_offer_quantity(order[3], new_quantity)

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
            logger.error(
                f"Failed to notify seller {get_store_field(store, 'owner_id')}: {e}"
            )

    await callback.answer()
