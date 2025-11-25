"""
Admin Dashboard Handlers
Handles all admin panel callbacks and statistics
"""

import asyncio
import logging
from datetime import datetime

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)

# Router for admin dashboard
router = Router(name="admin_dashboard")


def setup(bot_instance, db_instance, get_text_func, moderation_keyboard_func, get_uzb_time_func):
    """Initialize module with bot and database instances"""
    global bot, db, get_text, moderation_keyboard, get_uzb_time
    bot = bot_instance
    db = db_instance
    get_text = get_text_func
    moderation_keyboard = moderation_keyboard_func
    get_uzb_time = get_uzb_time_func


@router.callback_query(F.data == "admin_refresh_dashboard")
async def refresh_dashboard(callback: types.CallbackQuery):
    """Обновить dashboard"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    # Используем тот же код что и в admin_dashboard
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # [Копируем весь код из admin_dashboard для получения статистики]
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "seller"')
        sellers = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "customer"')
        customers = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "active"')
        active_stores = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "pending"')
        pending_stores = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "active"')
    active_offers = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "inactive"')
    inactive_offers = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM bookings")
    total_bookings = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "pending"')
    pending_bookings = cursor.fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("SELECT COUNT(*) FROM bookings WHERE DATE(created_at) = ?", (today,))
    today_bookings = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT SUM(o.discount_price * b.quantity)
        FROM bookings b
        JOIN offers o ON b.offer_id = o.offer_id
        WHERE DATE(b.created_at) = ? AND b.status != 'cancelled'
    """,
        (today,),
    )
    today_revenue = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = ?", (today,))
    today_users = cursor.fetchone()[0]

    text = "📊 <b>Dashboard - Общая статистика</b>\n\n"
    text += "👥 <b>Пользователи:</b>\n"
    text += f"├ Всего: {total_users} (+{today_users} сегодня)\n"
    text += f"├ 🏪 Партнёры: {sellers}\n"
    text += f"└ 🛍 Покупатели: {customers}\n\n"
    text += "🏪 <b>Магазины:</b>\n"
    text += f"├ ✅ Активные: {active_stores}\n"
    text += f"└ ⏳ На модерации: {pending_stores}\n\n"
    text += "📦 <b>Товары:</b>\n"
    text += f"├ ✅ Активные: {active_offers}\n"
    text += f"└ ❌ Неактивные: {inactive_offers}\n\n"
    text += "🎫 <b>Бронирования:</b>\n"
    text += f"├ Всего: {total_bookings}\n"
    text += f"├ ⏳ Активные: {pending_bookings}\n"
    text += f"└ 📅 Сегодня: {today_bookings}\n\n"
    text += f"💰 <b>Выручка сегодня:</b> {int(today_revenue):,} сум"

    kb = InlineKeyboardBuilder()
    if pending_stores > 0:
        kb.button(text=f"⏳ Модерация ({pending_stores})", callback_data="admin_moderation")
    kb.button(text="📊 Детальная статистика", callback_data="admin_detailed_stats")
    kb.button(text="🔄 Обновить", callback_data="admin_refresh_dashboard")
    kb.adjust(1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    await callback.answer("✅ Обновлено")


@router.callback_query(F.data == "admin_moderation")
async def admin_moderation_callback(callback: types.CallbackQuery):
    """Показать заявки на модерацию"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer()

    lang = "ru"
    pending = db.get_pending_stores()

    if not pending:
        await bot.send_message(callback.message.chat.id, get_text(lang, "no_pending_stores"))
        return

    await bot.send_message(
        callback.message.chat.id, get_text(lang, "pending_stores_count", count=len(pending))
    )

    for store in pending:
        # PostgreSQL returns dicts, SQLite returns tuples
        # Support both formats for compatibility
        if isinstance(store, dict):
            store_id = store["store_id"]
            name = store["name"]
            city = store["city"]
            address = store.get("address") or "не указан"
            description = store.get("description") or "нет описания"
            category = store.get("category", "Ресторан")
            phone = store.get("phone") or "не указан"
            created_at = store.get("created_at", "")
            first_name = store.get("first_name", "Неизвестно")
            username = store.get("username")
        else:
            # PostgreSQL also returns dict format now, so this branch is just for safety
            store_id = store[0] if isinstance(store, (list, tuple)) and len(store) > 0 else 0
            name = (
                store[2] if isinstance(store, (list, tuple)) and len(store) > 2 else "Без названия"
            )
            city = store[3] if isinstance(store, (list, tuple)) and len(store) > 3 else ""
            address = (
                store[4] if isinstance(store, (list, tuple)) and len(store) > 4 else ""
            ) or "не указан"
            description = (
                store[5] if isinstance(store, (list, tuple)) and len(store) > 5 else ""
            ) or "нет описания"
            category = (
                store[6] if isinstance(store, (list, tuple)) and len(store) > 6 else "Ресторан"
            )
            phone = (
                store[7] if isinstance(store, (list, tuple)) and len(store) > 7 else ""
            ) or "не указан"
            created_at = store[10] if isinstance(store, (list, tuple)) and len(store) > 10 else ""
            first_name = (
                store[15] if isinstance(store, (list, tuple)) and len(store) > 15 else "Неизвестно"
            )
            username = store[16] if isinstance(store, (list, tuple)) and len(store) > 16 else None

        text = f"🏪 <b>{name}</b>\n\n"
        text += f"От: {first_name} (@{username or 'нет'})\n"
        text += f"ID: <code>{store_id}</code>\n\n"
        text += f"📍 {city}, {address}\n"
        text += f"🏷 {category}\n"
        text += f"📱 {phone}\n"
        text += f"📝 {description}\n"
        text += f"📅 {created_at}"

        await bot.send_message(
            callback.message.chat.id,
            text,
            parse_mode="HTML",
            reply_markup=moderation_keyboard(store_id),
        )
        await asyncio.sleep(0.3)


@router.callback_query(F.data == "admin_detailed_stats")
async def admin_detailed_stats_callback(callback: types.CallbackQuery):
    """Детальная статистика из Dashboard"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer()

    await bot.send_message(callback.message.chat.id, "⏳ Собираю статистику...")

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Статистика по пользователям
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "seller"')
        sellers = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "customer"')
        customers = cursor.fetchone()[0]

        # Статистика по магазинам
        cursor.execute("SELECT COUNT(*) FROM stores")
        total_stores = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "active"')
        approved_stores = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "pending"')
        pending_stores = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "rejected"')
        rejected_stores = cursor.fetchone()[0]

        # Статистика по городам
        cursor.execute(
            "SELECT city, COUNT(*) FROM stores GROUP BY city ORDER BY COUNT(*) DESC LIMIT 5"
        )
        top_cities = cursor.fetchall()

        # Статистика по категориям
        cursor.execute(
            "SELECT category, COUNT(*) FROM stores GROUP BY category ORDER BY COUNT(*) DESC LIMIT 5"
        )
        top_categories = cursor.fetchall()

        # Статистика по предложениям
        cursor.execute("SELECT COUNT(*) FROM offers")
        total_offers = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "active"')
        active_offers = cursor.fetchone()[0]
        cursor.execute('SELECT SUM(original_price) FROM offers WHERE status = "active"')
        total_original_price = cursor.fetchone()[0] or 0
        cursor.execute('SELECT SUM(discount_price) FROM offers WHERE status = "active"')
        total_discounted_price = cursor.fetchone()[0] or 0

        # Статистика по бронированиям
        cursor.execute("SELECT COUNT(*) FROM bookings")
        total_bookings = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "active"')
        active_bookings = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "completed"')
        completed_bookings = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "cancelled"')
        cancelled_bookings = cursor.fetchone()[0]
        cursor.execute('SELECT SUM(quantity) FROM bookings WHERE status IN ("active", "completed")')
        total_quantity = cursor.fetchone()[0] or 0

        # Доход (экономия покупателей)
        cursor.execute(
            """
            SELECT SUM((o.original_price - o.discount_price) * b.quantity)
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            WHERE b.status IN ("active", "completed")
        """
        )
        total_savings = cursor.fetchone()[0] or 0

        # Самые активные магазины
        cursor.execute(
            """
            SELECT s.name, COUNT(b.booking_id) as bookings_count
            FROM stores s
            LEFT JOIN offers o ON s.store_id = o.store_id
            LEFT JOIN bookings b ON o.offer_id = b.offer_id
            WHERE b.status IN ("active", "completed")
            GROUP BY s.store_id
            ORDER BY bookings_count DESC
            LIMIT 5
        """
        )
        top_stores = cursor.fetchall()

    # Формируем текст
    text = "📈 <b>ДЕТАЛЬНАЯ АНАЛИТИКА</b>\n\n"

    text += "👥 <b>ПОЛЬЗОВАТЕЛИ:</b>\n"
    text += f"├ Всего: {total_users}\n"
    text += f"├ Партнёры: {sellers}\n"
    text += f"└ Покупатели: {customers}\n\n"

    text += "🏪 <b>МАГАЗИНЫ:</b>\n"
    text += f"├ Всего: {total_stores}\n"
    text += f"├ ✅ Активные: {approved_stores}\n"
    text += f"├ ⏳ На модерации: {pending_stores}\n"
    text += f"└ ❌ Отклонённые: {rejected_stores}\n\n"

    if top_cities:
        text += "📍 <b>ТОП ГОРОДА:</b>\n"
        for city, count in top_cities:
            text += f"├ {city}: {count}\n"
        text += "\n"

    if top_categories:
        text += "🏷 <b>ТОП КАТЕГОРИИ:</b>\n"
        for cat, count in top_categories:
            text += f"├ {cat}: {count}\n"
        text += "\n"

    text += "📦 <b>ПРЕДЛОЖЕНИЯ:</b>\n"
    text += f"├ Всего: {total_offers}\n"
    text += f"├ Активные: {active_offers}\n"
    text += f"├ Общая стоимость: {int(total_original_price):,} сум\n"
    text += f"└ Со скидкой: {int(total_discounted_price):,} сум\n\n"

    text += "📋 <b>БРОНИРОВАНИЯ:</b>\n"
    text += f"├ Всего: {total_bookings}\n"
    text += f"├ ⏳ Активные: {active_bookings}\n"
    text += f"├ ✅ Завершённые: {completed_bookings}\n"
    text += f"├ ❌ Отменённые: {cancelled_bookings}\n"
    text += f"└ Забронировано товаров: {total_quantity} шт\n\n"

    text += f"💰 <b>ЭКОНОМИЯ ПОКУПАТЕЛЕЙ:</b> {int(total_savings):,} сум\n\n"

    if top_stores:
        text += "🏆 <b>ТОП МАГАЗИНЫ:</b>\n"
        for store_name, count in top_stores:
            text += f"├ {store_name}: {count} бронирований\n"

    await bot.send_message(callback.message.chat.id, text, parse_mode="HTML")


@router.callback_query(F.data == "admin_list_sellers")
async def admin_list_sellers_callback(callback: types.CallbackQuery):
    """Полный список продавцов с детальной информацией"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Получаем всех продавцов с дополнительной информацией
        cursor.execute(
            """
            SELECT u.user_id, u.username, u.first_name, u.city, u.created_at,
                   COUNT(DISTINCT s.store_id) as stores_count,
                   COUNT(DISTINCT CASE WHEN s.status = 'active' THEN s.store_id END) as active_stores,
                   COUNT(DISTINCT o.offer_id) as offers_count
            FROM users u
            LEFT JOIN stores s ON u.user_id = s.owner_id
            LEFT JOIN offers o ON s.store_id = o.store_id AND o.status = 'active'
            WHERE u.role = 'seller'
            GROUP BY u.user_id
            ORDER BY active_stores DESC, offers_count DESC
        """
        )
        sellers = cursor.fetchall()

    if not sellers:
        await bot.send_message(callback.message.chat.id, "👥 Продавцов нет")
        return

    text = f"👥 <b>Список партнёров ({len(sellers)}):</b>\n\n"

    kb = InlineKeyboardBuilder()

    for (
        user_id,
        username,
        first_name,
        city,
        created_at,
        stores_count,
        active_stores,
        offers_count,
    ) in sellers[:20]:
        text += f"👤 <b>{first_name or 'Без имени'}</b>"
        if username:
            text += f" (@{username})"
        text += "\n"
        text += f"├ 📍 {city or 'Не указан'}\n"
        text += f"├ 🏪 Магазинов: {active_stores}/{stores_count}\n"
        text += f"├ 📦 Активных товаров: {offers_count}\n"
        text += f"└ ID: <code>{user_id}</code>\n"

        # Кнопка удаления магазинов партнёра
        if stores_count > 0:
            kb.button(
                text=f"🗑 Удалить магазины {first_name or user_id}",
                callback_data=f"admin_delete_user_stores_{user_id}",
            )
        text += "\n"

    kb.adjust(1)

    if len(sellers) > 20:
        text += f"\n<i>Показано 20 из {len(sellers)}. Используйте поиск для остальных.</i>"

    await bot.send_message(
        callback.message.chat.id,
        text,
        parse_mode="HTML",
        reply_markup=kb.as_markup() if kb.export() else None,
    )


@router.callback_query(F.data.startswith("admin_delete_user_stores_"))
async def admin_delete_user_stores_callback(callback: types.CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid user_id in callback data: {callback.data}, error: {e}")
        await callback.answer("❌ Неверный запрос", show_alert=True)
        return

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Получаем информацию о пользователе
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()

        if not user_info:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        first_name, username = user_info

        # Получаем список магазинов
        cursor.execute("SELECT store_id, name, status FROM stores WHERE owner_id = %s", (user_id,))
        stores = cursor.fetchall()

    if not stores:
        await callback.answer("❌ У пользователя нет магазинов", show_alert=True)
        return

    # Подтверждение удаления
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить все", callback_data=f"admin_confirm_delete_stores_{user_id}")
    kb.button(text="❌ Отмена", callback_data="admin_cancel_action")
    kb.adjust(1)

    text = "⚠️ <b>Подтверждение удаления</b>\n\n"
    text += f"Пользователь: {first_name or 'Без имени'}"
    if username:
        text += f" (@{username})"
    text += f"\n\nМагазины ({len(stores)}):\n"

    for store_id, name, status in stores:
        status_emoji = "✅" if status == "active" else "⏳" if status == "pending" else "❌"
        text += f"{status_emoji} {name}\n"

    text += "\n<b>Вы уверены, что хотите удалить все магазины этого пользователя?</b>"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_delete_stores_"))
async def admin_confirm_delete_stores_callback(callback: types.CallbackQuery):
    """Подтверждение удаления магазинов"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    try:
        user_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid user_id in callback data: {callback.data}, error: {e}")
        await callback.answer("❌ Неверный запрос", show_alert=True)
        return

    conn = db.get_connection()
    cursor = conn.cursor()

    # Получаем магазины
    cursor.execute("SELECT store_id FROM stores WHERE owner_id = %s", (user_id,))
    stores = cursor.fetchall()

    if not stores:
        await callback.answer("❌ Магазины не найдены", show_alert=True)
        conn.close()
        return

    # Удаляем все товары магазинов
    for (store_id,) in stores:
        cursor.execute('UPDATE offers SET status = "deleted" WHERE store_id = %s', (store_id,))

    # Удаляем магазины (меняем статус на rejected)
    cursor.execute('UPDATE stores SET status = "rejected" WHERE owner_id = %s', (user_id,))

    # Меняем роль пользователя на customer
    cursor.execute('UPDATE users SET role = "customer" WHERE user_id = %s', (user_id,))

    conn.commit()
    conn.close()

    await callback.message.edit_text(
        f"✅ <b>Успешно удалено</b>\n\n"
        f"Удалено магазинов: {len(stores)}\n"
        f"Все товары этих магазинов деактивированы\n"
        f"Пользователь переведён в роль покупателя",
        parse_mode="HTML",
    )
    await callback.answer("✅ Магазины удалены")


@router.callback_query(F.data == "admin_cancel_action")
async def admin_cancel_action_callback(callback: types.CallbackQuery):
    """Отмена действия"""
    await callback.message.delete()
    await callback.answer("Действие отменено")


@router.callback_query(F.data == "admin_search_user")
async def admin_search_user_callback(callback: types.CallbackQuery):
    """Поиск пользователя"""
    await callback.answer("🔍 Отправьте ID или username пользователя для поиска", show_alert=True)


@router.callback_query(F.data == "admin_approved_stores")
async def admin_approved_stores_callback(callback: types.CallbackQuery):
    """Полный список одобренных магазинов"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT s.store_id, s.name, s.city, s.category, u.first_name, u.username,
                   s.created_at, COUNT(o.offer_id) as offers_count
            FROM stores s
            JOIN users u ON s.owner_id = u.user_id
            LEFT JOIN offers o ON s.store_id = o.store_id AND o.status = 'active'
            WHERE s.status = 'active'
            GROUP BY s.store_id
            ORDER BY s.created_at DESC
        """
        )
        stores = cursor.fetchall()

    if not stores:
        await bot.send_message(callback.message.chat.id, "🏪 Одобренных магазинов нет")
        return

    text = f"🏪 <b>Одобренные магазины ({len(stores)}):</b>\n\n"

    kb = InlineKeyboardBuilder()

    for store_id, name, city, category, owner_name, username, created_at, offers_count in stores[
        :15
    ]:
        text += f"🏪 <b>{name}</b>\n"
        text += f"├ 📍 {city} | 🏷 {category}\n"
        text += f"├ 👤 {owner_name}"
        if username:
            text += f" (@{username})"
        text += f"\n├ 📦 Товаров: {offers_count}\n"
        text += f"└ ID: <code>{store_id}</code>\n"

        # Добавляем кнопку блокировки магазина
        kb.button(
            text=f"🚫 Заблокировать {name[:15]}", callback_data=f"admin_block_store_{store_id}"
        )
        text += "\n"

    kb.adjust(1)

    if len(stores) > 15:
        text += f"\n<i>Показано 15 из {len(stores)}</i>"

    await bot.send_message(
        callback.message.chat.id,
        text,
        parse_mode="HTML",
        reply_markup=kb.as_markup() if kb.export() else None,
    )


