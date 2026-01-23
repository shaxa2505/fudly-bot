"""Seller offer creation handlers - step-by-step process with quick buttons."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.utils import get_store_field
from app.keyboards import (
    discount_keyboard,
    expiry_keyboard,
    photo_keyboard,
    product_categories_keyboard,
    quantity_keyboard,
    unit_type_keyboard,
)
from database_protocol import DatabaseProtocol
from handlers.common.states import CreateOffer
from handlers.common.utils import is_main_menu_button
from localization import get_text, normalize_category
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router()


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


# Category names for display
CATEGORY_NAMES = {
    "ru": {
        "bakery": "Выпечка",
        "dairy": "Молочные",
        "meat": "Мясные",
        "fruits": "Фрукты",
        "vegetables": "Овощи",
        "drinks": "Напитки",
        "snacks": "Снеки",
        "frozen": "Замороженное",
        "sweets": "Сладости",
        "other": "Другое",
    },
    "uz": {
        "bakery": "Pishiriq",
        "dairy": "Sut mahsulotlari",
        "meat": "Go'sht",
        "fruits": "Mevalar",
        "vegetables": "Sabzavotlar",
        "drinks": "Ichimliklar",
        "snacks": "Gaz. ovqatlar",
        "frozen": "Muzlatilgan",
        "sweets": "Shirinliklar",
        "other": "Boshqa",
    },
}

ALLOWED_CATEGORIES = {
    "bakery",
    "dairy",
    "meat",
    "fruits",
    "vegetables",
    "drinks",
    "snacks",
    "frozen",
    "sweets",
    "other",
}

UNIT_ALIASES = {
    "шт": "шт",
    "штука": "шт",
    "штук": "шт",
    "dona": "шт",
    "pcs": "шт",
    "piece": "шт",
    "уп": "уп",
    "упак": "уп",
    "упаковка": "уп",
    "qadoq": "уп",
    "кг": "кг",
    "kg": "кг",
    "килограмм": "кг",
    "г": "г",
    "гр": "г",
    "g": "г",
    "gram": "г",
    "л": "л",
    "l": "л",
    "литр": "л",
    "ml": "мл",
    "мл": "мл",
    "milliliter": "мл",
}

DECIMAL_UNITS = {"кг", "л"}


def get_category_name(category: str, lang: str) -> str:
    """Get localized category name."""
    return CATEGORY_NAMES.get(lang, CATEGORY_NAMES["ru"]).get(category, category)


def build_progress_text(data: dict, lang: str, current_step: int) -> str:
    """Build progress indicator showing completed steps."""
    steps = [
        ("Категория", "Kategoriya", data.get("category")),
        ("Название", "Nomi", data.get("title")),
        ("Описание", "Tavsif", data.get("description")),
        ("Цена", "Narx", data.get("original_price")),
        ("Скидка", "Chegirma", data.get("discount_percent")),
        ("Единица", "Birlik", data.get("unit")),
        ("Количество", "Miqdor", data.get("quantity")),
        ("Срок", "Muddat", data.get("expiry_date")),
        ("Фото", "Rasm", data.get("photo")),
    ]

    lines = []
    for i, (ru_name, uz_name, value) in enumerate(steps, 1):
        name = ru_name if lang == "ru" else uz_name
        if i < current_step:
            if i == 1 and value:  # Category
                display_value = get_category_name(value, lang)
            elif i == 4 and value is not None:  # Price
                display_value = f"{int(value):,} сум"
            elif i == 5 and value is not None:  # Discount (0 allowed)
                display_value = f"{value}%"
            elif i == 6 and value:  # Unit
                display_value = value
            elif i == 7 and value is not None:  # Quantity
                unit = data.get("unit", "шт")
                display_value = f"{value} {unit}"
            elif i == 8:  # Expiry optional
                if value is None and "expiry_date" in data:
                    display_value = "Без срока" if lang == "ru" else "Muddatsiz"
                elif value:
                    display_value = str(value)[:20]
                else:
                    display_value = "-"
            elif value:
                display_value = str(value)[:20]
            else:
                display_value = "-"
            lines.append(f"[x] {name}: <b>{display_value}</b>")
        elif i == current_step:
            lines.append(f"[>] <b>{name}</b>")
        else:
            lines.append(f"[ ] {name}")

    return "\n".join(lines)


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


def _parse_expiry_input(value: str) -> str | None:
    """Parse expiry input into ISO date or None (no expiry)."""
    if not value:
        return None

    raw = value.strip().lower()
    if not raw or raw in NO_EXPIRY_TOKENS:
        return None

    # Days offset (e.g. 3, +3, 3д, 3 кун)
    day_match = re.fullmatch(
        r"\+?\s*(\d{1,3})\s*(д|дн|дня|дней|кун|kun|day|days)?",
        raw,
    )
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


def _normalize_unit_input(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().lower().replace(".", "").replace(" ", "")
    return UNIT_ALIASES.get(raw)


def _normalize_category_input(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    raw_lower = raw.lower()
    if raw_lower in ALLOWED_CATEGORIES:
        return raw_lower
    normalized = normalize_category(raw)
    return normalized if normalized in ALLOWED_CATEGORIES else None


def _parse_price_value(value: str) -> float:
    numbers = re.findall(r"\d+(?:[.,]\d+)?", value or "")
    if not numbers:
        raise ValueError("Invalid price")
    return float(numbers[0].replace(",", "."))


def _parse_discount_value(original_price: float, raw: str | None) -> tuple[int, float]:
    if not raw or not raw.strip():
        return 0, original_price

    if "%" in raw:
        percent_value = _parse_price_value(raw)
        discount_percent = int(percent_value)
        if discount_percent < 0 or discount_percent > 99:
            raise ValueError("Invalid discount percent")
        discount_price = original_price * (1 - discount_percent / 100)
        return discount_percent, discount_price

    discount_price = _parse_price_value(raw)
    if discount_price >= original_price:
        if discount_price <= 99:
            discount_percent = int(discount_price)
            discount_price = original_price * (1 - discount_percent / 100)
            return discount_percent, discount_price
        raise ValueError("Discount price must be less than original")
    discount_percent = int((1 - discount_price / original_price) * 100)
    return discount_percent, discount_price


def _parse_quantity_value(raw: str | None, unit: str) -> float:
    if not raw or not raw.strip():
        return 1.0 if unit in DECIMAL_UNITS else 1
    numbers = re.findall(r"\d+(?:[.,]\d+)?", raw)
    if not numbers:
        raise ValueError("Invalid quantity")
    quantity = float(numbers[0].replace(",", "."))
    if quantity <= 0:
        raise ValueError("Invalid quantity")
    if unit not in DECIMAL_UNITS and quantity != int(quantity):
        raise ValueError("Quantity must be integer")
    return quantity


def _quick_add_instructions(lang: str) -> str:
    """Return quick add instructions text."""
    if lang == "ru":
        return (
            "<b>⚡ Быстрое добавление</b>\n\n"
            "Формат:\n"
            "Название | Цена | Скидка | Кол-во | Ед | Срок | Категория | Описание\n\n"
            "Можно отправить текстом или подписью к фото.\n"
            "Поля после цены можно пропускать.\n"
            "Скидка: % или цена со скидкой (30% или 35000)\n"
            "Срок: ДД.ММ, ДД.ММ.ГГГГ, +3 или 0/без срока\n\n"
            "Пример:\n"
            "<code>Хлеб | 12000 | 9000 | 10 | шт | 25.12 | Выпечка | свежий</code>"
        )
    return (
        "<b>⚡ Tez qo`shish</b>\n\n"
        "Format:\n"
        "Nomi | Narx | Chegirma | Miqdor | Birlik | Muddat | Kategoriya | Tavsif\n\n"
        "Matn yoki surat osti (caption) bilan yuboring.\n"
        "Narxdan keyingi maydonlar ixtiyoriy.\n"
        "Chegirma: % yoki chegirmali narx (30% yoki 35000)\n"
        "Muddat: KK.OO, KK.OO.YYYY, +3 yoki 0/muddatsiz\n\n"
        "Misol:\n"
        "<code>Non | 12000 | 9000 | 10 | dona | 25.12 | Pishiriq | yangi</code>"
    )


def _parse_quick_input(text: str) -> dict[str, Any]:
    """Parse quick add input into offer data."""
    parts = [part.strip() for part in (text or "").split("|")]
    if len(parts) < 2:
        raise ValueError("Not enough data")

    if len(parts) > 8:
        parts = parts[:7] + [" | ".join(parts[7:])]

    title = parts[0]
    if not title:
        raise ValueError("Missing title")

    original_price = _parse_price_value(parts[1])

    discount_raw = parts[2] if len(parts) > 2 else ""
    unit_raw = parts[4] if len(parts) > 4 else ""
    unit = _normalize_unit_input(unit_raw) if unit_raw else "шт"
    if unit_raw and not unit:
        raise ValueError("Invalid unit")

    quantity_raw = parts[3] if len(parts) > 3 else ""
    quantity = _parse_quantity_value(quantity_raw, unit)

    expiry_raw = parts[5] if len(parts) > 5 else ""
    expiry_date = _parse_expiry_input(expiry_raw) if expiry_raw.strip() else None

    category_raw = parts[6] if len(parts) > 6 else ""
    category = _normalize_category_input(category_raw) if category_raw else "other"
    if category_raw and not category:
        raise ValueError("Invalid category")

    description = parts[7].strip() if len(parts) > 7 else ""

    discount_percent, discount_price = _parse_discount_value(original_price, discount_raw)

    return {
        "title": title,
        "description": description,
        "original_price": original_price,
        "discount_price": discount_price,
        "discount_percent": discount_percent,
        "quantity": quantity,
        "unit": unit,
        "expiry_date": expiry_date,
        "category": category,
    }


# ============ STEP 1: Start & Category ============


async def _prompt_quick_input(target: types.Message, state: FSMContext, lang: str) -> None:
    """Prompt for quick add input."""
    data = await state.get_data()
    store_name = data.get("store_name")

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "cancel"), callback_data="create_cancel")

    header = f"<b>{store_name}</b>\n\n" if store_name else ""
    await target.answer(
        header + _quick_add_instructions(lang),
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(CreateOffer.quick_input)


@router.message(
    (F.text == get_text("ru", "quick_add")) | (F.text == get_text("uz", "quick_add"))
)
async def quick_add_start(message: types.Message, state: FSMContext) -> None:
    """Start quick add flow."""
    await state.clear()

    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    stores = [
        s
        for s in db.get_user_accessible_stores(message.from_user.id)
        if get_store_field(s, "status") in ("active", "approved")
    ]

    if not stores:
        await message.answer(get_text(lang, "no_approved_stores"))
        return

    if len(stores) > 1:
        builder = InlineKeyboardBuilder()
        for store in stores:
            store_id = get_store_field(store, "store_id")
            store_name = get_store_field(store, "name", "Магазин")
            if store_id is None:
                continue
            builder.button(text=store_name[:30], callback_data=f"quick_store_{store_id}")
        builder.adjust(1)

        await message.answer(
            get_text(lang, "choose_store"),
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
        await state.set_state(CreateOffer.store)
        return

    store_id = get_store_field(stores[0], "store_id")
    store_name = get_store_field(stores[0], "name", "Магазин")
    await state.update_data(store_id=store_id, store_name=store_name)
    await _prompt_quick_input(message, state, lang)


@router.callback_query(F.data.startswith("quick_store_"))
async def quick_store_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Store selected for quick add."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    try:
        store_id = int(callback.data.replace("quick_store_", ""))
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    stores = [
        s
        for s in db.get_user_accessible_stores(callback.from_user.id)
        if get_store_field(s, "status") in ("active", "approved")
    ]
    store = next((s for s in stores if get_store_field(s, "store_id") == store_id), None)
    if not store:
        await callback.answer(get_text(lang, "no_approved_stores"), show_alert=True)
        return

    store_name = get_store_field(store, "name", "Магазин")
    await state.update_data(store_id=store_id, store_name=store_name)
    await callback.answer()
    await _prompt_quick_input(callback.message, state, lang)


@router.message(F.text.contains("Добавить") | F.text.contains("Qo'shish"))
async def add_offer_start(message: types.Message, state: FSMContext) -> None:
    """Start offer creation - select store and category."""
    # Clear any previous FSM state
    await state.clear()

    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)

    # Get only APPROVED stores (owned + admin access)
    stores = [
        s
        for s in db.get_user_accessible_stores(message.from_user.id)
        if get_store_field(s, "status") in ("active", "approved")
    ]

    if not stores:
        await message.answer(get_text(lang, "no_approved_stores"))
        return

    if len(stores) > 1:
        builder = InlineKeyboardBuilder()
        for store in stores:
            store_id = get_store_field(store, "store_id")
            store_name = get_store_field(store, "name", "Магазин")
            if store_id is None:
                continue
            builder.button(text=store_name[:30], callback_data=f"create_store_{store_id}")
        builder.adjust(1)

        await message.answer(
            get_text(lang, "choose_store"),
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
        await state.set_state(CreateOffer.store)
        return

    # Auto-select first store
    store_id = get_store_field(stores[0], "store_id")
    store_name = get_store_field(stores[0], "name", "Магазин")
    await state.update_data(store_id=store_id, store_name=store_name)

    header = (
        f"<b>{store_name}</b>\n\n"
        f"<b>{'Добавить товар' if lang == 'ru' else 'Mahsulot qo`shish'}</b>\n\n"
    )

    step_text = (
        "<b>Шаг 1/9:</b> Выберите категорию"
        if lang == "ru"
        else "<b>1/9-qadam:</b> Kategoriyani tanlang"
    )

    await message.answer(
        header + step_text,
        parse_mode="HTML",
        reply_markup=product_categories_keyboard(lang),
    )
    await state.set_state(CreateOffer.category)


@router.callback_query(F.data.startswith("create_store_"))
async def create_store_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Store selected for offer creation."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    try:
        store_id = int(callback.data.replace("create_store_", ""))
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    stores = [
        s
        for s in db.get_user_accessible_stores(callback.from_user.id)
        if get_store_field(s, "status") in ("active", "approved")
    ]
    store = next((s for s in stores if get_store_field(s, "store_id") == store_id), None)
    if not store:
        await callback.answer(get_text(lang, "no_approved_stores"), show_alert=True)
        return

    store_name = get_store_field(store, "name", "Магазин")
    await state.update_data(store_id=store_id, store_name=store_name)

    header = (
        f"<b>{store_name}</b>\n\n"
        f"<b>{'Добавить товар' if lang == 'ru' else 'Mahsulot qo`shish'}</b>\n\n"
    )
    step_text = (
        "<b>Шаг 1/9:</b> Выберите категорию"
        if lang == "ru"
        else "<b>1/9-qadam:</b> Kategoriyani tanlang"
    )

    await callback.message.edit_text(
        header + step_text,
        parse_mode="HTML",
        reply_markup=product_categories_keyboard(lang),
    )
    await state.set_state(CreateOffer.category)
    await callback.answer()


@router.message(CreateOffer.quick_input, F.text)
async def quick_input_entered(message: types.Message, state: FSMContext) -> None:
    """Process quick add input from text."""
    if not db:
        await message.answer("System error")
        return

    if is_main_menu_button(message.text):
        await state.clear()
        return

    lang = db.get_user_language(message.from_user.id)

    try:
        offer_data = _parse_quick_input(message.text)
    except Exception:
        await message.answer(_quick_add_instructions(lang), parse_mode="HTML")
        return

    await state.update_data(**offer_data, photo=None)
    await _finalize_offer(message, state, lang)


@router.message(CreateOffer.quick_input, F.photo)
async def quick_input_photo(message: types.Message, state: FSMContext) -> None:
    """Process quick add input from photo caption."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    caption = message.caption or ""

    if not caption.strip():
        await message.answer(
            _quick_add_instructions(lang),
            parse_mode="HTML",
        )
        return

    try:
        offer_data = _parse_quick_input(caption)
    except Exception:
        await message.answer(_quick_add_instructions(lang), parse_mode="HTML")
        return

    photo_id = message.photo[-1].file_id
    await state.update_data(**offer_data, photo=photo_id)
    await _finalize_offer(message, state, lang)


