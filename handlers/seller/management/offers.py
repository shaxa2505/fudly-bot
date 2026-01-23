"""Seller offer management handlers - CRUD operations for offers."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import main_menu_seller
from handlers.common.states import EditOffer
from handlers.common.utils import is_main_menu_button
from localization import get_text
from logging_config import logger

from .utils import (
    format_quantity,
    get_db,
    get_offer_field,
    get_store_field,
    send_offer_card,
    update_offer_message,
)

router = Router()

DECIMAL_UNITS = {"кг", "л"}
NO_EXPIRY_TOKENS = {
    "-",
    "0",
    "без",
    "без срока",
    "нет",
    "нет срока",
    "none",
    "no",
    "muddatsiz",
    "muddati yo'q",
    "muddati yoq",
}

CATEGORY_OPTIONS = [
    ("bakery", "Выпечка", "Pishiriq"),
    ("dairy", "Молочные", "Sut mahsulotlari"),
    ("meat", "Мясные", "Go'sht mahsulotlari"),
    ("fruits", "Фрукты", "Mevalar"),
    ("vegetables", "Овощи", "Sabzavotlar"),
    ("drinks", "Напитки", "Ichimliklar"),
    ("snacks", "Снеки", "Gaz. ovqatlar"),
    ("frozen", "Замороженное", "Muzlatilgan"),
    ("sweets", "Сладости", "Shirinliklar"),
    ("other", "Другое", "Boshqa"),
]

UNIT_OPTIONS = [
    ("шт", "Штуки (шт)", "Dona (dona)"),
    ("уп", "Упаковки (уп)", "Qadoq (up)"),
    ("кг", "Килограммы (кг)", "Kilogramm (kg)"),
    ("г", "Граммы (г)", "Gramm (g)"),
    ("л", "Литры (л)", "Litr (l)"),
    ("мл", "Миллилитры (мл)", "Millilitr (ml)"),
]


def _price_input_hint(lang: str) -> str:
    if lang == "ru":
        return (
            "Отправьте 2 числа: цена и цена со скидкой (пример: 10000 7000).\n"
            "Можно отправить процент: 30%."
        )
    return (
        "2 ta son yuboring: asl narx va chegirmali narx (misol: 10000 7000).\n"
        "Foiz ham mumkin: 30%."
    )


def _extract_numbers(text: str) -> list[int]:
    return [int(value) for value in re.findall(r"\d+", text or "")]


def _parse_qty_delta(callback_data: str, default_delta: int) -> tuple[int, int] | None:
    parts = callback_data.split("_")
    if len(parts) < 3:
        return None
    try:
        offer_id = int(parts[-1])
    except ValueError:
        return None

    delta = default_delta
    if len(parts) >= 4 and parts[-2].isdigit():
        delta_value = int(parts[-2])
        delta = delta_value if default_delta > 0 else -delta_value
    return offer_id, delta


def _parse_expiry_date(value: object) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def _is_low_stock(offer: object, threshold: int = 5) -> bool:
    status = get_offer_field(offer, "status", "active")
    if status != "active":
        return False
    qty = get_offer_field(offer, "quantity", 0)
    try:
        qty_value = float(qty)
    except (TypeError, ValueError):
        qty_value = 0
    return qty_value < threshold


def _is_expiring_soon(offer: object, days: int = 2) -> bool:
    status = get_offer_field(offer, "status", "active")
    if status != "active":
        return False
    expiry = _parse_expiry_date(get_offer_field(offer, "expiry_date"))
    if not expiry:
        return False
    today = datetime.now().date()
    delta_days = (expiry - today).days
    return 0 <= delta_days <= days


def _category_keyboard(offer_id: int, lang: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for code, ru_label, uz_label in CATEGORY_OPTIONS:
        label = ru_label if lang == "ru" else uz_label
        builder.button(text=label, callback_data=f"setcat_{offer_id}_{code}")
    builder.button(text=get_text(lang, "back"), callback_data=f"back_to_offer_{offer_id}")
    builder.adjust(2)
    return builder


def _unit_keyboard(offer_id: int, lang: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for code, ru_label, uz_label in UNIT_OPTIONS:
        label = ru_label if lang == "ru" else uz_label
        builder.button(text=label, callback_data=f"setunit_{offer_id}_{code}")
    builder.button(text=get_text(lang, "back"), callback_data=f"back_to_offer_{offer_id}")
    builder.adjust(2, 2, 2, 1)
    return builder


def _expiry_keyboard(offer_id: int, lang: str) -> InlineKeyboardBuilder:
    today = datetime.now()
    builder = InlineKeyboardBuilder()
    dates = [
        ("Сегодня" if lang == "ru" else "Bugun", 0),
        ("Завтра" if lang == "ru" else "Ertaga", 1),
        ("+3 дня" if lang == "ru" else "+3 kun", 3),
        ("+7 дней" if lang == "ru" else "+7 kun", 7),
        ("+14 дней" if lang == "ru" else "+14 kun", 14),
    ]
    for label, days in dates:
        date_label = (today + timedelta(days=days)).strftime("%d.%m")
        builder.button(text=f"{label} ({date_label})", callback_data=f"setexp_{offer_id}_{days}")
    builder.button(
        text="Без срока" if lang == "ru" else "Muddatsiz",
        callback_data=f"setexp_{offer_id}_none",
    )
    builder.button(
        text="Другая дата" if lang == "ru" else "Boshqa sana",
        callback_data=f"edit_expiry_custom_{offer_id}",
    )
    builder.button(text=get_text(lang, "back"), callback_data=f"back_to_offer_{offer_id}")
    builder.adjust(2, 2, 1, 2, 1)
    return builder


def _parse_expiry_input_text(text: str) -> str | None:
    raw = (text or "").strip().lower()
    if not raw or raw in NO_EXPIRY_TOKENS:
        return None
    day_match = re.fullmatch(r"\+?\s*(\d{1,3})\s*(д|дн|дня|дней|кун|kun|day|days)?", raw)
    if day_match:
        days = int(day_match.group(1))
        return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    normalized = raw.replace("/", ".").replace("-", ".")
    parts = normalized.split(".")
    today = datetime.now()
    try:
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            day, month = map(int, parts)
            date_obj = datetime(today.year, month, day)
            if date_obj.date() < today.date():
                date_obj = date_obj.replace(year=today.year + 1)
            return date_obj.strftime("%Y-%m-%d")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            if len(parts[0]) == 4:
                year, month, day = map(int, parts)
            else:
                day, month, year = map(int, parts)
                if year < 100:
                    year += 2000
            date_obj = datetime(year, month, day)
            return date_obj.strftime("%Y-%m-%d")
    except ValueError:
        pass

    raise ValueError("Invalid expiry format")


@router.message(
    F.text.contains("Мои товары")
    | F.text.contains("Mening mahsulotlarim")
    | F.text.contains(get_text("ru", "my_items"))
    | F.text.contains(get_text("uz", "my_items"))
)
async def my_offers(message: types.Message, state: FSMContext) -> None:
    """Display seller's offers with management buttons."""
    # Clear any active FSM state
    await state.clear()
    
    db = get_db()
    lang = db.get_user_language(message.from_user.id)
    stores = db.get_user_accessible_stores(message.from_user.id)

    logger.info(f"my_offers: user {message.from_user.id}, stores count: {len(stores)}")

    if not stores:
        await message.answer(get_text(lang, "no_stores"))
        return

    all_offers = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        store_name = get_store_field(store, "name", "Магазин")
        offers = db.get_offers_by_store(store_id, include_all=True)
        logger.info(f"Store {store_id} ({store_name}), offers count: {len(offers)}")
        all_offers.extend(offers)

    logger.info(f"Total offers: {len(all_offers)}")

    if not all_offers:
        await message.answer(
            "<b>" + ("Ваши товары" if lang == "ru" else "Mahsulotlaringiz") + "</b>\n\n"
            + get_text(lang, "no_offers_yet")
            + "\n\n"
            + (
                "Нажмите «Добавить», чтобы создать первый товар."
                if lang == "ru"
                else "Birinchi mahsulotni yaratish uchun «Qo'shish» tugmasini bosing."
            ),
            parse_mode="HTML",
        )
        return

    # Count active and inactive
    active_count = sum(1 for o in all_offers if get_offer_field(o, "status") == "active")
    inactive_count = len(all_offers) - active_count
    low_stock_count = sum(1 for o in all_offers if _is_low_stock(o))
    expiring_count = sum(1 for o in all_offers if _is_expiring_soon(o))

    # Filter menu
    filter_kb = InlineKeyboardBuilder()
    filter_kb.button(text=f"Активные ({active_count})", callback_data="filter_offers_active_0")
    filter_kb.button(
        text=(
            f"Мало (<5) ({low_stock_count})"
            if lang == "ru"
            else f"Kam (<5) ({low_stock_count})"
        ),
        callback_data="filter_offers_low_0",
    )
    filter_kb.button(
        text=(
            f"Срок ≤2д ({expiring_count})"
            if lang == "ru"
            else f"Muddat ≤2k ({expiring_count})"
        ),
        callback_data="filter_offers_expiring_0",
    )
    filter_kb.button(
        text=f"Неактивные ({inactive_count})", callback_data="filter_offers_inactive_0"
    )
    filter_kb.button(text=f"Все ({len(all_offers)})", callback_data="filter_offers_all_0")
    filter_kb.button(
        text="Поиск" if lang == "ru" else "Qidirish", callback_data="search_my_offers"
    )
    filter_kb.adjust(2, 2, 2)

    await message.answer(
        f"<b>{'Ваши товары' if lang == 'ru' else 'Mahsulotlaringiz'}</b>\n\n"
        f"Активных: <b>{active_count}</b>\n"
        f"{'Мало (<5)' if lang == 'ru' else 'Kam (<5)'}: <b>{low_stock_count}</b>\n"
        f"{'Срок ≤2д' if lang == 'ru' else 'Muddat ≤2k'}: <b>{expiring_count}</b>\n"
        f"Неактивных: <b>{inactive_count}</b>\n"
        f"Всего: <b>{len(all_offers)}</b>\n\n"
        f"{'Выберите фильтр:' if lang == 'ru' else 'Filtrni tanlang:'}",
        parse_mode="HTML",
        reply_markup=filter_kb.as_markup(),
    )


