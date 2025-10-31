from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile
import asyncio
import os
import random
import string
import socket
import sys
import signal
from datetime import datetime
from dotenv import load_dotenv
from database import Database
from keyboards import *
from localization import get_text, get_cities, get_categories

# Production optimizations (optional imports with fallbacks)
try:
    from security import validator, rate_limiter, secure_user_input, validate_admin_action
    from logging_config import logger
    from background import start_background_tasks
    PRODUCTION_FEATURES = True
except ImportError as e:
    print(f"⚠️ Production features not available: {e}")
    # Create fallback implementations
    class FallbackValidator:
        @staticmethod
        def sanitize_text(text, max_length=1000):
            return str(text)[:max_length] if text else ""
        @staticmethod
        def validate_city(city):
            return bool(city and len(city) < 50)
    
    class FallbackRateLimiter:
        def is_allowed(self, *args, **kwargs):
            return True
    
    validator = FallbackValidator()
    rate_limiter = FallbackRateLimiter()
    
    def secure_user_input(func):
        return func
    
    def validate_admin_action(user_id, db):
        return db.is_admin(user_id)
    
    import logging
    logger = logging.getLogger('fudly')
    
    def start_background_tasks(db):
        print("Background tasks disabled (dependencies not available)")
    
    PRODUCTION_FEATURES = False

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# Словарь для преобразования узбекских названий городов в русские
CITY_UZ_TO_RU = {
    "Toshkent": "Ташкент",
    "Samarqand": "Самарканд",
    "Buxoro": "Бухара",
    "Andijon": "Андижан",
    "Namangan": "Наманган",
    "Farg'ona": "Фергана",
    "Xiva": "Хива",
    "Nukus": "Нукус"
}

def normalize_city(city: str) -> str:
    """Преобразует название города в русский формат для поиска в БД"""
    return CITY_UZ_TO_RU.get(city, city)

# Initialize bot, dispatcher and database
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
db = Database()

# Устанавливаем первого админа при старте
if ADMIN_ID > 0:
    try:
        # Проверяем существует ли пользователь
        user = db.get_user(ADMIN_ID)
        if not user:
            # Создаём пользователя-админа
            db.add_user(ADMIN_ID, "admin", "Admin")
        # Делаем админом
        db.set_admin(ADMIN_ID)
        print(f"✅ Админ установлен: {ADMIN_ID}")
    except Exception as e:
        print(f"⚠️ Ошибка при установке админа: {e}")

# FSM States
class Registration(StatesGroup):
    phone = State()
    city = State()

class RegisterStore(StatesGroup):
    city = State()
    category = State()
    name = State()
    address = State()
    description = State()
    phone = State()

class CreateOffer(StatesGroup):
    store_id = State()
    title = State()
    description = State()
    photo = State()
    original_price = State()
    discount_price = State()
    quantity = State()
    available_from = State()
    expiry_date = State()  # Новое поле для срока годности (дата)
    available_until = State()  # Остается для времени забора

class BulkCreate(StatesGroup):
    store_id = State()
    title = State()
    description = State()
    photo = State()
    original_price = State()
    discount_price = State()
    quantity = State()
    available_from = State()
    available_until = State()
    count = State()

class ChangeCity(StatesGroup):
    city = State()

class ConfirmOrder(StatesGroup):
    booking_code = State()

class BookOffer(StatesGroup):
    offer_id = State()
    quantity = State()

# ============== КОМАНДА /START ==============

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    
    if not user:
        # Новый пользователь - выбор языка
        db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
        await message.answer(
            get_text('ru', 'choose_language'),
            reply_markup=language_keyboard()
        )
        return
    
    lang = db.get_user_language(message.from_user.id)
    
    # Проверка телефона
    if not user[3]:
        await message.answer(
            get_text(lang, 'welcome', name=message.from_user.first_name),
            parse_mode="HTML",
            reply_markup=phone_request_keyboard(lang)
        )
        await state.set_state(Registration.phone)
        return
    
    # Проверка города
    if not user[4]:
        await message.answer(
            get_text(lang, 'choose_city'),
            parse_mode="HTML",
            reply_markup=city_keyboard(lang)
        )
        await state.set_state(Registration.city)
        return
    
    # Приветствие
    menu = main_menu_seller(lang) if user[5] == "seller" else main_menu_customer(lang)
    await message.answer(
        get_text(lang, 'welcome_back', name=message.from_user.first_name, city=user[4]),
        parse_mode="HTML",
        reply_markup=menu
    )

# ============== АДМИН ПАНЕЛЬ ==============

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    lang = db.get_user_language(message.from_user.id)
    
    if not db.is_admin(message.from_user.id):
        await message.answer(get_text(lang, 'no_admin_access'))
        return
    
    await message.answer(
        "👑 <b>Админ панель</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=admin_menu()
    )

# ============== АДМИН ПАНЕЛЬ - ОБРАБОТЧИКИ ==============

@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: types.Message):
    print(f"DEBUG: Получено сообщение: '{message.text}'")
    lang = 'ru'
    if not db.is_admin(message.from_user.id):
        print(f"DEBUG: Пользователь {message.from_user.id} не админ")
        await message.answer(get_text(lang, 'access_denied'))
        return
    
    print("DEBUG: Начинаем сбор статистики")
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users')
    users_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "approved"')
    stores_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "pending"')
    pending_stores = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "active"')
    offers_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM bookings')
    bookings_count = cursor.fetchone()[0]
    
    conn.close()
    
    text = f"📊 <b>Статистика системы</b>\n\n"
    text += f"👥 Пользователей: {users_count}\n"
    text += f"🏪 Магазинов: {stores_count}\n"
    text += f"⏳ На модерации: {pending_stores}\n"
    text += f"🍽 Активных предложений: {offers_count}\n"
    text += f"📋 Бронирований: {bookings_count}"
    
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "👥 Пользователи")
async def admin_users(message: types.Message):
    print(f"DEBUG: Получено сообщение для пользователей: '{message.text}'")
    lang = 'ru'
    if not db.is_admin(message.from_user.id):
        print(f"DEBUG: Пользователь {message.from_user.id} не админ")
        await message.answer(get_text(lang, 'access_denied'))
        return
    
    print("DEBUG: Собираем данные пользователей")
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "seller"')
    sellers = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "customer"')
    customers = cursor.fetchone()[0]
    conn.close()
    
    text = f"👥 <b>Пользователи</b>\n\n"
    text += f"Всего: {total}\n"
    text += f"🏪 Партнеров: {sellers}\n"
    text += f"🛍 Покупателей: {customers}"
    
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🔙 Выход из админки")
async def admin_exit(message: types.Message):
    lang = db.get_user_language(message.from_user.id)
    user = db.get_user(message.from_user.id)
    menu = main_menu_seller(lang) if user and user[6] == "seller" else main_menu_customer(lang)
    await message.answer(
        get_text(lang, 'operation_cancelled'),
        reply_markup=menu
    )

# ============== ВЫБОР ЯЗЫКА ==============

