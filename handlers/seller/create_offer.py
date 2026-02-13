"""Seller offer creation handlers - step-by-step process with quick buttons."""
from __future__ import annotations

import re
import time
from datetime import datetime, time as dt_time, timedelta
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.units import (
    effective_order_unit,
    format_quantity,
    normalize_unit,
    parse_quantity_input,
    quantity_step,
    unit_label,
)
from app.core.utils import calc_discount_percent, get_store_field
from app.keyboards import (
    expiry_keyboard,
    photo_keyboard,
    product_categories_keyboard,
    quantity_keyboard,
)
from database_protocol import DatabaseProtocol
from handlers.common.states import CreateOffer
from handlers.common.utils import (
    html_escape,
    is_main_menu_button,
    safe_delete_message,
    safe_edit_message,
)
from localization import get_text, normalize_category
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router()

TOTAL_STEPS = 6
MIN_DISCOUNT_PERCENT = 20
MAX_DISCOUNT_PERCENT = 90
MIN_TITLE_LEN = 3
MAX_TITLE_LEN = 80
MAX_QUANTITY = 500
MAX_EXPIRY_DAYS = 30  # Legacy limit (no longer enforced)
WIZARD_TTL_SECONDS = 600
DEFAULT_OFFER_AVAILABLE_FROM = "08:00"
DEFAULT_OFFER_AVAILABLE_UNTIL = "23:00"
_TIME_TOKEN_RE = re.compile(r"\d{1,2}(?::\d{1,2})?")


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


def _parse_time_value(value: object) -> dt_time | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.replace(".", ":")
    if "T" in raw:
        raw = raw.split("T", 1)[1]
    raw = raw.strip()
    if re.fullmatch(r"\d{1,2}", raw):
        raw = f"{int(raw):02d}:00"
    elif re.fullmatch(r"\d{1,2}:\d{1,2}", raw):
        hh, mm = raw.split(":", 1)
        raw = f"{int(hh):02d}:{int(mm):02d}"
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return None


def _get_store_hours_raw(store: Any) -> str | None:
    if not store:
        return None
    if hasattr(store, "get"):
        working_hours = store.get("working_hours") or store.get("work_time")
        if not working_hours and store.get("open_time") and store.get("close_time"):
            working_hours = f"{store.get('open_time')} - {store.get('close_time')}"
        return str(working_hours) if working_hours else None
    working_hours = getattr(store, "working_hours", None) or getattr(store, "work_time", None)
    if not working_hours:
        open_time = getattr(store, "open_time", None)
        close_time = getattr(store, "close_time", None)
        if open_time and close_time:
            working_hours = f"{open_time} - {close_time}"
    return str(working_hours) if working_hours else None


def _resolve_offer_default_times(store: Any | None) -> tuple[dt_time, dt_time]:
    default_start = _parse_time_value(DEFAULT_OFFER_AVAILABLE_FROM) or dt_time(hour=8, minute=0)
    default_end = _parse_time_value(DEFAULT_OFFER_AVAILABLE_UNTIL) or dt_time(hour=23, minute=0)

    raw_hours = _get_store_hours_raw(store)
    if not raw_hours:
        return default_start, default_end

    tokens = _TIME_TOKEN_RE.findall(raw_hours.replace(".", ":"))
    if len(tokens) < 2:
        return default_start, default_end

    start = _parse_time_value(tokens[0])
    end = _parse_time_value(tokens[1])
    if not start or not end:
        return default_start, default_end

    return start, end


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


async def _ensure_wizard_alive(
    target: types.Message | types.CallbackQuery,
    state: FSMContext,
    lang: str,
) -> bool:
    """Ensure wizard session is not expired (10 minutes)."""
    try:
        data = await state.get_data()
    except Exception:
        return True

    started_at = data.get("wizard_started_at")
    if not started_at:
        return True
    if time.time() - float(started_at) <= WIZARD_TTL_SECONDS:
        return True

    await state.clear()
    message = target.message if isinstance(target, types.CallbackQuery) else target
    if message:
        await _upsert_prompt(message, state, get_text(lang, "offer_creation_expired"))
    return False


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

WEIGHT_ALLOWED_CATEGORIES = {"meat", "fruits", "dairy"}
VOLUME_ALLOWED_CATEGORIES = {"drinks", "dairy"}


def get_category_name(category: str, lang: str) -> str:
    """Get localized category name."""
    return CATEGORY_NAMES.get(lang, CATEGORY_NAMES["ru"]).get(category, category)


