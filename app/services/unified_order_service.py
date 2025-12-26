"""
Unified Order Service - Single entry point for ALL order operations.

This service handles:
- Both bookings (pickup) and orders (delivery)
- Unified status management
- Consistent notifications for customers and sellers
- Automatic status updates with customer notifications
- Visual progress bar for order tracking

Status Flow:
    PENDING     → Waiting for seller confirmation
    PREPARING   → Seller accepted, preparing order
    READY       → Ready for pickup/delivery (internal state, no customer notification)
    DELIVERING  → In transit (delivery only)
    COMPLETED   → Order completed
    REJECTED    → Rejected by seller
    CANCELLED   → Cancelled by customer

NOTIFICATION STRATEGY (Optimized v2):
    - Minimize spam by skipping READY notifications
    - Use visual progress bars for better UX
    - Pickup: PREPARING → COMPLETED (2 notifications)
    - Delivery: PREPARING → DELIVERING → COMPLETED (3 notifications)
"""
from __future__ import annotations

import html
import os
from datetime import datetime
import re
from dataclasses import dataclass
from typing import Any, Literal

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.notifications import Notification, NotificationType, get_notification_service
from app.services.notification_builder import NotificationBuilder

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


# =============================================================================
# ORDER STATUSES
# =============================================================================


class OrderStatus:
    """Unified order statuses for both bookings and orders."""

    PENDING = "pending"  # Waiting for seller confirmation
    PREPARING = "preparing"  # Seller accepted, preparing
    READY = "ready"  # Ready for pickup/delivery
    DELIVERING = "delivering"  # In transit (delivery only)
    COMPLETED = "completed"  # Order completed
    REJECTED = "rejected"  # Rejected by seller
    CANCELLED = "cancelled"  # Cancelled by customer

    # Mapping from old statuses
    @classmethod
    def normalize(cls, status: str) -> str:
        """Normalize status from old system."""
        mapping = {
            "confirmed": cls.PREPARING,  # Old booking "confirmed" = now "preparing"
            "new": cls.PENDING,
            # Legacy/temporary order_status values used during payment flows.
            "awaiting_payment": cls.PENDING,
            "awaiting_admin_confirmation": cls.PENDING,
            "paid": cls.PENDING,
        }
        return mapping.get(status, status)


# =============================================================================
# PAYMENT STATUSES
# =============================================================================


class PaymentStatus:
    """Payment lifecycle status stored in orders.payment_status."""

    NOT_REQUIRED = "not_required"  # cash payments
    AWAITING_PAYMENT = "awaiting_payment"  # online providers (click/payme)
    AWAITING_PROOF = "awaiting_proof"  # manual card transfer (screenshot)
    PROOF_SUBMITTED = "proof_submitted"  # proof uploaded, waiting for admin review
    CONFIRMED = "confirmed"  # payment confirmed (admin or provider)
    REJECTED = "rejected"  # payment rejected by admin

    @classmethod
    def normalize_method(cls, payment_method: str | None) -> str:
        if not payment_method:
            return "cash"
        method = str(payment_method).strip().lower()
        return "card" if method == "pending" else method

    @classmethod
    def initial_for_method(cls, payment_method: str | None) -> str:
        method = cls.normalize_method(payment_method)
        if method == "cash":
            return cls.NOT_REQUIRED
        if method in ("click", "payme"):
            return cls.AWAITING_PAYMENT
        return cls.AWAITING_PROOF

    @classmethod
    def normalize(
        cls,
        payment_status: str | None,
        *,
        payment_method: str | None = None,
        payment_proof_photo_id: str | None = None,
    ) -> str | None:
        """Normalize legacy payment_status values to the target model."""
        if payment_status is None:
            return None

        status = str(payment_status).strip().lower()
        method = cls.normalize_method(payment_method)

        # Legacy "pending" was overloaded; infer from method and proof presence.
        if status in ("pending", ""):
            if method == "cash":
                return cls.NOT_REQUIRED
            if payment_proof_photo_id:
                return cls.PROOF_SUBMITTED
            if method in ("click", "payme"):
                return cls.AWAITING_PAYMENT
            return cls.AWAITING_PROOF

        if status == "paid":
            return cls.CONFIRMED

        return status

    @classmethod
    def is_cleared(
        cls,
        payment_status: str | None,
        *,
        payment_method: str | None = None,
        payment_proof_photo_id: str | None = None,
    ) -> bool:
        normalized = cls.normalize(
            payment_status,
            payment_method=payment_method,
            payment_proof_photo_id=payment_proof_photo_id,
        )
        return normalized in (cls.NOT_REQUIRED, cls.CONFIRMED)


# =============================================================================
# DATA CLASSES
# =============================================================================


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
    booking_ids: list[int]  # For pickup orders
    pickup_codes: list[str]
    total_items: int
    total_price: int
    delivery_price: int
    grand_total: int
    error_message: str | None = None
    failed_items: list[OrderItem] | None = None


# =============================================================================
# NOTIFICATION TEMPLATES
# =============================================================================