@router.callback_query(F.data.startswith("product_cat_"))
async def category_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Category selected - ask for title."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    category = callback.data.replace("product_cat_", "")

    await state.update_data(category=category)
    data = await state.get_data()

    # Build back/cancel keyboard
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "back"), callback_data="create_back_category")
    builder.button(text=get_text(lang, "cancel"), callback_data="create_cancel")
    builder.adjust(2)

    progress = build_progress_text({**data, "category": category}, lang, 2)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Введите название товара:' if lang == 'ru' else 'Mahsulot nomini kiriting:'}</b>\n\n"
        f"{'Пример: Чай Ахмад Английский 100г' if lang == 'ru' else 'Misol: Ahmad English Tea 100g'}"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(CreateOffer.title)
    await callback.answer()


# ============ STEP 2: Title ============


@router.message(CreateOffer.title, F.text)
async def title_entered(message: types.Message, state: FSMContext) -> None:
    """Title entered - ask for description."""
    if not db:
        await message.answer("System error")
        return

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(message.text):
        await state.clear()
        return

    lang = db.get_user_language(message.from_user.id)
    title = message.text.strip()

    if len(title) < 2:
        await message.answer(
            "Название слишком короткое" if lang == "ru" else "Nom juda qisqa"
        )
        return

    if len(title) > 100:
        await message.answer(
            "Название слишком длинное (макс 100 символов)"
            if lang == "ru"
            else "Nom juda uzun (maks 100 belgi)"
        )
        return

    await state.update_data(title=title)
    data = await state.get_data()

    # Build back/skip/cancel keyboard
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "back"), callback_data="create_back_title")
    builder.button(
        text="Пропустить" if lang == "ru" else "O'tkazib yuborish",
        callback_data="create_skip_description",
    )
    builder.button(text=get_text(lang, "cancel"), callback_data="create_cancel")
    builder.adjust(2, 1)

    progress = build_progress_text(data, lang, 3)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Введите описание (можно пропустить):' if lang == 'ru' else 'Tavsif kiriting (o`tqazib yuborish mumkin):'}</b>\n\n"
        f"{'Пример: свежий, 450г' if lang == 'ru' else 'Misol: yangi, 450g'}"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(CreateOffer.description)


# ============ STEP 3: Description ============


async def _prompt_price(target: types.Message, state: FSMContext, lang: str) -> None:
    """Ask for original price (with flexible input)."""
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "back"), callback_data="create_back_description")
    builder.button(text=get_text(lang, "cancel"), callback_data="create_cancel")
    builder.adjust(2)

    progress = build_progress_text(data, lang, 4)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Введите цену (до скидки):' if lang == 'ru' else 'Narxni kiriting (chegirmadan oldin):'}</b>\n"
        f"{'Можно: 50000 или 50000 35000 (со скидкой).' if lang == 'ru' else 'Misol: 50000 yoki 50000 35000 (chegirmali).'}"
    )

    await target.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(CreateOffer.original_price)


@router.message(CreateOffer.description, F.text)
async def description_entered(message: types.Message, state: FSMContext) -> None:
    """Description entered - ask for price."""
    if not db:
        await message.answer("System error")
        return

    if is_main_menu_button(message.text):
        await state.clear()
        return

    lang = db.get_user_language(message.from_user.id)
    description = message.text.strip()

    if description.lower() in ("-", "нет", "без описания", "no"):
        description = ""

    await state.update_data(description=description)
    await _prompt_price(message, state, lang)


@router.callback_query(F.data == "create_skip_description")
async def skip_description(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Skip description and move to price."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    await state.update_data(description="")
    await _prompt_price(callback.message, state, lang)
    await callback.answer()


# ============ STEP 4: Price ============


@router.message(CreateOffer.original_price, F.text)
async def price_entered(message: types.Message, state: FSMContext) -> None:
    """Price entered - ask for discount."""
    if not db:
        await message.answer("System error")
        return

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(message.text):
        await state.clear()
        return

    lang = db.get_user_language(message.from_user.id)

    raw_text = message.text.strip()
    numbers = re.findall(r"\d+(?:[.,]\d+)?", raw_text)
    if not numbers:
        await message.answer(
            "Введите число. Пример: 50000" if lang == "ru" else "Raqam kiriting. Misol: 50000"
        )
        return

    def _to_number(value: str) -> float:
        return float(value.replace(",", "."))

    try:
        if len(numbers) >= 2:
            original = _to_number(numbers[0])
            discount_price = _to_number(numbers[1])
            if original <= 0 or discount_price <= 0 or discount_price >= original:
                raise ValueError

            discount_percent = int((1 - discount_price / original) * 100)
            await state.update_data(
                original_price=original,
                discount_price=discount_price,
                discount_percent=discount_percent,
            )
            await _go_to_unit_step(message, state, lang)
            return

        original = _to_number(numbers[0])
        if original <= 0:
            raise ValueError

        await state.update_data(original_price=original)
        data = await state.get_data()
        progress = build_progress_text(data, lang, 5)

        text = (
            f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
            f"{progress}\n\n"
            f"<b>{'Выберите скидку или отправьте цену со скидкой:' if lang == 'ru' else 'Chegirma tanlang yoki chegirmali narxni yuboring:'}</b>"
        )

        await message.answer(text, parse_mode="HTML", reply_markup=discount_keyboard(lang))
        await state.set_state(CreateOffer.discount_price)
    except ValueError:
        await message.answer(
            "Неверный формат. Пример: 50000 или 50000 35000"
            if lang == "ru"
            else "Noto`g`ri format. Misol: 50000 yoki 50000 35000"
        )


@router.callback_query(CreateOffer.discount_price, F.data.startswith("discount_"))
async def discount_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Discount selected via button."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    discount_data = callback.data.replace("discount_", "")

    if discount_data == "custom":
        # Ask for custom discount
        builder = InlineKeyboardBuilder()
        builder.button(text=get_text(lang, "back"), callback_data="create_back_price")

        await callback.message.edit_text(
            "<b>"
            + ("Введите скидку (%):" if lang == "ru" else "Chegirmani kiriting (%):")
            + "</b>\n\n"
            + ("Пример: 35" if lang == "ru" else "Misol: 35"),
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
        await callback.answer()
        return

    discount_percent = int(discount_data)
    await _process_discount(callback.message, state, lang, discount_percent)
    await callback.answer()


@router.message(CreateOffer.discount_price, F.text)
async def discount_entered(message: types.Message, state: FSMContext) -> None:
    """Custom discount or final price entered."""
    if not db:
        await message.answer("System error")
        return

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(message.text):
        await state.clear()
        return

    lang = db.get_user_language(message.from_user.id)

    raw_text = message.text.strip()
    numbers = re.findall(r"\d+(?:[.,]\d+)?", raw_text)
    if not numbers:
        await message.answer(
            "Введите число или процент. Пример: 30% или 35000"
            if lang == "ru"
            else "Foiz yoki narx yuboring. Misol: 30% yoki 35000"
        )
        return

    try:
        data = await state.get_data()
        original_price = float(data.get("original_price", 0))

        if "%" in raw_text:
            discount_percent = int(float(numbers[0]))
            if discount_percent < 0 or discount_percent > 99:
                raise ValueError
            await _process_discount(message, state, lang, discount_percent)
            return

        discount_price = float(numbers[0].replace(",", "."))
        if original_price <= 0 or discount_price <= 0:
            raise ValueError
        if discount_price >= original_price:
            # If looks like percent without %, treat as percent
            if discount_price <= 99:
                await _process_discount(message, state, lang, int(discount_price))
                return
            raise ValueError

        discount_percent = int((1 - discount_price / original_price) * 100)
        await state.update_data(discount_percent=discount_percent, discount_price=discount_price)
        await _go_to_unit_step(message, state, lang)
    except ValueError:
        await message.answer(
            "Неверный формат. Пример: 30% или 35000"
            if lang == "ru"
            else "Noto`g`ri format. Misol: 30% yoki 35000"
        )


async def _go_to_unit_step(target: types.Message, state: FSMContext, lang: str) -> None:
    """Move to unit selection step."""
    data = await state.get_data()
    progress = build_progress_text(data, lang, 8)

    discount_price = data.get("discount_price")
    price_line = ""
    if discount_price:
        price_line = (
            f"Цена со скидкой: <b>{int(discount_price):,} сум</b>\n\n"
            if lang == "ru"
            else f"Chegirmali narx: <b>{int(discount_price):,} sum</b>\n\n"
        )

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"{price_line}"
        f"<b>{'Выберите единицу измерения:' if lang == 'ru' else 'O`lchov birligini tanlang:'}</b>"
    )

    await target.answer(text, parse_mode="HTML", reply_markup=unit_type_keyboard(lang))
    await state.set_state(CreateOffer.unit_type)


