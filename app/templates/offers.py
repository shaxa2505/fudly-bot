"""Text templates for offer-related handlers."""
from __future__ import annotations

import html
from collections.abc import Iterable, Sequence
from typing import Any

from app.services.offer_service import OfferDetails, OfferListItem, StoreDetails, StoreSummary


def render_hot_offers_list(
    lang: str,
    city: str,
    offers: Sequence[OfferListItem],
    total_count: int,
    select_hint: str,
    offset: int = 0,
) -> str:
    header = _hot_header(lang, total_count)
    lines = [header, f"📍 {city}"]
    shown = offset + len(offers)
    shown_text = "Ko'rsatilgan" if lang == "uz" else "Показано"
    of_text = "dan" if lang == "uz" else "из"
    lines.append(f"{shown_text}: {shown} {of_text} {total_count}")
    lines.append("")

    # Category emoji mapping
    category_emoji = {
        "bakery": "🍞",
        "dairy": "🥛",
        "meat": "🥩",
        "fish": "🐟",
        "vegetables": "🥬",
        "fruits": "🍎",
        "cheese": "🧀",
        "beverages": "🥤",
        "ready_food": "🍱",
        "other": "🏪",
    }

    for idx, offer in enumerate(offers, offset + 1):
        name = _trim_title(offer.title)
        price_line = _format_price_line(offer, lang)

        # Get category emoji
        category = offer.store_category or "other"
        emoji = category_emoji.get(category, "🏪")

        # Format store line with emoji
        store_line = f"   {emoji} {offer.store_name}"

        lines.append(f"{idx}. <b>{name}</b>")
        lines.append(store_line)
        lines.append(f"   {price_line}")
        lines.append("")

    lines.append(select_hint)
    return "\n".join(lines)


def render_hot_offers_empty(lang: str) -> str:
    header = _hot_header(lang)
    wait_text = (
        "Мы уведомим вас, когда появятся новые предложения!"
        if lang == "ru"
        else "Yangi takliflar paydo bo'lganda xabar beramiz!"
    )
    return f"{header}\n\n{wait_text}"


def render_business_type_store_list(
    lang: str,
    business_type: str,
    city: str,
    stores: Sequence[StoreSummary],
) -> str:
    """Render store list in unified compact style like hot offers."""
    emoji_map = {
        "supermarket": "🛒",
        "restaurant": "🍽",
        "bakery": "🥖",
        "cafe": "☕",
        "pharmacy": "💊",
        "delivery": "🚚",
    }
    type_names = {
        "supermarket": "СУПЕРМАРКЕТЫ" if lang == "ru" else "SUPERMARKETLAR",
        "restaurant": "РЕСТОРАНЫ" if lang == "ru" else "RESTORANLAR",
        "bakery": "ПЕКАРНИ" if lang == "ru" else "NONVOYXONALAR",
        "cafe": "КАФЕ" if lang == "ru" else "KAFELAR",
        "pharmacy": "АПТЕКИ" if lang == "ru" else "DORIXONALAR",
        "delivery": "ДОСТАВКА" if lang == "ru" else "YETKAZISH",
    }
    emoji = emoji_map.get(business_type, "🏪")
    title = type_names.get(business_type, business_type.upper())

    # Header
    lines = [f"{emoji} <b>{title}</b>", f"📍 {city}"]

    # Count info
    total_text = "Найдено" if lang == "ru" else "Topildi"
    stores_word = "заведений" if lang == "ru" else "ta joy"
    lines.append(f"{total_text}: {len(stores)} {stores_word}")
    lines.append("")

    # Compact store list (like hot offers)
    for idx, store in enumerate(stores, 1):
        # Store name
        name = store.name[:30] + "..." if len(store.name) > 30 else store.name

        # Rating and offers count
        rating_str = f"⭐{store.rating:.1f}" if store.rating else "⭐—"
        offers_word = "шт" if lang == "ru" else "ta"
        offers_str = f"🔥{store.offers_count} {offers_word}" if store.offers_count else ""

        # Build line
        lines.append(f"{idx}. <b>{name}</b>")
        if store.address:
            short_addr = store.address[:25] + "..." if len(store.address) > 25 else store.address
            lines.append(f"   📍 {short_addr}")
        lines.append(f"   {rating_str} {offers_str}".strip())
        lines.append("")

    # Selection prompt
    prompt = (
        "👆 Нажмите на заведение для просмотра"
        if lang == "ru"
        else "👆 Ko'rish uchun joyni tanlang"
    )
    lines.append(prompt)
    return "\n".join(lines)


