import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

async def start_booking_expiry_worker(db: Any, bot: Any) -> None:
    """Periodic worker that sends reminders and cancels expired bookings.

    - Sends a reminder 1 hour before expiry (sets `reminder_sent`)
    - Cancels expired bookings and returns reserved quantity to offers
    """
    check_interval = getattr(db, 'BOOKING_EXPIRY_CHECK_MINUTES', 30)

    while True:
        try:
            # 1) Reminders: bookings with expiry_time within next 1 hour and reminder_sent = 0
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor(row_factory=None)
                    cursor.execute("""
                        SELECT booking_id, user_id
                        FROM bookings
                        WHERE reminder_sent = 0
                          AND expiry_time IS NOT NULL
                          AND expiry_time > now()
                          AND expiry_time <= now() + INTERVAL '1 hour'
                    """)
                    rows = cursor.fetchall()
                    for row in rows:
                        try:
                            # support dict-like or tuple rows
                            if hasattr(row, 'get'):
                                booking_id = row.get('booking_id')
                                user_id = row.get('user_id')
                            else:
                                booking_id = row[0]
                                user_id = row[1]

                            # localized reminder
                            try:
                                lang = 'ru'
                                try:
                                    lang = db.get_user_language(user_id)
                                except Exception:
                                    pass

                                if lang == 'uz':
                                    text = (
                                        "⏰ Esingizga solamiz: bron avtomatik bekor qilinishidan 1 soat qoldi. "
                                        "Iltimos, buyurtmangizni oling yoki kerak bo'lsa uzaytiring."
                                    )
                                else:
                                    text = (
                                        "⏰ Напоминание: у вас осталось 1 час до автоматической отмены брони. "
                                        "Пожалуйста, заберите заказ или продлите его, если нужно."
                                    )

                                await bot.send_message(user_id, text)
                            except Exception as e:
                                logger.debug(f"Failed to send reminder to {user_id}: {e}")

                            # mark reminder_sent
                            try:
                                cursor.execute('UPDATE bookings SET reminder_sent = 1 WHERE booking_id = %s', (booking_id,))
                            except Exception as e:
                                logger.error(f"Failed to mark reminder_sent for booking {booking_id}: {e}")
                        except Exception as e:
                            logger.error(f"Error processing reminder row: {e}")
            except Exception as e:
                logger.error(f"Reminder query failed: {e}")

            # 2) Expired bookings: cancel and return quantity
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor(row_factory=None)
                    cursor.execute("""
                        SELECT booking_id, user_id, offer_id, quantity
                        FROM bookings
                        WHERE status IN ('pending','active')
                          AND expiry_time IS NOT NULL
                          AND expiry_time <= now()
                    """)
                    rows = cursor.fetchall()
                    for row in rows:
                        try:
                            if hasattr(row, 'get'):
                                booking_id = row.get('booking_id')
                                user_id = row.get('user_id')
                                offer_id = row.get('offer_id')
                                quantity = int(row.get('quantity') or 0)
                            else:
                                booking_id = row[0]
                                user_id = row[1]
                                offer_id = row[2]
                                quantity = int(row[3] or 0)

                            # Cancel booking in DB
                            try:
                                db.cancel_booking(booking_id)
                            except Exception as e:
                                logger.error(f"Failed to cancel booking {booking_id}: {e}")

                            # Return quantity atomically
                            try:
                                if offer_id and quantity > 0:
                                    db.increment_offer_quantity_atomic(offer_id, quantity)
                            except Exception as e:
                                logger.error(f"Failed to increment offer {offer_id} by {quantity}: {e}")

                            # Notify user about auto-cancel (localized)
                            try:
                                lang = 'ru'
                                try:
                                    lang = db.get_user_language(user_id)
                                except Exception:
                                    pass

                                if lang == 'uz':
                                    text = (
                                        "❌ Bron avtomatik ravishda bekor qilindi, chunki kutish vaqti tugadi. "
                                        "Mahsulot miqdori qaytarildi va yana mavjud bo'ldi."
                                    )
                                else:
                                    text = (
                                        "❌ Ваша бронь была автоматически отменена, так как время ожидания истекло. "
                                        "Количество товара возвращено в доступность."
                                    )

                                await bot.send_message(user_id, text)
                            except Exception as e:
                                logger.debug(f"Failed to notify user {user_id} about auto-cancel: {e}")
                        except Exception as e:
                            logger.error(f"Error processing expired booking row: {e}")
            except Exception as e:
                logger.error(f"Expired booking query failed: {e}")

        except Exception as e:
            logger.error(f"Booking expiry worker failed: {e}")

        await asyncio.sleep(check_interval * 60)
