import asyncio
import logging
import os
from typing import Any

from app.keyboards import main_menu_customer
from localization import get_text

logger = logging.getLogger(__name__)


async def run_booking_expiry_cycle(db: Any, bot: Any) -> None:
    """Run a single booking expiry/reminder cycle."""
    pending_expiry_minutes = int(os.environ.get("PICKUP_PENDING_EXPIRY_MINUTES", "60"))
    delivery_pending_expiry_minutes = int(os.environ.get("DELIVERY_PENDING_EXPIRY_MINUTES", "120"))
    ready_expiry_hours = int(os.environ.get("PICKUP_READY_EXPIRY_HOURS", "2"))

    order_service = None
    set_order_status_direct = None
    set_booking_status_direct = None
    order_status_cancelled = "cancelled"
    try:
        from app.services.unified_order_service import (
            OrderStatus,
            get_unified_order_service,
            init_unified_order_service,
            set_order_status_direct,
        )

        order_service = get_unified_order_service()
        if not order_service and bot:
            order_service = init_unified_order_service(db, bot)
        order_status_cancelled = OrderStatus.CANCELLED
    except Exception as e:
        logger.error(f"Failed to init UnifiedOrderService for order auto-cancel: {e}")

    try:
        from app.services.booking_service import set_booking_status_direct
    except Exception:
        set_booking_status_direct = None

    # 1) Reminders: bookings with expiry_time within next 1 hour and reminder_sent = 0
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT booking_id, user_id, booking_code, status
                FROM bookings
                WHERE reminder_sent = 0
                  AND expiry_time IS NOT NULL
                  AND status IN ('pending')
                  AND delivery_option = 0
                  AND expiry_time > now()
                  AND expiry_time <= now() + INTERVAL '1 hour'
            """
            )
            rows = cursor.fetchall()
            for row in rows:
                try:
                    # support dict-like or tuple rows
                    if hasattr(row, "get"):
                        booking_id = row.get("booking_id")
                        user_id = row.get("user_id")
                        booking_code = row.get("booking_code")
                        status = row.get("status")
                    else:
                        booking_id = row[0]
                        user_id = row[1]
                        booking_code = row[2] if len(row) > 2 else None
                        status = row[3] if len(row) > 3 else None

                    # Re-check booking status to avoid sending reminder for already-confirmed/completed bookings
                    try:
                        cursor.execute(
                            "SELECT status FROM bookings WHERE booking_id = %s",
                            (booking_id,),
                        )
                        cur_row = cursor.fetchone()
                        current_status = None
                        if cur_row:
                            # row may be tuple or dict-like depending on driver
                            if hasattr(cur_row, "get"):
                                current_status = cur_row.get("status")
                            else:
                                current_status = cur_row[0] if len(cur_row) > 0 else None
                        if current_status not in (None, "pending"):
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
                        lang = "ru"
                        try:
                            lang = db.get_user_language(user_id)
                        except Exception:
                            pass

                        # Include booking code if available
                        code_part = f" (код: {booking_code})" if booking_code else ""
                        if lang == "uz":
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
                        logger.error(
                            f"Failed to mark reminder_sent for booking {booking_id}: {e}"
                        )
                except Exception as e:
                    logger.error(f"Error processing reminder row: {e}")
    except Exception as e:
        logger.error(f"Reminder query failed: {e}")

    # 1.5) Partner reminders: bookings pending > 30 minutes without partner action
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT b.booking_id, b.store_id, b.user_id, b.booking_code, b.is_cart_booking
                FROM bookings b
                WHERE b.status = 'pending'
                  AND b.partner_reminder_sent = 0
                  AND b.created_at < now() - INTERVAL '30 minutes'
                LIMIT 50
            """
            )
            rows = cursor.fetchall()
            for row in rows:
                try:
                    if hasattr(row, "get"):
                        booking_id = row.get("booking_id")
                        store_id = row.get("store_id")
                        user_id = row.get("user_id")
                        booking_code = row.get("booking_code")
                        is_cart = int(row.get("is_cart_booking") or 0)
                    else:
                        booking_id = row[0]
                        store_id = row[1]
                        user_id = row[2]
                        booking_code = row[3]
                        is_cart = int(row[4] if len(row) > 4 else 0)

                    # Get store owner
                    try:
                        store = db.get_store(store_id)
                        if store:
                            if hasattr(store, "get"):
                                owner_id = store.get("owner_id")
                            else:
                                owner_id = store[1] if len(store) > 1 else None

                            if owner_id:
                                lang = "ru"
                                try:
                                    lang = db.get_user_language(owner_id)
                                except Exception:
                                    pass

                                booking_type = "savat broni" if is_cart else "bron"
                                if lang == "uz":
                                    text = (
                                        f"⏰ <b>Eslatma: {booking_type} kutmoqda!</b>\n\n"
                                        f"📋 Kod: {booking_code}\n"
                                        f"⏱ 30 daqiqadan ko'proq vaqt o'tdi.\n\n"
                                        f"Iltimos, bronni tasdiqlang yoki rad eting."
                                    )
                                else:
                                    booking_type = "бронь корзины" if is_cart else "бронь"
                                    text = (
                                        f"⏰ <b>Напоминание: {booking_type} ожидает подтверждения!</b>\n\n"
                                        f"📋 Код: {booking_code}\n"
                                        f"⏱ Прошло более 30 минут.\n\n"
                                        f"Пожалуйста, подтвердите или отклоните бронирование."
                                    )

                                # Send reminder
                                await bot.send_message(owner_id, text, parse_mode="HTML")
                                logger.info(
                                    f"Sent partner reminder for booking {booking_id} to owner {owner_id}"
                                )

                                # Mark as sent
                                try:
                                    cursor.execute(
                                        "UPDATE bookings SET partner_reminder_sent = 1 WHERE booking_id = %s",
                                        (booking_id,),
                                    )
                                    conn.commit()
                                except Exception as e:
                                    logger.error(
                                        f"Failed to mark partner reminder for {booking_id}: {e}"
                                    )

                    except Exception as e:
                        logger.error(
                            f"Failed to send partner reminder for booking {booking_id}: {e}"
                        )

                except Exception as e:
                    logger.error(f"Error processing partner reminder row: {e}")

    except Exception as e:
        logger.error(f"Partner reminder query failed: {e}")

    # 2) Expired bookings: cancel and return quantity (including cart bookings)
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT booking_id, user_id, offer_id, quantity, is_cart_booking
                FROM bookings
                WHERE status IN ('pending','active')
                  AND delivery_option = 0
                  AND expiry_time IS NOT NULL
                  AND expiry_time <= now()
            """
            )
            rows = cursor.fetchall()
            for row in rows:
                try:
                    if hasattr(row, "get"):
                        booking_id = row.get("booking_id")
                        user_id = row.get("user_id")
                        offer_id = row.get("offer_id")
                        quantity = int(row.get("quantity") or 0)
                        is_cart = int(row.get("is_cart_booking") or 0)
                    else:
                        booking_id = row[0]
                        user_id = row[1]
                        offer_id = row[2]
                        quantity = int(row[3] or 0)
                        is_cart = int(row[4] if len(row) > 4 else 0)

                    # Cancel booking in DB (cancel_booking already returns quantity atomically)
                    try:
                        db.cancel_booking(booking_id)
                        log_type = "cart booking" if is_cart else "booking"
                        logger.info(f"Auto-cancelled expired {log_type} {booking_id}")
                    except Exception as e:
                        logger.error(f"Failed to auto-cancel booking {booking_id}: {e}")

                    # Notify customer
                    try:
                        if bot and user_id:
                            lang = "ru"
                            try:
                                lang = db.get_user_language(user_id)
                            except Exception:
                                pass
                            if lang == "uz":
                                text = (
                                    "⏰ Bron vaqti tugadi va avtomatik bekor qilindi."
                                )
                            else:
                                text = (
                                    "⏰ Срок брони истёк и она была автоматически отменена."
                                )
                            await bot.send_message(user_id, text)
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Error processing expired booking row: {e}")
    except Exception as e:
        logger.error(f"Expired bookings query failed: {e}")

    # 3) Pending delivery orders auto-cancel after timeout
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT o.order_id, o.user_id, o.order_status, o.delivery_address, o.created_at
                FROM orders o
                WHERE o.order_status = 'pending'
                  AND o.order_type = 'delivery'
                  AND o.created_at < now() - (%s * INTERVAL '1 minute')
            """,
                (int(delivery_pending_expiry_minutes),),
            )
            rows = cursor.fetchall()
            for row in rows:
                try:
                    if hasattr(row, "get"):
                        order_id = row.get("order_id")
                        user_id = row.get("user_id")
                    else:
                        order_id = row[0]
                        user_id = row[1]

                    # Update order status
                    try:
                        if order_service:
                            await order_service.cancel_order(order_id, entity_type="order")
                        elif set_order_status_direct:
                            set_order_status_direct(db, order_id, order_status_cancelled)
                    except Exception as e:
                        logger.error(f"Failed to auto-cancel delivery order {order_id}: {e}")

                    # Notify user
                    try:
                        if bot and user_id:
                            lang = "ru"
                            try:
                                lang = db.get_user_language(user_id)
                            except Exception:
                                pass
                            if lang == "uz":
                                text = (
                                    "⏰ Buyurtma tasdiqlanmaganligi sababli avtomatik bekor qilindi."
                                )
                            else:
                                text = (
                                    "⏰ Заказ был автоматически отменён из-за отсутствия подтверждения."
                                )
                            await bot.send_message(user_id, text)
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Error processing delivery order row: {e}")
    except Exception as e:
        logger.error(f"Delivery orders query failed: {e}")

    # 4) Ready pickup bookings expire after configured hours
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT booking_id, user_id
                FROM bookings
                WHERE status = 'ready'
                  AND updated_at < now() - (%s * INTERVAL '1 hour')
            """,
                (int(ready_expiry_hours),),
            )
            rows = cursor.fetchall()
            for row in rows:
                try:
                    if hasattr(row, "get"):
                        booking_id = row.get("booking_id")
                        user_id = row.get("user_id")
                    else:
                        booking_id = row[0]
                        user_id = row[1]

                    # Update status to cancelled/expired
                    try:
                        if set_booking_status_direct:
                            set_booking_status_direct(db, booking_id, order_status_cancelled)
                    except Exception as e:
                        logger.error(f"Failed to expire ready booking {booking_id}: {e}")

                    # Notify user
                    try:
                        if bot and user_id:
                            lang = "ru"
                            try:
                                lang = db.get_user_language(user_id)
                            except Exception:
                                pass
                            if lang == "uz":
                                text = "⏰ Bron muddati tugadi va bekor qilindi."
                            else:
                                text = "⏰ Бронь истекла и была отменена."
                            await bot.send_message(user_id, text)
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Error processing ready booking row: {e}")
    except Exception as e:
        logger.error(f"Ready bookings query failed: {e}")

    # 4.5) Ready pickup orders expire after configured hours
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT order_id, user_id
                FROM orders
                WHERE order_type = 'pickup'
                  AND order_status = 'ready'
                  AND updated_at < now() - (%s * INTERVAL '1 hour')
            """,
                (int(ready_expiry_hours),),
            )
            rows = cursor.fetchall()
            for row in rows:
                try:
                    if hasattr(row, "get"):
                        order_id = row.get("order_id")
                        user_id = row.get("user_id")
                    else:
                        order_id = row[0]
                        user_id = row[1]

                    # Update status to cancelled and restore quantities
                    try:
                        if order_service:
                            await order_service.cancel_order(order_id, entity_type="order")
                        elif set_order_status_direct:
                            set_order_status_direct(db, order_id, order_status_cancelled)
                    except Exception as e:
                        logger.error(f"Failed to expire ready pickup order {order_id}: {e}")

                    # Notify user if unified order service is unavailable
                    if bot and user_id and not order_service:
                        try:
                            lang = "ru"
                            try:
                                lang = db.get_user_language(user_id)
                            except Exception:
                                pass
                            await bot.send_message(
                                user_id, get_text(lang, "pickup_ready_expired")
                            )
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(f"Error processing ready pickup order row: {e}")
    except Exception as e:
        logger.error(f"Ready pickup orders query failed: {e}")

    # 5) Pending pickup bookings expire after configured minutes
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT booking_id, user_id
                FROM bookings
                WHERE status = 'pending'
                  AND delivery_option = 0
                  AND created_at < now() - (%s * INTERVAL '1 minute')
            """,
                (int(pending_expiry_minutes),),
            )
            rows = cursor.fetchall()
            for row in rows:
                try:
                    if hasattr(row, "get"):
                        booking_id = row.get("booking_id")
                        user_id = row.get("user_id")
                    else:
                        booking_id = row[0]
                        user_id = row[1]

                    # Update status to cancelled/expired
                    try:
                        if set_booking_status_direct:
                            set_booking_status_direct(db, booking_id, order_status_cancelled)
                    except Exception as e:
                        logger.error(f"Failed to expire pending booking {booking_id}: {e}")

                    # Notify user
                    try:
                        if bot and user_id:
                            lang = "ru"
                            try:
                                lang = db.get_user_language(user_id)
                            except Exception:
                                pass
                            if lang == "uz":
                                text = "⏰ Bron muddati tugadi va bekor qilindi."
                            else:
                                text = "⏰ Бронь истекла и была отменена."
                            await bot.send_message(user_id, text)
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Error processing pending booking row: {e}")
    except Exception as e:
        logger.error(f"Pending bookings query failed: {e}")


async def start_booking_expiry_worker(db: Any, bot: Any) -> None:
    """Periodic worker that sends reminders and cancels expired bookings.

    - Sends a reminder 1 hour before expiry (sets `reminder_sent`)
    - Cancels expired bookings and returns reserved quantity to offers
    """
    check_interval = getattr(db, "BOOKING_EXPIRY_CHECK_MINUTES", 30)

    while True:
        try:
            await run_booking_expiry_cycle(db, bot)
        except Exception as e:
            logger.error(f"Booking expiry worker error: {e}")

        await asyncio.sleep(check_interval * 60)
