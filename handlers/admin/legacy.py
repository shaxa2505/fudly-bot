"""
Легаси админские обработчики (система модерации, команды, статистика)

Содержит:
- Статистика с экспортом CSV (admin_analytics)
- Модерация магазинов (pending/approve/reject)
- Просмотр магазинов и товаров
- Системные команды (migrate_db, enable_delivery)
"""

import csv
import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)
import os
import sqlite3
from datetime import datetime

router = Router(name="admin_legacy")

# Dependencies будут внедрены через setup
_bot = None
_db = None
_get_text = None
_moderation_keyboard = None
_get_uzb_time = None
_ADMIN_ID = None
_DATABASE_URL = None


def setup(bot, db, get_text, moderation_keyboard, get_uzb_time, admin_id, database_url):
    """Инициализация зависимостей"""
    global _bot, _db, _get_text, _moderation_keyboard, _get_uzb_time, _ADMIN_ID, _DATABASE_URL
    _bot = bot
    _db = db
    _get_text = get_text
    _moderation_keyboard = moderation_keyboard
    _get_uzb_time = get_uzb_time
    _ADMIN_ID = admin_id
    _DATABASE_URL = database_url


# ============== СТАТИСТИКА С CSV ==============


@router.message(F.text == "📈 Аналитика")
async def admin_analytics(message: types.Message):
    """
    Расширенная статистика с экспортом в CSV

    ВАЖНО: Очищена дублирующаяся логика сбора статистики
    """
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    try:
        # Собираем статистику один раз
        conn = _db.get_connection()
        cursor = conn.cursor()

        # 1. Общая статистика пользователей
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "seller"')
        total_sellers = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "customer"')
        total_customers = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE language = "ru"')
        ru_users = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE language = "uz"')
        uz_users = cursor.fetchone()[0]

        # 2. Статистика магазинов
        cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "active"')
        active_stores = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "pending"')
        pending_stores = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "rejected"')
        rejected_stores = cursor.fetchone()[0]

        # 3. Статистика товаров
        cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "active"')
        active_offers = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "expired"')
        expired_offers = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "sold_out"')
        sold_out_offers = cursor.fetchone()[0]

        # 4. Статистика бронирований
        cursor.execute("SELECT COUNT(*) FROM bookings")
        total_bookings = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "pending"')
        pending_bookings = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "confirmed"')
        confirmed_bookings = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "cancelled"')
        cancelled_bookings = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "completed"')
        completed_bookings = cursor.fetchone()[0]

        # 5. Топ-5 продавцов по активным товарам
        cursor.execute(
            """
            SELECT u.first_name, COUNT(o.offer_id) as offers_count
            FROM users u
            INNER JOIN stores s ON u.user_id = s.owner_id
            INNER JOIN offers o ON s.store_id = o.store_id
            WHERE o.status = "active"
            GROUP BY u.user_id
            ORDER BY offers_count DESC
            LIMIT 5
        """
        )
        top_sellers = cursor.fetchall()

        # 6. Самые популярные категории
        cursor.execute(
            """
            SELECT category, COUNT(*) as count
            FROM offers
            WHERE status = "active"
            GROUP BY category
            ORDER BY count DESC
            LIMIT 5
        """
        )
        top_categories = cursor.fetchall()

        # 7. Средний discount
        cursor.execute(
            """
            SELECT AVG(((original_price - discount_price) * 100.0 / original_price)) as avg_discount
            FROM offers
            WHERE status = "active" AND original_price > 0
        """
        )
        avg_discount_result = cursor.fetchone()
        avg_discount = (
            round(avg_discount_result[0], 1)
            if avg_discount_result and avg_discount_result[0]
            else 0
        )

        conn.close()

        # Формируем текстовый отчёт
        report = f"""📊 <b>РАСШИРЕННАЯ АНАЛИТИКА</b>

👥 <b>ПОЛЬЗОВАТЕЛИ</b>
├ Всего: {total_users}
├ Продавцы: {total_sellers}
├ Покупатели: {total_customers}
├ Русский язык: {ru_users}
└ Узбекский язык: {uz_users}

🏪 <b>МАГАЗИНЫ</b>
├ Активные: {active_stores}
├ На модерации: {pending_stores}
└ Отклонённые: {rejected_stores}

🔥 <b>ТОВАРЫ</b>
├ Активные: {active_offers}
├ Истекшие: {expired_offers}
└ Распроданные: {sold_out_offers}

📦 <b>БРОНИРОВАНИЯ</b>
├ Всего: {total_bookings}
├ Ожидают: {pending_bookings}
├ Подтверждены: {confirmed_bookings}
├ Отменены: {cancelled_bookings}
└ Завершены: {completed_bookings}

💰 <b>СРЕДНЯЯ СКИДКА:</b> {avg_discount}%

🏆 <b>ТОП-5 ПРОДАВЦОВ:</b>"""

        for i, (name, count) in enumerate(top_sellers, 1):
            report += f"\n{i}. {name} — {count} товаров"

        report += "\n\n📊 <b>ПОПУЛЯРНЫЕ КАТЕГОРИИ:</b>"

        category_names = {
            "bakery": "🍞 Хлеб",
            "dairy": "🥛 Молочка",
            "meat": "🥩 Мясо",
            "fruits": "🍎 Фрукты",
            "vegetables": "🥕 Овощи",
            "ready_food": "🍱 Готовая еда",
        }

        for i, (cat, count) in enumerate(top_categories, 1):
            cat_name = category_names.get(cat, cat)
            report += f"\n{i}. {cat_name} — {count} товаров"

        await message.answer(report, parse_mode="HTML")

        # Экспорт в CSV
        csv_filename = f"analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        with open(csv_filename, "w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.writer(csvfile)

            # Заголовки и данные
            writer.writerow(["РАЗДЕЛ", "ПОКАЗАТЕЛЬ", "ЗНАЧЕНИЕ"])
            writer.writerow(["Пользователи", "Всего", total_users])
            writer.writerow(["Пользователи", "Продавцы", total_sellers])
            writer.writerow(["Пользователи", "Покупатели", total_customers])
            writer.writerow(["Пользователи", "Русский язык", ru_users])
            writer.writerow(["Пользователи", "Узбекский язык", uz_users])
            writer.writerow([])
            writer.writerow(["Магазины", "Активные", active_stores])
            writer.writerow(["Магазины", "На модерации", pending_stores])
            writer.writerow(["Магазины", "Отклонённые", rejected_stores])
            writer.writerow([])
            writer.writerow(["Товары", "Активные", active_offers])
            writer.writerow(["Товары", "Истекшие", expired_offers])
            writer.writerow(["Товары", "Распроданные", sold_out_offers])
            writer.writerow([])
            writer.writerow(["Бронирования", "Всего", total_bookings])
            writer.writerow(["Бронирования", "Ожидают", pending_bookings])
            writer.writerow(["Бронирования", "Подтверждены", confirmed_bookings])
            writer.writerow(["Бронирования", "Отменены", cancelled_bookings])
            writer.writerow(["Бронирования", "Завершены", completed_bookings])
            writer.writerow([])
            writer.writerow(["Средняя скидка", "", f"{avg_discount}%"])
            writer.writerow([])
            writer.writerow(["ТОП-5 ПРОДАВЦОВ", "", ""])
            for i, (name, count) in enumerate(top_sellers, 1):
                writer.writerow([i, name, count])

        # Отправляем CSV файл
        csv_file = FSInputFile(csv_filename)
        await message.answer_document(csv_file, caption="📊 Полная аналитика в CSV формате")

        # Удаляем временный файл
        if os.path.exists(csv_filename):
            os.remove(csv_filename)

    except Exception as e:
        await message.answer(f"❌ Ошибка при формировании аналитики: {e}")


