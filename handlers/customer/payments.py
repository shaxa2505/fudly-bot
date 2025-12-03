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

# Telegram Payments provider token (Click test token)
PROVIDER_TOKEN = os.getenv(
    "TELEGRAM_PAYMENT_PROVIDER_TOKEN",
    "398062629:TEST:999999999_F91D8F69C042267444B74CC0B3C747757EB0E065",
)


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

    This is called after payment is completed successfully.
    """
    import json

    payment = message.successful_payment

    try:
        # Parse payload
        payload = json.loads(payment.invoice_payload)
        order_id = payload.get("order_id")

        # Get payment details
        total_amount = payment.total_amount / 100  # Convert from tiyin to UZS
        currency = payment.currency
        provider_payment_charge_id = payment.provider_payment_charge_id
        telegram_payment_charge_id = payment.telegram_payment_charge_id

        logger.info(
            f"💰 Payment successful! Order: {order_id}, "
            f"Amount: {total_amount} {currency}, "
            f"Charge ID: {provider_payment_charge_id}"
        )

        # Update order status in database
        if db and order_id:
            try:
                # Update booking/order status to paid
                if hasattr(db, "update_booking_status"):
                    db.update_booking_status(order_id, "confirmed")

                # Save payment record
                if hasattr(db, "save_payment_record"):
                    db.save_payment_record(
                        order_id=order_id,
                        amount=total_amount,
                        currency=currency,
                        provider="click_telegram",
                        provider_charge_id=provider_payment_charge_id,
                        telegram_charge_id=telegram_payment_charge_id,
                        status="completed",
                        phone=payment.order_info.phone_number if payment.order_info else None,
                    )

                logger.info(f"✅ Order {order_id} marked as paid")

            except Exception as e:
                logger.error(f"Error updating order status: {e}")

        # Get user language
        lang = "uz"
        if db and hasattr(db, "get_user_language"):
            lang = db.get_user_language(message.from_user.id) or "uz"

        # Send success message
        success_text = (
            (
                f"✅ To'lov muvaffaqiyatli amalga oshirildi!\n\n"
                f"📋 Buyurtma: #{order_id}\n"
                f"💰 Summa: {total_amount:,.0f} {currency}\n"
                f"🧾 Chek: {provider_payment_charge_id}\n\n"
                f"Buyurtmangiz tayyorlanmoqda. Tayyor bo'lganda xabar beramiz! 🎉"
            )
            if lang == "uz"
            else (
                f"✅ Оплата успешно проведена!\n\n"
                f"📋 Заказ: #{order_id}\n"
                f"💰 Сумма: {total_amount:,.0f} {currency}\n"
                f"🧾 Чек: {provider_payment_charge_id}\n\n"
                f"Ваш заказ готовится. Уведомим когда будет готов! 🎉"
            )
        )

        await message.answer(success_text)

        # Notify store owner
        if db and order_id:
            try:
                # Get booking to find store
                if hasattr(db, "get_booking"):
                    booking = db.get_booking(order_id)
                    if booking:
                        offer_id = (
                            booking.get("offer_id")
                            if isinstance(booking, dict)
                            else (booking[1] if len(booking) > 1 else None)
                        )
                        if offer_id and hasattr(db, "get_offer"):
                            offer = db.get_offer(offer_id)
                            if offer:
                                store_id = (
                                    offer.get("store_id")
                                    if isinstance(offer, dict)
                                    else (offer[1] if len(offer) > 1 else None)
                                )
                                if store_id and hasattr(db, "get_store_owner"):
                                    owner_id = db.get_store_owner(store_id)
                                    if owner_id:
                                        # Get offer title
                                        title = (
                                            offer.get("title")
                                            if isinstance(offer, dict)
                                            else (offer[2] if len(offer) > 2 else "Товар")
                                        )

                                        await bot.send_message(
                                            owner_id,
                                            f"🎉 <b>Новый оплаченный заказ!</b>\n\n"
                                            f"📦 {title}\n"
                                            f"💰 {total_amount:,.0f} UZS\n"
                                            f"👤 Покупатель: {message.from_user.full_name}\n"
                                            f"📱 Телефон: {payment.order_info.phone_number if payment.order_info else 'Не указан'}\n\n"
                                            f"Заказ #{order_id} - подтвердите готовность!",
                                            parse_mode="HTML",
                                        )
            except Exception as e:
                logger.error(f"Error notifying store owner: {e}")

    except Exception as e:
        logger.error(f"Successful payment processing error: {e}")
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