@router.callback_query(F.data.startswith("admin_block_store_"))
async def admin_block_store_callback(callback: types.CallbackQuery):
    """Блокировка магазина"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    try:
        store_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
        await callback.answer("❌ Неверный запрос", show_alert=True)
        return

    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM stores WHERE store_id = %s", (store_id,))
        store = cursor.fetchone()

        if not store:
            await callback.answer("❌ Магазин не найден", show_alert=True)
            return

        # Блокируем магазин
        cursor.execute('UPDATE stores SET status = "rejected" WHERE store_id = %s', (store_id,))

        # Деактивируем все товары
        cursor.execute('UPDATE offers SET status = "inactive" WHERE store_id = %s', (store_id,))

    await callback.message.edit_text(
        f"🚫 <b>Магазин заблокирован</b>\n\n"
        f"Название: {store[0]}\n"
        f"ID: {store_id}\n\n"
        f"Все товары этого магазина деактивированы.",
        parse_mode="HTML",
    )
    await callback.answer("✅ Магазин заблокирован")


@router.callback_query(F.data == "admin_rejected_stores")
async def admin_rejected_stores_callback(callback: types.CallbackQuery):
    """Отклонённые магазины"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT s.store_id, s.name, s.city, u.first_name, u.username, s.created_at
            FROM stores s
            JOIN users u ON s.owner_id = u.user_id
            WHERE s.status = 'rejected'
            ORDER BY s.created_at DESC
            LIMIT 10
        """
        )
        stores = cursor.fetchall()

    if not stores:
        await bot.send_message(callback.message.chat.id, "🏪 Отклонённых магазинов нет")
        return

    text = f"❌ <b>Отклонённые магазины ({len(stores)}):</b>\n\n"

    for store_id, name, city, owner_name, username, created_at in stores:
        text += f"🏪 {name}\n"
        text += f"├ 📍 {city}\n"
        text += f"├ 👤 {owner_name}"
        if username:
            text += f" (@{username})"
        text += f"\n└ ID: <code>{store_id}</code>\n\n"

    await bot.send_message(callback.message.chat.id, text, parse_mode="HTML")


@router.callback_query(F.data == "admin_search_store")
async def admin_search_store_callback(callback: types.CallbackQuery):
    """Поиск магазина"""
    await callback.answer("🔍 Функция поиска будет добавлена позже", show_alert=True)


@router.callback_query(F.data == "admin_all_offers")
async def admin_all_offers_callback(callback: types.CallbackQuery):
    """Детальный список всех товаров"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT o.offer_id, o.title, o.original_price, o.discount_price, o.quantity,
                   s.name as store_name, o.status, o.created_at
            FROM offers o
            JOIN stores s ON o.store_id = s.store_id
            ORDER BY o.created_at DESC
            LIMIT 20
        """
        )
        offers = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) FROM offers")
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "active"')
        active = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "deleted"')
        deleted = cursor.fetchone()[0]

    text = "📦 <b>Все товары</b>\n\n"
    text += "📊 Статистика:\n"
    text += f"├ Всего: {total}\n"
    text += f"├ ✅ Активных: {active}\n"
    text += f"└ 🗑 Удалённых: {deleted}\n\n"

    if offers:
        text += "<b>Последние товары:</b>\n\n"
        for offer_id, title, orig, disc, qty, store, status, created in offers[:10]:
            status_emoji = "✅" if status == "active" else "❌"
            text += f"{status_emoji} <b>{title}</b>\n"
            text += f"├ 🏪 {store}\n"
            text += f"├ 💰 {int(orig):,} → {int(disc):,} сум\n"
            text += f"├ 📦 Остаток: {qty}\n"
            text += f"└ ID: <code>{offer_id}</code>\n\n"

        if len(offers) > 10:
            text += f"<i>Показано 10 из {len(offers)}</i>"

    await bot.send_message(callback.message.chat.id, text, parse_mode="HTML")


@router.callback_query(F.data == "admin_cleanup_offers")
async def admin_cleanup_offers_callback(callback: types.CallbackQuery):
    """Очистка истекших и удалённых товаров"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Подсчёт истекших товаров
        today = get_uzb_time().strftime("%Y-%m-%d")
        cursor.execute(
            'SELECT COUNT(*) FROM offers WHERE expiry_date < ? AND status = "active"', (today,)
        )
        expired = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "deleted"')
        deleted = cursor.fetchone()[0]

    text = "🗑 <b>Очистка товаров</b>\n\n"
    text += "📊 Найдено:\n"
    text += f"├ ⏰ Истекших: {expired}\n"
    text += f"└ 🗑 Удалённых: {deleted}\n\n"

    if expired + deleted > 0:
        text += "<i>Функция автоочистки будет добавлена в следующем обновлении</i>"
    else:
        text += "✅ Все товары актуальны!"

    await bot.send_message(callback.message.chat.id, text, parse_mode="HTML")