def _allowed_units_for_category(category: str | None) -> set[str]:
    allowed = {"piece"}
    if category in WEIGHT_ALLOWED_CATEGORIES:
        allowed.update({"kg", "g"})
    if category in VOLUME_ALLOWED_CATEGORIES:
        allowed.update({"l", "ml"})
    return allowed


def _build_unit_keyboard(lang: str, category: str | None) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    allowed = _allowed_units_for_category(category)

    if "piece" in allowed:
        piece_label = f"📦 {get_text(lang, 'unit_piece_title')} ({get_text(lang, 'unit_piece')})"
        builder.button(text=piece_label, callback_data="unit_type_piece")
    if "kg" in allowed:
        kg_label = f"⚖️ {get_text(lang, 'unit_kg_title')} ({get_text(lang, 'unit_kg')})"
        builder.button(text=kg_label, callback_data="unit_type_kg")
    if "g" in allowed:
        g_label = f"⚖️ {get_text(lang, 'unit_g_title')} ({get_text(lang, 'unit_g')})"
        builder.button(text=g_label, callback_data="unit_type_g")
    if "l" in allowed:
        l_label = f"🧃 {get_text(lang, 'unit_l_title')} ({get_text(lang, 'unit_l')})"
        builder.button(text=l_label, callback_data="unit_type_l")
    if "ml" in allowed:
        ml_label = f"🧃 {get_text(lang, 'unit_ml_title')} ({get_text(lang, 'unit_ml')})"
        builder.button(text=ml_label, callback_data="unit_type_ml")

    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_discount")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")

    builder.adjust(2)
    return builder


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
    step_label = (
        f"Шаг {step}/{TOTAL_STEPS}: {label}"
        if lang == "ru"
        else f"{step}/{TOTAL_STEPS}-qadam: {label}"
    )
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

    if current_step > 1:
        title = data.get("title")
        if title:
            parts.append(f"📝 {html_escape(_shorten(title, 22))}")

    if current_step > 2:
        original_price = data.get("original_price")
        if original_price is not None:
            discount_price = data.get("discount_price")
            if discount_price and discount_price != original_price:
                price_value = f"{int(original_price):,}→{int(discount_price):,}"
            else:
                price_value = f"{int(original_price):,}"
            currency = "сум" if lang == "ru" else "sum"
            parts.append(f"💰 {price_value} {currency}")

    if current_step > 3:
        unit = data.get("unit")
        if unit:
            parts.append(f"📦 {html_escape(unit_label(unit, lang))}")

    if current_step > 4:
        quantity = data.get("quantity")
        if quantity is not None:
            quantity_unit = effective_order_unit(data.get("unit", "piece"))
            try:
                qty_str = format_quantity(quantity, quantity_unit, lang)
            except Exception:
                qty_str = str(quantity)
            unit_text = unit_label(quantity_unit, lang)
            parts.append(f"📦 {html_escape(_shorten(f'{qty_str} {unit_text}', 18))}")

        expiry_value = data.get("expiry_date")
        if expiry_value:
            parts.append(f"⏳ {html_escape(_shorten(expiry_value, 16))}")

    if data.get("photo"):
        parts.append("🖼️")

    if not parts:
        return ""

    if len(parts) > 4:
        parts = parts[:4] + ["…"]

    return " • ".join(parts)


def _parse_expiry_input(value: str) -> str:
    """Parse expiry input into ISO date (required)."""
    if not value:
        raise ValueError("Empty expiry")

    raw = value.strip().lower()
    if not raw:
        raise ValueError("Empty expiry")

    # Days offset (e.g. 3, +3, 3д, 3 кун)
    day_match = re.fullmatch(
        r"\+?\s*(\d{1,3})\s*(д|дн|дня|дней|кун|kun|day|days)?",
        raw,
    )
    if day_match:
        days = int(day_match.group(1))
        date_obj = (datetime.now() + timedelta(days=days)).date()
        return _validate_expiry_date(date_obj)

    normalized = raw.replace("/", ".").replace("-", ".")
    parts = normalized.split(".")
    today = datetime.now()

    date_obj: datetime | None = None
    try:
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            day, month = map(int, parts)
            date_obj = datetime(today.year, month, day)
        elif len(parts) == 3 and all(p.isdigit() for p in parts):
            if len(parts[0]) == 4:
                year, month, day = map(int, parts)
            else:
                day, month, year = map(int, parts)
                if year < 100:
                    year += 2000
            date_obj = datetime(year, month, day)
    except ValueError:
        date_obj = None

    if date_obj is None:
        raise ValueError("Invalid expiry format")

    return _validate_expiry_date(date_obj.date())


