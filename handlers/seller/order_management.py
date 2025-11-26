"""
Seller Order Management Handlers
Handles order confirmation, cancellation, payment operations,
and courier handover for delivery orders
"""

import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.common.states import CourierHandover
from localization import get_text

logger = logging.getLogger(__name__)

# Router for seller order management
router = Router(name="seller_order_management")


def setup(bot_instance, db_instance):
    """Initialize module with bot and database instances"""
    global bot, db
    bot = bot_instance
    db = db_instance


def get_order_field(order, field: str, index: int):
    """Helper to get field from order dict or tuple."""
    if isinstance(order, dict):
        return order.get(field)
    if isinstance(order, (list, tuple)) and len(order) > index:
        return order[index]
    return None


@router.callback_query(F.data.startswith("confirm_order_"))
async def confirm_order(callback: types.CallbackQuery):
    """Подтверждение заказа продавцом"""
    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer(
            "❌ " + ("Заказ не найден" if lang == "ru" else "Buyurtma topilmadi"), show_alert=True
        )
        return

    # Обновляем статус
    db.update_order_status(order_id, "confirmed")

    # Уведомляем продавца
    await callback.message.edit_text(
        callback.message.text
        + f"\n\n✅ {'Заказ подтверждён!' if lang == 'ru' else 'Buyurtma tasdiqlandi!'}"
    )

    # Уведомляем покупателя
    customer_lang = db.get_user_language(get_order_field(order, "user_id", 1))
    preparing_ru = "Магазин начинает подготовку вашего заказа"
    preparing_uz = "Do'kon buyurtmangizni tayyorlaydi"
    try:
        await bot.send_message(
            get_order_field(order, "user_id", 1),  # user_id
            f"✅ <b>{'Заказ подтверждён!' if customer_lang == 'ru' else 'Buyurtma tasdiqlandi!'}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"{preparing_ru if customer_lang == 'ru' else preparing_uz}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {get_order_field(order, 'user_id', 1)}: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order(callback: types.CallbackQuery):
    """Отмена заказа продавцом"""
    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer(
            "❌ " + ("Заказ не найден" if lang == "ru" else "Buyurtma topilmadi"), show_alert=True
        )
        return

    # Обновляем статус
    db.update_order_status(order_id, "cancelled")

    # Helper for dict/tuple
    def get_field(item, field, index):
        return (
            item.get(field)
            if isinstance(item, dict)
            else (item[index] if len(item) > index else None)
        )

    # Возвращаем товар в наличие
    offer_id = get_field(order, "offer_id", 3)
    quantity = get_field(order, "quantity", 4)
    offer = db.get_offer(offer_id)
    if offer:
        try:
            db.increment_offer_quantity_atomic(offer_id, quantity)
        except Exception as e:
            logger.error(f"Failed to restore quantity for offer {offer_id}: {e}")

    # Уведомляем продавца
    await callback.message.edit_text(
        callback.message.text
        + f"\n\n❌ {'Заказ отменён' if lang == 'ru' else 'Buyurtma bekor qilindi'}"
    )

    # Уведомляем покупателя
    customer_lang = db.get_user_language(get_order_field(order, "user_id", 1))
    cancelled_ru = "К сожалению, магазин отменил ваш заказ"
    cancelled_uz = "Afsuski, do'kon buyurtmangizni bekor qildi"
    try:
        await bot.send_message(
            get_order_field(order, "user_id", 1),  # user_id
            f"❌ <b>{'Заказ отменён' if customer_lang == 'ru' else 'Buyurtma bekor qilindi'}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"{cancelled_ru if customer_lang == 'ru' else cancelled_uz}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {get_order_field(order, 'user_id', 1)}: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("confirm_payment_"))
async def confirm_payment(callback: types.CallbackQuery):
    """Подтверждение оплаты продавцом"""
    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer(
            "❌ " + ("Заказ не найден" if lang == "ru" else "Buyurtma topilmadi"), show_alert=True
        )
        return

    # Обновляем статус оплаты
    db.update_payment_status(order_id, "confirmed")
    # Обновляем статус заказа на "preparing" (готовится)
    db.update_order_status(order_id, "preparing")

    # Создаём кнопку "Передать курьеру"
    kb = InlineKeyboardBuilder()
    handover_text = "🚕 Передать курьеру" if lang == "ru" else "🚕 Kuryerga topshirish"
    kb.button(text=handover_text, callback_data=f"handover_courier_{order_id}")

    # Уведомляем продавца с кнопкой
    payment_confirmed_text = "Оплата подтверждена!" if lang == "ru" else "To'lov tasdiqlandi!"
    next_step_text = (
        "Когда заказ будет готов, передайте его курьеру"
        if lang == "ru"
        else "Buyurtma tayyor bo'lganda, kuryerga topshiring"
    )

    try:
        await callback.message.edit_caption(
            caption=callback.message.caption
            + f"\n\n✅ {payment_confirmed_text}\n\n📝 {next_step_text}",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        # Если нет caption (текстовое сообщение)
        await callback.message.edit_text(
            callback.message.text + f"\n\n✅ {payment_confirmed_text}\n\n📝 {next_step_text}",
            reply_markup=kb.as_markup(),
        )

    # Уведомляем покупателя
    customer_lang = db.get_user_language(get_order_field(order, "user_id", 1))
    preparing_ru = (
        "Магазин начинает подготовку вашего заказа. Ожидайте уведомление о передаче курьеру!"
    )
    preparing_uz = "Do'kon buyurtmangizni tayyorlaydi. Kuryerga topshirish haqida xabar kuting!"
    payment_confirmed_uz = "To'lov tasdiqlandi!"
    try:
        await bot.send_message(
            get_order_field(order, "user_id", 1),  # user_id
            f"✅ <b>{'Оплата подтверждена!' if customer_lang == 'ru' else payment_confirmed_uz}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"👨‍🍳 {preparing_ru if customer_lang == 'ru' else preparing_uz}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {get_order_field(order, 'user_id', 1)}: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(callback: types.CallbackQuery):
    """Отклонение оплаты продавцом"""
    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer(
            "❌ " + ("Заказ не найден" if lang == "ru" else "Buyurtma topilmadi"), show_alert=True
        )
        return

    # Обновляем статусы
    db.update_payment_status(order_id, "pending")
    db.update_order_status(order_id, "cancelled")

    # Helper for dict/tuple
    def get_field(item, field, index):
        return (
            item.get(field)
            if isinstance(item, dict)
            else (item[index] if len(item) > index else None)
        )

    # Возвращаем товар в наличие
    offer_id = get_field(order, "offer_id", 3)
    quantity = get_field(order, "quantity", 4)
    offer = db.get_offer(offer_id)
    if offer:
        try:
            db.increment_offer_quantity_atomic(offer_id, quantity)
        except Exception as e:
            logger.error(f"Failed to restore quantity for offer {offer_id}: {e}")

    # Уведомляем продавца
    payment_rejected_text = (
        "Оплата отклонена, заказ отменён"
        if lang == "ru"
        else "To'lov rad etildi, buyurtma bekor qilindi"
    )
    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n❌ {payment_rejected_text}"
    )

    # Уведомляем покупателя
    customer_lang = db.get_user_language(get_order_field(order, "user_id", 1))
    payment_failed_ru = "Магазин не смог подтвердить вашу оплату. Заказ отменён."
    payment_failed_uz = "Do'kon to'lovingizni tasdiqlay olmadi. Buyurtma bekor qilindi."
    check_payment_ru = "Пожалуйста, проверьте правильность перевода или свяжитесь с магазином"
    check_payment_uz = "Iltimos, o'tkazma to'g'riligini tekshiring yoki do'kon bilan bog'laning"
    payment_rejected_uz = "To'lov tasdiqlanmadi"
    try:
        await bot.send_message(
            get_order_field(order, "user_id", 1),  # user_id
            f"❌ <b>{'Оплата не подтверждена' if customer_lang == 'ru' else payment_rejected_uz}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"{payment_failed_ru if customer_lang == 'ru' else payment_failed_uz}\n"
            f"{check_payment_ru if customer_lang == 'ru' else check_payment_uz}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {get_order_field(order, 'user_id', 1)}: {e}")

    await callback.answer()


# ============== COURIER HANDOVER FLOW ==============


@router.callback_query(F.data.startswith("handover_courier_"))
async def start_courier_handover(callback: types.CallbackQuery, state: FSMContext):
    """Начало передачи заказа курьеру - запрос имени курьера"""
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
            "❌ " + ("Заказ не найден" if lang == "ru" else "Buyurtma topilmadi"), show_alert=True
        )
        return

    # Сохраняем order_id в состояние
    await state.set_state(CourierHandover.courier_name)
    await state.update_data(order_id=order_id)

    prompt_ru = "📝 Введите имя курьера/таксиста:"
    prompt_uz = "📝 Kuryer/taksi haydovchisi ismini kiriting:"

    await callback.message.answer(prompt_ru if lang == "ru" else prompt_uz)
    await callback.answer()


@router.message(CourierHandover.courier_name)
async def process_courier_name(message: types.Message, state: FSMContext):
    """Обработка имени курьера - запрос телефона"""
    lang = db.get_user_language(message.from_user.id)

    courier_name = message.text.strip()
    if not courier_name or len(courier_name) < 2:
        error_text = "❌ Введите корректное имя" if lang == "ru" else "❌ To'g'ri ism kiriting"
        await message.answer(error_text)
        return

    await state.update_data(courier_name=courier_name)
    await state.set_state(CourierHandover.courier_phone)

    prompt_ru = "📱 Введите телефон курьера/таксиста:"
    prompt_uz = "📱 Kuryer/taksi haydovchisi telefonini kiriting:"

    await message.answer(prompt_ru if lang == "ru" else prompt_uz)


@router.message(CourierHandover.courier_phone)
async def process_courier_phone(message: types.Message, state: FSMContext):
    """Обработка телефона курьера - завершение передачи"""
    lang = db.get_user_language(message.from_user.id)

    courier_phone = message.text.strip()
    # Простая валидация телефона
    phone_digits = "".join(filter(str.isdigit, courier_phone))
    if len(phone_digits) < 9:
        error_text = (
            "❌ Введите корректный номер телефона"
            if lang == "ru"
            else "❌ To'g'ri telefon raqamini kiriting"
        )
        await message.answer(error_text)
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    courier_name = data.get("courier_name")

    await state.clear()

    order = db.get_order(order_id)
    if not order:
        error_text = "❌ Заказ не найден" if lang == "ru" else "❌ Buyurtma topilmadi"
        await message.answer(error_text)
        return

    # Обновляем статус заказа на "delivering"
    db.update_order_status(order_id, "delivering")

    # Получаем данные для уведомлений
    customer_id = get_order_field(order, "user_id", 1)
    customer_lang = db.get_user_language(customer_id)
    delivery_address = get_order_field(order, "delivery_address", 6)

    # Уведомляем продавца об успешной передаче
    success_ru = f"✅ Заказ #{order_id} передан курьеру!\n\n🚕 Курьер: {courier_name}\n📱 Телефон: {courier_phone}"
    success_uz = f"✅ Buyurtma #{order_id} kuryerga topshirildi!\n\n🚕 Kuryer: {courier_name}\n📱 Telefon: {courier_phone}"
    await message.answer(success_ru if lang == "ru" else success_uz)

    # Уведомляем клиента с кнопкой "Получил заказ"
    kb = InlineKeyboardBuilder()
    received_btn_text = "✅ Получил заказ" if customer_lang == "ru" else "✅ Buyurtmani oldim"
    kb.button(text=received_btn_text, callback_data=f"order_received_{order_id}")

    customer_msg_ru = (
        f"🚕 <b>Ваш заказ передан курьеру!</b>\n\n"
        f"📦 Заказ #{order_id}\n"
        f"👤 Курьер: {courier_name}\n"
        f"📱 Телефон: {courier_phone}\n\n"
        f"📍 Адрес доставки: {delivery_address}\n\n"
        f"Когда получите заказ, нажмите кнопку ниже:"
    )
    customer_msg_uz = (
        f"🚕 <b>Buyurtmangiz kuryerga topshirildi!</b>\n\n"
        f"📦 Buyurtma #{order_id}\n"
        f"👤 Kuryer: {courier_name}\n"
        f"📱 Telefon: {courier_phone}\n\n"
        f"📍 Yetkazib berish manzili: {delivery_address}\n\n"
        f"Buyurtmani olganingizda, quyidagi tugmani bosing:"
    )

    try:
        await bot.send_message(
            customer_id,
            customer_msg_ru if customer_lang == "ru" else customer_msg_uz,
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {customer_id}: {e}")


@router.callback_query(F.data.startswith("order_received_"))
async def order_received_by_customer(callback: types.CallbackQuery):
    """Клиент подтвердил получение заказа"""
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
            "❌ " + ("Заказ не найден" if lang == "ru" else "Buyurtma topilmadi"), show_alert=True
        )
        return

    # Проверяем, что это заказ текущего пользователя
    if get_order_field(order, "user_id", 1) != callback.from_user.id:
        await callback.answer(
            "❌ " + ("Это не ваш заказ" if lang == "ru" else "Bu sizning buyurtmangiz emas"),
            show_alert=True,
        )
        return

    # Обновляем статус на "completed"
    db.update_order_status(order_id, "completed")

    # Обновляем сообщение клиенту
    completed_text_ru = "✅ Заказ успешно доставлен!\n\nСпасибо за покупку! 🎉"
    completed_text_uz = "✅ Buyurtma muvaffaqiyatli yetkazildi!\n\nXaridingiz uchun rahmat! 🎉"

    try:
        await callback.message.edit_text(
            callback.message.text
            + f"\n\n{'─' * 20}\n\n"
            + (completed_text_ru if lang == "ru" else completed_text_uz),
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Предлагаем оценить заказ
    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text="⭐" * i, callback_data=f"rate_order_{order_id}_{i}")
    kb.adjust(5)

    rate_prompt_ru = "Как вам понравился заказ? Оцените от 1 до 5 звёзд:"
    rate_prompt_uz = "Buyurtma qanday bo'ldi? 1 dan 5 gacha yulduz bilan baholang:"

    await callback.message.answer(
        rate_prompt_ru if lang == "ru" else rate_prompt_uz, reply_markup=kb.as_markup()
    )

    # Уведомляем продавца
    offer_id = get_order_field(order, "offer_id", 2)
    offer = db.get_offer(offer_id)
    if offer:
        store_id = offer.get("store_id") if isinstance(offer, dict) else offer[2]
        store = db.get_store(store_id)
        if store:
            seller_id = store.get("owner_id") if isinstance(store, dict) else store[2]
            seller_lang = db.get_user_language(seller_id)

            seller_msg_ru = (
                f"✅ <b>Заказ #{order_id} доставлен!</b>\n\nКлиент подтвердил получение."
            )
            seller_msg_uz = (
                f"✅ <b>Buyurtma #{order_id} yetkazildi!</b>\n\nMijoz qabul qilganini tasdiqladi."
            )

            try:
                await bot.send_message(
                    seller_id,
                    seller_msg_ru if seller_lang == "ru" else seller_msg_uz,
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Failed to notify seller {seller_id}: {e}")

    await callback.answer("✅")


@router.callback_query(F.data.startswith("rate_order_"))
async def rate_order(callback: types.CallbackQuery):
    """Оценка заказа клиентом"""
    lang = db.get_user_language(callback.from_user.id)

    try:
        parts = callback.data.split("_")
        order_id = int(parts[2])
        rating = int(parts[3])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid rating callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer(
            "❌ " + ("Заказ не найден" if lang == "ru" else "Buyurtma topilmadi"), show_alert=True
        )
        return

    # TODO: Сохранить рейтинг в БД (можно добавить поле rating в orders или отдельную таблицу)
    # db.save_order_rating(order_id, callback.from_user.id, rating)

    thanks_ru = f"Спасибо за оценку! {'⭐' * rating}\n\nБудем рады видеть вас снова! 😊"
    thanks_uz = f"Baholaganingiz uchun rahmat! {'⭐' * rating}\n\nSizni yana kutamiz! 😊"

    await callback.message.edit_text(thanks_ru if lang == "ru" else thanks_uz)
    await callback.answer()
