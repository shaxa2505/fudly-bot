from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from localization import get_text, LANGUAGES

# Список городов Узбекистана
CITIES_RU = ["Ташкент", "Самарканд", "Бухара", "Андижан", "Наманган", "Фергана", "Хива", "Нукус"]
CITIES_UZ = ["Toshkent", "Samarqand", "Buxoro", "Andijon", "Namangan", "Farg'ona", "Xiva", "Nukus"]

# Категории заведений
CATEGORIES_RU = ["Ресторан", "Кафе", "Пекарня", "Супермаркет", "Кондитерская", "Фастфуд"]
CATEGORIES_UZ = ["Restoran", "Kafe", "Nonvoyxona", "Supermarket", "Qandolatxona", "Fastfud"]

def get_cities(lang: str) -> list:
    """Получить список городов на нужном языке"""
    return CITIES_UZ if lang == 'uz' else CITIES_RU

def get_categories(lang: str) -> list:
    """Получить список категорий на нужном языке"""
    return CATEGORIES_UZ if lang == 'uz' else CATEGORIES_RU

# ============== ВЫБОР ЯЗЫКА ==============

def language_keyboard():
    """Клавиатура выбора языка"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🇷🇺 Русский", callback_data="lang_ru")
    builder.button(text="🇺🇿 O'zbekcha", callback_data="lang_uz")
    builder.adjust(2)
    return builder.as_markup()

# ============== ОСНОВНЫЕ МЕНЮ ==============

def main_menu_customer(lang: str = 'ru'):
    """Главное меню для покупателя"""
    builder = ReplyKeyboardBuilder()
    builder.button(text=get_text(lang, 'available_offers'))
    builder.button(text=get_text(lang, 'stores'))
    builder.button(text=get_text(lang, 'favorites'))
    builder.button(text=get_text(lang, 'my_city'))
    builder.button(text=get_text(lang, 'my_bookings'))
    builder.button(text=get_text(lang, 'profile'))
    builder.button(text=get_text(lang, 'become_partner'))
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def main_menu_seller(lang: str = 'ru'):
    """Главное меню для продавца"""
    builder = ReplyKeyboardBuilder()
    builder.button(text=get_text(lang, 'add_offer'))
    builder.button(text=get_text(lang, 'bulk_create'))
    builder.button(text=get_text(lang, 'my_stores'))
    builder.button(text=get_text(lang, 'my_offers'))
    builder.button(text=get_text(lang, 'analytics'))
    builder.button(text=get_text(lang, 'store_bookings'))
    builder.button(text=get_text(lang, 'confirm_delivery'))
    builder.button(text=get_text(lang, 'profile'))
    builder.button(text=get_text(lang, 'back_to_customer'))
    builder.adjust(2, 2, 1, 2, 2)
    return builder.as_markup(resize_keyboard=True)

# ============== ВЫБОР ГОРОДА И КАТЕГОРИИ ==============

def city_keyboard(lang: str = 'ru'):
    """Клавиатура выбора города"""
    cities = get_cities(lang)
    builder = ReplyKeyboardBuilder()
    for city in cities:
        builder.button(text=f"📍 {city}")
    builder.button(text=f"❌ {get_text(lang, 'cancel')}")
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def category_keyboard(lang: str = 'ru'):
    """Клавиатура выбора категории"""
    categories = get_categories(lang)
    builder = ReplyKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"🏷 {cat}")
    builder.button(text=f"❌ {get_text(lang, 'cancel')}")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

# ============== INLINE КЛАВИАТУРЫ ==============

def offer_keyboard(offer_id: int, lang: str = 'ru'):
    """Клавиатура для предложения"""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, 'book'), callback_data=f"book_{offer_id}")
    builder.button(text=get_text(lang, 'details'), callback_data=f"details_{offer_id}")
    builder.adjust(1)
    return builder.as_markup()

def offer_manage_keyboard(offer_id: int, lang: str = 'ru'):
    """Клавиатура управления предложением"""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, 'duplicate'), callback_data=f"duplicate_{offer_id}")
    builder.button(text=get_text(lang, 'delete'), callback_data=f"delete_offer_{offer_id}")
    builder.adjust(2)
    return builder.as_markup()

def booking_keyboard(booking_id: int, lang: str = 'ru'):
    """Клавиатура для бронирования"""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, 'cancel_booking'), callback_data=f"cancel_booking_{booking_id}")
    return builder.as_markup()

def rate_keyboard(booking_id: int):
    """Клавиатура для оценки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐⭐⭐⭐⭐", callback_data=f"rate_{booking_id}_5")
    builder.button(text="⭐⭐⭐⭐", callback_data=f"rate_{booking_id}_4")
    builder.button(text="⭐⭐⭐", callback_data=f"rate_{booking_id}_3")
    builder.button(text="⭐⭐", callback_data=f"rate_{booking_id}_2")
    builder.button(text="⭐", callback_data=f"rate_{booking_id}_1")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def stores_list_keyboard(stores, lang: str = 'ru'):
    """Клавиатура списка магазинов"""
    builder = InlineKeyboardBuilder()
    for store in stores[:10]:
        builder.button(
            text=f"🏪 {store[2]} - 📍 {store[3]}", 
            callback_data=f"filter_store_{store[0]}"
        )
    builder.button(text=f"🔄 {get_text(lang, 'available_offers')}", callback_data="filter_all")
    builder.adjust(1)
    return builder.as_markup()

def phone_request_keyboard(lang: str = 'ru'):
    """Клавиатура запроса телефона"""
    builder = ReplyKeyboardBuilder()
    builder.button(text=f"📱 {get_text(lang, 'share_phone')}", request_contact=True)
    builder.button(text=f"❌ {get_text(lang, 'cancel')}")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def cancel_keyboard(lang: str = 'ru'):
    """Клавиатура отмены"""
    builder = ReplyKeyboardBuilder()
    builder.button(text=f"❌ {get_text(lang, 'cancel')}")
    return builder.as_markup(resize_keyboard=True)

