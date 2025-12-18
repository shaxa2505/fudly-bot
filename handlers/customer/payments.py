"""
Telegram Payments integration for Click via Telegram Bot Payments.

This module handles:
- Creating invoices (send_invoice)
- Pre-checkout validation (pre_checkout_query)
- Successful payment handling (successful_payment)
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from aiogram import F, Router, types
from aiogram.types import LabeledPrice

if TYPE_CHECKING:
    from database_protocol import DatabaseProtocol

logger = logging.getLogger(__name__)

router = Router(name="payments")

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: types.Bot | None = None
get_text = None

# Telegram Payments provider token (required env var)
PROVIDER_TOKEN = os.getenv("TELEGRAM_PAYMENT_PROVIDER_TOKEN")
if not PROVIDER_TOKEN:
    logger.warning("⚠️ TELEGRAM_PAYMENT_PROVIDER_TOKEN not set - payments will not work")


def setup(
    database: DatabaseProtocol,
    bot_instance: types.Bot,
    get_text_func,
) -> None:
    """Setup module dependencies."""
    global db, bot, get_text
    db = database
    bot = bot_instance
    get_text = get_text_func
    logger.info("✅ Telegram Payments handler initialized")


async def create_invoice(
    chat_id: int,
    order_id: int,
    title: str,
    description: str,
    amount: int,
    photo_url: str | None = None,
    payload_data: dict | None = None,
) -> types.Message:
    """
    Create and send an invoice to user.

    Args:
        chat_id: Telegram user ID
        order_id: Order/booking ID for tracking
        title: Invoice title (product name)
        description: Invoice description
        amount: Amount in UZS (will be converted to smallest unit)
        photo_url: Optional product photo
        payload_data: Additional data to include in payload

    Returns:
        Sent message with invoice
    """
    if not bot:
        raise RuntimeError("Bot not initialized")

    # Build payload string (will be returned in successful_payment)
    import json

    payload = json.dumps({"order_id": order_id, "type": "order", **(payload_data or {})})

    # Prices in smallest currency unit (for UZS it's 1 UZS = 100 tiyin, but Telegram uses UZS directly)
    # For Click via Telegram, amount is in UZS
    prices = [
        LabeledPrice(label=title, amount=amount * 100)  # Convert to tiyin
    ]

    # Send invoice
    invoice_params = {
        "chat_id": chat_id,
        "title": title,
        "description": description,
        "payload": payload,
        "provider_token": PROVIDER_TOKEN,
        "currency": "UZS",
        "prices": prices,
        "start_parameter": f"order_{order_id}",
        "need_name": False,
        "need_phone_number": True,
        "need_email": False,
        "need_shipping_address": False,
        "is_flexible": False,
    }

    if photo_url:
        invoice_params["photo_url"] = photo_url
        invoice_params["photo_width"] = 512
        invoice_params["photo_height"] = 512

    return await bot.send_invoice(**invoice_params)


async def create_order_invoice(
    chat_id: int,
    order_id: int,
    items: list[dict],
    delivery_cost: int = 0,
    store_name: str = "",
) -> types.Message:
    """
    Create invoice for an order with multiple items.

    Args:
        chat_id: Telegram user ID
        order_id: Order ID
        items: List of items [{title, quantity, price}]
        delivery_cost: Delivery cost in UZS
        store_name: Store name for description
    """
    if not bot:
        raise RuntimeError("Bot not initialized")

    import json

    # Build prices list
    prices = []
    total = 0

    for item in items:
        item_total = item["price"] * item["quantity"]
        total += item_total
        label = f"{item['title']} x{item['quantity']}"
        prices.append(LabeledPrice(label=label, amount=item_total * 100))

    if delivery_cost > 0:
        prices.append(LabeledPrice(label="🚚 Yetkazib berish", amount=delivery_cost * 100))
        total += delivery_cost

    # Payload
    payload = json.dumps(
        {
            "order_id": order_id,
            "type": "multi_order",
            "items_count": len(items),
        }
    )

    # Build description
    items_text = ", ".join([f"{i['title']} x{i['quantity']}" for i in items[:3]])
    if len(items) > 3:
        items_text += f" va yana {len(items) - 3} ta"

    description = f"📦 {items_text}\n🏪 {store_name}" if store_name else f"📦 {items_text}"

    return await bot.send_invoice(
        chat_id=chat_id,
        title=f"Buyurtma #{order_id}",
        description=description[:255],  # Telegram limit
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency="UZS",
        prices=prices,
        start_parameter=f"order_{order_id}",
        need_name=False,
        need_phone_number=True,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False,
    )


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: types.PreCheckoutQuery) -> None:
    """
    Handle pre-checkout query from Telegram.

    This is called when user clicks "Pay" button.
    We must respond within 10 seconds - respond IMMEDIATELY first!
    """
    # CRITICAL: Answer immediately to avoid timeout
    # Telegram requires response within 10 seconds
    logger.info(f"🔔 PRE-CHECKOUT RECEIVED from user {pre_checkout_query.from_user.id}")

    try:
        # Answer OK immediately - we can validate async later
        await pre_checkout_query.answer(ok=True)
        logger.info(
            f"✅ Pre-checkout approved for payload: {pre_checkout_query.invoice_payload[:100]}"
        )
    except Exception as e:
        logger.error(f"❌ Pre-checkout error: {e}", exc_info=True)
        try:
            await pre_checkout_query.answer(ok=False, error_message="Xatolik yuz berdi")
        except Exception:
            pass


@router.message(F.successful_payment)
async def process_successful_payment(message: types.Message) -> None:
    """
    Handle successful payment notification from Telegram.
    Unified flow for both delivery and pickup orders.
    """
    import json

    payment = message.successful_payment
    user_id = message.from_user.id

    try:
        # Parse payload
        payload = json.loads(payment.invoice_payload)
        order_id = payload.get("order_id")
        order_type = payload.get("type", "order")

        # Get payment details
        total_amount = payment.total_amount / 100  # Convert from tiyin to UZS
        currency = payment.currency
        provider_charge_id = payment.provider_payment_charge_id
        phone = payment.order_info.phone_number if payment.order_info else None

        logger.info(
            f"💰 Click payment SUCCESS: order={order_id}, amount={total_amount}, type={order_type}"
        )

        if not db or not order_id:
            raise ValueError("No database or order_id")

        # Get order/booking details
        offer_id = None
        store_id = None
        quantity = 1
        address = None
        delivery_price = 0

        # Try to get from orders table first (delivery)
        order = None
        booking = None

        if hasattr(db, "get_order"):
            order = db.get_order(order_id)

        if order:
            # Delivery order
            offer_id = order.get("offer_id") if isinstance(order, dict) else None
            store_id = order.get("store_id") if isinstance(order, dict) else None
            quantity = order.get("quantity", 1) if isinstance(order, dict) else 1
            address = order.get("delivery_address") if isinstance(order, dict) else None
            delivery_price = order.get("delivery_price", 0) if isinstance(order, dict) else 0

            # Payment is confirmed by Telegram provider (Click)
            if hasattr(db, "update_payment_status"):
                db.update_payment_status(order_id, "confirmed")
            if hasattr(db, "update_order_status"):
                # Keep fulfillment status separate from payment
                db.update_order_status(order_id, "pending")
        else:
            # Try bookings table (pickup from hot_offer flow)
            if hasattr(db, "get_booking"):
                booking = db.get_booking(order_id)

            if booking:
                offer_id = (
                    booking.get("offer_id")
                    if isinstance(booking, dict)
                    else (booking[2] if len(booking) > 2 else None)
                )
                quantity = (
                    booking.get("quantity", 1)
                    if isinstance(booking, dict)
                    else (booking[3] if len(booking) > 3 else 1)
                )

                # Keep booking status separate from payment confirmation
                if hasattr(db, "update_booking_status"):
                    db.update_booking_status(order_id, "pending")

        # Get offer and store details
        offer = db.get_offer(offer_id) if offer_id else None
        offer_photo = None
        if offer:
            title = (
                offer.get("title")
                if isinstance(offer, dict)
                else (offer[2] if len(offer) > 2 else "Товар")
            )
            unit_price = (
                offer.get("discount_price", 0)
                if isinstance(offer, dict)
                else (offer[4] if len(offer) > 4 else 0)
            )
            # Get photo for partner notification
            offer_photo = (
                offer.get("photo")
                if isinstance(offer, dict)
                else (offer[10] if len(offer) > 10 else None)
            )
            if not store_id:
                store_id = (
                    offer.get("store_id")
                    if isinstance(offer, dict)
                    else (offer[1] if len(offer) > 1 else None)
                )
        else:
            title = "Товар"
            unit_price = 0

        store = db.get_store(store_id) if store_id else None
        store_name = ""
        store_address = ""
        owner_id = None

        if store:
            store_name = (
                store.get("name")
                if isinstance(store, dict)
                else (store[1] if len(store) > 1 else "")
            )
            store_address = (
                store.get("address")
                if isinstance(store, dict)
                else (store[3] if len(store) > 3 else "")
            )
            owner_id = (
                store.get("owner_id")
                if isinstance(store, dict)
                else (store[2] if len(store) > 2 else None)
            )

        # Get user language
        lang = db.get_user_language(user_id) or "uz"

        # Build detailed success message for customer
        is_delivery = bool(address)
        subtotal = unit_price * quantity

        # Text labels
        success_title = "To'lov muvaffaqiyatli!" if lang == "uz" else "Оплата успешна!"
        qty_label = "Miqdor" if lang == "uz" else "Кол-во"
        price_label = "Narxi" if lang == "uz" else "Цена"
        unit_label = "dona" if lang == "uz" else "шт"
        delivery_label = "Yetkazish" if lang == "uz" else "Доставка"
        total_label = "JAMI" if lang == "uz" else "ИТОГО"
        receipt_label = "Chek" if lang == "uz" else "Чек"
        addr_label = "Manzil" if lang == "uz" else "Адрес"

        lines = []
        lines.append(f"✅ <b>{success_title}</b>")
        lines.append("")
        lines.append(f"📦 <b>{title}</b>")
        lines.append(f"   {qty_label}: {quantity} {unit_label}")
        lines.append(f"   {price_label}: {subtotal:,} {currency}")

        if is_delivery and delivery_price:
            lines.append(f"🚚 {delivery_label}: {delivery_price:,} {currency}")

        lines.append("")
        lines.append("─" * 25)
        lines.append(f"💵 <b>{total_label}: {int(total_amount):,} {currency}</b>")
        lines.append(f"🧾 {receipt_label}: <code>{provider_charge_id[:20]}</code>")
        lines.append("")

        if store_name:
            lines.append(f"🏪 {store_name}")
        if is_delivery and address:
            lines.append(f"📍 {addr_label}: {address}")
        elif store_address:
            lines.append(f"📍 {store_address}")

        lines.append("")
        if is_delivery:
            hint = (
                "Do'kon tasdiqlashini kuting..."
                if lang == "uz"
                else "Ожидаем подтверждения магазина..."
            )
        else:
            hint = (
                "Do'konga boring va buyurtmani oling!"
                if lang == "uz"
                else "Приходите в магазин за заказом!"
            )
        lines.append(f"⏳ {hint}" if is_delivery else f"🏪 {hint}")

        success_text = "\n".join(lines)

        from app.keyboards.user import main_menu_customer

        await message.answer(success_text, parse_mode="HTML", reply_markup=main_menu_customer(lang))

        # NOTIFY STORE OWNER - detailed card like card payment
        if owner_id and bot:
            seller_lang = db.get_user_language(owner_id) or "ru"

            customer = db.get_user_model(user_id)
            customer_name = customer.first_name if customer else message.from_user.first_name
            customer_phone = customer.phone if customer else (phone or "Не указан")

            # Labels for seller
            new_order_title = (
                "Yangi to'langan buyurtma!" if seller_lang == "uz" else "Новый оплаченный заказ!"
            )
            click_paid = (
                "💳 Click orqali to'langan" if seller_lang == "uz" else "💳 Оплачено через Click"
            )
            order_label = "Buyurtma" if seller_lang == "uz" else "Заказ"
            qty_s = "Miqdor" if seller_lang == "uz" else "Количество"
            sum_s = "Summa" if seller_lang == "uz" else "Сумма"
            client_s = "Mijoz" if seller_lang == "uz" else "Клиент"
            phone_s = "Telefon" if seller_lang == "uz" else "Телефон"
            unit_s = "dona" if seller_lang == "uz" else "шт"
            confirm_hint = "Buyurtmani tasdiqlang!" if seller_lang == "uz" else "Подтвердите заказ!"

            order_caption = (
                f"🎉 <b>{new_order_title}</b>\n\n"
                f"{click_paid}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 {order_label} #{order_id}\n"
                f"🍽 <b>{title}</b>\n"
                f"📦 {qty_s}: {quantity} {unit_s}\n"
                f"💵 {sum_s}: <b>{int(total_amount):,} {currency}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 {client_s}: {customer_name}\n"
                f"📱 {phone_s}: <code>{customer_phone}</code>\n"
            )

            if is_delivery and address:
                addr_s = "Manzil" if seller_lang == "uz" else "Адрес доставки"
                order_caption += f"📍 {addr_s}: {address}\n\n"
            else:
                order_caption += "\n"

            order_caption += f"⏳ <b>{confirm_hint}</b>"

            # Partner confirmation keyboard - use unified callback pattern
            from aiogram.utils.keyboard import InlineKeyboardBuilder

            partner_kb = InlineKeyboardBuilder()

            # Use unified order_confirm_ / order_reject_ pattern for all orders
            if is_delivery:
                confirm_text = "✅ Qabul qilish" if seller_lang == "uz" else "✅ Принять"
                reject_text = "❌ Rad etish" if seller_lang == "uz" else "❌ Отклонить"
            else:
                confirm_text = "✅ Tasdiqlash" if seller_lang == "uz" else "✅ Подтвердить"
                reject_text = "❌ Rad etish" if seller_lang == "uz" else "❌ Отклонить"

            partner_kb.button(text=confirm_text, callback_data=f"order_confirm_{order_id}")
            partner_kb.button(text=reject_text, callback_data=f"order_reject_{order_id}")
            partner_kb.adjust(2)

            try:
                # Try to send with photo first for beautiful card
                if offer_photo:
                    try:
                        await bot.send_photo(
                            owner_id,
                            photo=offer_photo,
                            caption=order_caption,
                            parse_mode="HTML",
                            reply_markup=partner_kb.as_markup(),
                        )
                        logger.info(
                            f"✅ Notified store owner {owner_id} with photo about Click payment for order {order_id}"
                        )
                    except Exception as photo_err:
                        logger.warning(f"Failed to send photo to partner: {photo_err}")
                        # Fallback to text only
                        await bot.send_message(
                            owner_id,
                            order_caption,
                            parse_mode="HTML",
                            reply_markup=partner_kb.as_markup(),
                        )
                else:
                    await bot.send_message(
                        owner_id,
                        order_caption,
                        parse_mode="HTML",
                        reply_markup=partner_kb.as_markup(),
                    )
                logger.info(
                    f"✅ Notified store owner {owner_id} about Click payment for order {order_id}"
                )
            except Exception as e:
                logger.error(f"Failed to notify store owner {owner_id}: {e}")

        logger.info(f"✅ Click payment processed successfully for order {order_id}")

    except Exception as e:
        logger.error(f"Click payment processing error: {e}", exc_info=True)
        # Fallback message
        await message.answer(
            "✅ To'lov qabul qilindi!\n\n"
            "Buyurtmangiz qabul qilindi. Tez orada siz bilan bog'lanamiz."
        )


async def send_payment_invoice_for_booking(
    user_id: int,
    booking_id: int,
    offer_title: str,
    quantity: int,
    unit_price: int,
    delivery_cost: int = 0,
    photo_url: str | None = None,
) -> types.Message | None:
    """
    Helper function to send payment invoice for a booking.

    Args:
        user_id: Telegram user ID
        booking_id: Booking ID
        offer_title: Product title
        quantity: Quantity ordered
        unit_price: Price per unit in UZS
        delivery_cost: Delivery cost in UZS
        photo_url: Optional product photo URL

    Returns:
        Sent invoice message or None if failed
    """
    try:
        total = (unit_price * quantity) + delivery_cost

        items = [
            {
                "title": offer_title,
                "quantity": quantity,
                "price": unit_price,
            }
        ]

        return await create_order_invoice(
            chat_id=user_id,
            order_id=booking_id,
            items=items,
            delivery_cost=delivery_cost,
        )

    except Exception as e:
        logger.error(f"Error sending payment invoice: {e}")
        return None
