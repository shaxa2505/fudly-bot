"""
Unified Order Service - single entry point for all order operations.

This service handles:
- Single item orders (from product page)
- Cart orders (multiple items)
- Pickup and delivery orders
- Seller notifications (grouped by store)
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


@dataclass
class OrderItem:
    """Single item in an order."""

    offer_id: int
    store_id: int
    title: str
    price: int  # discount_price
    original_price: int
    quantity: int
    store_name: str
    store_address: str
    delivery_price: int = 0
    photo: str | None = None


@dataclass
class OrderResult:
    """Result of order creation."""

    success: bool
    order_ids: list[int]
    pickup_codes: list[str]  # For pickup orders
    total_items: int
    total_price: int
    delivery_price: int
    grand_total: int
    error_message: str | None = None
    failed_items: list[OrderItem] | None = None


class OrderService:
    """Unified service for creating orders."""

    def __init__(self, db: Any, bot: Bot):
        self.db = db
        self.bot = bot

    def _esc(self, val: Any) -> str:
        """HTML-escape helper."""
        if val is None:
            return ""
        return html.escape(str(val))

    async def create_order(
        self,
        user_id: int,
        items: list[OrderItem],
        order_type: str,  # "pickup" or "delivery"
        delivery_address: str | None = None,
        payment_method: str = "cash",
        notify_sellers: bool = True,
    ) -> OrderResult:
        """
        Create order(s) from items list.

        This is the SINGLE entry point for all order creation:
        - Single item from product page
        - Multiple items from cart

        Args:
            user_id: Customer user ID
            items: List of OrderItem objects
            order_type: "pickup" or "delivery"
            delivery_address: Required for delivery orders
            payment_method: "cash" or "card"
            notify_sellers: Whether to send notifications to sellers

        Returns:
            OrderResult with all order details
        """
        if not items:
            return OrderResult(
                success=False,
                order_ids=[],
                pickup_codes=[],
                total_items=0,
                total_price=0,
                delivery_price=0,
                grand_total=0,
                error_message="No items provided",
            )

        if order_type == "delivery" and not delivery_address:
            return OrderResult(
                success=False,
                order_ids=[],
                pickup_codes=[],
                total_items=0,
                total_price=0,
                delivery_price=0,
                grand_total=0,
                error_message="Delivery address required",
            )

        # Prepare items for database
        db_items = [
            {
                "offer_id": item.offer_id,
                "store_id": item.store_id,
                "quantity": item.quantity,
                "price": item.price,
                "delivery_price": item.delivery_price if order_type == "delivery" else 0,
                "title": item.title,
                "store_name": item.store_name,
                "store_address": item.store_address,
            }
            for item in items
        ]

        # Create orders in database
        result = self.db.create_cart_order(
            user_id=user_id,
            items=db_items,
            order_type=order_type,
            delivery_address=delivery_address,
            payment_method=payment_method,
        )

        created_orders = result.get("created_orders", [])
        stores_orders = result.get("stores_orders", {})
        failed_items_data = result.get("failed_items", [])

        if not created_orders:
            return OrderResult(
                success=False,
                order_ids=[],
                pickup_codes=[],
                total_items=0,
                total_price=0,
                delivery_price=0,
                grand_total=0,
                error_message="Failed to create orders",
            )

        # Calculate totals
        order_ids = [o["order_id"] for o in created_orders]
        pickup_codes = [o["pickup_code"] for o in created_orders if o.get("pickup_code")]
        total_items = sum(o["quantity"] for o in created_orders)
        total_price = sum(o["price"] * o["quantity"] for o in created_orders)
        delivery_price = items[0].delivery_price if order_type == "delivery" and items else 0
        grand_total = total_price + delivery_price

        # Send notifications to sellers (grouped by store)
        if notify_sellers and stores_orders:
            customer = self.db.get_user_model(user_id)
            customer_name = customer.first_name if customer else "—"
            customer_phone = customer.phone if customer else "—"

            await self._notify_sellers(
                stores_orders=stores_orders,
                order_type=order_type,
                delivery_address=delivery_address,
                payment_method=payment_method,
                customer_name=customer_name,
                customer_phone=customer_phone,
            )

        # Convert failed items back to OrderItem
        failed_order_items = None
        if failed_items_data:
            failed_order_items = [
                OrderItem(
                    offer_id=f["offer_id"],
                    store_id=f["store_id"],
                    title=f.get("title", ""),
                    price=f.get("price", 0),
                    original_price=0,
                    quantity=f.get("quantity", 1),
                    store_name=f.get("store_name", ""),
                    store_address=f.get("store_address", ""),
                )
                for f in failed_items_data
            ]

        # Structured logging for OrderService
        logger.info(
            f"ORDER_CREATED: ids={','.join(map(str, order_ids))}, user={user_id}, type={order_type}, "
            f"total={int(grand_total)}, items={total_items}, source=order_service"
        )

        return OrderResult(
            success=True,
            order_ids=order_ids,
            pickup_codes=pickup_codes,
            total_items=total_items,
            total_price=int(total_price),
            delivery_price=int(delivery_price),
            grand_total=int(grand_total),
            failed_items=failed_order_items,
        )

    async def _notify_sellers(
        self,
        stores_orders: dict[int, list[dict]],
        order_type: str,
        delivery_address: str | None,
        payment_method: str,
        customer_name: str,
        customer_phone: str,
    ) -> None:
        """Send order notifications to sellers, grouped by store."""
        for store_id, store_orders in stores_orders.items():
            try:
                store = self.db.get_store(store_id)
                if not store:
                    continue

                owner_id = store.get("owner_id") if isinstance(store, dict) else None
                if not owner_id:
                    continue

                seller_lang = self.db.get_user_language(owner_id)
                currency = "so'm" if seller_lang == "uz" else "сум"

                # Calculate store totals
                store_total = sum(o["price"] * o["quantity"] for o in store_orders)
                store_delivery = (
                    store_orders[0].get("delivery_price", 0) if order_type == "delivery" else 0
                )

                # Build notification text
                order_ids = [str(o["order_id"]) for o in store_orders]
                pickup_codes = [o["pickup_code"] for o in store_orders if o.get("pickup_code")]

                if seller_lang == "uz":
                    seller_text = self._build_seller_notification_uz(
                        order_ids=order_ids,
                        pickup_codes=pickup_codes,
                        store_orders=store_orders,
                        order_type=order_type,
                        delivery_address=delivery_address,
                        payment_method=payment_method,
                        customer_name=customer_name,
                        customer_phone=customer_phone,
                        store_total=store_total,
                        store_delivery=store_delivery,
                        currency=currency,
                    )
                    confirm_text = "✅ Qabul qilish"
                    reject_text = "❌ Rad etish"
                else:
                    seller_text = self._build_seller_notification_ru(
                        order_ids=order_ids,
                        pickup_codes=pickup_codes,
                        store_orders=store_orders,
                        order_type=order_type,
                        delivery_address=delivery_address,
                        payment_method=payment_method,
                        customer_name=customer_name,
                        customer_phone=customer_phone,
                        store_total=store_total,
                        store_delivery=store_delivery,
                        currency=currency,
                    )
                    confirm_text = "✅ Принять"
                    reject_text = "❌ Отклонить"

                # Build keyboard - use unified callback pattern
                first_order_id = store_orders[0]["order_id"]
                partner_kb = InlineKeyboardBuilder()
                partner_kb.button(
                    text=confirm_text, callback_data=f"order_confirm_{first_order_id}"
                )
                partner_kb.button(text=reject_text, callback_data=f"order_reject_{first_order_id}")
                partner_kb.adjust(2)

                sent_msg = await self.bot.send_message(
                    owner_id, seller_text, parse_mode="HTML", reply_markup=partner_kb.as_markup()
                )
                logger.info(f"Sent order notification to seller {owner_id} for orders {order_ids}")

                # Save seller_message_id for live editing
                if sent_msg and hasattr(self.db, "set_order_seller_message_id"):
                    try:
                        self.db.set_order_seller_message_id(first_order_id, sent_msg.message_id)
                        logger.info(
                            f"Saved seller_message_id={sent_msg.message_id} for order#{first_order_id}"
                        )
                    except Exception as save_err:
                        logger.error(f"Failed to save seller_message_id: {save_err}")

            except Exception as e:
                logger.error(f"Failed to notify seller for store {store_id}: {e}")

    def _build_seller_notification_ru(
        self,
        order_ids: list[str],
        pickup_codes: list[str],
        store_orders: list[dict],
        order_type: str,
        delivery_address: str | None,
        payment_method: str,
        customer_name: str,
        customer_phone: str,
        store_total: int,
        store_delivery: int,
        currency: str,
    ) -> str:
        """Build Russian seller notification."""
        order_type_text = "🏪 Самовывоз" if order_type == "pickup" else "🚚 Доставка"

        lines = [
            "🔔 <b>Новый заказ!</b>\n",
            f"📦 #{', #'.join(order_ids)}",
            f"📋 {order_type_text}",
        ]

        if pickup_codes:
            lines.append(f"🎫 Код: <b>{', '.join(pickup_codes)}</b>")

        lines.extend(
            [
                f"👤 {customer_name}",
                f"📱 <code>{customer_phone}</code>",
            ]
        )

        if order_type == "delivery" and delivery_address:
            lines.append(f"📍 {self._esc(delivery_address)}")

        lines.append("\n<b>Товары:</b>")
        for o in store_orders:
            subtotal = o["price"] * o["quantity"]
            lines.append(
                f"• {self._esc(o['title'])} × {o['quantity']} = {int(subtotal):,} {currency}"
            )

        lines.append("")
        lines.append(f"💵 Товары: {int(store_total):,} {currency}")

        if order_type == "delivery":
            lines.append(f"🚚 Доставка: {int(store_delivery):,} {currency}")
            lines.append(f"💰 <b>Итого: {int(store_total + store_delivery):,} {currency}</b>")
        else:
            lines.append(f"💰 <b>Итого: {int(store_total):,} {currency}</b>")

        lines.append("")
        payment_text = "💵 Наличные" if payment_method == "cash" else "💳 Карта"
        lines.append(payment_text)
        lines.append("")
        lines.append("⏳ <b>Подтвердите заказ!</b>")

        return "\n".join(lines)

    def _build_seller_notification_uz(
        self,
        order_ids: list[str],
        pickup_codes: list[str],
        store_orders: list[dict],
        order_type: str,
        delivery_address: str | None,
        payment_method: str,
        customer_name: str,
        customer_phone: str,
        store_total: int,
        store_delivery: int,
        currency: str,
    ) -> str:
        """Build Uzbek seller notification."""
        order_type_text = "🏪 O'zim olib ketaman" if order_type == "pickup" else "🚚 Yetkazish"

        lines = [
            "🔔 <b>Yangi buyurtma!</b>\n",
            f"📦 #{', #'.join(order_ids)}",
            f"📋 {order_type_text}",
        ]

        if pickup_codes:
            lines.append(f"🎫 Kod: <b>{', '.join(pickup_codes)}</b>")

        lines.extend(
            [
                f"👤 {customer_name}",
                f"📱 <code>{customer_phone}</code>",
            ]
        )

        if order_type == "delivery" and delivery_address:
            lines.append(f"📍 {self._esc(delivery_address)}")

        lines.append("\n<b>Mahsulotlar:</b>")
        for o in store_orders:
            subtotal = o["price"] * o["quantity"]
            lines.append(
                f"• {self._esc(o['title'])} × {o['quantity']} = {int(subtotal):,} {currency}"
            )

        lines.append("")
        lines.append(f"💵 Mahsulotlar: {int(store_total):,} {currency}")

        if order_type == "delivery":
            lines.append(f"🚚 Yetkazish: {int(store_delivery):,} {currency}")
            lines.append(f"💰 <b>Jami: {int(store_total + store_delivery):,} {currency}</b>")
        else:
            lines.append(f"💰 <b>Jami: {int(store_total):,} {currency}</b>")

        lines.append("")
        payment_text = "💵 Naqd" if payment_method == "cash" else "💳 Karta"
        lines.append(payment_text)
        lines.append("")
        lines.append("⏳ <b>Buyurtmani tasdiqlang!</b>")

        return "\n".join(lines)

    def build_customer_confirmation_ru(
        self,
        result: OrderResult,
        order_type: str,
        delivery_address: str | None,
        payment_method: str,
        items: list[OrderItem],
    ) -> str:
        """Build Russian confirmation message for customer."""
        currency = "сум"

        lines = ["✅ <b>Заказ оформлен!</b>\n"]

        if order_type == "pickup":
            lines.append("🏪 <b>Самовывоз</b>")
            if result.pickup_codes:
                for i, (code, item) in enumerate(zip(result.pickup_codes, items)):
                    lines.append(f"🎫 Код: <b>{code}</b> — {self._esc(item.store_name)}")
                    if item.store_address:
                        lines.append(f"   📍 {self._esc(item.store_address)}")
        else:
            lines.append("🚚 <b>Доставка</b>")
            if delivery_address:
                lines.append(f"📍 {self._esc(delivery_address)}")

        lines.append("\n<b>Товары:</b>")
        for item in items:
            subtotal = item.price * item.quantity
            lines.append(
                f"• {self._esc(item.title)} × {item.quantity} = {int(subtotal):,} {currency}"
            )

        lines.append("")
        lines.append("─" * 25)
        lines.append(f"💵 Товары: {result.total_price:,} {currency}")

        if order_type == "delivery":
            lines.append(f"🚚 Доставка: {result.delivery_price:,} {currency}")

        lines.append(f"💰 <b>Итого: {result.grand_total:,} {currency}</b>")
        lines.append("")

        payment_text = "💵 Наличные" if payment_method == "cash" else "💳 Карта"
        lines.append(payment_text)
        lines.append("")

        if order_type == "pickup":
            lines.append("👆 Покажите код продавцу при получении")
        else:
            lines.append("🚚 Заказ будет доставлен в течение часа")

        return "\n".join(lines)

    def build_customer_confirmation_uz(
        self,
        result: OrderResult,
        order_type: str,
        delivery_address: str | None,
        payment_method: str,
        items: list[OrderItem],
    ) -> str:
        """Build Uzbek confirmation message for customer."""
        currency = "so'm"

        lines = ["✅ <b>Buyurtma qabul qilindi!</b>\n"]

        if order_type == "pickup":
            lines.append("🏪 <b>O'zim olib ketaman</b>")
            if result.pickup_codes:
                for i, (code, item) in enumerate(zip(result.pickup_codes, items)):
                    lines.append(f"🎫 Kod: <b>{code}</b> — {self._esc(item.store_name)}")
                    if item.store_address:
                        lines.append(f"   📍 {self._esc(item.store_address)}")
        else:
            lines.append("🚚 <b>Yetkazish</b>")
            if delivery_address:
                lines.append(f"📍 {self._esc(delivery_address)}")

        lines.append("\n<b>Mahsulotlar:</b>")
        for item in items:
            subtotal = item.price * item.quantity
            lines.append(
                f"• {self._esc(item.title)} × {item.quantity} = {int(subtotal):,} {currency}"
            )

        lines.append("")
        lines.append("─" * 25)
        lines.append(f"💵 Mahsulotlar: {result.total_price:,} {currency}")

        if order_type == "delivery":
            lines.append(f"🚚 Yetkazish: {result.delivery_price:,} {currency}")

        lines.append(f"💰 <b>Jami: {result.grand_total:,} {currency}</b>")
        lines.append("")

        payment_text = "💵 Naqd" if payment_method == "cash" else "💳 Karta"
        lines.append(payment_text)
        lines.append("")

        if order_type == "pickup":
            lines.append("👆 Olishda sotuvchiga kodni ko'rsating")
        else:
            lines.append("🚚 Buyurtma 1 soat ichida yetkaziladi")

        return "\n".join(lines)


# Singleton instance
_order_service: OrderService | None = None


def get_order_service() -> OrderService | None:
    """Get the order service singleton."""
    return _order_service


def init_order_service(db: Any, bot: Bot) -> OrderService:
    """Initialize the order service singleton."""
    global _order_service
    _order_service = OrderService(db, bot)
    return _order_service