async def _process_discount(
    target: types.Message, state: FSMContext, lang: str, discount_percent: int
) -> None:
    """Process discount and move to unit type step."""
    data = await state.get_data()
    original_price = data.get("original_price", 0)
    discount_price = original_price * (1 - discount_percent / 100)

    await state.update_data(discount_percent=discount_percent, discount_price=discount_price)
    await _go_to_unit_step(target, state, lang)


# ============ STEP 6: Unit Type ============


@router.callback_query(CreateOffer.unit_type, F.data.startswith("unit_type_"))
async def unit_type_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Unit type selected via button."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    unit = callback.data.replace("unit_type_", "")

    await state.update_data(unit=unit)
    data = await state.get_data()

    progress = build_progress_text(data, lang, 6)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Выберите количество:' if lang == 'ru' else 'Miqdorni tanlang:'}</b>"
    )

    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=quantity_keyboard(lang, unit)
    )
    await state.set_state(CreateOffer.quantity)
    await callback.answer()


# ============ STEP 7: Quantity ============


@router.callback_query(CreateOffer.quantity, F.data.startswith("quantity_"))
async def quantity_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Quantity selected via button."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    qty_data = callback.data.replace("quantity_", "")
    data = await state.get_data()
    unit = data.get("unit", "шт")

    if qty_data == "custom":
        # Ask for custom quantity
        builder = InlineKeyboardBuilder()
        builder.button(text=get_text(lang, "back"), callback_data="create_back_unit")

        example = "Пример: 2.5" if unit in DECIMAL_UNITS else "Пример: 25"
        example_uz = "Misol: 2.5" if unit in DECIMAL_UNITS else "Misol: 25"

        await callback.message.edit_text(
            "<b>"
            + ("Введите количество:" if lang == "ru" else "Miqdorni kiriting:")
            + "</b>\n\n"
            + (example if lang == "ru" else example_uz),
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
        await callback.answer()
        return

    quantity = float(qty_data) if unit in DECIMAL_UNITS else int(float(qty_data))
    await _process_quantity(callback.message, state, lang, quantity)
    await callback.answer()


@router.message(CreateOffer.quantity, F.text)
async def quantity_entered(message: types.Message, state: FSMContext) -> None:
    """Custom quantity entered."""
    if not db:
        await message.answer("System error")
        return

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(message.text):
        await state.clear()
        return

    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()
    unit = data.get("unit", "шт")

    try:
        quantity_text = message.text.strip().replace(",", ".")
        quantity = float(quantity_text)
        if quantity <= 0:
            raise ValueError("Invalid quantity")
        # For non-decimal units, ensure integer
        if unit not in DECIMAL_UNITS and quantity != int(quantity):
            await message.answer(
                "Введите целое число для выбранной единицы"
                if lang == "ru"
                else "Tanlangan birlik uchun butun son kiriting"
            )
            return
    except ValueError:
        await message.answer(
            "Введите положительное число" if lang == "ru" else "Musbat raqam kiriting"
        )
        return

    await _process_quantity(message, state, lang, quantity)


async def _process_quantity(
    target: types.Message, state: FSMContext, lang: str, quantity: float
) -> None:
    """Process quantity and move to expiry step."""
    await state.update_data(quantity=quantity)
    data = await state.get_data()

    progress = build_progress_text(data, lang, 7)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Выберите срок годности:' if lang == 'ru' else 'Yaroqlilik muddatini tanlang:'}</b>"
    )

    await target.answer(text, parse_mode="HTML", reply_markup=expiry_keyboard(lang))
    await state.set_state(CreateOffer.expiry_date)


