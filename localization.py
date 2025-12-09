# Локализация для бота Fudly

LANGUAGES = {"ru": "🇷🇺 Русский", "uz": "🇺🇿 O'zbekcha"}

TEXTS = {
    "ru": {
        # Приветствие
        "choose_language": "🌍 Выберите язык / Tilni tanlang",
        "language_changed": "✅ Язык изменён на Русский",
        "welcome": """🛍 <b>Fudly — спасаем еду от выброса!</b>

Покупайте товары с истекающим сроком годности
со скидкой <b>до 70%</b>

✅ <b>Безопасно</b> — товары свежие
✅ <b>Выгодно</b> — скидки до 70%
✅ <b>Полезно</b> — меньше отходов

🔥 Более 100 магазинов в вашем городе""",
        "welcome_phone_step": """📱 <b>Укажите номер телефона</b>

Это нужно чтобы:
• Магазин мог связаться с вами
• Вы получали уведомления о заказах

👇 Нажмите кнопку ниже""",
        "welcome_city_step": """📍 <b>Выберите ваш город</b>

Мы покажем магазины и предложения рядом с вами

👇 Выберите из списка""",
        "registration_complete": """🎉 <b>Готово! Добро пожаловать!</b>

Теперь вы можете:
🔥 <b>Акции</b> — скидки до 70% каждый день
🏪 <b>Заведения</b> — все магазины города
🔍 <b>Поиск</b> — найти нужный товар

💡 Совет: проверяйте "Акции" каждый день — товары обновляются!""",
        "welcome_back": """👋 <b>Привет, {name}!</b>

📍 Город: {city}""",
        "registration_required": """⚠️ <b>Нужна регистрация</b>

Нажмите /start чтобы начать""",
        # Кнопки
        "share_phone": "📱 Поделиться номером",
        "cancel": "❌ Отмена",
        "hot_offers": "🏪 Магазины и акции",
        "browse_places": "Места",
        "my_cart": "🛒 Корзина",
        "my_orders": "📋 Заказы и бронирования",
        "available_offers": "Доступные предложения",
        "my_bookings": "Мои бронирования",
        "stores": "Все магазины",
        "favorites": "❤️ Избранное",
        "my_city": "🌆 Мой город",
        "profile": "👤 Профиль",
        "become_partner": "🏪 Стать партнером",
        "establishments": "🏪 Заведения",
        "search": "🔍 Поиск",
        "help": "❓ Как это работает",
        "enter_search_query": "🔍 Что ищете?",
        "search_results": "🔍 Результаты",
        "no_results": "😔 Ничего не найдено",
        "action_cancelled": "❌ Отменено",
        "select_category_in_store": "Выберите категорию в этом заведении:",
        # Партнёр - новые короткие названия
        "add_item": "➕ Добавить",
        "my_items": "📦 Мои товары",
        "orders": "🎫 Заказы продавца",
        "today_stats": "📊 Сегодня",
        "bulk_import": "📥 Массовый импорт",
        "store_settings": "⚙️ Настройки",
        "back_to_customer": "🛒 Режим покупателя",
        # Старые ключи (для совместимости)
        "add_offer": "➕ Добавить",
        "my_offers": "📋 Мои товары",
        "store_bookings": "Заказы",
        "notifications": "Уведомления",
        "settings": "Настройки",
        # Профиль
        "your_profile": "<b>Ваш профиль</b>",
        "name": "Имя",
        "phone": "Телефон",
        "city": "Город",
        "language": "Язык",
        "role": "Роль",
        "role_seller": "Партнёр",
        "role_customer": "Покупатель",
        "switched_to_customer": "Переключено в режим покупателя",
        "switched_to_seller": "Переключено в режим партнёра",
        # Города
        "your_city": "Ваш город",
        "choose_city": "<b>Выберите ваш город:</b>",
        "city_changed": "Город изменён на {city}",
        # Предложения
        "no_offers": "😔 Пока нет доступных предложений в вашем городе",
        "no_offers_in_store": "😔 В этом магазине пока нет предложений",
        "offers_in_city": "🍽 <b>Доступные предложения в городе {city}</b>\n\nВсего: {count}",
        "offers_found": "🍽 <b>Доступные предложения</b>\n\nНайдено: {count}",
        "hot_offers_title": "🔥 <b>АКЦИИ ДО -70%</b>",
        "hot_offers_subtitle": "Свежие товары со скидками — обновляется каждый день!",
        "select_by_number": "Введите номер товара для просмотра:",
        "browse_by_business_type": "🏪 <b>Выберите тип заведения:</b>",
        "supermarkets": "🛒 Супермаркеты",
        "restaurants": "🍽 Рестораны",
        "bakeries": "🥖 Пекарни",
        "cafes": "☕️ Кафе",
        "pharmacies": "💊 Аптеки",
        "all_offers": "Все предложения",
        "no_active_offers": "Нет активных предложений",
        "choose_category": "🏪 Выберите категорию заведения:",
        "choose_store": "🏪 Выберите магазин:",
        "choose_offer": "🍽 Выберите предложение:",
        "back": "🔙 Назад",
        "book": "Заказать",
        "details": "ℹ️ Подробнее",
        "discount": "Скидка",
        "available": "Доступно",
        "time": "Время",
        "address": "Адрес",
        "currency": "сум",
        "unit": "шт",
        "expires_on": "Годен до",
        # Help and FAQ
        "help_customer": """❓ <b>Как работает Fudly?</b>

<b>🔥 Акции</b>
Товары с самыми большими скидками (30-70%)
Обновляется каждый день!

<b>🏪 Магазины</b>
1️⃣ Выберите магазин в вашем городе
2️⃣ Посмотрите категории товаров
3️⃣ Выберите товар и забронируйте

<b>🔍 Поиск</b>
Найдите товар по названию
Пример: йогурт, хлеб, молоко

<b>📦 Как забронировать:</b>
1️⃣ Нажмите на товар
2️⃣ Выберите количество
3️⃣ Получите 8-значный код
4️⃣ Покажите код продавцу

<b>📱 Статусы заказа:</b>
⏳ <b>Ожидает</b> - магазин проверяет заказ
✅ <b>Готов</b> - приезжайте забрать товар
🎉 <b>Завершён</b> - вы получили товар
❌ <b>Отменён</b> - заказ отменён

<b>💡 Советы:</b>
• Проверяйте раздел "Акции" каждый день
• Забирайте товар в указанное время
• Оценивайте магазины после покупки""",
        "help_partner": """❓ <b>Как работать партнёром?</b>

<b>➕ Добавление товаров:</b>
1️⃣ Нажмите "Добавить товар"
2️⃣ Укажите название, фото, цены
3️⃣ Категория определится автоматически
4️⃣ Товар сразу появится у покупателей

<b>📦 Ваши товары</b>
Просмотр всех ваших товаров
Можно редактировать или удалить

<b>🎫 Заказы продавца:</b>
⏳ <b>Новые</b> - покупатель забронировал товар
   → Подтвердите заказ (кнопка ✅)

✅ <b>Подтверждённые</b> - покупатель придёт забрать
   → Попросите 8-значный код
   → Выдайте товар и завершите заказ

🎉 <b>Завершённые</b> - товар выдан, деньги получены

❌ <b>Отменённые</b> - заказ не состоялся

<b>📊 Статистика:</b>
• Сколько товаров продано
• Какие товары популярны
• Средний чек

<b>💡 Советы для роста продаж:</b>
• Делайте скидки 30-70%
• Загружайте качественные фото
• Обновляйте товары каждый день
• Быстро подтверждайте заказы
• Указывайте точное время забора""",
        # Бронирование
        "booking_step_quantity": """┏━━━━━━━━━━━━━━━━━━━━━┓
┃   БРОНИРОВАНИЕ        ┃
┗━━━━━━━━━━━━━━━━━━━━━┛

📦 <b>{title}</b>
🏪 {store_name}

💰 Цена: <b>{price:,} сум</b> за 1 {unit}
📋 Доступно: <b>{quantity}</b> {unit}

💡 Введите число от 1 до {quantity}

<i>Например: 2</i>""",
        "booking_confirm": """┏━━━━━━━━━━━━━━━━━━━━━┓
┃   ПОДТВЕРЖДЕНИЕ       ┃
┗━━━━━━━━━━━━━━━━━━━━━┛

📦 <b>{title}</b>
🏪 {store_name}
📍 {address}

━━━━━━━━━━━━━━━━━━━━━
📊 Количество: <b>{quantity}</b> {unit}
💰 К оплате: <b>{total:,} сум</b>
━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 2 из 2: Подтвердите заказ</b>

✓ Резервируем товар для вас
✓ Вы получите код для получения
✓ Оплата при получении

<i>Нажмите "Подтвердить" ниже</i> 👇""",
        "booking_success": """🎉 <b>Бронирование успешно!</b>

🏪 {store_name}
🍽 {offer_name}
💰 К оплате: {price} сум

📍 Адрес: {city}, {address}
🕐 Забрать до: {time}

🎫 Код бронирования: <code>{code}</code>

⚠️ Покажите этот код при получении заказа!""",
        "my_bookings_empty": "У вас пока нет заказов.\n\nПопробуйте раздел 🔥 Акции!",
        "no_active_bookings": "Нет активных бронирований",
        "no_completed_bookings": "Нет завершённых бронирований",
        "no_cancelled_bookings": "Нет отменённых бронирований",
        "active_bookings": "<b>Ваши активные заказы</b>\n\nВсего: {count}",
        "cancel_booking": "Отменить заказ",
        "booking_cancelled": "Заказ отменён",
        "insufficient_stock": "× К сожалению, выбранное количество уже недоступно. Обновите список предложений.",
        "error_qty_gt_zero": "× Количество должно быть больше 0",
        "error_price_gt_zero": "× Цена должна быть больше 0",
        "error_price_too_high": "× Слишком большая цена",
        "error_discount_less_than_original": "× Цена со скидкой должна быть меньше обычной цены",
        "warn_discount_low": "⚠️ Внимание: скидка меньше 10%. Рекомендуем делать скидку от 30% для привлечения клиентов.",
        "booking_how_many": "Сколько вы хотите забронировать? (1-{max_qty})",
        # Партнёр
        "become_partner_text": """🏪 <b>Стать партнёром Fudly</b>

💰 Предлагайте товары со скидкой и находите новых клиентов
🌱 Снижайте потери и заботьтесь об экологии

┏━━━━━━━━━━━━━━━━━━━━━━━━┏
┃ Шаг 1/5: Город 🏙     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┗

Выберите город, где находится ваше заведение:""",
        "store_name": '''┏━━━━━━━━━━━━━━━━━━━━━━━━┏
┃ Шаг 3/5: Название 🏪 ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┗

Введите название вашего заведения:

💡 Пример: "Пекарня Хлеб и Соль"''',
        "store_category": """┏━━━━━━━━━━━━━━━━━━━━━━━━┏
┃ Шаг 2/5: Категория 🏷 ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┗

Выберите тип вашего заведения:""",
        "store_address": '''┏━━━━━━━━━━━━━━━━━━━━━━━━┏
┃ Шаг 4/5: Адрес 📍   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┗

Введите адрес заведения:

💡 Пример: "ул. Амира Темура, 12"''',
        "store_description": '''┏━━━━━━━━━━━━━━━━━━━━━━━━┏
┃ Шаг 5/5: Описание 📝 ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┗

Опишите ваше заведение и ассортимент:

💡 Пример: "Свежая выпечка ежедневно. Хлеб, булочки, торты"''',
        "store_phone": "Введите контактный телефон:",
        "store_registered": """✅ <b>Заявка отправлена!</b>

🏪 {name}
📍 {city}, {address}
🏷 {category}
📝 {description}
📞 {phone}

⏳ Ожидайте одобрения администратором.
Вы получите уведомление о решении!""",
        "store_pending": """✅ <b>Заявка отправлена на модерацию!</b>

🏪 {name}
📍 {city}, {address}
🏷 {category}
📝 {description}
📞 {phone}

⏳ Ожидайте одобрения администратором.
Обычно это занимает не более 24 часов.""",
        "store_approved": """🎉 <b>Поздравляем! Ваш магазин одобрен!</b>

Теперь вы официальный партнёр Fudly!

<b>🚀 С чего начать:</b>
1️⃣ Добавьте первый товар (кнопка «➕ Добавить»)
2️⃣ Установите скидку 30-70% — это привлекает покупателей
3️⃣ Загрузите фото — товары с фото продаются в 3 раза лучше!

<b>💡 Совет:</b> Начните с 3-5 товаров и смотрите что лучше продаётся.

Желаем успешных продаж! 🎉""",
        "store_rejected": """❌ <b>Заявка отклонена</b>

К сожалению, ваша заявка не была одобрена.

Вы можете подать новую заявку с исправленными данными.""",
        # Создание предложения
        "choose_product_category": "🏷 Выберите категорию продукта:",
        "choose_unit": "📏 Выберите единицу измерения:",
        "offer_title": "Введите название предложения:",
        "offer_description": "📝 Введите описание предложения:",
        "original_price": "💰 Введите обычную цену (в сумах):",
        "discount_price": "💸 Введите цену со скидкой (в сумах):",
        "quantity": "📦 Введите количество порций:",
        "time_from": "🕐 Введите время начала (например: 18:00):",
        "expiry_date": "📅 Введите срок годности (например: 31.12.2025):",
        "time_until": "🕐 Введите время окончания забора (например: 21:00):",
        "offer_created": """✅ <b>Предложение создано!</b>

🍽 {title}
📝 {description}
💰 {original_price} ➜ {discount_price} сум (-{discount}%)
📦 Количество: {quantity}
🕐 {time_from} - {time_until}

Предложение теперь доступно для покупателей!""",
        # Массовое создание
        "bulk_create_start": """📦 <b>Массовое создание предложений</b>

🏪 Магазин: {store_name}

Эта функция позволит создать несколько одинаковых предложений за один раз.
Например: 50 наборов "Завтрак" с одинаковой ценой и временем.

Введите название предложения:""",
        "bulk_count": """🔢 <b>Сколько таких предложений создать?</b>

Введите количество (от 1 до 100):""",
        "bulk_created": """✅ <b>Массовое создание завершено!</b>

📦 Создано предложений: {count}

🍽 {title}
📝 {description}
💰 {original_price} ➜ {discount_price} сум (-{discount}%)
📦 Порций в каждом: {quantity}
📊 Всего порций: {total_quantity}
🕐 {time_from} - {time_until}

Все предложения доступны для покупателей!""",
        # Подтверждение выдачи
        "confirm_delivery_prompt": "✅ <b>Подтверждение выдачи заказа</b>\n\nВведите 8-значный код бронирования:",
        "booking_not_found": "❌ Бронирование с таким кодом не найдено",
        "order_confirmed": """✅ <b>Заказ подтверждён!</b>

Бронирование #{booking_id} завершено
Клиент: {customer_name}
Сумма: {price} сум

Клиент получит уведомление с просьбой оценить ваш магазин.""",
        # Рейтинг
        "rate_store": "⭐ <b>Оцените магазин</b>\n\n🏪 {store_name}\n\nКак вам понравилось?",
        "rating_saved": "✅ <b>Спасибо за оценку!</b>\n\nВаш отзыв поможет другим покупателям!",
        "already_rated": "Вы уже оценили этот заказ",
        # Статистика
        "store_stats": """🏪 <b>{name}</b>
🏷 {category}
📍 {city}, {address}
📝 {description}

⭐ Рейтинг: {rating}/5 ({reviews} отзывов)
📊 Продано: {sales} заказов
💰 Доход: {revenue:,} сум
📦 Активных броней: {pending}""",
        # Ошибки
        "error_invalid_number": "❌ Пожалуйста, введите корректное число",
        "error_invalid_time": "❌ Неверный формат времени. Используйте формат ЧЧ:ММ (например: 18:00)",
        "no_stores": "❌ У вас нет одобренных магазинов!",
        "no_approved_stores": "❌ У вас нет одобренных магазинов!\n\n⏳ Дождитесь одобрения вашей заявки администратором.",
        "operation_cancelled": "❌ Операция отменена",
        "no_admin_access": "❌ У вас нет доступа к админ панели",
        "send_photo": '📸 Отправьте фото блюда (или напишите "пропустить")',
        "invalid_range": "❌ От 1 до 100",
        "no_offers_yet": "📊 Пока нет предложений",
        "your_offers": "📊 Ваши предложения ({count}):",
        "no_stores_in_city": "😔 В городе {city} пока нет магазинов",
        "stores_in_city": "🏪 <b>Магазины в городе {city}</b>\n\nВсего: {count}",
        "your_stores": "🏪 Ваши магазины ({count}):",
        "access_denied": "❌ Доступ запрещён",
        "no_pending_stores": "✅ Нет заявок на модерации",
        "pending_stores_count": "⏳ Заявок на модерации: {count}",
        "store_approved_admin": "✅ Магазин одобрен!",
        "store_rejected_admin": "✅ Магазин отклонён!",
        # Избранное
        "no_favorites": "😔 У вас пока нет избранных магазинов\n\nДобавьте магазины в избранное, чтобы быстро находить их!",
        "already_in_favorites": "❤️ Уже в избранном!",
        "added_to_favorites": "✅ Добавлено в избранное!",
        "removed_from_favorites": "💔 Удалено из избранного",
        # Аналитика
        "not_seller": "❌ Эта функция доступна только партнёрам",
        "select_store_for_analytics": "📊 Выберите магазин для просмотра аналитики:",
        # Прочее
        "duplicate": "📋 Дублировать",
        "delete": "❌ Удалить",
        "duplicated": "✅ Предложение продублировано!",
        "deleted": "✅ Предложение удалено",
        "change_language": "Изменить язык",
        "delete_account": "Удалить аккаунт",
        # Настройки
        "notifications_enabled": "Уведомления: Вкл",
        "notifications_disabled": "Уведомления: Выкл",
        "confirm_delete_account": """⚠ <b>Удаление аккаунта</b>

Вы уверены что хотите удалить свой аккаунт?

Будут удалены:
• Все ваши данные
• Ваши магазины
• Все предложения
• История бронирований

Это действие необратимо!""",
        "account_deleted": "✅ Ваш аккаунт успешно удалён",
        "yes_delete": "✅ Да, удалить",
        "no_cancel": "❌ Нет, отменить",
        "store_deleted": "✅ Магазин успешно удалён",
        "error_general": "❌ Произошла ошибка. Попробуйте позже.",
        "system_error": "⚠️ Системная ошибка. Попробуйте позже или напишите в поддержку.",
        # Улучшенные пустые состояния
        "cart_empty": """🛒 <b>Корзина пуста</b>

Найдите что-нибудь вкусное со скидкой до 70%!

💡 Совет: загляните в раздел «🔥 Акции»""",
        "cart_empty_cta": "🔥 Смотреть предложения",
        # Навигация
        "go_back": "◀️ Назад",
        "continue_shopping": "🔙 Продолжить покупки",
        # Кнопки количества
        "qty_select": "📦 Выберите количество:",
        "qty_custom": "✏️ Другое",
        "qty_enter_custom": "Введите количество (от 1 до {max}):",
        # Улучшенные ошибки с подсказками
        "error_qty_invalid": """❌ <b>Неверное количество</b>

Доступно: {available} шт
Попробуйте: 1, 2 или {max}""",
        "error_qty_exceeded": """❌ <b>Слишком много</b>

Максимум: {max} шт
Введите число от 1 до {max}""",
        # Quick actions
        "add_to_cart": "🛒 В корзину",
        "buy_now": "⚡ Купить сейчас",
        "added_to_cart": "✅ Добавлено в корзину!",
        # Партнёрский онбординг
        "partner_welcome": """🎉 <b>Добро пожаловать, партнёр!</b>

Ваш магазин одобрен и готов к работе.

<b>Начните прямо сейчас:</b>
1️⃣ Добавьте первый товар
2️⃣ Установите скидку 30-70%
3️⃣ Получайте заказы!

💡 Совет: товары с фото продаются в 3 раза лучше""",
        "partner_add_first": "➕ Добавить первый товар",
        # Хардкод-тексты которые нужно было перевести
        "offer_not_found": "❌ Товар не найден",
        "not_your_offer": "❌ Это не ваш товар",
        "edit_unavailable": "📝 Редактирование товара временно недоступно",
        "main_menu": "🏠 Главное меню",
        "time_edit_title": "🕐 Изменение времени забора",
        "time_edit_prompt": "Введите новое время начала (например: 18:00):",
        "time_end_prompt": "Введите время окончания (например: 21:00):",
        "time_updated": "✅ Время забора обновлено!",
        "title_saved": "✅ Название сохранено",
        "send_photo_now": "📸 Теперь отправьте фото товара или нажмите кнопку",
        "without_photo": "📝 Без фото",
        "user_not_found": "Ошибка: пользователь не найден",
        # Валидация/лимиты
        "invalid_city": "Пожалуйста, выберите город из списка.",
        "rate_limit_exceeded": "Слишком много запросов. Попробуйте позже.",
    },
    "uz": {
        # Salomlashish
        "choose_language": "🌍 Выберите язык / Tilni tanlang",
        "language_changed": "✅ Til O'zbekchaga o'zgartirildi",
        "welcome": """🛍 <b>Fudly — oziq-ovqatni isrofdan saqlaymiz!</b>

Muddati tugash arafasidagi mahsulotlarni
<b>70% gacha</b> chegirma bilan sotib oling

✅ <b>Xavfsiz</b> — mahsulotlar yangi
✅ <b>Foydali</b> — 70% gacha chegirma
✅ <b>Ekologik</b> — kamroq isrof

🔥 Shahringizda 100 dan ortiq do'konlar""",
        "welcome_phone_step": """📱 <b>Telefon raqamingizni kiriting</b>

Bu nima uchun kerak:
• Do'kon siz bilan bog'lanishi uchun
• Buyurtma haqida xabar olish uchun

👇 Quyidagi tugmani bosing""",
        "welcome_city_step": """📍 <b>Shahringizni tanlang</b>

Yaqin atrofdagi do'konlarni ko'rsatamiz

👇 Ro'yxatdan tanlang""",
        "registration_complete": """🎉 <b>Tayyor! Xush kelibsiz!</b>

Endi siz:
🔥 <b>Aksiyalar</b> — har kuni 70% gacha chegirmalar
🏪 <b>Do'konlar</b> — shahardagi barcha do'konlar
🔍 <b>Qidirish</b> — kerakli mahsulotni topish

💡 Maslahat: har kuni "Aksiyalar" bo'limini tekshiring — mahsulotlar yangilanadi!""",
        "welcome_back": """👋 <b>Salom, {name}!</b>

📍 Shahar: {city}""",
        "registration_required": """⚠️ <b>Ro'yxatdan o'tish kerak</b>

Boshlash uchun /start bosing""",
        # Tugmalar
        "share_phone": "📱 Raqamni ulashish",
        "cancel": "❌ Bekor qilish",
        "hot_offers": "🏪 Do'konlar va aksiyalar",
        "browse_places": "🏪 Joylar",
        "my_cart": "🛒 Savat",
        "my_orders": "📋 Buyurtmalar va bronlar",
        "available_offers": "🍽 Mavjud takliflar",
        "my_bookings": "📋 Mening buyurtmalarim",
        "stores": "🏪 Barcha do'konlar",
        "favorites": "❤️ Sevimlilar",
        "my_city": "Mening shahrim",
        "your_city": "Sizning shahringiz",
        "profile": "👤 Profil",
        "become_partner": "🏪 Hamkor bo'lish",
        "establishments": "🏪 Do'konlar",
        "search": "🔍 Qidirish",
        "help": "❓ Qanday ishlaydi",
        "enter_search_query": "🔍 Nimani qidiryapsiz?",
        "search_results": "🔍 <b>Qidiruv natijalari</b>",
        "no_results": "😔 Hech narsa topilmadi\n\nBoshqa so'rov bilan sinab ko'ring yoki Aksiyalar bo'limiga qarang",
        "action_cancelled": "❌ Amal bekor qilindi",
        "select_category_in_store": "Ushbu muassasada toifani tanlang:",
        # Hamkor - yangi qisqa nomlar
        "add_item": "➕ Qo'shish",
        "my_items": "📦 Mening mahsulotlarim",
        "orders": "🎫 Buyurtmalar (sotuvchi)",
        "today_stats": "📊 Bugun",
        "bulk_import": "📦 Ommaviy import",
        "store_settings": "⚙️ Sozlamalar",
        "back_to_customer": "🔙 Xaridor rejimi",
        # Eski kalitlar (muvofiqligi uchun)
        "add_offer": "➕ Qo'shish",
        "my_offers": "📦 Mening mahsulotlarim",
        "store_bookings": "🎫 Buyurtmalar",
        "notifications": "🔔 Bildirishnomalar",
        "settings": "⚙️ Sozlamalar",
        # Profil
        "choose_unit": "📏 O‘lchov birliklarini tanlang:",
        "choose_product_category": "🏷 Mahsulot kategoriyasini tanlang:",
        "your_profile": "👤 <b>Sizning profilingiz</b>",
        "name": "📝 Ism",
        "phone": "📱 Telefon",
        "city": "📍 Shahar",
        "language": "🌍 Til",
        "role": "👔 Rol",
        "role_seller": "Hamkor",
        "role_customer": "Xaridor",
        "switched_to_customer": "🔄 Xaridor rejimiga o'girildi",
        "switched_to_seller": "🔄 Hamkor rejimiga o'girildi",
        # Shaharlar - your_city defined earlier at line 501
        "choose_city": "🌆 <b>Shahringizni tanlang:</b>",
        "city_changed": "✅ Shahar {city}ga o'zgartirildi",
        # Takliflar
        "no_offers": "😔 Hozircha sizning shahringizda takliflar yo'q",
        "no_offers_in_store": "😔 Bu do'konda hali takliflar yo'q",
        "offers_in_city": "🍽 <b>{city} shahridagi mavjud takliflar</b>\n\nJami: {count}",
        "offers_found": "🍽 <b>Mavjud takliflar</b>\n\nTopildi: {count}",
        "hot_offers_title": "🔥 <b>-70% GACHA AKSIYALAR</b>",
        "hot_offers_subtitle": "Chegirmali yangi mahsulotlar — har kuni yangilanadi!",
        "select_by_number": "Mahsulot raqamini kiriting:",
        "browse_by_business_type": "🏪 <b>Muassasa turini tanlang:</b>",
        "supermarkets": "🛒 Supermarketlar",
        "restaurants": "🍽 Restoranlar",
        "bakeries": "🥖 Novvoyxonalar",
        "cafes": "☕️ Kafelar",
        "pharmacies": "💊 Dorixonalar",
        "all_offers": "Barcha takliflar",
        "no_active_offers": "Faol takliflar yo'q",
        "choose_category": "🏪 Kategoriyani tanlang:",
        "choose_store": "🏪 Do'konni tanlang:",
        "choose_offer": "🍽 Taklifni tanlang:",
        "back": "🔙 Orqaga",
        "book": "✅ Buyurtma qilish",
        "details": "ℹ️ Batafsil",
        "discount": "Chegirma",
        "available": "Mavjud",
        "time": "Vaqt",
        "address": "Manzil",
        "currency": "so'm",
        "unit": "dona",
        "expires_on": "Yaroqlilik muddati",
        # Help and FAQ
        "help_customer": """❓ <b>Fudly qanday ishlaydi?</b>

<b>🔥 Aksiyalar</b>
Eng katta chegirmali mahsulotlar (30-70%)
Har kuni yangilanadi!

<b>🏪 Do'konlar</b>
1️⃣ Shahringizdagi do'konni tanlang
2️⃣ Mahsulot kategoriyalarini ko'ring
3️⃣ Mahsulotni tanlang va bron qiling

<b>🔍 Qidirish</b>
Mahsulotni nomi bo'yicha toping
Misol: yogurt, non, sut

<b>📦 Qanday bron qilish:</b>
1️⃣ Mahsulotga bosing
2️⃣ Miqdorini tanlang
3️⃣ 8 raqamli kodni oling
4️⃣ Sotuvchiga kodni ko'rsating

<b>📱 Buyurtma holatlari:</b>
⏳ <b>Kutilmoqda</b> - do'kon buyurtmani tekshirmoqda
✅ <b>Tayyor</b> - kelib mahsulotni oling
🎉 <b>Bajarildi</b> - mahsulotni oldingiz
❌ <b>Bekor qilindi</b> - buyurtma bekor qilindi

<b>💡 Maslahatlar:</b>
• Har kuni "Aksiyalar" bo'limini tekshiring
• Mahsulotni ko'rsatilgan vaqtda oling
• Xariddan keyin do'konni baholang""",
        "help_partner": """❓ <b>Hamkor sifatida qanday ishlash?</b>

<b>➕ Mahsulot qo'shish:</b>
1️⃣ "Mahsulot qo'shish" tugmasini bosing
2️⃣ Nomi, rasm, narxlarni kiriting
3️⃣ Kategoriya avtomatik aniqlanadi
4️⃣ Mahsulot darhol xaridorlarda ko'rinadi

<b>📦 Mening mahsulotlarim</b>
Barcha mahsulotlaringizni ko'ring
Tahrirlash yoki o'chirish mumkin

<b>🎫 Sotuvchi buyurtmalari:</b>
⏳ <b>Yangi</b> - xaridor mahsulotni bron qildi
   → Buyurtmani tasdiqlang (✅ tugma)

✅ <b>Tasdiqlangan</b> - xaridor kelib oladi
   → 8 raqamli kodni so'rang
   → Mahsulotni bering va buyurtmani yakunlang

🎉 <b>Bajarilgan</b> - mahsulot berildi, pul olindi

❌ <b>Bekor qilindi</b> - buyurtma amalga oshmadi

<b>📊 Statistika:</b>
• Qancha mahsulot sotildi
• Qaysi mahsulotlar mashhur
• O'rtacha chek

<b>💡 Sotishni oshirish uchun:</b>
• 30-70% chegirma bering
• Sifatli rasm yuklang
• Har kuni mahsulotlarni yangilang
• Buyurtmalarni tez tasdiqlang
• Olib ketish vaqtini aniq ko'rsating""",
        # Buyurtma
        "booking_success": """✅ <b>Buyurtma muvaffaqiyatli!</b>

🏪 {store_name}
🍽 {offer_name}
💰 To'lash kerak: {price} so'm

📍 Manzil: {city}, {address}
🕐 Olish vaqti: {time}

🎫 Buyurtma kodi: <code>{code}</code>

⚠️ Buyurtmani olishda bu kodni ko'rsating!""",
        "my_bookings_empty": "📋 Sizda hali buyurtmalar yo'q.\n\nTakliflar ro'yxatidan tanlang! 🍽",
        "no_active_bookings": "Faol buyurtmalar yo'q",
        "no_completed_bookings": "Yakunlangan buyurtmalar yo'q",
        "no_cancelled_bookings": "Bekor qilingan buyurtmalar yo'q",
        "active_bookings": "📋 <b>Sizning faol buyurtmalaringiz:</b>\n\nJami: {count}",
        "cancel_booking": "❌ Buyurtmani bekor qilish",
        "booking_cancelled": "✅ Buyurtma bekor qilindi",
        "insufficient_stock": "❌ Afsuski, tanlangan miqdor endi mavjud emas. Takliflar ro‘yxatini yangilang.",
        "error_qty_gt_zero": "❌ Miqdor 0 dan katta bo‘lishi kerak",
        "error_price_gt_zero": "❌ Narx 0 dan katta bo‘lishi kerak",
        "error_price_too_high": "❌ Juda katta narx",
        "error_discount_less_than_original": "❌ Chegirma narxi oddiy narxdan kichik bo‘lishi kerak",
        "warn_discount_low": "⚠️ Diqqat: chegirma 10% dan kichik. Mijozlarni jalb qilish uchun 30% va undan yuqori tavsiya etamiz.",
        "booking_how_many": "Nechta buyurtma qilmoqchisiz? (1-{max_qty})",
        "booking_step_quantity": """┏━━━━━━━━━━━━━━━━━━━━━┓
┃   BUYURTMA BERISH     ┃
┗━━━━━━━━━━━━━━━━━━━━━┛

📦 <b>{title}</b>
🏪 {store_name}

💰 Narx: <b>{price:,} so'm</b> 1 {unit} uchun
📋 Mavjud: <b>{quantity}</b> {unit}

💡 1 dan {quantity} gacha son kiriting

<i>Masalan: 2</i>""",
        "booking_confirm": """┏━━━━━━━━━━━━━━━━━━━━━┓
┃   TASDIQLASH          ┃
┗━━━━━━━━━━━━━━━━━━━━━┛

📦 <b>{title}</b>
🏪 {store_name}
📍 {address}

━━━━━━━━━━━━━━━━━━━━━
📊 Miqdor: <b>{quantity}</b> {unit}
💰 To'lov: <b>{total:,} so'm</b>
━━━━━━━━━━━━━━━━━━━━━

<b>Qadam 2/2: Buyurtmani tasdiqlang</b>

✓ Mahsulotni siz uchun band qilamiz
✓ Olish uchun kod olasiz
✓ To'lov olishda

<i>Quyidagi "Tasdiqlash" tugmasini bosing</i> 👇""",
        # Hamkor
        "become_partner_text": """🏪 <b>Fudly hamkori bo'ling</b>

💰 Chegirmali mahsulotlar taklif qiling va yangi mijozlar toping
🌱 Yo'qotishlarni kamaytiring va ekologiyaga g'amxo'rlik qiling

┏━━━━━━━━━━━━━━━━━━━━━━━━┏
┃ Qadam 1/5: Shahar 🏙    ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┗

Muassasangiz joylashgan shaharni tanlang:""",
        "store_name": '''┏━━━━━━━━━━━━━━━━━━━━━━━━┏
┃ Qadam 3/5: Nomi 🏪    ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┗

Muassasangiz nomini kiriting:

💡 Misol: "Non va Tuz nonvoyxonasi"''',
        "store_category": """┏━━━━━━━━━━━━━━━━━━━━━━━━┏
┃ Qadam 2/5: Kategoriya 🏷 ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┗

Muassasangiz turini tanlang:""",
        "store_address": '''┏━━━━━━━━━━━━━━━━━━━━━━━━┏
┃ Qadam 4/5: Manzil 📍  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┗

Muassasa manzilini kiriting:

💡 Misol: "Amir Temur ko'chasi, 12"''',
        "store_description": '''┏━━━━━━━━━━━━━━━━━━━━━━━━┏
┃ Qadam 5/5: Ta'rif 📝  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┗

Muassasangiz va assortimentini ta'riflang:

💡 Misol: "Har kuni yangi pishirilgan non. Non, bulochka, tortlar"''',
        "store_phone": "Aloqa telefonini kiriting:",
        "store_registered": """✅ <b>Ariza yuborildi!</b>

🏪 {name}
📍 {city}, {address}
🏷 {category}
📝 {description}
📞 {phone}

⏳ Administrator tomonidan tasdiqlanishini kuting.
Qaror haqida xabar olasiz!""",
        "store_pending": """✅ <b>Ariza moderatsiyaga yuborildi!</b>

🏪 {name}
📍 {city}, {address}
🏷 {category}
📝 {description}
📞 {phone}

⏳ Administrator tomonidan tasdiqlanishini kuting.
Odatda bu 24 soatdan ortiq vaqt olmaydi.""",
        "store_approved": """🎉 <b>Tabriklaymiz! Do'koningiz tasdiqlandi!</b>

Endi siz Fudly ning rasmiy hamkorisiz!

<b>🚀 Nimadan boshlash kerak:</b>
1️⃣ Birinchi mahsulotni qo'shing («➕ Qo'shish» tugmasi)
2️⃣ 30-70% chegirma qo'ying — bu xaridorlarni jalb qiladi
3️⃣ Rasm yuklang — rasmli tovarlar 3 baravar yaxshi sotiladi!

<b>💡 Maslahat:</b> 3-5 ta tovar bilan boshlang va qaysi biri yaxshi sotilishini kuzating.

Muvaffaqiyatli savdo tilaymiz! 🎉""",
        "store_rejected": """❌ <b>Ariza rad etildi</b>

Afsuski, arizangiz tasdiqlanmadi.

Tuzatilgan ma'lumotlar bilan yangi ariza topshirishingiz mumkin.""",
        # Taklif yaratish - choose_store defined earlier at line 562
        "offer_title": "Taklif nomini kiriting:",
        "offer_description": "📝 Taklif ta'rifini kiriting:",
        "original_price": "💰 Oddiy narxni kiriting (so'mda):",
        "discount_price": "💸 Chegirmali narxni kiriting (so'mda):",
        "quantity": "📦 Portsialar sonini kiriting:",
        "time_from": "🕐 Boshlanish vaqtini kiriting (masalan: 18:00):",
        "expiry_date": "📅 Yaroqlilik muddatini kiriting (masalan: 31.12.2025):",
        "time_until": "🕐 Olib ketish tugash vaqtini kiriting (masalan: 21:00):",
        "offer_created": """✅ <b>Taklif yaratildi!</b>

🍽 {title}
📝 {description}
💰 {original_price} ➜ {discount_price} so\'m (-{discount}%)
📦 Soni: {quantity}
🕐 {time_from} - {time_until}

Taklif endi xaridorlar uchun mavjud!""",
        # Ommaviy yaratish
        "bulk_create_start": """📦 <b>Ommaviy taklif yaratish</b>

🏪 Do\'kon: {store_name}

Bu funksiya bir nechta bir xil takliflarni bir vaqtning o'zida yaratishga imkon beradi.
Masalan: 50 ta "Nonushta" to'plami bir xil narx va vaqt bilan.

Taklif nomini kiriting:""",
        "bulk_count": """🔢 <b>Nechta bunday taklif yaratilsin?</b>

Sonini kiriting (1 dan 100 gacha):""",
        "bulk_created": """✅ <b>Ommaviy yaratish tugadi!</b>

📦 Yaratilgan takliflar: {count}

🍽 {title}
📝 {description}
💰 {original_price} ➜ {discount_price} so\'m (-{discount}%)
📦 Har birida: {quantity}
📊 Jami portsialar: {total_quantity}
🕐 {time_from} - {time_until}

Barcha takliflar xaridorlar uchun mavjud!""",
        # Berishni tasdiqlash
        "confirm_delivery_prompt": "✅ <b>Buyurtma berishni tasdiqlash</b>\n\n8 xonali buyurtma kodini kiriting:",
        "booking_not_found": "❌ Bunday kodli buyurtma topilmadi",
        "order_confirmed": """✅ <b>Buyurtma tasdiqlandi!</b>

Buyurtma #{booking_id} tugallandi
Mijoz: {customer_name}
Summa: {price} so\'m

Mijoz do'koningizni baholash uchun xabar oladi.""",
        # Baho
        "rate_store": "⭐ <b>Do'konni baholang</b>\n\n🏪 {store_name}\n\nSizga qanday yoqdi?",
        "rating_saved": "✅ <b>Baholaganingiz uchun rahmat!</b>\n\nSizning fikringiz boshqa xaridorlarga yordam beradi!",
        "already_rated": "Siz bu buyurtmani allaqachon baholagansiz",
        # Statistika
        "store_stats": """🏪 <b>{name}</b>
🏷 {category}
📍 {city}, {address}
📝 {description}

⭐ Reyting: {rating}/5 ({reviews} ta sharh)
📊 Sotilgan: {sales} ta buyurtma
💰 Daromad: {revenue:,} so\'m
📦 Faol buyurtmalar: {pending}""",
        # Xatolar
        "error_invalid_number": "❌ Iltimos, to'g'ri raqam kiriting",
        "error_invalid_time": "❌ Noto'g'ri vaqt formati. HH:MM formatidan foydalaning (masalan: 18:00)",
        "no_stores": "❌ Sizda tasdiqlangan do'konlar yo'q!",
        "no_approved_stores": "❌ Sizda tasdiqlangan do'konlar yo'q!\n\n⏳ Administrator tomonidan arizangizni tasdiqlanishini kuting.",
        "operation_cancelled": "❌ Operatsiya bekor qilindi",
        "no_admin_access": "❌ Sizda admin paneliga kirish huquqi yo'q",
        "send_photo": '📸 Taom rasmini yuboring (yoki "otkazib yuborish" deb yozing)',
        "invalid_range": "❌ 1 dan 100 gacha",
        "no_offers_yet": "📊 Hali takliflar yo'q",
        "your_offers": "📊 Sizning takliflaringiz ({count}):",
        "no_stores_in_city": "😔 {city} shahrida hali do'konlar yo'q",
        "stores_in_city": "🏪 <b>{city} shahridagi do'konlar</b>\n\nJami: {count}",
        "your_stores": "🏪 Sizning do'konlaringiz ({count}):",
        "access_denied": "❌ Kirish taqiqlangan",
        "no_pending_stores": "✅ Moderatsiyada arizalar yo'q",
        "pending_stores_count": "⏳ Moderatsiyadagi arizalar: {count}",
        "store_approved_admin": "✅ Do'kon tasdiqlandi!",
        "store_rejected_admin": "✅ Do'kon rad etildi!",
        # Sevimlilar
        "no_favorites": "😔 Sizda hali sevimli do'konlar yo'q\n\nDo'konlarni sevimlilarga qo'shing, tez topish uchun!",
        "already_in_favorites": "❤️ Allaqachon sevimlilarda!",
        "added_to_favorites": "✅ Sevimlilarga qo'shildi!",
        "removed_from_favorites": "💔 Sevimlilardan o'chirildi",
        # Analitika - no_stores defined earlier at line 802
        "not_seller": "❌ Bu funksiya faqat hamkorlar uchun",
        "select_store_for_analytics": "📊 Analitika uchun do'konni tanlang:",
        # Boshqa
        "duplicate": "📋 Nusxalash",
        "delete": "❌ O'chirish",
        "duplicated": "✅ Taklif nusxalandi!",
        "deleted": "✅ Taklif o'chirildi",
        "change_language": "🌍 Tilni o'zgartirish",
        "delete_account": "🗑 Akkauntni o'chirish",
        # Sozlamalar
        "notifications_enabled": "✅ Bildirishnomalar yoqildi",
        "notifications_disabled": "🔕 Bildirishnomalar o'chirildi",
        "confirm_delete_account": """⚠️ <b>Akkauntni o\'chirish</b>

Akkauntingizni o\'chirishni xohlaysizmi?

O\'chiriladi:
• Barcha ma\'lumotlaringiz
• Do'konlaringiz
• Barcha takliflar
• Buyurtmalar tarixi

Bu harakatni qaytarib bo\'lmaydi!""",
        "account_deleted": "✅ Akkauntingiz muvaffaqiyatli o'chirildi",
        "yes_delete": "✅ Ha, o'chirish",
        "no_cancel": "❌ Yo'q, bekor qilish",
        "store_deleted": "✅ Do'kon muvaffaqiyatli o'chirildi",
        "error_general": "❌ Xatolik yuz berdi. Keyinroq urinib ko'ring.",
        "system_error": "⚠️ Tizim xatosi. Keyinroq urinib ko'ring yoki qo'llab-quvvatlash xizmatiga yozing.",
        # Yaxshilangan bo'sh holatlar
        "cart_empty": """🛒 <b>Savat bo'sh</b>

70% gacha chegirma bilan mazali narsa toping!

💡 Maslahat: «🔥 Aksiyalar» bo'limiga qarang""",
        "cart_empty_cta": "🔥 Takliflarni ko'rish",
        # Navigatsiya
        "go_back": "◀️ Orqaga",
        "continue_shopping": "🔙 Xaridni davom ettirish",
        # Miqdor tugmalari
        "qty_select": "📦 Miqdorni tanlang:",
        "qty_custom": "✏️ Boshqa",
        "qty_enter_custom": "Miqdorni kiriting (1 dan {max} gacha):",
        # Yaxshilangan xatolar
        "error_qty_invalid": """❌ <b>Noto'g'ri miqdor</b>

Mavjud: {available} dona
Urinib ko'ring: 1, 2 yoki {max}""",
        "error_qty_exceeded": """❌ <b>Juda ko'p</b>

Maksimum: {max} dona
1 dan {max} gacha son kiriting""",
        # Tezkor harakatlar
        "add_to_cart": "🛒 Savatga",
        "buy_now": "⚡ Hozir sotib olish",
        "added_to_cart": "✅ Savatga qo'shildi!",
        # Hamkor onbordingi
        "partner_welcome": """🎉 <b>Xush kelibsiz, hamkor!</b>

Do'koningiz tasdiqlandi va ishlashga tayyor.

<b>Hoziroq boshlang:</b>
1️⃣ Birinchi mahsulotni qo'shing
2️⃣ 30-70% chegirma qo'ying
3️⃣ Buyurtmalar oling!

💡 Maslahat: rasmli mahsulotlar 3 baravar yaxshi sotiladi""",
        "partner_add_first": "➕ Birinchi mahsulotni qo'shish",
        # Qo'shimcha tarjimalar (xardkod-tekstlar)
        "offer_not_found": "❌ Mahsulot topilmadi",
        "not_your_offer": "❌ Bu sizning mahsulotingiz emas",
        "edit_unavailable": "📝 Mahsulotni tahrirlash vaqtincha mavjud emas",
        "main_menu": "🏠 Asosiy menyu",
        "time_edit_title": "🕐 Olib ketish vaqtini o'zgartirish",
        "time_edit_prompt": "Yangi boshlanish vaqtini kiriting (masalan: 18:00):",
        "time_end_prompt": "Tugash vaqtini kiriting (masalan: 21:00):",
        "time_updated": "✅ Olib ketish vaqti yangilandi!",
        "title_saved": "✅ Nom saqlandi",
        "send_photo_now": "📸 Endi mahsulot rasmini yuboring yoki tugmani bosing",
        "without_photo": "📝 Fotosiz",
        "user_not_found": "Xato: foydalanuvchi topilmadi",
        # Validatsiya/limitlar
        "invalid_city": "Iltimos, ro'yxatdan shaharni tanlang.",
        "rate_limit_exceeded": "Juda ko'p so'rovlar. Keyinroq urinib ko'ring.",
    },
}


