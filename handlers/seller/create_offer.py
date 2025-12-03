"""Seller offer creation handlers - step-by-step process with quick buttons."""
from __future__ import annotations

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
from localization import get_text
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
        "bakery": "🥖 Выпечка",
        "dairy": "🥛 Молочные",
        "meat": "🥩 Мясные",
        "fruits": "🍎 Фрукты",
        "vegetables": "🥬 Овощи",
        "drinks": "🥤 Напитки",
        "snacks": "🍿 Снеки",
        "frozen": "🧊 Замороженное",
        "other": "📦 Другое",
    },
    "uz": {
        "bakery": "🥖 Pishiriq",
        "dairy": "🥛 Sut mahsulotlari",
        "meat": "🥩 Go'sht",
        "fruits": "🍎 Mevalar",
        "vegetables": "🥬 Sabzavotlar",
        "drinks": "🥤 Ichimliklar",
        "snacks": "🍿 Gaz. ovqatlar",
        "frozen": "🧊 Muzlatilgan",
        "other": "📦 Boshqa",
    },
}


def get_category_name(category: str, lang: str) -> str:
    """Get localized category name."""
    return CATEGORY_NAMES.get(lang, CATEGORY_NAMES["ru"]).get(category, category)


def build_progress_text(data: dict, lang: str, current_step: int) -> str:
    """Build progress indicator showing completed steps."""
    steps = [
        ("Категория", "Kategoriya", data.get("category")),
        ("Название", "Nomi", data.get("title")),
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
            # Completed step
            if i == 1 and value:  # Category
                display_value = get_category_name(value, lang)
            elif i == 3 and value:  # Price
                display_value = f"{int(value):,} сум"
            elif i == 4 and value:  # Discount
                display_value = f"{value}%"
            elif i == 5 and value:  # Unit
                display_value = value
            elif i == 6 and value:  # Quantity
                unit = data.get("unit", "шт")
                display_value = f"{value} {unit}"
            elif value:
                display_value = str(value)[:20]
            else:
                display_value = "—"
            lines.append(f"✅ {name}: <b>{display_value}</b>")
        elif i == current_step:
            # Current step
            lines.append(f"👉 <b>{name}</b>")
        else:
            # Future step
            lines.append(f"⬜ {name}")

    return "\n".join(lines)


# ============ STEP 1: Start & Category ============


@router.message(F.text.contains("Добавить") | F.text.contains("Qo'shish"))
async def add_offer_start(message: types.Message, state: FSMContext) -> None:
    """Start offer creation - select store and category."""
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

    # Auto-select first store
    store_id = get_store_field(stores[0], "store_id")
    store_name = get_store_field(stores[0], "name", "Магазин")
    await state.update_data(store_id=store_id, store_name=store_name)

    header = (
        f"🏪 <b>{store_name}</b>\n\n"
        f"➕ <b>{'ДОБАВИТЬ ТОВАР' if lang == 'ru' else 'MAHSULOT QO`SHISH'}</b>\n\n"
    )

    step_text = (
        "📂 <b>Шаг 1/8:</b> Выберите категорию"
        if lang == "ru"
        else "📂 <b>1/8-qadam:</b> Kategoriyani tanlang"
    )

    await message.answer(
        header + step_text,
        parse_mode="HTML",
        reply_markup=product_categories_keyboard(lang),
    )
    await state.set_state(CreateOffer.category)


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

    # Build cancel keyboard
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена" if lang == "ru" else "❌ Bekor", callback_data="create_cancel")

    progress = build_progress_text({**data, "category": category}, lang, 2)

    text = (
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"📝 <b>{'Введите название товара:' if lang == 'ru' else 'Mahsulot nomini kiriting:'}</b>\n\n"
        f"{'Пример: Чай Ахмад Английский 100г' if lang == 'ru' else 'Misol: Ahmad English Tea 100g'}"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(CreateOffer.title)
    await callback.answer()


# ============ STEP 2: Title ============


@router.message(CreateOffer.title, F.text)
async def title_entered(message: types.Message, state: FSMContext) -> None:
    """Title entered - ask for price."""
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
            "❌ " + ("Название слишком короткое" if lang == "ru" else "Nom juda qisqa")
        )
        return

    if len(title) > 100:
        await message.answer(
            "❌ "
            + (
                "Название слишком длинное (макс 100 символов)"
                if lang == "ru"
                else "Nom juda uzun (maks 100 belgi)"
            )
        )
        return

    await state.update_data(title=title)
    data = await state.get_data()

    # Build back/cancel keyboard
    builder = InlineKeyboardBuilder()
    builder.button(
        text="◀️ Назад" if lang == "ru" else "◀️ Orqaga", callback_data="create_back_category"
    )
    builder.button(text="❌ Отмена" if lang == "ru" else "❌ Bekor", callback_data="create_cancel")
    builder.adjust(2)

    progress = build_progress_text(data, lang, 3)

    text = (
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"💰 <b>{'Введите цену (до скидки):' if lang == 'ru' else 'Narxni kiriting (chegirmadan oldin):'}</b>\n\n"
        f"{'Пример: 50000' if lang == 'ru' else 'Misol: 50000'}"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(CreateOffer.original_price)


# ============ STEP 3: Price ============


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

    # Parse price
    try:
        price_text = message.text.strip().replace(" ", "").replace(",", "")
        price = float(price_text)
        if price <= 0:
            raise ValueError("Price must be positive")
    except ValueError:
        await message.answer(
            "❌ "
            + ("Введите число. Пример: 50000" if lang == "ru" else "Raqam kiriting. Misol: 50000")
        )
        return

    await state.update_data(original_price=price)
    data = await state.get_data()

    progress = build_progress_text(data, lang, 4)

    text = (
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"🏷️ <b>{'Выберите скидку:' if lang == 'ru' else 'Chegirmani tanlang:'}</b>"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=discount_keyboard(lang))
    await state.set_state(CreateOffer.discount_price)


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
        builder.button(
            text="◀️ Назад" if lang == "ru" else "◀️ Orqaga", callback_data="create_back_price"
        )

        await callback.message.edit_text(
            "🏷️ <b>"
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
    """Custom discount entered."""
    if not db:
        await message.answer("System error")
        return

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(message.text):
        await state.clear()
        return

    lang = db.get_user_language(message.from_user.id)

    try:
        discount_percent = int(message.text.strip().replace("%", ""))
        if discount_percent < 0 or discount_percent > 99:
            raise ValueError("Invalid discount")
    except ValueError:
        await message.answer(
            "❌ "
            + ("Введите число от 0 до 99" if lang == "ru" else "0 dan 99 gacha raqam kiriting")
        )
        return

    await _process_discount(message, state, lang, discount_percent)


async def _process_discount(
    target: types.Message, state: FSMContext, lang: str, discount_percent: int
) -> None:
    """Process discount and move to unit type step."""
    data = await state.get_data()
    original_price = data.get("original_price", 0)
    discount_price = original_price * (1 - discount_percent / 100)

    await state.update_data(discount_percent=discount_percent, discount_price=discount_price)
    data = await state.get_data()

    progress = build_progress_text(data, lang, 5)

    text = (
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"💰 Цена со скидкой: <b>{int(discount_price):,} сум</b>\n\n"
        f"📦 <b>{'Выберите единицу измерения:' if lang == 'ru' else 'O`lchov birligini tanlang:'}</b>"
    )

    await target.answer(text, parse_mode="HTML", reply_markup=unit_type_keyboard(lang))
    await state.set_state(CreateOffer.unit_type)


# ============ STEP 5: Unit Type ============


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
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"📊 <b>{'Выберите количество:' if lang == 'ru' else 'Miqdorni tanlang:'}</b>"
    )

    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=quantity_keyboard(lang, unit)
    )
    await state.set_state(CreateOffer.quantity)
    await callback.answer()


# ============ STEP 6: Quantity ============


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
        builder.button(
            text="◀️ Назад" if lang == "ru" else "◀️ Orqaga", callback_data="create_back_unit"
        )

        example = "Пример: 2.5" if unit == "кг" else "Пример: 25"
        example_uz = "Misol: 2.5" if unit == "кг" else "Misol: 25"

        await callback.message.edit_text(
            "📊 <b>"
            + ("Введите количество:" if lang == "ru" else "Miqdorni kiriting:")
            + "</b>\n\n"
            + (example if lang == "ru" else example_uz),
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
        await callback.answer()
        return

    quantity = float(qty_data)
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
        # For pieces, ensure integer
        if unit == "шт" and quantity != int(quantity):
            await message.answer(
                "❌ "
                + (
                    "Для штук введите целое число"
                    if lang == "ru"
                    else "Dona uchun butun son kiriting"
                )
            )
            return
    except ValueError:
        await message.answer(
            "❌ " + ("Введите положительное число" if lang == "ru" else "Musbat raqam kiriting")
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
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"📅 <b>{'Выберите срок годности:' if lang == 'ru' else 'Yaroqlilik muddatini tanlang:'}</b>"
    )

    await target.answer(text, parse_mode="HTML", reply_markup=expiry_keyboard(lang))
    await state.set_state(CreateOffer.expiry_date)


# ============ STEP 7: Expiry Date ============


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
        builder.button(
            text="◀️ Назад" if lang == "ru" else "◀️ Orqaga", callback_data="create_back_quantity"
        )

        await callback.message.edit_text(
            "📅 <b>"
            + ("Введите дату (ДД.ММ):" if lang == "ru" else "Sanani kiriting (KK.OO):")
            + "</b>\n\n"
            + ("Пример: 25.12" if lang == "ru" else "Misol: 25.12"),
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
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
        date_str = message.text.strip().replace("/", ".").replace("-", ".")
        today = datetime.now()

        if len(date_str.split(".")) == 3:
            date_obj = datetime.strptime(date_str, "%d.%m.%Y")
        elif len(date_str.split(".")) == 2:
            date_obj = datetime.strptime(f"{date_str}.{today.year}", "%d.%m.%Y")
            if date_obj.date() < today.date():
                date_obj = date_obj.replace(year=today.year + 1)
        else:
            raise ValueError("Invalid date format")

        expiry_date = date_obj.strftime("%Y-%m-%d")
    except ValueError:
        await message.answer(
            "❌ "
            + (
                "Формат: ДД.ММ (например 25.12)"
                if lang == "ru"
                else "Format: KK.OO (masalan 25.12)"
            )
        )
        return

    await _process_expiry(message, state, lang, expiry_date)


async def _process_expiry(
    target: types.Message, state: FSMContext, lang: str, expiry_date: str
) -> None:
    """Process expiry date and move to photo step."""
    await state.update_data(expiry_date=expiry_date)
    data = await state.get_data()

    progress = build_progress_text(data, lang, 8)

    text = (
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"📸 <b>{'Отправьте фото товара или пропустите:' if lang == 'ru' else 'Mahsulot rasmini yuboring yoki o`tkazib yuboring:'}</b>"
    )

    await target.answer(text, parse_mode="HTML", reply_markup=photo_keyboard(lang))
    await state.set_state(CreateOffer.photo)


# ============ STEP 8: Photo ============


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
    data = await state.get_data()

    try:
        if not db:
            raise ValueError("Database not initialized")

        unit = data.get("unit", "шт")
        quantity = data["quantity"]

        # Format quantity display
        if unit == "кг":
            qty_display = f"{quantity} кг"
        else:
            qty_display = f"{int(quantity)} шт"

        offer_id = db.add_offer(
            store_id=data["store_id"],
            title=data["title"],
            description=data["title"],
            original_price=data["original_price"],
            discount_price=data["discount_price"],
            quantity=quantity,
            available_from="08:00",
            available_until="23:00",
            photo=data.get("photo"),
            expiry_date=data["expiry_date"],
            unit=unit,
            category=data.get("category", "other"),
        )

        discount_percent = data.get("discount_percent", 0)

        success_text = (
            f"✅ <b>{'ТОВАР СОЗДАН!' if lang == 'ru' else 'MAHSULOT YARATILDI!'}</b>\n\n"
            f"📦 {data['title']}\n"
            f"💰 {int(data['original_price']):,} ➜ {int(data['discount_price']):,} сум (-{discount_percent}%)\n"
            f"📊 {qty_display}\n"
            f"📅 До: {data['expiry_date']}\n\n"
        )

        # Add quick action buttons
        builder = InlineKeyboardBuilder()
        builder.button(
            text="➕ Ещё товар" if lang == "ru" else "➕ Yana mahsulot",
            callback_data="create_another",
        )
        builder.button(
            text="🔄 Копировать" if lang == "ru" else "🔄 Nusxalash",
            callback_data=f"copy_offer_{offer_id}",
        )
        builder.button(
            text="📦 Мои товары" if lang == "ru" else "📦 Mahsulotlarim",
            callback_data="go_my_offers",
        )
        builder.adjust(2, 1)

        await target.answer(success_text, parse_mode="HTML", reply_markup=builder.as_markup())

    except Exception as e:
        logger.error(f"Error creating offer: {e}")
        await target.answer(
            "❌ "
            + (
                "Ошибка при сохранении. Попробуйте снова."
                if lang == "ru"
                else "Saqlashda xatolik. Qayta urinib ko'ring."
            )
        )
    finally:
        await state.clear()


# ============ Navigation Callbacks ============


@router.callback_query(F.data == "create_back_category")
async def back_to_category(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to category selection."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()

    header = (
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"➕ <b>{'ДОБАВИТЬ ТОВАР' if lang == 'ru' else 'MAHSULOT QO`SHISH'}</b>\n\n"
    )
    step_text = (
        "📂 <b>Шаг 1/8:</b> Выберите категорию"
        if lang == "ru"
        else "📂 <b>1/8-qadam:</b> Kategoriyani tanlang"
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
    builder.button(
        text="◀️ Назад" if lang == "ru" else "◀️ Orqaga", callback_data="create_back_category"
    )
    builder.button(text="❌ Отмена" if lang == "ru" else "❌ Bekor", callback_data="create_cancel")
    builder.adjust(2)

    progress = build_progress_text(data, lang, 3)

    text = (
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"💰 <b>{'Введите цену (до скидки):' if lang == 'ru' else 'Narxni kiriting (chegirmadan oldin):'}</b>"
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

    progress = build_progress_text(data, lang, 4)

    text = (
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"🏷️ <b>{'Выберите скидку:' if lang == 'ru' else 'Chegirmani tanlang:'}</b>"
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

    progress = build_progress_text(data, lang, 6)

    text = (
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"📊 <b>{'Выберите количество:' if lang == 'ru' else 'Miqdorni tanlang:'}</b>"
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

    progress = build_progress_text(data, lang, 5)

    text = (
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"📦 <b>{'Выберите единицу измерения:' if lang == 'ru' else 'O`lchov birligini tanlang:'}</b>"
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

    progress = build_progress_text(data, lang, 7)

    text = (
        f"🏪 <b>{data.get('store_name', 'Магазин')}</b>\n\n"
        f"{progress}\n\n"
        f"📅 <b>{'Выберите срок годности:' if lang == 'ru' else 'Yaroqlilik muddatini tanlang:'}</b>"
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
            "❌ "
            + ("Создание товара отменено" if lang == "ru" else "Mahsulot yaratish bekor qilindi"),
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

    store_id = get_store_field(stores[0], "store_id")
    store_name = get_store_field(stores[0], "name", "Магазин")
    await state.update_data(store_id=store_id, store_name=store_name)

    header = (
        f"🏪 <b>{store_name}</b>\n\n"
        f"➕ <b>{'ДОБАВИТЬ ТОВАР' if lang == 'ru' else 'MAHSULOT QO`SHISH'}</b>\n\n"
    )
    step_text = (
        "📂 <b>Шаг 1/8:</b> Выберите категорию"
        if lang == "ru"
        else "📂 <b>1/8-qadam:</b> Kategoriyani tanlang"
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
        text="✅ Сохранить как есть" if lang == "ru" else "✅ Shunday saqlash",
        callback_data="copy_save_as_is",
    )
    builder.button(
        text="✏️ Изменить название" if lang == "ru" else "✏️ Nomni o'zgartirish",
        callback_data="copy_edit_title",
    )
    builder.button(text="❌ Отмена" if lang == "ru" else "❌ Bekor", callback_data="create_cancel")
    builder.adjust(1)

    text = (
        f"🔄 <b>{'КОПИРОВАНИЕ ТОВАРА' if lang == 'ru' else 'MAHSULOTNI NUSXALASH'}</b>\n\n"
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
    builder.button(text="❌ Отмена" if lang == "ru" else "❌ Bekor", callback_data="create_cancel")

    text = (
        f"🔄 <b>{'КОПИРОВАНИЕ ТОВАРА' if lang == 'ru' else 'MAHSULOTNI NUSXALASH'}</b>\n\n"
        f"{'Текущее название:' if lang == 'ru' else 'Joriy nom:'} <b>{data.get('title', '')}</b>\n\n"
        f"📝 <b>{'Введите новое название:' if lang == 'ru' else 'Yangi nomni kiriting:'}</b>"
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
    await callback.message.answer("📦 Мои товары")
    await callback.answer()
