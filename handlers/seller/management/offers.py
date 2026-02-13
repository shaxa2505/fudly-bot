"""Seller offer management handlers - CRUD operations for offers."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.units import effective_order_unit, parse_quantity_input
from app.domain.offer_rules import (
    DISCOUNT_MUST_BE_LOWER_MESSAGE,
    INVALID_OFFER_PRICE_MESSAGE,
    MIN_OFFER_DISCOUNT_MESSAGE,
    MIN_OFFER_DISCOUNT_PERCENT,
    validate_offer_prices,
)
from app.keyboards import main_menu_seller
from handlers.common.states import EditOffer
from handlers.common.utils import is_main_menu_button
from localization import get_text
from logging_config import logger

from .utils import (
    build_offer_card,
    format_quantity,
    get_category_labels,
    get_db,
    get_offer_discount_percent,
    get_offer_effective_status,
    get_offer_expiry_days,
    get_offer_field,
    get_offer_quantity_value,
    get_store_field,
    offer_has_photo,
    send_offer_card,
    update_offer_message,
)

router = Router()

MIN_DISCOUNT_PERCENT = MIN_OFFER_DISCOUNT_PERCENT

ITEMS_PER_PAGE = 5
MAX_PAGES = 50
MAX_ITEMS = ITEMS_PER_PAGE * MAX_PAGES
ATTENTION_STOCK_THRESHOLD = 5
ATTENTION_EXPIRY_DAYS = 2

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
            "Можно отправить процент: 30%. Минимум 20%."
        )
    return (
        "2 ta son yuboring: asl narx va chegirmali narx (misol: 10000 7000).\n"
        "Foiz ham mumkin: 30%. Kamida 20%."
    )


def _extract_numbers(text: str) -> list[int]:
    return [int(value) for value in re.findall(r"\d+", text or "")]


def _parse_quantity_value(raw_text: str | None, unit: str, *, allow_zero: bool = False) -> float:
    """Parse quantity for seller stock actions using shared unit rules."""
    raw = (raw_text or "").strip().replace(",", ".").replace(" ", "")
    if not raw:
        raise ValueError("invalid")
    if allow_zero and raw in {"0", "0.0", "0.00"}:
        return 0.0
    return float(parse_quantity_input(raw, unit))


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


def _is_low_stock(offer: object, threshold: int = ATTENTION_STOCK_THRESHOLD) -> bool:
    qty_value = get_offer_quantity_value(offer)
    return qty_value <= threshold


def _is_expiring_soon(offer: object, days: int = ATTENTION_EXPIRY_DAYS) -> bool:
    days_left = get_offer_expiry_days(offer)
    return days_left is not None and 0 <= days_left <= days


def _is_expired(offer: object) -> bool:
    days_left = get_offer_expiry_days(offer)
    return days_left is not None and days_left < 0


def _needs_attention(offer: object) -> bool:
    low_stock = _is_low_stock(offer)
    days_left = get_offer_expiry_days(offer)
    expiring = days_left is not None and 0 <= days_left <= ATTENTION_EXPIRY_DAYS
    expired = days_left is not None and days_left < 0
    no_photo = not offer_has_photo(offer)
    min_discount = MIN_DISCOUNT_PERCENT if MIN_DISCOUNT_PERCENT > 0 else None
    discount_percent = get_offer_discount_percent(offer)
    low_discount = min_discount is not None and discount_percent < min_discount
    return low_stock or expiring or expired or no_photo or low_discount


def _format_money(value: Any) -> str:
    try:
        return f"{int(float(value)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def _pluralize_days_ru(days: int) -> str:
    if days % 10 == 1 and days % 100 != 11:
        return "день"
    if 2 <= days % 10 <= 4 and not (12 <= days % 100 <= 14):
        return "дня"
    return "дней"


def _format_days(days: int, lang: str) -> str:
    if lang == "ru":
        return f"{days} {_pluralize_days_ru(days)}"
    return f"{days} kun"


def _format_expiry_line(offer: object, lang: str) -> str:
    label = get_text(lang, "seller_label_expiry")
    days_left = get_offer_expiry_days(offer)
    if days_left is None:
        return f"{label}: {get_text(lang, 'seller_expiry_no')}"
    if days_left < 0:
        return f"⚠️ {label}: {get_text(lang, 'seller_expiry_expired')}"
    days_text = _format_days(days_left, lang)
    if days_left <= ATTENTION_EXPIRY_DAYS:
        return f"⚠️ {label}: {days_text}"
    return f"{label}: {days_text}"


def _build_offer_list_item(offer: object, lang: str) -> str:
    title = get_offer_field(offer, "title", "Товар")
    original_price = get_offer_field(offer, "original_price", 0) or 0
    discount_price = get_offer_field(offer, "discount_price", 0) or 0
    discount_percent = get_offer_discount_percent(offer)

    qty = get_offer_quantity_value(offer)
    unit = get_offer_field(offer, "unit", "шт") or "шт"
    qty_display = format_quantity(qty, unit, lang)
    stock_label = get_text(lang, "seller_label_stock")
    if qty <= ATTENTION_STOCK_THRESHOLD:
        stock_line = f"⚠️ {stock_label}: {qty_display}"
    else:
        stock_line = f"{stock_label}: {qty_display}"

    price_line = (
        f"–{discount_percent}% | {_format_money(original_price)} → {_format_money(discount_price)}"
    )
    expiry_line = _format_expiry_line(offer, lang)

    return "\n".join([f"<b>{title}</b>", price_line, stock_line, expiry_line])


def _offer_sort_key(offer: object) -> tuple[int, date, float]:
    status = get_offer_effective_status(offer)
    status_rank = 0 if status == "active" else 1
    expiry_date = _parse_expiry_date(get_offer_field(offer, "expiry_date")) or date.max
    created_at = get_offer_field(offer, "created_at")
    created_ts = 0.0
    if isinstance(created_at, datetime):
        created_ts = created_at.timestamp()
    elif isinstance(created_at, date):
        created_ts = datetime.combine(created_at, datetime.min.time()).timestamp()
    elif isinstance(created_at, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                created_ts = datetime.strptime(created_at, fmt).timestamp()
                break
            except ValueError:
                continue
    return (status_rank, expiry_date, -created_ts)


def _collect_user_offers(db: Any, user_id: int) -> list[Any]:
    stores = db.get_user_accessible_stores(user_id)
    all_offers: list[Any] = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        offers = db.get_offers_by_store(store_id, include_all=True)
        all_offers.extend(offers)
    return all_offers


def _build_offers_main_screen(lang: str, all_offers: list[Any]) -> tuple[str, InlineKeyboardMarkup]:
    active_count = sum(1 for o in all_offers if get_offer_effective_status(o) == "active")
    inactive_count = len(all_offers) - active_count
    attention_count = sum(1 for o in all_offers if _needs_attention(o))
    total_count = len(all_offers)

    text = (
        f"<b>{get_text(lang, 'seller_items_title')}</b>\n\n"
        f"{get_text(lang, 'seller_items_active_label')}: <b>{active_count}</b>\n"
        f"{get_text(lang, 'seller_items_attention_label')}: <b>{attention_count}</b>\n"
        f"{get_text(lang, 'seller_items_inactive_label')}: <b>{inactive_count}</b>\n"
        f"{get_text(lang, 'seller_items_total_label')}: <b>{total_count}</b>\n"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                text=get_text(lang, "seller_items_active_btn"), callback_data="filter_offers_active_0"
            ),
            InlineKeyboardButton(
                text=get_text(lang, "seller_items_attention_btn"),
                callback_data="filter_offers_attention_0",
            ),
        ],
        [
            InlineKeyboardButton(
                text=get_text(lang, "seller_items_inactive_btn"),
                callback_data="filter_offers_inactive_0",
            ),
            InlineKeyboardButton(
                text=get_text(lang, "seller_items_search_btn"), callback_data="search_my_offers"
            ),
        ],
        [
            InlineKeyboardButton(
                text=get_text(lang, "seller_items_add_btn"), callback_data="add_offer"
            )
        ],
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)


class _MessageProxy:
    """Lightweight proxy to reuse message handlers from callback context."""

    def __init__(self, callback: types.CallbackQuery) -> None:
        self.from_user = callback.from_user
        self._callback = callback

    async def answer(self, *args: Any, **kwargs: Any) -> Any:
        if self._callback.message:
            return await self._callback.message.answer(*args, **kwargs)
        return await self._callback.bot.send_message(*args, chat_id=self.from_user.id, **kwargs)


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


def _search_offers(db: Any, user_id: int, query: str) -> list[Any]:
    all_offers = _collect_user_offers(db, user_id)
    results = []
    for offer in all_offers:
        title = str(get_offer_field(offer, "title", "") or "").lower()
        description = str(get_offer_field(offer, "description", "") or "").lower()
        category = str(get_offer_field(offer, "category", "") or "").lower()
        cat_ru, cat_uz = get_category_labels(get_offer_field(offer, "category", None))
        haystack = " ".join([title, description, category, cat_ru.lower(), cat_uz.lower()])
        if query in haystack:
            results.append(offer)
    return results


async def _send_offer_search_results(
    message: types.Message, lang: str, query: str, results: list[Any]
) -> None:
    if not results:
        await message.answer(get_text(lang, "no_results"), parse_mode="HTML")
        return

    results = results[:ITEMS_PER_PAGE]
    text = (
        f"<b>{get_text(lang, 'seller_items_search_results')}</b>\n"
        f"{get_text(lang, 'seller_items_found').format(count=len(results))}\n\n"
    )
    for offer in results:
        text += _build_offer_list_item(offer, lang) + "\n\n"

    keyboard: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(results), 2):
        row = []
        for offer in results[i : i + 2]:
            offer_id = get_offer_field(offer, "offer_id")
            title = str(get_offer_field(offer, "title", "Товар") or "")[:20]
            row.append(InlineKeyboardButton(text=title, callback_data=f"view_offer_{offer_id}"))
        keyboard.append(row)

    keyboard.append(
        [InlineKeyboardButton(text=get_text(lang, "seller_items_back_btn"), callback_data="back_to_offers_menu")]
    )

    await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.message(
    F.text.in_(
        {
            get_text("ru", "my_items"),
            get_text("uz", "my_items"),
            "Товары",
            "Mahsulotlar",
            "📦 Товары",
            "📦 Mahsulotlar",
        }
    )
    | F.text.contains("Мои товары")
    | F.text.contains("Mening mahsulotlarim")
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

    all_offers = _collect_user_offers(db, message.from_user.id)
    logger.info(f"Total offers: {len(all_offers)}")

    text, markup = _build_offers_main_screen(lang, all_offers)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)
    await state.set_state(EditOffer.browse)


@router.message(EditOffer.browse, F.text & ~F.text.startswith("/"))
async def my_offers_quick_search(message: types.Message, state: FSMContext) -> None:
    """Allow quick text search right after opening 'My items'."""
    if not message.text:
        return

    if is_main_menu_button(message.text):
        from handlers.seller.create_offer import _handle_main_menu_action

        handled = await _handle_main_menu_action(message, state)
        if handled:
            return

    db = get_db()
    lang = db.get_user_language(message.from_user.id)
    query = (message.text or "").strip().lower()

    if len(query) < 2:
        await message.answer("Минимум 2 символа" if lang == "ru" else "Kamida 2 ta belgi")
        return

    results = _search_offers(db, message.from_user.id, query)
    await _send_offer_search_results(message, lang, query, results)


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

    all_offers = _collect_user_offers(db, callback.from_user.id)

    # Apply filter
    if filter_type == "active":
        filtered = [o for o in all_offers if get_offer_effective_status(o) == "active"]
        title = get_text(lang, "seller_items_active_label")
    elif filter_type == "inactive":
        filtered = [o for o in all_offers if get_offer_effective_status(o) != "active"]
        title = get_text(lang, "seller_items_inactive_label")
    elif filter_type == "attention":
        filtered = [o for o in all_offers if _needs_attention(o)]
        title = get_text(lang, "seller_items_attention_label")
    elif filter_type == "low":
        filtered = [o for o in all_offers if _is_low_stock(o)]
        title = get_text(lang, "seller_items_attention_label")
    elif filter_type == "expiring":
        filtered = [o for o in all_offers if _is_expiring_soon(o)]
        title = get_text(lang, "seller_items_attention_label")
    elif filter_type == "all":
        filtered = all_offers
        title = get_text(lang, "seller_items_title")
    else:
        filtered = all_offers
        title = get_text(lang, "seller_items_title")

    if not filtered:
        await callback.answer(get_text(lang, "seller_items_not_found"), show_alert=True)
        return

    filtered = sorted(filtered, key=_offer_sort_key)
    if len(filtered) > MAX_ITEMS:
        filtered = filtered[:MAX_ITEMS]

    # Pagination
    total_pages = max(1, (len(filtered) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = min(page, total_pages - 1)
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_offers = filtered[start_idx:end_idx]

    text = f"<b>{title}</b>\n"
    text += f"{get_text(lang, 'seller_items_page_label')} {page + 1} / {total_pages}\n\n"

    for offer in page_offers:
        text += _build_offer_list_item(offer, lang) + "\n\n"

    keyboard: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(page_offers), 2):
        row = []
        for offer in page_offers[i : i + 2]:
            offer_id = get_offer_field(offer, "offer_id")
            title_btn = str(get_offer_field(offer, "title", "Товар") or "")[:20]
            row.append(InlineKeyboardButton(text=title_btn, callback_data=f"view_offer_{offer_id}"))
        keyboard.append(row)

    prev_cb = f"filter_offers_{filter_type}_{page - 1}" if page > 0 else "noop"
    next_cb = f"filter_offers_{filter_type}_{page + 1}" if page < total_pages - 1 else "noop"
    keyboard.append(
        [
            InlineKeyboardButton(text="◀️", callback_data=prev_cb),
            InlineKeyboardButton(text=f"{page + 1} / {total_pages}", callback_data="noop"),
            InlineKeyboardButton(text="▶️", callback_data=next_cb),
        ]
    )
    keyboard.append(
        [InlineKeyboardButton(text=get_text(lang, "seller_items_back_btn"), callback_data="back_to_offers_menu")]
    )

    await callback.answer()

    try:
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception:
        await callback.message.answer(
            text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )


@router.callback_query(F.data == "back_to_offers_menu")
async def back_to_offers_menu(callback: types.CallbackQuery) -> None:
    """Return to main offers menu."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    all_offers = _collect_user_offers(db, callback.from_user.id)
    text, markup = _build_offers_main_screen(lang, all_offers)

    await callback.answer()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "add_offer")
