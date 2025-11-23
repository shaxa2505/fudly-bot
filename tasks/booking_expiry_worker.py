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
                        SELECT booking_id, user_id, booking_code, status
                        FROM bookings
                        WHERE reminder_sent = 0
                          AND expiry_time IS NOT NULL
                          AND status IN ('pending')
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
                                booking_code = row.get('booking_code')
                                status = row.get('status')
                            else:
                                booking_id = row[0]
                                user_id = row[1]
                                booking_code = row[2] if len(row) > 2 else None
                                status = row[3] if len(row) > 3 else None

                            # Re-check booking status to avoid sending reminder for already-confirmed/completed bookings
                            try:
                                cursor.execute('SELECT status FROM bookings WHERE booking_id = %s', (booking_id,))
                                cur_row = cursor.fetchone()
                                current_status = None
                                if cur_row:
                                    # row may be tuple or dict-like depending on driver
                                    if hasattr(cur_row, 'get'):
                                        current_status = cur_row.get('status')
                                    else:
                                        current_status = cur_row[0] if len(cur_row) > 0 else None
                                if current_status not in (None, 'pending'):
                                    # Skip sending reminder for non-pending bookings
                                    try:
                                        if db:
                                            db.mark_reminder_sent(booking_id)
                                    except Exception:
                                        pass
                                    continue
                            except Exception:
                                # If re-check fails, proceed cautiously with sending the reminder
                                pass

                            # localized reminder
                            try:
                                lang = 'ru'
                                try:
                                    lang = db.get_user_language(user_id)
                                except Exception:
                                    pass

                                # Include booking code if available
                                code_part = f" (код: {booking_code})" if booking_code else ""
                                if lang == 'uz':
                                    text = (
                                        "⏰ Esingizga solamiz: bron avtomatik bekor qilinishidan 1 soat qoldi. "
                                        f"Iltimos, buyurtmangizni oling yoki kerak bo'lsa uzaytiring.{code_part}"
                                    )
                                else:
                                    text = (
                                        "⏰ Напоминание: у вас осталось 1 час до автоматической отмены брони. "
                                        f"Пожалуйста, заберите заказ или продлите его, если нужно.{code_part}"
                                    )

                                await bot.send_message(user_id, text)
                            except Exception as e:
                                logger.debug(f"Failed to send reminder to {user_id}: {e}")

                            # mark reminder_sent
                            try:
                                if db:
                                    db.mark_reminder_sent(booking_id)
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