# ============ STEP 8: Expiry Date ============


@router.callback_query(CreateOffer.expiry_date, F.data.startswith("expiry_"))
async def expiry_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Expiry date selected via button."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    expiry_data = callback.data.replace("expiry_", "")

    if expiry_data == "custom":
        # Ask for custom date
        builder = InlineKeyboardBuilder()
        builder.button(text=get_text(lang, "back"), callback_data="create_back_quantity")

        await callback.message.edit_text(
            "<b>"
            + ("Введите дату (ДД.ММ):" if lang == "ru" else "Sanani kiriting (KK.OO):")
            + "</b>\n\n"
            + ("Пример: 25.12" if lang == "ru" else "Misol: 25.12"),
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
        await callback.answer()
        return

    if expiry_data == "none":
        await _process_expiry(callback.message, state, lang, None)
        await callback.answer()
        return

    days = int(expiry_data)
    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    await _process_expiry(callback.message, state, lang, expiry_date)
    await callback.answer()


@router.message(CreateOffer.expiry_date, F.text)
async def expiry_entered(message: types.Message, state: FSMContext) -> None:
    """Custom expiry date entered."""
    if not db:
        await message.answer("System error")
        return

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(message.text):
        await state.clear()
        return

    lang = db.get_user_language(message.from_user.id)

    try:
        expiry_date = _parse_expiry_input(message.text)
    except ValueError:
        await message.answer(
            "Формат: ДД.ММ (например 25.12)"
            if lang == "ru"
            else "Format: KK.OO (masalan 25.12)"
        )
        return

    await _process_expiry(message, state, lang, expiry_date)


async def _process_expiry(
    target: types.Message, state: FSMContext, lang: str, expiry_date: str | None
) -> None:
    """Process expiry date and move to photo step."""
    await state.update_data(expiry_date=expiry_date)
    data = await state.get_data()

    progress = build_progress_text(data, lang, 9)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Отправьте фото товара или пропустите:' if lang == 'ru' else 'Mahsulot rasmini yuboring yoki o`tkazib yuboring:'}</b>"
    )

    await target.answer(text, parse_mode="HTML", reply_markup=photo_keyboard(lang))
    await state.set_state(CreateOffer.photo)


# ============ STEP 9: Photo ============


@router.message(CreateOffer.photo, F.photo)
async def photo_received(message: types.Message, state: FSMContext) -> None:
    """Photo received - finalize offer."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    photo_id = message.photo[-1].file_id
    await state.update_data(photo=photo_id)
    await _finalize_offer(message, state, lang)


@router.callback_query(F.data == "create_skip_photo")
async def skip_photo(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Skip photo and finalize."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    # Answer callback first to remove "loading" indicator
    await callback.answer()

    lang = db.get_user_language(callback.from_user.id)
    await state.update_data(photo=None)
    await _finalize_offer(callback.message, state, lang)


async def _finalize_offer(target: types.Message, state: FSMContext, lang: str) -> None:
    """Save offer to database."""
    from datetime import datetime, timedelta

    data = await state.get_data()

    try:
        if not db:
            raise ValueError("Database not initialized")

        unit = data.get("unit", "шт")
        quantity = data["quantity"]

        def _format_qty(value: Any, unit_value: str) -> str:
            try:
                qty = float(value)
                if unit_value in DECIMAL_UNITS:
                    qty_str = f"{qty:.2f}".rstrip("0").rstrip(".")
                else:
                    qty_str = str(int(qty))
            except (TypeError, ValueError):
                qty_str = str(value)
            return f"{qty_str} {unit_value}"

        qty_display = _format_qty(quantity, unit)

        # Prepare times in ISO format (will be parsed by Pydantic)
        now = datetime.now()
        available_from = now.replace(hour=8, minute=0, second=0, microsecond=0)
        available_until = now.replace(hour=23, minute=0, second=0, microsecond=0)

        # Store prices directly as entered
        original_price_value = int(data["original_price"])
        discount_price_value = int(data["discount_price"])

        offer_id = db.add_offer(
            store_id=data["store_id"],
            title=data["title"],
            description=data.get("description") or data["title"],
            original_price=original_price_value,
            discount_price=discount_price_value,
            quantity=quantity,
            available_from=available_from.time().isoformat(),  # ISO time format
            available_until=available_until.time().isoformat(),  # ISO time format
            photo_id=data.get("photo"),  # Unified parameter name
            expiry_date=data.get("expiry_date"),  # Will be parsed by Pydantic
            unit=unit,
            category=data.get("category", "other"),
        )

        discount_percent = data.get("discount_percent", 0)

        expiry_display = data.get("expiry_date")
        if not expiry_display:
            expiry_display = "Без срока" if lang == "ru" else "Muddatsiz"

        success_text = (
            f"<b>{'Товар создан' if lang == 'ru' else 'Mahsulot yaratildi'}</b>\n\n"
            f"{data['title']}\n"
            f"{'Цена' if lang == 'ru' else 'Narx'}: {int(data['original_price']):,} -> {int(data['discount_price']):,} сум (-{discount_percent}%)\n"
            f"{'Количество' if lang == 'ru' else 'Miqdor'}: {qty_display}\n"
            f"{'Срок годности' if lang == 'ru' else 'Yaroqlilik muddati'}: {expiry_display}\n\n"
        )

        # Add quick action buttons
        builder = InlineKeyboardBuilder()
        builder.button(
            text="Еще товар" if lang == "ru" else "Yana mahsulot",
            callback_data="create_another",
        )
        builder.button(
            text="Копировать" if lang == "ru" else "Nusxalash",
            callback_data=f"copy_offer_{offer_id}",
        )
        builder.button(
            text="Мои товары" if lang == "ru" else "Mahsulotlarim",
            callback_data="go_my_offers",
        )
        builder.adjust(2, 1)

        await target.answer(success_text, parse_mode="HTML", reply_markup=builder.as_markup())

    except Exception as e:
        logger.error(f"Error creating offer: {e}")
        await target.answer(
            "Ошибка при сохранении. Попробуйте снова."
            if lang == "ru"
            else "Saqlashda xatolik. Qayta urinib ko'ring."
        )
    finally:
        await state.clear()


# ============ Navigation Callbacks ============


@router.callback_query(F.data == "create_back_title")
async def back_to_title(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to title input."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "back"), callback_data="create_back_category")
    builder.button(text=get_text(lang, "cancel"), callback_data="create_cancel")
    builder.adjust(2)

    progress = build_progress_text(data, lang, 2)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Введите название товара:' if lang == 'ru' else 'Mahsulot nomini kiriting:'}</b>\n\n"
        f"{'Пример: Чай Ахмад Английский 100г' if lang == 'ru' else 'Misol: Ahmad English Tea 100g'}"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(CreateOffer.title)
    await callback.answer()


@router.callback_query(F.data == "create_back_description")
async def back_to_description(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to description input."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "back"), callback_data="create_back_title")
    builder.button(
        text="Пропустить" if lang == "ru" else "O'tkazib yuborish",
        callback_data="create_skip_description",
    )
    builder.button(text=get_text(lang, "cancel"), callback_data="create_cancel")
    builder.adjust(2, 1)

    progress = build_progress_text(data, lang, 3)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Введите описание (можно пропустить):' if lang == 'ru' else 'Tavsif kiriting (o`tqazib yuborish mumkin):'}</b>\n\n"
        f"{'Пример: свежий, 450г' if lang == 'ru' else 'Misol: yangi, 450g'}"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(CreateOffer.description)
    await callback.answer()


