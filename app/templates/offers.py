"""Text templates for offer-related handlers."""
from __future__ import annotations

from typing import Any, Iterable, Sequence

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
    lines.append(f"Показано: {shown} из {total_count}")
    lines.append("")

    for idx, offer in enumerate(offers, offset + 1):
        name = _trim_title(offer.title)
        price_line = _format_price_line(offer, lang)
        store_line = f"   {offer.store_name}"
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

    lines = [f"{emoji} <b>{title}</b>", f"📍 {city}", ""]
    for idx, store in enumerate(stores, 1):
        address = f"\n   📍 {store.address}" if store.address else ""
        ratings = f"{store.rating:.1f}/5 ({store.ratings_count})"
        offers_text = "Предложений" if lang == "ru" else "Takliflar"
        lines.append(f"{idx}. <b>{store.name}</b>")
        if address:
            lines.append(address.strip())
        lines.append(f"   ⭐ {ratings}")
        lines.append(f"   🔥 {offers_text}: {store.offers_count}")
        lines.append("")

    prompt = (
        "💬 Введите номер магазина для просмотра"
        if lang == "ru"
        else "💬 Do'kon raqamini kiriting"
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

    lines = [f"{emoji} <b>{store.name}</b>"]
    lines.append(f"🏷 {type_name}")
    location = ", ".join(filter(None, [store.address, store.city]))
    if location:
        lines.append(f"📍 {location}")
    if store.description:
        lines.append(f"📝 {store.description}")
    if store.phone:
        lines.append(f"📞 {store.phone}")
    reviews_text = "отзывов" if lang == "ru" else "sharh"
    lines.append(f"⭐ {store.rating:.1f}/5 ({store.ratings_count} {reviews_text})")
    offers_label = "Горячих предложений" if lang == "ru" else "Issiq takliflar"
    lines.append(f"🔥 {offers_label}: {store.offers_count}")
    return "\n".join(lines)


def render_offer_details(lang: str, offer: OfferDetails, store: StoreDetails | None = None) -> str:
    lines = [f"<b>{offer.title}</b>"]
    if offer.description:
        lines.append(offer.description)
        lines.append("")
    lines.append(_format_price_line(offer, lang))
    lines.append("")
    
    # Магазин и адрес (без эмоджи, элегантно)
    store_name = store.name if store else offer.store_name
    store_address = store.address if store else offer.store_address
    store_city = store.city if store else offer.store_city
    lines.append(store_name)
    if store_address or store_city:
        location = " · ".join(filter(None, [store_address, store_city]))
        lines.append(location)
    lines.append("")
    
    # Доступность и срок годности
    lines.append(f"{'Доступно' if lang == 'ru' else 'Mavjud'}: {offer.quantity} {offer.unit}")
    if offer.expiry_date:
        expiry_label = "Годен до" if lang == "ru" else "Yaroqlilik"
        # Форматируем дату красиво: DD.MM.YYYY
        expiry_str = str(offer.expiry_date)[:10]
        try:
            from datetime import datetime
            dt = datetime.strptime(expiry_str, "%Y-%m-%d")
            expiry_str = dt.strftime("%d.%m.%Y")
        except:
            pass
        lines.append(f"{expiry_label}: {expiry_str}")

    # Доставка (если доступна)
    if store and store.delivery_enabled:
        lines.append("")
        currency = "сум" if lang == "ru" else "so'm"
        delivery_label = "Доставка" if lang == "ru" else "Yetkazib berish"
        lines.append(f"{delivery_label}: {store.delivery_price:,.0f} {currency}")
        if store.min_order_amount:
            min_label = "Мин. заказ" if lang == "ru" else "Min. buyurtma"
            lines.append(f"{min_label}: {store.min_order_amount:,.0f} {currency}")

    return "\n".join(lines)


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
    lines.append(f"Показано: {shown} из {total}")
    lines.append("")

    for idx, offer in enumerate(offers, offset + 1):
        price_line = _format_price_line(offer, lang)
        lines.append(f"{idx}. <b>{_trim_title(offer.title)}</b>")
        lines.append(f"   {price_line}")
        lines.append("")

    prompt = (
        "💬 Введите номер товара для просмотра"
        if lang == "ru"
        else "💬 Mahsulot raqamini kiriting"
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
    lines = [f"<b>{offer.title}</b>"]
    lines.append(_format_price_line(offer, lang))
    lines.append(offer.store_name)
    if offer.store_address:
        lines.append(offer.store_address)
    if offer.quantity is not None:
        stock_label = "Осталось" if lang == "ru" else "Qoldi"
        lines.append(f"{stock_label}: {offer.quantity} {offer.unit or ''}".strip())
    if offer.expiry_date:
        expiry_str = str(offer.expiry_date)[:10]
        try:
            from datetime import datetime
            dt = datetime.strptime(expiry_str, "%Y-%m-%d")
            expiry_str = dt.strftime("%d.%m.%Y")
        except:
            pass
        lines.append(f"До: {expiry_str}")
    return "\n".join(lines)


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
    
    return (
        f"<s>{offer.original_price:,.0f}</s> → <b>{offer.discount_price:,.0f} {currency}</b> ({discount}{fire})"
    )


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