def render_store_card(lang: str, store: StoreDetails) -> str:
    type_names = {
        "supermarket": "Супермаркет" if lang == "ru" else "Supermarket",
        "restaurant": "Ресторан" if lang == "ru" else "Restoran",
        "bakery": "Пекарня" if lang == "ru" else "Nonvoyxona",
        "cafe": "Кафе" if lang == "ru" else "Kafe",
        "pharmacy": "Аптека" if lang == "ru" else "Dorixona",
    }
    emoji_map = {
        "supermarket": "🛒",
        "restaurant": "🍽",
        "bakery": "🥖",
        "cafe": "☕",
        "pharmacy": "💊",
    }
    emoji = emoji_map.get(store.business_type, "🏪")
    type_name = type_names.get(store.business_type, store.business_type)

    lines = []

    # Заголовок с названием и типом
    lines.append(f"{emoji} <b>{store.name}</b>")
    lines.append(f"<i>{type_name}</i>")
    lines.append("")

    # Основная информация
    lines.append("━━━━━━━━━━━━━━━━")

    # Адрес и контакты
    if store.city:
        city_label = "🏙 Город" if lang == "ru" else "🏙 Shahar"
        lines.append(f"{city_label}: {store.city}")

    if store.address:
        address_label = "📍 Адрес" if lang == "ru" else "📍 Manzil"
        lines.append(f"{address_label}: {store.address}")

    if store.phone:
        phone_label = "📞 Телефон" if lang == "ru" else "📞 Telefon"
        lines.append(f"{phone_label}: {store.phone}")

    lines.append("")

    # Описание
    if store.description:
        lines.append(f"📝 {store.description}")
        lines.append("")

    # Статистика
    lines.append("━━━━━━━━━━━━━━━━")

    reviews_text = "отзывов" if lang == "ru" else "sharh"
    lines.append(f"⭐ Рейтинг: <b>{store.rating:.1f}/5</b> ({store.ratings_count} {reviews_text})")

    offers_label = "Доступно товаров" if lang == "ru" else "Mavjud mahsulotlar"
    lines.append(f"🔥 {offers_label}: <b>{store.offers_count}</b>")

    # Информация о доставке
    if store.delivery_enabled:
        delivery_label = "🚚 Доставка" if lang == "ru" else "🚚 Yetkazib berish"
        available = "Доступна" if lang == "ru" else "Mavjud"
        lines.append(f"{delivery_label}: {available}")
        if store.delivery_price > 0:
            cost_label = "Стоимость" if lang == "ru" else "Narxi"
            lines.append(f"   {cost_label}: {store.delivery_price:,.0f} сум")
        if store.min_order_amount > 0:
            min_order = "Минимальный заказ" if lang == "ru" else "Minimal buyurtma"
            lines.append(f"   {min_order}: {store.min_order_amount:,.0f} сум")

    return "\n".join(lines)


def render_offer_details(lang: str, offer: OfferDetails, store: StoreDetails | None = None) -> str:
    return format_product_card(offer, lang=lang, store=store)
def render_store_offers_list(
    lang: str,
    store_name: str,
    offers: Sequence[OfferListItem],
    offset: int,
    total: int,
) -> str:
    lines = [f"🛍 <b>{store_name}</b>"]
    lines.append("Все товары" if lang == "ru" else "Barcha mahsulotlar")
    shown = offset + len(offers)
    shown_text = "Ko'rsatilgan" if lang == "uz" else "Показано"
    of_text = "dan" if lang == "uz" else "из"
    lines.append(f"{shown_text}: {shown} {of_text} {total}")
    lines.append("")

    for idx, offer in enumerate(offers, offset + 1):
        price_line = _format_price_line(offer, lang)
        lines.append(f"{idx}. <b>{_trim_title(offer.title)}</b>")
        lines.append(f"   {price_line}")
        lines.append("")

    prompt = (
        "💬 Введите номер товара для просмотра" if lang == "ru" else "💬 Mahsulot raqamini kiriting"
    )
    lines.append(prompt)
    return "\n".join(lines)