@router.callback_query(F.data.startswith("filter_offers_"))
async def filter_offers(callback: types.CallbackQuery) -> None:
    """Filter offers by status with pagination."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_accessible_stores(callback.from_user.id)

    if not stores:
        await callback.answer(get_text(lang, "no_stores"), show_alert=True)
        return

    # Parse filter type and page: filter_offers_active_0
    parts = callback.data.split("_")
    filter_type = parts[2] if len(parts) > 2 else "all"  # active, inactive, all
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0

    ITEMS_PER_PAGE = 5

    all_offers = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        offers = db.get_offers_by_store(store_id, include_all=True)
        all_offers.extend(offers)

    # Apply filter
    if filter_type == "active":
        filtered = [o for o in all_offers if get_offer_field(o, "status") == "active"]
        title = "Активные" if lang == "ru" else "Faol"
    elif filter_type == "inactive":
        filtered = [o for o in all_offers if get_offer_field(o, "status") != "active"]
        title = "Неактивные" if lang == "ru" else "Nofaol"
    elif filter_type == "low":
        filtered = [o for o in all_offers if _is_low_stock(o)]
        title = "Мало (<5)" if lang == "ru" else "Kam (<5)"
    elif filter_type == "expiring":
        filtered = [o for o in all_offers if _is_expiring_soon(o)]
        title = "Срок ≤2д" if lang == "ru" else "Muddat ≤2k"
    else:
        filtered = all_offers
        title = "Все" if lang == "ru" else "Hammasi"

    if not filtered:
        await callback.answer(
            f"{'Нет товаров в этой категории' if lang == 'ru' else 'Bu kategoriyada mahsulot yo`q'}",
            show_alert=True,
        )
        return

    # Pagination
    total_pages = (len(filtered) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = min(page, total_pages - 1)
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_offers = filtered[start_idx:end_idx]

    # Build compact list
    text = f"<b>{title}</b> ({len(filtered)})\n"
    text += f"{'Страница' if lang == 'ru' else 'Sahifa'} {page + 1}/{total_pages}\n\n"

    for i, offer in enumerate(page_offers, start=start_idx + 1):
        offer_id = get_offer_field(offer, "offer_id")
        offer_title = get_offer_field(offer, "title", "Товар")[:25]
        price = get_offer_field(offer, "discount_price", 0)
        qty = get_offer_field(offer, "quantity", 0)
        unit = get_offer_field(offer, "unit", "шт")
        status = get_offer_field(offer, "status", "active")

        status_label = "Активен" if lang == "ru" else "Faol"
        if status != "active":
            status_label = "Неактивен" if lang == "ru" else "Nofaol"
        price_label = "Цена" if lang == "ru" else "Narx"
        qty_label = "Остаток" if lang == "ru" else "Miqdor"
        qty_display = format_quantity(qty, unit, lang)

        text += f"{i}. <b>{offer_title}</b>\n"
        if filter_type == "all":
            text += f"   {status_label} | {price_label}: {price:,} | {qty_label}: {qty_display}\n"
        else:
            text += f"   {price_label}: {price:,} | {qty_label}: {qty_display}\n"

    # Navigation buttons
    nav_kb = InlineKeyboardBuilder()

    # Add item buttons for quick access
    for offer in page_offers:
        offer_id = get_offer_field(offer, "offer_id")
        offer_title = get_offer_field(offer, "title", "Товар")[:18]
        nav_kb.button(text=offer_title, callback_data=f"view_offer_{offer_id}")

    nav_kb.adjust(2)  # 2 buttons per row for items

    # Pagination row
    pagination_buttons = []
    if page > 0:
        prev_text = "Предыдущая" if lang == "ru" else "Oldingi"
        pagination_buttons.append((prev_text, f"filter_offers_{filter_type}_{page - 1}"))
    pagination_buttons.append((f"{page + 1}/{total_pages}", "noop"))
    if page < total_pages - 1:
        next_text = "Следующая" if lang == "ru" else "Keyingi"
        pagination_buttons.append((next_text, f"filter_offers_{filter_type}_{page + 1}"))

    for btn_text, btn_data in pagination_buttons:
        nav_kb.button(text=btn_text, callback_data=btn_data)

    # Back button
    nav_kb.button(
        text="К фильтрам" if lang == "ru" else "Filtrlarga", callback_data="back_to_offers_menu"
    )

    # Adjust: items (2 per row), then pagination (3), then back (1)
    nav_kb.adjust(2, 2, len(pagination_buttons), 1)

    await callback.answer()

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=nav_kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=nav_kb.as_markup())


@router.callback_query(F.data == "back_to_offers_menu")
async def back_to_offers_menu(callback: types.CallbackQuery) -> None:
    """Return to main offers menu."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_accessible_stores(callback.from_user.id)

    all_offers = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        offers = db.get_offers_by_store(store_id, include_all=True)
        all_offers.extend(offers)

    active_count = sum(1 for o in all_offers if get_offer_field(o, "status") == "active")
    inactive_count = len(all_offers) - active_count
    low_stock_count = sum(1 for o in all_offers if _is_low_stock(o))
    expiring_count = sum(1 for o in all_offers if _is_expiring_soon(o))

    filter_kb = InlineKeyboardBuilder()
    filter_kb.button(text=f"Активные ({active_count})", callback_data="filter_offers_active_0")
    filter_kb.button(
        text=(
            f"Мало (<5) ({low_stock_count})"
            if lang == "ru"
            else f"Kam (<5) ({low_stock_count})"
        ),
        callback_data="filter_offers_low_0",
    )
    filter_kb.button(
        text=(
            f"Срок ≤2д ({expiring_count})"
            if lang == "ru"
            else f"Muddat ≤2k ({expiring_count})"
        ),
        callback_data="filter_offers_expiring_0",
    )
    filter_kb.button(
        text=f"Неактивные ({inactive_count})", callback_data="filter_offers_inactive_0"
    )
    filter_kb.button(text=f"Все ({len(all_offers)})", callback_data="filter_offers_all_0")
    filter_kb.button(text="Поиск" if lang == "ru" else "Qidirish", callback_data="search_my_offers")
    filter_kb.adjust(2, 2, 2)

    await callback.answer()
    await callback.message.edit_text(
        f"<b>{'Ваши товары' if lang == 'ru' else 'Mahsulotlaringiz'}</b>\n\n"
        f"{'Активных' if lang == 'ru' else 'Faol'}: <b>{active_count}</b>\n"
        f"{'Мало (<5)' if lang == 'ru' else 'Kam (<5)'}: <b>{low_stock_count}</b>\n"
        f"{'Срок ≤2д' if lang == 'ru' else 'Muddat ≤2k'}: <b>{expiring_count}</b>\n"
        f"{'Неактивных' if lang == 'ru' else 'Nofaol'}: <b>{inactive_count}</b>\n"
        f"{'Всего' if lang == 'ru' else 'Jami'}: <b>{len(all_offers)}</b>\n\n"
        f"{'Выберите фильтр:' if lang == 'ru' else 'Filtrni tanlang:'}",
        parse_mode="HTML",
        reply_markup=filter_kb.as_markup(),
    )


