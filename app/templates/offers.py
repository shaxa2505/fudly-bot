"""Text templates for offer-related handlers."""
from __future__ import annotations

import html
from collections.abc import Iterable, Sequence
from typing import Any

from app.services.offer_service import OfferDetails, OfferListItem, StoreDetails, StoreSummary
from app.core.units import format_quantity, normalize_unit, unit_label
from localization import get_text


def render_hot_offers_list(
    lang: str,
    city: str,
    offers: Sequence[OfferListItem],
    total_count: int,
    select_hint: str,
    offset: int = 0,
) -> str:
    labels = _catalog_labels(lang)
    lines = [
        labels["title"],
        f"{city} • {labels['today']}",
        get_text(lang, "catalog_found", count=total_count),
        "",
    ]

    for offer in offers:
        lines.append(_render_catalog_item(lang, offer, labels))
        lines.append("")

    return "\n".join(lines).rstrip()


def render_hot_offers_empty(lang: str) -> str:
    return f"{get_text(lang, 'catalog_empty_title')}\n\n{get_text(lang, 'catalog_empty_subtitle')}"


def render_business_type_store_list(
    lang: str,
    business_type: str,
    city: str,
    stores: Sequence[StoreSummary],
    page: int = 0,
    per_page: int = 10,
) -> str:
    """Render store list in unified compact style like hot offers."""
    type_names = {
        "supermarket": "Супермаркеты" if lang == "ru" else "Supermarketlar",
        "restaurant": "Рестораны" if lang == "ru" else "Restoranlar",
        "bakery": "Пекарни" if lang == "ru" else "Nonvoyxonalar",
        "cafe": "Кафе" if lang == "ru" else "Kafelar",
        "pharmacy": "Аптеки" if lang == "ru" else "Dorixonalar",
        "delivery": "Доставка" if lang == "ru" else "Yetkazish",
    }
    title = type_names.get(business_type, business_type.replace("_", " ").title())
    city_label = "Город" if lang == "ru" else "Shahar"
    page_label = "Стр." if lang == "ru" else "Sah."

    total = len(stores)
    per_page = max(1, int(per_page))
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(int(page), total_pages - 1))
    start_idx = page * per_page
    page_stores = stores[start_idx : start_idx + per_page]

    total_label = "Всего" if lang == "ru" else "Jami"
    lines = [
        f"<b>{title}</b>",
        f"{city_label}: {city} | {page_label} {page + 1}/{total_pages} | {total_label} {total}",
        "",
    ]

    for idx, store in enumerate(page_stores, start_idx + 1):
        store_name = store.name or ("Магазин" if lang == "ru" else "Do'kon")
        name = store_name[:30] + "..." if len(store_name) > 30 else store_name
        line = f"{idx}. <b>{_escape(name)}</b>"
        if store.address:
            short_addr = store.address[:30] + "..." if len(store.address) > 30 else store.address
            line += f" - {_escape(short_addr)}"
        lines.append(line)

    return "\n".join(lines).rstrip()


def render_store_card(lang: str, store: StoreDetails) -> str:
    type_names = {
        "supermarket": "Супермаркет" if lang == "ru" else "Supermarket",
        "restaurant": "Ресторан" if lang == "ru" else "Restoran",
        "bakery": "Пекарня" if lang == "ru" else "Nonvoyxona",
        "cafe": "Кафе" if lang == "ru" else "Kafe",
        "pharmacy": "Аптека" if lang == "ru" else "Dorixona",
    }
    type_name = type_names.get(store.business_type, store.business_type)

    lines = []

    # Заголовок с названием и типом
    lines.append(f"<b>{_escape(store.name)}</b>")
    if type_name:
        lines.append(type_name)
    lines.append("")

    # Основная информация
    if store.city:
        city_label = "Город" if lang == "ru" else "Shahar"
        lines.append(f"{city_label}: {_escape(store.city)}")

    if store.address:
        address_label = "Адрес" if lang == "ru" else "Manzil"
        lines.append(f"{address_label}: {_escape(store.address)}")

    if store.description:
        description_label = "Описание" if lang == "ru" else "Tavsif"
        lines.append(f"{description_label}: {_escape(_trim_title(store.description, limit=120))}")
        lines.append("")

    # Статистика
    rating_label = "Рейтинг" if lang == "ru" else "Reyting"
    reviews_text = "отзывов" if lang == "ru" else "sharh"
    if store.ratings_count:
        rating_value = store.rating or 0
        lines.append(
            f"{rating_label}: {rating_value:.1f}/5 ({store.ratings_count} {reviews_text})"
        )
    else:
        lines.append(f"{rating_label}: —")

    offers_label = "Предложений" if lang == "ru" else "Takliflar"
    lines.append(f"{offers_label}: {store.offers_count}")

    currency = "сум" if lang == "ru" else "so'm"
    delivery_label = "Доставка" if lang == "ru" else "Yetkazib berish"
    if store.delivery_enabled is True:
        available = "доступна" if lang == "ru" else "mavjud"
        lines.append(f"{delivery_label}: {available}")
        if store.delivery_price > 0:
            cost_label = "Стоимость" if lang == "ru" else "Narx"
            lines.append(
                f"{cost_label}: {_format_money(store.delivery_price)} {currency}"
            )
        if store.min_order_amount > 0:
            min_order = "Мин. заказ" if lang == "ru" else "Min. buyurtma"
            lines.append(
                f"{min_order}: {_format_money(store.min_order_amount)} {currency}"
            )
    elif store.delivery_enabled is False:
        unavailable = "нет" if lang == "ru" else "yo'q"
        lines.append(f"{delivery_label}: {unavailable}")

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
    lines = [f"<b>{_escape(store_name)}</b>"]
    lines.append("Все товары" if lang == "ru" else "Barcha mahsulotlar")
    shown = offset + len(offers)
    shown_text = "Ko'rsatilgan" if lang == "uz" else "Показано"
    of_text = "dan" if lang == "uz" else "из"
    lines.append(f"{shown_text}: {shown} {of_text} {total}")
    lines.append("")

    for idx, offer in enumerate(offers, offset + 1):
        price_line = _format_price_line(offer, lang)
        lines.append(f"{idx}. <b>{_escape(_trim_title(offer.title))}</b> - {price_line}")

    return "\n".join(lines).rstrip()