def render_store_reviews(
    lang: str,
    store_name: str,
    avg_rating: float,
    reviews: Iterable[Sequence[Any]],
) -> str:
    header = "Отзывы" if lang == "ru" else "Sharhlar"
    avg_label = "Средний рейтинг" if lang == "ru" else "O'rtacha reyting"
    lines = [f"⭐ <b>{store_name}</b>", header, f"{avg_label}: {avg_rating:.1f}/5"]
    lines.append("")
    reviews = list(reviews)
    if not reviews:
        lines.append("😔 Отзывов пока нет" if lang == "ru" else "😔 Hali sharhlar yo'q")
        return "\n".join(lines)

    for review in reviews[:5]:
        rating = review[3] if len(review) > 3 else 0
        comment = review[4] if len(review) > 4 else ""
        created_at = review[5] if len(review) > 5 else ""
        stars = "⭐" * int(rating or 0)
        lines.append(f"{stars} {rating}/5")
        if comment:
            lines.append(f"💬 {comment}")
        if created_at:
            lines.append(f"📅 {str(created_at)[:10]}")
        lines.append("")

    return "\n".join(lines).strip()


def render_offer_card(lang: str, offer: OfferListItem) -> str:
    return format_product_card(offer, lang=lang)

def format_product_card(
    offer: OfferListItem,
    lang: str = "ru",
    store: StoreDetails | None = None,
    max_lines: int = 10,
) -> str:
    labels = _product_card_labels(lang)
    raw_title = offer.title or ""
    if raw_title.startswith("Пример:"):
        raw_title = raw_title[7:].strip()
    title = _trim_title(raw_title, limit=36)
    lines = [f"🏷 <b>{_escape(title)}</b>"]

    current_price = getattr(offer, "discount_price", None)
    if current_price is None:
        current_price = getattr(offer, "price", 0) or 0
    original_price = getattr(offer, "original_price", 0) or 0

    if original_price and original_price > current_price:
        discount_pct = round((1 - current_price / original_price) * 100)
        discount_pct = min(99, max(1, discount_pct))
        lines.append(
            f"💰 <b>{_format_money(current_price)}</b> {labels['currency']} • -{discount_pct}%"
        )
        lines.append(
            f"<s>{_format_money(original_price)}</s> • {labels['save']} "
            f"{_format_money(original_price - current_price)} {labels['currency']}"
        )
    else:
        lines.append(f"💰 <b>{_format_money(current_price)}</b> {labels['currency']}")

    qty = getattr(offer, "quantity", None)
    if qty is not None:
        if qty <= 0:
            lines.append(labels["out_of_stock"])
        else:
            unit = offer.unit or labels["unit"]
            lines.append(f"📦 {labels['in_stock']}: {qty} {unit}")

    optional: list[tuple[int, str]] = []

    expiry_date = getattr(offer, "expiry_date", None)
    if expiry_date:
        date_str = _format_date(expiry_date)
        if date_str:
            if _days_until(expiry_date) <= 2:
                optional.append((1, f"⚠️ {labels['expiry']}: {date_str}"))
            else:
                optional.append((1, f"⏰ {labels['expiry']}: {date_str}"))

    store_name = None
    store_address = None
    delivery_enabled = None
    delivery_price = None
    min_order_amount = None
    if store:
        store_name = store.name
        store_address = store.address
        delivery_enabled = store.delivery_enabled
        delivery_price = store.delivery_price
        min_order_amount = store.min_order_amount
    else:
        store_name = getattr(offer, "store_name", None)
        store_address = getattr(offer, "store_address", None)
        delivery_enabled = getattr(offer, "delivery_enabled", None)
        delivery_price = getattr(offer, "delivery_price", None)
        min_order_amount = getattr(offer, "min_order_amount", None)

    if store_name:
        optional.append((1, f"🏪 {_escape(_trim_title(store_name, limit=28))}"))
    if store_address:
        optional.append((2, f"📍 {_escape(_trim_title(store_address, limit=32))}"))

    if delivery_enabled is True:
        if delivery_price and delivery_price > 0:
            optional.append(
                (3, f"🚚 {labels['delivery']}: {_format_money(delivery_price)} {labels['currency']}")
            )
        else:
            optional.append((3, f"🚚 {labels['delivery_free']}"))
        if min_order_amount and min_order_amount > 0:
            optional.append(
                (4, f"🧾 {labels['min_order']}: {_format_money(min_order_amount)} {labels['currency']}")
            )
    elif delivery_enabled is False:
        optional.append((3, f"🚶 {labels['delivery_none']}"))

    for _, line in sorted(optional, key=lambda item: item[0]):
        if len(lines) >= max_lines:
            break
        lines.append(line)

    return "\n".join(lines)


