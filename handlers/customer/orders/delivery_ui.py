"""
Delivery order UI components - card text builders and keyboards.

Extracted from delivery.py for maintainability.
"""
from __future__ import annotations

from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.common.utils import html_escape as _esc


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
    total = subtotal + delivery_price

    lines = [
        f"🚚 <b>{'Yetkazib berish' if lang == 'uz' else 'Доставка'}</b>",
        "",
        f"<b>{_esc(title)}</b>",
        _esc(store_name),
        "",
        "-" * 24,
    ]

    # Price info
    lines.append(f"{'Narxi' if lang == 'uz' else 'Цена'}: {price:,} {currency}")
    lines.append(
        f"{'Miqdor' if lang == 'uz' else 'Кол-во'}: <b>{quantity}</b> {'dona' if lang == 'uz' else 'шт'}"
    )
    lines.append(f"{'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}")
    lines.append("-" * 24)
    lines.append(f"<b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total:,} {currency}</b>")
    lines.append("")

    # Address section
    if address:
        lines.append(_esc(address))

    # Step-specific hints
    if step == "qty":
        hint = "Miqdorini tanlang" if lang == "uz" else "Выберите количество"
        lines.append(f"\n<i>{hint}</i>")
    elif step == "address":
        hint = "Manzilni kiriting yoki tanlang" if lang == "uz" else "Введите адрес или выберите"
        lines.append(f"\n<i>{hint}</i>")
    elif step == "payment":
        hint = "To'lov usulini tanlang" if lang == "uz" else "Выберите способ оплаты"
        lines.append(f"\n<i>{hint}</i>")
    elif step == "processing":
        hint = "Jarayonda..." if lang == "uz" else "Обработка..."
        lines.append(f"\n<i>{hint}</i>")

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
    next_text = "📍 Davom etish" if lang == "uz" else "📍 Продолжить"
    kb.button(text=next_text, callback_data=f"dlv_to_address_{offer_id}")

    # Row 3: Cancel
    cancel_text = "Bekor qilish" if lang == "uz" else "Отмена"
    kb.button(text=cancel_text, callback_data="dlv_cancel")

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
    manual_text = "✏️ Yangi manzil" if lang == "uz" else "✏️ Новый адрес"
    kb.button(text=manual_text, callback_data=f"dlv_new_address_{offer_id}")

    # Back and Cancel
    back_text = "Orqaga" if lang == "uz" else "Назад"
    cancel_text = "Bekor qilish" if lang == "uz" else "Отмена"
    kb.button(text=back_text, callback_data=f"dlv_back_qty_{offer_id}")
    kb.button(text=cancel_text, callback_data="dlv_cancel")

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

    # Payment options (Click only)
    click_text = "💳 Click"
    kb.button(text=click_text, callback_data=f"dlv_pay_click_{offer_id}")

    # Back and Cancel
    back_text = "Orqaga" if lang == "uz" else "Назад"
    cancel_text = "Bekor qilish" if lang == "uz" else "Отмена"
    kb.button(text=back_text, callback_data=f"dlv_back_address_{offer_id}")
    kb.button(text=cancel_text, callback_data="dlv_cancel")

    kb.adjust(1, 2)
    return kb
