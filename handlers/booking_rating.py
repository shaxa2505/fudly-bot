"""
Booking Rating Handler
Handles customer ratings for completed bookings
"""

from aiogram import Router, F, types
import logging

logger = logging.getLogger(__name__)

# Router for booking ratings
router = Router(name='booking_rating')


def setup(bot_instance, db_instance):
    """Initialize module with bot and database instances"""
    global bot, db
    bot = bot_instance
    db = db_instance


@router.callback_query(F.data.startswith("booking_rate_"))
async def save_booking_rating(callback: types.CallbackQuery):
    """Сохраняет оценку заказа"""
    lang = db.get_user_language(callback.from_user.id)
    parts = callback.data.split("_")
    booking_id = int(parts[2])
    rating = int(parts[3])
    
    # Получаем информацию о бронировании и магазине
    booking = db.get_booking(booking_id)
    offer = db.get_offer(booking[1])
    store_id = offer[1]
    
    # Сохраняем рейтинг
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO ratings (booking_id, user_id, store_id, rating) VALUES (?, ?, ?, ?)', 
                      (booking_id, callback.from_user.id, store_id, rating))
    
    await callback.message.edit_text(
        f"✅ Спасибо за оценку: {'⭐' * rating}\n\nВаш отзыв поможет другим покупателям!"
    )
    await callback.answer()