# ============== МОДЕРАЦИЯ МАГАЗИНОВ ==============


@router.message(F.text == "🏪 Заявки на партнерство")
async def admin_pending_stores(message: types.Message):
    """Показать заявки на модерацию магазинов"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    try:
        stores = _db.get_stores_by_status("pending")

        if not stores:
            await message.answer("✅ Новых заявок нет")
            return

        for store in stores:
            store_text = f"""
🏪 <b>{store['name']}</b>

📍 Город: {store['city']}
🏢 Адрес: {store['address']}
📋 Описание: {store['description']}
📂 Категория: {store['category']}
📞 Телефон: {store['phone']}
👤 Владелец ID: {store['owner_id']}
🏢 Тип: {store['business_type']}
"""

            await message.answer(
                store_text, reply_markup=_moderation_keyboard(store["store_id"]), parse_mode="HTML"
            )

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("approve_"))
async def approve_store(callback: types.CallbackQuery):
    """Одобрить магазин"""
    if callback.from_user.id != _ADMIN_ID:
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    try:
        # callback.data format: "approve_store_6" -> split by "_" -> take last element
        store_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
        await callback.answer("❌ Неверный запрос", show_alert=True)
        return

    try:
        # Обновляем статус магазина
        _db.update_store_status(store_id, "active")

        # Получаем данные о магазине
        store = _db.get_store(store_id)

        # Обновляем роль владельца на seller
        _db.update_user_role(store["owner_id"], "seller")

        # Отправляем уведомление владельцу
        lang = _db.get_user_language(store["owner_id"])

        notification = _get_text("store_approved", lang).format(store_name=store["name"])

        try:
            await _bot.send_message(store["owner_id"], notification)
        except Exception:
            pass

        await callback.message.edit_text(
            f"✅ Магазин '{store['name']}' одобрен!\n\n{callback.message.text}"
        )
        await callback.answer("✅ Магазин одобрен")

    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("reject_"))
async def reject_store(callback: types.CallbackQuery):
    """Отклонить заявку на магазин"""
    if callback.from_user.id != _ADMIN_ID:
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    try:
        # callback.data format: "reject_store_6" -> split by "_" -> take last element
        store_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
        await callback.answer("❌ Неверный запрос", show_alert=True)
        return

    try:
        # Обновляем статус
        _db.update_store_status(store_id, "rejected")

        # Получаем данные о магазине
        store = _db.get_store(store_id)

        # Уведомляем владельца
        lang = _db.get_user_language(store["owner_id"])
        notification = _get_text("store_rejected", lang).format(store_name=store["name"])

        try:
            await _bot.send_message(store["owner_id"], notification)
        except Exception:
            pass

        await callback.message.edit_text(
            f"❌ Магазин '{store['name']}' отклонён\n\n{callback.message.text}"
        )
        await callback.answer("✅ Заявка отклонена")

    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


# ============== ПРОСМОТР МАГАЗИНОВ И ТОВАРОВ ==============


@router.message(F.text == "📋 Все предложения")
async def admin_all_offers(message: types.Message):
    """Показать все активные предложения"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    try:
        offers = _db.get_all_offers()

        if not offers:
            await message.answer("📋 Нет активных предложений")
            return

        # Показываем первые 10
        for offer in offers[:10]:
            offer_text = f"""
🔥 <b>{offer.get('title', 'Без названия')}</b>

📦 ID: {offer.get('offer_id')}
🏪 Магазин ID: {offer.get('store_id')}
💵 Цена: <s>{offer.get('original_price', 0):,}</s> → <b>{offer.get('discount_price', 0):,} сум</b>
📦 Остаток: {offer.get('quantity', 0)} {offer.get('unit', 'шт')}
📅 Истекает: {offer.get('expiry_date', 'неизвестно')}
📊 Статус: {offer.get('status', 'unknown')}
"""
            await message.answer(offer_text, parse_mode="HTML")

        if len(offers) > 10:
            await message.answer(f"... и ещё {len(offers) - 10} предложений")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(F.text == "🏪 Все магазины")
