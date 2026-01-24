"""Payment proof admin message builders."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _fmt_money(value: int | float | None) -> str:
    try:
        return f"{int(value or 0):,}"
    except Exception:
        return "0"


def build_admin_payment_proof_caption(
    *,
    order_id: int,
    customer_name: str,
    customer_phone: str | None,
    store_name: str | None,
    delivery_address: str | None,
    cart_items: list[dict] | None,
    total_price: int | float | None,
    delivery_fee: int | float | None,
    lang: str = "ru",
) -> str:
    ru = lang != "uz"
    currency = "сум" if ru else "so'm"
    client_label = "Клиент" if ru else "Mijoz"
    phone_label = "Телефон" if ru else "Telefon"
    store_label = "Магазин" if ru else "Do'kon"
    address_label = "Адрес" if ru else "Manzil"
    items_label = "Товары" if ru else "Mahsulotlar"
    total_label = "Итого" if ru else "Jami"
    delivery_label = "Доставка" if ru else "Yetkazish"

    caption = (
        "💳 <b>НОВАЯ ДОСТАВКА - ЧЕК НА ПРОВЕРКЕ</b>\n\n"
        if ru
        else "💳 <b>YANGI YETKAZISH - CHEK TEKSHIRUVDA</b>\n\n"
    )
    caption += (
        "🔄 <b>Статус:</b> ◼ ◼ ◼ ◼ ◼\n"
        "   <i>Ожидает подтверждения оплаты</i>\n\n"
        if ru
        else "🔄 <b>Status:</b> ◼ ◼ ◼ ◼ ◼\n   <i>To'lov tasdiqlanishini kutmoqda</i>\n\n"
    )
    caption += f"📦 <b>Заказ #{order_id}</b>\n"
    caption += f"👤 {customer_name or ('Клиент' if ru else 'Mijoz')}\n"

    if customer_phone:
        caption += f"📱 <code>{customer_phone}</code>\n"
    if store_name:
        caption += f"🏪 {store_name}\n"
    if delivery_address:
        caption += f"📍 {delivery_address}\n"

    if cart_items:
        caption += f"\n📋 <b>{items_label} ({len(cart_items)}):</b>\n"
        for idx, item in enumerate(cart_items[:5], 1):
            title = item.get("title", "Товар" if ru else "Mahsulot")
            qty = item.get("quantity", 1)
            price = item.get("price", 0)
            item_total = int(price) * int(qty)
            caption += f"{idx}. {title} × {qty} = {_fmt_money(item_total)} {currency}\n"
        if len(cart_items) > 5:
            caption += f"   ... и ещё {len(cart_items) - 5}\n" if ru else f"   ... yana {len(cart_items) - 5}\n"

    subtotal = None
    try:
        subtotal = (total_price or 0) - (delivery_fee or 0)
    except Exception:
        subtotal = total_price or 0

    caption += f"\n💰 <b>{total_label}:</b>\n"
    caption += f"   {items_label}: {_fmt_money(subtotal)} {currency}\n"
    if delivery_fee:
        caption += f"   {delivery_label}: {_fmt_money(delivery_fee)} {currency}\n"
    caption += f"   <b>Всего: {_fmt_money(total_price)} {currency}</b>\n"
    caption += (
        "\n⚠️ <b>ПРОВЕРЬТЕ ЧЕК И ПОДТВЕРДИТЕ ОПЛАТУ</b>"
        if ru
        else "\n⚠️ <b>CHEKNI TEKSHIRING VA TO'LOVNI TASDIQLANG</b>"
    )
    return caption


def build_admin_payment_proof_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Оплата подтверждена",
                    callback_data=f"admin_confirm_payment_{order_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить заказ",
                    callback_data=f"admin_reject_payment_{order_id}",
                ),
            ],
        ]
    )
