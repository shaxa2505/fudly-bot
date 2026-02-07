"""Seller offer creation handlers - step-by-step process with quick buttons."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import StateFilter
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
from handlers.common.utils import html_escape, is_main_menu_button, safe_delete_message, safe_edit_message
from localization import get_text, normalize_category
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router()

MIN_DISCOUNT_PERCENT = 20


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


async def _handle_main_menu_action(message: types.Message, state: FSMContext) -> bool:
    """Handle main menu buttons during offer creation flow."""
    if not message or not message.text:
        return False
    if not is_main_menu_button(message.text):
        return False

    await state.clear()
    if not db:
        return True

    text_value = message.text.strip()

    ru_items = get_text("ru", "my_items")
    uz_items = get_text("uz", "my_items")
    ru_items_tail = ru_items.split(" ", 1)[-1]
    uz_items_tail = uz_items.split(" ", 1)[-1]

    if text_value in {ru_items, uz_items} or text_value.endswith(ru_items_tail) or text_value.endswith(
        uz_items_tail
    ):
        from handlers.seller.management.offers import my_offers

        await my_offers(message, state)
        await safe_delete_message(message)
        return True

    if text_value in {
        get_text("ru", "orders"),
        get_text("uz", "orders"),
    }:
        from handlers.seller.management.orders import seller_orders_main

        await seller_orders_main(message, state)
        await safe_delete_message(message)
        return True

    if text_value in {
        get_text("ru", "add_item"),
        get_text("uz", "add_item"),
    }:
        await add_offer_start(message, state)
        await safe_delete_message(message)
        return True

    if text_value in {
        get_text("ru", "partner_panel"),
        get_text("uz", "partner_panel"),
    }:
        from handlers.seller.dashboard import partner_panel

        await partner_panel(message, state)
        await safe_delete_message(message)
        return True

    if text_value.endswith(get_text("ru", "profile")) or text_value.endswith(get_text("uz", "profile")):
        from handlers.customer.profile import profile

        await profile(message, state)
        await safe_delete_message(message)
        return True

    await safe_delete_message(message)
    return True


async def _upsert_prompt(
    target: types.Message,
    state: FSMContext,
    text: str,
    reply_markup: Any | None = None,
    parse_mode: str = "HTML",
) -> None:
    """Send or edit a single prompt message to keep the flow compact."""
    if not target:
        return
    chat_id = target.chat.id if target.chat else None
    message_id = None
    try:
        data = await state.get_data()
        message_id = data.get("prompt_message_id")
    except Exception:
        message_id = None

    if bot and chat_id and message_id:
        try:
            await bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            return
        except Exception:
            pass

    try:
        msg = await target.answer(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        return
    try:
        await state.update_data(prompt_message_id=msg.message_id)
    except Exception:
        pass


async def _edit_prompt_from_callback(
    callback: types.CallbackQuery,
    state: FSMContext,
    text: str,
    reply_markup: Any | None = None,
    parse_mode: str = "HTML",
) -> None:
    """Edit the current prompt from a callback, fallback to sending a new one."""
    if not callback.message:
        return
    try:
        await state.update_data(prompt_message_id=callback.message.message_id)
    except Exception:
        pass
    if not await safe_edit_message(
        callback.message, text, parse_mode=parse_mode, reply_markup=reply_markup
    ):
        await _upsert_prompt(callback.message, state, text, reply_markup, parse_mode)


# Category names for display
CATEGORY_NAMES = {
    "ru": {
        "bakery": "\u0412\u044b\u043f\u0435\u0447\u043a\u0430",
        "dairy": "\u041c\u043e\u043b\u043e\u0447\u043d\u044b\u0435",
        "meat": "\u041c\u044f\u0441\u043d\u044b\u0435",
        "fruits": "\u0424\u0440\u0443\u043a\u0442\u044b",
        "vegetables": "\u041e\u0432\u043e\u0449\u0438",
        "drinks": "\u041d\u0430\u043f\u0438\u0442\u043a\u0438",
        "snacks": "\u0421\u043d\u0435\u043a\u0438",
        "frozen": "\u0417\u0430\u043c\u043e\u0440\u043e\u0436\u0435\u043d\u043d\u043e\u0435",
        "sweets": "\u0421\u043b\u0430\u0434\u043e\u0441\u0442\u0438",
        "other": "\u0414\u0440\u0443\u0433\u043e\u0435",
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


def _shorten(text: Any, limit: int = 24) -> str:
    value = str(text) if text is not None else ""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def _store_fallback(lang: str) -> str:
    return "Магазин" if lang == "ru" else "Do'kon"


def _store_header(data: dict, lang: str) -> str:
    store_name = html_escape(data.get("store_name") or _store_fallback(lang))
    return f"🏪 <b>{store_name}</b>"


def _step_title(lang: str, step: int, ru_title: str, uz_title: str, emoji: str) -> str:
    label = ru_title if lang == "ru" else uz_title
    step_label = f"Шаг {step}/9: {label}" if lang == "ru" else f"{step}/9-qadam: {label}"
    return f"{emoji} <b>{step_label}</b>"


def _compose_step_message(
    data: dict, lang: str, step: int, ru_title: str, uz_title: str, emoji: str, hint: str
) -> str:
    summary = build_progress_text(data, lang, step)
    summary_block = f"{summary}\n\n" if summary else ""
    return f"{_store_header(data, lang)}\n\n{summary_block}{_step_title(lang, step, ru_title, uz_title, emoji)}\n{hint}"


def build_progress_text(data: dict, lang: str, current_step: int) -> str:
    """Build a compact progress summary of completed steps."""
    parts: list[str] = []

    if current_step > 1:
        category = data.get("category")
        if category:
            parts.append(f"🏷 {html_escape(_shorten(get_category_name(category, lang), 18))}")

    if current_step > 2:
        title = data.get("title")
        if title:
            parts.append(f"📝 {html_escape(_shorten(title, 22))}")

    if current_step > 3:
        original_price = data.get("original_price")
        if original_price is not None:
            discount_price = data.get("discount_price")
            if discount_price and discount_price != original_price:
                price_value = f"{int(original_price):,}→{int(discount_price):,}"
            else:
                price_value = f"{int(original_price):,}"
            currency = "сум" if lang == "ru" else "sum"
            parts.append(f"💰 {price_value} {currency}")

    if current_step > 6:
        quantity = data.get("quantity")
        unit = data.get("unit")
        if quantity is not None and unit:
            try:
                qty_value = float(quantity)
                if unit in DECIMAL_UNITS:
                    qty_str = f"{qty_value:.2f}".rstrip("0").rstrip(".")
                else:
                    qty_str = str(int(qty_value))
            except (TypeError, ValueError):
                qty_str = str(quantity)
            parts.append(f"📦 {html_escape(_shorten(f'{qty_str} {unit}', 18))}")

    if current_step > 8:
        if "expiry_date" in data:
            expiry_value = data.get("expiry_date")
            if not expiry_value:
                expiry_value = "Без срока" if lang == "ru" else "Muddatsiz"
            parts.append(f"⏳ {html_escape(_shorten(expiry_value, 16))}")

    if data.get("photo"):
        parts.append("🖼️")

    if not parts:
        return ""

    if len(parts) > 4:
        parts = parts[:4] + ["…"]

    return " • ".join(parts)


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
        raise ValueError("Discount required")

    if "%" in raw:
        percent_value = _parse_price_value(raw)
        discount_percent = int(percent_value)
        if discount_percent < MIN_DISCOUNT_PERCENT or discount_percent > 99:
            raise ValueError("Invalid discount percent")
        discount_price = original_price * (1 - discount_percent / 100)
        return discount_percent, discount_price

    discount_price = _parse_price_value(raw)
    if discount_price >= original_price:
        if discount_price <= 99:
            discount_percent = int(discount_price)
            if discount_percent < MIN_DISCOUNT_PERCENT or discount_percent > 99:
                raise ValueError("Invalid discount percent")
            discount_price = original_price * (1 - discount_percent / 100)
            return discount_percent, discount_price
        raise ValueError("Discount price must be less than original")
    discount_percent = int((1 - discount_price / original_price) * 100)
    if discount_percent < MIN_DISCOUNT_PERCENT:
        raise ValueError("Discount too low")
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
            "<b>\u26A1 Быстрое добавление</b>\n\n"
            "\U0001F9FE Формат:\n"
            "Название | Цена | Скидка | Кол-во | Ед | Срок | Категория | Описание\n\n"
            "\U0001F4CC Можно отправить текстом или подписью к фото.\n"
            "\U0001F4CC Поля после скидки — необязательные.\n"
            "\U0001F3F7 Скидка: минимум 20% (30% или 35000)\n"
            "\u23F3 Срок: ДД.ММ, ДД.ММ.ГГГГ, +3 или 0/без срока\n\n"
            "\U0001F9EA Пример:\n"
            "<code>Хлеб | 12000 | 9000 | 10 | шт | 25.12 | Выпечка | свежий</code>"
        )
    return (
        "<b>\u26A1 Tez qo`shish</b>\n\n"
        "\U0001F9FE Format:\n"
        "Nomi | Narx | Chegirma | Miqdor | Birlik | Muddat | Kategoriya | Tavsif\n\n"
        "\U0001F4CC Matn yoki surat osti (caption) bilan yuboring.\n"
        "\U0001F4CC Chegirmadan keyingi maydonlar ixtiyoriy.\n"
        "\U0001F3F7 Chegirma: kamida 20% (30% yoki 35000)\n"
        "\u23F3 Muddat: KK.OO, KK.OO.YYYY, +3 yoki 0/muddatsiz\n\n"
        "\U0001F9EA Misol:\n"
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

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")

    header = f"{_store_header(data, lang)}\n\n" if data.get("store_name") else ""
    await _upsert_prompt(
        target,
        state,
        header + _quick_add_instructions(lang),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
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

        await _upsert_prompt(
            message,
            state,
            get_text(lang, "choose_store"),
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
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
        builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
        builder.adjust(1)

        await _upsert_prompt(
            message,
            state,
            get_text(lang, "choose_store"),
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await state.set_state(CreateOffer.store)
        return

    # Auto-select first store
    store_id = get_store_field(stores[0], "store_id")
    store_name = get_store_field(stores[0], "name", "Магазин")
    await state.update_data(store_id=store_id, store_name=store_name)

    data = await state.get_data()
    step_text = _compose_step_message(
        data,
        lang,
        1,
        "Категория",
        "Kategoriya",
        "🧺",
        "Выберите категорию ниже." if lang == "ru" else "Kategoriyani tanlang.",
    )

    await _upsert_prompt(
        message,
        state,
        step_text,
        reply_markup=product_categories_keyboard(lang),
        parse_mode="HTML",
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

    data = await state.get_data()
    step_text = _compose_step_message(
        data,
        lang,
        1,
        "Категория",
        "Kategoriya",
        "🧺",
        "Выберите категорию ниже." if lang == "ru" else "Kategoriyani tanlang.",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        step_text,
        reply_markup=product_categories_keyboard(lang),
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.category)
    await callback.answer()


@router.callback_query(F.data == "create_back_store")
async def back_to_store(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to store selection."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    stores = [
        s
        for s in db.get_user_accessible_stores(callback.from_user.id)
        if get_store_field(s, "status") in ("active", "approved")
    ]

    if not stores:
        await callback.answer(get_text(lang, "no_approved_stores"), show_alert=True)
        return

    if len(stores) == 1:
        store_id = get_store_field(stores[0], "store_id")
        store_name = get_store_field(stores[0], "name", "Магазин")
        await state.update_data(store_id=store_id, store_name=store_name)

        data = await state.get_data()
        step_text = _compose_step_message(
            data,
            lang,
            1,
            "Категория",
            "Kategoriya",
            "🧺",
            "Выберите категорию ниже." if lang == "ru" else "Kategoriyani tanlang.",
        )

        await _edit_prompt_from_callback(
            callback,
            state,
            step_text,
            reply_markup=product_categories_keyboard(lang),
            parse_mode="HTML",
        )
        await state.set_state(CreateOffer.category)
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for store in stores:
        store_id = get_store_field(store, "store_id")
        store_name = get_store_field(store, "name", "Магазин")
        if store_id is None:
            continue
        builder.button(text=store_name[:30], callback_data=f"create_store_{store_id}")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(1)

    await _edit_prompt_from_callback(
        callback,
        state,
        get_text(lang, "choose_store"),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.store)
    await callback.answer()


@router.message(
    StateFilter(CreateOffer.category, CreateOffer.store, CreateOffer.unit_type, CreateOffer.photo),
    F.text,
)
async def create_offer_menu_fallback(message: types.Message, state: FSMContext) -> None:
    """Handle main menu buttons during callback-only steps."""
    if not db:
        await message.answer("System error")
        return

    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)
    current_state = await state.get_state()
    data = await state.get_data()

    if current_state == CreateOffer.store.state:
        stores = [
            s
            for s in db.get_user_accessible_stores(message.from_user.id)
            if get_store_field(s, "status") in ("active", "approved")
        ]
        if not stores:
            await _upsert_prompt(message, state, get_text(lang, "no_approved_stores"))
            await safe_delete_message(message)
            return
        builder = InlineKeyboardBuilder()
        for store in stores:
            store_id = get_store_field(store, "store_id")
            store_name = get_store_field(store, "name", "Магазин")
            if store_id is None:
                continue
            builder.button(text=store_name[:30], callback_data=f"create_store_{store_id}")
        builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
        builder.adjust(1)
        await _upsert_prompt(
            message,
            state,
            get_text(lang, "choose_store"),
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await safe_delete_message(message)
        return

    if current_state == CreateOffer.category.state:
        step_text = _compose_step_message(
            data,
            lang,
            1,
            "Категория",
            "Kategoriya",
            "🧺",
            "Выберите категорию ниже." if lang == "ru" else "Kategoriyani tanlang.",
        )
        await _upsert_prompt(
            message,
            state,
            step_text,
            reply_markup=product_categories_keyboard(lang),
            parse_mode="HTML",
        )
        await safe_delete_message(message)
        return

    if current_state == CreateOffer.unit_type.state:
        await _go_to_unit_step(message, state, lang)
        await safe_delete_message(message)
        return

    if current_state == CreateOffer.photo.state:
        text = _compose_step_message(
            data,
            lang,
            9,
            "Фото",
            "Rasm",
            "🖼️",
            "Отправьте фото или пропустите." if lang == "ru" else "Rasm yuboring yoki o`tkazib yuboring.",
        )
        await _upsert_prompt(
            message,
            state,
            text,
            reply_markup=photo_keyboard(lang),
            parse_mode="HTML",
        )
        await safe_delete_message(message)
        return


@router.message(CreateOffer.quick_input, F.text)
async def quick_input_entered(message: types.Message, state: FSMContext) -> None:
    """Process quick add input from text."""
    if not db:
        await message.answer("System error")
        return

    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)

    try:
        offer_data = _parse_quick_input(message.text)
    except Exception:
        await _upsert_prompt(message, state, _quick_add_instructions(lang), parse_mode="HTML")
        await safe_delete_message(message)
        return

    await state.update_data(**offer_data, photo=None)
    await _finalize_offer(message, state, lang)
    await safe_delete_message(message)


@router.message(CreateOffer.quick_input, F.photo)
async def quick_input_photo(message: types.Message, state: FSMContext) -> None:
    """Process quick add input from photo caption."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    caption = message.caption or ""

    if not caption.strip():
        await _upsert_prompt(message, state, _quick_add_instructions(lang), parse_mode="HTML")
        await safe_delete_message(message)
        return

    try:
        offer_data = _parse_quick_input(caption)
    except Exception:
        await _upsert_prompt(message, state, _quick_add_instructions(lang), parse_mode="HTML")
        await safe_delete_message(message)
        return

    photo_id = message.photo[-1].file_id
    await state.update_data(**offer_data, photo=photo_id)
    await _finalize_offer(message, state, lang)
    await safe_delete_message(message)


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
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_category")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)

    text = _compose_step_message(
        data,
        lang,
        2,
        "Название",
        "Nomi",
        "📝",
        "Пример: Чай Ahmad Английский 100 г" if lang == "ru" else "Misol: Ahmad English Tea 100g",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
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
    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)
    title = message.text.strip()

    if len(title) < 2:
        await _upsert_prompt(
            message,
            state,
            "⚠️ Название слишком короткое" if lang == "ru" else "⚠️ Nom juda qisqa",
        )
        await safe_delete_message(message)
        return

    if len(title) > 100:
        await _upsert_prompt(
            message,
            state,
            "⚠️ Название слишком длинное (макс 100 символов)"
            if lang == "ru"
            else "⚠️ Nom juda uzun (maks 100 belgi)",
        )
        await safe_delete_message(message)
        return

    await state.update_data(title=title)
    data = await state.get_data()

    # Build back/skip/cancel keyboard
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_title")
    builder.button(text=get_text(lang, "btn_skip"), callback_data="create_skip_description")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2, 1)

    text = _compose_step_message(
        data,
        lang,
        3,
        "Описание",
        "Tavsif",
        "✍️",
        "Можно пропустить. Пример: свежий, 450 г"
        if lang == "ru"
        else "Ixtiyoriy. Misol: yangi, 450g",
    )

    await _upsert_prompt(
        message,
        state,
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.description)
    await safe_delete_message(message)