@router.callback_query(F.data == "noop")
async def noop_handler(callback: types.CallbackQuery) -> None:
    """Handle noop button press (pagination indicator)."""
    await callback.answer()


@router.callback_query(F.data == "search_my_offers")
async def search_my_offers_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start search for seller's offers."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    await state.set_state(EditOffer.search_query)
    await callback.answer()
    await callback.message.answer(
        f"{'Введите название товара для поиска:' if lang == 'ru' else 'Qidiruv uchun mahsulot nomini kiriting:'}",
        parse_mode="HTML",
    )


@router.message(EditOffer.search_query)
async def search_my_offers_process(message: types.Message, state: FSMContext) -> None:
    """Process search query for seller's offers."""
    db = get_db()
    lang = db.get_user_language(message.from_user.id)
    query = (message.text or "").strip().lower()

    # Check for cancel
    if "отмена" in query or "bekor" in query or query.startswith("/"):
        await state.clear()
        await message.answer(
            "Поиск отменен" if lang == "ru" else "Qidiruv bekor qilindi",
            reply_markup=main_menu_seller(lang),
        )
        return

    if len(query) < 2:
        await message.answer("Минимум 2 символа" if lang == "ru" else "Kamida 2 ta belgi")
        return

    await state.clear()

    stores = db.get_user_accessible_stores(message.from_user.id)
    all_offers = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        offers = db.get_offers_by_store(store_id, include_all=True)
        all_offers.extend(offers)

    # Search
    results = []
    for offer in all_offers:
        title = get_offer_field(offer, "title", "").lower()
        if query in title:
            results.append(offer)

    if not results:
        await message.answer(
            f"{'Ничего не найдено по запросу' if lang == 'ru' else 'Topilmadi'}: <b>{query}</b>",
            parse_mode="HTML",
        )
        return

    # Show results
    text = f"{'Результаты поиска' if lang == 'ru' else 'Qidiruv natijalari'}: <b>{query}</b>\n"
    text += f"{'Найдено' if lang == 'ru' else 'Topildi'}: {len(results)}\n\n"

    nav_kb = InlineKeyboardBuilder()

    for offer in results[:10]:
        offer_id = get_offer_field(offer, "offer_id")
        offer_title = get_offer_field(offer, "title", "Товар")[:25]
        price = get_offer_field(offer, "discount_price", 0)
        qty = get_offer_field(offer, "quantity", 0)
        unit = get_offer_field(offer, "unit", "шт")
        status = get_offer_field(offer, "status", "active")

        status_label = "Активен" if status == "active" else "Неактивен"
        if lang != "ru":
            status_label = "Faol" if status == "active" else "Nofaol"
        price_label = "Цена" if lang == "ru" else "Narx"
        qty_label = "Остаток" if lang == "ru" else "Miqdor"
        qty_display = format_quantity(qty, unit, lang)

        text += f"<b>{offer_title}</b>\n"
        text += f"   {status_label} | {price_label}: {price:,} | {qty_label}: {qty_display}\n"

        nav_kb.button(
            text=("Открыть " if lang == "ru" else "Ochish ") + offer_title[:15],
            callback_data=f"edit_offer_{offer_id}",
        )

    nav_kb.button(
        text="К фильтрам" if lang == "ru" else "Filtrlarga", callback_data="back_to_offers_menu"
    )
    nav_kb.adjust(2, 1)

    await message.answer(text, parse_mode="HTML", reply_markup=nav_kb.as_markup())


