"""
Booking UI components - card builders and keyboards.

Extracted from bookings/customer.py for maintainability.
"""
from __future__ import annotations

from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.common.utils import fix_mojibake_text, html_escape as _esc
from logging_config import logger
from localization import get_text


def build_order_card_text(
    lang: str,
    title: str,
    price: int,
    quantity: int,
    store_name: str,
    delivery_enabled: bool,
    delivery_price: int,
    delivery_method: str | None,
    max_qty: int,
    original_price: int = 0,
    description: str = "",
    expiry_date: str = "",
    store_address: str = "",
    unit: str = "",
) -> str:
    """Build order card in same style as product card."""
    currency = "so'm" if lang == "uz" else "сум"
    unit = unit or ("dona" if lang == "uz" else "шт")

    # Delivery fee is paid separately to courier/taxi driver.
    subtotal = price * quantity
    total = subtotal
    delivery_note = None
    if delivery_enabled and delivery_method == "delivery" and int(delivery_price or 0) > 0:
        delivery_note = get_text(lang, "delivery_fee_paid_to_courier")
        if delivery_note == "delivery_fee_paid_to_courier":
            delivery_note = None

    # Header - same as product card
    lines = [f"📦 <b>{_esc(title)}</b>"]

    if description:
        desc = description[:80] + "..." if len(description) > 80 else description
        lines.append(f"<i>{_esc(desc)}</i>")

    lines.append("")
    lines.append("─" * 25)

    # Price with discount - same style as product card
    if original_price and original_price > price:
        discount_pct = round((1 - price / original_price) * 100)
        lines.append(
            f"<s>{int(original_price):,}</s> → <b>{int(price):,}</b> {currency} (-{discount_pct}%)"
        )
    else:
        lines.append(f"💰 <b>{int(price):,}</b> {currency}")

    lines.append("─" * 25)
    lines.append("")

    # Quantity selection
    qty_label = "Miqdor" if lang == "uz" else "Количество"
    lines.append(f"📦 {qty_label}: <b>{quantity}</b> {unit}")

    # Expiry date if available
    if expiry_date:
        expiry_label = "Yaroqlilik" if lang == "uz" else "Срок до"
        expiry_str = str(expiry_date)[:10]
        try:
            from datetime import datetime

            dt = datetime.strptime(expiry_str, "%Y-%m-%d")
            expiry_str = dt.strftime("%d.%m.%Y")
        except ValueError:
            logger.debug("Could not parse expiry date: %s", expiry_str)
        lines.append(f"📅 {expiry_label}: {expiry_str}")

    # Store info - same style
    lines.append("")
    lines.append(f"🏪 {_esc(store_name)}")
    if store_address:
        lines.append(f"📍 {_esc(store_address)}")

    # Delivery section - cleaner style
    if delivery_enabled:
        lines.append("")
        delivery_label = "Yetkazish" if lang == "uz" else "Доставка"
        lines.append(f"🚚 {delivery_label}")

        # Show selection hint if not selected
        if not delivery_method:
            hint = "👇 Usulni tanlang" if lang == "uz" else "👇 Выберите способ"
            lines.append(f"<i>{hint}</i>")

    # Totals section
    lines.append("")
    lines.append("─" * 25)
    total_label = "JAMI" if lang == "uz" else "ИТОГО"
    lines.append(f"💵 <b>{total_label}: {total:,} {currency}</b>")
    if delivery_note:
        lines.append(f"   <i>{delivery_note}</i>")

    return fix_mojibake_text("\n".join(lines))