@router.callback_query(F.data == "admin_pending_bookings")
async def admin_pending_bookings_callback(callback: types.CallbackQuery):
    """Детальный список активных бронирований"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT b.booking_id, o.title, b.quantity, u.first_name, s.name,
                   b.created_at, (o.original_price - o.discount_price) * b.quantity as savings
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            JOIN users u ON b.user_id = u.user_id
            JOIN stores s ON o.store_id = s.store_id
            WHERE b.status = 'active'
            ORDER BY b.created_at DESC
            LIMIT 15
        """
        )
        bookings = cursor.fetchall()

        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "active"')
        total = cursor.fetchone()[0]

        cursor.execute('SELECT SUM(quantity) FROM bookings WHERE status = "active"')
        total_qty = cursor.fetchone()[0] or 0

    text = "📋 <b>Активные бронирования</b>\n\n"
    text += f"📊 Всего: {total} ({total_qty} шт.)\n\n"

    if bookings:
        for booking_id, title, qty, customer, store, created, savings in bookings[:10]:
            text += f"🎫 <b>{title}</b> ({qty} шт.)\n"
            text += f"├ 👤 {customer}\n"
            text += f"├ 🏪 {store}\n"
            text += f"├ 💰 Экономия: {int(savings):,} сум\n"
            text += f"└ ID: <code>{booking_id}</code>\n\n"

        if len(bookings) > 10:
            text += f"<i>Показано 10 из {len(bookings)}</i>"
    else:
        text += "📭 Активных бронирований нет"

    await bot.send_message(callback.message.chat.id, text, parse_mode="HTML")


