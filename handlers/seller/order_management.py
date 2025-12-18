"""
Seller Order Management Handlers
Handles order confirmation, cancellation, payment operations,
and courier handover for delivery orders
"""

import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.utils import get_field, get_store_field
from app.services.unified_order_service import get_unified_order_service
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

    # Verify store ownership
    store_id = get_order_field(order, "store_id", 2)
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, "owner_id") if store else None

    if callback.from_user.id != owner_id:
        await callback.answer("❌", show_alert=True)
        return

    # Используем UnifiedOrderService для обновления статуса
    service = get_unified_order_service()
    await service.confirm_order(order_id, "order")

    # Уведомляем продавца
    await callback.message.edit_text(
        callback.message.text
        + f"\n\n✅ {'Заказ подтверждён!' if lang == 'ru' else 'Buyurtma tasdiqlandi!'}"
    )

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

    # Verify store ownership
    store_id = get_order_field(order, "store_id", 2)
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, "owner_id") if store else None

    if callback.from_user.id != owner_id:
        await callback.answer("❌", show_alert=True)
        return

    # Используем UnifiedOrderService для отмены заказа
    service = get_unified_order_service()
    await service.cancel_order(order_id, "Отменено продавцом", "Seller cancelled")

    # Уведомляем продавца
    await callback.message.edit_text(
        callback.message.text
        + f"\n\n❌ {'Заказ отменён' if lang == 'ru' else 'Buyurtma bekor qilindi'}"
    )

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

    # Verify store ownership
    store_id = get_order_field(order, "store_id", 2)
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, "owner_id") if store else None

    if callback.from_user.id != owner_id:
        await callback.answer("❌", show_alert=True)
        return

    # Используем UnifiedOrderService для подтверждения заказа
    service = get_unified_order_service()
    await service.confirm_order(order_id, "order")

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

    # Verify store ownership
    store_id = get_order_field(order, "store_id", 2)
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, "owner_id") if store else None

    if callback.from_user.id != owner_id:
        await callback.answer("❌", show_alert=True)
        return

    # Используем UnifiedOrderService для отклонения (отмены)
    service = get_unified_order_service()
    await service.reject_order(
        order_id, 
        "Оплата не подтверждена" if lang == "ru" else "To'lov tasdiqlanmadi"
    )

    # Уведомляем продавца
    payment_rejected_text = (
        "Оплата отклонена, заказ отменён"
        if lang == "ru"
        else "To'lov rad etildi, buyurtma bekor qilindi"
    )
    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n❌ {payment_rejected_text}"
    )

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

    # Verify store ownership
    store_id = get_order_field(order, "store_id", 2)
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, "owner_id") if store else None

    if callback.from_user.id != owner_id:
        await callback.answer("❌", show_alert=True)
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

    # Используем UnifiedOrderService для начала доставки
    service = get_unified_order_service()
    await service.start_delivery(order_id)

    # Уведомляем продавца об успешной передаче
    success_ru = f"✅ Заказ #{order_id} передан курьеру!\n\n🚕 Курьер: {courier_name}\n📱 Телефон: {courier_phone}"
    success_uz = f"✅ Buyurtma #{order_id} kuryerga topshirildi!\n\n🚕 Kuryer: {courier_name}\n📱 Telefon: {courier_phone}"
    await message.answer(success_ru if lang == "ru" else success_uz)

    # Дополнительное сообщение клиенту с информацией о курьере
    customer_id = get_order_field(order, "user_id", 1)
    customer_lang = db.get_user_language(customer_id)
    delivery_address = get_order_field(order, "delivery_address", 6)

    kb = InlineKeyboardBuilder()
    received_btn_text = "✅ Получил заказ" if customer_lang == "ru" else "✅ Buyurtmani oldim"
    kb.button(text=received_btn_text, callback_data=f"order_received_{order_id}")

    courier_info_ru = (
        f"\n\n👤 Курьер: {courier_name}\n"
        f"📱 Телефон: {courier_phone}\n"
        f"📍 Адрес: {delivery_address}"
    )
    courier_info_uz = (
        f"\n\n👤 Kuryer: {courier_name}\n"
        f"📱 Telefon: {courier_phone}\n"
        f"📍 Manzil: {delivery_address}"
    )

    try:
        await bot.send_message(
            customer_id,
            (courier_info_ru if customer_lang == "ru" else courier_info_uz) + 
            ("\n\nКогда получите заказ, нажмите кнопку ниже:" if customer_lang == "ru" 
             else "\n\nBuyurtmani olganingizda, quyidagi tugmani bosing:"),
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

    # Используем UnifiedOrderService для завершения заказа
    service = get_unified_order_service()
    await service.complete_order(order_id)

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

    # Verify order belongs to this customer
    order_user_id = get_order_field(order, "user_id", 1)
    if callback.from_user.id != order_user_id:
        await callback.answer("❌", show_alert=True)
        return

    # Check if already rated
    if hasattr(db, "has_rated_order") and db.has_rated_order(order_id):
        await callback.answer(
            "Вы уже оценили этот заказ"
            if lang == "ru"
            else "Siz bu buyurtmani allaqachon baholadingiz",
            show_alert=True,
        )
        return

    # Get store_id from order
    store_id = get_order_field(order, "store_id", 2)
    user_id = callback.from_user.id

    # Save rating to database
    if store_id and hasattr(db, "add_order_rating"):
        rating_id = db.add_order_rating(order_id, user_id, store_id, rating)
        if rating_id:
            logger.info(f"✅ Order {order_id} rated {rating} stars by user {user_id}")
        else:
            logger.warning(f"Failed to save rating for order {order_id}")

    thanks_ru = f"Спасибо за оценку! {'⭐' * rating}\n\nБудем рады видеть вас снова! 😊"
    thanks_uz = f"Baholaganingiz uchun rahmat! {'⭐' * rating}\n\nSizni yana kutamiz! 😊"

    await callback.message.edit_text(thanks_ru if lang == "ru" else thanks_uz)
    await callback.answer()