def get_text(lang: str, key: str, **kwargs: str) -> str:
    """Получить текст на нужном языке с форматированием

    Args:
        lang: Код языка ('ru' или 'uz')
        key: Ключ текста из TEXTS
        **kwargs: Параметры для форматирования строки

    Returns:
        Отформатированная строка текста или сам ключ, если текст не найден
    """
    try:
        texts = TEXTS.get(lang, TEXTS.get("ru", {}))
        text = texts.get(key, key)

        # Если текст не найден, пробуем русский
        if text == key and lang != "ru":
            text = TEXTS.get("ru", {}).get(key, key)

        # Форматируем, если есть параметры и текст содержит плейсхолдеры
        if kwargs and text != key:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError) as e:
                # Если форматирование не удалось, возвращаем текст без форматирования
                import logging

                logging.warning(f"Format error in get_text: {e}, key={key}, lang={lang}")
                return text

        return text
    except Exception as e:
        import logging

        logging.error(f"Error in get_text: {e}, key={key}, lang={lang}")
        return key


def get_language_name(lang: str) -> str:
    """Получить название языка"""
    return LANGUAGES.get(lang, LANGUAGES["ru"])


def get_cities(lang: str) -> list[str]:
    """Получить список городов на нужном языке"""
    return [
        "Ташкент" if lang == "ru" else "Toshkent",
        "Самарканд" if lang == "ru" else "Samarqand",
        "Бухара" if lang == "ru" else "Buxoro",
        "Андижан" if lang == "ru" else "Andijon",
        "Наманган" if lang == "ru" else "Namangan",
        "Фергана" if lang == "ru" else "Farg'ona",
        "Хива" if lang == "ru" else "Xiva",
        "Нукус" if lang == "ru" else "Nukus",
    ]