async def add_offer_from_items(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start add offer flow from items section."""
    from handlers.seller.create_offer import add_offer_start

    await add_offer_start(_MessageProxy(callback), state)
    await callback.answer()


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
        get_text(lang, "seller_items_search_prompt"),
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

    results = _search_offers(db, message.from_user.id, query)
    await _send_offer_search_results(message, lang, query, results)


@router.callback_query(F.data.startswith("qty_add_"))
async def quantity_add(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Increase offer quantity."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    parsed = _parse_qty_delta(callback.data, 1)
    if not parsed:
        logger.error(f"Invalid offer_id in callback data: {callback.data}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    offer_id, delta = parsed
    parts = callback.data.split("_")
    has_explicit_delta = len(parts) >= 4 and parts[-2].isdigit()

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    offer_store_id = get_offer_field(offer, "store_id")
    offer_unit = effective_order_unit(get_offer_field(offer, "unit", "piece"))
    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    if not has_explicit_delta:
        await state.update_data(
            offer_id=offer_id,
            edit_field="quantity_add",
            card_message_id=getattr(callback.message, "message_id", None),
            card_chat_id=getattr(callback.message, "chat", None).id if callback.message else None,
        )
        await state.set_state(EditOffer.value)
        await callback.message.answer(get_text(lang, "seller_prompt_add_stock"), parse_mode="HTML")
        await callback.answer()
        return

    try:
        new_quantity = db.increment_offer_quantity_atomic(offer_id, delta)
    except Exception as e:
        logger.error(f"Failed to increment quantity for {offer_id}: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    new_quantity_text = format_quantity(new_quantity, offer_unit, lang)
    delta_text = format_quantity(abs(delta), offer_unit, lang)
    await update_offer_message(callback, offer_id, lang)
    await callback.answer(
        (
            f"Количество увеличено на {delta_text}"
            if lang == "ru"
            else f"Miqdor {delta_text} ga oshirildi"
        )
        + f" ({new_quantity_text})"
    )


@router.callback_query(F.data.startswith("qty_sub_"))
async def quantity_subtract(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Decrease offer quantity."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    parsed = _parse_qty_delta(callback.data, -1)
    if not parsed:
        logger.error(f"Invalid offer_id in callback data: {callback.data}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    offer_id, delta = parsed
    parts = callback.data.split("_")
    has_explicit_delta = len(parts) >= 4 and parts[-2].isdigit()

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    offer_store_id = get_offer_field(offer, "store_id")
    offer_unit = effective_order_unit(get_offer_field(offer, "unit", "piece"))
    user_stores = db.get_user_accessible_stores(callback.from_user.id)
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    if not has_explicit_delta:
        await state.update_data(
            offer_id=offer_id,
            edit_field="quantity_sub",
            card_message_id=getattr(callback.message, "message_id", None),
            card_chat_id=getattr(callback.message, "chat", None).id if callback.message else None,
        )
        await state.set_state(EditOffer.value)
        await callback.message.answer(get_text(lang, "seller_prompt_sub_stock"), parse_mode="HTML")
        await callback.answer()
        return

    try:
        new_quantity = db.increment_offer_quantity_atomic(offer_id, delta)
    except Exception as e:
        logger.error(f"Failed to decrement quantity for {offer_id}: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    new_quantity_text = format_quantity(new_quantity, offer_unit, lang)
    delta_text = format_quantity(abs(delta), offer_unit, lang)
    await update_offer_message(callback, offer_id, lang)

    if new_quantity == 0:
        await callback.answer(get_text(lang, "seller_stock_zero"), show_alert=True)
    else:
        await callback.answer(
            (
                f"Количество уменьшено на {delta_text}"
                if lang == "ru"
                else f"Miqdor {delta_text} ga kamaytirildi"
            )
            + f" ({new_quantity_text})"
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
async def edit_offer(callback: types.CallbackQuery, state: FSMContext) -> None:
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

    await state.update_data(
        card_message_id=getattr(callback.message, "message_id", None),
        card_chat_id=getattr(callback.message, "chat", None).id if callback.message else None,
    )

    kb = InlineKeyboardBuilder()
    kb.button(
        text="Изменить цену" if lang == "ru" else "Narxni o'zgartirish",
        callback_data=f"edit_price_{offer_id}",
    )
    kb.button(
        text="Изменить остаток" if lang == "ru" else "Miqdorni o'zgartirish",
        callback_data=f"edit_quantity_{offer_id}",
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
        text="Изменить категорию" if lang == "ru" else "Kategoriyani o'zgartirish",
        callback_data=f"edit_category_{offer_id}",
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
        (
            "Введите дату (ДД.ММ или ДД.ММ.ГГГГ) или 0/без срока"
            if lang == "ru"
            else "Sana kiriting (KK.OO yoki KK.OO.YYYY) yoki 0/muddatsiz"
        ),
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

    unit = effective_order_unit(get_offer_field(offer, "unit", "piece"))
    current_qty = get_offer_field(offer, "quantity", 0) or 0
    current_qty_text = format_quantity(current_qty, unit, lang)

    await state.update_data(offer_id=offer_id, edit_field="quantity")
    await state.set_state(EditOffer.value)

    text = (
        f"{get_text(lang, 'seller_label_stock')}\n"
        f"{'Текущая' if lang == 'ru' else 'Joriy'}: {current_qty_text}"
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
    card_message_id = data.get("card_message_id")
    card_chat_id = data.get("card_chat_id")
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
            if discount_percent < MIN_DISCOUNT_PERCENT:
                await message.answer(get_text(lang, "error_min_discount"))
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

        try:
            validate_offer_prices(original_price, discount_price, require_both=True)
        except ValueError as exc:
            message_text = str(exc)
            if message_text == MIN_OFFER_DISCOUNT_MESSAGE:
                await message.answer(get_text(lang, "error_min_discount"))
            elif message_text == DISCOUNT_MUST_BE_LOWER_MESSAGE:
                await message.answer(get_text(lang, "error_discount_less_than_original"))
            elif message_text == INVALID_OFFER_PRICE_MESSAGE:
                await message.answer(get_text(lang, "error_price_gt_zero"))
            else:
                await message.answer(message_text)
            return

        db.update_offer(
            offer_id=offer_id,
            original_price=original_price,
            discount_price=discount_price,
        )
    elif edit_field == "quantity":
        unit = effective_order_unit(get_offer_field(offer, "unit", "piece"))
        try:
            quantity = _parse_quantity_value(message.text, unit, allow_zero=True)
        except ValueError as exc:
            code = str(exc)
            if code == "integer":
                await message.answer(get_text(lang, "quantity_integer_only"))
            elif code == "step":
                await message.answer(get_text(lang, "offer_error_quantity_step"))
            else:
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
                "Формат: ДД.ММ или ДД.ММ.ГГГГ (например 25.12 или 25.12.2027)"
                if lang == "ru"
                else "Format: KK.OO yoki KK.OO.YYYY (masalan 25.12 yoki 25.12.2027)"
            )
            return
        db.update_offer_expiry(offer_id, expiry_value)
    elif edit_field in ("quantity_add", "quantity_sub"):
        unit = effective_order_unit(get_offer_field(offer, "unit", "piece"))
        try:
            amount = _parse_quantity_value(message.text, unit, allow_zero=False)
        except ValueError as exc:
            code = str(exc)
            if code == "integer":
                await message.answer(get_text(lang, "quantity_integer_only"))
            elif code == "step":
                await message.answer(get_text(lang, "offer_error_quantity_step"))
            else:
                await message.answer(get_text(lang, "error_qty_gt_zero"))
            return
        delta = amount
        if edit_field == "quantity_sub":
            delta = -delta
        db.increment_offer_quantity_atomic(offer_id, delta)
    else:
        await state.clear()
        await message.answer(get_text(lang, "error_general"), reply_markup=main_menu_seller(lang))
        return

    await state.clear()

    updated_offer = db.get_offer(offer_id)
    if updated_offer:
        if card_message_id and card_chat_id:
            text, markup = build_offer_card(updated_offer, lang)
            try:
                await message.bot.edit_message_text(
                    text,
                    chat_id=card_chat_id,
                    message_id=card_message_id,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            except Exception:
                await send_offer_card(message, updated_offer, lang)
        else:
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
