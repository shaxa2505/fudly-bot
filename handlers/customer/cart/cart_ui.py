"""
Cart UI components - card text builders and keyboards.

Extracted from cart/router.py for maintainability.
"""
from __future__ import annotations

from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_cart_add_card_text(
    lang: str,
    title: str,
    price: float,
    quantity: int,
    store_name: str,
    max_qty: int,
    original_price: float = 0,
    description: str = "",
    expiry_date: str = "",
    store_address: str = "",
    unit: str = "шт",
) -> str:
    """Build simplified cart addition card text - only quantity selection."""
    text_parts = []

    # Title
    text_parts.append(f"<b>{title}</b>")
    if description:
        text_parts.append(f"<i>{description}</i>")

    text_parts.append("")

    # Price
    if original_price and original_price > price:
        discount_pct = int(((original_price - price) / original_price) * 100)
        text_parts.append(
            f"<s>{original_price:,.0f}</s> → <b>{price:,.0f} сум</b> <code>(-{discount_pct}%)</code>"
        )
    else:
        text_parts.append(f"<b>{price:,.0f} сум</b>")

    # Quantity
    text_parts.append(
        f"Количество: <b>{quantity} {unit}</b>"
        if lang == "ru"
        else f"Miqdor: <b>{quantity} {unit}</b>"
    )

    # Stock
    stock_label = "В наличии" if lang == "ru" else "Omborda"
    text_parts.append(f"{stock_label}: {max_qty} {unit}")

    # Expiry
    if expiry_date:
        expiry_label = "Годен до" if lang == "ru" else "Srok"
        text_parts.append(f"{expiry_label}: {expiry_date}")

    text_parts.append("")

    # Store
    text_parts.append(f"<b>{store_name}</b>")
    if store_address:
        text_parts.append(store_address)

    text_parts.append("")

    # Total
    total = price * quantity
    text_parts.append(
        f"<b>ИТОГО: {total:,.0f} сум</b>"
        if lang == "ru"
        else f"<b>JAMI: {total:,.0f} so'm</b>"
    )

    return "\n".join(text_parts)


def build_cart_add_card_keyboard(
    lang: str, offer_id: int, quantity: int, max_qty: int
) -> InlineKeyboardBuilder:
    """Build simplified cart addition keyboard - quantity buttons + add to cart button."""
    kb = InlineKeyboardBuilder()

    # Simple quantity control: [ - ] [qty] [ + ]
    minus_btn = "-" if quantity > 1 else "."
    plus_btn = "+" if quantity < max_qty else "."

    kb.button(
        text=minus_btn,
        callback_data=f"cart_qty_{offer_id}_{quantity - 1}" if quantity > 1 else "cart_noop",
    )
    kb.button(text=str(quantity), callback_data="cart_noop")
    kb.button(
        text=plus_btn,
        callback_data=f"cart_qty_{offer_id}_{quantity + 1}" if quantity < max_qty else "cart_noop",
    )
    kb.adjust(3)

    # Add to cart button
    kb.button(
        text="➕ В корзину" if lang == "ru" else "➕ Savatga",
        callback_data=f"cart_add_confirm_{offer_id}",
    )

    # Cancel button
    kb.button(
        text="Отмена" if lang == "ru" else "Bekor qilish",
        callback_data=f"cart_add_cancel_{offer_id}",
    )

    kb.adjust(3, 1, 1)

    return kb


def build_cart_view_keyboard(
    lang: str, items_count: int, store_count: int = 1
) -> InlineKeyboardBuilder:
    """Build cart view keyboard."""
    kb = InlineKeyboardBuilder()

    if items_count > 0:
        # Checkout button
        kb.button(
            text="✅ Оформить заказ" if lang == "ru" else "✅ Buyurtma berish",
            callback_data="cart_checkout",
        )

        # Continue shopping
        kb.button(
            text="Продолжить покупки" if lang == "ru" else "Xaridni davom ettirish",
            callback_data="continue_shopping",
        )

        # Clear cart
        kb.button(
            text="Очистить корзину" if lang == "ru" else "Savatni tozalash",
            callback_data="cart_clear",
        )

        kb.adjust(1)
    else:
        # Empty cart - just continue shopping
        kb.button(
            text="К покупкам" if lang == "ru" else "Xaridga",
            callback_data="continue_shopping",
        )

    return kb


def build_checkout_method_keyboard(
    lang: str,
    has_pickup: bool = True,
    has_delivery: bool = True,
) -> InlineKeyboardBuilder:
    """Build checkout method selection keyboard."""
    kb = InlineKeyboardBuilder()

    if has_pickup:
        kb.button(
            text="🏪 Самовывоз" if lang == "ru" else "🏪 O'zim olaman",
            callback_data="cart_confirm_pickup",
        )

    if has_delivery:
        kb.button(
            text="🚚 Доставка" if lang == "ru" else "🚚 Yetkazib berish",
            callback_data="cart_confirm_delivery",
        )

    kb.button(
        text="Назад" if lang == "ru" else "Orqaga",
        callback_data="back_to_cart",
    )

    kb.adjust(1)
    return kb


def build_payment_method_keyboard(
    lang: str,
    order_type: str = "pickup",  # "pickup" or "delivery"
) -> InlineKeyboardBuilder:
    """Build payment method selection keyboard."""
    kb = InlineKeyboardBuilder()

    # Click payment
    kb.button(text="💳 Click", callback_data="cart_pay_click")

    # Card transfer
    kb.button(
        text="💳 Перевод на карту" if lang == "ru" else "💳 Kartaga o'tkazma",
        callback_data="cart_pay_card",
    )

    # Back button
    back_data = "cart_confirm_delivery" if order_type == "delivery" else "cart_confirm_pickup"
    kb.button(
        text="Назад" if lang == "ru" else "Orqaga",
        callback_data=back_data,
    )

    kb.adjust(2, 1)
    return kb
