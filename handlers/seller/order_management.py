"""
Seller Order Management Handlers
Handles order confirmation, cancellation, and payment operations
"""

import logging
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from localization import get_text

logger = logging.getLogger(__name__)

# Router for seller order management
router = Router(name='seller_order_management')


def setup(bot_instance, db_instance):
    """Initialize module with bot and database instances"""
    global bot, db
    bot = bot_instance
    db = db_instance


@router.callback_query(F.data.startswith("confirm_order_"))
async def confirm_order(callback: types.CallbackQuery):
    """Подтверждение заказа продавцом"""
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        order_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ " + ("Заказ не найден" if lang == 'ru' else "Buyurtma topilmadi"), show_alert=True)
        return
    
    # Обновляем статус
    db.update_order_status(order_id, 'confirmed')
    
    # Уведомляем продавца
    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ {'Заказ подтверждён!' if lang == 'ru' else 'Buyurtma tasdiqlandi!'}"
    )
    
    # Уведомляем покупателя
    customer_lang = db.get_user_language(order[1])
    preparing_ru = 'Магазин начинает подготовку вашего заказа'
    preparing_uz = "Do'kon buyurtmangizni tayyorlaydi"
    try:
        await bot.send_message(
            order[1],  # user_id
            f"✅ <b>{'Заказ подтверждён!' if customer_lang == 'ru' else 'Buyurtma tasdiqlandi!'}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"{preparing_ru if customer_lang == 'ru' else preparing_uz}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {order[1]}: {e}")
    
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order(callback: types.CallbackQuery):
    """Отмена заказа продавцом"""
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        order_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ " + ("Заказ не найден" if lang == 'ru' else "Buyurtma topilmadi"), show_alert=True)
        return
    
    # Обновляем статус
    db.update_order_status(order_id, 'cancelled')
    
    # Helper for dict/tuple
    def get_field(item, field, index):
        return item.get(field) if isinstance(item, dict) else (item[index] if len(item) > index else None)
    
    # Возвращаем товар в наличие
    offer_id = get_field(order, 'offer_id', 3)
    quantity = get_field(order, 'quantity', 4)
    offer = db.get_offer(offer_id)
    if offer:
        offer_quantity = get_field(offer, 'quantity', 6)
        new_quantity = offer_quantity + quantity
        db.update_offer_quantity(offer_id, new_quantity)
    
    # Уведомляем продавца
    await callback.message.edit_text(
        callback.message.text + f"\n\n❌ {'Заказ отменён' if lang == 'ru' else 'Buyurtma bekor qilindi'}"
    )
    
    # Уведомляем покупателя
    customer_lang = db.get_user_language(order[1])
    cancelled_ru = 'К сожалению, магазин отменил ваш заказ'
    cancelled_uz = "Afsuski, do'kon buyurtmangizni bekor qildi"
    try:
        await bot.send_message(
            order[1],  # user_id
            f"❌ <b>{'Заказ отменён' if customer_lang == 'ru' else 'Buyurtma bekor qilindi'}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"{cancelled_ru if customer_lang == 'ru' else cancelled_uz}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {order[1]}: {e}")
    
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_payment_"))
async def confirm_payment(callback: types.CallbackQuery):
    """Подтверждение оплаты продавцом"""
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        order_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ " + ("Заказ не найден" if lang == 'ru' else "Buyurtma topilmadi"), show_alert=True)
        return
    
    # Обновляем статус оплаты
    db.update_payment_status(order_id, 'confirmed')
    # Обновляем статус заказа
    db.update_order_status(order_id, 'confirmed')
    
    # Уведомляем продавца
    payment_confirmed_text = 'Оплата подтверждена!' if lang == 'ru' else "To'lov tasdiqlandi!"
    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n✅ {payment_confirmed_text}"
    )
    
    # Уведомляем покупателя
    customer_lang = db.get_user_language(order[1])
    preparing_ru = 'Магазин начинает подготовку вашего заказа'
    preparing_uz = "Do'kon buyurtmangizni tayyorlaydi"
    payment_confirmed_uz = "To'lov tasdiqlandi!"
    try:
        await bot.send_message(
            order[1],  # user_id
            f"✅ <b>{'Оплата подтверждена!' if customer_lang == 'ru' else payment_confirmed_uz}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"{preparing_ru if customer_lang == 'ru' else preparing_uz}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {order[1]}: {e}")
    
    await callback.answer()


@router.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(callback: types.CallbackQuery):
    """Отклонение оплаты продавцом"""
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        order_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid order_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ " + ("Заказ не найден" if lang == 'ru' else "Buyurtma topilmadi"), show_alert=True)
        return
    
    # Обновляем статусы
    db.update_payment_status(order_id, 'pending')
    db.update_order_status(order_id, 'cancelled')
    
    # Helper for dict/tuple
    def get_field(item, field, index):
        return item.get(field) if isinstance(item, dict) else (item[index] if len(item) > index else None)
    
    # Возвращаем товар в наличие
    offer_id = get_field(order, 'offer_id', 3)
    quantity = get_field(order, 'quantity', 4)
    offer = db.get_offer(offer_id)
    if offer:
        offer_quantity = get_field(offer, 'quantity', 6)
        new_quantity = offer_quantity + quantity
        db.update_offer_quantity(offer_id, new_quantity)
    
    # Уведомляем продавца
    payment_rejected_text = 'Оплата отклонена, заказ отменён' if lang == 'ru' else "To'lov rad etildi, buyurtma bekor qilindi"
    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n❌ {payment_rejected_text}"
    )
    
    # Уведомляем покупателя
    customer_lang = db.get_user_language(order[1])
    payment_failed_ru = 'Магазин не смог подтвердить вашу оплату. Заказ отменён.'
    payment_failed_uz = "Do'kon to'lovingizni tasdiqlay olmadi. Buyurtma bekor qilindi."
    check_payment_ru = 'Пожалуйста, проверьте правильность перевода или свяжитесь с магазином'
    check_payment_uz = "Iltimos, o'tkazma to'g'riligini tekshiring yoki do'kon bilan bog'laning"
    payment_rejected_uz = "To'lov tasdiqlanmadi"
    try:
        await bot.send_message(
            order[1],  # user_id
            f"❌ <b>{'Оплата не подтверждена' if customer_lang == 'ru' else payment_rejected_uz}</b>\n\n"
            f"📦 {'Заказ' if customer_lang == 'ru' else 'Buyurtma'} #{order_id}\n"
            f"{payment_failed_ru if customer_lang == 'ru' else payment_failed_uz}\n"
            f"{check_payment_ru if customer_lang == 'ru' else check_payment_uz}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {order[1]}: {e}")
    
    await callback.answer()
