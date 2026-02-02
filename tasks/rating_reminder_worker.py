"""
Background worker to remind users to rate their completed orders.

Sends a gentle reminder 1 hour after order completion if user hasn't rated.
"""
import asyncio
import logging
from typing import Any

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)


async def run_rating_reminder_cycle(db: Any, bot: Bot) -> None:
    """Run a single rating reminder cycle."""
    await _send_rating_reminders(db, bot)


async def start_rating_reminder_worker(db: Any, bot: Bot) -> None:
    """Send rating reminders for unrated completed orders/bookings.

    Checks every 30 minutes for orders completed 1+ hour ago without rating.
    """
    check_interval_minutes = 30

    while True:
        try:
            await run_rating_reminder_cycle(db, bot)
        except Exception as e:
            logger.error(f"Rating reminder worker error: {e}")

        await asyncio.sleep(check_interval_minutes * 60)


async def _send_rating_reminders(db: Any, bot: Bot) -> None:
    """Find unrated completed orders and send reminders."""

    # Check completed bookings without ratings (completed 1+ hour ago)
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Find bookings completed 1-24 hours ago without rating
            cursor.execute(
                """
                SELECT DISTINCT b.booking_id, b.user_id, b.offer_id, o.title as offer_title, s.name as store_name
                FROM bookings b
                LEFT JOIN offers o ON b.offer_id = o.offer_id
                LEFT JOIN stores s ON o.store_id = s.store_id
                LEFT JOIN ratings r ON r.booking_id = b.booking_id AND r.user_id = b.user_id
                WHERE b.status = 'completed'
                  AND b.updated_at < NOW() - INTERVAL '1 hour'
                  AND b.updated_at > NOW() - INTERVAL '24 hours'
                  AND r.rating_id IS NULL
                  AND COALESCE(b.rating_reminder_sent, false) = false
                LIMIT 20
            """
            )
            bookings = cursor.fetchall()

            for booking in bookings:
                try:
                    if hasattr(booking, "get"):
                        booking_id = booking.get("booking_id")
                        user_id = booking.get("user_id")
                        offer_title = booking.get("offer_title") or "Заказ"
                        store_name = booking.get("store_name") or "Магазин"
                    else:
                        booking_id = booking[0]
                        user_id = booking[1]
                        offer_title = booking[3] if len(booking) > 3 else "Заказ"
                        store_name = booking[4] if len(booking) > 4 else "Магазин"

                    lang = db.get_user_language(user_id) or "ru"

                    await _send_rating_reminder(
                        bot, user_id, booking_id, "booking", offer_title, store_name, lang
                    )

                    # Mark reminder sent
                    cursor.execute(
                        "UPDATE bookings SET rating_reminder_sent = true WHERE booking_id = %s",
                        (booking_id,),
                    )
                    conn.commit()

                    logger.info(f"Sent rating reminder for booking {booking_id} to user {user_id}")

                except Exception as e:
                    logger.warning(f"Failed to send rating reminder for booking: {e}")
                    continue

            # Find orders completed 1-24 hours ago without rating
            cursor.execute(
                """
                SELECT DISTINCT o.order_id, o.user_id, o.store_id,
                       COALESCE(of.title, 'Заказ') as offer_title,
                       COALESCE(s.name, 'Магазин') as store_name
                FROM orders o
                LEFT JOIN offers of ON o.offer_id = of.offer_id
                LEFT JOIN stores s ON o.store_id = s.store_id
                LEFT JOIN ratings r ON r.order_id = o.order_id AND r.user_id = o.user_id
                WHERE o.order_status = 'completed'
                  AND o.updated_at < NOW() - INTERVAL '1 hour'
                  AND o.updated_at > NOW() - INTERVAL '24 hours'
                  AND r.rating_id IS NULL
                  AND COALESCE(o.rating_reminder_sent, false) = false
                LIMIT 20
            """
            )
            orders = cursor.fetchall()

            for order in orders:
                try:
                    if hasattr(order, "get"):
                        order_id = order.get("order_id")
                        user_id = order.get("user_id")
                        offer_title = order.get("offer_title") or "Заказ"
                        store_name = order.get("store_name") or "Магазин"
                    else:
                        order_id = order[0]
                        user_id = order[1]
                        offer_title = order[3] if len(order) > 3 else "Заказ"
                        store_name = order[4] if len(order) > 4 else "Магазин"

                    lang = db.get_user_language(user_id) or "ru"

                    await _send_rating_reminder(
                        bot, user_id, order_id, "order", offer_title, store_name, lang
                    )

                    # Mark reminder sent
                    cursor.execute(
                        "UPDATE orders SET rating_reminder_sent = true WHERE order_id = %s",
                        (order_id,),
                    )
                    conn.commit()

                    logger.info(f"Sent rating reminder for order {order_id} to user {user_id}")

                except Exception as e:
                    logger.warning(f"Failed to send rating reminder for order: {e}")
                    continue

    except Exception as e:
        logger.error(f"Rating reminder query failed: {e}")


async def _send_rating_reminder(
    bot: Bot,
    user_id: int,
    entity_id: int,
    entity_type: str,  # "order" or "booking"
    offer_title: str,
    store_name: str,
    lang: str,
) -> None:
    """Send a friendly rating reminder with star buttons."""

    if lang == "uz":
        text = (
            f"⭐ <b>Buyurtmangiz yoqdimi?</b>\n\n"
            f"🏪 {store_name}\n"
            f"📦 {offer_title}\n\n"
            f"5 soniyada baholang va boshqa xaridorlarga yordam bering!"
        )
    else:
        text = (
            f"⭐ <b>Понравился заказ?</b>\n\n"
            f"🏪 {store_name}\n"
            f"📦 {offer_title}\n\n"
            f"Оцените за 5 секунд и помогите другим покупателям!"
        )

    # Build rating buttons
    kb = InlineKeyboardBuilder()
    callback_prefix = f"rate_{entity_type}_{entity_id}_"

    for i in range(1, 6):
        kb.button(text="⭐" * i, callback_data=f"{callback_prefix}{i}")
    kb.adjust(5)

    try:
        await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        logger.warning(f"Failed to send rating reminder to user {user_id}: {e}")
