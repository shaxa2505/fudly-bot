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
    READY       → Ready for pickup/delivery
    DELIVERING  → In transit (delivery only)
    COMPLETED   → Order completed
    REJECTED    → Rejected by seller
    CANCELLED   → Cancelled by customer

NOTIFICATION STRATEGY:
    - Minimize spam by sending fewer, more meaningful notifications
    - Use visual progress bars for better UX
    - Pickup: only PREPARING and COMPLETED notifications
    - Delivery: PREPARING, DELIVERING, COMPLETED notifications
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Literal

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

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
        }
        return mapping.get(status, status)


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

        if lang == "uz":
            order_type_text = "🏪 O'zi olib ketadi" if order_type == "pickup" else "🚚 Yetkazish"
            lines = [
                "🔔 <b>YANGI BUYURTMA!</b>",
                "━━━━━━━━━━━━━━━━━━",
                "",
                f"📦 #{', #'.join(order_ids)}",
                f"📋 {order_type_text}",
            ]

            if pickup_codes:
                lines.append(f"🎫 Kod: <b>{', '.join(pickup_codes)}</b>")

            lines.extend(
                [
                    "",
                    f"👤 {_esc(customer_name)}",
                    f"📱 <code>{_esc(customer_phone)}</code>",
                ]
            )

            if order_type == "delivery" and delivery_address:
                lines.append(f"📍 {_esc(delivery_address)}")

            lines.append("")
            lines.append("<b>Mahsulotlar:</b>")
            for item in items:
                subtotal = item["price"] * item["quantity"]
                lines.append(
                    f"• {_esc(item['title'])} × {item['quantity']} = {int(subtotal):,} {currency}"
                )

            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━")
            lines.append(f"💵 Mahsulotlar: {int(total):,} {currency}")

            if order_type == "delivery":
                lines.append(f"🚚 Yetkazish: {int(delivery_price):,} {currency}")
                lines.append(f"💰 <b>JAMI: {int(total + delivery_price):,} {currency}</b>")
            else:
                lines.append(f"💰 <b>JAMI: {int(total):,} {currency}</b>")

            payment_text = "💵 Naqd" if payment_method == "cash" else "💳 Karta"
            lines.extend(["", payment_text, ""])
            lines.append("⏳ <b>Buyurtmani tasdiqlang!</b>")

        else:  # Russian
            order_type_text = "🏪 Самовывоз" if order_type == "pickup" else "🚚 Доставка"
            lines = [
                "🔔 <b>НОВЫЙ ЗАКАЗ!</b>",
                "━━━━━━━━━━━━━━━━━━",
                "",
                f"📦 #{', #'.join(order_ids)}",
                f"📋 {order_type_text}",
            ]

            if pickup_codes:
                lines.append(f"🎫 Код: <b>{', '.join(pickup_codes)}</b>")

            lines.extend(
                [
                    "",
                    f"👤 {_esc(customer_name)}",
                    f"📱 <code>{_esc(customer_phone)}</code>",
                ]
            )

            if order_type == "delivery" and delivery_address:
                lines.append(f"📍 {_esc(delivery_address)}")

            lines.append("")
            lines.append("<b>Товары:</b>")
            for item in items:
                subtotal = item["price"] * item["quantity"]
                lines.append(
                    f"• {_esc(item['title'])} × {item['quantity']} = {int(subtotal):,} {currency}"
                )

            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━")
            lines.append(f"💵 Товары: {int(total):,} {currency}")

            if order_type == "delivery":
                lines.append(f"🚚 Доставка: {int(delivery_price):,} {currency}")
                lines.append(f"💰 <b>ИТОГО: {int(total + delivery_price):,} {currency}</b>")
            else:
                lines.append(f"💰 <b>ИТОГО: {int(total):,} {currency}</b>")

            payment_text = "💵 Наличные" if payment_method == "cash" else "💳 Карта"
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
    ) -> str:
        """Build customer notification for order creation."""

        def _esc(val: Any) -> str:
            return html.escape(str(val)) if val else ""

        if lang == "uz":
            lines = [
                "✅ <b>BUYURTMA QABUL QILINDI!</b>",
                "━━━━━━━━━━━━━━━━━━━━",
                "",
                f"📦 #{', #'.join(order_ids)}",
                f"🏪 {_esc(store_name)}",
            ]

            if order_type == "pickup":
                lines.append("📋 🏪 O'zim olib ketaman")
                lines.append(f"📍 {_esc(store_address)}")
                if pickup_codes:
                    lines.append("")
                    lines.append(f"🎫 <b>Kod: {', '.join(pickup_codes)}</b>")
            else:
                lines.append("📋 🚚 Yetkazib berish")
                if delivery_address:
                    lines.append(f"📍 {_esc(delivery_address)}")

            lines.append("")
            lines.append("<b>Mahsulotlar:</b>")
            for item in items:
                subtotal = item["price"] * item["quantity"]
                lines.append(
                    f"• {_esc(item['title'])} × {item['quantity']} = {int(subtotal):,} {currency}"
                )

            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"💵 Mahsulotlar: {int(total):,} {currency}")

            if order_type == "delivery":
                lines.append(f"🚚 Yetkazish: {int(delivery_price):,} {currency}")

            lines.append(f"💰 <b>JAMI: {int(total + delivery_price):,} {currency}</b>")

            payment_text = "💵 Naqd" if payment_method == "cash" else "💳 Karta"
            lines.extend(["", payment_text, ""])

            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("⏰ <b>KEYINGI QADAM?</b>")
            lines.append("Do'kon tasdiqlashini kuting")
            lines.append("(odatda 5-10 daqiqa)")
            lines.append("")
            lines.append("✨ Buyurtma tayyor bo'lganda yozamiz!")

            if order_type == "pickup" and pickup_codes:
                lines.append("")
                lines.append("💡 <b>Maslahat:</b> olishda sotuvchiga kodni ko'rsating")

        else:  # Russian
            lines = [
                "✅ <b>ЗАКАЗ ОФОРМЛЕН!</b>",
                "━━━━━━━━━━━━━━━━━━━━",
                "",
                f"📦 #{', #'.join(order_ids)}",
                f"🏪 {_esc(store_name)}",
            ]

            if order_type == "pickup":
                lines.append("📋 🏪 Самовывоз")
                lines.append(f"📍 {_esc(store_address)}")
                if pickup_codes:
                    lines.append("")
                    lines.append(f"🎫 <b>Код: {', '.join(pickup_codes)}</b>")
            else:
                lines.append("📋 🚚 Доставка")
                if delivery_address:
                    lines.append(f"📍 {_esc(delivery_address)}")

            lines.append("")
            lines.append("<b>Товары:</b>")
            for item in items:
                subtotal = item["price"] * item["quantity"]
                lines.append(
                    f"• {_esc(item['title'])} × {item['quantity']} = {int(subtotal):,} {currency}"
                )

            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"💵 Товары: {int(total):,} {currency}")

            if order_type == "delivery":
                lines.append(f"🚚 Доставка: {int(delivery_price):,} {currency}")

            lines.append(f"💰 <b>ИТОГО: {int(total + delivery_price):,} {currency}</b>")

            payment_text = "💵 Наличные" if payment_method == "cash" else "💳 Карта"
            lines.extend(["", payment_text, ""])

            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("⏰ <b>ЧТО ДАЛЬШЕ?</b>")
            lines.append("Ожидайте подтверждения от заведения")
            lines.append("(обычно 5-10 минут)")
            lines.append("")
            lines.append("✨ Мы напишем, когда заказ будет готов!")

            if order_type == "pickup" and pickup_codes:
                lines.append("")
                lines.append("💡 <b>Совет:</b> покажите код продавцу при получении")

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
        """Build customer notification for status update with visual progress."""

        def _esc(val: Any) -> str:
            return html.escape(str(val)) if val else ""

        # Visual progress bars
        def progress_pickup(step: int) -> str:
            """Progress for pickup: 1=accepted, 2=completed"""
            if step == 1:
                return (
                    "🟢 Qabul qilindi ━━━ ⚪ Topshirildi"
                    if lang == "uz"
                    else "🟢 Принят ━━━━━━ ⚪ Выдан"
                )
            return (
                "🟢 Qabul qilindi ━━━ 🟢 Topshirildi ✓"
                if lang == "uz"
                else "🟢 Принят ━━━━━━ 🟢 Выдан ✓"
            )

        def progress_delivery(step: int) -> str:
            """Progress for delivery: 1=accepted, 2=delivering, 3=completed"""
            if step == 1:
                return "🟢━━⚪━━⚪" if lang == "uz" else "🟢━━⚪━━⚪"
            elif step == 2:
                return "🟢━━🟢━━⚪" if lang == "uz" else "🟢━━🟢━━⚪"
            return "🟢━━🟢━━🟢 ✓"

        # Build templates based on order type
        if order_type == "pickup":
            # PICKUP: Clear instructions - where to go, what code, deadline
            templates = {
                "uz": {
                    OrderStatus.PREPARING: (
                        f"✅ <b>BRON TASDIQLANDI!</b>\n\n"
                        f"{progress_pickup(1)}\n\n"
                        f"📦 #{order_id}\n"
                        f"🏪 {_esc(store_name)}\n"
                        + (f"📍 {_esc(store_address)}\n\n" if store_address else "\n")
                        + (
                            f"🎫 <b>SIZNING KODINGIZ: {pickup_code}</b>\n\n"
                            if pickup_code
                            else "\n"
                        )
                        + "⏰ <b>2 SOAT ICHIDA OLIB KETING</b>\n"
                        + "❗ Muddati o'tsa bron bekor bo'ladi"
                    ),
                    OrderStatus.COMPLETED: (
                        f"🎊 <b>Buyurtma topshirildi!</b>\n\n"
                        f"{progress_pickup(2)}\n\n"
                        f"📦 #{order_id} • {_esc(store_name)}\n\n"
                        f"Rahmat! Yoqdimi? ⭐"
                    ),
                    OrderStatus.REJECTED: (
                        f"😔 <b>Bron rad etildi</b>\n\n"
                        f"📦 #{order_id}\n"
                        + (f"📝 Sabab: {_esc(reject_reason)}" if reject_reason else "")
                    ),
                    OrderStatus.CANCELLED: (f"❌ <b>Bron bekor qilindi</b>\n📦 #{order_id}"),
                },
                "ru": {
                    OrderStatus.PREPARING: (
                        f"✅ <b>БРОНЬ ПОДТВЕРЖДЕНА!</b>\n\n"
                        f"{progress_pickup(1)}\n\n"
                        f"📦 #{order_id}\n"
                        f"🏪 {_esc(store_name)}\n"
                        + (f"📍 {_esc(store_address)}\n\n" if store_address else "\n")
                        + (f"🎫 <b>ВАШ КОД: {pickup_code}</b>\n\n" if pickup_code else "\n")
                        + "⏰ <b>ЗАБЕРИТЕ В ТЕЧЕНИЕ 2 ЧАСОВ</b>\n"
                        + "❗ По истечении срока бронь отменится"
                    ),
                    OrderStatus.COMPLETED: (
                        f"🎊 <b>Заказ выдан!</b>\n\n"
                        f"{progress_pickup(2)}\n\n"
                        f"📦 #{order_id} • {_esc(store_name)}\n\n"
                        f"Спасибо! Понравилось? ⭐"
                    ),
                    OrderStatus.REJECTED: (
                        f"😔 <b>Бронь отклонена</b>\n\n"
                        f"📦 #{order_id}\n"
                        + (f"📝 Причина: {_esc(reject_reason)}" if reject_reason else "")
                    ),
                    OrderStatus.CANCELLED: (f"❌ <b>Бронь отменена</b>\n📦 #{order_id}"),
                },
            }
        else:  # delivery
            templates = {
                "uz": {
                    OrderStatus.PREPARING: (
                        f"🎉 <b>Buyurtma qabul qilindi!</b>\n\n"
                        f"{progress_delivery(1)}\n"
                        f"Qabul │ Yo'lda │ Yetkazildi\n\n"
                        f"📦 #{order_id} • {_esc(store_name)}\n"
                        f"👨‍🍳 Tayyorlanmoqda..."
                    ),
                    OrderStatus.DELIVERING: (
                        f"🚚 <b>Buyurtma yo'lda!</b>\n\n"
                        f"{progress_delivery(2)}\n"
                        f"Qabul │ Yo'lda │ Yetkazildi\n\n"
                        f"📦 #{order_id}\n"
                        f"⏱ ~30-60 daqiqa\n"
                        + (
                            f"\n📞 Kuryer: <code>{_esc(courier_phone)}</code>"
                            if courier_phone
                            else ""
                        )
                    ),
                    OrderStatus.COMPLETED: (
                        f"🎊 <b>Yetkazildi!</b>\n\n"
                        f"{progress_delivery(3)}\n\n"
                        f"📦 #{order_id} • {_esc(store_name)}\n\n"
                        f"Rahmat! ⭐"
                    ),
                    OrderStatus.REJECTED: (
                        f"😔 <b>Rad etildi</b>\n\n"
                        f"📦 #{order_id}\n" + (f"📝 {_esc(reject_reason)}" if reject_reason else "")
                    ),
                    OrderStatus.CANCELLED: (f"❌ <b>Bekor qilindi</b>\n📦 #{order_id}"),
                },
                "ru": {
                    OrderStatus.PREPARING: (
                        f"🎉 <b>Заказ принят!</b>\n\n"
                        f"{progress_delivery(1)}\n"
                        f"Принят │ В пути │ Доставлен\n\n"
                        f"📦 #{order_id} • {_esc(store_name)}\n"
                        f"👨‍🍳 Готовится..."
                    ),
                    OrderStatus.DELIVERING: (
                        f"🚚 <b>Заказ в пути!</b>\n\n"
                        f"{progress_delivery(2)}\n"
                        f"Принят │ В пути │ Доставлен\n\n"
                        f"📦 #{order_id}\n"
                        f"⏱ ~30-60 мин\n"
                        + (
                            f"\n📞 Курьер: <code>{_esc(courier_phone)}</code>"
                            if courier_phone
                            else ""
                        )
                    ),
                    OrderStatus.COMPLETED: (
                        f"🎊 <b>Доставлено!</b>\n\n"
                        f"{progress_delivery(3)}\n\n"
                        f"📦 #{order_id} • {_esc(store_name)}\n\n"
                        f"Спасибо! ⭐"
                    ),
                    OrderStatus.REJECTED: (
                        f"😔 <b>Отклонён</b>\n\n"
                        f"📦 #{order_id}\n" + (f"📝 {_esc(reject_reason)}" if reject_reason else "")
                    ),
                    OrderStatus.CANCELLED: (f"❌ <b>Отменён</b>\n📦 #{order_id}"),
                },
            }

        lang_templates = templates.get(lang, templates["ru"])
        return lang_templates.get(status, f"📦 #{order_id} - {status}")

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
        if order_type == "delivery":
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
        if lang == "uz":
            order_type_text = "🏪 O'zi olib ketadi" if order_type == "pickup" else "🚚 Yetkazish"
        else:
            order_type_text = "🏪 Самовывоз" if order_type == "pickup" else "🚚 Доставка"

        # Build message
        lines = [
            f"<b>{status_text}</b>",
            "━━━━━━━━━━━━━━━━━━",
            "",
            f"📦 #{order_id} │ {order_type_text}",
            "",
        ]

        # Customer info
        if customer_name or customer_phone:
            lines.append(f"👤 {_esc(customer_name or '-')}")
            if customer_phone:
                lines.append(f"📱 <code>{_esc(customer_phone)}</code>")

        # Delivery address (only for delivery)
        if order_type == "delivery" and delivery_address:
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
        order_type: Literal["pickup", "delivery"],
        delivery_address: str | None = None,
        payment_method: str = "cash",
        notify_customer: bool = True,
        notify_sellers: bool = True,
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

        if order_type == "delivery" and not delivery_address:
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

        # Create orders using appropriate method based on type
        if order_type == "pickup":
            # Use booking system for pickup
            result = await self._create_pickup_orders(user_id, db_items, payment_method)
        else:
            # Use order system for delivery
            result = await self._create_delivery_orders(
                user_id, db_items, delivery_address, payment_method
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
        delivery_price = items[0].delivery_price if order_type == "delivery" and items else 0
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

        # Send notifications to sellers
        if notify_sellers and stores_orders:
            await self._notify_sellers_new_order(
                stores_orders=stores_orders,
                order_type=order_type,
                delivery_address=delivery_address,
                payment_method=payment_method,
                customer_name=customer_name,
                customer_phone=customer_phone,
            )

        # Send notification to customer
        if notify_customer:
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

            try:
                await self.bot.send_message(user_id, customer_msg, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to notify customer {user_id}: {e}")

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
        """Create pickup orders using booking system."""
        try:
            # Use cart order creation for consistency
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
        self, user_id: int, items: list[dict], delivery_address: str, payment_method: str
    ) -> dict:
        """Create delivery orders."""
        try:
            result = self.db.create_cart_order(
                user_id=user_id,
                items=items,
                order_type="delivery",
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

                # Build notification
                order_ids = [str(o["order_id"]) for o in store_orders]
                pickup_codes = [o["pickup_code"] for o in store_orders if o.get("pickup_code")]

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

                await self.bot.send_message(
                    owner_id, seller_text, parse_mode="HTML", reply_markup=kb.as_markup()
                )
                logger.info(f"Sent order notification to seller {owner_id} for orders {order_ids}")

            except Exception as e:
                logger.error(f"Failed to notify seller for store {store_id}: {e}")

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
            # Get entity
            if entity_type == "order":
                entity = self.db.get_order(entity_id)
                update_func = self.db.update_order_status
                user_id_field = "user_id"
                store_id_field = "store_id"
                code_field = "pickup_code"
                order_type_field = "order_type"
            else:
                entity = self.db.get_booking(entity_id)
                update_func = self.db.update_booking_status
                user_id_field = "user_id"
                store_id_field = "store_id"
                code_field = "code"
                order_type_field = None  # Bookings are always pickup

            if not entity:
                logger.warning(f"Entity not found: {entity_type}#{entity_id}")
                return False

            # Get entity fields
            if isinstance(entity, dict):
                user_id = entity.get(user_id_field)
                store_id = entity.get(store_id_field)
                pickup_code = entity.get(code_field)
                # For orders, check delivery_address to determine type if order_type not set
                if order_type_field:
                    order_type = entity.get(order_type_field)
                    if not order_type:
                        # Fallback: if has delivery_address → delivery, else pickup
                        order_type = "delivery" if entity.get("delivery_address") else "pickup"
                else:
                    order_type = "pickup"  # Bookings are always pickup
            else:
                user_id = getattr(entity, user_id_field, None)
                store_id = getattr(entity, store_id_field, None)
                pickup_code = getattr(entity, code_field, None)
                if order_type_field:
                    order_type = getattr(entity, order_type_field, None)
                    if not order_type:
                        order_type = (
                            "delivery" if getattr(entity, "delivery_address", None) else "pickup"
                        )
                else:
                    order_type = "pickup"

            # Update status in DB
            update_func(entity_id, new_status)

            # Restore quantity if rejected or cancelled
            if new_status in [OrderStatus.REJECTED, OrderStatus.CANCELLED]:
                await self._restore_quantities(entity, entity_type)

            # Send notification to customer - SMART FILTERING
            # Skip redundant notifications to avoid spam:
            # - READY status for pickup (they already know it's being prepared)
            # - Only important statuses: PREPARING (accepted), DELIVERING, COMPLETED, REJECTED, CANCELLED
            should_notify = notify_customer and user_id

            # Skip READY notification for pickup - go directly from PREPARING to COMPLETED
            if order_type == "pickup" and new_status == OrderStatus.READY:
                should_notify = False

            if should_notify:
                store = self.db.get_store(store_id) if store_id else None
                store_name = store.get("name", "") if isinstance(store, dict) else ""
                store_address = store.get("address", "") if isinstance(store, dict) else ""

                customer_lang = self.db.get_user_language(user_id)
                msg = NotificationTemplates.customer_status_update(
                    lang=customer_lang,
                    order_id=entity_id,
                    status=new_status,
                    order_type=order_type,
                    store_name=store_name,
                    store_address=store_address,
                    pickup_code=pickup_code,
                    reject_reason=reject_reason,
                    courier_phone=courier_phone,
                )

                # Add buttons for customer based on status
                reply_markup = None
                if new_status == OrderStatus.COMPLETED:
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
                elif new_status == OrderStatus.DELIVERING and order_type == "delivery":
                    # "Received" button for delivery orders in transit
                    kb = InlineKeyboardBuilder()
                    received_text = "✅ Oldim" if customer_lang == "uz" else "✅ Получил"
                    kb.button(text=received_text, callback_data=f"customer_received_{entity_id}")
                    reply_markup = kb.as_markup()

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
                        f"Trying to edit message {existing_message_id} for {entity_type}#{entity_id}"
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
                        # Save message_id for future edits (only for first notification)
                        if message_sent and new_status == OrderStatus.PREPARING:
                            if entity_type == "order" and hasattr(
                                self.db, "set_order_customer_message_id"
                            ):
                                self.db.set_order_customer_message_id(
                                    entity_id, message_sent.message_id
                                )
                            elif entity_type == "booking" and hasattr(
                                self.db, "set_booking_customer_message_id"
                            ):
                                self.db.set_booking_customer_message_id(
                                    entity_id, message_sent.message_id
                                )
                    except Exception as e:
                        logger.error(f"Failed to notify customer {user_id}: {e}")

            logger.info(f"STATUS_UPDATE: {entity_type}#{entity_id} -> {new_status}")
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
