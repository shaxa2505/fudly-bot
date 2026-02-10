"""
Delivery order UI components - card text builders and keyboards.

Extracted from delivery.py for maintainability.
"""
from __future__ import annotations

import os

from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.order_math import calc_total_price
from handlers.common.utils import html_escape as _esc
from localization import get_text


# =============================================================================
# DELIVERY ORDER CARD BUILDERS
# =============================================================================


def build_delivery_card_text(
    lang: str,
    title: str,
    price: int,
    quantity: int,
    max_qty: int,
    store_name: str,
    delivery_price: int,
    address: str | None,
    step: str,  # "qty" | "address" | "payment" | "processing"
) -> str:
    """Build delivery order card text."""
    currency = "so'm" if lang == "uz" else "сум"

    subtotal = price * quantity
    total = calc_total_price(subtotal, delivery_price)

    lines = [
        f"<b>{get_text(lang, 'delivery_card_title')}</b>",
        "",
        f"<b>{_esc(title)}</b>",
        _esc(store_name),
        "",
        "-" * 24,
    ]

    # Price info
    lines.append(f"{get_text(lang, 'delivery_price_label')}: {price:,} {currency}")
    lines.append(
        f"{get_text(lang, 'delivery_qty_label')}: <b>{quantity}</b> {'dona' if lang == 'uz' else 'шт'}"
    )
    lines.append(f"{get_text(lang, 'delivery_delivery_label')}: {delivery_price:,} {currency}")
    lines.append("-" * 24)
    lines.append(f"<b>{get_text(lang, 'delivery_total_label')}: {total:,} {currency}</b>")
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
    quantity: int,
    max_qty: int,
) -> InlineKeyboardBuilder:
    """Build quantity selection keyboard for delivery."""
    kb = InlineKeyboardBuilder()

    # Row 1: [-] [qty] [+]
    minus_ok = quantity > 1
    plus_ok = quantity < max_qty

    kb.button(
        text="-" if minus_ok else ".",
        callback_data=f"dlv_qty_{offer_id}_{quantity - 1}" if minus_ok else "dlv_noop",
    )
    kb.button(text=str(quantity), callback_data="dlv_noop")
    kb.button(
        text="+" if plus_ok else ".",
        callback_data=f"dlv_qty_{offer_id}_{quantity + 1}" if plus_ok else "dlv_noop",
    )

    # Row 2: Continue
    next_text = get_text(lang, "delivery_next_button")
    kb.button(text=next_text, callback_data=f"dlv_to_address_{offer_id}")

    # Row 3: Cancel
    kb.button(text=get_text(lang, "cancel"), callback_data="dlv_cancel")

    kb.adjust(3, 1, 1)
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