# ============== АДМИН ПАНЕЛЬ ==============

def admin_menu(lang: str = 'ru'):
    """Меню администратора"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📊 Статистика")
    builder.button(text="📈 Полная статистика")
    builder.button(text="👥 Пользователи")
    builder.button(text="🏪 Заявки на партнерство")
    builder.button(text="🏪 Все магазины")
    builder.button(text="📋 Все предложения")
    builder.button(text="📢 Рассылка")
    builder.button(text="⚙️ Настройки")
    builder.button(text="🔙 Выход из админки")
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def moderation_keyboard(store_id: int):
    """Кнопки модерации магазина"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"approve_store_{store_id}")
    builder.button(text="❌ Отклонить", callback_data=f"reject_store_{store_id}")
    builder.adjust(2)
    return builder.as_markup()

def settings_keyboard(notifications_enabled: bool, lang: str = 'ru'):
    """Кнопки настроек пользователя"""
    notif_text = "🔔 Откл. уведомления" if notifications_enabled else "🔕 Вкл. уведомления"
    builder = InlineKeyboardBuilder()
    builder.button(text=notif_text, callback_data="toggle_notifications")
    builder.button(text=get_text(lang, 'change_language'), callback_data="change_language")
    builder.button(text="🗑 Удалить аккаунт", callback_data="delete_account")
    builder.adjust(1)
    return builder.as_markup()

def store_keyboard(store_id: int):
    """Кнопки управления магазином"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data=f"store_stats_{store_id}")
    builder.button(text="📋 Предложения", callback_data=f"show_offers_{store_id}")
    builder.adjust(2)
    return builder.as_markup()

# ============== ЕДИНИЦЫ ИЗМЕРЕНИЯ ==============

def units_keyboard(lang: str = 'ru'):
    """Клавиатура выбора единиц измерения"""
    builder = ReplyKeyboardBuilder()
    units = ['шт', 'кг', 'г', 'л', 'мл', 'упак', 'м', 'см']
    for unit in units:
        builder.button(text=unit)
    builder.adjust(4, 4)  # 4 кнопки в первом ряду, 4 во втором
    return builder.as_markup(resize_keyboard=True)

# ============== КАТЕГОРИИ ТОВАРОВ ==============

def product_categories_keyboard(lang: str = 'ru'):
    """Клавиатура выбора категорий товаров для супермаркетов"""
    builder = ReplyKeyboardBuilder()
    
    categories_ru = [
        '🍞 Хлеб и выпечка', '🥛 Молочные продукты', '🥩 Мясо и птица', 
        '🐟 Рыба и морепродукты', '🥬 Овощи', '🍎 Фрукты и ягоды',
        '🧀 Сыры', '🥚 Яйца', '🍚 Крупы и макароны', '🥫 Консервы',
        '🍫 Кондитерские изделия', '🍪 Печенье и снэки', '☕ Чай и кофе', 
        '🥤 Напитки', '🧴 Бытовая химия', '🧼 Гигиена', '🏠 Для дома', '🎯 Другое'
    ]
    
    categories_uz = [
        '🍞 Non va pishiriq', '🥛 Sut mahsulotlari', '🥩 Go\'sht va parrandalar', 
        '🐟 Baliq va dengiz mahsulotlari', '🥬 Sabzavotlar', '🍎 Mevalar va rezavorlar',
        '🧀 Pishloqlar', '🥚 Tuxum', '🍚 Yorma va makaron', '🥫 Konservalar',
        '🍫 Qandolat mahsulotlari', '🍪 Pechene va sneklar', '☕ Choy va qahva', 
        '🥤 Ichimliklar', '🧴 Maishiy kimyo', '🧼 Gigiyena', '🏠 Uy uchun', '🎯 Boshqa'
    ]
    
    categories = categories_uz if lang == 'uz' else categories_ru
    
    for category in categories:
        builder.button(text=category)
    
    builder.adjust(2, 2, 2, 2, 2, 2, 2, 2, 2)  # По 2 кнопки в ряду
    return builder.as_markup(resize_keyboard=True)

def store_category_selection(lang: str = 'ru'):
    """Inline клавиатура для выбора категории заведения"""
    builder = InlineKeyboardBuilder()
    
    categories = get_categories(lang)
    
    for i, category in enumerate(categories):
        builder.button(text=category, callback_data=f"cat_{i}")
    
    builder.adjust(2)  # 2 кнопки в ряду
    return builder.as_markup()

def store_selection(stores, lang: str = 'ru'):
    """Inline клавиатура для выбора магазина"""
    builder = InlineKeyboardBuilder()
    
    for store in stores[:10]:  # Ограничим 10
        builder.button(text=f"{store[1]} ({store[3]})", callback_data=f"store_{store[0]}")
    
    builder.button(text=get_text(lang, 'back'), callback_data="back_to_categories")
    builder.adjust(1)
    return builder.as_markup()

def offer_selection(offers, lang: str = 'ru'):
    """Inline клавиатура для выбора предложения"""
    builder = InlineKeyboardBuilder()
    
    for offer in offers[:10]:
        discount_percent = int((1 - offer[5] / offer[4]) * 100) if offer[4] > 0 else 0
        text = f"{offer[2]} (-{discount_percent}%)"
        builder.button(text=text, callback_data=f"offer_{offer[0]}")
    
    builder.button(text=get_text(lang, 'back'), callback_data="back_to_stores")
    builder.adjust(1)
    return builder.as_markup()
