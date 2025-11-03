"""
Background tasks module - автоматические задачи
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

def start_background_tasks(db):
    """Запуск фоновых задач
    
    Args:
        db: Database instance
    """
    # Фоновые задачи будут запускаться через asyncio
    # Задачи: автоматические напоминания, уведомления о новых предложениях, очистка
    
    try:
        from bot import bot
        from core.services.notification_service import NotificationService
        
        notification_service = NotificationService(bot, db)
        
        # Запускаем фоновые задачи
        asyncio.create_task(reminders_task(db, notification_service))
        asyncio.create_task(new_offers_notifications_task(db, notification_service))
        asyncio.create_task(cleanup_expired_offers_task(db))
        
        print("✅ Background tasks started")
    except Exception as e:
        print(f"⚠️ Background tasks error: {e}")

async def reminders_task(db, notification_service):
    """Оптимизированная задача отправки напоминаний о бронированиях"""
    while True:
        try:
            await asyncio.sleep(300)  # Проверка каждые 5 минут
            
            # Оптимизированный запрос с использованием индексов
            conn = db.get_connection()
            cursor = conn.cursor()
            
            # Используем индекс idx_bookings_user_status для быстрого поиска
            # Бронирования, которые нужно напомнить (за 2 часа до времени получения)
            cursor.execute('''
                SELECT b.booking_id, b.user_id, o.available_until, b.booking_code
                FROM bookings b
                INNER JOIN offers o ON b.offer_id = o.offer_id
                INNER JOIN users u ON b.user_id = u.user_id
                WHERE b.status = 'pending' 
                AND u.notifications_enabled = 1
                AND o.available_until IS NOT NULL
                AND o.available_until != ''
                AND datetime(o.available_until) BETWEEN datetime('now', '+1 hour') AND datetime('now', '+3 hours')
            ''')
            bookings = cursor.fetchall()
            conn.close()
            
            now = datetime.now()
            for booking in bookings:
                try:
                    available_until_str = booking[9] if len(booking) > 9 else None
                    if not available_until_str:
                        continue
                    
                    # Парсим время получения
                    try:
                        pickup_time = datetime.strptime(available_until_str, '%Y-%m-%d %H:%M')
                    except:
                        continue
                    
                    # Напоминание за 2 часа
                    reminder_time = pickup_time - timedelta(hours=2)
                    
                    # Если время напоминания прошло, но еще не отправлено
                    if reminder_time <= now < pickup_time:
                        user_id = booking[10] if len(booking) > 10 else None
                        booking_id = booking[0]
                        
                        if user_id:
                            try:
                                await notification_service.notify_new_booking(
                                    user_id,
                                    {
                                        'booking_id': booking_id,
                                        'pickup_time': available_until_str,
                                        'reminder': True
                                    },
                                    'ru'
                                )
                            except Exception:
                                pass
                except Exception:
                    continue
                    
        except Exception as e:
            import logging
            logging.error(f"Error in reminders task: {e}")
        await asyncio.sleep(300)

async def new_offers_notifications_task(db, notification_service):
    """Задача уведомлений о новых предложениях"""
    while True:
        try:
            await asyncio.sleep(600)  # Проверка каждые 10 минут
            
            # Получаем пользователей с включенными уведомлениями
            users = db.get_all_users()
            
            for user_tuple in users:
                try:
                    user_id = user_tuple[0]
                    user_city = user_tuple[4] if len(user_tuple) > 4 else None
                    
                    if not user_city:
                        continue
                    
                    # Оптимизированный запрос новых предложений с использованием индексов
                    conn = db.get_connection()
                    cursor = conn.cursor()
                    # Использует индексы idx_offers_created и idx_stores_city_status
                    cursor.execute('''
                        SELECT o.offer_id, o.title, o.discount_price, s.name as store_name
                        FROM offers o
                        INNER JOIN stores s ON o.store_id = s.store_id
                        WHERE o.status = 'active' 
                        AND s.city = ?
                        AND s.status = 'active'
                        AND o.created_at > datetime('now', '-10 minutes')
                        ORDER BY o.created_at DESC
                        LIMIT 5
                    ''', (user_city,))
                    new_offers = cursor.fetchall()
                    conn.close()
                    
                    if new_offers:
                        try:
                            text = f"🔔 <b>Новые предложения в {user_city}!</b>\n\n"
                            for offer_tuple in new_offers[:3]:
                                try:
                                    offer = Offer.from_tuple(offer_tuple)
                                    text += f"🍽 {offer.title}\n"
                                    text += f"💰 {int(offer.discount_price):,} сум\n\n"
                                except:
                                    continue
                            
                            text += "👉 Нажмите 'Доступные предложения' для просмотра"
                            
                            await notification_service._send_notification(user_id, text)
                        except Exception:
                            pass
                except Exception:
                    continue
                    
        except Exception as e:
            import logging
            logging.error(f"Error in new offers notifications task: {e}")
        await asyncio.sleep(600)

async def cleanup_expired_offers_task(db):
    """Задача очистки истёкших предложений"""
    while True:
        try:
            await asyncio.sleep(3600)  # Проверка каждый час
            db.delete_expired_offers()
        except Exception as e:
            import logging
            logging.error(f"Error in cleanup task: {e}")
        await asyncio.sleep(3600)

try:
    from models import Offer
except ImportError:
    pass

