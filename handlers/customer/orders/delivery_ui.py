"""
Delivery order UI components - card text builders and keyboards.

Extracted from delivery.py for maintainability.
"""
from __future__ import annotations

import os

from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.units import calc_total_price as calc_total_price_units
from app.core.units import format_quantity, normalize_unit, unit_label
from handlers.common.utils import html_escape as _esc
from localization import get_text


# =============================================================================
# DELIVERY ORDER CARD BUILDERS
# =============================================================================


def build_delivery_card_text(
    lang: str,
    title: str,
    price: int,
    quantity: float,
    max_qty: float,
    store_name: str,
    delivery_price: int,
    address: str | None,
    step: str,  # "qty" | "address" | "payment" | "processing"
    unit: str = "piece",
) -> str:
    """Build delivery order card text."""
    currency = "so'm" if lang == "uz" else "сум"
    unit_type = normalize_unit(unit)
    unit_text = unit_label(unit_type, lang)
    qty_text = format_quantity(quantity, unit_type, lang)

    subtotal = calc_total_price_units(price, quantity)
    total = subtotal

    lines = [
        f"<b>{get_text(lang, 'delivery_card_title')}</b>",
        "",
        f"<b>{_esc(title)}</b>",
        _esc(store_name),
        "",
        "-" * 24,
    ]

    # Price info
    price_text = f"{price:,} {currency}"
    if unit_type != "piece":
        price_text = f"{price:,} {currency} / {unit_text}"
    lines.append(f"{get_text(lang, 'delivery_price_label')}: {price_text}")
    lines.append(
        f"{get_text(lang, 'delivery_qty_label')}: <b>{qty_text}</b> {unit_text}"
    )
    lines.append("-" * 24)
    lines.append(f"<b>{get_text(lang, 'delivery_total_label')}: {total:,} {currency}</b>")
    if delivery_price:
        delivery_note = get_text(lang, "delivery_fee_paid_to_courier")
        if delivery_note and delivery_note != "delivery_fee_paid_to_courier":
            lines.append(f"<i>{delivery_note}</i>")
    lines.append("")

    # Address section
    if address:
        lines.append(_esc(address))

    # Step-specific hints
    if step == "qty":
        lines.append(f"\n<i>{get_text(lang, 'delivery_qty_hint')}</i>")
    elif step == "address":
        lines.append(f"\n<i>{get_text(lang, 'delivery_address_hint')}</i>")
    elif step == "payment":
        lines.append(f"\n<i>{get_text(lang, 'delivery_payment_hint')}</i>")
    elif step == "processing":
        lines.append(f"\n<i>{get_text(lang, 'delivery_processing_hint')}</i>")

    return "\n".join(lines)


def build_delivery_qty_keyboard(
    lang: str,
    offer_id: int,
    quantity: float,
    max_qty: float,
    unit: str = "piece",
) -> InlineKeyboardBuilder:
    """Build quantity selection keyboard for delivery."""
    kb = InlineKeyboardBuilder()

    unit_type = normalize_unit(unit)
    unit_text = unit_label(unit_type, lang)

    if unit_type == "piece":
        minus_ok = quantity > 1
        plus_ok = quantity < max_qty

        kb.button(
            text="-" if minus_ok else ".",
            callback_data=f"dlv_qty_{offer_id}_{int(quantity - 1)}" if minus_ok else "dlv_noop",
        )
        kb.button(text=str(int(quantity)), callback_data="dlv_noop")
        kb.button(
            text="+" if plus_ok else ".",
            callback_data=f"dlv_qty_{offer_id}_{int(quantity + 1)}" if plus_ok else "dlv_noop",
        )
        kb.adjust(3)
    else:
        if unit_type in {"kg", "l"}:
            options = [0.5, 1, 2, 5]
        elif unit_type == "g":
            options = [200, 500, 1000]
        else:
            options = [250, 500, 1000]

        for opt in options:
            if max_qty > 0 and opt > max_qty:
                continue
            label = f"{format_quantity(opt, unit_type, lang)} {unit_text}"
            kb.button(text=label, callback_data=f"dlv_qty_{offer_id}_{opt}")
        kb.button(
            text="Другое" if lang == "ru" else "Boshqa",
            callback_data=f"dlv_qty_custom_{offer_id}",
        )
        kb.adjust(2)

    next_text = get_text(lang, "delivery_next_button")
    kb.button(text=next_text, callback_data=f"dlv_to_address_{offer_id}")
    kb.button(text=get_text(lang, "cancel"), callback_data="dlv_cancel")

    if unit_type == "piece":
        kb.adjust(3, 1, 1)
    else:
        kb.adjust(2, 1, 1)
    return kb


def build_delivery_address_keyboard(
    lang: str,
    offer_id: int,
    saved_address: str | None,
) -> InlineKeyboardBuilder:
    """Build address selection keyboard."""
    kb = InlineKeyboardBuilder()

    # If user has saved address - show button to use it
    if saved_address:
        short_addr = saved_address[:30] + "..." if len(saved_address) > 30 else saved_address
        kb.button(text=short_addr, callback_data=f"dlv_use_saved_{offer_id}")

    # Manual input button
    manual_text = get_text(lang, "delivery_new_address_button")
    kb.button(text=manual_text, callback_data=f"dlv_new_address_{offer_id}")

    # Back and Cancel
    kb.button(text=get_text(lang, "back"), callback_data=f"dlv_back_qty_{offer_id}")
    kb.button(text=get_text(lang, "cancel"), callback_data="dlv_cancel")

    if saved_address:
        kb.adjust(1, 1, 2)
    else:
        kb.adjust(1, 2)

    return kb


def build_delivery_payment_keyboard(
    lang: str,
    offer_id: int,
) -> InlineKeyboardBuilder:
    """Build payment method selection keyboard."""
    kb = InlineKeyboardBuilder()

    cash_enabled = _delivery_cash_enabled()
    if cash_enabled:
        kb.button(
            text=get_text(lang, "delivery_payment_cash_button"),
            callback_data=f"dlv_pay_cash_{offer_id}",
        )

    # Payment options (Click)
    kb.button(
        text=get_text(lang, "delivery_payment_click_button"),
        callback_data=f"dlv_pay_click_{offer_id}",
    )

    # Back and Cancel
    kb.button(text=get_text(lang, "back"), callback_data=f"dlv_back_address_{offer_id}")
    kb.button(text=get_text(lang, "cancel"), callback_data="dlv_cancel")

    if cash_enabled:
        kb.adjust(1, 1, 2)
    else:
        kb.adjust(1, 2)
    return kb


def _delivery_cash_enabled() -> bool:
    return os.getenv("FUDLY_DELIVERY_CASH_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