def render_store_reviews(
    lang: str,
    store_name: str,
    avg_rating: float,
    reviews: Iterable[Sequence[Any]],
) -> str:
    header = "Отзывы" if lang == "ru" else "Sharhlar"
    avg_label = "Средняя оценка" if lang == "ru" else "O'rtacha baho"
    lines = [f"<b>{_escape(store_name)}</b>", header, f"{avg_label}: {avg_rating:.1f}/5"]
    lines.append("")
    reviews = list(reviews)
    if not reviews:
        lines.append("Отзывов пока нет" if lang == "ru" else "Hali sharhlar yo'q")
        return "\n".join(lines)

    for review in reviews[:5]:
        rating = review[3] if len(review) > 3 else 0
        comment = review[4] if len(review) > 4 else ""
        created_at = review[5] if len(review) > 5 else ""
        lines.append(f"Оценка: {rating}/5" if lang == "ru" else f"Baho: {rating}/5")
        if comment:
            label = "Комментарий" if lang == "ru" else "Izoh"
            lines.append(f"{label}: {_escape(comment)}")
        if created_at:
            label = "Дата" if lang == "ru" else "Sana"
            lines.append(f"{label}: {str(created_at)[:10]}")
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
    lines = [f"🧾 <b>{_escape(title)}</b>"]

    current_price = getattr(offer, "discount_price", None)
    if current_price is None:
        current_price = getattr(offer, "price", 0) or 0
    original_price = getattr(offer, "original_price", 0) or 0

    unit_type = normalize_unit(getattr(offer, "unit", "") or labels["unit"])
    unit_text = unit_label(unit_type, lang)

    if original_price and original_price > current_price:
        discount_pct = round((1 - current_price / original_price) * 100)
        discount_pct = min(99, max(1, discount_pct))
        lines.append(
            f"{labels['price']}: {_format_money(current_price)} {labels['currency']} / {unit_text} (-{discount_pct}%)"
        )
        lines.append(
            f"{labels['was']}: {_format_money(original_price)} {labels['currency']} / {unit_text}"
        )
    else:
        lines.append(f"{labels['price']}: {_format_money(current_price)} {labels['currency']} / {unit_text}")

    qty = getattr(offer, "quantity", None)
    if qty is not None:
        if qty <= 0:
            lines.append(labels["out_of_stock"])
        else:
            qty_text = format_quantity(qty, unit_type, lang)
            if unit_type == "piece":
                lines.append(f"{labels['in_stock']}: {qty_text} {unit_text}")
            else:
                upto = get_text(lang, "catalog_pickup_until_short")
                lines.append(f"{labels['in_stock']}: {upto} {qty_text} {unit_text}")

    optional: list[tuple[int, str]] = []

    expiry_date = getattr(offer, "expiry_date", None)
    if expiry_date:
        date_str = _format_date(expiry_date)
        if date_str:
            optional.append((1, f"{labels['expiry']}: {date_str}"))

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
        optional.append((2, f"{labels['store']}: {_escape(_trim_title(store_name, limit=28))}"))
    if store_address:
        optional.append(
            (3, f"{labels['address']}: {_escape(_trim_title(store_address, limit=32))}")
        )

    if delivery_enabled is True:
        if delivery_price and delivery_price > 0:
            optional.append(
                (4, f"{labels['delivery']}: {_format_money(delivery_price)} {labels['currency']}")
            )
        else:
            optional.append((4, labels["delivery_free"]))
        if min_order_amount and min_order_amount > 0:
            optional.append(
                (5, f"{labels['min_order']}: {_format_money(min_order_amount)} {labels['currency']}")
            )
    elif delivery_enabled is False:
        optional.append((4, labels["delivery_none"]))

    for _, line in sorted(optional, key=lambda item: item[0]):
        if len(lines) >= max_lines:
            break
        lines.append(line)

    return "\n".join(lines)