def _validate_expiry_date(date_value: datetime.date) -> str:
    today = datetime.now().date()
    if date_value < today:
        raise ValueError("Expiry in the past")
    return date_value.strftime("%Y-%m-%d")


def _normalize_unit_input(value: str | None) -> str | None:
    if not value:
        return None
    return normalize_unit(value)


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
        if discount_percent < MIN_DISCOUNT_PERCENT or discount_percent > MAX_DISCOUNT_PERCENT:
            raise ValueError("Invalid discount percent")
        discount_price = original_price * (1 - discount_percent / 100)
        return discount_percent, discount_price

    discount_price = _parse_price_value(raw)
    if discount_price >= original_price:
        if discount_price <= 99:
            discount_percent = int(discount_price)
            if discount_percent < MIN_DISCOUNT_PERCENT or discount_percent > MAX_DISCOUNT_PERCENT:
                raise ValueError("Invalid discount percent")
            discount_price = original_price * (1 - discount_percent / 100)
            return discount_percent, discount_price
        raise ValueError("Discount price must be less than original")
    discount_percent = calc_discount_percent(original_price, discount_price)
    if discount_percent < MIN_DISCOUNT_PERCENT:
        raise ValueError("Discount too low")
    if discount_percent > MAX_DISCOUNT_PERCENT:
        raise ValueError("Discount too high")
    return discount_percent, discount_price


def _parse_quantity_value(raw: str | None, unit: str) -> float:
    if not raw or not raw.strip():
        return 1.0
    value = parse_quantity_input(raw, effective_order_unit(unit))
    return float(value)


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
    unit = _normalize_unit_input(unit_raw) if unit_raw else "piece"
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
    """Quick add disabled; redirect to full wizard."""
    await add_offer_start(message, state)