def get_categories(lang: str) -> list[str]:
    """Получить список категорий бизнеса на нужном языке"""
    if lang == "ru":
        return ["Ресторан", "Кафе", "Пекарня", "Супермаркет", "Кондитерская", "Фастфуд"]
    else:
        return ["Restoran", "Kafe", "Nonvoyxona", "Supermarket", "Qandolatxona", "Fastfud"]


def get_product_categories(lang: str) -> list[str]:
    """Получить список категорий товаров - совпадает с теми, что выбирает партнёр"""
    if lang == "ru":
        return [
            "Выпечка",
            "Молочные",
            "Мясные",
            "Фрукты",
            "Овощи",
            "Напитки",
            "Снеки",
            "Замороженное",
        ]
    else:
        return [
            "Pishiriq",
            "Sut mahsulotlari",
            "Go'sht mahsulotlari",
            "Mevalar",
            "Sabzavotlar",
            "Ichimliklar",
            "Gaz. ovqatlar",
            "Muzlatilgan",
        ]


def normalize_category(category: str) -> str:
    """Нормализовать категорию к английскому для БД (для таблицы offers)"""
    # Маппинг категорий товаров (product categories) в английские названия БД
    product_mapping = {
        # Русский
        "Выпечка": "bakery",
        "Молочные": "dairy",
        "Мясные": "meat",
        "Фрукты": "fruits",
        "Овощи": "vegetables",
        "Напитки": "drinks",
        "Снеки": "snacks",
        "Замороженное": "frozen",
        # Узбекский
        "Pishiriq": "bakery",
        "Sut mahsulotlari": "dairy",
        "Go'sht mahsulotlari": "meat",
        "Mevalar": "fruits",
        "Sabzavotlar": "vegetables",
        "Ichimliklar": "drinks",
        "Gaz. ovqatlar": "snacks",
        "Muzlatilgan": "frozen",
        # Старые названия (для совместимости)
        "Хлеб": "bakery",
        "Non": "bakery",
        "Sut": "dairy",
        "Мясо": "meat",
        "Go'sht": "meat",
        "Рыба": "fish",
        "Baliq": "fish",
        "Sabzavot": "vegetables",
        "Meva": "fruits",
        "Сыры": "cheese",
        "Pishloq": "cheese",
        "Ichimlik": "drinks",
        "Готовая еда": "ready_food",
        "Tayyor ovqat": "ready_food",
        "Другое": "other",
        "Boshqa": "other",
    }
    # Маппинг категорий магазинов (store categories)
    store_mapping = {
        "Restoran": "Ресторан",
        "Kafe": "Кафе",
        "Nonvoyxona": "Пекарня",
        "Supermarket": "Супермаркет",
        "Qandolatxona": "Кондитерская",
        "Fastfud": "Фастфуд",
    }
    # Сначала пробуем найти в product_mapping, потом в store_mapping
    return product_mapping.get(category, store_mapping.get(category, category))