@dp.callback_query(F.data.startswith("lang_"))
async def choose_language(callback: types.CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    db.update_user_language(callback.from_user.id, lang)
    
    await callback.message.edit_text(get_text(lang, 'language_changed'))
    
    # Показываем меню после выбора языка
    user = db.get_user(callback.from_user.id)
    
    # ПРОВЕРКА: если пользователь удалил аккаунт
    if not user:
        # Создаём нового пользователя
        db.add_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
        db.update_user_language(callback.from_user.id, lang)
        await callback.message.answer(
            get_text(lang, 'welcome', name=callback.from_user.first_name),
            parse_mode="HTML",
            reply_markup=phone_request_keyboard(lang)
        )
        await state.set_state(Registration.phone)
        return
    
    # Если нет телефона - запрашиваем
    if not user[3]:
        await callback.message.answer(
            get_text(lang, 'welcome', name=callback.from_user.first_name),
            parse_mode="HTML",
            reply_markup=phone_request_keyboard(lang)
        )
        await state.set_state(Registration.phone)
        return
    
    # Если нет города - запрашиваем
    if not user[4]:
        await callback.message.answer(
            get_text(lang, 'choose_city'),
            parse_mode="HTML",
            reply_markup=city_keyboard(lang)
        )
        await state.set_state(Registration.city)
        return
    
    # Показываем главное меню
    menu = main_menu_seller(lang) if user[5] == "seller" else main_menu_customer(lang)
    await callback.message.answer(
        get_text(lang, 'welcome_back', name=callback.from_user.first_name, city=user[4]),
        parse_mode="HTML",
        reply_markup=menu
    )

# ============== ОТМЕНА ДЕЙСТВИЙ ==============

@dp.message(F.text.contains("Отмена") | F.text.contains("Bekor qilish"))
async def cancel_action(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.clear()
    
    user = db.get_user(message.from_user.id)
    menu = main_menu_seller(lang) if user[5] == "seller" else main_menu_customer(lang)
    
    await message.answer(
        get_text(lang, 'operation_cancelled'),
        reply_markup=menu
    )

# ============== РЕГИСТРАЦИЯ ==============

@dp.message(Registration.phone, F.contact)
async def process_phone(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    phone = message.contact.phone_number
    db.update_user_phone(message.from_user.id, phone)
    
    await message.answer(
        get_text(lang, 'choose_city'),
        parse_mode="HTML",
        reply_markup=city_keyboard(lang)
    )
    await state.set_state(Registration.city)

@dp.message(Registration.city)
@secure_user_input
async def process_city(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    
    # Rate limiting check
    try:
        if not rate_limiter.is_allowed(message.from_user.id, 'city_selection', max_requests=5, window_seconds=60):
            await message.answer(get_text(lang, 'rate_limit_exceeded', 'Слишком много запросов. Попробуйте позже.'))
            return
    except Exception as e:
        logger.warning(f"Rate limiter error: {e}")
    
    cities = get_cities(lang)
    city_text = validator.sanitize_text(message.text.replace("📍 ", "").strip())
    
    # Validate city input
    if not validator.validate_city(city_text):
        await message.answer(get_text(lang, 'invalid_city', 'Пожалуйста, выберите город из списка.'))
        return
    
    if city_text in cities:
        db.update_user_city(message.from_user.id, city_text)
        await state.clear()
        await message.answer(
            get_text(lang, 'city_changed', city=city_text),
            reply_markup=main_menu_customer(lang)
        )

# ============== ДОСТУПНЫЕ ПРЕДЛОЖЕНИЯ ==============

@dp.message(F.text.contains("Доступные предложения") | F.text.contains("Mavjud takliflar"))
async def available_offers(message: types.Message):
    lang = db.get_user_language(message.from_user.id)
    
    # Показываем ВСЕ предложения независимо от города и языка
    offers = db.get_active_offers()
    
    if not offers:
        await message.answer(get_text(lang, 'no_offers'))
        return
    
    await message.answer(get_text(lang, 'offers_found', count=len(offers)), parse_mode="HTML")
    
    for offer in offers[:20]:
        discount_percent = int((1 - offer[5] / offer[4]) * 100)
        
        text = f"🍽 <b>{offer[2]}</b>\n"
        text += f"📝 {offer[3]}\n\n"
        text += f"💰 {int(offer[4]):,} ➜ <b>{int(offer[5]):,} сум</b> (-{discount_percent}%)\n"
        text += f"📦 {get_text(lang, 'available')}: {offer[6]} шт.\n"
        text += f"🕐 {get_text(lang, 'time')}: {offer[7]} - {offer[8]}\n"
        
        # Показываем срок годности если он есть
        if len(offer) > 10 and offer[9]:  # expiry_date - индекс 9
            text += f"📅 Годен до: {offer[9]}\n"
        
        text += f"📍 {offer[12]}, {offer[13]}"
        
        # Если есть фото
        if offer[14]:  # photo field
            try:
                await message.answer_photo(
                    photo=offer[14],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=offer_keyboard(offer[0], lang)
                )
            except:
                await message.answer(text, parse_mode="HTML", reply_markup=offer_keyboard(offer[0], lang))
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=offer_keyboard(offer[0], lang))

# ============== БРОНИРОВАНИЕ ==============

@dp.callback_query(F.data.startswith("book_"))
async def book_offer_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало бронирования - спрашиваем количество"""
    lang = db.get_user_language(callback.from_user.id)
    offer_id = int(callback.data.split("_")[1])
    offer = db.get_offer(offer_id)
    
    if not offer or offer[6] <= 0:
        await callback.answer(get_text(lang, 'no_offers'), show_alert=True)
        return
    
    # Сохраняем offer_id в состояние
    await state.update_data(offer_id=offer_id)
    await state.set_state(BookOffer.quantity)
    
    # Спрашиваем количество
    await callback.message.answer(
        f"🍽 <b>{offer[2]}</b>\n\n"
        f"📦 Доступно: {offer[6]} шт.\n"
        f"💰 Цена за 1 шт: {int(offer[5]):,} сум\n\n"
        f"Сколько вы хотите забронировать? (1-{offer[6]})",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(lang)
    )
    await callback.answer()

@dp.message(BookOffer.quantity)
async def book_offer_quantity(message: types.Message, state: FSMContext):
    """Обработка количества и создание бронирования"""
    lang = db.get_user_language(message.from_user.id)
    
    try:
        quantity = int(message.text)
        if quantity < 1:
            await message.answer("❌ Количество должно быть больше 0")
            return
        
        data = await state.get_data()
        offer_id = data['offer_id']
        offer = db.get_offer(offer_id)
        
        if not offer or offer[6] < quantity:
            await message.answer(f"❌ Доступно только {offer[6]} шт.")
            return
        
        # Создаём бронирование
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        booking_id = db.create_booking(offer_id, message.from_user.id, code)
        db.update_offer_quantity(offer_id, offer[6] - quantity)
        
        await state.clear()
        
        # Уведомление партнёру
        store = db.get_store(offer[1])
        if store:
            partner_lang = db.get_user_language(store[1])
            try:
                await bot.send_message(
                    store[1],
                    f"🔔 <b>Новое бронирование!</b>\n\n"
                    f"🏪 {store[2]}\n"
                    f"🍽 {offer[2]}\n"
                    f"📦 Количество: {quantity} шт.\n"
                    f"👤 {message.from_user.first_name}\n"
                    f"🎫 <code>{code}</code>\n"
                    f"💰 {int(offer[5] * quantity):,} сум",
                    parse_mode="HTML"
                )
            except:
                pass
        
        total_price = int(offer[5] * quantity)
        text = get_text(lang, 'booking_success',
                       store_name=offer[12],
                       offer_name=offer[2],
                       price=f"{total_price:,}",
                       city=offer[14],
                       address=offer[13],
                       time=offer[8],
                       code=code)
        text += f"\n📦 Количество: {quantity} шт."
        
        user = db.get_user(message.from_user.id)
        menu = main_menu_seller(lang) if user and user[6] == "seller" else main_menu_customer(lang)
        
        await message.answer(text, parse_mode="HTML", reply_markup=booking_keyboard(booking_id, lang))
        await message.answer("✅ Готово!", reply_markup=menu)
        
    except ValueError:
        await message.answer("❌ Введите число!")

# ============== МОИ БРОНИРОВАНИЯ ==============

@dp.message(F.text.contains("Мои бронирования") | F.text.contains("Mening buyurt"))
async def my_bookings(message: types.Message):
    lang = db.get_user_language(message.from_user.id)
    bookings = db.get_user_bookings(message.from_user.id)
    
    if not bookings:
        await message.answer(get_text(lang, 'my_bookings_empty'))
        return
    
    await message.answer(get_text(lang, 'active_bookings', count=len(bookings)), parse_mode="HTML")
    
    # SQL: b.* (8 полей: 0-7), o.title (8), o.discount_price (9), o.available_until (10), s.name (11), s.address (12), s.city (13)
    # b.* = booking_id[0], offer_id[1], user_id[2], status[3], booking_code[4], pickup_time[5], quantity[6], created_at[7]
    for booking in bookings:
        if booking[3] == "pending":
            try:
                quantity = 1
                # Пытаемся получить quantity из разных позиций
                for i in [6, 7, 8]:
                    if len(booking) > i and booking[i] and str(booking[i]).isdigit():
                        quantity = int(booking[i])
                        break
            except:
                quantity = 1
            
            try:
                discount_price = float(booking[9]) if len(booking) > 9 else 0
            except:
                discount_price = 0
            total_price = int(discount_price * quantity)  # discount_price * quantity
            
            text = f"🎫 <b>#{booking[0]}</b>\n"
            text += f"🍽 {booking[8]}\n"  # title
            text += f"🏪 {booking[11]}\n"  # store_name
            text += f"� Количество: {quantity} шт\n"
            text += f"💰 {total_price:,} сум\n"
            text += f"📍 {booking[13]}, {booking[12]}\n"  # city, address
            text += f"🕐 {booking[10]}\n\n"  # available_until
            text += f"🎫 Код: <code>{booking[4]}</code>"  # booking_code
            
            await message.answer(text, parse_mode="HTML", reply_markup=booking_keyboard(booking[0], lang))

@dp.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: types.CallbackQuery):
    lang = db.get_user_language(callback.from_user.id)
    booking_id = int(callback.data.split("_")[2])
    
    booking = db.get_booking(booking_id)
    if booking and booking[3] == 'pending':  # Только если статус pending
        offer = db.get_offer(booking[1])
        if offer:
            db.cancel_booking(booking_id)
            # Возвращаем товар (update_offer_quantity сам активирует если нужно)
            db.update_offer_quantity(booking[1], offer[6] + 1)
        
        await callback.message.edit_text(
            callback.message.text + f"\n\n❌ {get_text(lang, 'booking_cancelled')}"
        )
    await callback.answer()

# ============== СТАТЬ ПАРТНЁРОМ ==============

@dp.message(F.text.contains("Стать партнером") | F.text.contains("Hamkor bolish"))
async def become_partner(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    user = db.get_user(message.from_user.id)
    
    # ПРОВЕРКА: если пользователя нет в БД
    if not user:
        await message.answer(
            get_text(lang, 'choose_language'),
            reply_markup=language_keyboard()
        )
        return
    
    # Проверяем: если уже партнер И есть магазин - просто переключаем режим
    # user: [0]user_id, [1]username, [2]first_name, [3]phone, [4]city, [5]language, [6]role, [7]is_admin, [8]notifications
    if user[6] == 'seller':
        # Проверяем, есть ли у партнера хоть один магазин
        stores = db.get_user_stores(message.from_user.id)
        if stores:
            await message.answer(
                get_text(lang, 'switched_to_seller'),
                reply_markup=main_menu_seller(lang)
            )
            return
        else:
            # Если магазина нет - меняем роль на customer и начинаем регистрацию
            db.update_user_role(message.from_user.id, 'customer')
    
    # Если не партнер или нет магазина - начинаем регистрацию
    await message.answer(
        get_text(lang, 'become_partner_text'),
        parse_mode="HTML",
        reply_markup=city_keyboard(lang)
    )
    await state.set_state(RegisterStore.city)

@dp.message(RegisterStore.city)
async def register_store_city(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    cities = get_cities(lang)
    city_text = message.text.replace("📍 ", "").strip()
    
    if city_text in cities:
        await state.update_data(city=city_text)
        await message.answer(
            get_text(lang, 'store_category'),
            reply_markup=category_keyboard(lang)
        )
        await state.set_state(RegisterStore.category)

@dp.message(RegisterStore.category)
async def register_store_category(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    categories = get_categories(lang)
    cat_text = message.text.replace("🏷 ", "").strip()
    
    if cat_text in categories:
        await state.update_data(category=cat_text)
        await message.answer(get_text(lang, 'store_name'), reply_markup=cancel_keyboard(lang))
        await state.set_state(RegisterStore.name)

@dp.message(RegisterStore.name)
async def register_store_name(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(name=message.text)
    await message.answer(get_text(lang, 'store_address'))
    await state.set_state(RegisterStore.address)

@dp.message(RegisterStore.address)
async def register_store_address(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(address=message.text)
    await message.answer(get_text(lang, 'store_description'))
    await state.set_state(RegisterStore.description)

@dp.message(RegisterStore.description)
async def register_store_description(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(description=message.text)
    await message.answer(get_text(lang, 'store_phone'))
    await state.set_state(RegisterStore.phone)

@dp.message(RegisterStore.phone)
async def register_store_phone(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()
    
    store_id = db.add_store(
        message.from_user.id,
        data['name'],
        data['city'],
        data['address'],
        data['description'],
        data['category'],
        message.text
    )
    
    await state.clear()
    
    # Уведомляем пользователя что заявка отправлена
    await message.answer(
        get_text(lang, 'store_pending',
                name=data['name'],
                city=data['city'],
                address=data['address'],
                category=data['category'],
                description=data['description'],
                phone=message.text),
        parse_mode="HTML",
        reply_markup=main_menu_customer(lang)
    )
    
    # Уведомляем ВСЕХ админов
    admins = db.get_all_admins()
    for admin in admins:
        try:
            admin_text = (
                f"🔔 <b>Новая заявка на партнерство!</b>\n\n"
                f"От: {message.from_user.full_name} (@{message.from_user.username or 'нет'})\n"
                f"ID: <code>{message.from_user.id}</code>\n\n"
                f"🏪 {data['name']}\n"
                f"📍 {data['city']}, {data['address']}\n"
                f"🏷 {data['category']}\n"
                f"📝 {data['description']}\n"
                f"📱 {message.text}\n\n"
                f"Перейдите в админ панель для модерации."
            )
            await bot.send_message(admin[0], admin_text, parse_mode="HTML")
        except:
            pass

# ============== СОЗДАНИЕ ПРЕДЛОЖЕНИЯ ==============

@dp.message(F.text.contains("Добавить предложение") | F.text.contains("Taklif qoshish"))
async def add_offer_start(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    
    # ВАЖНО: Берём только ОДОБРЕННЫЕ магазины!
    stores = db.get_approved_stores(message.from_user.id)
    
    if not stores:
        await message.answer(get_text(lang, 'no_approved_stores'))
        return
    
    if len(stores) == 1:
        # Один магазин - сразу начинаем создание
        await state.update_data(store_id=stores[0][0])
        await message.answer(
            f"🏪 {stores[0][2]}\n\n{get_text(lang, 'offer_title')}",
            reply_markup=cancel_keyboard(lang)
        )
        await state.set_state(CreateOffer.title)
    else:
        # Несколько магазинов - нужно выбрать
        await message.answer(
            get_text(lang, 'choose_store'),
            reply_markup=cancel_keyboard(lang)
        )
        text = ""
        for i, store in enumerate(stores, 1):
            text += f"{i}. 🏪 {store[2]} - 📍 {store[3]}\n"
        await message.answer(text)
        await state.set_state(CreateOffer.store_id)

@dp.message(CreateOffer.store_id)
async def create_offer_store_selected(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    stores = db.get_approved_stores(message.from_user.id)
    
    try:
        store_num = int(message.text)
        if 1 <= store_num <= len(stores):
            selected_store = stores[store_num - 1]
            await state.update_data(store_id=selected_store[0])
            await message.answer(
                f"🏪 {selected_store[2]}\n\n{get_text(lang, 'offer_title')}",
                reply_markup=cancel_keyboard(lang)
            )
            await state.set_state(CreateOffer.title)
        else:
            await message.answer(get_text(lang, 'error_invalid_number'))
    except:
        await message.answer(get_text(lang, 'error_invalid_number'))

@dp.message(CreateOffer.title)
async def create_offer_title(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(title=message.text)
    await message.answer(get_text(lang, 'offer_description'))
    await state.set_state(CreateOffer.description)

@dp.message(CreateOffer.description)
async def create_offer_description(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(description=message.text)
    await message.answer(
        get_text(lang, 'send_photo'),
        reply_markup=cancel_keyboard(lang)
    )
    await state.set_state(CreateOffer.photo)

@dp.message(CreateOffer.photo, F.photo)
async def create_offer_photo(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    photo_id = message.photo[-1].file_id
    await state.update_data(photo=photo_id)
    await message.answer(get_text(lang, 'original_price'))
    await state.set_state(CreateOffer.original_price)

@dp.message(CreateOffer.photo)
async def create_offer_no_photo(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(photo=None)
    await message.answer(get_text(lang, 'original_price'))
    await state.set_state(CreateOffer.original_price)

@dp.message(CreateOffer.original_price)
async def create_offer_original_price(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    try:
        price = float(message.text)
        await state.update_data(original_price=price)
        await message.answer(get_text(lang, 'discount_price'))
        await state.set_state(CreateOffer.discount_price)
    except:
        await message.answer(get_text(lang, 'error_invalid_number'))

@dp.message(CreateOffer.discount_price)
async def create_offer_discount_price(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    try:
        price = float(message.text)
        await state.update_data(discount_price=price)
        await message.answer(get_text(lang, 'quantity'))
        await state.set_state(CreateOffer.quantity)
    except:
        await message.answer(get_text(lang, 'error_invalid_number'))

@dp.message(CreateOffer.quantity)
async def create_offer_quantity(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    try:
        qty = int(message.text)
        await state.update_data(quantity=qty)
        await message.answer(get_text(lang, 'time_from'))
        await state.set_state(CreateOffer.available_from)
    except:
        await message.answer(get_text(lang, 'error_invalid_number'))

@dp.message(CreateOffer.available_from)
async def create_offer_time_from(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(available_from=message.text)
    await message.answer(get_text(lang, 'expiry_date'))
    await state.set_state(CreateOffer.expiry_date)

@dp.message(CreateOffer.expiry_date)
async def create_offer_expiry_date(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(expiry_date=message.text)
    await message.answer(get_text(lang, 'time_until'))
    await state.set_state(CreateOffer.available_until)

@dp.message(CreateOffer.available_until)
async def create_offer_time_until(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()
    
    # Теперь expiry_date и available_until - это отдельные поля
    # expiry_date - срок годности продукта (например "31.12.2025")
    # available_from и available_until - время когда можно забрать (например "18:00" - "21:00")
    
    offer_id = db.add_offer(
        data['store_id'],
        data['title'],
        data['description'],
        data['original_price'],
        data['discount_price'],
        data['quantity'],
        data['available_from'],  # Время начала (например "18:00")
        message.text,  # Время окончания (например "21:00")
        data.get('photo'),
        data.get('expiry_date')  # Срок годности (например "31.12.2025")
    )
    
    await state.clear()
    
    discount = int((1 - data['discount_price'] / data['original_price']) * 100)
    text = get_text(lang, 'offer_created',
                   title=data['title'],
                   description=data['description'],
                   original_price=f"{int(data['original_price']):,}",
                   discount_price=f"{int(data['discount_price']):,}",
                   discount=discount,
                   quantity=data['quantity'],
                   time_from=data['available_from'],
                   time_until=message.text)
    
    # Добавляем информацию о сроке годности отдельно
    if data.get('expiry_date'):
        text += f"\n\n📅 Срок годности: {data['expiry_date']}"
    text += f"\n🕐 Время забора: {data['available_from']} - {message.text}"
    
    if data.get('photo'):
        await message.answer_photo(
            photo=data['photo'],
            caption=text,
            parse_mode="HTML",
            reply_markup=main_menu_seller(lang)
        )
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=main_menu_seller(lang))

# ============== МАССОВОЕ СОЗДАНИЕ ==============

@dp.message(F.text.contains("Массовое создание") | F.text.contains("Ommaviy yaratish"))
async def bulk_create_start(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    stores = db.get_approved_stores(message.from_user.id)
    
    if not stores:
        await message.answer(get_text(lang, 'no_approved_stores'))
        return
    
    if len(stores) == 1:
        # Один магазин - сразу начинаем
        await state.update_data(store_id=stores[0][0])
        await message.answer(
            get_text(lang, 'bulk_create_start', store_name=stores[0][2]),
            parse_mode="HTML",
            reply_markup=cancel_keyboard(lang)
        )
        await state.set_state(BulkCreate.title)
    else:
        # Несколько магазинов - нужно выбрать
        await message.answer(
            get_text(lang, 'choose_store'),
            reply_markup=cancel_keyboard(lang)
        )
        text = ""
        for i, store in enumerate(stores, 1):
            text += f"{i}. 🏪 {store[2]} - 📍 {store[3]}\n"
        await message.answer(text)
        await state.set_state(BulkCreate.store_id)

@dp.message(BulkCreate.store_id)
async def bulk_create_store_selected(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    stores = db.get_approved_stores(message.from_user.id)
    
    try:
        store_num = int(message.text)
        if 1 <= store_num <= len(stores):
            selected_store = stores[store_num - 1]
            await state.update_data(store_id=selected_store[0])
            await message.answer(
                get_text(lang, 'bulk_create_start', store_name=selected_store[2]),
                parse_mode="HTML",
                reply_markup=cancel_keyboard(lang)
            )
            await state.set_state(BulkCreate.title)
        else:
            await message.answer(get_text(lang, 'error_invalid_number'))
    except:
        await message.answer(get_text(lang, 'error_invalid_number'))

@dp.message(BulkCreate.title)
async def bulk_create_title(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(title=message.text)
    await message.answer(get_text(lang, 'offer_description'))
    await state.set_state(BulkCreate.description)

@dp.message(BulkCreate.description)
async def bulk_create_description(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(description=message.text)
    await message.answer(
        get_text(lang, 'send_photo'),
        reply_markup=cancel_keyboard(lang)
    )
    await state.set_state(BulkCreate.photo)

@dp.message(BulkCreate.photo, F.photo)
async def bulk_create_photo(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer(get_text(lang, 'original_price'))
    await state.set_state(BulkCreate.original_price)

@dp.message(BulkCreate.photo)
async def bulk_create_no_photo(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(photo=None)
    await message.answer(get_text(lang, 'original_price'))
    await state.set_state(BulkCreate.original_price)

@dp.message(BulkCreate.original_price)
async def bulk_create_original_price(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    try:
        await state.update_data(original_price=float(message.text))
        await message.answer(get_text(lang, 'discount_price'))
        await state.set_state(BulkCreate.discount_price)
    except:
        await message.answer(get_text(lang, 'error_invalid_number'))

@dp.message(BulkCreate.discount_price)
async def bulk_create_discount_price(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    try:
        await state.update_data(discount_price=float(message.text))
        await message.answer(get_text(lang, 'quantity'))
        await state.set_state(BulkCreate.quantity)
    except:
        await message.answer(get_text(lang, 'error_invalid_number'))

@dp.message(BulkCreate.quantity)
async def bulk_create_quantity(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    try:
        await state.update_data(quantity=int(message.text))
        await message.answer(get_text(lang, 'time_from'))
        await state.set_state(BulkCreate.available_from)
    except:
        await message.answer(get_text(lang, 'error_invalid_number'))

@dp.message(BulkCreate.available_from)
async def bulk_create_time_from(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(available_from=message.text)
    await message.answer(get_text(lang, 'time_until'))
    await state.set_state(BulkCreate.available_until)

@dp.message(BulkCreate.available_until)
async def bulk_create_time_until(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(available_until=message.text)
    await message.answer(get_text(lang, 'bulk_count'), parse_mode="HTML")
    await state.set_state(BulkCreate.count)

@dp.message(BulkCreate.count)
async def bulk_create_count(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    try:
        count = int(message.text)
        if count < 1 or count > 100:
            await message.answer(get_text(lang, 'invalid_range'))
            return
        
        data = await state.get_data()
        created = 0
        
        for i in range(count):
            offer_id = db.add_offer(
                data['store_id'],
                data['title'],
                data['description'],
                data['original_price'],
                data['discount_price'],
                data['quantity'],
                data['available_from'],
                data['available_until'],
                data.get('photo')
            )
            if offer_id:
                created += 1
        
        await state.clear()
        
        discount = int((1 - data['discount_price'] / data['original_price']) * 100)
        total_qty = data['quantity'] * created
        
        text = get_text(lang, 'bulk_created',
                       count=created,
                       title=data['title'],
                       description=data['description'],
                       original_price=f"{int(data['original_price']):,}",
                       discount_price=f"{int(data['discount_price']):,}",
                       discount=discount,
                       quantity=data['quantity'],
                       total_quantity=total_qty,
                       time_from=data['available_from'],
                       time_until=data['available_until'])
        
        await message.answer(text, parse_mode="HTML", reply_markup=main_menu_seller(lang))
    except:
        await message.answer(get_text(lang, 'error_invalid_number'))

# ============== МОИ ПРЕДЛОЖЕНИЯ ==============

@dp.message(F.text.contains("Мои предложения") | F.text.contains("Mening taklif"))
async def my_offers(message: types.Message):
    lang = db.get_user_language(message.from_user.id)
    stores = db.get_user_stores(message.from_user.id)
    
    if not stores:
        await message.answer(get_text(lang, 'no_stores'))
        return
    
    all_offers = []
    for store in stores:
        offers = db.get_store_offers(store[0])
        all_offers.extend(offers)
    
    if not all_offers:
        await message.answer(get_text(lang, 'no_offers_yet'))
        return
    
    await message.answer(get_text(lang, 'your_offers', count=len(all_offers)), parse_mode="HTML")
    
    # offers: SELECT * FROM offers (11 полей)
    # [0]offer_id, [1]store_id, [2]title, [3]description, [4]original_price, [5]discount_price,
    # [6]quantity, [7]available_from, [8]available_until, [9]status, [10]photo, [11]created_at
    for offer in all_offers[:15]:
        text = f"{'✅' if offer[9] == 'active' else '❌'} <b>{offer[2]}</b>\n"
        text += f"💰 {int(offer[4]):,} ➜ {int(offer[5]):,} сум\n"
        text += f"📦 Осталось: {offer[6]} шт.\n"
        text += f"🕐 {offer[7]} - {offer[8]}"
        
        if offer[10]:  # photo (индекс 10, а не 14!)
            try:
                await message.answer_photo(
                    photo=offer[10],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=offer_manage_keyboard(offer[0], lang)
                )
            except:
                await message.answer(text, parse_mode="HTML", reply_markup=offer_manage_keyboard(offer[0], lang))
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=offer_manage_keyboard(offer[0], lang))

# ============== ДУБЛИРОВАНИЕ/УДАЛЕНИЕ ==============

@dp.callback_query(F.data.startswith("duplicate_"))
async def duplicate_offer(callback: types.CallbackQuery):
    lang = db.get_user_language(callback.from_user.id)
    offer_id = int(callback.data.split("_")[1])
    offer = db.get_offer(offer_id)
    
    if offer:
        # offer из get_offer: [0-11]=o.*, [12]=store_name, [13]=address, [14]=city, [15]=category
        # но для add_offer нужно только базовые поля из таблицы offers
        new_id = db.add_offer(
            offer[1], offer[2], offer[3], offer[4], offer[5],
            offer[6], offer[7], offer[8], offer[10]  # photo из offers
        )
        await callback.answer(get_text(lang, 'duplicated'), show_alert=True)

@dp.callback_query(F.data.startswith("delete_offer_"))
async def delete_offer(callback: types.CallbackQuery):
    lang = db.get_user_language(callback.from_user.id)
    offer_id = int(callback.data.split("_")[2])
    db.deactivate_offer(offer_id)
    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n❌ {get_text(lang, 'deleted')}"
    ) if callback.message.photo else await callback.message.edit_text(
        callback.message.text + f"\n\n❌ {get_text(lang, 'deleted')}"
    )
    await callback.answer()

# ============== ПОДТВЕРЖДЕНИЕ ВЫДАЧИ ==============

@dp.message(F.text.contains("Подтвердить выдачу") | F.text.contains("Berishni"))
async def confirm_delivery_start(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await message.answer(
        get_text(lang, 'confirm_delivery_prompt'),
        parse_mode="HTML",
        reply_markup=cancel_keyboard(lang)
    )
    await state.set_state(ConfirmOrder.booking_code)

@dp.message(ConfirmOrder.booking_code)
async def confirm_delivery_process(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    code = message.text.upper().strip()
    
    booking = db.get_booking_by_code(code)
    
    if not booking:
        await message.answer(get_text(lang, 'booking_not_found'))
        return
    
    db.complete_booking(booking[0])
    offer = db.get_offer(booking[1])
    
    await state.clear()
    await message.answer(
        get_text(lang, 'order_confirmed',
                booking_id=booking[0],
                customer_name=booking[5],
                price=f"{int(offer[5]):,}"),
        parse_mode="HTML",
        reply_markup=main_menu_seller(lang)
    )
    
    # Отправка оценки клиенту
    customer_lang = db.get_user_language(booking[2])
    store = db.get_store(offer[1])
    try:
        await bot.send_message(
            booking[2],
            get_text(customer_lang, 'rate_store', store_name=store[2]),
            parse_mode="HTML",
            reply_markup=rate_keyboard(booking[0])
        )
    except:
        pass

# ============== РЕЙТИНГ ==============

@dp.callback_query(F.data.startswith("rate_"))
async def rate_store(callback: types.CallbackQuery):
    lang = db.get_user_language(callback.from_user.id)
    parts = callback.data.split("_")
    booking_id = int(parts[1])
    rating = int(parts[2])
    
    if db.has_rated_booking(booking_id):
        await callback.answer(get_text(lang, 'already_rated'), show_alert=True)
        return
    
    booking = db.get_booking(booking_id)
    offer = db.get_offer(booking[1])
    store_id = offer[1]
    
    db.add_rating(booking_id, callback.from_user.id, store_id, rating)
    
    await callback.message.edit_text(
        callback.message.text + f"\n\n{'⭐' * rating}\n{get_text(lang, 'rating_saved')}",
        parse_mode="HTML"
    )
    await callback.answer()

# ============== МОИ МАГАЗИНЫ ==============

@dp.message(F.text.contains("Магазины") | F.text.contains("Dokonlar"))
async def all_stores(message: types.Message):
    """Список всех магазинов в городе пользователя"""
    lang = db.get_user_language(message.from_user.id)
    user = db.get_user(message.from_user.id)
    city = user[4]  # город пользователя (исправлено: было [3], должно быть [4])
    
    # Преобразуем узбекское название города в русское для поиска в БД
    search_city = normalize_city(city)
    
    # Получаем все одобренные магазины в городе
    stores = db.get_stores_by_city(search_city)
    
    if not stores:
        await message.answer(get_text(lang, 'no_stores_in_city', city=city))
        return
    
    await message.answer(get_text(lang, 'stores_in_city', city=city, count=len(stores)), parse_mode="HTML")
    
    for store in stores:
        avg_rating = db.get_store_average_rating(store[0])
        ratings = db.get_store_ratings(store[0])
        
        text = f"""🏪 <b>{store[2]}</b>
🏷 {store[6]}
📍 {store[4]}
📝 {store[5]}
⭐ Рейтинг: {avg_rating:.1f}/5 ({len(ratings)} отзывов)"""
        
        await message.answer(text, parse_mode="HTML")

@dp.message(F.text.contains("Мои магазины") | F.text.contains("Mening dokonlarim"))
async def my_stores(message: types.Message):
    lang = db.get_user_language(message.from_user.id)
    stores = db.get_user_stores(message.from_user.id)
    
    if not stores:
        await message.answer(get_text(lang, 'no_stores'))
        return
    
    await message.answer(get_text(lang, 'your_stores', count=len(stores)))
    
    for store in stores:
        stats = db.get_store_sales_stats(store[0])
        avg_rating = db.get_store_average_rating(store[0])
        ratings = db.get_store_ratings(store[0])
        
        text = get_text(lang, 'store_stats',
                       name=store[2],
                       category=store[6],
                       city=store[3],
                       address=store[4],
                       description=store[5],
                       rating=f"{avg_rating:.1f}",
                       reviews=len(ratings),
                       sales=stats['total_sales'],
                       revenue=stats['total_revenue'],
                       pending=stats['pending_bookings'])
        
        await message.answer(text, parse_mode="HTML")

# ============== БРОНИРОВАНИЯ МАГАЗИНА ==============

@dp.message(F.text.contains("Бронирования магазина") | F.text.contains("buyurtmalari"))
async def store_bookings(message: types.Message):
    """Показать все бронирования для магазинов партнера"""
    lang = db.get_user_language(message.from_user.id)
    
    # Получаем все магазины партнера
    stores = db.get_approved_stores(message.from_user.id)
    
    if not stores:
        await message.answer(get_text(lang, 'no_approved_stores'))
        return
    
    all_bookings = []
    for store in stores:
        bookings = db.get_store_bookings(store[0])
        all_bookings.extend(bookings)
    
    if not all_bookings:
        await message.answer("📋 Пока нет бронирований")
        return
    
    # Фильтруем только активные (pending)
    pending_bookings = [b for b in all_bookings if b[3] == 'pending']
    
    if not pending_bookings:
        await message.answer("✅ Все бронирования обработаны!")
        return
    
    await message.answer(f"📋 <b>Активные бронирования: {len(pending_bookings)}</b>", parse_mode="HTML")
    
    # Показываем каждое бронирование
    # SQL из get_store_bookings: b.* (8 полей: 0-7), o.title (8), u.first_name (9), u.username (10)
    # b.* = booking_id[0], offer_id[1], user_id[2], status[3], booking_code[4], pickup_time[5], quantity[6], created_at[7]
    for booking in pending_bookings[:10]:
        quantity = booking[6] if len(booking) > 6 else 1  # quantity
        
        text = f"🎫 <b>Бронь #{booking[0]}</b>\n\n"
        text += f"🍽 {booking[8]}\n"  # offer title
        text += f"📦 Количество: {quantity} шт\n"
        text += f"👤 {booking[9]}"  # customer name
        if booking[10]:
            text += f" (@{booking[10]})"
        text += f"\n🎫 Код: <code>{booking[4]}</code>\n"  # booking code
        text += f"📅 {booking[7]}"  # created_at
        
        await message.answer(text, parse_mode="HTML")

# ============== СМЕНА ГОРОДА ==============

@dp.message(F.text.contains("Мой город") | F.text.contains("Mening shahr"))
async def change_city_start(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    await message.answer(
        get_text(lang, 'choose_city'),
        parse_mode="HTML",
        reply_markup=city_keyboard(lang)
    )
    await state.set_state(ChangeCity.city)

@dp.message(ChangeCity.city)
async def change_city_process(message: types.Message, state: FSMContext):
    lang = db.get_user_language(message.from_user.id)
    cities = get_cities(lang)
    city_text = message.text.replace("📍 ", "").strip()
    
    if city_text in cities:
        db.update_user_city(message.from_user.id, city_text)
        await state.clear()
        user = db.get_user(message.from_user.id)
        menu = main_menu_seller(lang) if user[5] == "seller" else main_menu_customer(lang)
        await message.answer(
            get_text(lang, 'city_changed', city=city_text),
            reply_markup=menu
        )

# ============== ПРОФИЛЬ ==============

@dp.message(F.text.contains("Профиль") | F.text.contains("Profil"))
async def profile(message: types.Message):
    lang = db.get_user_language(message.from_user.id)
    user = db.get_user(message.from_user.id)
    
    # ПРОВЕРКА: если пользователь удалил аккаунт
    if not user:
        await message.answer(
            get_text(lang, 'choose_language'),
            reply_markup=language_keyboard()
        )
        return
    
    # user: [0]user_id, [1]username, [2]first_name, [3]phone, [4]city, [5]language, [6]role, [7]is_admin, [8]notifications
    role_text = get_text(lang, 'role_seller') if user[6] == 'seller' else get_text(lang, 'role_customer')
    lang_text = 'Русский' if lang == 'ru' else 'Ozbekcha'
    
    text = f"{get_text(lang, 'your_profile')}\n\n"
    text += f"{get_text(lang, 'name')}: {user[2]}\n"
    text += f"{get_text(lang, 'phone')}: {user[3]}\n"
    text += f"{get_text(lang, 'city')}: {user[4]}\n"
    text += f"{get_text(lang, 'language')}: {lang_text}\n"
    text += f"{get_text(lang, 'role')}: {role_text}"
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=settings_keyboard(user[8], lang)
    )

@dp.callback_query(F.data == "change_language")
async def change_language(callback: types.CallbackQuery):
    await callback.message.answer(
        get_text('ru', 'choose_language'),
        reply_markup=language_keyboard()
    )
    await callback.answer()


# ============== НАСТРОЙКИ: УВЕДОМЛЕНИЯ / УДАЛЕНИЕ АККАУНТА ==============
@dp.callback_query(F.data == "toggle_notifications")
async def toggle_notifications_callback(callback: types.CallbackQuery):
    """Переключить уведомления пользователя и обновить клавиатуру настроек"""
    lang = db.get_user_language(callback.from_user.id)
    try:
        new_enabled = db.toggle_notifications(callback.from_user.id)
    except Exception as e:
        await callback.answer(get_text(lang, 'access_denied'), show_alert=True)
        return

    # Покажем уведомление и обновим клавиатуру настроек
    text = get_text(lang, 'notifications_enabled') if new_enabled else get_text(lang, 'notifications_disabled')
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=settings_keyboard(new_enabled, lang))
    except:
        # Если не получилось редактировать (возможно это не то сообщение), просто отправим новый
        await callback.message.answer(text, reply_markup=settings_keyboard(new_enabled, lang))

    await callback.answer()


@dp.callback_query(F.data == "delete_account")
async def delete_account_prompt(callback: types.CallbackQuery):
    """Попросить подтверждение перед удалением аккаунта"""
    lang = db.get_user_language(callback.from_user.id)

    # Подтверждение с двумя кнопками (aiogram 3.x синтаксис)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, 'yes_delete'), callback_data="confirm_delete_yes")
    builder.button(text=get_text(lang, 'no_cancel'), callback_data="confirm_delete_no")
    builder.adjust(2)

    # Редактируем сообщение (или отправляем новое) с предупреждением
    try:
        await callback.message.edit_text(get_text(lang, 'confirm_delete_account'), parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        await callback.message.answer(get_text(lang, 'confirm_delete_account'), parse_mode="HTML", reply_markup=builder.as_markup())

    await callback.answer()


@dp.callback_query(F.data == "confirm_delete_yes")
async def confirm_delete_yes(callback: types.CallbackQuery):
    lang = db.get_user_language(callback.from_user.id)

    # Удаляем данные пользователя полностью
    try:
        db.delete_user(callback.from_user.id)
    except Exception as e:
        await callback.answer(get_text(lang, 'access_denied'), show_alert=True)
        return

    # Сообщаем об удалении и предлагаем зарегистрироваться заново
    try:
        await callback.message.edit_text(
            get_text(lang, 'account_deleted') + "\n\n" + get_text(lang, 'choose_language'),
            parse_mode="HTML",
            reply_markup=language_keyboard()
        )
    except:
        await callback.message.answer(
            get_text(lang, 'account_deleted') + "\n\n" + get_text(lang, 'choose_language'),
            parse_mode="HTML",
            reply_markup=language_keyboard()
        )

    await callback.answer()


@dp.callback_query(F.data == "confirm_delete_no")
async def confirm_delete_no(callback: types.CallbackQuery):
    """Отмена удаления — возвращаем настройки"""
    lang = db.get_user_language(callback.from_user.id)
    user = db.get_user(callback.from_user.id)

    if not user:
        # На всякий случай — если пользователя уже нет
        await callback.message.edit_text(get_text(lang, 'account_deleted'))
        await callback.answer()
        return

    try:
        await callback.message.edit_text(get_text(lang, 'operation_cancelled'), reply_markup=settings_keyboard(user[8], lang))
    except:
        await callback.message.answer(get_text(lang, 'operation_cancelled'), reply_markup=settings_keyboard(user[8], lang))

    await callback.answer()

# ============== РЕЖИМ ПОКУПАТЕЛЯ ==============

@dp.message(F.text.contains("Режим покупателя") | F.text.contains("Xaridor rejimi"))
async def switch_to_customer(message: types.Message):
    lang = db.get_user_language(message.from_user.id)
    await message.answer(
        get_text(lang, 'switched_to_customer'),
        reply_markup=main_menu_customer(lang)
    )

# ============== АДМИН ПАНЕЛЬ - ОБРАБОТЧИКИ (продолжение) ==============

@dp.message(F.text == "📈 Полная статистика")
async def admin_full_stats(message: types.Message):
    lang = 'ru'
    if not db.is_admin(message.from_user.id):
        await message.answer(get_text(lang, 'access_denied'))
        return
    
    await message.answer("⏳ Собираю статистику...")
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Статистика по пользователям
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "seller"')
    sellers = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "customer"')
    customers = cursor.fetchone()[0]
    
    # Статистика по магазинам
    cursor.execute('SELECT COUNT(*) FROM stores')
    total_stores = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "approved"')
    approved_stores = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "pending"')
    pending_stores = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "rejected"')
    rejected_stores = cursor.fetchone()[0]
    
    # Статистика по городам
    cursor.execute('SELECT city, COUNT(*) FROM stores GROUP BY city ORDER BY COUNT(*) DESC LIMIT 5')
    top_cities = cursor.fetchall()
    
    # Статистика по категориям
    cursor.execute('SELECT category, COUNT(*) FROM stores GROUP BY category ORDER BY COUNT(*) DESC LIMIT 5')
    top_categories = cursor.fetchall()
    
    # Статистика по предложениям
    cursor.execute('SELECT COUNT(*) FROM offers')
    total_offers = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "active"')
    active_offers = cursor.fetchone()[0]
    cursor.execute('SELECT SUM(original_price) FROM offers WHERE status = "active"')
    total_original_price = cursor.fetchone()[0] or 0
    cursor.execute('SELECT SUM(discount_price) FROM offers WHERE status = "active"')
    total_discounted_price = cursor.fetchone()[0] or 0
    
    # Статистика по бронированиям
    cursor.execute('SELECT COUNT(*) FROM bookings')
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
    cursor.execute('''
        SELECT SUM((o.original_price - o.discount_price) * b.quantity)
        FROM bookings b
        JOIN offers o ON b.offer_id = o.offer_id
        WHERE b.status IN ("active", "completed")
    ''')
    total_savings = cursor.fetchone()[0] or 0
    
    # Самые активные магазины
    cursor.execute('''
        SELECT s.name, COUNT(b.booking_id) as bookings_count
        FROM stores s
        LEFT JOIN offers o ON s.store_id = o.store_id
        LEFT JOIN bookings b ON o.offer_id = b.offer_id
        WHERE b.status IN ("active", "completed")
        GROUP BY s.store_id
        ORDER BY bookings_count DESC
        LIMIT 5
    ''')
    top_stores = cursor.fetchall()
    
    conn.close()
    
    # Формируем текстовый отчёт
    text = "📈 <b>ПОЛНАЯ СТАТИСТИКА СИСТЕМЫ</b>\n\n"
    
    text += "👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n"
    text += f"Всего: {total_users}\n"
    text += f"🏪 Партнёров: {sellers}\n"
    text += f"🛍 Покупателей: {customers}\n\n"
    
    text += "🏪 <b>МАГАЗИНЫ</b>\n"
    text += f"Всего: {total_stores}\n"
    text += f"✅ Одобрено: {approved_stores}\n"
    text += f"⏳ На модерации: {pending_stores}\n"
    text += f"❌ Отклонено: {rejected_stores}\n\n"
    
    if top_cities:
        text += "📍 <b>ТОП-5 ГОРОДОВ</b>\n"
        for city, count in top_cities:
            text += f"• {city}: {count}\n"
        text += "\n"
    
    if top_categories:
        text += "🏷 <b>ТОП-5 КАТЕГОРИЙ</b>\n"
        for category, count in top_categories:
            text += f"• {category}: {count}\n"
        text += "\n"
    
    text += "🍽 <b>ПРЕДЛОЖЕНИЯ</b>\n"
    text += f"Всего: {total_offers}\n"
    text += f"✅ Активных: {active_offers}\n"
    text += f"💰 Общая стоимость: {int(total_original_price):,} сум\n"
    text += f"💸 Со скидкой: {int(total_discounted_price):,} сум\n\n"
    
    text += "📋 <b>БРОНИРОВАНИЯ</b>\n"
    text += f"Всего: {total_bookings}\n"
    text += f"✅ Активных: {active_bookings}\n"
    text += f"✔️ Завершено: {completed_bookings}\n"
    text += f"❌ Отменено: {cancelled_bookings}\n"
    text += f"📦 Товаров забронировано: {total_quantity} шт\n"
    text += f"💰 Экономия покупателей: {int(total_savings):,} сум\n\n"
    
    if top_stores:
        text += "🏆 <b>ТОП-5 МАГАЗИНОВ</b>\n"
        for store_name, bookings_count in top_stores:
            text += f"• {store_name}: {bookings_count} заказов\n"
    
    await message.answer(text, parse_mode="HTML")
    
    # Создаём CSV файл
    import csv
    from datetime import datetime
    from aiogram.types import FSInputFile
    
    filename = f"statistics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        
        # Заголовок
        writer.writerow(['ПОЛНАЯ СТАТИСТИКА FUDLY'])
        writer.writerow(['Дата создания', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        
        # Пользователи
        writer.writerow(['ПОЛЬЗОВАТЕЛИ'])
        writer.writerow(['Всего', total_users])
        writer.writerow(['Партнёров', sellers])
        writer.writerow(['Покупателей', customers])
        writer.writerow([])
        
        # Магазины
        writer.writerow(['МАГАЗИНЫ'])
        writer.writerow(['Всего', total_stores])
        writer.writerow(['Одобрено', approved_stores])
        writer.writerow(['На модерации', pending_stores])
        writer.writerow(['Отклонено', rejected_stores])
        writer.writerow([])
        
        # Города
        if top_cities:
            writer.writerow(['ТОП ГОРОДА'])
            writer.writerow(['Город', 'Количество'])
            for city, count in top_cities:
                writer.writerow([city, count])
            writer.writerow([])
        
        # Категории
        if top_categories:
            writer.writerow(['ТОП КАТЕГОРИИ'])
            writer.writerow(['Категория', 'Количество'])
            for category, count in top_categories:
                writer.writerow([category, count])
            writer.writerow([])
        
        # Предложения
        writer.writerow(['ПРЕДЛОЖЕНИЯ'])
        writer.writerow(['Всего', total_offers])
        writer.writerow(['Активных', active_offers])
        writer.writerow(['Общая стоимость (сум)', int(total_original_price)])
        writer.writerow(['Со скидкой (сум)', int(total_discounted_price)])
        writer.writerow([])
        
        # Бронирования
        writer.writerow(['БРОНИРОВАНИЯ'])
        writer.writerow(['Всего', total_bookings])
        writer.writerow(['Активных', active_bookings])
        writer.writerow(['Завершено', completed_bookings])
        writer.writerow(['Отменено', cancelled_bookings])
        writer.writerow(['Товаров забронировано', total_quantity])
        writer.writerow(['Экономия покупателей (сум)', int(total_savings)])
        writer.writerow([])
        
        # Топ магазины
        if top_stores:
            writer.writerow(['ТОП МАГАЗИНЫ'])
            writer.writerow(['Название', 'Заказов'])
            for store_name, bookings_count in top_stores:
                writer.writerow([store_name, bookings_count])
    
    # Отправляем файл
    document = FSInputFile(filename)
    await message.answer_document(
        document=document,
        caption="📊 Полная статистика в формате CSV"
    )
    
    # Удаляем файл после отправки
    import os
    os.remove(filename)

@dp.message(F.text == "🏪 Заявки на партнерство")
async def admin_pending_stores(message: types.Message):
    lang = 'ru'  # Админ-панель только на русском
    if not db.is_admin(message.from_user.id):
        await message.answer(get_text(lang, 'access_denied'))
        return
    
    pending = db.get_pending_stores()
    
    if not pending:
        await message.answer(get_text(lang, 'no_pending_stores'))
        return
    
    await message.answer(get_text(lang, 'pending_stores_count', count=len(pending)))
    
    for store in pending:
        text = f"🏪 <b>{store[2]}</b>\n\n"
        text += f"От: {store[8]} (@{store[9] or 'нет'})\n"
        text += f"ID: <code>{store[1]}</code>\n\n"
        text += f"📍 {store[3]}, {store[4]}\n"
        text += f"🏷 {store[6]}\n"
        text += f"📱 {store[7]}\n"
        text += f"📝 {store[5]}\n"
        text += f"📅 {store[10]}"
        
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=moderation_keyboard(store[0])
        )
        await asyncio.sleep(0.3)

@dp.callback_query(F.data.startswith("approve_"))
async def approve_store(callback: types.CallbackQuery):
    lang = 'ru'  # Админ-панель на русском
    if not db.is_admin(callback.from_user.id):
        await callback.answer(get_text(lang, 'access_denied'), show_alert=True)
        return
    
    store_id = int(callback.data.split("_")[2])
    db.approve_store(store_id)
    
    # Получаем владельца магазина
    store = db.get_store(store_id)
    if store:
        owner_id = store[1]
        db.update_user_role(owner_id, "seller")
        
        # Уведомляем владельца
        try:
            owner_lang = db.get_user_language(owner_id)
            await bot.send_message(
                owner_id,
                get_text(owner_lang, 'store_approved'),
                parse_mode="HTML",
                reply_markup=main_menu_seller(owner_lang)
            )
        except:
            pass
    
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>ОДОБРЕНО</b>",
        parse_mode="HTML"
    )
    await callback.answer(get_text(lang, 'store_approved_admin'))

@dp.callback_query(F.data.startswith("reject_"))
async def reject_store(callback: types.CallbackQuery):
    lang = 'ru'  # Админ-панель на русском
    if not db.is_admin(callback.from_user.id):
        await callback.answer(get_text(lang, 'access_denied'), show_alert=True)
        return
    
    store_id = int(callback.data.split("_")[2])
    db.reject_store(store_id, "Не соответствует требованиям")
    
    # Уведомляем владельца
    store = db.get_store(store_id)
    if store:
        owner_id = store[1]
        try:
            owner_lang = db.get_user_language(owner_id)
            await bot.send_message(
                owner_id,
                get_text(owner_lang, 'store_rejected'),
                parse_mode="HTML"
            )
        except:
            pass
    
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>ОТКЛОНЕНО</b>",
        parse_mode="HTML"
    )
    await callback.answer(get_text(lang, 'store_rejected_admin'))

@dp.message(F.text == " Все предложения")
async def admin_all_offers(message: types.Message):
    lang = 'ru'
    if not db.is_admin(message.from_user.id):
        await message.answer(get_text(lang, 'access_denied'))
        return
    
    offers = db.get_active_offers()
    text = f"📋 <b>Все предложения</b>\n\n"
    text += f"Активных: {len(offers)}"
    
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🏪 Все магазины")
async def admin_all_stores(message: types.Message):
    lang = 'ru'
    if not db.is_admin(message.from_user.id):
        await message.answer(get_text(lang, 'access_denied'))
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM stores ORDER BY created_at DESC')
    stores = cursor.fetchall()
    conn.close()
    
    if not stores:
        await message.answer("Магазинов нет")
        return
    
    await message.answer(f"🏪 <b>Все магазины ({len(stores)})</b>", parse_mode="HTML")
    
    for store in stores[:20]:
        status_emoji = {
            'approved': '✅',
            'pending': '⏳',
            'rejected': '❌'
        }.get(store[8], '❓')
        
        text = f"{status_emoji} <b>{store[2]}</b>\n"
        text += f"ID: {store[0]}\n"
        text += f"📍 {store[3]}, {store[4]}\n"
        text += f"🏷 {store[6]}\n"
        text += f"Статус: {store[8]}"
        
        # Создаем inline кнопку для удаления
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="🗑 Удалить магазин", callback_data=f"delete_store_{store[0]}")
        
        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
        await asyncio.sleep(0.2)

@dp.callback_query(F.data.startswith("delete_store_"))
async def delete_store_callback(callback: types.CallbackQuery):
    lang = 'ru'
    if not db.is_admin(callback.from_user.id):
        await callback.answer(get_text(lang, 'access_denied'), show_alert=True)
        return
    
    store_id = int(callback.data.split("_")[2])
    
    try:
        db.delete_store(store_id)
        await callback.message.edit_text(
            callback.message.text + "\n\n🗑 <b>УДАЛЕНО</b>",
            parse_mode="HTML"
        )
        await callback.answer("✅ Магазин удалён!")
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.message(F.text == "📢 Рассылка")
async def admin_broadcast(message: types.Message):
    lang = 'ru'
    if not db.is_admin(message.from_user.id):
        await message.answer(get_text(lang, 'access_denied'))
        return
    
    await message.answer("📢 Функция рассылки в разработке")

@dp.message(F.text == "⚙️ Настройки")
async def admin_settings(message: types.Message):
    lang = 'ru'
    if not db.is_admin(message.from_user.id):
        await message.answer(get_text(lang, 'access_denied'))
        return
    
    await message.answer("⚙️ Настройки админа в разработке")

# ============== ОТЛАДКА - НЕИЗВЕСТНЫЕ СООБЩЕНИЯ ==============

@dp.message(F.text)
async def unknown_message_debug(message: types.Message):
    """Отладочный обработчик для неизвестных текстовых сообщений"""
    print(f"⚠️ НЕИЗВЕСТНОЕ СООБЩЕНИЕ от {message.from_user.id}: '{message.text}'")
    print(f"   Длина текста: {len(message.text)}")
    print(f"   Байты: {message.text.encode('utf-8')}")

# ============== ЗАПУСК БОТА ==============

# ============================================
# ФОНОВАЯ ЗАДАЧА - УДАЛЕНИЕ ИСТЕКШИХ ТОВАРОВ
# ============================================

async def cleanup_expired_offers():
    """Фоновая задача для удаления истекших предложений"""
    while True:
        try:
            await asyncio.sleep(300)  # Проверяем каждые 5 минут (300 секунд)
            deleted_count = db.delete_expired_offers()
            if deleted_count > 0:
                print(f"🗑 Удалено истекших предложений: {deleted_count}")
        except Exception as e:
            print(f"⚠️ Ошибка при очистке истекших товаров: {e}")

# ============================================
# ЗАПУСК БОТА
# ============================================

async def main():
    print("✅ Бот успешно запущен!")
    print("⚠️ Нажмите Ctrl+C для остановки")
    print("=" * 50)
    
    # Запускаем фоновую задачу очистки
    cleanup_task = asyncio.create_task(cleanup_expired_offers())
    
    try:
        # Запускаем polling с правильными параметрами
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True  # Игнорируем старые обновления
        )
    except asyncio.CancelledError:
        print("\n⏸ Получен сигнал отмены...")
    except KeyboardInterrupt:
        print("\n⛔ Бот остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {type(e).__name__}: {e}")
    finally:
        # Отменяем фоновую задачу
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        print("\n🔄 Завершение работы бота...")
        await bot.session.close()
        print("✅ Бот остановлен корректно")

# ============================================
# ЗАЩИТА ОТ МНОЖЕСТВЕННОГО ЗАПУСКА
# ============================================

def is_bot_already_running(port=8444):
    """Проверяет, не запущен ли уже бот на этом порту"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', port))
        sock.close()
        return False
    except OSError:
        print(f"🛑 ОШИБКА: Бот уже запущен на порту {port}!")
        print("⚠️ Остановите другой экземпляр перед запуском нового.")
        return True

# Глобальная переменная для graceful shutdown
shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    """Обработчик сигнала завершения (Ctrl+C)"""
    print("\n🛑 Получен сигнал завершения...")
    shutdown_event.set()

if __name__ == "__main__":
    # Проверяем, не запущен ли бот уже
    if is_bot_already_running():
        print("❌ Завершение работы дубликата...")
        sys.exit(1)
    
    print("=" * 50)
    print("🚀 Запуск бота Fudly (Production Optimized)...")
    print("=" * 50)
    print(f"📊 База данных: {db.db_name}")
    if ADMIN_ID > 0:
        print(f"👑 Главный админ: {ADMIN_ID}")
    print(f"🔒 Порт блокировки: 8444")
    print(f"🌍 Языки: Русский, Узбекский")
    print(f"📸 Поддержка фото: Да")
    print(f"⚡ Оптимизация: Пулинг соединений, кэширование, безопасность")
    print("=" * 50)
    
    # Start background tasks for cleanup and maintenance
    if PRODUCTION_FEATURES:
        logger.info("Starting background tasks...")
        start_background_tasks(db)
        print("✅ Background tasks started")
    else:
        print("⚠️ Running in basic mode (production features disabled)")
    
    # Устанавливаем обработчик сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("Bot starting...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        print("\n👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        print(f"\n❌ Ошибка: {e}")
    finally:
        logger.info("Bot shutdown complete")