@router.callback_query(F.data == "admin_completed_bookings")
async def admin_completed_bookings_callback(callback: types.CallbackQuery):
    """Завершённые бронирования"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT b.booking_id, o.title, b.quantity, u.first_name, s.name,
                   b.created_at, (o.original_price - o.discount_price) * b.quantity as savings
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            JOIN users u ON b.user_id = u.user_id
            JOIN stores s ON o.store_id = s.store_id
            WHERE b.status = 'completed'
            ORDER BY b.created_at DESC
            LIMIT 10
        """
        )
        bookings = cursor.fetchall()

        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "completed"')
        total = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT SUM((o.original_price - o.discount_price) * b.quantity)
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            WHERE b.status = 'completed'
        """
        )
        total_savings = cursor.fetchone()[0] or 0

    text = "✅ <b>Завершённые бронирования</b>\n\n"
    text += f"📊 Всего: {total}\n"
    text += f"💰 Общая экономия: {int(total_savings):,} сум\n\n"

    if bookings:
        for booking_id, title, qty, customer, store, created, savings in bookings[:8]:
            text += f"✅ {title} ({qty} шт.)\n"
            text += f"├ {customer} | {store}\n"
            text += f"└ 💰 {int(savings):,} сум\n\n"

        if len(bookings) > 8:
            text += f"<i>Показано 8 из {len(bookings)}</i>"
    else:
        text += "📭 Завершённых бронирований нет"

    await bot.send_message(callback.message.chat.id, text, parse_mode="HTML")


@router.callback_query(F.data == "admin_bookings_stats")
async def admin_bookings_stats_callback(callback: types.CallbackQuery):
    """Детальная статистика бронирований"""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Общая статистика
        cursor.execute("SELECT COUNT(*) FROM bookings")
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "active"')
        active = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "completed"')
        completed = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "cancelled"')
        cancelled = cursor.fetchone()[0]

        # Экономия
        cursor.execute(
            """
            SELECT SUM((o.original_price - o.discount_price) * b.quantity)
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            WHERE b.status IN ('active', 'completed')
        """
        )
        total_savings = cursor.fetchone()[0] or 0

        # Топ магазинов по бронированиям
        cursor.execute(
            """
            SELECT s.name, COUNT(b.booking_id) as cnt
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            JOIN stores s ON o.store_id = s.store_id
            WHERE b.status IN ('active', 'completed')
            GROUP BY s.store_id
            ORDER BY cnt DESC
            LIMIT 5
        """
        )
        top_stores = cursor.fetchall()

        # Топ покупателей
        cursor.execute(
            """
            SELECT u.first_name, COUNT(b.booking_id) as cnt
            FROM bookings b
            JOIN users u ON b.user_id = u.user_id
            GROUP BY u.user_id
            ORDER BY cnt DESC
            LIMIT 5
        """
        )
        top_customers = cursor.fetchall()

    text = "📋 <b>Статистика бронирований</b>\n\n"
    text += "📊 <b>Общее:</b>\n"
    text += f"├ Всего: {total}\n"
    text += f"├ ⏳ Активных: {active}\n"
    text += f"├ ✅ Завершённых: {completed}\n"
    text += f"└ ❌ Отменённых: {cancelled}\n\n"

    text += f"💰 <b>Экономия покупателей:</b> {int(total_savings):,} сум\n\n"

    if top_stores:
        text += "🏆 <b>Топ магазины:</b>\n"
        for name, cnt in top_stores:
            text += f"├ {name}: {cnt}\n"
        text += "\n"

    if top_customers:
        text += "👥 <b>Топ покупатели:</b>\n"
        for name, cnt in top_customers:
            text += f"├ {name or 'Без имени'}: {cnt}\n"

    await bot.send_message(callback.message.chat.id, text, parse_mode="HTML")


@router.callback_query(F.data == "admin_payment_settings")
async def admin_payment_settings(callback: types.CallbackQuery):
    """Show platform payment settings."""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    payment_card = db.get_platform_payment_card()
    
    text = "💳 <b>Платёжные реквизиты платформы</b>\n\n"
    
    if payment_card:
        if isinstance(payment_card, dict):
            card_number = payment_card.get("card_number", "Не указан")
            card_holder = payment_card.get("card_holder", "Не указан")
        else:
            card_number = str(payment_card)
            card_holder = "FUDLY PLATFORM"
        text += f"💳 Карта: <code>{card_number}</code>\n"
        text += f"👤 Владелец: {card_holder}\n"
    else:
        text += "❌ <b>Карта не настроена!</b>\n"
        text += "\nДля настройки добавьте запись в базу:\n"
        text += "<code>INSERT INTO platform_settings (key, value) VALUES ('payment_card', 'НОМЕР_КАРТЫ');</code>\n"
        text += "<code>INSERT INTO platform_settings (key, value) VALUES ('payment_card_holder', 'ИМЯ_ВЛАДЕЛЬЦА');</code>\n"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад", callback_data="admin_back_to_main")
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()