@router.callback_query(F.data.startswith("quick_store_"))
async def quick_store_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Legacy quick add store selection - redirect to wizard."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
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
    await state.update_data(store_id=store_id, store_name=store_name, wizard_started_at=time.time())

    data = await state.get_data()
    step_text = _compose_step_message(
        data,
        lang,
        1,
        "Товар",
        "Mahsulot",
        "🥗",
        get_text(lang, "offer_step1_category_hint"),
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


@router.message(F.text.contains("Добавить") | F.text.contains("Qo'shish"))
async def add_offer_start(message: types.Message, state: FSMContext) -> None:
    """Start offer creation - select store and category."""
    # Clear any previous FSM state
    await state.clear()

    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    await state.update_data(wizard_started_at=time.time())

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
        "Товар",
        "Mahsulot",
        "🥗",
        get_text(lang, "offer_step1_category_hint"),
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
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
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
    if not data.get("wizard_started_at"):
        await state.update_data(wizard_started_at=time.time())

    step_text = _compose_step_message(
        data,
        lang,
        1,
        "Товар",
        "Mahsulot",
        "🥗",
        get_text(lang, "offer_step1_category_hint"),
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
            "Товар",
            "Mahsulot",
            "🥗",
            get_text(lang, "offer_step1_category_hint"),
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
    StateFilter(
        CreateOffer.category,
        CreateOffer.store,
        CreateOffer.unit_type,
        CreateOffer.photo,
        CreateOffer.confirm,
    ),
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
    if not await _ensure_wizard_alive(message, state, lang):
        return
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
            "Товар",
            "Mahsulot",
            "🥗",
            get_text(lang, "offer_step1_category_hint"),
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
            6,
            "Фото",
            "Rasm",
            "🖼️",
            get_text(lang, "offer_step4_photo_hint"),
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

    if current_state == CreateOffer.confirm.state:
        await _show_confirmation(message, state, lang)
        await safe_delete_message(message)
        return


@router.message(CreateOffer.quick_input, F.text)
async def quick_input_entered(message: types.Message, state: FSMContext) -> None:
    """Quick add disabled - redirect to wizard."""
    if not db:
        await message.answer("System error")
        return

    if await _handle_main_menu_action(message, state):
        return

    await add_offer_start(message, state)
    await safe_delete_message(message)


@router.message(CreateOffer.quick_input, F.photo)
async def quick_input_photo(message: types.Message, state: FSMContext) -> None:
    """Quick add disabled - redirect to wizard."""
    if not db:
        await message.answer("System error")
        return
    if await _handle_main_menu_action(message, state):
        return

    await add_offer_start(message, state)
    await safe_delete_message(message)


@router.callback_query(F.data.startswith("product_cat_"))
async def category_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Category selected - ask for title."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
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
        1,
        "Товар",
        "Mahsulot",
        "🥗",
        get_text(lang, "offer_step1_title_hint"),
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


# ============ STEP 1: Title ============


@router.message(CreateOffer.title, F.text)
async def title_entered(message: types.Message, state: FSMContext) -> None:
    """Title entered - ask for original price."""
    if not db:
        await message.answer("System error")
        return

    # Check if user pressed main menu button - clear state and let other handlers process
    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)
    if not await _ensure_wizard_alive(message, state, lang):
        return
    title = message.text.strip()

    if len(title) < MIN_TITLE_LEN:
        await _upsert_prompt(message, state, get_text(lang, "offer_error_title_short"))
        await safe_delete_message(message)
        return

    if len(title) > MAX_TITLE_LEN:
        await _upsert_prompt(message, state, get_text(lang, "offer_error_title_long"))
        await safe_delete_message(message)
        return

    if not re.match(r"^[A-Za-zА-Яа-яЁё0-9]", title):
        await _upsert_prompt(message, state, get_text(lang, "offer_error_title_start"))
        await safe_delete_message(message)
        return

    await state.update_data(title=title)
    await _prompt_price(message, state, lang)
    await safe_delete_message(message)


# ============ STEP 2: Price ============


async def _prompt_price(target: types.Message, state: FSMContext, lang: str) -> None:
    """Ask for original price (with flexible input)."""
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_title")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)

    text = _compose_step_message(
        data,
        lang,
        2,
        "Цена",
        "Narx",
        "💰",
        get_text(lang, "offer_step2_original_hint"),
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
    """Legacy description step - continue to price."""
    if not db:
        await message.answer("System error")
        return

    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)
    if not await _ensure_wizard_alive(message, state, lang):
        return

    await _prompt_price(message, state, lang)
    await safe_delete_message(message)


@router.callback_query(F.data == "create_skip_description")
async def skip_description(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Skip description and move to price."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return

    await _prompt_price(callback.message, state, lang)
    await callback.answer()


# ============ STEP 2: Discounted Price ============


@router.message(CreateOffer.original_price, F.text)
async def price_entered(message: types.Message, state: FSMContext) -> None:
    """Original price entered - ask for discounted price."""
    if not db:
        await message.answer("System error")
        return

    # Check if user pressed main menu button - clear state and let other handlers process
    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)
    if not await _ensure_wizard_alive(message, state, lang):
        return

    raw_text = message.text.strip()
    try:
        original = _parse_price_value(raw_text)
        if original <= 0:
            raise ValueError
    except ValueError:
        await _upsert_prompt(message, state, get_text(lang, "offer_error_price_number"))
        await safe_delete_message(message)
        return

    await state.update_data(original_price=original)
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_price")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)

    text = _compose_step_message(
        data,
        lang,
        2,
        "Цена",
        "Narx",
        "💰",
        get_text(lang, "offer_step2_discount_hint"),
    )

    await _upsert_prompt(
        message,
        state,
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.discount_price)
    await safe_delete_message(message)


@router.callback_query(CreateOffer.discount_price, F.data.startswith("discount_"))
async def discount_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Discount selected via button (legacy support)."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
    discount_data = callback.data.replace("discount_", "")

    if discount_data == "custom":
        builder = InlineKeyboardBuilder()
        builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_price")
        builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
        builder.adjust(2)

        data = await state.get_data()
        await _edit_prompt_from_callback(
            callback,
            state,
            _compose_step_message(
                data,
                lang,
                2,
                "Цена",
                "Narx",
                "💰",
                get_text(lang, "offer_step2_discount_hint"),
            ),
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    data = await state.get_data()
    original_price = data.get("original_price")
    if not original_price:
        await callback.answer(get_text(lang, "offer_error_price_number"), show_alert=True)
        return

    try:
        discount_percent = int(discount_data)
        if discount_percent < MIN_DISCOUNT_PERCENT or discount_percent > MAX_DISCOUNT_PERCENT:
            raise ValueError
        discount_price = original_price * (1 - discount_percent / 100)
        await state.update_data(discount_percent=discount_percent, discount_price=discount_price)
    except ValueError:
        await callback.answer(get_text(lang, "offer_error_discount_range"), show_alert=True)
        return

    await _go_to_unit_step(callback.message, state, lang)
    await callback.answer()


@router.message(CreateOffer.discount_price, F.text)
async def discount_entered(message: types.Message, state: FSMContext) -> None:
    """Discount price entered."""
    if not db:
        await message.answer("System error")
        return

    # Check if user pressed main menu button - clear state and let other handlers process
    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)
    if not await _ensure_wizard_alive(message, state, lang):
        return

    data = await state.get_data()
    original_price = data.get("original_price")
    if not original_price:
        await _upsert_prompt(message, state, get_text(lang, "offer_error_price_number"))
        await safe_delete_message(message)
        return

    raw_text = message.text.strip()

    try:
        if "%" in raw_text:
            percent_value = _parse_price_value(raw_text)
            discount_percent = int(percent_value)
            if discount_percent < MIN_DISCOUNT_PERCENT or discount_percent > MAX_DISCOUNT_PERCENT:
                raise ValueError("range")
            discount_price = original_price * (1 - discount_percent / 100)
        else:
            discount_price = _parse_price_value(raw_text)
            if discount_price >= original_price:
                raise ValueError("logic")
            discount_percent = calc_discount_percent(original_price, discount_price)
            if discount_percent < MIN_DISCOUNT_PERCENT or discount_percent > MAX_DISCOUNT_PERCENT:
                raise ValueError("range")
    except ValueError as exc:
        reason = str(exc)
        if "logic" in reason:
            await _upsert_prompt(message, state, get_text(lang, "offer_error_discount_logic"))
        elif "range" in reason:
            await _upsert_prompt(message, state, get_text(lang, "offer_error_discount_range"))
        else:
            await _upsert_prompt(message, state, get_text(lang, "offer_error_price_number"))
        await safe_delete_message(message)
        return

    await state.update_data(discount_percent=discount_percent, discount_price=discount_price)
    await _go_to_unit_step(message, state, lang)
    await safe_delete_message(message)


async def _go_to_unit_step(target: types.Message, state: FSMContext, lang: str) -> None:
    """Move to unit selection step."""
    data = await state.get_data()
    text = _compose_step_message(
        data,
        lang,
        3,
        "Единица измерения",
        "O'lchov birligi",
        "📏",
        get_text(lang, "offer_step3_unit_hint"),
    )

    unit_kb = _build_unit_keyboard(lang, data.get("category"))

    await _upsert_prompt(
        target,
        state,
        text,
        reply_markup=unit_kb.as_markup(),
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.unit_type)


# ============ LEGACY: Unit Type ============


@router.callback_query(CreateOffer.unit_type, F.data.startswith("unit_type_"))
async def unit_type_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Unit type selected - move to quantity."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return

    unit_type = callback.data.replace("unit_type_", "") if callback.data else "piece"
    unit_type = normalize_unit(unit_type)
    data = await state.get_data()
    allowed = _allowed_units_for_category(data.get("category"))
    if unit_type not in allowed:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await state.update_data(unit=unit_type)
    await _prompt_quantity_step(callback.message, state, lang)
    await callback.answer()


# ============ STEP 4: Quantity ============


async def _prompt_quantity_step(
    target: types.Message, state: FSMContext, lang: str
) -> None:
    data = await state.get_data()
    selected_unit = data.get("unit", "piece")
    quantity_unit = effective_order_unit(selected_unit)
    if quantity_unit in {"kg", "g"}:
        hint = get_text(lang, "offer_step4_quantity_hint_weight")
    elif quantity_unit in {"l", "ml"}:
        hint = get_text(lang, "offer_step4_quantity_hint_volume")
    else:
        hint = get_text(lang, "offer_step4_quantity_hint_piece")

    text = _compose_step_message(
        data,
        lang,
        4,
        "Остаток и срок годности",
        "Miqdor va yaroqlilik",
        "📦",
        hint,
    )

    await _upsert_prompt(
        target,
        state,
        text,
        reply_markup=quantity_keyboard(lang, unit=quantity_unit),
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.quantity)


@router.callback_query(CreateOffer.quantity, F.data.startswith("quantity_"))
async def quantity_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Quantity selected via button."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
    qty_data = callback.data.replace("quantity_", "")
    data = await state.get_data()
    unit = effective_order_unit(data.get("unit", "piece"))

    if qty_data == "custom":
        # Ask for custom quantity
        builder = InlineKeyboardBuilder()
        builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_quantity")
        builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
        builder.adjust(2)

        await _edit_prompt_from_callback(
            callback,
            state,
            f"<b>{get_text(lang, 'offer_step3_quantity_custom')}</b>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    try:
        quantity_val = parse_quantity_input(qty_data, unit)
        quantity = float(quantity_val)
        if quantity <= 0 or quantity > MAX_QUANTITY:
            raise ValueError("range")
    except (TypeError, ValueError) as exc:
        reason = str(exc)
        if reason == "integer":
            msg = get_text(lang, "offer_error_quantity_integer")
        elif reason == "step":
            msg = get_text(lang, "offer_error_quantity_step")
        elif unit in {"kg", "g"}:
            msg = get_text(lang, "offer_error_quantity_weight_range").format(max=MAX_QUANTITY)
        elif unit in {"l", "ml"}:
            msg = get_text(lang, "offer_error_quantity_volume_range").format(max=MAX_QUANTITY)
        else:
            msg = get_text(lang, "offer_error_quantity_range").format(max=MAX_QUANTITY)
        await callback.answer(msg, show_alert=True)
        return

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
    if not await _ensure_wizard_alive(message, state, lang):
        return

    data = await state.get_data()
    unit = effective_order_unit(data.get("unit", "piece"))

    try:
        quantity_val = parse_quantity_input(message.text, unit)
        quantity = float(quantity_val)
        if quantity <= 0 or quantity > MAX_QUANTITY:
            raise ValueError("range")
    except ValueError as exc:
        reason = str(exc)
        if reason == "integer":
            msg = get_text(lang, "offer_error_quantity_integer")
        elif reason == "step":
            msg = get_text(lang, "offer_error_quantity_step")
        elif unit in {"kg", "g"}:
            msg = get_text(lang, "offer_error_quantity_weight_range").format(max=MAX_QUANTITY)
        elif unit in {"l", "ml"}:
            msg = get_text(lang, "offer_error_quantity_volume_range").format(max=MAX_QUANTITY)
        else:
            msg = get_text(lang, "offer_error_quantity_range").format(max=MAX_QUANTITY)
        await _upsert_prompt(message, state, msg)
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
        5,
        "Остаток и срок годности",
        "Miqdor va yaroqlilik",
        "📦",
        get_text(lang, "offer_step3_expiry_hint"),
    )

    await _upsert_prompt(
        target,
        state,
        text,
        reply_markup=expiry_keyboard(lang),
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.expiry_date)


# ============ STEP 4: Expiry Date ============


@router.callback_query(CreateOffer.expiry_date, F.data.startswith("expiry_"))
async def expiry_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Expiry date selected via button."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
    expiry_data = callback.data.replace("expiry_", "")

    if expiry_data == "custom":
        # Ask for custom date
        builder = InlineKeyboardBuilder()
        builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_quantity")
        builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
        builder.adjust(2)

        await _edit_prompt_from_callback(
            callback,
            state,
            f"<b>{get_text(lang, 'offer_step3_expiry_custom')}</b>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    try:
        days = int(expiry_data)
        expiry_date = _validate_expiry_date((datetime.now() + timedelta(days=days)).date())
    except (TypeError, ValueError):
        await callback.answer(get_text(lang, "offer_error_expiry_range"), show_alert=True)
        return

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
    if not await _ensure_wizard_alive(message, state, lang):
        return

    try:
        expiry_date = _parse_expiry_input(message.text)
    except ValueError as exc:
        msg = str(exc)
        if "format" in msg.lower():
            await _upsert_prompt(message, state, get_text(lang, "offer_error_expiry_format"))
        else:
            await _upsert_prompt(message, state, get_text(lang, "offer_error_expiry_range"))
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
        6,
        "Фото",
        "Rasm",
        "🖼️",
        get_text(lang, "offer_step4_photo_hint"),
    )

    await _upsert_prompt(
        target,
        state,
        text,
        reply_markup=photo_keyboard(lang),
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.photo)


# ============ STEP 5: Photo ============


@router.message(CreateOffer.photo, F.photo)
async def photo_received(message: types.Message, state: FSMContext) -> None:
    """Photo received - show confirmation."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    if not await _ensure_wizard_alive(message, state, lang):
        return
    photo_id = message.photo[-1].file_id
    await state.update_data(photo=photo_id)
    await _show_confirmation(message, state, lang)
    await safe_delete_message(message)


@router.message(CreateOffer.photo)
async def photo_required(message: types.Message, state: FSMContext) -> None:
    """Handle non-photo input on photo step."""
    if not db:
        await message.answer("System error")
        return

    if await _handle_main_menu_action(message, state):
        return

    lang = db.get_user_language(message.from_user.id)
    if not await _ensure_wizard_alive(message, state, lang):
        return

    await _upsert_prompt(
        message,
        state,
        get_text(lang, "offer_error_photo_required"),
        reply_markup=photo_keyboard(lang),
        parse_mode="HTML",
    )
    await safe_delete_message(message)


@router.callback_query(F.data == "create_skip_photo")
async def skip_photo(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Photo is mandatory - show error."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    await callback.answer(get_text(lang, "offer_error_photo_required"), show_alert=True)


async def _show_confirmation(target: types.Message, state: FSMContext, lang: str) -> None:
    """Show final confirmation before publishing."""
    data = await state.get_data()

    title = html_escape(data.get("title") or "")
    category = get_category_name(data.get("category", "other"), lang)
    category = html_escape(category)

    original_price = int(data.get("original_price", 0))
    discount_price = int(data.get("discount_price", 0))
    discount_percent = int(data.get("discount_percent") or calc_discount_percent(original_price, discount_price))

    quantity = data.get("quantity", 0)
    unit = effective_order_unit(data.get("unit", "piece"))
    try:
        qty_display = f"{format_quantity(quantity, unit, lang)} {unit_label(unit, lang)}"
    except Exception:
        qty_display = f"{quantity} {unit_label(unit, lang)}"

    expiry_raw = data.get("expiry_date") or ""

    def _format_expiry(value: str) -> str:
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m")
        except Exception:
            return value

    expiry_display = _format_expiry(expiry_raw)
    urgent_label = ""
    try:
        if expiry_raw:
            exp_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
            if exp_date == datetime.now().date():
                urgent_label = f" ({get_text(lang, 'offer_confirm_urgent')})"
    except Exception:
        urgent_label = ""

    currency = get_text(lang, "currency")
    expiry_prefix = "до" if lang == "ru" else "gacha"

    lines = [
        f"<b>{get_text(lang, 'offer_confirm_title')}</b>",
        "",
        f"🧀 {title}",
        f"{get_text(lang, 'offer_confirm_category')}: {category}",
        "",
        f"{get_text(lang, 'offer_confirm_price_title')}:",
        f"{get_text(lang, 'offer_confirm_was')}: {original_price:,} {currency}",
        f"{get_text(lang, 'offer_confirm_now')}: {discount_price:,} {currency} (-{discount_percent}%)",
        "",
        f"{get_text(lang, 'offer_confirm_qty')}: {qty_display}",
        f"{get_text(lang, 'offer_confirm_expiry')}: {expiry_prefix} {expiry_display}{urgent_label}",
    ]

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "offer_publish_btn"), callback_data="create_publish")
    builder.button(text=get_text(lang, "offer_edit_btn"), callback_data="create_edit")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2, 1)

    await _upsert_prompt(
        target,
        state,
        "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.confirm)


async def _finalize_offer(target: types.Message, state: FSMContext, lang: str) -> None:
    """Save offer to database."""
    data = await state.get_data()

    try:
        if not db:
            raise ValueError("Database not initialized")

        unit = data.get("unit", "piece")
        quantity_unit = effective_order_unit(unit)
        quantity = float(data["quantity"])
        qty_display = f"{format_quantity(quantity, quantity_unit, lang)} {unit_label(quantity_unit, lang)}"

        store = None
        if hasattr(db, "get_store") and data.get("store_id") is not None:
            try:
                store = db.get_store(int(data["store_id"]))
            except Exception as e:
                logger.warning(f"Failed to load store {data.get('store_id')} for offer defaults: {e}")
        available_from, available_until = _resolve_offer_default_times(store)

        # Store prices directly as entered
        original_price_value = int(data["original_price"])
        discount_price_value = int(data["discount_price"])

        _offer_id = db.add_offer(
            store_id=data["store_id"],
            title=data["title"],
            description=data.get("description") or data["title"],
            original_price=original_price_value,
            discount_price=discount_price_value,
            quantity=quantity,
            available_from=available_from.isoformat(),  # ISO time format
            available_until=available_until.isoformat(),  # ISO time format
            photo_id=data.get("photo"),  # Unified parameter name
            expiry_date=data.get("expiry_date"),  # Will be parsed by Pydantic
            unit=unit,
            category=data.get("category", "other"),
        )

        success_text = f"<b>{get_text(lang, 'offer_published_title')}</b>\n{get_text(lang, 'offer_published_hint')}"

        builder = InlineKeyboardBuilder()
        builder.button(text=get_text(lang, 'offer_add_more_btn'), callback_data='create_another')
        builder.button(text=get_text(lang, 'offer_to_items_btn'), callback_data='go_my_offers')
        builder.adjust(2)

        await _upsert_prompt(
            target,
            state,
            success_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Error creating offer: {e}")
        await _upsert_prompt(target, state, get_text(lang, "offer_create_failed"))
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
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_category")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)

    text = _compose_step_message(
        data,
        lang,
        1,
        "Товар",
        "Mahsulot",
        "🥗",
        get_text(lang, "offer_step1_title_hint"),
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
    """Legacy back action - return to title input."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_title")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)

    text = _compose_step_message(
        data,
        lang,
        1,
        "Товар",
        "Mahsulot",
        "🥗",
        get_text(lang, "offer_step1_title_hint"),
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


@router.callback_query(F.data == "create_back_category")
async def back_to_category(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to category selection."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
    data = await state.get_data()

    step_text = _compose_step_message(
        data,
        lang,
        1,
        "Товар",
        "Mahsulot",
        "🥗",
        get_text(lang, "offer_step1_category_hint"),
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
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_title")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)

    text = _compose_step_message(
        data,
        lang,
        2,
        "Цена",
        "Narx",
        "💰",
        get_text(lang, "offer_step2_original_hint"),
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
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "btn_back"), callback_data="create_back_price")
    builder.button(text=get_text(lang, "btn_cancel"), callback_data="create_cancel")
    builder.adjust(2)

    text = _compose_step_message(
        data,
        lang,
        2,
        "Цена",
        "Narx",
        "💰",
        get_text(lang, "offer_step2_discount_hint"),
    )

    await _edit_prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=builder.as_markup(),
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
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
    data = await state.get_data()

    await _prompt_quantity_step(callback.message, state, lang)
    await callback.answer()


@router.callback_query(F.data == "create_back_unit")
async def back_to_unit(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to unit selection."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return

    await _go_to_unit_step(callback.message, state, lang)


@router.callback_query(F.data == "create_back_expiry")
async def back_to_expiry(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to expiry selection."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return
    data = await state.get_data()

    text = _compose_step_message(
        data,
        lang,
        5,
        "Остаток и срок годности",
        "Miqdor va yaroqlilik",
        "📦",
        get_text(lang, "offer_step3_expiry_hint"),
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


@router.callback_query(F.data == "create_publish")
async def create_publish(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Publish offer after confirmation."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return

    await _finalize_offer(callback.message, state, lang)
    await callback.answer()


@router.callback_query(F.data == "create_edit")
async def create_edit(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Return to step 1 for editing."""
    if not db or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    if not await _ensure_wizard_alive(callback, state, lang):
        await callback.answer()
        return

    data = await state.get_data()
    step_text = _compose_step_message(
        data,
        lang,
        1,
        "Товар",
        "Mahsulot",
        "🥗",
        get_text(lang, "offer_step1_category_hint"),
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


@router.callback_query(F.data == "create_another")
async def create_another(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start creating another offer."""
    if not db or not callback.message:
        await callback.answer()
        return

    # Simulate pressing "Добавить" button
    lang = db.get_user_language(callback.from_user.id)
    await state.update_data(wizard_started_at=time.time())

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
    await state.update_data(wizard_started_at=time.time())

    data = await state.get_data()
    step_text = _compose_step_message(
        data,
        lang,
        1,
        "Товар",
        "Mahsulot",
        "🥗",
        get_text(lang, "offer_step1_category_hint"),
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
        photo = offer.get("photo") or offer.get("photo_id")
        store_id = offer.get("store_id")
        expiry_date = offer.get("expiry_date", "")
    else:
        title = getattr(offer, "title", "")
        original_price = getattr(offer, "original_price", 0)
        discount_price = getattr(offer, "discount_price", 0)
        quantity = getattr(offer, "quantity", 0)
        category = getattr(offer, "category", "other")
        photo = getattr(offer, "photo", None) or getattr(offer, "photo_id", None)
        store_id = getattr(offer, "store_id", None)
        expiry_date = getattr(offer, "expiry_date", "")

    # Calculate discount percent
    discount_percent = calc_discount_percent(original_price, discount_price)

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