async def admin_all_stores(message: types.Message):
    """Показать все магазины с возможностью удаления"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    try:
        stores = _db.get_all_stores()

        if not stores:
            await message.answer("🏪 Магазинов нет")
            return

        for store in stores:
            builder = InlineKeyboardBuilder()
            builder.button(
                text=f"🗑 Удалить {store['name'][:20]}",
                callback_data=f"delete_store_{store['store_id']}",
            )

            store_text = f"""
🏪 <b>{store['name']}</b>

📍 {store['city']}
📊 Статус: {store['status']}
👤 Владелец ID: {store['owner_id']}
📞 {store['phone']}
"""
            await message.answer(store_text, reply_markup=builder.as_markup(), parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("delete_store_"))
async def delete_store_callback(callback: types.CallbackQuery):
    """Удалить магазин"""
    if callback.from_user.id != _ADMIN_ID:
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return

    try:
        store_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
        await callback.answer("❌ Неверный запрос", show_alert=True)
        return

    try:
        store = _db.get_store(store_id)

        # Удаляем магазин
        _db.delete_store(store_id)

        await callback.message.edit_text(f"🗑 Магазин '{store['name']}' удалён")
        await callback.answer("✅ Магазин удалён")

    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


# ============== ПЛЕЙСХОЛДЕРЫ ==============


@router.message(F.text == "📢 Рассылка")
async def admin_broadcast(message: types.Message):
    """Рассылка (в разработке)"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    await message.answer("📢 Функция рассылки в разработке")