def formatProductCard(product: OfferListItem, lang: str = "ru") -> str:
    return format_product_card(product, lang=lang)


def _catalog_labels(lang: str) -> dict[str, str]:
    product_labels = _product_card_labels(lang)
    return {
        "title": get_text(lang, "catalog_title"),
        "today": get_text(lang, "catalog_today"),
        "discount": get_text(lang, "catalog_discount"),
        "price": get_text(lang, "catalog_price"),
        "store": get_text(lang, "catalog_store"),
        "pickup_until_short": get_text(lang, "catalog_pickup_until_short"),
        "expiry_until": get_text(lang, "catalog_expiry_until"),
        "was": get_text(lang, "catalog_was"),
        "currency": product_labels["currency"],
    }


def _render_catalog_item(
    lang: str,
    offer: OfferListItem,
    labels: dict[str, str],
) -> str:
    title = _escape(_trim_title(offer.title or "", limit=32))

    current_price = getattr(offer, "discount_price", None)
    if current_price is None:
        current_price = getattr(offer, "price", 0) or 0
    original_price = getattr(offer, "original_price", 0) or 0
    if not original_price or original_price < current_price:
        original_price = current_price

    discount_pct = getattr(offer, "discount_percent", 0) or 0
    if not discount_pct and original_price and original_price > current_price:
        discount_pct = round((1 - current_price / original_price) * 100)
    discount_pct = int(discount_pct) if discount_pct is not None else 0

    price_line = (
        f"–{discount_pct}%   {_format_money(current_price)} {labels['currency']} "
        f"({labels['was']} {_format_money(original_price)})"
    )

    store_name = getattr(offer, "store_name", "") or ""
    pickup_until = _format_time(getattr(offer, "available_until", None))
    expiry_date = (
        _format_date(getattr(offer, "expiry_date", None))
        if getattr(offer, "expiry_date", None)
        else ""
    )

    meta_parts = [f"📍 {_escape(_trim_title(store_name, limit=28))}"]
    if pickup_until:
        meta_parts.append(f"⏰ {labels['pickup_until_short']} {pickup_until}")
    if expiry_date:
        meta_parts.append(f"📅 {labels['expiry_until']} {expiry_date}")

    return "\n".join(
        [
            f"🥗 {title}",
            price_line,
            " • ".join(meta_parts),
        ]
    )


def _product_card_labels(lang: str) -> dict[str, str]:
    if lang == "ru":
        return {
            "currency": "сум",
            "price": "Цена",
            "was": "Было",
            "in_stock": "В наличии",
            "out_of_stock": "Нет в наличии",
            "expiry": "Срок",
            "store": "Магазин",
            "address": "Адрес",
            "delivery": "Доставка",
            "delivery_free": "Доставка: бесплатно",
            "delivery_none": "Только самовывоз",
            "min_order": "Мин. заказ",
            "unit": "шт",
        }
    return {
        "currency": "so'm",
        "price": "Narx",
        "was": "Avval",
        "in_stock": "Mavjud",
        "out_of_stock": "Mavjud emas",
        "expiry": "Yaroqlilik",
        "store": "Do'kon",
        "address": "Manzil",
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


def _format_time(value: str | Any) -> str:
    try:
        if value is None:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%H:%M")
        text = str(value)
        if "T" in text:
            text = text.split("T")[-1]
        if len(text) >= 5:
            return text[:5]
        return text
    except Exception:
        return ""


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
    currency = "сум" if lang == "ru" else "so'm"
    current_price = getattr(offer, "discount_price", None)
    if current_price is None:
        current_price = getattr(offer, "price", 0) or 0
    original_price = getattr(offer, "original_price", 0) or 0

    if original_price and original_price > current_price:
        discount_pct = round((1 - current_price / original_price) * 100)
        discount_pct = min(99, max(1, discount_pct))
        return f"{_format_money(current_price)} {currency} (-{discount_pct}%)"
    return f"{_format_money(current_price)} {currency}"


def _trim_title(title: str, limit: int = 30) -> str:
    if len(title) <= limit:
        return title
    return f"{title[: limit - 3]}..."


def _hot_header(lang: str, total: int = 0) -> str:
    title = "🥗 Еда со скидкой" if lang == "ru" else "🥗 Chegirmali taomlar"
    if total > 0:
        return f"<b>{title}</b> ({total})"
    return f"<b>{title}</b>"