@router.callback_query(F.data == "create_back_category")
async def back_to_category(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to category selection."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()

    header = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"<b>{'Добавить товар' if lang == 'ru' else 'Mahsulot qo`shish'}</b>\n\n"
    )
    step_text = (
        "<b>Шаг 1/9:</b> Выберите категорию"
        if lang == "ru"
        else "<b>1/9-qadam:</b> Kategoriyani tanlang"
    )

    await callback.message.edit_text(
        header + step_text,
        parse_mode="HTML",
        reply_markup=product_categories_keyboard(lang),
    )
    await state.set_state(CreateOffer.category)
    await callback.answer()


@router.callback_query(F.data == "create_back_price")
async def back_to_price(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to price input."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "back"), callback_data="create_back_description")
    builder.button(text=get_text(lang, "cancel"), callback_data="create_cancel")
    builder.adjust(2)

    progress = build_progress_text(data, lang, 4)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Введите цену (до скидки):' if lang == 'ru' else 'Narxni kiriting (chegirmadan oldin):'}</b>"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(CreateOffer.original_price)
    await callback.answer()


@router.callback_query(F.data == "create_back_discount")
async def back_to_discount(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to discount selection."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()

    progress = build_progress_text(data, lang, 5)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Выберите скидку:' if lang == 'ru' else 'Chegirmani tanlang:'}</b>"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=discount_keyboard(lang))
    await state.set_state(CreateOffer.discount_price)
    await callback.answer()


@router.callback_query(F.data == "create_back_quantity")
async def back_to_quantity(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to quantity selection."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    unit = data.get("unit", "шт")

    progress = build_progress_text(data, lang, 7)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Выберите количество:' if lang == 'ru' else 'Miqdorni tanlang:'}</b>"
    )

    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=quantity_keyboard(lang, unit)
    )
    await state.set_state(CreateOffer.quantity)
    await callback.answer()


@router.callback_query(F.data == "create_back_unit")
async def back_to_unit(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to unit type selection."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()

    progress = build_progress_text(data, lang, 6)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Выберите единицу измерения:' if lang == 'ru' else 'O`lchov birligini tanlang:'}</b>"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=unit_type_keyboard(lang))
    await state.set_state(CreateOffer.unit_type)
    await callback.answer()


@router.callback_query(F.data == "create_back_expiry")
async def back_to_expiry(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to expiry selection."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()

    progress = build_progress_text(data, lang, 8)

    text = (
        f"<b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"<b>{'Выберите срок годности:' if lang == 'ru' else 'Yaroqlilik muddatini tanlang:'}</b>"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=expiry_keyboard(lang))
    await state.set_state(CreateOffer.expiry_date)
    await callback.answer()


@router.callback_query(F.data == "create_cancel")
async def cancel_creation(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel offer creation."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    await state.clear()

    if callback.message:
        await callback.message.edit_text(
            "Создание товара отменено" if lang == "ru" else "Mahsulot yaratish bekor qilindi",
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "create_another")
async def create_another(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start creating another offer."""
    if not db or not callback.message:
        await callback.answer()
        return

    # Simulate pressing "Добавить" button
    lang = db.get_user_language(callback.from_user.id)

    stores = [
        s
        for s in db.get_user_accessible_stores(callback.from_user.id)
        if get_store_field(s, "status") in ("active", "approved")
    ]

    if not stores:
        await callback.answer(get_text(lang, "no_approved_stores"), show_alert=True)
        return

    if len(stores) > 1:
        builder = InlineKeyboardBuilder()
        for store in stores:
            store_id = get_store_field(store, "store_id")
            store_name = get_store_field(store, "name", "Магазин")
            if store_id is None:
                continue
            builder.button(text=store_name[:30], callback_data=f"create_store_{store_id}")
        builder.adjust(1)

        await callback.message.edit_text(
            get_text(lang, "choose_store"),
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
        await state.set_state(CreateOffer.store)
        await callback.answer()
        return

    store_id = get_store_field(stores[0], "store_id")
    store_name = get_store_field(stores[0], "name", "Магазин")
    await state.update_data(store_id=store_id, store_name=store_name)

    header = (
        f"<b>{store_name}</b>\n\n"
        f"<b>{'Добавить товар' if lang == 'ru' else 'Mahsulot qo`shish'}</b>\n\n"
    )
    step_text = (
        "<b>Шаг 1/9:</b> Выберите категорию"
        if lang == "ru"
        else "<b>1/9-qadam:</b> Kategoriyani tanlang"
    )

    await callback.message.edit_text(
        header + step_text,
        parse_mode="HTML",
        reply_markup=product_categories_keyboard(lang),
    )
    await state.set_state(CreateOffer.category)
    await callback.answer()


# ============ Copy Offer ============


@router.callback_query(F.data.startswith("copy_offer_"))
async def copy_offer_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start copying an offer - pre-fill data from existing offer."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.replace("copy_offer_", ""))
        offer = db.get_offer(offer_id)
        if not offer:
            await callback.answer(
                "Товар не найден" if lang == "ru" else "Mahsulot topilmadi", show_alert=True
            )
            return
    except (ValueError, AttributeError):
        await callback.answer("Error", show_alert=True)
        return

    # Get offer fields
    if isinstance(offer, dict):
        title = offer.get("title", "")
        original_price = offer.get("original_price", 0)
        discount_price = offer.get("discount_price", 0)
        quantity = offer.get("quantity", 0)
        category = offer.get("category", "other")
        photo = offer.get("photo")
        store_id = offer.get("store_id")
        expiry_date = offer.get("expiry_date", "")
    else:
        title = getattr(offer, "title", "")
        original_price = getattr(offer, "original_price", 0)
        discount_price = getattr(offer, "discount_price", 0)
        quantity = getattr(offer, "quantity", 0)
        category = getattr(offer, "category", "other")
        photo = getattr(offer, "photo", None)
        store_id = getattr(offer, "store_id", None)
        expiry_date = getattr(offer, "expiry_date", "")

    # Calculate discount percent
    discount_percent = int((1 - discount_price / original_price) * 100) if original_price > 0 else 0

    # Get store name
    stores = db.get_user_stores(callback.from_user.id)
    store_name = "Магазин"
    for s in stores:
        if get_store_field(s, "store_id") == store_id:
            store_name = get_store_field(s, "name", "Магазин")
            break

    # Pre-fill state with copied data
    await state.update_data(
        store_id=store_id,
        store_name=store_name,
        category=category,
        title=f"{title} (копия)" if lang == "ru" else f"{title} (nusxa)",
        original_price=original_price,
        discount_percent=discount_percent,
        discount_price=discount_price,
        quantity=quantity,
        expiry_date=expiry_date,
        photo=photo,
        is_copy=True,
    )

    data = await state.get_data()
    progress = build_progress_text(data, lang, 2)

    # Ask to confirm or edit title
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Сохранить как есть" if lang == "ru" else "Shunday saqlash",
        callback_data="copy_save_as_is",
    )
    builder.button(
        text="Изменить название" if lang == "ru" else "Nomni o'zgartirish",
        callback_data="copy_edit_title",
    )
    builder.button(text=get_text(lang, "cancel"), callback_data="create_cancel")
    builder.adjust(1)

    text = (
        f"<b>{'Копирование товара' if lang == 'ru' else 'Mahsulotni nusxalash'}</b>\n\n"
        f"{progress}\n\n"
        f"{'Сохранить копию или изменить название?' if lang == 'ru' else 'Nusxani saqlash yoki nomini o`zgartirish?'}"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "copy_save_as_is")
async def copy_save_as_is(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Save copy without changes."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    await _finalize_offer(callback.message, state, lang)
    await callback.answer()


@router.callback_query(F.data == "copy_edit_title")
async def copy_edit_title(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Edit title before saving copy."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "cancel"), callback_data="create_cancel")

    text = (
        f"<b>{'Копирование товара' if lang == 'ru' else 'Mahsulotni nusxalash'}</b>\n\n"
        f"{'Текущее название:' if lang == 'ru' else 'Joriy nom:'} <b>{data.get('title', '')}</b>\n\n"
        f"<b>{'Введите новое название:' if lang == 'ru' else 'Yangi nomni kiriting:'}</b>"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(CreateOffer.title)
    await state.update_data(is_copy_edit=True)
    await callback.answer()


@router.callback_query(F.data == "go_my_offers")
async def go_my_offers(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Navigate to My Offers."""
    if not callback.message:
        await callback.answer()
        return

    # Send message to trigger my_offers handler
    lang = db.get_user_language(callback.from_user.id) if db else "ru"
    await callback.message.answer(get_text(lang, "my_items"))
    await callback.answer()