@router.message(F.text == "⚙️ Настройки")
async def admin_settings(message: types.Message):
    """Настройки админ-панели"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Платёжные реквизиты", callback_data="admin_payment_settings")
    kb.button(text="🔔 Уведомления", callback_data="admin_notifications_settings")
    kb.button(text="📊 Лимиты", callback_data="admin_limits_settings")
    kb.adjust(1)
    
    text = "⚙️ <b>Настройки платформы</b>\n\n"
    text += "Выберите раздел для настройки:"
    
    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


# ============== СИСТЕМНЫЕ КОМАНДЫ ==============


@router.message(Command("migrate_db"))
async def cmd_migrate_db(message: types.Message):
    """Миграция базы данных (только для SQLite)"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    try:
        if _DATABASE_URL:
            await message.answer("⚠️ Эта команда работает только с SQLite")
            return

        await message.answer("🔄 Начинаю миграцию БД...")

        conn = sqlite3.connect(_db.db_name)
        cursor = conn.cursor()

        # Добавляем поля доставки если их нет
        cursor.execute("PRAGMA table_info(stores)")
        columns = [col[1] for col in cursor.fetchall()]

        added = []
        if "delivery_enabled" not in columns:
            cursor.execute("ALTER TABLE stores ADD COLUMN delivery_enabled INTEGER DEFAULT 1")
            added.append("delivery_enabled")

        if "delivery_price" not in columns:
            cursor.execute("ALTER TABLE stores ADD COLUMN delivery_price INTEGER DEFAULT 15000")
            added.append("delivery_price")

        if "min_order_amount" not in columns:
            cursor.execute("ALTER TABLE stores ADD COLUMN min_order_amount INTEGER DEFAULT 30000")
            added.append("min_order_amount")

        conn.commit()

        if added:
            await message.answer(f"✅ Добавлены поля: {', '.join(added)}")
        else:
            await message.answer("✅ Все поля уже существуют")

        # Показываем список таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()

        tables_text = "\n".join([f"✅ {t[0]}" for t in tables])
        await message.answer(f"📊 Таблицы в БД:\n{tables_text}")

    except Exception as e:
        await message.answer(f"❌ Ошибка миграции: {e}")


@router.message(Command("enable_delivery"))
async def cmd_enable_delivery(message: types.Message):
    """Команда для включения доставки для всех магазинов (только для админа)"""
    if message.from_user.id != _ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return

    try:
        if _DATABASE_URL:
            await message.answer(
                "⚠️ Эта команда работает только с SQLite.\nДля PostgreSQL доставка работает автоматически."
            )
            return

        await message.answer("🔄 Включаю доставку для всех магазинов...")

        conn = sqlite3.connect(_db.db_name)
        cursor = conn.cursor()

        # Проверяем наличие таблицы stores и полей доставки
        cursor.execute("PRAGMA table_info(stores)")
        columns = [col[1] for col in cursor.fetchall()]

        if "delivery_enabled" not in columns:
            await message.answer("❌ Таблица stores не имеет полей доставки. Запустите /migrate_db")
            conn.close()
            return

        # Включаем доставку
        cursor.execute(
            """
            UPDATE stores
            SET delivery_enabled = 1,
                delivery_price = 15000,
                min_order_amount = 30000
            WHERE delivery_enabled = 0
        """
        )
        updated = cursor.rowcount
        conn.commit()

        # Проверяем результат
        cursor.execute("SELECT store_id, name, delivery_enabled FROM stores")
        stores = cursor.fetchall()
        conn.close()

        result = f"✅ Доставка включена для {updated} магазина(ов)\n\n"
        result += "📊 Статус магазинов:\n"
        for store in stores:
            # Dict-compatible access
            store_id = (
                store.get("store_id")
                if isinstance(store, dict)
                else (store[0] if len(store) > 0 else 0)
            )
            store_name = (
                store.get("name")
                if isinstance(store, dict)
                else (store[1] if len(store) > 1 else "Без названия")
            )
            delivery_enabled = (
                store.get("delivery_enabled")
                if isinstance(store, dict)
                else (store[2] if len(store) > 2 else False)
            )
            status = "✅" if delivery_enabled else "❌"
            result += f"{status} {store_name} (ID: {store_id})\n"

        await message.answer(result)

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
