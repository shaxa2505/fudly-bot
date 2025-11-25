"""
Admin panel handlers - main admin interface.

Note: This module contains the main admin handlers. Additional admin handlers
remain in bot.py and can be migrated here incrementally.
"""
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import admin_menu
from database_protocol import DatabaseProtocol
from handlers.common import get_uzb_time
from localization import get_text

router = Router(name="admin_panel")


@router.message(Command("admin"))
async def cmd_admin(message: types.Message, db: DatabaseProtocol):
    lang = db.get_user_language(message.from_user.id)

    if not db.is_admin(message.from_user.id):
        await message.answer(get_text(lang, "no_admin_access"))
        return

    await message.answer(
        "👑 <b>Админ-панель Fudly</b>\n\n" "Добро пожаловать! Выберите раздел:",
        parse_mode="HTML",
        reply_markup=admin_menu(),
    )


@router.message(F.text == "📊 Dashboard")
async def admin_dashboard(message: types.Message, db: DatabaseProtocol):
    """Main panel with general statistics and quick actions."""
    if not db.is_admin(message.from_user.id):
        return

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # General statistics
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'seller'")
        sellers = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'")
        customers = cursor.fetchone()[0]

        # Stores
        cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'active'")
        active_stores = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'pending'")
        pending_stores = cursor.fetchone()[0]

        # Offers
        cursor.execute("SELECT COUNT(*) FROM offers WHERE status = 'active'")
        active_offers = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM offers WHERE status = 'inactive'")
        inactive_offers = cursor.fetchone()[0]

        # Bookings
        cursor.execute("SELECT COUNT(*) FROM bookings")
        total_bookings = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM bookings WHERE status = 'pending'")
        pending_bookings = cursor.fetchone()[0]

        # Today's statistics
        today = get_uzb_time().strftime("%Y-%m-%d")

        cursor.execute("SELECT COUNT(*) FROM bookings WHERE DATE(created_at) = %s", (today,))
        today_bookings = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT SUM(o.discount_price * b.quantity)
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            WHERE DATE(b.created_at) = %s AND b.status != %s
        """,
            (today, "cancelled"),
        )
        today_revenue = cursor.fetchone()[0] or 0

        # New users today
        cursor.execute(
            """
            SELECT COUNT(*) FROM users
            WHERE DATE(created_at) = %s
        """,
            (today,),
        )
        today_users = cursor.fetchone()[0]

    # Format message
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

    # Inline buttons for quick actions
    kb = InlineKeyboardBuilder()

    if pending_stores > 0:
        kb.button(text=f"⏳ Модерация ({pending_stores})", callback_data="admin_moderation")

    kb.button(text="📊 Детальная статистика", callback_data="admin_detailed_stats")
    kb.button(text="🔄 Обновить", callback_data="admin_refresh_dashboard")
    kb.adjust(1)

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.message(F.text == "🔙 Выход")
async def admin_exit(message: types.Message, db: DatabaseProtocol):
    """Exit admin panel."""
    if not db.is_admin(message.from_user.id):
        return

    lang = db.get_user_language(message.from_user.id)
    user = db.get_user_model(message.from_user.id)

    # Import here to avoid circular dependencies
    from app.keyboards import main_menu_customer, main_menu_seller

    # Return to appropriate main menu based on user role
    user_role = user.role if user else "customer"
    menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)

    await message.answer("👋 Выход из админ-панели", reply_markup=menu)


@router.message(Command("load_test_data"))
async def load_test_data(message: types.Message, db: DatabaseProtocol):
    """Load test products into database."""
    if not db.is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        return

    await message.answer("⏳ Загружаю тестовые товары...")

    import random
    from datetime import datetime, timedelta

    # Sample product data
    PRODUCTS = [
        # Bakery
        ("Хлеб белый", "Свежий белый хлеб", 5000, 4000, "bakery", "шт"),
        ("Хлеб черный", "Ржаной хлеб", 6000, 4500, "bakery", "шт"),
        ("Батон нарезной", "Классический батон", 4500, 3500, "bakery", "шт"),
        ("Булочки с изюмом", "Сдобные булочки", 8000, 6000, "bakery", "упак"),
        ("Круассаны", "Французские круассаны", 12000, 9000, "bakery", "упак"),
        ("Лепешка узбекская", "Свежая лепешка", 3000, 2500, "bakery", "шт"),
        ("Сомса с мясом", "Свежая сомса", 10000, 8000, "bakery", "шт"),
        # Dairy
        ("Молоко 3.2%", "Пастеризованное", 10000, 8500, "dairy", "л"),
        ("Кефир", "Натуральный кефир", 12000, 10000, "dairy", "л"),
        ("Йогурт натуральный", "Без добавок", 8000, 6500, "dairy", "шт"),
        ("Yogurt фруктовый", "С клубникой", 9000, 7000, "dairy", "шт"),
        ("Сметана 20%", "Густая сметана", 15000, 12000, "dairy", "кг"),
        ("Творог 9%", "Домашний творог", 18000, 15000, "dairy", "кг"),
        ("Сыр российский", "Твердый сыр", 50000, 40000, "dairy", "кг"),
        # Meat
        ("Курица целая", "Охлажденная", 28000, 24000, "meat", "кг"),
        ("Говядина", "Вырезка", 80000, 70000, "meat", "кг"),
        ("Колбаса докторская", "ГОСТ", 45000, 38000, "meat", "кг"),
        ("Пельмени домашние", "Ручная лепка", 35000, 30000, "meat", "кг"),
        # Fruits
        ("Яблоки красные", "Импорт", 18000, 15000, "fruits", "кг"),
        ("Бананы", "Эквадор", 20000, 17000, "fruits", "кг"),
        ("Апельсины", "Турция", 22000, 18000, "fruits", "кг"),
        ("Виноград белый", "Без косточек", 35000, 30000, "fruits", "кг"),
        # Vegetables
        ("Помидоры", "Свежие", 15000, 12000, "vegetables", "кг"),
        ("Огурцы", "Местные", 12000, 10000, "vegetables", "кг"),
        ("Картофель", "Молодой", 8000, 6500, "vegetables", "кг"),
        ("Перец болгарский", "Разноцветный", 25000, 20000, "vegetables", "кг"),
        # Drinks
        ("Вода минеральная", "Гидролайф 1.5л", 3000, 2500, "drinks", "шт"),
        ("Сок апельсиновый", "Rich 1л", 12000, 10000, "drinks", "шт"),
        ("Coca-Cola", "1.5л", 10000, 8500, "drinks", "шт"),
        ("Чай Ahmad Tea", "Earl Grey 100пак", 35000, 30000, "drinks", "упак"),
        ("Coffee Nescafe", "Classic 100г", 40000, 35000, "drinks", "банка"),
        # Snacks
        ("Чипсы Lays", "Сметана-лук", 8000, 6500, "snacks", "упак"),
        ("Орехи миндаль", "Жареный", 40000, 35000, "snacks", "кг"),
        ("Шоколад Milka", "Молочный 90г", 12000, 10000, "snacks", "шт"),
        ("Конфеты Raffaello", "150г", 35000, 30000, "snacks", "упак"),
        # Frozen
        ("Пицца замороженная", "Маргарита", 30000, 25000, "frozen", "шт"),
        ("Мороженое эскимо", "Шоколадное", 15000, 12000, "frozen", "упак"),
    ]

    # Find first active store in Samarkand
    stores = db.get_stores_by_city("Самарканд")
    if not stores:
        await message.answer("❌ Не найдено магазинов в Самарканде")
        return

    store = stores[0]
    store_id = store.get("store_id") or store[0]

    today = datetime.now()
    added_count = 0

    for title, description, original_price, discount_price, category, unit in PRODUCTS:
        try:
            quantity = random.randint(10, 50)
            days_ahead = random.randint(3, 7)
            expiry_date = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

            offer_id = db.add_offer(
                store_id=store_id,
                title=title,
                description=description,
                original_price=original_price,
                discount_price=discount_price,
                quantity=quantity,
                expiry_date=expiry_date,
                unit=unit,
                category=category,
            )
            added_count += 1
        except Exception as e:
            print(f"Error adding {title}: {e}")
            continue

    await message.answer(
        f"✅ <b>Загружено тестовых товаров: {added_count}</b>\n\n"
        f"📦 Категории: bakery, dairy, meat, fruits, vegetables, drinks, snacks, frozen\n"
        f"🏪 Магазин ID: {store_id}\n"
        f"📅 Срок годности: 3-7 дней\n"
        f"💰 Цены: 2,500 - 80,000 сум\n\n"
        f"Товары доступны для поиска и бронирования!",
        parse_mode="HTML",
    )