# ============ STEP 3: Description ============


async def _prompt_price(target: types.Message, state: FSMContext, lang: str) -> None:
    """Ask for original price (with flexible input)."""
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_description")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)

    text = _compose_step_message(
        data,
        lang,
        4,
        "Цена",
        "Narx",
        "💰",
        "Можно: 50000 или 50000 35000 (со скидкой)."
        if lang == "ru"
        else "Misol: 50000 yoki 50000 35000 (chegirmali).",
    )

    await _upsert_prompt(
        target,
        state,
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.original_price)


@router.message(CreateOffer.description, F.text)
async def description_entered(message: types.Message, state: FSMContext) -> None:
    """Description entered - ask for price."""
    if not db:
        await message.answer("System error")
        return

    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)
    description = message.text.strip()

    if description.lower() in ("-", "нет", "без описания", "no"):
        description = ""

    await state.update_data(description=description)
    await _prompt_price(message, state, lang)
    await safe_delete_message(message)


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
    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)

    raw_text = message.text.strip()
    numbers = re.findall(r"\d+(?:[.,]\d+)?", raw_text)
    if not numbers:
        await _upsert_prompt(
            message,
            state,
            "⚠️ Введите число. Пример: 50000" if lang == "ru" else "⚠️ Raqam kiriting. Misol: 50000",
        )
        await safe_delete_message(message)
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
            if discount_percent < MIN_DISCOUNT_PERCENT:
                await state.update_data(original_price=original)
                data = await state.get_data()
                text = _compose_step_message(
                    data,
                    lang,
                    5,
                    "Скидка",
                    "Chegirma",
                    "🏷️",
                    "Выберите % или отправьте цену со скидкой. Минимум 20%."
                    if lang == "ru"
                    else "Foizni tanlang yoki chegirmali narxni yuboring. Kamida 20%.",
                )
                text = f"{get_text(lang, 'error_min_discount')}\n\n{text}"
                await _upsert_prompt(
                    message,
                    state,
                    text,
                    reply_markup=discount_keyboard(lang),
                    parse_mode="HTML",
                )
                await state.set_state(CreateOffer.discount_price)
                await safe_delete_message(message)
                return
            await state.update_data(
                original_price=original,
                discount_price=discount_price,
                discount_percent=discount_percent,
            )
            await _go_to_unit_step(message, state, lang)
            await safe_delete_message(message)
            return

        original = _to_number(numbers[0])
        if original <= 0:
            raise ValueError

        await state.update_data(original_price=original)
        data = await state.get_data()
        text = _compose_step_message(
            data,
            lang,
            5,
            "Скидка",
            "Chegirma",
            "🏷️",
            "Выберите % или отправьте цену со скидкой. Минимум 20%."
            if lang == "ru"
            else "Foizni tanlang yoki chegirmali narxni yuboring. Kamida 20%.",
        )

        await _upsert_prompt(
            message,
            state,
            text,
            reply_markup=discount_keyboard(lang),
            parse_mode="HTML",
        )
        await state.set_state(CreateOffer.discount_price)
        await safe_delete_message(message)
    except ValueError:
        await _upsert_prompt(
            message,
            state,
            "⚠️ Неверный формат. Пример: 50000 или 50000 35000"
            if lang == "ru"
            else "⚠️ Noto`g`ri format. Misol: 50000 yoki 50000 35000",
        )
        await safe_delete_message(message)


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
        builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_price")

        await _edit_prompt_from_callback(
            callback,
            state,
            "<b>"
            + ("🏷️ Скидка (%)" if lang == "ru" else "🏷️ Chegirma (%)")
            + "</b>\n"
            + ("Введите процент. Пример: 35" if lang == "ru" else "Foizni kiriting. Misol: 35"),
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
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
    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)

    raw_text = message.text.strip()
    numbers = re.findall(r"\d+(?:[.,]\d+)?", raw_text)
    if not numbers:
        await _upsert_prompt(
            message,
            state,
            "⚠️ Введите процент или цену. Пример: 30% или 35000"
            if lang == "ru"
            else "⚠️ Foiz yoki narx yuboring. Misol: 30% yoki 35000",
        )
        await safe_delete_message(message)
        return

    try:
        data = await state.get_data()
        original_price = float(data.get("original_price", 0))

        if "%" in raw_text:
            discount_percent = int(float(numbers[0]))
            if discount_percent < 0 or discount_percent > 99:
                raise ValueError
            await _process_discount(message, state, lang, discount_percent)
            await safe_delete_message(message)
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
        if discount_percent < MIN_DISCOUNT_PERCENT:
            await _upsert_prompt(
                message,
                state,
                get_text(lang, "error_min_discount"),
                reply_markup=discount_keyboard(lang),
                parse_mode="HTML",
            )
            await safe_delete_message(message)
            return
        await state.update_data(discount_percent=discount_percent, discount_price=discount_price)
        await _go_to_unit_step(message, state, lang)
        await safe_delete_message(message)
    except ValueError:
        await _upsert_prompt(
            message,
            state,
            "Неверный формат. Пример: 30% или 35000"
            if lang == "ru"
            else "Noto`g`ri format. Misol: 30% yoki 35000",
        )
        await safe_delete_message(message)