def formatProductCard(product: OfferListItem, lang: str = "ru") -> str:
    return format_product_card(product, lang=lang)


def _product_card_labels(lang: str) -> dict[str, str]:
    if lang == "ru":
        return {
            "currency": "сум",
            "save": "выгода",
            "in_stock": "В наличии",
            "out_of_stock": "⛔ Нет в наличии",
            "expiry": "Срок до",
            "delivery": "Доставка",
            "delivery_free": "Доставка: бесплатно",
            "delivery_none": "Только самовывоз",
            "min_order": "Мин. заказ",
            "unit": "шт",
        }
    return {
        "currency": "so'm",
        "save": "tejash",
        "in_stock": "Mavjud",
        "out_of_stock": "⛔ Mavjud emas",
        "expiry": "Yaroqlilik",
        "delivery": "Yetkazib berish",
        "delivery_free": "Yetkazib berish: bepul",
        "delivery_none": "Faqat olib ketish",
        "min_order": "Min. buyurtma",
        "unit": "dona",
    }


def _format_money(value: float) -> str:
    return f"{int(value):,}".replace(",", " ")


def _format_date(value: str | Any) -> str:
    try:
        from datetime import datetime

        if isinstance(value, str):
            expiry_str = value[:10]
            dt = datetime.strptime(expiry_str, "%Y-%m-%d")
        else:
            dt = value
        now = datetime.now()
        if dt.year == now.year:
            return dt.strftime("%d.%m")
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return str(value)[:10]


def _days_until(value: str | Any) -> int:
    try:
        from datetime import datetime

        if isinstance(value, str):
            expiry_str = value[:10]
            dt = datetime.strptime(expiry_str, "%Y-%m-%d")
        else:
            dt = value
        return int((dt.date() - datetime.now().date()).days)
    except Exception:
        return 999


def _escape(text: str) -> str:
    return html.escape(text or "")
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_price_line(offer: OfferListItem, lang: str) -> str:
    discount = f"-{offer.discount_percent:.0f}%"
    currency = "сум" if lang == "ru" else "so'm"

    # Добавляем огонь только для ТОП скидок (элегантно)
    fire = ""
    if offer.discount_percent >= 70:
        fire = " 🔥🔥"
    elif offer.discount_percent >= 60:
        fire = " 🔥"

    return f"<s>{offer.original_price:,.0f}</s> → <b>{offer.discount_price:,.0f} {currency}</b> ({discount}{fire})"


def _trim_title(title: str, limit: int = 30) -> str:
    if len(title) <= limit:
        return title
    return f"{title[: limit - 3]}..."


def _hot_header(lang: str, total: int = 0) -> str:
    if lang == "ru":
        title = f"<b>ГОРЯЧЕЕ</b> ({total})" if total > 0 else "<b>ГОРЯЧЕЕ</b>"
    else:
        title = f"<b>ISSIQ</b> ({total})" if total > 0 else "<b>ISSIQ</b>"
    return title