class NotificationTemplates:
    """Unified notification templates for RU and UZ languages."""

    @staticmethod
    def _is_delivery(order_type: str) -> bool:
        return order_type in ("delivery", "taxi")

    @staticmethod
    def _order_type_label(lang: str, order_type: str) -> str:
        if lang == "uz":
            if order_type == "pickup":
                return "🏪 O'zi olib ketadi"
            if order_type == "taxi":
                return "🚕 Taksi"
            return "🚚 Yetkazish"
        if order_type == "pickup":
            return "🏪 Самовывоз"
        if order_type == "taxi":
            return "🚕 Такси"
        return "🚚 Доставка"

    @staticmethod
    def _payment_label(lang: str, payment_method: str) -> str:
        if lang == "uz":
            if payment_method == "cash":
                return "💵 Naqd"
            if payment_method == "card":
                return "🏦 Kartaga o'tkazma"
            if payment_method == "click":
                return "💳 Click"
            if payment_method == "payme":
                return "💳 Payme"
            return "💳 Onlayn to'lov"
        if payment_method == "cash":
            return "💵 Наличные"
        if payment_method == "card":
            return "🏦 Перевод на карту"
        if payment_method == "click":
            return "💳 Click"
        if payment_method == "payme":
            return "💳 Payme"
        return "💳 Онлайн оплата"

    @staticmethod
    def seller_new_order(
        lang: str,
        order_ids: list[str],
        pickup_codes: list[str],
        items: list[dict],
        order_type: str,
        delivery_address: str | None,
        payment_method: str,
        customer_name: str,
        customer_phone: str,
        total: int,
        delivery_price: int,
        currency: str,
    ) -> str:
        """Build seller notification for new order."""

        def _esc(val: Any) -> str:
            return html.escape(str(val)) if val else ""

        # Ensure customer name is not empty
        display_name = _esc(customer_name) if customer_name and customer_name.strip() else "Клиент"

        is_delivery = NotificationTemplates._is_delivery(order_type)
        if lang == "uz":
            display_name = (
                _esc(customer_name) if customer_name and customer_name.strip() else "Mijoz"
            )
            order_type_text = NotificationTemplates._order_type_label(lang, order_type)
            lines = [
                "🔔 <b>YANGI BUYURTMA!</b>",
                "━━━━━━━━━━━━━━━━━━",
                "",
                f"📦 #{', #'.join(order_ids)} | {order_type_text}",
            ]

            if pickup_codes:
                lines.append(f"🎫 Kod: <b>{', '.join(pickup_codes)}</b>")

            lines.extend(
                [
                    "",
                    f"👤 {display_name}",
                    f"📱 <code>{_esc(customer_phone) if customer_phone else 'Не указан'}</code>",
                ]
            )

            if is_delivery and delivery_address:
                lines.append(f"📍 {_esc(delivery_address)}")

            lines.append("")
            lines.append("<b>📦 Mahsulotlar:</b>")
            for item in items:
                item_title = item.get("title") or "Товар"
                item_price = item.get("price") or 0
                item_qty = item.get("quantity") or 1
                subtotal = item_price * item_qty
                lines.append(f"  • {_esc(item_title)} × {item_qty} = {int(subtotal):,} {currency}")

            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━")

            if is_delivery:
                lines.append(f"🚚 Yetkazish: {int(delivery_price):,} {currency}")
                grand_total = int(total + delivery_price)
            else:
                grand_total = int(total)

            lines.append(f"💰 <b>JAMI: {grand_total:,} {currency}</b>")

            payment_text = NotificationTemplates._payment_label(lang, payment_method)
            lines.extend(["", payment_text, ""])
            lines.append("⏳ <b>Buyurtmani tasdiqlang!</b>")

        else:  # Russian
            display_name = (
                _esc(customer_name) if customer_name and customer_name.strip() else "Клиент"
            )
            order_type_text = NotificationTemplates._order_type_label(lang, order_type)
            lines = [
                "🔔 <b>НОВЫЙ ЗАКАЗ!</b>",
                "━━━━━━━━━━━━━━━━━━",
                "",
                f"📦 #{', #'.join(order_ids)} | {order_type_text}",
            ]

            if pickup_codes:
                lines.append(f"🎫 Код: <b>{', '.join(pickup_codes)}</b>")

            lines.extend(
                [
                    "",
                    f"👤 {display_name}",
                    f"📱 <code>{_esc(customer_phone) if customer_phone else 'Не указан'}</code>",
                ]
            )

            if is_delivery and delivery_address:
                lines.append(f"📍 {_esc(delivery_address)}")

            lines.append("")
            lines.append("<b>📦 Товары:</b>")
            for item in items:
                item_title = item.get("title") or "Товар"
                item_price = item.get("price") or 0
                item_qty = item.get("quantity") or 1
                subtotal = item_price * item_qty
                lines.append(f"  • {_esc(item_title)} × {item_qty} = {int(subtotal):,} {currency}")

            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━")

            if is_delivery:
                lines.append(f"🚚 Доставка: {int(delivery_price):,} {currency}")
                grand_total = int(total + delivery_price)
            else:
                grand_total = int(total)

            lines.append(f"💰 <b>ИТОГО: {grand_total:,} {currency}</b>")

            payment_text = NotificationTemplates._payment_label(lang, payment_method)
            lines.extend(["", payment_text, ""])
            lines.append("⏳ <b>Подтвердите заказ!</b>")

        return "\n".join(lines)

    @staticmethod
    def customer_order_created(
        lang: str,
        order_ids: list[str],
        pickup_codes: list[str],
        items: list[dict],
        order_type: str,
        delivery_address: str | None,
        payment_method: str,
        store_name: str,
        store_address: str,
        total: int,
        delivery_price: int,
        currency: str,
        awaiting_payment: bool = False,
    ) -> str:
        """Build customer notification for order creation.

        When awaiting_payment is True (typically for card payments with manual
        receipt review), the header makes it clear that the order is sent for
        verification, not fully confirmed yet.
        """

        def _esc(val: Any) -> str:
            return html.escape(str(val)) if val else ""

        is_delivery = NotificationTemplates._is_delivery(order_type)
        order_type_text = NotificationTemplates._order_type_label(lang, order_type)
        if lang == "uz":
            header = (
                "⏳ <b>BUYURTMA TEKSHIRILMOQDA</b>"
                if awaiting_payment and payment_method == "card"
                else "✅ <b>BUYURTMA YUBORILDI</b>"
            )

            lines = [
                header,
                "",
                f"📦 #{', #'.join(order_ids)}",
                f"🏪 {_esc(store_name)}",
            ]

            if order_type == "pickup":
                lines.append(order_type_text)
                lines.append(f"📍 {_esc(store_address)}")
                if pickup_codes:
                    lines.append(f"🎫 Kod: <b>{', '.join(pickup_codes)}</b>")
            else:
                lines.append(order_type_text)
                if delivery_address:
                    lines.append(f"📍 {_esc(delivery_address)}")

            lines.append("")
            for item in items:
                subtotal = item["price"] * item["quantity"]
                lines.append(
                    f"• {_esc(item['title'])} × {item['quantity']} — {int(subtotal):,} {currency}"
                )

            lines.append("")

            if is_delivery:
                lines.append(f"🚚 Yetkazish: {int(delivery_price):,} {currency}")

            lines.append(f"💰 <b>Jami: {int(total + delivery_price):,} {currency}</b>")

            payment_text = NotificationTemplates._payment_label(lang, payment_method)
            lines.append(payment_text)

            lines.append("")
            lines.append("⏳ Do'kon tasdiqlashini kuting (5-10 min)")

            if order_type == "pickup" and pickup_codes:
                lines.append("")
                lines.append("💡 Kodni sotuvchiga ko'rsating")

        else:  # Russian
            header = (
                "⏳ <b>ЗАКАЗ ОТПРАВЛЕН НА ПРОВЕРКУ</b>"
                if awaiting_payment and payment_method == "card"
                else "✅ <b>ЗАКАЗ ОТПРАВЛЕН</b>"
            )

            lines = [
                header,
                "",
                f"📦 #{', #'.join(order_ids)}",
                f"🏪 {_esc(store_name)}",
            ]

            if order_type == "pickup":
                lines.append(order_type_text)
                lines.append(f"📍 {_esc(store_address)}")
                if pickup_codes:
                    lines.append(f"🎫 Код: <b>{', '.join(pickup_codes)}</b>")
            else:
                lines.append("🚚 Доставка")
                if delivery_address:
                    lines.append(f"📍 {_esc(delivery_address)}")

            lines.append("")
            for item in items:
                subtotal = item["price"] * item["quantity"]
                lines.append(
                    f"• {_esc(item['title'])} × {item['quantity']} — {int(subtotal):,} {currency}"
                )

            lines.append("")

            if is_delivery:
                lines.append(f"🚚 Доставка: {int(delivery_price):,} {currency}")

            lines.append(f"💰 <b>Итого: {int(total + delivery_price):,} {currency}</b>")

            payment_text = NotificationTemplates._payment_label(lang, payment_method)
            lines.append(payment_text)

            lines.append("")
            lines.append("⏳ Ожидайте подтверждения (5-10 мин)")

            if order_type == "pickup" and pickup_codes:
                lines.append("")
                lines.append("💡 Покажите код продавцу при получении")

        return "\n".join(lines)

    @staticmethod
    def customer_status_update(
        lang: str,
        order_id: int | str,
        status: str,
        order_type: str,
        store_name: str | None = None,
        store_address: str | None = None,
        pickup_code: str | None = None,
        reject_reason: str | None = None,
        courier_phone: str | None = None,
    ) -> str:
        """
        Build customer notification for status update with visual progress.
        
        Uses NotificationBuilder to eliminate code duplication.
        """
        normalized_type = "delivery" if order_type == "taxi" else order_type
        builder = NotificationBuilder(normalized_type)  # type: ignore
        return builder.build(
            status=status,
            lang=lang,
            order_id=int(order_id) if isinstance(order_id, str) else order_id,
            store_name=store_name or "",
            store_address=store_address,
            pickup_code=pickup_code,
            reject_reason=reject_reason,
            courier_phone=courier_phone,
        )

    @staticmethod
    def seller_status_update(
        lang: str,
        order_id: int | str,
        status: str,
        order_type: str,
        items: list[dict] | None = None,
        customer_name: str | None = None,
        customer_phone: str | None = None,
        delivery_address: str | None = None,
        total: int = 0,
        delivery_price: int = 0,
        currency: str = "сум",
    ) -> str:
        """Build seller notification with dynamic status indicator.

        This creates ONE message that gets edited as status changes.
        Status indicator at top shows current state.
        """

        def _esc(val: Any) -> str:
            return html.escape(str(val)) if val else ""

        # Status indicators - different for pickup vs delivery
        if order_type in ("delivery", "taxi"):
            status_indicators = {
                "uz": {
                    OrderStatus.PENDING: "⏳ KUTILMOQDA",
                    OrderStatus.PREPARING: "👨‍🍳 TAYYORLANMOQDA",
                    OrderStatus.READY: "📦 KURYERGA TAYYOR",
                    OrderStatus.DELIVERING: "🚚 KURYERDA",
                    OrderStatus.COMPLETED: "✅ YETKAZILDI",
                    OrderStatus.REJECTED: "❌ RAD ETILDI",
                    OrderStatus.CANCELLED: "❌ BEKOR QILINDI",
                },
                "ru": {
                    OrderStatus.PENDING: "⏳ ОЖИДАЕТ",
                    OrderStatus.PREPARING: "👨‍🍳 ГОТОВИТСЯ",
                    OrderStatus.READY: "📦 ГОТОВ К ПЕРЕДАЧЕ",
                    OrderStatus.DELIVERING: "🚚 У КУРЬЕРА",
                    OrderStatus.COMPLETED: "✅ ДОСТАВЛЕНО",
                    OrderStatus.REJECTED: "❌ ОТКЛОНЁН",
                    OrderStatus.CANCELLED: "❌ ОТМЕНЁН",
                },
            }
        else:
            # Pickup status indicators
            status_indicators = {
                "uz": {
                    OrderStatus.PENDING: "⏳ KUTILMOQDA",
                    OrderStatus.PREPARING: "👨‍🍳 TAYYORLANMOQDA",
                    OrderStatus.READY: "✅ TAYYOR",
                    OrderStatus.DELIVERING: "🚚 YETKAZILMOQDA",
                    OrderStatus.COMPLETED: "✅ TOPSHIRILDI",
                    OrderStatus.REJECTED: "❌ RAD ETILDI",
                    OrderStatus.CANCELLED: "❌ BEKOR QILINDI",
                },
                "ru": {
                    OrderStatus.PENDING: "⏳ ОЖИДАЕТ",
                    OrderStatus.PREPARING: "👨‍🍳 ГОТОВИТСЯ",
                    OrderStatus.READY: "✅ ГОТОВО",
                    OrderStatus.DELIVERING: "🚚 В ДОСТАВКЕ",
                    OrderStatus.COMPLETED: "✅ ВЫДАНО",
                    OrderStatus.REJECTED: "❌ ОТКЛОНЁН",
                    OrderStatus.CANCELLED: "❌ ОТМЕНЁН",
                },
            }

        indicators = status_indicators.get(lang, status_indicators["ru"])
        status_text = indicators.get(status, status)

        # Order type text
        is_delivery = NotificationTemplates._is_delivery(order_type)
        order_type_text = NotificationTemplates._order_type_label(lang, order_type)

        # Build message
        if lang == "uz":
            header_line = f"📦 Buyurtma #{order_id} │ {order_type_text}"
        else:
            header_line = f"📦 Заказ #{order_id} │ {order_type_text}"

        lines = [
            f"<b>{status_text}</b>",
            "━━━━━━━━━━━━━━━━━━",
            "",
            header_line,
            "",
        ]

        # Customer info
        if customer_name or customer_phone:
            lines.append(f"👤 {_esc(customer_name or '-')}")
            if customer_phone:
                lines.append(f"📱 <code>{_esc(customer_phone)}</code>")

        # Delivery address (only for delivery)
        if is_delivery and delivery_address:
            lines.append(f"📍 {_esc(delivery_address)}")

        # Items
        if items:
            lines.append("")
            if lang == "uz":
                lines.append("<b>Mahsulotlar:</b>")
            else:
                lines.append("<b>Товары:</b>")
            for item in items:
                qty = item.get("quantity", 1)
                title = item.get("title", "?")
                lines.append(f"• {_esc(title)} × {qty}")

        # Total
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━")
        grand_total = int(total + delivery_price)
        if lang == "uz":
            lines.append(f"💰 <b>JAMI: {grand_total:,} {currency}</b>")
        else:
            lines.append(f"💰 <b>ИТОГО: {grand_total:,} {currency}</b>")

        return "\n".join(lines)