async def _go_to_unit_step(target: types.Message, state: FSMContext, lang: str) -> None:
    """Move to unit selection step."""
    data = await state.get_data()
    text = _compose_step_message(
        data,
        lang,
        6,
        "Ед. измерения",
        "O'lchov birligi",
        "📏",
        "Выберите единицу измерения." if lang == "ru" else "O'lchov birligini tanlang.",
    )

    await _upsert_prompt(
        target,
        state,
        text,
        reply_markup=unit_type_keyboard(lang),
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.unit_type)


async def _process_discount(
    target: types.Message, state: FSMContext, lang: str, discount_percent: int
) -> None:
    """Process discount and move to unit type step."""
    if discount_percent < MIN_DISCOUNT_PERCENT:
        await _upsert_prompt(
            target,
            state,
            get_text(lang, "error_min_discount"),
            reply_markup=discount_keyboard(lang),
            parse_mode="HTML",
        )
        await state.set_state(CreateOffer.discount_price)
        return
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

    text = _compose_step_message(
        data,
        lang,
        7,
        "Количество",
        "Miqdor",
        "🔢",
        "Выберите или отправьте количество." if lang == "ru" else "Miqdorni tanlang yoki yuboring.",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=quantity_keyboard(lang, unit),
        parse_mode="HTML",
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
        builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_unit")

        example = "Пример: 2.5" if unit in DECIMAL_UNITS else "Пример: 25"
        example_uz = "Misol: 2.5" if unit in DECIMAL_UNITS else "Misol: 25"

        await _edit_prompt_from_callback(
            callback,
            state,
            "<b>"
            + ("🔢 Введите количество" if lang == "ru" else "🔢 Miqdorni kiriting")
            + "</b>\n"
            + (example if lang == "ru" else example_uz),
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
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
    if await _handle_main_menu_action(message, state):
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
            await _upsert_prompt(
                message,
                state,
                "⚠️ Введите целое число для выбранной единицы"
                if lang == "ru"
                else "⚠️ Tanlangan birlik uchun butun son kiriting",
            )
            await safe_delete_message(message)
            return
    except ValueError:
        await _upsert_prompt(
            message,
            state,
            "⚠️ Введите положительное число" if lang == "ru" else "⚠️ Musbat raqam kiriting",
        )
        await safe_delete_message(message)
        return

    await _process_quantity(message, state, lang, quantity)
    await safe_delete_message(message)


async def _process_quantity(
    target: types.Message, state: FSMContext, lang: str, quantity: float
) -> None:
    """Process quantity and move to expiry step."""
    await state.update_data(quantity=quantity)
    data = await state.get_data()

    text = _compose_step_message(
        data,
        lang,
        8,
        "Срок годности",
        "Yaroqlilik muddati",
        "⏳",
        "Выберите срок годности." if lang == "ru" else "Yaroqlilik muddatini tanlang.",
    )

    await _upsert_prompt(
        target,
        state,
        text,
        reply_markup=expiry_keyboard(lang),
        parse_mode="HTML",
    )
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
        builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_quantity")

        await _edit_prompt_from_callback(
            callback,
            state,
            "<b>"
            + ("⏳ Дата (ДД.ММ)" if lang == "ru" else "⏳ Sana (KK.OO)")
            + "</b>\n"
            + ("Введите дату. Пример: 25.12" if lang == "ru" else "Sana kiriting. Misol: 25.12"),
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
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
    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)

    try:
        expiry_date = _parse_expiry_input(message.text)
    except ValueError:
        await _upsert_prompt(
            message,
            state,
            "⚠️ Формат: ДД.ММ (например 25.12)"
            if lang == "ru"
            else "⚠️ Format: KK.OO (masalan 25.12)",
        )
        await safe_delete_message(message)
        return

    await _process_expiry(message, state, lang, expiry_date)
    await safe_delete_message(message)


async def _process_expiry(
    target: types.Message, state: FSMContext, lang: str, expiry_date: str | None
) -> None:
    """Process expiry date and move to photo step."""
    await state.update_data(expiry_date=expiry_date)
    data = await state.get_data()

    text = _compose_step_message(
        data,
        lang,
        9,
        "Фото",
        "Rasm",
        "🖼️",
        "Отправьте фото или пропустите." if lang == "ru" else "Rasm yuboring yoki o`tkazib yuboring.",
    )

    await _upsert_prompt(
        target,
        state,
        text,
        reply_markup=photo_keyboard(lang),
        parse_mode="HTML",
    )
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
    await safe_delete_message(message)


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

        title_display = html_escape(data["title"])
        expiry_safe = html_escape(expiry_display)
        success_text = (
            f"<b>\u2705 {'Товар создан' if lang == 'ru' else 'Mahsulot yaratildi'}</b>\n\n"
            f"{title_display}\n"
            f"💰 {'Цена' if lang == 'ru' else 'Narx'}: {int(data['original_price']):,} → {int(data['discount_price']):,} сум (-{discount_percent}%)\n"
            f"📦 {'Количество' if lang == 'ru' else 'Miqdor'}: {qty_display}\n"
            f"⏳ {'Срок годности' if lang == 'ru' else 'Yaroqlilik muddati'}: {expiry_safe}\n\n"
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

        await _upsert_prompt(
            target,
            state,
            success_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Error creating offer: {e}")
        await _upsert_prompt(
            target,
            state,
            "Ошибка при сохранении. Попробуйте снова."
            if lang == "ru"
            else "Saqlashda xatolik. Qayta urinib ko'ring.",
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
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_category")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)

    text = _compose_step_message(
        data,
        lang,
        2,
        "Название",
        "Nomi",
        "📝",
        "Пример: Чай Ahmad Английский 100 г" if lang == "ru" else "Misol: Ahmad English Tea 100g",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
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
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_title")
    builder.button(text=get_text(lang, "btn_skip"), callback_data="create_skip_description")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2, 1)

    text = _compose_step_message(
        data,
        lang,
        3,
        "Описание",
        "Tavsif",
        "✍️",
        "Можно пропустить. Пример: свежий, 450 г"
        if lang == "ru"
        else "Ixtiyoriy. Misol: yangi, 450g",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
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

    step_text = _compose_step_message(
        data,
        lang,
        1,
        "Категория",
        "Kategoriya",
        "🧺",
        "Выберите категорию ниже." if lang == "ru" else "Kategoriyani tanlang.",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        step_text,
        reply_markup=product_categories_keyboard(lang),
        parse_mode="HTML",
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
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_description")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)

    text = _compose_step_message(
        data,
        lang,
        4,
        "Цена",
        "Narx",
        "💰",
        "Можно: 50000 или 50000 35000 (со скидкой)."
        if lang == "ru"
        else "Misol: 50000 yoki 50000 35000 (chegirmali).",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
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

    text = _compose_step_message(
        data,
        lang,
        5,
        "Скидка",
        "Chegirma",
        "🏷️",
        "Выберите % или отправьте цену со скидкой. Минимум 20%."
        if lang == "ru"
        else "Foizni tanlang yoki chegirmali narxni yuboring. Kamida 20%.",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=discount_keyboard(lang),
        parse_mode="HTML",
    )
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

    text = _compose_step_message(
        data,
        lang,
        7,
        "Количество",
        "Miqdor",
        "🔢",
        "Выберите или отправьте количество." if lang == "ru" else "Miqdorni tanlang yoki yuboring.",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=quantity_keyboard(lang, unit),
        parse_mode="HTML",
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

    text = _compose_step_message(
        data,
        lang,
        6,
        "Ед. измерения",
        "O'lchov birligi",
        "📏",
        "Выберите единицу измерения." if lang == "ru" else "O'lchov birligini tanlang.",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=unit_type_keyboard(lang),
        parse_mode="HTML",
    )
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

    text = _compose_step_message(
        data,
        lang,
        8,
        "Срок годности",
        "Yaroqlilik muddati",
        "⏳",
        "Выберите срок годности." if lang == "ru" else "Yaroqlilik muddatini tanlang.",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=expiry_keyboard(lang),
        parse_mode="HTML",
    )
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
        await _edit_prompt_from_callback(
            callback,
            state,
            get_text(lang, "offer_creation_cancelled"),
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
        builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
        builder.adjust(1)

        await _edit_prompt_from_callback(
            callback,
            state,
            get_text(lang, "choose_store"),
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await state.set_state(CreateOffer.store)
        await callback.answer()
        return

    store_id = get_store_field(stores[0], "store_id")
    store_name = get_store_field(stores[0], "name", "Магазин")
    await state.update_data(store_id=store_id, store_name=store_name)

    data = await state.get_data()
    step_text = _compose_step_message(
        data,
        lang,
        1,
        "Категория",
        "Kategoriya",
        "🧺",
        "Выберите категорию ниже." if lang == "ru" else "Kategoriyani tanlang.",
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        step_text,
        reply_markup=product_categories_keyboard(lang),
        parse_mode="HTML",
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
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(1)

    text = (
        f"<b>{'Копирование товара' if lang == 'ru' else 'Mahsulotni nusxalash'}</b>\n\n"
        f"{progress}\n\n"
        f"{'Сохранить копию или изменить название?' if lang == 'ru' else 'Nusxani saqlash yoki nomini o`zgartirish?'}"
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
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
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")

    text = (
        f"<b>{'Копирование товара' if lang == 'ru' else 'Mahsulotni nusxalash'}</b>\n\n"
        f"{'Текущее название:' if lang == 'ru' else 'Joriy nom:'} <b>{data.get('title', '')}</b>\n\n"
        f"<b>{'Введите новое название:' if lang == 'ru' else 'Yangi nomni kiriting:'}</b>"
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
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