@router.callback_query(F.data.startswith("qty_add_"))
async def quantity_add(callback: types.CallbackQuery) -> None:
    """Increase offer quantity by 1."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    parsed = _parse_qty_delta(callback.data, 1)
    if not parsed:
        logger.error(f"Invalid offer_id in callback data: {callback.data}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    offer_id, delta = parsed

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    offer_store_id = get_offer_field(offer, "store_id")
    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    try:
        new_quantity = db.increment_offer_quantity_atomic(offer_id, delta)
    except Exception as e:
        logger.error(f"Failed to increment quantity for {offer_id}: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await update_offer_message(callback, offer_id, lang)
    await callback.answer(
        (
            f"Количество увеличено на {abs(delta)}"
            if lang == "ru"
            else f"Miqdor {abs(delta)} taga oshirildi"
        )
        + f" ({new_quantity})"
    )


@router.callback_query(F.data.startswith("qty_sub_"))
async def quantity_subtract(callback: types.CallbackQuery) -> None:
    """Decrease offer quantity by 1."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    parsed = _parse_qty_delta(callback.data, -1)
    if not parsed:
        logger.error(f"Invalid offer_id in callback data: {callback.data}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    offer_id, delta = parsed

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    offer_store_id = get_offer_field(offer, "store_id")
    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    try:
        new_quantity = db.increment_offer_quantity_atomic(offer_id, delta)
    except Exception as e:
        logger.error(f"Failed to decrement quantity for {offer_id}: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await update_offer_message(callback, offer_id, lang)

    if new_quantity == 0:
        await callback.answer(
            "Количество стало 0 - товар снят с продажи"
            if lang == "ru"
            else "Miqdor 0 bo'ldi - mahsulot savdodan olindi",
            show_alert=True,
        )
    else:
        await callback.answer(
            (
                f"Количество уменьшено на {abs(delta)}"
                if lang == "ru"
                else f"Miqdor {abs(delta)} taga kamaytirildi"
            )
            + f" ({new_quantity})"
        )


@router.callback_query(F.data.startswith("extend_offer_"))
async def extend_offer(callback: types.CallbackQuery) -> None:
    """Extend offer expiry date."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    today = datetime.now()

    builder = InlineKeyboardBuilder()
    builder.button(text=f"Сегодня {today.strftime('%d.%m')}", callback_data=f"setexp_{offer_id}_0")
    builder.button(
        text=f"Завтра {(today + timedelta(days=1)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_1",
    )
    builder.button(
        text=f"+2 дня {(today + timedelta(days=2)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_2",
    )
    builder.button(
        text=f"+3 дня {(today + timedelta(days=3)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_3",
    )
    builder.button(
        text=f"Неделя {(today + timedelta(days=7)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_7",
    )
    builder.button(text=get_text(lang, "cancel"), callback_data="cancel_extend")
    builder.adjust(2, 2, 1, 1)

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer(
        "Выберите новый срок годности" if lang == "ru" else "Yangi muddatni tanlang"
    )


@router.callback_query(F.data.startswith("setexp_"))
async def set_expiry(callback: types.CallbackQuery) -> None:
    """Set new expiry date."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    try:
        offer_id = int(parts[1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    days_part = parts[2]

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    # Verify ownership
    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    if days_part == "none":
        new_expiry = None
        db.update_offer_expiry(offer_id, None)
    else:
        try:
            days_add = int(days_part)
        except ValueError:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        new_expiry = (datetime.now() + timedelta(days=days_add)).strftime("%Y-%m-%d")
        db.update_offer_expiry(offer_id, new_expiry)

    await update_offer_message(callback, offer_id, lang)
    if new_expiry:
        await callback.answer(
            f"{'Срок продлён до' if lang == 'ru' else 'Muddat uzaytirildi'} {new_expiry}"
        )
    else:
        await callback.answer(
            "Срок снят" if lang == "ru" else "Muddat olib tashlandi"
        )


@router.callback_query(F.data == "cancel_extend")
async def cancel_extend(callback: types.CallbackQuery) -> None:
    """Cancel expiry extension."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    await callback.answer("Отменено" if lang == "ru" else "Bekor qilindi")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("deactivate_offer_"))
async def deactivate_offer(callback: types.CallbackQuery) -> None:
    """Deactivate offer."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    db.deactivate_offer(offer_id)
    await update_offer_message(callback, offer_id, lang)
    await callback.answer(
        "Товар снят с продажи" if lang == "ru" else "Mahsulot savdodan olindi"
    )


@router.callback_query(F.data.startswith("activate_offer_"))
async def activate_offer(callback: types.CallbackQuery) -> None:
    """Activate offer."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    db.activate_offer(offer_id)
    await update_offer_message(callback, offer_id, lang)
    await callback.answer(
        "Товар активирован" if lang == "ru" else "Mahsulot faollashtirildi"
    )


@router.callback_query(F.data.startswith("delete_offer_"))
async def delete_offer(callback: types.CallbackQuery) -> None:
    """Delete offer."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    try:
        db.delete_offer(offer_id)
        await callback.message.delete()
        await callback.answer("Товар удалён" if lang == "ru" else "Mahsulot o'chirildi")
    except Exception as e:
        error_msg = str(e).lower()
        if "foreign key" in error_msg or "constraint" in error_msg or "bookings" in error_msg:
            # There are active bookings for this offer
            logger.warning(f"Cannot delete offer {offer_id}: has active bookings - {e}")
            await callback.answer(
                "Невозможно удалить товар: есть активные бронирования"
                if lang == "ru"
                else "Mahsulotni o'chirib bo'lmaydi: faol bronlar mavjud",
                show_alert=True,
            )
        else:
            logger.error(f"Error deleting offer {offer_id}: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("edit_offer_"))
async def edit_offer(callback: types.CallbackQuery) -> None:
    """Show offer edit menu."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.button(
        text="Изменить цену" if lang == "ru" else "Narxni o'zgartirish",
        callback_data=f"edit_price_{offer_id}",
    )
    kb.button(
        text="Изменить количество" if lang == "ru" else "Sonini o'zgartirish",
        callback_data=f"edit_quantity_{offer_id}",
    )
    kb.button(
        text="Изменить категорию" if lang == "ru" else "Kategoriyani o'zgartirish",
        callback_data=f"edit_category_{offer_id}",
    )
    kb.button(
        text="Изменить единицу" if lang == "ru" else "Birligini o'zgartirish",
        callback_data=f"edit_unit_{offer_id}",
    )
    kb.button(
        text="Изменить срок" if lang == "ru" else "Muddatni o'zgartirish",
        callback_data=f"edit_expiry_{offer_id}",
    )
    kb.button(
        text="Изменить время" if lang == "ru" else "Vaqtni o'zgartirish",
        callback_data=f"edit_time_{offer_id}",
    )
    kb.button(
        text="Изменить описание" if lang == "ru" else "Tavsifni o'zgartirish",
        callback_data=f"edit_description_{offer_id}",
    )
    kb.button(
        text="Изменить фото" if lang == "ru" else "Rasmni o'zgartirish",
        callback_data=f"edit_photo_{offer_id}",
    )
    kb.button(
        text="Копировать" if lang == "ru" else "Nusxalash",
        callback_data=f"copy_offer_{offer_id}",
    )
    kb.button(text=get_text(lang, "back"), callback_data="back_to_offers_menu")
    kb.adjust(1)

    try:
        await callback.message.edit_reply_markup(reply_markup=kb.as_markup())
    except Exception:
        await callback.answer(get_text(lang, "edit_unavailable"), show_alert=True)

    await callback.answer()


@router.callback_query(F.data.startswith("edit_category_"))
async def edit_category_start(callback: types.CallbackQuery) -> None:
    """Start editing offer category."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=_category_keyboard(offer_id, lang).as_markup())
    except Exception:
        await callback.answer(get_text(lang, "edit_unavailable"), show_alert=True)
        return

    await callback.answer(
        "Выберите категорию" if lang == "ru" else "Kategoriya tanlang"
    )


@router.callback_query(F.data.startswith("setcat_"))
async def set_category(callback: types.CallbackQuery) -> None:
    """Set offer category."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    try:
        offer_id = int(parts[1])
        category = parts[2]
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE offers SET category = %s WHERE offer_id = %s", (category, offer_id))

    await update_offer_message(callback, offer_id, lang)
    await callback.answer(
        "Категория обновлена" if lang == "ru" else "Kategoriya yangilandi"
    )


@router.callback_query(F.data.startswith("edit_unit_"))
async def edit_unit_start(callback: types.CallbackQuery) -> None:
    """Start editing offer unit."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=_unit_keyboard(offer_id, lang).as_markup())
    except Exception:
        await callback.answer(get_text(lang, "edit_unavailable"), show_alert=True)
        return

    await callback.answer(
        "Выберите единицу" if lang == "ru" else "Birlik tanlang"
    )


@router.callback_query(F.data.startswith("setunit_"))
async def set_unit(callback: types.CallbackQuery) -> None:
    """Set offer unit."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    try:
        offer_id = int(parts[1])
        unit = parts[2]
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE offers SET unit = %s WHERE offer_id = %s", (unit, offer_id))

    await update_offer_message(callback, offer_id, lang)
    await callback.answer(
        "Единица обновлена" if lang == "ru" else "Birlik yangilandi"
    )


@router.callback_query(F.data.startswith("edit_expiry_"))
async def edit_expiry_start(callback: types.CallbackQuery) -> None:
    """Start editing offer expiry."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=_expiry_keyboard(offer_id, lang).as_markup())
    except Exception:
        await callback.answer(get_text(lang, "edit_unavailable"), show_alert=True)
        return

    await callback.answer(
        "Выберите срок" if lang == "ru" else "Muddatni tanlang"
    )


@router.callback_query(F.data.startswith("edit_expiry_custom_"))
async def edit_expiry_custom(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start custom expiry input."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[3])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    await state.update_data(offer_id=offer_id, edit_field="expiry")
    await state.set_state(EditOffer.value)

    await callback.message.answer(
        "Введите дату (ДД.ММ) или 0/без срока"
        if lang == "ru"
        else "Sana kiriting (KK.OO) yoki 0/muddatsiz",
        parse_mode="HTML",
    )
    await callback.answer()

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start editing offer price."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    current_original = int(get_offer_field(offer, "original_price", 0) or 0)
    current_discount = int(get_offer_field(offer, "discount_price", 0) or 0)

    await state.update_data(offer_id=offer_id, edit_field="price")
    await state.set_state(EditOffer.value)

    text = (
        f"{get_text(lang, 'original_price')}\n"
        f"{get_text(lang, 'discount_price')}\n"
        f"{_price_input_hint(lang)}\n"
        f"{'Текущая' if lang == 'ru' else 'Joriy'}: {current_original} -> {current_discount}"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("edit_quantity_"))
async def edit_quantity_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start editing offer quantity."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    current_qty = int(get_offer_field(offer, "quantity", 0) or 0)

    await state.update_data(offer_id=offer_id, edit_field="quantity")
    await state.set_state(EditOffer.value)

    text = (
        f"{get_text(lang, 'quantity')}\n"
        f"{'Текущая' if lang == 'ru' else 'Joriy'}: {current_qty}"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("edit_description_"))
async def edit_description_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start editing offer description."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    await state.update_data(offer_id=offer_id, edit_field="description")
    await state.set_state(EditOffer.value)

    await callback.message.answer(get_text(lang, "offer_description"), parse_mode="HTML")
    await callback.answer()


@router.message(EditOffer.value)
async def edit_offer_value(message: types.Message, state: FSMContext) -> None:
    """Handle offer edit input."""
    db = get_db()
    lang = db.get_user_language(message.from_user.id)

    if is_main_menu_button(message.text):
        await state.clear()
        return

    data = await state.get_data()
    offer_id = data.get("offer_id")
    edit_field = data.get("edit_field")
    if not offer_id or not edit_field:
        await state.clear()
        await message.answer(get_text(lang, "error_general"), reply_markup=main_menu_seller(lang))
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await state.clear()
        await message.answer(get_text(lang, "offer_not_found"), reply_markup=main_menu_seller(lang))
        return

    user_stores = db.get_user_accessible_stores(message.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await state.clear()
        await message.answer(get_text(lang, "not_your_offer"), reply_markup=main_menu_seller(lang))
        return

    if edit_field == "price":
        if "%" in (message.text or ""):
            percent_values = _extract_numbers(message.text)
            if len(percent_values) != 1:
                await message.answer(_price_input_hint(lang))
                return
            discount_percent = percent_values[0]
            if discount_percent < 0 or discount_percent > 99:
                await message.answer(_price_input_hint(lang))
                return
            original_price = int(get_offer_field(offer, "original_price", 0) or 0)
            if original_price <= 0:
                await message.answer(get_text(lang, "error_price_gt_zero"))
                return
            discount_price = int(original_price * (100 - discount_percent) / 100)
        else:
            numbers = _extract_numbers(message.text)
            if len(numbers) not in (1, 2):
                await message.answer(_price_input_hint(lang))
                return
            if len(numbers) == 1:
                original_price = int(get_offer_field(offer, "original_price", 0) or 0)
                discount_price = numbers[0]
            else:
                original_price, discount_price = numbers

            if original_price <= 0 or discount_price <= 0:
                await message.answer(get_text(lang, "error_price_gt_zero"))
                return
            if discount_price >= original_price:
                await message.answer(get_text(lang, "error_discount_less_than_original"))
                return

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE offers SET original_price = %s, discount_price = %s WHERE offer_id = %s",
                (original_price, discount_price, offer_id),
            )
    elif edit_field == "quantity":
        unit = get_offer_field(offer, "unit", "шт")
        numbers = re.findall(r"\d+(?:[.,]\d+)?", message.text or "")
        if len(numbers) != 1:
            await message.answer(get_text(lang, "error_qty_gt_zero"))
            return
        quantity = float(numbers[0].replace(",", "."))
        if unit not in DECIMAL_UNITS and quantity != int(quantity):
            await message.answer(
                "Введите целое число" if lang == "ru" else "Butun son kiriting"
            )
            return
        if quantity < 0:
            await message.answer(get_text(lang, "error_qty_gt_zero"))
            return
        db.update_offer_quantity(offer_id, quantity)
    elif edit_field == "description":
        description = (message.text or "").strip()
        if not description:
            await message.answer(get_text(lang, "error_general"))
            return
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE offers SET description = %s WHERE offer_id = %s",
                (description, offer_id),
            )
    elif edit_field == "expiry":
        try:
            expiry_value = _parse_expiry_input_text(message.text or "")
        except ValueError:
            await message.answer(
                "Формат: ДД.ММ (например 25.12)"
                if lang == "ru"
                else "Format: KK.OO (masalan 25.12)"
            )
            return
        db.update_offer_expiry(offer_id, expiry_value)
    else:
        await state.clear()
        await message.answer(get_text(lang, "error_general"), reply_markup=main_menu_seller(lang))
        return

    await state.clear()

    updated_offer = db.get_offer(offer_id)
    if updated_offer:
        await send_offer_card(message, updated_offer, lang)
    else:
        await message.answer(get_text(lang, "error_general"), reply_markup=main_menu_seller(lang))


@router.callback_query(F.data.startswith("view_offer_"))
async def view_offer(callback: types.CallbackQuery) -> None:
    """View offer details with management buttons."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    try:
        offer_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await update_offer_message(callback, offer_id, lang)
    await callback.answer()


@router.callback_query(F.data.startswith("back_to_offer_"))
async def back_to_offer(callback: types.CallbackQuery) -> None:
    """Return to offer management view."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    try:
        offer_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await update_offer_message(callback, offer_id, lang)
    await callback.answer()


@router.callback_query(F.data.startswith("edit_time_"))
async def edit_time_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start editing pickup time."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    await state.update_data(offer_id=offer_id)
    await state.set_state(EditOffer.available_from)

    available_from = get_offer_field(offer, "available_from", "")
    available_until = get_offer_field(offer, "available_until", "")

    await callback.message.answer(
        f"<b>{'Изменение времени забора' if lang == 'ru' else 'Olib ketish vaqtini o`zgartirish'}</b>\n\n"
        f"{'Текущее время' if lang == 'ru' else 'Joriy vaqt'}: {available_from} - {available_until}\n\n"
        f"{'Введите новое время начала (например: 18:00):' if lang == 'ru' else 'Yangi boshlanish vaqtini kiriting (masalan: 18:00):'}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EditOffer.available_from)
async def edit_time_from(message: types.Message, state: FSMContext) -> None:
    """Process start time."""
    db = get_db()
    lang = db.get_user_language(message.from_user.id)

    time_pattern = r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$"
    if not re.match(time_pattern, message.text.strip()):
        error_msg = (
            "Неверный формат! Введите время в формате ЧЧ:ММ (например: 18:00)"
            if lang == "ru"
            else "Noto'g'ri format! ЧЧ:ММ formatida vaqt kiriting (masalan: 18:00)"
        )
        await message.answer(error_msg)
        return

    await state.update_data(available_from=message.text.strip())
    await message.answer(
        f"{'Введите время окончания (например: 21:00):' if lang == 'ru' else 'Tugash vaqtini kiriting (masalan: 21:00):'}",
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.set_state(EditOffer.available_until)


@router.message(EditOffer.available_until)
async def edit_time_until(message: types.Message, state: FSMContext) -> None:
    """Complete time editing."""
    db = get_db()
    lang = db.get_user_language(message.from_user.id)

    time_pattern = r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$"
    if not re.match(time_pattern, message.text.strip()):
        error_msg = (
            "Неверный формат! Введите время в формате ЧЧ:ММ (например: 21:00)"
            if lang == "ru"
            else "Noto'g'ri format! ЧЧ:ММ formatida vaqt kiriting (masalan: 21:00)"
        )
        await message.answer(error_msg)
        return

    data = await state.get_data()
    offer_id = data["offer_id"]
    available_from = data["available_from"]
    available_until = message.text.strip()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE offers SET available_from = %s, available_until = %s WHERE offer_id = %s",
            (available_from, available_until, offer_id),
        )

    await message.answer(
        f"{'Время забора обновлено' if lang == 'ru' else 'Olib ketish vaqti yangilandi'}\n\n"
        f"{available_from} - {available_until}",
        reply_markup=main_menu_seller(lang),
    )
    await state.clear()


@router.callback_query(F.data.startswith("edit_photo_"))
async def edit_photo_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start editing offer photo."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    # Verify ownership
    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    await state.update_data(offer_id=offer_id)
    await state.set_state(EditOffer.photo)

    kb = InlineKeyboardBuilder()
    kb.button(
        text="Удалить фото" if lang == "ru" else "Rasmni o'chirish",
        callback_data=f"remove_photo_{offer_id}",
    )
    kb.button(text=get_text(lang, "back"), callback_data="back_to_offers_menu")
    kb.adjust(1)

    await callback.message.answer(
        f"{'Отправьте новое фото товара:' if lang == 'ru' else 'Mahsulotning yangi rasmini yuboring:'}",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_photo_"))
async def remove_photo(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Remove photo from offer."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    # Verify ownership
    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE offers SET photo_id = NULL WHERE offer_id = %s", (offer_id,))

    await state.clear()
    await callback.message.edit_text(
        f"{'Фото удалено' if lang == 'ru' else 'Rasm o`chirildi'}",
    )
    await callback.answer()


@router.message(EditOffer.photo, F.photo)
async def edit_photo_receive(message: types.Message, state: FSMContext) -> None:
    """Receive new photo for offer."""
    db = get_db()
    lang = db.get_user_language(message.from_user.id)

    data = await state.get_data()
    offer_id = data.get("offer_id")

    if not offer_id:
        await message.answer("Error: offer not found")
        await state.clear()
        return

    photo_id = message.photo[-1].file_id

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE offers SET photo_id = %s WHERE offer_id = %s", (photo_id, offer_id))

    await message.answer(
        f"{'Фото обновлено' if lang == 'ru' else 'Rasm yangilandi'}",
        reply_markup=main_menu_seller(lang),
    )
    await state.clear()


@router.callback_query(F.data.startswith("duplicate_"))
async def duplicate_offer(callback: types.CallbackQuery) -> None:
    """Duplicate offer."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    offer_id = int(callback.data.split("_")[1])
    offer = db.get_offer(offer_id)

    if offer:
        unit_val = get_offer_field(offer, "unit", "шт")
        if not unit_val or not isinstance(unit_val, str) or len(unit_val) > 5:
            unit_val = "шт"
        category_val = get_offer_field(offer, "category", "other") or "other"

        db.add_offer(
            store_id=get_offer_field(offer, "store_id"),
            title=get_offer_field(offer, "title"),
            description=get_offer_field(offer, "description"),
            original_price=get_offer_field(offer, "original_price"),
            discount_price=get_offer_field(offer, "discount_price"),
            quantity=get_offer_field(offer, "quantity"),
            available_from=get_offer_field(offer, "available_from"),
            available_until=get_offer_field(offer, "available_until"),
            photo_id=get_offer_field(offer, "photo"),
            expiry_date=get_offer_field(offer, "expiry_date"),
            unit=unit_val,
            category=category_val,
        )
        await callback.answer(get_text(lang, "duplicated"), show_alert=True)