# =============================================================================
# UNIFIED ORDER SERVICE
# =============================================================================


class UnifiedOrderService:
    """
    Unified service for all order operations.

    Handles both bookings (pickup) and orders (delivery) with:
    - Consistent status management
    - Automatic customer notifications on status changes
    - Unified seller notifications
    """

    def __init__(self, db: Any, bot: Bot):
        self.db = db
        self.bot = bot
        self.telegram_order_notifications = (
            os.getenv("ORDER_TELEGRAM_NOTIFICATIONS", "false").strip().lower()
            in {"1", "true", "yes", "y"}
        )

    def _esc(self, val: Any) -> str:
        """HTML-escape helper."""
        return html.escape(str(val)) if val else ""

    # =========================================================================
    # ORDER CREATION
    # =========================================================================

    async def create_order(
        self,
        user_id: int,
        items: list[OrderItem],
        order_type: str,
        delivery_address: str | None = None,
        payment_method: str = "cash",
        notify_customer: bool = True,
        notify_sellers: bool = True,
        telegram_notify: bool | None = None,
    ) -> OrderResult:
        """
        Create order(s) from items list.

        Unified entry point for:
        - Single item from product page (pickup or delivery)
        - Multiple items from cart (pickup or delivery)
        - WebApp orders

        Args:
            user_id: Customer user ID
            items: List of OrderItem objects
            order_type: "pickup" or "delivery"
            delivery_address: Required for delivery orders
            payment_method: "cash" or "card"
            notify_customer: Send confirmation to customer
            notify_sellers: Send notifications to sellers

        Returns:
            OrderResult with all order details
        """
        if not items:
            return OrderResult(
                success=False,
                order_ids=[],
                booking_ids=[],
                pickup_codes=[],
                total_items=0,
                total_price=0,
                delivery_price=0,
                grand_total=0,
                error_message="No items provided",
            )

        is_delivery = order_type in ("delivery", "taxi")
        if is_delivery and not delivery_address:
            return OrderResult(
                success=False,
                order_ids=[],
                booking_ids=[],
                pickup_codes=[],
                total_items=0,
                total_price=0,
                delivery_price=0,
                grand_total=0,
                error_message="Delivery address required",
            )

        payment_method = PaymentStatus.normalize_method(payment_method)
        # Enforce business invariant: one order must belong to ONE store
        # This protects from mixed-store carts and keeps pricing logic correct.
        store_ids = {item.store_id for item in items}
        if len(store_ids) > 1:
            total_items = sum(item.quantity for item in items)
            total_price = sum(item.price * item.quantity for item in items)
            return OrderResult(
                success=False,
                order_ids=[],
                booking_ids=[],
                pickup_codes=[],
                total_items=total_items,
                total_price=int(total_price),
                delivery_price=0,
                grand_total=0,
                error_message=(
                    "Orders from multiple stores are not supported. "
                    "Please place separate orders for each store."
                ),
            )

        # Normalize and enforce: sellers should only see paid/cash orders
        if not PaymentStatus.is_cleared(
            PaymentStatus.initial_for_method(payment_method),
            payment_method=payment_method,
        ):
            notify_sellers = False

        # Prepare items for database
        db_items = [
            {
                "offer_id": item.offer_id,
                "store_id": item.store_id,
                "quantity": item.quantity,
                "price": item.price,
                "delivery_price": item.delivery_price if is_delivery else 0,
                "title": item.title,
                "store_name": item.store_name,
                "store_address": item.store_address,
            }
            for item in items
        ]

        # Create orders using appropriate method based on type
        if order_type == "pickup":
            # Use booking system for pickup
            result = await self._create_pickup_orders(user_id, db_items, payment_method)
        else:
            # Use order system for delivery
            result = await self._create_delivery_orders(
                user_id, db_items, delivery_address, payment_method, order_type
            )

        if not result.get("success"):
            return OrderResult(
                success=False,
                order_ids=[],
                booking_ids=[],
                pickup_codes=[],
                total_items=0,
                total_price=0,
                delivery_price=0,
                grand_total=0,
                error_message=result.get("error", "Failed to create orders"),
            )

        # Calculate totals
        order_ids = result.get("order_ids", [])
        booking_ids = result.get("booking_ids", [])
        pickup_codes = result.get("pickup_codes", [])
        stores_orders = result.get("stores_orders", {})
        total_items = sum(item.quantity for item in items)
        total_price = sum(item.price * item.quantity for item in items)
        delivery_price = items[0].delivery_price if is_delivery and items else 0
        grand_total = total_price + delivery_price

        # Get customer info
        customer = (
            self.db.get_user_model(user_id)
            if hasattr(self.db, "get_user_model")
            else self.db.get_user(user_id)
        )
        if isinstance(customer, dict):
            customer_name = customer.get("first_name", "Клиент")
            customer_phone = customer.get("phone", "—")
        else:
            customer_name = getattr(customer, "first_name", "Клиент") if customer else "Клиент"
            customer_phone = getattr(customer, "phone", "—") if customer else "—"

        customer_lang = self.db.get_user_language(user_id)
        currency = "so'm" if customer_lang == "uz" else "сум"

        telegram_enabled = (
            self.telegram_order_notifications
            if telegram_notify is None
            else telegram_notify
        )

        # Send notifications to sellers
        if notify_sellers and stores_orders:
            await self._notify_sellers_new_order(
                stores_orders=stores_orders,
                order_type=order_type,
                delivery_address=delivery_address,
                payment_method=payment_method,
                customer_name=customer_name,
                customer_phone=customer_phone,
                send_telegram=telegram_enabled,
            )

        # Send notification/event to customer (WebApp sync always; Telegram optional)
        publish_customer_event = bool(user_id)
        if notify_customer or publish_customer_event:
            all_ids = [str(x) for x in (order_ids + booking_ids)]
            items_for_template = [
                {"title": item.title, "price": item.price, "quantity": item.quantity}
                for item in items
            ]

            customer_msg = NotificationTemplates.customer_order_created(
                lang=customer_lang,
                order_ids=all_ids,
                pickup_codes=pickup_codes,
                items=items_for_template,
                order_type=order_type,
                delivery_address=delivery_address,
                payment_method=payment_method,
                store_name=items[0].store_name if items else "",
                store_address=items[0].store_address if items else "",
                total=total_price,
                delivery_price=delivery_price,
                currency=currency,
            )

            if notify_customer and telegram_enabled:
                try:
                    await self.bot.send_message(user_id, customer_msg, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to notify customer {user_id}: {e}")

            if publish_customer_event:
                try:
                    notification_service = get_notification_service()
                    title = (
                        "Buyurtma qabul qilindi" if customer_lang == "uz" else "Заказ принят"
                    )
                    plain_msg = re.sub(r"<[^>]+>", "", customer_msg)
                    await notification_service.notify_user(
                        Notification(
                            type=NotificationType.NEW_BOOKING,
                            recipient_id=int(user_id),
                            title=title,
                            message=plain_msg,
                            data={
                                "order_ids": order_ids,
                                "booking_ids": booking_ids,
                                "status": OrderStatus.PENDING,
                                "order_type": order_type,
                            },
                            priority=0,
                        )
                    )
                except Exception as notify_error:
                    logger.warning(
                        f"Notification service failed for order create: {notify_error}"
                    )

                try:
                    from app.core.websocket import get_websocket_manager

                    ws_manager = get_websocket_manager()
                    await ws_manager.send_to_user(
                        int(user_id),
                        {
                            "type": "order_created",
                            "data": {
                                "order_ids": order_ids,
                                "booking_ids": booking_ids,
                                "status": OrderStatus.PENDING,
                                "order_type": order_type,
                            },
                        },
                    )
                except Exception as ws_error:
                    logger.warning(f"WebSocket notify failed for order create: {ws_error}")

        # Log order creation
        logger.info(
            f"ORDER_CREATED: ids={','.join(map(str, order_ids + booking_ids))}, "
            f"user={user_id}, type={order_type}, total={int(grand_total)}, "
            f"items={total_items}, source=unified_order_service"
        )

        return OrderResult(
            success=True,
            order_ids=order_ids,
            booking_ids=booking_ids,
            pickup_codes=pickup_codes,
            total_items=total_items,
            total_price=int(total_price),
            delivery_price=int(delivery_price),
            grand_total=int(grand_total),
        )

    async def _create_pickup_orders(
        self, user_id: int, items: list[dict], payment_method: str
    ) -> dict:
        """Create pickup orders.

        Target model (v24+): pickup orders live in the unified `orders` table.
        """
        try:
            # Cart pickup must be a SINGLE order row (per store) to keep status/payment/proof consistent.
            if (
                len(items) > 1
                and hasattr(self.db, "create_cart_order_atomic")
                and items
                and items[0].get("store_id")
            ):
                store_id = int(items[0]["store_id"])

                cart_items = [
                    {
                        "offer_id": int(item["offer_id"]),
                        "quantity": int(item.get("quantity", 1)),
                        "price": int(item.get("price", 0)),
                        "title": item.get("title", ""),
                    }
                    for item in items
                ]

                ok, order_id, pickup_code, error_reason = self.db.create_cart_order_atomic(
                    user_id=user_id,
                    store_id=store_id,
                    cart_items=cart_items,
                    delivery_address=None,
                    delivery_price=0,
                    payment_method=payment_method,
                )

                if not ok or not order_id:
                    return {
                        "success": False,
                        "error": error_reason or "Failed to create cart pickup order",
                    }

                store_orders: list[dict[str, Any]] = []
                for item in items:
                    qty = int(item.get("quantity", 1))
                    price = int(item.get("price", 0))
                    store_orders.append(
                        {
                            "order_id": int(order_id),
                            "offer_id": int(item.get("offer_id") or 0),
                            "store_id": store_id,
                            "quantity": qty,
                            "price": price,
                            "total": price * qty,
                            "pickup_code": pickup_code,
                            "title": item.get("title", ""),
                            "store_name": item.get("store_name", ""),
                            "store_address": item.get("store_address", ""),
                            "delivery_price": 0,
                        }
                    )

                return {
                    "success": True,
                    "order_ids": [int(order_id)],
                    "booking_ids": [],
                    "pickup_codes": [pickup_code] if pickup_code else [],
                    "stores_orders": {store_id: store_orders},
                }

            # Single-item pickup: regular order row is fine
            result = self.db.create_cart_order(
                user_id=user_id,
                items=items,
                order_type="pickup",
                delivery_address=None,
                payment_method=payment_method,
            )

            created_orders = result.get("created_orders", [])
            if not created_orders:
                return {"success": False, "error": "No orders created"}

            return {
                "success": True,
                "order_ids": [o.get("order_id") for o in created_orders if o.get("order_id")],
                "booking_ids": [],
                "pickup_codes": [
                    o.get("pickup_code") for o in created_orders if o.get("pickup_code")
                ],
                "stores_orders": result.get("stores_orders", {}),
            }
        except Exception as e:
            logger.error(f"Failed to create pickup orders: {e}")
            return {"success": False, "error": str(e)}

    async def _create_delivery_orders(
        self,
        user_id: int,
        items: list[dict],
        delivery_address: str,
        payment_method: str,
        order_type: str = "delivery",
    ) -> dict:
        """Create delivery orders."""
        try:
            # Cart delivery must be a SINGLE order row (per store) to keep payment/proof/admin flow consistent.
            if (
                len(items) > 1
                and hasattr(self.db, "create_cart_order_atomic")
                and items
                and items[0].get("store_id")
            ):
                store_id = int(items[0]["store_id"])
                delivery_price = int(items[0].get("delivery_price") or 0)

                cart_items = [
                    {
                        "offer_id": int(item["offer_id"]),
                        "quantity": int(item.get("quantity", 1)),
                        "price": int(item.get("price", 0)),
                        "title": item.get("title", ""),
                    }
                    for item in items
                ]

                ok, order_id, _pickup_code, error_reason = self.db.create_cart_order_atomic(
                    user_id=user_id,
                    store_id=store_id,
                    cart_items=cart_items,
                    delivery_address=delivery_address,
                    delivery_price=delivery_price,
                    payment_method=payment_method,
                    order_type=order_type,
                )

                if not ok or not order_id:
                    return {
                        "success": False,
                        "error": error_reason or "Failed to create cart delivery order",
                    }

                store_orders: list[dict[str, Any]] = []
                for item in items:
                    qty = int(item.get("quantity", 1))
                    price = int(item.get("price", 0))
                    store_orders.append(
                        {
                            "order_id": int(order_id),
                            "offer_id": int(item.get("offer_id") or 0),
                            "store_id": store_id,
                            "quantity": qty,
                            "price": price,
                            "total": price * qty,
                            "pickup_code": None,  # delivery
                            "title": item.get("title", ""),
                            "store_name": item.get("store_name", ""),
                            "store_address": item.get("store_address", ""),
                            "delivery_price": delivery_price,
                        }
                    )

                return {
                    "success": True,
                    "order_ids": [int(order_id)],
                    "booking_ids": [],
                    "pickup_codes": [],
                    "stores_orders": {store_id: store_orders},
                }

            result = self.db.create_cart_order(
                user_id=user_id,
                items=items,
                order_type=order_type,
                delivery_address=delivery_address,
                payment_method=payment_method,
            )

            created_orders = result.get("created_orders", [])
            if not created_orders:
                return {"success": False, "error": "No orders created"}

            return {
                "success": True,
                "order_ids": [o.get("order_id") for o in created_orders if o.get("order_id")],
                "booking_ids": [],
                "pickup_codes": [
                    o.get("pickup_code") for o in created_orders if o.get("pickup_code")
                ],
                "stores_orders": result.get("stores_orders", {}),
            }
        except Exception as e:
            logger.error(f"Failed to create delivery orders: {e}")
            return {"success": False, "error": str(e)}

    async def _notify_sellers_new_order(
        self,
        stores_orders: dict[int, list[dict]],
        order_type: str,
        delivery_address: str | None,
        payment_method: str,
        customer_name: str,
        customer_phone: str,
        send_telegram: bool | None = None,
    ) -> None:
        """Send order notifications to sellers, grouped by store."""
        telegram_enabled = (
            self.telegram_order_notifications
            if send_telegram is None
            else send_telegram
        )
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
                    store_orders[0].get("delivery_price", 0)
                    if order_type in ("delivery", "taxi")
                    else 0
                )

                # Build notification
                order_ids: list[str] = []
                order_id_ints: list[int] = []
                seen_order_ids: set[int] = set()
                for o in store_orders:
                    oid = o.get("order_id")
                    if not oid:
                        continue
                    oid_int = int(oid)
                    if oid_int in seen_order_ids:
                        continue
                    seen_order_ids.add(oid_int)
                    order_ids.append(str(oid_int))
                    order_id_ints.append(oid_int)

                pickup_codes: list[str] = []
                seen_codes: set[str] = set()
                for o in store_orders:
                    code = o.get("pickup_code")
                    if not code or code in seen_codes:
                        continue
                    seen_codes.add(code)
                    pickup_codes.append(code)

                seller_text = NotificationTemplates.seller_new_order(
                    lang=seller_lang,
                    order_ids=order_ids,
                    pickup_codes=pickup_codes,
                    items=store_orders,
                    order_type=order_type,
                    delivery_address=delivery_address,
                    payment_method=payment_method,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    total=store_total,
                    delivery_price=store_delivery,
                    currency=currency,
                )

                # Build keyboard - unified callback pattern
                first_order_id = store_orders[0]["order_id"]
                kb = InlineKeyboardBuilder()
                if seller_lang == "uz":
                    kb.button(
                        text="✅ Qabul qilish", callback_data=f"order_confirm_{first_order_id}"
                    )
                    kb.button(text="❌ Rad etish", callback_data=f"order_reject_{first_order_id}")
                else:
                    kb.button(text="✅ Принять", callback_data=f"order_confirm_{first_order_id}")
                    kb.button(text="❌ Отклонить", callback_data=f"order_reject_{first_order_id}")
                kb.adjust(2)

                sent_msg = None
                if telegram_enabled:
                    sent_msg = await self.bot.send_message(
                        owner_id, seller_text, parse_mode="HTML", reply_markup=kb.as_markup()
                    )
                    logger.info(
                        f"Sent order notification to seller {owner_id} for orders {order_ids}"
                    )

                    if sent_msg and hasattr(self.db, "set_order_seller_message_id"):
                        for order_id in order_id_ints:
                            try:
                                self.db.set_order_seller_message_id(order_id, sent_msg.message_id)
                            except Exception as save_err:
                                logger.warning(
                                    f"Failed to save seller_message_id for order #{order_id}: {save_err}"
                            )

                # Send NotificationService store event (partner panel WebSocket)
                try:
                    notification_service = get_notification_service()
                    title = (
                        "Yangi buyurtma" if seller_lang == "uz" else "Новый заказ"
                    )
                    plain_msg = re.sub(r"<[^>]+>", "", seller_text)
                    await notification_service.notify_store(
                        Notification(
                            type=NotificationType.SYSTEM_ANNOUNCEMENT,
                            recipient_id=int(store_id),
                            title=title,
                            message=plain_msg,
                            data={
                                "kind": "new_order",
                                "order_ids": order_ids,
                                "order_type": order_type,
                                "customer_name": customer_name,
                                "total": store_total,
                                "items": [
                                    {
                                        "title": o.get("title", ""),
                                        "quantity": o.get("quantity", 1),
                                        "price": o.get("price", 0),
                                    }
                                    for o in store_orders
                                ],
                                "delivery_address": delivery_address,
                            },
                            priority=0,
                        )
                    )
                except Exception as notify_error:
                    logger.warning(f"Store notification failed: {notify_error}")

                # Send WebSocket notification to web panel (real-time)
                try:
                    from app.api.websocket_manager import get_connection_manager
                    manager = get_connection_manager()
                    
                    # Prepare order data for WebSocket
                    order_data = {
                        "order_ids": order_ids,
                        "order_type": order_type,
                        "customer_name": customer_name,
                        "total": store_total,
                        "items": [
                            {
                                "title": o.get("title", ""),
                                "quantity": o.get("quantity", 1),
                                "price": o.get("price", 0)
                            }
                            for o in store_orders
                        ],
                        "delivery_address": delivery_address,
                        "timestamp": str(datetime.now())
                    }
                    
                    sent = await manager.notify_new_order(store_id, order_data)
                    if sent > 0:
                        logger.info(f"📤 Sent WebSocket notification to {sent} web panels for store {store_id}")
                    
                except Exception as ws_error:
                    logger.warning(f"⚠️ Failed to send WebSocket notification: {ws_error}")
                    # Don't fail if WebSocket fails - Telegram notification still sent

            except Exception as e:
                logger.error(f"Failed to notify seller for store {store_id}: {e}")

    async def confirm_payment(self, order_id: int) -> bool:
        """Mark payment as confirmed and notify seller if not yet notified."""
        try:
            if not hasattr(self.db, "get_order"):
                return False

            order = self.db.get_order(order_id)
            if not order:
                return False

            if isinstance(order, dict):
                store_id = order.get("store_id")
                delivery_address = order.get("delivery_address")
                order_type = order.get("order_type")
                payment_method = order.get("payment_method")
                pickup_code = order.get("pickup_code")
                cart_items_json = order.get("cart_items")
                offer_id = order.get("offer_id")
                quantity = order.get("quantity", 1)
                customer_id = order.get("user_id")
                seller_message_id = order.get("seller_message_id")
                current_status = order.get("order_status")
            else:
                store_id = getattr(order, "store_id", None)
                delivery_address = getattr(order, "delivery_address", None)
                order_type = getattr(order, "order_type", None)
                payment_method = getattr(order, "payment_method", None)
                pickup_code = getattr(order, "pickup_code", None)
                cart_items_json = getattr(order, "cart_items", None)
                offer_id = getattr(order, "offer_id", None)
                quantity = getattr(order, "quantity", 1)
                customer_id = getattr(order, "user_id", None)
                seller_message_id = getattr(order, "seller_message_id", None)
                current_status = getattr(order, "order_status", None)

            if hasattr(self.db, "update_payment_status"):
                self.db.update_payment_status(order_id, PaymentStatus.CONFIRMED)

            if current_status in ("awaiting_payment", "awaiting_admin_confirmation"):
                if hasattr(self.db, "update_order_status"):
                    self.db.update_order_status(order_id, OrderStatus.PENDING)

            if seller_message_id:
                return True

            if not order_type:
                order_type = "delivery" if delivery_address else "pickup"

            store = self.db.get_store(store_id) if store_id else None
            store_name = store.get("name", "") if isinstance(store, dict) else ""
            store_address = store.get("address", "") if isinstance(store, dict) else ""

            items: list[dict[str, Any]] = []
            if cart_items_json:
                import json

                cart_items = (
                    json.loads(cart_items_json)
                    if isinstance(cart_items_json, str)
                    else cart_items_json
                )
                store_delivery_price = (
                    store.get("delivery_price", 0) if isinstance(store, dict) else 0
                )
                for item in cart_items or []:
                    item_delivery_price = int(item.get("delivery_price", 0))
                    if order_type in ("delivery", "taxi") and not item_delivery_price:
                        item_delivery_price = int(store_delivery_price or 0)
                    items.append(
                        {
                            "order_id": order_id,
                            "offer_id": int(item.get("offer_id") or 0),
                            "store_id": int(store_id or 0),
                            "quantity": int(item.get("quantity", 1)),
                            "price": int(item.get("price", 0)),
                            "total": int(item.get("price", 0)) * int(item.get("quantity", 1)),
                            "pickup_code": pickup_code,
                            "title": item.get("title", ""),
                            "store_name": store_name,
                            "store_address": store_address,
                            "delivery_price": item_delivery_price,
                        }
                    )
            elif offer_id:
                offer = self.db.get_offer(int(offer_id)) if hasattr(self.db, "get_offer") else None
                title = offer.get("title", "") if isinstance(offer, dict) else ""
                price = offer.get("discount_price", 0) if isinstance(offer, dict) else 0
                items.append(
                    {
                        "order_id": order_id,
                        "offer_id": int(offer_id),
                        "store_id": int(store_id or 0),
                        "quantity": int(quantity or 1),
                        "price": int(price),
                        "total": int(price) * int(quantity or 1),
                        "pickup_code": pickup_code,
                        "title": title,
                        "store_name": store_name,
                        "store_address": store_address,
                        "delivery_price": int(order.get("delivery_price", 0))
                        if isinstance(order, dict)
                        else int(getattr(order, "delivery_price", 0) or 0),
                    }
                )

            if not items or not store_id:
                return True

            customer = (
                self.db.get_user_model(customer_id)
                if hasattr(self.db, "get_user_model")
                else self.db.get_user(customer_id)
            )
            if isinstance(customer, dict):
                customer_name = customer.get("first_name", "")
                customer_phone = customer.get("phone", "")
            else:
                customer_name = getattr(customer, "first_name", "") if customer else ""
                customer_phone = getattr(customer, "phone", "") if customer else ""

            await self._notify_sellers_new_order(
                stores_orders={int(store_id): items},
                order_type=order_type,
                delivery_address=delivery_address,
                payment_method=PaymentStatus.normalize_method(payment_method),
                customer_name=customer_name,
                customer_phone=customer_phone,
            )

            return True
        except Exception as e:
            logger.error(f"Failed to confirm payment for order #{order_id}: {e}")
            return False

    # =========================================================================
    # STATUS MANAGEMENT
    # =========================================================================

    async def update_status(
        self,
        entity_id: int,
        entity_type: Literal["order", "booking"],
        new_status: str,
        notify_customer: bool = True,
        reject_reason: str | None = None,
        courier_phone: str | None = None,
    ) -> bool:
        """
        Update order/booking status with automatic customer notification.

        Args:
            entity_id: Order or booking ID
            entity_type: "order" or "booking"
            new_status: New status from OrderStatus
            notify_customer: Whether to notify customer
            reject_reason: Reason for rejection (if status is REJECTED)
            courier_phone: Courier phone number (for DELIVERING status)

        Returns:
            True if successful
        """
        try:
            # IMPORTANT: orders and bookings may still live in different tables at runtime.
            # Respect entity_type to avoid updating a wrong record on id collision.
            if entity_type == "booking":
                if not hasattr(self.db, "get_booking"):
                    logger.warning("DB layer does not support bookings")
                    return False

                entity = self.db.get_booking(entity_id)
                if not entity:
                    logger.warning(f"Booking not found: #{entity_id}")
                    return False
            else:
                if not hasattr(self.db, "get_order"):
                    logger.warning("DB layer does not support orders")
                    return False

                entity = self.db.get_order(entity_id)
                if not entity:
                    logger.warning(f"Order not found: #{entity_id}")
                    return False

            # Get entity fields
            if entity_type == "booking":
                if isinstance(entity, dict):
                    user_id = entity.get("user_id")
                    store_id = entity.get("store_id")
                    pickup_code = entity.get("booking_code") or entity.get("pickup_code")
                    current_status_raw = entity.get("status") or entity.get("order_status")
                else:
                    user_id = getattr(entity, "user_id", None)
                    store_id = getattr(entity, "store_id", None)
                    pickup_code = getattr(entity, "booking_code", None) or getattr(
                        entity, "pickup_code", None
                    )
                    current_status_raw = getattr(entity, "status", None) or getattr(
                        entity, "order_status", None
                    )

                order_type = "pickup"
            else:
                if isinstance(entity, dict):
                    user_id = entity.get("user_id")
                    store_id = entity.get("store_id")
                    pickup_code = entity.get("pickup_code")
                    current_status_raw = entity.get("order_status")
                    order_type = entity.get("order_type")
                    payment_method = entity.get("payment_method")

                    # Fallback: if order_type not set, determine from delivery_address
                    if not order_type:
                        delivery_addr = entity.get("delivery_address")
                        order_type = "delivery" if delivery_addr else "pickup"
                        logger.info(
                            f"Order type fallback for #{entity_id}: "
                            f"delivery_address={delivery_addr}, order_type={order_type}"
                        )
                    else:
                        logger.info(f"Order type from DB for #{entity_id}: {order_type}")
                else:
                    # Tuple format
                    user_id = getattr(entity, "user_id", None)
                    store_id = getattr(entity, "store_id", None)
                    pickup_code = getattr(entity, "pickup_code", None)
                    current_status_raw = getattr(entity, "order_status", None)
                    order_type = getattr(entity, "order_type", None)
                    payment_method = getattr(entity, "payment_method", None)
                    if not order_type:
                        order_type = (
                            "delivery"
                            if getattr(entity, "delivery_address", None)
                            else "pickup"
                        )

            # Normalize statuses and enforce safe transitions/idempotence
            current_status = (
                OrderStatus.normalize(str(current_status_raw)) if current_status_raw else None
            )
            target_status = OrderStatus.normalize(str(new_status))
            normalized_payment_method = PaymentStatus.normalize_method(payment_method)
            terminal_statuses = {
                OrderStatus.COMPLETED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
            }

            # Idempotent update: requested status already set
            if current_status == target_status:
                logger.info(f"STATUS_UPDATE no-op (already {target_status}): #{entity_id}")
                return True

            # Do not move away from terminal statuses (completed/cancelled/rejected)
            if current_status in terminal_statuses and target_status != current_status:
                logger.info(
                    f"STATUS_UPDATE ignored for terminal entity: #{entity_id} "
                    f"status={current_status} -> {target_status}"
                )
                return True

            if target_status == OrderStatus.DELIVERING:
                if order_type not in ("delivery", "taxi"):
                    logger.info(
                        f"STATUS_UPDATE invalid delivering for pickup: #{entity_id} order_type={order_type}"
                    )
                    return False

            # Update status in DB
            if entity_type == "booking":
                if not hasattr(self.db, "update_booking_status"):
                    logger.warning("DB layer does not support update_booking_status")
                    return False
                self.db.update_booking_status(entity_id, target_status)
            else:
                if not hasattr(self.db, "update_order_status"):
                    logger.warning("DB layer does not support update_order_status")
                    return False
                self.db.update_order_status(entity_id, target_status)

            # Restore quantity if rejected or cancelled
            if target_status in [OrderStatus.REJECTED, OrderStatus.CANCELLED] and (
                current_status not in [OrderStatus.REJECTED, OrderStatus.CANCELLED]
            ):
                await self._restore_quantities(entity, entity_type)

            # Send notification to customer - SMART FILTERING
            # Skip redundant notifications to avoid spam:
            # - READY status (internal state, customer doesn't need notification)
            # - Only important statuses: PREPARING (accepted), DELIVERING, COMPLETED, REJECTED, CANCELLED
            should_notify = notify_customer and user_id

            logger.info(
                f"Notification check for #{entity_id}: "
                f"status={target_status}, order_type={order_type}, "
                f"notify_customer={notify_customer}, user_id={user_id}, "
                f"should_notify={should_notify}"
            )

            # OPTIMIZATION: Skip READY notification for ALL orders
            # READY is an internal state (order packed, waiting for pickup/courier)
            # Customer only needs: PREPARING (accepted) → DELIVERING (in transit) → COMPLETED
            if target_status == OrderStatus.READY:
                should_notify = False
                logger.info(
                    f"⚡ Skipping READY notification (internal state) for {order_type} order#{entity_id}"
                )

            if user_id:
                try:
                    from app.core.websocket import get_websocket_manager

                    ws_manager = get_websocket_manager()
                    await ws_manager.send_to_user(
                        int(user_id),
                        {
                            "type": "order_status_changed",
                            "data": {
                                "entity_id": entity_id,
                                "entity_type": entity_type,
                                "status": target_status,
                                "order_type": order_type,
                            },
                        },
                    )
                except Exception as ws_error:
                    logger.warning(f"WebSocket notify failed for status change: {ws_error}")

            if store_id:
                try:
                    from app.api.websocket_manager import get_connection_manager

                    store_ws = get_connection_manager()
                    await store_ws.notify_order_status(
                        int(store_id), int(entity_id), target_status
                    )
                except Exception as ws_error:
                    logger.warning(f"Partner WebSocket notify failed: {ws_error}")

                try:
                    notification_service = get_notification_service()
                    await notification_service.notify_store(
                        Notification(
                            type=NotificationType.SYSTEM_ANNOUNCEMENT,
                            recipient_id=int(store_id),
                            title=f"Order #{entity_id}",
                            message=f"Status: {target_status}",
                            data={
                                "kind": "order_status_changed",
                                "order_id": entity_id,
                                "status": target_status,
                                "order_type": order_type,
                            },
                            priority=0,
                        )
                    )
                except Exception as notify_error:
                    logger.warning(f"Store status notification failed: {notify_error}")

            if should_notify:
                store = self.db.get_store(store_id) if store_id else None
                store_name = store.get("name", "") if isinstance(store, dict) else ""
                store_address = store.get("address", "") if isinstance(store, dict) else ""

                customer_lang = self.db.get_user_language(user_id)
                msg = NotificationTemplates.customer_status_update(
                    lang=customer_lang,
                    order_id=entity_id,
                    status=target_status,
                    order_type=order_type,
                    store_name=store_name,
                    store_address=store_address,
                    pickup_code=pickup_code,
                    reject_reason=reject_reason,
                    courier_phone=courier_phone,
                )

                try:
                    notif_title = (
                        f"Buyurtma #{entity_id}"
                        if customer_lang == "uz"
                        else f"Заказ #{entity_id}"
                    )
                    plain_msg = re.sub(r"<[^>]+>", "", msg)
                    if target_status in (OrderStatus.CANCELLED,):
                        notif_type = NotificationType.BOOKING_CANCELLED
                    elif target_status in (OrderStatus.COMPLETED,):
                        notif_type = NotificationType.BOOKING_COMPLETED
                    elif target_status in (OrderStatus.PREPARING, OrderStatus.DELIVERING):
                        notif_type = NotificationType.BOOKING_CONFIRMED
                    else:
                        notif_type = NotificationType.SYSTEM_ANNOUNCEMENT

                    notification_service = get_notification_service()
                    await notification_service.notify_user(
                        Notification(
                            type=notif_type,
                            recipient_id=int(user_id),
                            title=notif_title,
                            message=plain_msg,
                            data={
                                "order_id": entity_id,
                                "status": target_status,
                                "order_type": order_type,
                                "entity_type": entity_type,
                            },
                            priority=0,
                        )
                    )
                except Exception as notify_error:
                    logger.warning(
                        f"Notification service failed for {entity_type}#{entity_id}: {notify_error}"
                    )

                # Add buttons for customer based on status
                reply_markup = None
                if target_status == OrderStatus.COMPLETED:
                    # Rating buttons for completed orders
                    kb = InlineKeyboardBuilder()
                    callback_prefix = (
                        f"rate_order_{entity_id}_"
                        if entity_type == "order"
                        else f"rate_booking_{entity_id}_"
                    )
                    for i in range(1, 6):
                        kb.button(text="⭐" * i, callback_data=f"{callback_prefix}{i}")
                    kb.adjust(5)
                    reply_markup = kb.as_markup()
                elif new_status == OrderStatus.DELIVERING and order_type in ("delivery", "taxi"):
                    # "Received" button for delivery orders in transit
                    kb = InlineKeyboardBuilder()
                    received_text = "✅ Oldim" if customer_lang == "uz" else "✅ Получил"
                    kb.button(text=received_text, callback_data=f"customer_received_{entity_id}")
                    reply_markup = kb.as_markup()
                elif target_status == OrderStatus.PREPARING and order_type == "pickup":
                    # "Received" button for pickup orders when preparing
                    # v24+: all orders in unified table, use customer_received_
                    kb = InlineKeyboardBuilder()
                    received_text = "✅ Oldim" if customer_lang == "uz" else "✅ Получил"
                    kb.button(text=received_text, callback_data=f"customer_received_{entity_id}")
                    reply_markup = kb.as_markup()

                if self.telegram_order_notifications:
                    # Try to EDIT existing message first (live status update)
                    # This reduces spam - customer sees ONE message that updates
                    existing_message_id = None
                    if isinstance(entity, dict):
                        existing_message_id = entity.get("customer_message_id")
                    else:
                        existing_message_id = getattr(entity, "customer_message_id", None)

                    message_sent = None
                    edit_success = False

                    if existing_message_id:
                        logger.info(
                            f"Trying to edit message {existing_message_id} for #{entity_id}"
                        )

                        # Try BOTH methods - caption first (for photos), then text
                        # Because we don't know if original message had photo or not

                        # Method 1: Try edit_message_caption (for messages with photo)
                        try:
                            await self.bot.edit_message_caption(
                                chat_id=user_id,
                                message_id=existing_message_id,
                                caption=msg,
                                parse_mode="HTML",
                                reply_markup=reply_markup,
                            )
                            edit_success = True
                            logger.info(f"✅ Edited CAPTION for {entity_type}#{entity_id}")
                        except Exception as caption_error:
                            logger.debug(f"Caption edit failed: {caption_error}")

                            # Method 2: Try edit_message_text (for text-only messages)
                            try:
                                await self.bot.edit_message_text(
                                    chat_id=user_id,
                                    message_id=existing_message_id,
                                    text=msg,
                                    parse_mode="HTML",
                                    reply_markup=reply_markup,
                                )
                                edit_success = True
                                logger.info(f"✅ Edited TEXT for {entity_type}#{entity_id}")
                            except Exception as text_error:
                                logger.warning(
                                    f"❌ Both edit methods failed for {entity_type}#{entity_id}: caption={caption_error}, text={text_error}"
                                )

                    if not edit_success:
                        # Send new message only if edit failed or no existing message
                        try:
                            message_sent = await self.bot.send_message(
                                user_id, msg, parse_mode="HTML", reply_markup=reply_markup
                            )
                            logger.info(f"📤 Sent NEW message for {entity_type}#{entity_id}")
                            # Save message_id for future edits - ALWAYS save to maintain live update chain
                            if message_sent:
                                if entity_type == "order" and hasattr(
                                    self.db, "set_order_customer_message_id"
                                ):
                                    self.db.set_order_customer_message_id(
                                        entity_id, message_sent.message_id
                                    )
                                    logger.info(
                                        f"💾 Saved message_id={message_sent.message_id} for order#{entity_id}"
                                    )
                                elif entity_type == "booking" and hasattr(
                                    self.db, "set_booking_customer_message_id"
                                ):
                                    self.db.set_booking_customer_message_id(
                                        entity_id, message_sent.message_id
                                    )
                                    logger.info(
                                        f"💾 Saved message_id={message_sent.message_id} for booking#{entity_id}"
                                    )
                        except Exception as e:
                            logger.error(f"Failed to notify customer {user_id}: {e}")

            logger.info(f"STATUS_UPDATE: #{entity_id} -> {target_status}")
            return True

        except Exception as e:
            logger.error(f"Failed to update status: {e}")
            return False

    async def _restore_quantities(self, entity: Any, entity_type: str) -> None:
        """Restore offer quantities when order is cancelled/rejected."""
        import json

        try:
            if isinstance(entity, dict):
                is_cart = (
                    entity.get("is_cart_order", 0) == 1 or entity.get("is_cart_booking", 0) == 1
                )
                cart_items_json = entity.get("cart_items")
                offer_id = entity.get("offer_id")
                quantity = entity.get("quantity", 1)
            else:
                is_cart = (
                    getattr(entity, "is_cart_order", 0) == 1
                    or getattr(entity, "is_cart_booking", 0) == 1
                )
                cart_items_json = getattr(entity, "cart_items", None)
                offer_id = getattr(entity, "offer_id", None)
                quantity = getattr(entity, "quantity", 1)

            if is_cart and cart_items_json:
                cart_items = (
                    json.loads(cart_items_json)
                    if isinstance(cart_items_json, str)
                    else cart_items_json
                )
                for item in cart_items:
                    item_offer_id = item.get("offer_id")
                    item_qty = item.get("quantity", 1)
                    if item_offer_id:
                        try:
                            self.db.increment_offer_quantity_atomic(item_offer_id, int(item_qty))
                        except Exception:
                            pass
            elif offer_id:
                try:
                    self.db.increment_offer_quantity_atomic(offer_id, int(quantity))
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Failed to restore quantities: {e}")

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def confirm_order(
        self,
        entity_id: int,
        entity_type: Literal["order", "booking"],
    ) -> bool:
        """Seller confirms an order - moves to PREPARING status."""
        return await self.update_status(
            entity_id=entity_id,
            entity_type=entity_type,
            new_status=OrderStatus.PREPARING,
            notify_customer=True,
        )

    async def reject_order(
        self,
        entity_id: int,
        entity_type: Literal["order", "booking"],
        reason: str | None = None,
    ) -> bool:
        """Seller rejects an order."""
        return await self.update_status(
            entity_id=entity_id,
            entity_type=entity_type,
            new_status=OrderStatus.REJECTED,
            notify_customer=True,
            reject_reason=reason,
        )

    async def mark_ready(
        self,
        entity_id: int,
        entity_type: Literal["order", "booking"],
    ) -> bool:
        """Mark order as ready for pickup/delivery."""
        return await self.update_status(
            entity_id=entity_id,
            entity_type=entity_type,
            new_status=OrderStatus.READY,
            notify_customer=True,
        )

    async def start_delivery(
        self,
        order_id: int,
        courier_phone: str | None = None,
    ) -> bool:
        """Mark delivery order as in transit."""
        return await self.update_status(
            entity_id=order_id,
            entity_type="order",
            new_status=OrderStatus.DELIVERING,
            notify_customer=True,
            courier_phone=courier_phone,
        )

    async def complete_order(
        self,
        entity_id: int,
        entity_type: Literal["order", "booking"],
    ) -> bool:
        """Mark order as completed."""
        return await self.update_status(
            entity_id=entity_id,
            entity_type=entity_type,
            new_status=OrderStatus.COMPLETED,
            notify_customer=True,
        )

    async def cancel_order(
        self,
        entity_id: int,
        entity_type: Literal["order", "booking"],
    ) -> bool:
        """Customer cancels an order."""
        return await self.update_status(
            entity_id=entity_id,
            entity_type=entity_type,
            new_status=OrderStatus.CANCELLED,
            notify_customer=True,
        )


# =============================================================================
# SINGLETON
# =============================================================================

_unified_order_service: UnifiedOrderService | None = None


def get_unified_order_service() -> UnifiedOrderService | None:
    """Get the unified order service singleton."""
    return _unified_order_service


def init_unified_order_service(db: Any, bot: Bot) -> UnifiedOrderService:
    """Initialize the unified order service singleton."""
    global _unified_order_service
    _unified_order_service = UnifiedOrderService(db, bot)
    return _unified_order_service