def build_order_card_keyboard(
    lang: str,
    offer_id: int,
    store_id: int,
    quantity: int,
    max_qty: int,
    delivery_enabled: bool,
    delivery_method: str | None,
) -> InlineKeyboardBuilder:
    """Build order card keyboard with quick quantity buttons and delivery options."""
    kb = InlineKeyboardBuilder()

    # Row 1: Quick quantity buttons [1] [2] [3] [5] or [−][qty][+] for large max
    if max_qty <= 10:
        # Show quick buttons for small quantities
        quick_qtys = [q for q in [1, 2, 3, 5, 10] if q <= max_qty]
        for q in quick_qtys[:4]:  # Max 4 quick buttons
            is_selected = quantity == q
            text = f"✓ {q}" if is_selected else str(q)
            kb.button(text=text, callback_data=f"pbook_qty_{offer_id}_{q}")
    else:
        # Show [−][qty][+] for large quantities
        minus_enabled = quantity > 1
        plus_enabled = quantity < max_qty

        minus_text = "➖" if minus_enabled else "▫️"
        plus_text = "➕" if plus_enabled else "▫️"

        kb.button(
            text=minus_text,
            callback_data=f"pbook_qty_{offer_id}_{quantity - 1}" if minus_enabled else "pbook_noop",
        )
        kb.button(text=f"📦 {quantity}", callback_data="pbook_noop")
        kb.button(
            text=plus_text,
            callback_data=f"pbook_qty_{offer_id}_{quantity + 1}" if plus_enabled else "pbook_noop",
        )

    # Row 2-3: Delivery options (if enabled)
    if delivery_enabled:
        pickup_text = "🏪 O'zim olib ketaman" if lang == "uz" else "🏪 Самовывоз"
        delivery_text = "🚚 Yetkazish" if lang == "uz" else "🚚 Доставка"

        # Add checkmarks for selected option
        if delivery_method == "pickup":
            pickup_text = "✓ " + pickup_text
        elif delivery_method == "delivery":
            delivery_text = "✓ " + delivery_text

        kb.button(text=pickup_text, callback_data=f"pbook_method_{offer_id}_pickup")
        kb.button(text=delivery_text, callback_data=f"pbook_method_{offer_id}_delivery")

    # Row 4: Confirm and Back
    if delivery_method or not delivery_enabled:
        confirm_text = "✅ Tasdiqlash" if lang == "uz" else "✅ Подтвердить"
        kb.button(text=confirm_text, callback_data=f"pbook_confirm_{offer_id}")

    back_text = "◀️ Orqaga" if lang == "uz" else "◀️ Назад"
    kb.button(text=back_text, callback_data=f"pbook_cancel_{offer_id}_{store_id}")

    # Layout - calculate based on what we have
    qty_button_count = (
        min(4, len([q for q in [1, 2, 3, 5, 10] if q <= max_qty])) if max_qty <= 10 else 3
    )
    if delivery_enabled:
        if delivery_method:
            kb.adjust(qty_button_count, 2, 2)  # qty buttons, [pickup][delivery], [confirm][back]
        else:
            kb.adjust(qty_button_count, 2, 1)  # qty buttons, [pickup][delivery], [back]
    else:
        kb.adjust(qty_button_count, 2)  # qty buttons, [confirm][back]

    return kb


def build_booking_list_text(lang: str, bookings: list, status_filter: str = "all") -> str:
    """Build booking list text."""
    if not bookings:
        if lang == "uz":
            return "📋 Bronlar yo'q"
        return "📋 Нет бронирований"

    lines = []
    if lang == "uz":
        title = (
            "📋 Sizning bronlaringiz" if status_filter == "all" else f"📋 Bronlar ({status_filter})"
        )
    else:
        title = (
            "📋 Ваши бронирования"
            if status_filter == "all"
            else f"📋 Бронирования ({status_filter})"
        )

    lines.append(f"<b>{title}</b>\n")

    for b in bookings[:10]:  # Limit to 10
        from .utils import get_booking_field

        booking_id = get_booking_field(b, "id")
        code = get_booking_field(b, "code", "—")
        status = get_booking_field(b, "status", "pending")

        status_emoji = {
            "pending": "⏳",
            "confirmed": "✅",
            "completed": "🎉",
            "cancelled": "❌",
        }.get(status, "❓")

        lines.append(f"{status_emoji} #{booking_id} | {code}")

    return fix_mojibake_text("\n".join(lines))


def build_booking_list_keyboard(lang: str, bookings: list) -> InlineKeyboardBuilder:
    """Build keyboard for booking list with cancel buttons."""
    kb = InlineKeyboardBuilder()

    for b in bookings[:5]:  # Limit buttons
        from .utils import get_booking_field

        booking_id = get_booking_field(b, "id")
        status = get_booking_field(b, "status", "pending")

        if status in ("pending", "confirmed"):
            text = f"❌ Отменить #{booking_id}" if lang == "ru" else f"❌ Bekor #{booking_id}"
            kb.button(text=text, callback_data=f"cancel_booking_{booking_id}")

    kb.adjust(1)
    return kb
