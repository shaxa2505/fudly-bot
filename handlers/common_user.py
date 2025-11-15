"""
Common User Handlers
Shared functionality like mode switching
"""

from typing import Any
from aiogram import Router, F, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import logging

logger = logging.getLogger(__name__)

# Router for common user handlers
router = Router(name='common_user')


@router.message(F.text.contains("🎫") | F.text.contains("Заказы") | F.text.contains("Buyurtmalar"))
async def my_orders_handler(message: types.Message) -> None:
    """Handler for Orders button - show user's bookings and orders."""
    if not db:
        await message.answer("System error")
        return
    
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    
    # Get user bookings
    bookings = db.get_user_bookings(user_id)
    
    if not bookings:
        text = "У вас пока нет заказов" if lang == "ru" else "Sizda hali buyurtmalar yo'q"
        await message.answer(text)
        return
    
    # Group by status
    active = [b for b in bookings if b[3] in ("pending", "confirmed")]
    completed = [b for b in bookings if b[3] == "completed"]
    cancelled = [b for b in bookings if b[3] == "cancelled"]
    
    text = "📦 <b>Мои заказы</b>\n\n" if lang == "ru" else "📦 <b>Mening buyurtmalarim</b>\n\n"
    
    if active:
        text += f"🟢 {'Активные' if lang == 'ru' else 'Faol'}: {len(active)}\n"
    if completed:
        text += f"✅ {'Завершённые' if lang == 'ru' else 'Yakunlangan'}: {len(completed)}\n"
    if cancelled:
        text += f"❌ {'Отменённые' if lang == 'ru' else 'Bekor qilingan'}: {len(cancelled)}\n"
    
    await message.answer(text, parse_mode="HTML")


def setup(
    bot_instance: Any,
    db_instance: Any,
    user_view_mode_dict: Any,
    get_text_func: Any,
    main_menu_func: Any,
) -> None:
    """Initialize module with bot and database instances"""
    global bot, db, user_view_mode, get_text, main_menu_customer
    bot = bot_instance
    db = db_instance
    user_view_mode = user_view_mode_dict
    get_text = get_text_func
    main_menu_customer = main_menu_func


@router.message(F.text.contains("Режим покупателя") | F.text.contains("Xaridor rejimi"))
async def switch_to_customer(message: types.Message):
    """Switch user to customer mode"""
    if not db or not get_text or not main_menu_customer or not user_view_mode:
        logger.error("❌ switch_to_customer: dependencies not initialized!")
        await message.answer("System error: dependencies not initialized")
        return
    
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    
    logger.info(f"🔄 User {user_id} switching to customer mode")
    
    # Remember that the user prefers customer view until changed
    user_view_mode[user_id] = 'customer'
    
    await message.answer(
        get_text(lang, 'switched_to_customer'),
        reply_markup=main_menu_customer(lang)
    )
    
    logger.info(f"✅ User {user_id} switched to customer mode successfully")
