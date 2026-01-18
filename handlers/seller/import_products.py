"""
Handlers for product import and auto-discount features.
"""

from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.integrations.onec_integration import (
    OneCConfig,
    OneCIntegration,
)
from app.services.auto_discount_service import AutoDiscountService
from logging_config import logger

router = Router(name="import")


class ImportProducts(StatesGroup):
    """States for product import."""

    waiting_file = State()
    confirm_import = State()


# Module dependencies
db: Any = None
bot: Any = None
auto_discount_service: AutoDiscountService | None = None


def setup_dependencies(database: Any, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot, auto_discount_service
    db = database
    bot = bot_instance
    auto_discount_service = AutoDiscountService(db, bot)


# =============================================================================
# SELLER MENU CALLBACK - Return to seller main menu
# =============================================================================


@router.callback_query(F.data == "seller_menu")
async def back_to_seller_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Return to seller main menu - clear state and show menu."""
    if not db or not callback.message:
        await callback.answer("Ошибка", show_alert=True)
        return

    # Clear any active FSM state
    await state.clear()

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    from app.keyboards import main_menu_seller

    await callback.message.answer(
        "Главное меню" if lang == "ru" else "Asosiy menyu",
        reply_markup=main_menu_seller(lang),
    )
    await callback.answer()


# =============================================================================
# IMPORT HANDLERS
# =============================================================================


@router.callback_query(F.data == "import_products")
async def start_import(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start product import flow."""
    if not db or not callback.message:
        await callback.answer("Ошибка системы", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Check if user has a store
    stores = db.get_user_accessible_stores(user_id)
    if not stores:
        await callback.answer(
            "У вас нет магазина" if lang == "ru" else "Sizda do'kon yo'q",
            show_alert=True,
        )
        return

    store = stores[0]
    store_id = store.get("store_id") if isinstance(store, dict) else store[0]
    await state.update_data(store_id=store_id)
    await state.set_state(ImportProducts.waiting_file)

    kb = InlineKeyboardBuilder()
    kb.button(text="Скачать пример CSV", callback_data="download_sample_csv")
    kb.button(text="Отмена", callback_data="cancel_import")
    kb.adjust(1)

    if lang == "uz":
        text = (
            "<b>Mahsulotlarni import qilish</b>\n\n"
            "CSV yoki Excel faylni yuboring:\n\n"
            "<b>Kerakli ustunlar:</b>\n"
            "- name - Mahsulot nomi\n"
            "- price - Narx\n"
            "- quantity - Miqdor\n"
            "- expiry_date - Yaroqlilik muddati (KK.OO.YYYY)\n"
            "- category - Kategoriya (ixtiyoriy)\n\n"
            "Chegirma avtomatik hisoblanadi."
        )
    else:
        text = (
            "<b>Импорт товаров</b>\n\n"
            "Отправьте CSV или Excel файл:\n\n"
            "<b>Необходимые колонки:</b>\n"
            "- name - Название товара\n"
            "- price - Цена\n"
            "- quantity - Количество\n"
            "- expiry_date - Срок годности (ДД.ММ.ГГГГ)\n"
            "- category - Категория (опционально)\n\n"
            "Скидка рассчитается автоматически."
        )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "download_sample_csv")
async def send_sample_csv(callback: types.CallbackQuery) -> None:
    """Send sample CSV file."""
    if not auto_discount_service or not callback.message:
        await callback.answer("Ошибка", show_alert=True)
        return

    sample = auto_discount_service.generate_sample_csv()

    from aiogram.types import BufferedInputFile

    file = BufferedInputFile(sample.encode("utf-8-sig"), filename="sample_import.csv")

    await callback.message.answer_document(
        file,
        caption=(
            "<b>Пример CSV файла</b>\n\n"
            "Заполните по образцу и отправьте мне.\n"
            "Разделитель: точка с запятой (;)"
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ImportProducts.waiting_file, F.document)
async def process_import_file(message: types.Message, state: FSMContext) -> None:
    """Process uploaded file for import."""
    if not db or not bot or not auto_discount_service or not message.document:
        await message.answer("Ошибка системы")
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    data = await state.get_data()
    store_id = data.get("store_id")

    if not store_id:
        await message.answer("Магазин не найден")
        await state.clear()
        return

    # Check file type
    filename = message.document.file_name or ""
    if not filename.lower().endswith((".csv", ".txt")):
        await message.answer(
            "Поддерживаются только CSV файлы"
            if lang == "ru"
            else "Faqat CSV fayllar qo'llab-quvvatlanadi"
        )
        return

    # Download file
    try:
        file = await bot.get_file(message.document.file_id)
        file_content = await bot.download_file(file.file_path)
        content = file_content.read()
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        await message.answer("Не удалось загрузить файл")
        return

    # Show processing message
    processing_msg = await message.answer("Обрабатываю файл...")

    # Import products
    try:
        result = await auto_discount_service.import_from_csv(store_id, content, user_id)
    except Exception as e:
        logger.error(f"Import failed: {e}")
        await processing_msg.edit_text(f"Ошибка импорта: {e}")
        await state.clear()
        return

    await state.clear()

    # Build result message
    if lang == "uz":
        text = (
            f"<b>Import yakunlandi</b>\n\n"
            f"Import qilindi: <b>{result['imported']}</b>\n"
            f"O'tkazib yuborildi: {result['skipped']}\n"
            f"Xatolar: {result['total_errors']}"
        )
    else:
        text = (
            f"<b>Импорт завершён</b>\n\n"
            f"Импортировано: <b>{result['imported']}</b>\n"
            f"Пропущено: {result['skipped']}\n"
            f"Ошибок: {result['total_errors']}"
        )

    if result["errors"]:
        text += "\n\n<b>Ошибки:</b>\n" + "\n".join(f"- {e}" for e in result["errors"][:5])

    await processing_msg.edit_text(text, parse_mode="HTML")


@router.callback_query(F.data == "cancel_import")
async def cancel_import(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel import."""
    await state.clear()

    if callback.message:
        await callback.message.edit_text("Импорт отменён")

    await callback.answer()


# =============================================================================
# AUTO-DISCOUNT SETTINGS
# =============================================================================


@router.callback_query(F.data == "auto_discount_settings")
async def show_discount_settings(callback: types.CallbackQuery) -> None:
    """Show auto-discount settings."""
    if not db or not auto_discount_service or not callback.message:
        await callback.answer("Ошибка", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    rules = auto_discount_service.discount_rules

    if lang == "uz":
        text = "<b>Avtomatik chegirma sozlamalari</b>\n\n<b>Joriy qoidalar:</b>\n"
        for days, percent in sorted(rules.items(), reverse=True):
            if days == 0:
                text += f"- Bugun tugaydi: <b>-{percent}%</b>\n"
            elif days == 1:
                text += f"- 1 kun qoldi: <b>-{percent}%</b>\n"
            else:
                text += f"- {days} kun qoldi: <b>-{percent}%</b>\n"
    else:
        text = "<b>Настройки автоскидок</b>\n\n<b>Текущие правила:</b>\n"
        for days, percent in sorted(rules.items(), reverse=True):
            if days == 0:
                text += f"- Истекает сегодня: <b>-{percent}%</b>\n"
            elif days == 1:
                text += f"- Остался 1 день: <b>-{percent}%</b>\n"
            else:
                text += f"- Осталось {days} дней: <b>-{percent}%</b>\n"

    text += "\n<i>Скидки пересчитываются автоматически каждый день</i>"

    kb = InlineKeyboardBuilder()
    kb.button(
        text="Обновить скидки сейчас" if lang == "ru" else "Chegirmalarni yangilash",
        callback_data="update_discounts_now",
    )
    kb.button(text="Назад" if lang == "ru" else "Orqaga", callback_data="seller_menu")
    kb.adjust(1)

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "update_discounts_now")
async def update_discounts_now(callback: types.CallbackQuery) -> None:
    """Manually trigger discount update."""
    if not db or not auto_discount_service or not callback.message:
        await callback.answer("Ошибка", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Get user's store
    stores = db.get_user_accessible_stores(user_id)
    if not stores:
        await callback.answer("У вас нет магазина", show_alert=True)
        return

    store = stores[0]
    store_id = store.get("store_id") if isinstance(store, dict) else store[0]

    await callback.answer("Обновляю скидки...")

    try:
        result = await auto_discount_service.update_existing_offers_discounts(store_id)

        if lang == "uz":
            text = (
                f"<b>Chegirmalar yangilandi</b>\n\n"
                f"Yangilandi: {result['updated']}\n"
                f"O'chirildi: {result['deactivated']}"
            )
        else:
            text = (
                f"<b>Скидки обновлены</b>\n\n"
                f"Обновлено: {result['updated']}\n"
                f"Деактивировано: {result['deactivated']}"
            )

        await callback.message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Failed to update discounts: {e}")
        await callback.message.answer(f"Ошибка: {e}")


# =============================================================================
# 1C INTEGRATION HANDLERS
# =============================================================================


class OneCSetup(StatesGroup):
    """States for 1C setup."""

    waiting_url = State()
    waiting_credentials = State()
    waiting_days = State()


# Storage for 1C configs (in production use database)
onec_configs: dict[int, OneCConfig] = {}
onec_instances: dict[int, OneCIntegration] = {}


@router.callback_query(F.data == "setup_1c_integration")
async def start_1c_setup(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start 1C integration setup."""
    if not db or not callback.message:
        await callback.answer("Ошибка", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Check if user has a store
    stores = db.get_user_accessible_stores(user_id)
    if not stores:
        await callback.answer("У вас нет магазина", show_alert=True)
        return

    store = stores[0]
    store_id = store.get("store_id") if isinstance(store, dict) else store[0]
    await state.update_data(store_id=store_id)

    if lang == "uz":
        text = (
            "<b>1C integratsiyasini sozlash</b>\n\n"
            "1C OData URL manzilini yuboring:\n\n"
            "<code>http://server:port/base/odata/standard.odata/</code>\n\n"
            "yoki HTTP-xizmat URL:\n"
            "<code>http://server:port/base/hs/fudly/</code>\n\n"
            "Bekor qilish uchun /cancel yozing"
        )
    else:
        text = (
            "<b>Настройка интеграции с 1С</b>\n\n"
            "Отправьте URL 1C OData:\n\n"
            "<code>http://server:port/base/odata/standard.odata/</code>\n\n"
            "или URL HTTP-сервиса:\n"
            "<code>http://server:port/base/hs/fudly/</code>\n\n"
            "Для отмены напишите /cancel"
        )

    kb = InlineKeyboardBuilder()
    kb.button(text="Инструкция по настройке", callback_data="1c_setup_guide")
    kb.button(text="Отмена", callback_data="cancel_1c_setup")
    kb.adjust(1)

    await state.set_state(OneCSetup.waiting_url)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "1c_setup_guide")
async def show_1c_guide(callback: types.CallbackQuery) -> None:
    """Show 1C setup guide."""
    if not callback.message:
        return

    guide = """
<b>Инструкция по настройке 1С</b>

<b>Вариант 1: OData (1С 8.3+)</b>
1. В 1С откройте Администрирование → Настройка OData
2. Включите REST API
3. Создайте пользователя для API
4. URL будет: <code>http://ip:port/base/odata/standard.odata/</code>

<b>Вариант 2: HTTP-сервис (рекомендуется)</b>
1. Создайте HTTP-сервис в 1С
2. Добавьте метод GET /products?days=N
3. Возвращайте JSON со списком товаров

<b>Формат JSON:</b>
<code>[{
  "code": "00001",
  "name": "Молоко 1л",
  "price": 15000,
  "quantity": 10,
  "expiry_date": "2025-11-30"
}]</code>

<b>Важно:</b>
- Возвращайте только товары со сроком <= N дней
- price в тийинах (15000 = 150 сум)
- expiry_date в формате YYYY-MM-DD
"""

    await callback.message.answer(guide, parse_mode="HTML")
    await callback.answer()


@router.message(OneCSetup.waiting_url)
async def process_1c_url(message: types.Message, state: FSMContext) -> None:
    """Process 1C URL."""
    if not db or not message.text:
        return

    url = message.text.strip()

    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        await message.answer("URL должен начинаться с http:// или https://")
        return

    await state.update_data(onec_url=url)
    await state.set_state(OneCSetup.waiting_credentials)

    user_id = message.from_user.id if message.from_user else 0
    lang = db.get_user_language(user_id)

    if lang == "uz":
        text = (
            "<b>Avtorizatsiya</b>\n\n"
            "Login va parolni yuboring:\n"
            "<code>login:parol</code>\n\n"
            "Yoki avtorizatsiya kerak bo'lmasa, <b>skip</b> yozing"
        )
    else:
        text = (
            "<b>Авторизация</b>\n\n"
            "Отправьте логин и пароль:\n"
            "<code>логин:пароль</code>\n\n"
            "Или напишите <b>skip</b> если авторизация не нужна"
        )

    await message.answer(text, parse_mode="HTML")


@router.message(OneCSetup.waiting_credentials)
async def process_1c_credentials(message: types.Message, state: FSMContext) -> None:
    """Process 1C credentials."""
    if not db or not message.text:
        return

    text = message.text.strip()
    user_id = message.from_user.id if message.from_user else 0

    if text.lower() == "skip":
        await state.update_data(onec_username="", onec_password="")
    elif ":" in text:
        parts = text.split(":", 1)
        await state.update_data(onec_username=parts[0], onec_password=parts[1])
    else:
        await message.answer("Формат: логин:пароль или skip")
        return

    await state.set_state(OneCSetup.waiting_days)

    lang = db.get_user_language(user_id)

    if lang == "uz":
        text = (
            "<b>Muddat filteri</b>\n\n"
            "Necha kun qolgan mahsulotlarni import qilish kerak?\n"
            "(1-14 orasida raqam yuboring)\n\n"
            "Masalan: <b>7</b> - 7 kun va kamroq qolgan"
        )
    else:
        text = (
            "<b>Фильтр по сроку</b>\n\n"
            "За сколько дней до истечения импортировать товары?\n"
            "(отправьте число от 1 до 14)\n\n"
            "Например: <b>7</b> - срок <= 7 дней"
        )

    await message.answer(text, parse_mode="HTML")


@router.message(OneCSetup.waiting_days)
async def process_1c_days(message: types.Message, state: FSMContext) -> None:
    """Process days filter and complete setup."""
    if not db or not auto_discount_service or not message.text:
        return

    user_id = message.from_user.id if message.from_user else 0
    lang = db.get_user_language(user_id)

    try:
        days = int(message.text.strip())
        if not 1 <= days <= 14:
            raise ValueError("Out of range")
    except ValueError:
        await message.answer("Введите число от 1 до 14")
        return

    data = await state.get_data()
    await state.clear()

    # Create config
    config = OneCConfig(
        base_url=data["onec_url"],
        username=data.get("onec_username", ""),
        password=data.get("onec_password", ""),
        days_until_expiry=days,
    )

    # Save config for user
    onec_configs[user_id] = config

    # Create integration instance
    integration = OneCIntegration(config)
    onec_instances[user_id] = integration

    # Test connection
    await message.answer("Проверяю подключение...")

    success, status_msg = await integration.test_connection()

    if success:
        if lang == "uz":
            text = (
                f"<b>1C integratsiyasi sozlandi</b>\n\n"
                f"URL: <code>{config.base_url[:50]}...</code>\n"
                f"Filtr: {days} kun\n\n"
                f"Endi mahsulotlarni import qilishingiz mumkin"
            )
        else:
            text = (
                f"<b>Интеграция с 1С настроена</b>\n\n"
                f"URL: <code>{config.base_url[:50]}...</code>\n"
                f"Фильтр: {days} дней\n\n"
                f"Теперь можете импортировать товары"
            )
    else:
        if lang == "uz":
            text = (
                f"<b>Sozlamalar saqlandi</b>\n\n"
                f"Ulanish tekshiruvi: {status_msg}\n\n"
                f"Keyinroq qayta urinib ko'ring"
            )
        else:
            text = (
                f"<b>Настройки сохранены</b>\n\n"
                f"Проверка подключения: {status_msg}\n\n"
                f"Попробуйте позже"
            )

    kb = InlineKeyboardBuilder()
    kb.button(
        text="Импорт из 1С" if lang == "ru" else "1C dan import",
        callback_data="sync_from_1c",
    )
    kb.button(text="Назад" if lang == "ru" else "Orqaga", callback_data="seller_menu")
    kb.adjust(1)

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "sync_from_1c")
async def sync_from_1c(callback: types.CallbackQuery) -> None:
    """Sync products from 1C."""
    if not db or not auto_discount_service or not callback.message:
        await callback.answer("Ошибка", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Check if 1C is configured
    if user_id not in onec_instances:
        await callback.answer(
            "1C не настроен. Сначала настройте интеграцию.",
            show_alert=True,
        )
        return

    integration = onec_instances[user_id]

    # Get store
    stores = db.get_user_accessible_stores(user_id)
    if not stores:
        await callback.answer("У вас нет магазина", show_alert=True)
        return

    store = stores[0]
    store_id = store.get("store_id") if isinstance(store, dict) else store[0]

    await callback.answer("Синхронизация...")

    # Fetch products from 1C
    products = await integration.fetch_expiring_products()

    if not products:
        if lang == "uz":
            await callback.message.answer("1C da muddati tugayotgan mahsulotlar topilmadi")
        else:
            await callback.message.answer("В 1С нет товаров с истекающим сроком годности")
        return

    # Import products with auto-discount
    imported = 0
    errors = 0

    for product in products:
        try:
            # Calculate discount
            discount = auto_discount_service.calculate_discount(product.expiry_date, product.price)

            # Skip if no discount needed
            if discount.discount_percent == 0:
                continue

            # Create offer
            db.create_offer(
                store_id=store_id,
                title=product.name,
                description=f"[1C:{product.code}] {discount.urgency_message}",
                original_price=product.price,
                discount_price=discount.discount_price,
                quantity=product.quantity,
                category=product.category,
                expiry_date=product.expiry_date.strftime("%Y-%m-%d"),
            )
            imported += 1

        except Exception as e:
            logger.error(f"1C import error for {product.code}: {e}")
            errors += 1

    # Result message
    if lang == "uz":
        text = (
            f"<b>1C dan import yakunlandi</b>\n\n"
            f"Topildi: {len(products)}\n"
            f"Import qilindi: {imported}\n"
            f"Xatolar: {errors}"
        )
    else:
        text = (
            f"<b>Импорт из 1С завершён</b>\n\n"
            f"Найдено: {len(products)}\n"
            f"Импортировано: {imported}\n"
            f"Ошибок: {errors}"
        )

    await callback.message.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "cancel_1c_setup")
async def cancel_1c_setup(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel 1C setup."""
    await state.clear()

    if callback.message:
        await callback.message.edit_text("Настройка 1С отменена")

    await callback.answer()
