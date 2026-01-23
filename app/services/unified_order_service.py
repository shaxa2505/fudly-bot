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
import io
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from aiogram import Bot
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image

from app.core.notifications import Notification, NotificationType, get_notification_service
from app.services.notification_builder import NotificationBuilder
from app.services.notification_unified import build_unified_order_payload

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
                return "Olib ketish"
            if order_type == "taxi":
                return "Taksi"
            return "Yetkazib berish"
        if order_type == "pickup":
            return "Самовывоз"
        if order_type == "taxi":
            return "Такси"
        return "Доставка"


    @staticmethod
    def _payment_label(lang: str, payment_method: str) -> str:
        if lang == "uz":
            if payment_method == "cash":
                return "To'lov: naqd"
            if payment_method == "card":
                return "To'lov: kartaga o'tkazma"
            if payment_method == "click":
                return "To'lov: Click"
            if payment_method == "payme":
                return "To'lov: Payme"
            return "To'lov: onlayn"
        if payment_method == "cash":
            return "Оплата: наличными"
        if payment_method == "card":
            return "Оплата: перевод на карту"
        if payment_method == "click":
            return "Оплата: Click"
        if payment_method == "payme":
            return "Оплата: Payme"
        return "Оплата: онлайн"


    @staticmethod
    def admin_payment_review(
        lang: str,
        order_id: int,
        store_name: str,
        items_text: str,
        total_with_delivery: int,
        currency: str,
        address: str,
        customer_name: str,
        customer_phone: str,
    ) -> str:
        "Build admin caption for payment proof review."
        if lang == "uz":
            lines = [
                "<b>💳 To'lovni tasdiqlash</b>",
                "",
                f"Buyurtma: #{order_id} | {store_name}",
                f"Mahsulotlar:\\n{items_text}",
                f"Jami: {total_with_delivery:,} {currency}",
                f"Manzil: {address}",
                f"Mijoz: {customer_name}",
                f"Telefon: <code>{customer_phone}</code>",
            ]
        else:
            lines = [
                "<b>💳 Проверка оплаты</b>",
                "",
                f"Заказ: #{order_id} | {store_name}",
                f"Товары:\\n{items_text}",
                f"Итого: {total_with_delivery:,} {currency}",
                f"Адрес: {address}",
                f"Покупатель: {customer_name}",
                f"Телефон: <code>{customer_phone}</code>",
            ]
        return "\n".join(lines)


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
        "Build seller notification for new order."

        def _esc(val: Any) -> str:
            return html.escape(str(val)) if val else ""

        is_delivery = NotificationTemplates._is_delivery(order_type)
        order_type_text = NotificationTemplates._order_type_label(lang, order_type)

        if lang == "uz":
            display_name = (
                _esc(customer_name) if customer_name and customer_name.strip() else "Mijoz"
            )
            lines = [
                "<b>🧾 Yangi buyurtma</b>",
                f"Buyurtma: #{', #'.join(order_ids)}",
                f"Tur: {order_type_text}",
            ]

            if pickup_codes:
                lines.append(f"Kod: <b>{', '.join(pickup_codes)}</b>")

            lines.append("")
            lines.append(f"Mijoz: {display_name}")
            phone_value = _esc(customer_phone) if customer_phone else "Telefon yo'q"
            lines.append(f"Telefon: <code>{phone_value}</code>")

            if is_delivery and delivery_address:
                lines.append(f"Manzil: {_esc(delivery_address)}")

            lines.append("")
            lines.append("Mahsulotlar:")
            for item in items:
                item_title = item.get("title") or "Mahsulot"
                item_price = item.get("price") or 0
                item_qty = item.get("quantity") or 1
                subtotal = item_price * item_qty
                lines.append(
                    f"- {_esc(item_title)} × {item_qty} = {int(subtotal):,} {currency}"
                )

            lines.append("")
            grand_total = int(total + delivery_price) if is_delivery else int(total)
            if is_delivery:
                lines.append(f"Yetkazib berish: {int(delivery_price):,} {currency}")
            lines.append(f"<b>Jami: {grand_total:,} {currency}</b>")

            payment_text = NotificationTemplates._payment_label(lang, payment_method)
            lines.append(payment_text)
            lines.append("")
            lines.append("Buyurtmani tasdiqlang.")

        else:
            display_name = (
                _esc(customer_name)
                if customer_name and customer_name.strip()
                else "Клиент"
            )
            lines = [
                "<b>🧾 Новый заказ</b>",
                f"Заказ: #{', #'.join(order_ids)}",
                f"Тип: {order_type_text}",
            ]

            if pickup_codes:
                lines.append(
                    f"Код выдачи: <b>{', '.join(pickup_codes)}</b>"
                )

            lines.append("")
            lines.append(f"Клиент: {display_name}")
            phone_value = (
                _esc(customer_phone)
                if customer_phone
                else "Телефон не указан"
            )
            lines.append(f"Телефон: <code>{phone_value}</code>")

            if is_delivery and delivery_address:
                lines.append(f"Адрес: {_esc(delivery_address)}")

            lines.append("")
            lines.append("Состав:")
            for item in items:
                item_title = item.get("title") or "Товар"
                item_price = item.get("price") or 0
                item_qty = item.get("quantity") or 1
                subtotal = item_price * item_qty
                lines.append(
                    f"- {_esc(item_title)} × {item_qty} = {int(subtotal):,} {currency}"
                )

            lines.append("")
            grand_total = int(total + delivery_price) if is_delivery else int(total)
            if is_delivery:
                lines.append(
                    f"Доставка: {int(delivery_price):,} {currency}"
                )
            lines.append(f"<b>Итого: {grand_total:,} {currency}</b>")

            payment_text = NotificationTemplates._payment_label(lang, payment_method)
            lines.append(payment_text)
            lines.append("")
            lines.append("Подтвердите заказ.")

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
        "Build customer notification for order creation."

        def _esc(val: Any) -> str:
            return html.escape(str(val)) if val else ""

        is_delivery = NotificationTemplates._is_delivery(order_type)
        order_type_text = NotificationTemplates._order_type_label(lang, order_type)
        grand_total = int(total + delivery_price)

        if lang == "uz":
            header = (
                "<b>🧾 Buyurtma to'lov tekshiruvida</b>"
                if awaiting_payment and payment_method == "card"
                else "<b>🧾 Buyurtma yaratildi</b>"
            )

            lines = [
                header,
                f"Buyurtma: #{', #'.join(order_ids)} — {order_type_text}",
                f"Do'kon: {_esc(store_name)}",
            ]

            if order_type == "pickup":
                if store_address:
                    lines.append(f"Manzil: {_esc(store_address)}")
                if pickup_codes:
                    lines.append(f"Kod: <b>{', '.join(pickup_codes)}</b>")
            else:
                if delivery_address:
                    lines.append(f"Manzil: {_esc(delivery_address)}")

            lines.append("")
            lines.append("Mahsulotlar:")
            for item in items:
                subtotal = item["price"] * item["quantity"]
                lines.append(
                    f"- {_esc(item['title'])} × {item['quantity']} = {int(subtotal):,} {currency}"
                )

            lines.append("")
            if is_delivery:
                lines.append(f"Yetkazib berish: {int(delivery_price):,} {currency}")
            lines.append(f"<b>Jami: {grand_total:,} {currency}</b>")

            payment_text = NotificationTemplates._payment_label(lang, payment_method)
            lines.append(payment_text)

            lines.append("")
            lines.append("Do'kon tasdig'ini kuting (5-10 daqiqa)")

            if order_type == "pickup" and pickup_codes:
                lines.append("")
                lines.append("Kodini sotuvchiga ko'rsating")

        else:
            header = (
                "<b>🧾 Заказ на проверке оплаты</b>"
                if awaiting_payment and payment_method == "card"
                else "<b>🧾 Заказ создан</b>"
            )

            lines = [
                header,
                f"Заказ: #{', #'.join(order_ids)} — {order_type_text}",
                f"Магазин: {_esc(store_name)}",
            ]

            if order_type == "pickup":
                if store_address:
                    lines.append(f"Адрес: {_esc(store_address)}")
                if pickup_codes:
                    lines.append(f"Код выдачи: <b>{', '.join(pickup_codes)}</b>")
            else:
                if delivery_address:
                    lines.append(f"Адрес: {_esc(delivery_address)}")

            lines.append("")
            lines.append("Товары:")
            for item in items:
                subtotal = item["price"] * item["quantity"]
                lines.append(
                    f"- {_esc(item['title'])} × {item['quantity']} = {int(subtotal):,} {currency}"
                )

            lines.append("")
            if is_delivery:
                lines.append(f"Доставка: {int(delivery_price):,} {currency}")
            lines.append(f"<b>Итого: {grand_total:,} {currency}</b>")

            payment_text = NotificationTemplates._payment_label(lang, payment_method)
            lines.append(payment_text)

            lines.append("")
            lines.append("Ожидайте подтверждения магазина (5-10 мин)")

            if order_type == "pickup" and pickup_codes:
                lines.append("")
                lines.append("Код выдачи покажите продавцу")

        return "\n".join(lines)


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
    def customer_cart_status_update(
        lang: str,
        order_id: int | str,
        status: str,
        order_type: str,
        items: list[dict],
        currency: str,
        is_cart: bool = True,
        order_ids: list[int] | None = None,
        store_name: str | None = None,
        store_address: str | None = None,
        delivery_address: str | None = None,
        delivery_price: int = 0,
        pickup_code: str | None = None,
        reject_reason: str | None = None,
        courier_phone: str | None = None,
    ) -> str:
        """Build cart summary status message for customers."""

        def _esc(val: Any) -> str:
            return html.escape(str(val)) if val else ""

        normalized_type = "delivery" if order_type == "taxi" else order_type
        is_delivery = NotificationTemplates._is_delivery(normalized_type)
        type_label = NotificationTemplates._order_type_label(lang, normalized_type)

        status_labels = {
            "uz": {
                OrderStatus.PENDING: "Tasdiq kutilmoqda",
                OrderStatus.PREPARING: "Tayyorlanmoqda",
                OrderStatus.READY: "Tayyor",
                OrderStatus.DELIVERING: "Yo'lda",
                OrderStatus.COMPLETED: "Yetkazildi" if is_delivery else "Berildi",
                OrderStatus.REJECTED: "Rad etildi",
                OrderStatus.CANCELLED: "Bekor qilindi",
            },
            "ru": {
                OrderStatus.PENDING: "Ожидает подтверждения",
                OrderStatus.PREPARING: "Готовится",
                OrderStatus.READY: "Готово",
                OrderStatus.DELIVERING: "В пути",
                OrderStatus.COMPLETED: "Доставлено" if is_delivery else "Выдано",
                OrderStatus.REJECTED: "Отклонено",
                OrderStatus.CANCELLED: "Отменено",
            },
        }
        status_text = status_labels.get(lang, status_labels["ru"]).get(status, status)

        unique_ids = sorted({int(x) for x in (order_ids or []) if x})
        is_group = len(unique_ids) > 1

        title_label = "Buyurtma" if lang == "uz" else "Заказ"
        if is_group:
            header_label = "Savat" if lang == "uz" else "Корзина"
            header = f"🧾 {header_label} - {type_label}"
        else:
            header = f"🧾 {title_label} #{order_id} - {type_label}"

        status_label = "Holat" if lang == "uz" else "Статус"
        lines: list[str] = [
            header,
            f"{status_label}: {status_text}",
        ]

        if is_group:
            max_show = 5
            shown = unique_ids[:max_show]
            suffix = f" +{len(unique_ids) - max_show}" if len(unique_ids) > max_show else ""
            ids_text = ", ".join([f"#{oid}" for oid in shown]) + suffix
            label = "Buyurtmalar" if lang == "uz" else "Заказы"
            lines.append(f"{label}: {ids_text}")

        if store_name:
            store_label = "Do'kon" if lang == "uz" else "Магазин"
            lines.append(f"{store_label}: {_esc(store_name)}")

        if is_delivery:
            if delivery_address:
                addr_label = "Manzil" if lang == "uz" else "Адрес"
                lines.append(f"{addr_label}: {_esc(delivery_address)}")
            if courier_phone and status == OrderStatus.DELIVERING:
                courier_label = "Kuryer" if lang == "uz" else "Курьер"
                lines.append(f"{courier_label}: {_esc(courier_phone)}")
        else:
            if store_address:
                addr_label = "Manzil" if lang == "uz" else "Адрес"
                lines.append(f"{addr_label}: {_esc(store_address)}")
            if pickup_code:
                code_label = "Kod" if lang == "uz" else "Код"
                lines.append(f"{code_label}: <b>{_esc(pickup_code)}</b>")

        lines.append("")
        items_label = "Mahsulotlar" if lang == "uz" else "Товары"
        lines.append(f"{items_label}:")

        total = 0
        for item in items:
            title = _esc(item.get("title", ""))
            qty = int(item.get("quantity", 1))
            price = int(item.get("price", 0))
            subtotal = price * qty
            total += subtotal
            lines.append(f"- {title} × {qty} = {subtotal:,} {currency}")

        if is_delivery and delivery_price:
            total += int(delivery_price)
            delivery_label = "Yetkazish" if lang == "uz" else "Доставка"
            lines.append(f"{delivery_label}: {int(delivery_price):,} {currency}")

        total_label = "Jami" if lang == "uz" else "Итого"
        lines.append(f"{total_label}: <b>{int(total):,} {currency}</b>")

        if reject_reason and status in (OrderStatus.REJECTED, OrderStatus.CANCELLED):
            reason_label = "Sabab" if lang == "uz" else "Причина"
            lines.append(f"{reason_label}: {_esc(reject_reason)}")

        return "\n".join(lines)

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
        currency: str = "UZS",
    ) -> str:
        """Build seller notification with a clean status layout."""

        def _esc(val: Any) -> str:
            return html.escape(str(val)) if val else ""

        is_delivery = NotificationTemplates._is_delivery(order_type)
        type_label = NotificationTemplates._order_type_label(lang, order_type)

        status_labels = {
            "uz": {
                OrderStatus.PENDING: "Tasdiq kutilmoqda",
                OrderStatus.PREPARING: "Tayyorlanmoqda",
                OrderStatus.READY: "Tayyor",
                OrderStatus.DELIVERING: "Yo'lda",
                OrderStatus.COMPLETED: "Topshirildi" if is_delivery else "Berildi",
                OrderStatus.REJECTED: "Rad etildi",
                OrderStatus.CANCELLED: "Bekor qilindi",
            },
            "ru": {
                OrderStatus.PENDING: "Ожидает подтверждения",
                OrderStatus.PREPARING: "Готовится",
                OrderStatus.READY: "Готово",
                OrderStatus.DELIVERING: "В пути",
                OrderStatus.COMPLETED: "Доставлено" if is_delivery else "Выдано",
                OrderStatus.REJECTED: "Отклонено",
                OrderStatus.CANCELLED: "Отменено",
            },
        }
        status_text = status_labels.get(lang, status_labels["ru"]).get(status, status)

        title_label = "Buyurtma" if lang == "uz" else "Заказ"
        header = f"🧾 {title_label} #{order_id} - {type_label}"

        status_label = "Holat" if lang == "uz" else "Статус"
        lines: list[str] = [
            header,
            f"{status_label}: {status_text}",
        ]

        if customer_name:
            client_label = "Mijoz" if lang == "uz" else "Клиент"
            lines.append(f"{client_label}: {_esc(customer_name)}")
        if customer_phone:
            phone_label = "Telefon" if lang == "uz" else "Телефон"
            lines.append(f"{phone_label}: <code>{_esc(customer_phone)}</code>")

        if is_delivery and delivery_address:
            addr_label = "Manzil" if lang == "uz" else "Адрес"
            lines.append(f"{addr_label}: {_esc(delivery_address)}")

        items_total = 0
        if items:
            lines.append("")
            items_label = "Mahsulotlar" if lang == "uz" else "Товары"
            lines.append(f"{items_label}:")
            for item in items:
                title = _esc(item.get("title", ""))
                qty = int(item.get("quantity", 1))
                price = int(item.get("price", 0))
                subtotal = price * qty
                items_total += subtotal
                lines.append(f"- {title} × {qty} = {subtotal:,} {currency}")

        base_total = int(total or 0)
        if items_total > 0:
            base_total = items_total

        delivery_amount = int(delivery_price or 0)
        if is_delivery and delivery_amount:
            delivery_label = "Yetkazish" if lang == "uz" else "Доставка"
            lines.append(f"{delivery_label}: {delivery_amount:,} {currency}")

        total_label = "Jami" if lang == "uz" else "Итого"
        grand_total = base_total + (delivery_amount if is_delivery else 0)
        lines.append(f"{total_label}: <b>{grand_total:,} {currency}</b>")

        return "\n".join(lines)


class UnifiedOrderService:
    """Unified service for handling orders and bookings."""

    def __init__(self, db: Any, bot: Bot):
        self.db = db
        self.bot = bot
        self.telegram_order_notifications = os.getenv(
            "ORDER_TELEGRAM_NOTIFICATIONS", "false"
        ).strip().lower() in {"1", "true", "yes", "y"}
        self.force_telegram_sync = os.getenv("FORCE_TELEGRAM_SYNC", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }

    def _esc(self, val: Any) -> str:
        """HTML-escape helper."""
        return html.escape(str(val)) if val else ""

    def _notifications_enabled(self, user_id: int | None) -> bool:
        """Check if user notifications are enabled."""
        if not user_id:
            return False
        try:
            user = (
                self.db.get_user_model(user_id)
                if hasattr(self.db, "get_user_model")
                else self.db.get_user(user_id)
            )
            if isinstance(user, dict):
                return bool(user.get("notifications_enabled", True))
            return bool(getattr(user, "notifications_enabled", True))
        except Exception:
            return True

    # ------------------------------------------------------------------
    # Error normalization helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_creation_error(error: str | None, items: list[Any]) -> str:
        """Convert low-level DB error codes to user-friendly messages."""
        if not error:
            return "Failed to create order"

        err = str(error)
        if err.startswith("error:"):
            err = err[len("error:") :]
        lower = err.lower()

        def _lookup_title(offer_id: int | None) -> str | None:
            if offer_id is None:
                return None
            for item in items or []:
                try:
                    item_offer_id = getattr(item, "offer_id", None)
                    if item_offer_id is None and isinstance(item, dict):
                        item_offer_id = item.get("offer_id")
                    if item_offer_id is None:
                        continue
                    if int(item_offer_id) != int(offer_id):
                        continue
                except Exception:
                    continue
                if isinstance(item, dict):
                    return item.get("title")
                return getattr(item, "title", None)
            return None

        if "insufficient_stock" in lower:
            offer_id = None
            try:
                offer_id = int(err.split(":")[-1])
            except Exception:
                offer_id = None
            title = _lookup_title(offer_id)
            if title:
                return f"Insufficient stock for '{title}'"
            return "Insufficient stock for one of the items"

        if "offer_unavailable" in lower:
            offer_id = None
            try:
                offer_id = int(err.split(":")[-1])
            except Exception:
                offer_id = None
            title = _lookup_title(offer_id)
            if title:
                return f"Item is no longer available: '{title}'"
            return "Item is no longer available"

        return err

    def _get_offer_photo(self, offer_id: int | None) -> str | None:
        if not offer_id or not hasattr(self.db, "get_offer"):
            return None
        try:
            offer = self.db.get_offer(int(offer_id))
        except Exception:
            return None
        if isinstance(offer, dict):
            return offer.get("photo") or offer.get("photo_id")
        return getattr(offer, "photo", None) or getattr(offer, "photo_id", None)

    @staticmethod
    def _extract_photo_from_items(items: list[Any] | None) -> str | None:
        if not items:
            return None
        for item in items:
            if isinstance(item, dict):
                photo = (
                    item.get("photo")
                    or item.get("photo_id")
                    or item.get("offer_photo")
                    or item.get("offer_photo_id")
                )
            else:
                photo = getattr(item, "photo", None) or getattr(item, "photo_id", None)
            if photo:
                return str(photo)
        return None

    def _resolve_photo_from_items(
        self,
        items: list[Any] | None,
        offer_id: int | None = None,
    ) -> str | None:
        photo = self._extract_photo_from_items(items)
        if photo:
            return photo
        if items:
            for item in items:
                item_offer_id = None
                if isinstance(item, dict):
                    item_offer_id = item.get("offer_id")
                else:
                    item_offer_id = getattr(item, "offer_id", None)
                if item_offer_id:
                    try:
                        offer_id_int = int(item_offer_id)
                    except (TypeError, ValueError):
                        offer_id_int = None
                    photo = self._get_offer_photo(offer_id_int) if offer_id_int else None
                    if photo:
                        return photo
        return self._get_offer_photo(offer_id)

    def _collect_photos_from_items(
        self,
        items: list[Any] | None,
        limit: int = 4,
    ) -> list[str]:
        if not items or limit <= 0:
            return []

        photos: list[str] = []
        seen: set[str] = set()

        def _add(photo: Any) -> None:
            if not photo:
                return
            photo_str = str(photo)
            if photo_str in seen:
                return
            seen.add(photo_str)
            photos.append(photo_str)

        for item in items:
            if isinstance(item, dict):
                _add(
                    item.get("photo")
                    or item.get("photo_id")
                    or item.get("offer_photo")
                    or item.get("offer_photo_id")
                )
            else:
                _add(getattr(item, "photo", None) or getattr(item, "photo_id", None))
            if len(photos) >= limit:
                return photos

        for item in items:
            if len(photos) >= limit:
                break
            if isinstance(item, dict):
                item_offer_id = item.get("offer_id")
            else:
                item_offer_id = getattr(item, "offer_id", None)
            if item_offer_id is None:
                continue
            try:
                offer_id_int = int(item_offer_id)
            except (TypeError, ValueError):
                continue
            _add(self._get_offer_photo(offer_id_int))
        return photos

    async def _build_collage_photo(
        self,
        photo_ids: list[str],
        tile_size: int = 512,
    ) -> BufferedInputFile | None:
        if len(photo_ids) < 2 or tile_size <= 0:
            return None

        selected = [pid for pid in photo_ids if pid][:4]
        images: list[Image.Image] = []

        for photo_id in selected:
            try:
                file = await self.bot.get_file(photo_id)
                file_content = await self.bot.download_file(file.file_path)
                data = file_content.read()
            except Exception as download_error:
                logger.warning(f"Failed to download collage photo: {download_error}")
                continue

            try:
                img = Image.open(io.BytesIO(data))
                img = img.convert("RGB")
                width, height = img.size
                if width <= 0 or height <= 0:
                    continue
                min_side = min(width, height)
                left = (width - min_side) // 2
                top = (height - min_side) // 2
                img = img.crop((left, top, left + min_side, top + min_side))
                img = img.resize((tile_size, tile_size), Image.LANCZOS)
                images.append(img)
            except Exception as image_error:
                logger.warning(f"Failed to process collage photo: {image_error}")

        if len(images) < 2:
            return None

        if len(images) == 2:
            canvas = Image.new("RGB", (tile_size * 2, tile_size), "white")
            positions = [(0, 0), (tile_size, 0)]
        else:
            canvas = Image.new("RGB", (tile_size * 2, tile_size * 2), "white")
            positions = [
                (0, 0),
                (tile_size, 0),
                (0, tile_size),
                (tile_size, tile_size),
            ]

        for img, pos in zip(images, positions):
            canvas.paste(img, pos)

        buf = io.BytesIO()
        canvas.save(buf, format="JPEG", quality=85, optimize=True)
        return BufferedInputFile(buf.getvalue(), filename="order_collage.jpg")

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
        payment_proof: str | None = None,
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
        if any(int(getattr(item, "quantity", 0) or 0) <= 0 for item in items):
            return OrderResult(
                success=False,
                order_ids=[],
                booking_ids=[],
                pickup_codes=[],
                total_items=0,
                total_price=0,
                delivery_price=0,
                grand_total=0,
                error_message="Invalid item quantity",
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
        if is_delivery and payment_method == "cash":
            return OrderResult(
                success=False,
                order_ids=[],
                booking_ids=[],
                pickup_codes=[],
                total_items=0,
                total_price=0,
                delivery_price=0,
                grand_total=0,
                error_message="Cash is not allowed for delivery orders",
            )
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
            payment_proof_photo_id=payment_proof,
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
            error_msg = result.get("error", "Failed to create orders")
            friendly_error = self._normalize_creation_error(error_msg, items)
            return OrderResult(
                success=False,
                order_ids=[],
                booking_ids=[],
                pickup_codes=[],
                total_items=0,
                total_price=0,
                delivery_price=0,
                grand_total=0,
                error_message=friendly_error,
                failed_items=result.get("failed_items"),
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

        if (
            is_delivery
            and payment_proof
            and order_ids
            and hasattr(self.db, "update_payment_status")
        ):
            for oid in order_ids:
                try:
                    self.db.update_payment_status(
                        int(oid), PaymentStatus.PROOF_SUBMITTED, str(payment_proof)
                    )
                except Exception as proof_err:
                    logger.warning(f"Failed to save payment proof for order {oid}: {proof_err}")

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
            self.telegram_order_notifications if telegram_notify is None else telegram_notify
        )
        notifications_enabled = self._notifications_enabled(user_id)
        customer_notifications = bool(notify_customer and notifications_enabled)

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
        publish_customer_event = bool(user_id) and notifications_enabled
        if customer_notifications or publish_customer_event:
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

            primary_offer_id = items[0].offer_id if items else None
            photo_ids = self._collect_photos_from_items(items)
            customer_photo = None
            if len(photo_ids) > 1:
                customer_photo = await self._build_collage_photo(photo_ids)
            if not customer_photo and photo_ids:
                customer_photo = photo_ids[0]
            if not customer_photo and primary_offer_id:
                customer_photo = self._get_offer_photo(primary_offer_id)

            entity_ids_raw = [x for x in (order_ids + booking_ids) if x]
            entity_ids = [int(x) for x in entity_ids_raw]
            entity_id = entity_ids[0] if entity_ids else None
            entity_type = "order" if order_ids else "booking"
            store_id = items[0].store_id if items else None
            store_name = items[0].store_name if items else ""
            store_address = items[0].store_address if items else ""
            customer_payload = {"id": int(user_id)} if user_id else None
            if customer_payload is not None:
                customer_payload["name"] = customer_name or ""
                customer_payload["phone"] = customer_phone or ""
            amounts_payload = {
                "subtotal": int(total_price or 0),
                "delivery_fee": int(delivery_price or 0),
                "total": int(total_price or 0) + int(delivery_price or 0),
                "currency": currency,
            }
            unified_payload = build_unified_order_payload(
                kind="order_created",
                role="customer",
                entity_type=entity_type,
                entity_id=entity_id,
                entity_ids=entity_ids,
                is_cart=len(entity_ids) > 1,
                order_type=order_type,
                status=OrderStatus.PENDING,
                payment_status=PaymentStatus.initial_for_method(payment_method),
                pickup_code=pickup_codes[0] if len(pickup_codes) == 1 else None,
                delivery_address=delivery_address,
                store={
                    "id": int(store_id) if store_id is not None else None,
                    "name": store_name,
                    "address": store_address,
                },
                customer=customer_payload,
                items=items_for_template,
                amounts=amounts_payload,
            )

            sent_msg = None
            if customer_notifications and telegram_enabled:
                try:
                    if customer_photo:
                        try:
                            sent_msg = await self.bot.send_photo(
                                user_id,
                                photo=customer_photo,
                                caption=customer_msg,
                                parse_mode="HTML",
                            )
                        except Exception as photo_err:
                            logger.warning(
                                f"Failed to send customer photo for {user_id}: {photo_err}"
                            )
                    if not sent_msg:
                        sent_msg = await self.bot.send_message(
                            user_id, customer_msg, parse_mode="HTML"
                        )
                except Exception as e:
                    logger.error(f"Failed to notify customer {user_id}: {e}")

            if sent_msg:
                total_entities = len(order_ids) + len(booking_ids)
                if total_entities == 1:
                    if order_ids and hasattr(self.db, "set_order_customer_message_id"):
                        try:
                            self.db.set_order_customer_message_id(
                                int(order_ids[0]), sent_msg.message_id
                            )
                            logger.info(
                                "Saved customer_message_id=%s for order#%s",
                                sent_msg.message_id,
                                order_ids[0],
                            )
                        except Exception as save_err:
                            logger.warning(
                                "Failed to save customer_message_id for order %s: %s",
                                order_ids[0],
                                save_err,
                            )
                    elif booking_ids and hasattr(
                        self.db, "set_booking_customer_message_id"
                    ):
                        try:
                            self.db.set_booking_customer_message_id(
                                int(booking_ids[0]), sent_msg.message_id
                            )
                            logger.info(
                                "Saved customer_message_id=%s for booking#%s",
                                sent_msg.message_id,
                                booking_ids[0],
                            )
                        except Exception as save_err:
                            logger.warning(
                                "Failed to save customer_message_id for booking %s: %s",
                                booking_ids[0],
                                save_err,
                            )
                else:
                    # Cart/legacy multi-order: attach the same message_id to all entities
                    if order_ids and hasattr(self.db, "set_order_customer_message_id"):
                        for order_id in order_ids:
                            try:
                                self.db.set_order_customer_message_id(
                                    int(order_id), sent_msg.message_id
                                )
                            except Exception as save_err:
                                logger.warning(
                                    "Failed to save customer_message_id for order %s: %s",
                                    order_id,
                                    save_err,
                                )
                    if booking_ids and hasattr(self.db, "set_booking_customer_message_id"):
                        for booking_id in booking_ids:
                            try:
                                self.db.set_booking_customer_message_id(
                                    int(booking_id), sent_msg.message_id
                                )
                            except Exception as save_err:
                                logger.warning(
                                    "Failed to save customer_message_id for booking %s: %s",
                                    booking_id,
                                    save_err,
                                )
                    logger.info(
                        "Saved shared customer_message_id=%s for user %s: order_ids=%s booking_ids=%s",
                        sent_msg.message_id,
                        user_id,
                        order_ids,
                        booking_ids,
                    )

            if publish_customer_event:
                try:
                    notification_service = get_notification_service()
                    title = "Buyurtma qabul qilindi" if customer_lang == "uz" else "Заказ принят"
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
                                "unified": unified_payload,
                            },
                            priority=0,
                        )
                    )
                except Exception as notify_error:
                    logger.warning(f"Notification service failed for order create: {notify_error}")

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
                                "unified": unified_payload,
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
                return {
                    "success": False,
                    "error": "No orders created",
                    "failed_items": result.get("failed_items"),
                }

            return {
                "success": True,
                "order_ids": [o.get("order_id") for o in created_orders if o.get("order_id")],
                "booking_ids": [],
                "pickup_codes": [
                    o.get("pickup_code") for o in created_orders if o.get("pickup_code")
                ],
                "stores_orders": result.get("stores_orders", {}),
                "failed_items": result.get("failed_items"),
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
                return {
                    "success": False,
                    "error": "No orders created",
                    "failed_items": result.get("failed_items"),
                }

            return {
                "success": True,
                "order_ids": [o.get("order_id") for o in created_orders if o.get("order_id")],
                "booking_ids": [],
                "pickup_codes": [
                    o.get("pickup_code") for o in created_orders if o.get("pickup_code")
                ],
                "stores_orders": result.get("stores_orders", {}),
                "failed_items": result.get("failed_items"),
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
            self.telegram_order_notifications if send_telegram is None else send_telegram
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
                primary_offer_id = store_orders[0].get("offer_id") if store_orders else None
                photo_ids = self._collect_photos_from_items(store_orders)
                seller_photo = None
                if len(photo_ids) > 1:
                    seller_photo = await self._build_collage_photo(photo_ids)
                if not seller_photo and photo_ids:
                    seller_photo = photo_ids[0]
                if not seller_photo and primary_offer_id:
                    try:
                        seller_photo = self._get_offer_photo(int(primary_offer_id))
                    except (TypeError, ValueError):
                        seller_photo = None
                store_payload = {
                    "id": int(store_id),
                    "name": store.get("name", "") if isinstance(store, dict) else "",
                    "address": store.get("address", "") if isinstance(store, dict) else "",
                }
                customer_payload = {"name": customer_name or "", "phone": customer_phone or ""}
                amounts_payload = {
                    "subtotal": int(store_total or 0),
                    "delivery_fee": int(store_delivery or 0),
                    "total": int(store_total or 0) + int(store_delivery or 0),
                    "currency": currency,
                }
                unified_payload = build_unified_order_payload(
                    kind="order_created",
                    role="partner",
                    entity_type="order",
                    entity_id=order_id_ints[0] if order_id_ints else None,
                    entity_ids=order_id_ints,
                    is_cart=len(order_id_ints) > 1,
                    order_type=order_type,
                    status=OrderStatus.PENDING,
                    pickup_code=pickup_codes[0] if len(pickup_codes) == 1 else None,
                    delivery_address=delivery_address,
                    store=store_payload,
                    customer=customer_payload,
                    items=store_orders,
                    amounts=amounts_payload,
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
                    if seller_photo:
                        try:
                            sent_msg = await self.bot.send_photo(
                                owner_id,
                                photo=seller_photo,
                                caption=seller_text,
                                parse_mode="HTML",
                                reply_markup=kb.as_markup(),
                            )
                        except Exception as photo_err:
                            logger.warning(
                                f"Failed to send seller photo to {owner_id}: {photo_err}"
                            )
                    if not sent_msg:
                        sent_msg = await self.bot.send_message(
                            owner_id,
                            seller_text,
                            parse_mode="HTML",
                            reply_markup=kb.as_markup(),
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
                    title = "Yangi buyurtma" if seller_lang == "uz" else "Новый заказ"
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
                                "unified": unified_payload,
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
                                "price": o.get("price", 0),
                            }
                            for o in store_orders
                        ],
                        "delivery_address": delivery_address,
                        "timestamp": str(datetime.now()),
                        "unified": unified_payload,
                    }

                    sent = await manager.notify_new_order(store_id, order_data)
                    if sent > 0:
                        logger.info(
                            f"📤 Sent WebSocket notification to {sent} web panels for store {store_id}"
                        )

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

            if str(current_status or "").lower() in ("cancelled", "rejected"):
                return False

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
                offer_photo = None
                if isinstance(offer, dict):
                    offer_photo = offer.get("photo") or offer.get("photo_id")
                else:
                    offer_photo = getattr(offer, "photo", None) if offer else None
                    if not offer_photo:
                        offer_photo = getattr(offer, "photo_id", None) if offer else None
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
                        "photo": offer_photo,
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
            payment_method = None
            payment_status = None
            delivery_address = None
            delivery_price = 0
            cart_items_json = None
            is_cart = False
            offer_id = None
            quantity = 1
            total_price = None
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
                    is_cart = int(entity.get("is_cart_booking") or 0) == 1
                    cart_items_json = entity.get("cart_items")
                    offer_id = entity.get("offer_id")
                    quantity = int(entity.get("quantity") or 1)
                else:
                    user_id = getattr(entity, "user_id", None)
                    store_id = getattr(entity, "store_id", None)
                    pickup_code = getattr(entity, "booking_code", None) or getattr(
                        entity, "pickup_code", None
                    )
                    current_status_raw = getattr(entity, "status", None) or getattr(
                        entity, "order_status", None
                    )
                    is_cart = int(getattr(entity, "is_cart_booking", 0) or 0) == 1
                    cart_items_json = getattr(entity, "cart_items", None)
                    offer_id = getattr(entity, "offer_id", None)
                    quantity = int(getattr(entity, "quantity", 1) or 1)

                order_type = "pickup"
            else:
                if isinstance(entity, dict):
                    user_id = entity.get("user_id")
                    store_id = entity.get("store_id")
                    pickup_code = entity.get("pickup_code")
                    current_status_raw = entity.get("order_status")
                    order_type = entity.get("order_type")
                    payment_method = entity.get("payment_method")
                    payment_status = entity.get("payment_status")
                    delivery_address = entity.get("delivery_address")
                    delivery_price = int(entity.get("delivery_price") or 0)
                    is_cart = int(entity.get("is_cart_order") or 0) == 1
                    cart_items_json = entity.get("cart_items")
                    offer_id = entity.get("offer_id")
                    quantity = int(entity.get("quantity") or 1)
                    total_price = entity.get("total_price")

                    # Fallback: if order_type not set, determine from delivery_address
                    if not order_type:
                        order_type = "delivery" if delivery_address else "pickup"
                        logger.info(
                            f"Order type fallback for #{entity_id}: "
                            f"delivery_address={delivery_address}, order_type={order_type}"
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
                    payment_status = getattr(entity, "payment_status", None)
                    delivery_address = getattr(entity, "delivery_address", None)
                    delivery_price = int(getattr(entity, "delivery_price", 0) or 0)
                    is_cart = int(getattr(entity, "is_cart_order", 0) or 0) == 1
                    cart_items_json = getattr(entity, "cart_items", None)
                    offer_id = getattr(entity, "offer_id", None)
                    quantity = int(getattr(entity, "quantity", 1) or 1)
                    total_price = getattr(entity, "total_price", None)
                    if not order_type:
                        order_type = "delivery" if delivery_address else "pickup"

            # Normalize statuses and enforce safe transitions/idempotence
            current_status = (
                OrderStatus.normalize(str(current_status_raw)) if current_status_raw else None
            )
            target_status = OrderStatus.normalize(str(new_status))
            normalized_payment_method = PaymentStatus.normalize_method(payment_method)
            normalized_payment_status = PaymentStatus.normalize(
                payment_status, payment_method=payment_method
            )
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
            update_ok = True
            if target_status in [OrderStatus.REJECTED, OrderStatus.CANCELLED]:
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        if entity_type == "booking":
                            if current_status_raw is not None:
                                cursor.execute(
                                    "UPDATE bookings SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE booking_id = %s AND status = %s",
                                    (target_status, entity_id, current_status_raw),
                                )
                            else:
                                cursor.execute(
                                    "UPDATE bookings SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE booking_id = %s",
                                    (target_status, entity_id),
                                )
                        else:
                            if current_status_raw is not None:
                                cursor.execute(
                                    "UPDATE orders SET order_status = %s, updated_at = CURRENT_TIMESTAMP WHERE order_id = %s AND order_status = %s",
                                    (target_status, entity_id, current_status_raw),
                                )
                            else:
                                cursor.execute(
                                    "UPDATE orders SET order_status = %s, updated_at = CURRENT_TIMESTAMP WHERE order_id = %s",
                                    (target_status, entity_id),
                                )
                        update_ok = cursor.rowcount > 0
                except Exception as e:
                    logger.error(f"Failed to update status atomically: {e}")
                    return False

                if not update_ok:
                    latest = (
                        self.db.get_booking(entity_id)
                        if entity_type == "booking"
                        else self.db.get_order(entity_id)
                    )
                    latest_status_raw = None
                    if isinstance(latest, dict):
                        latest_status_raw = (
                            latest.get("status")
                            if entity_type == "booking"
                            else latest.get("order_status")
                        )
                    else:
                        latest_status_raw = getattr(latest, "status", None) if entity_type == "booking" else getattr(latest, "order_status", None)

                    latest_status = (
                        OrderStatus.normalize(str(latest_status_raw))
                        if latest_status_raw
                        else None
                    )
                    if latest_status in terminal_statuses:
                        logger.info(
                            f"STATUS_UPDATE skipped due to race: #{entity_id} status={latest_status}"
                        )
                        return True
                    return False
            else:
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
                if update_ok:
                    await self._restore_quantities(entity, entity_type)
            # Send notification to customer - SMART FILTERING
            # Skip redundant notifications to avoid spam:
            # - READY status (internal state, customer doesn't need notification)
            # - Only important statuses: PREPARING (accepted), DELIVERING, COMPLETED, REJECTED, CANCELLED
            notifications_enabled = self._notifications_enabled(user_id)
            should_notify = notify_customer and user_id and notifications_enabled
            existing_message_id = None
            if isinstance(entity, dict):
                existing_message_id = entity.get("customer_message_id")
            else:
                existing_message_id = getattr(entity, "customer_message_id", None)
            should_edit = bool(existing_message_id) and user_id and notifications_enabled
            should_force_send = (
                self.force_telegram_sync and user_id and not existing_message_id and notifications_enabled
            )

            logger.info(
                f"Notification check for #{entity_id}: "
                f"status={target_status}, order_type={order_type}, "
                f"notify_customer={notify_customer}, user_id={user_id}, "
                f"should_notify={should_notify}, should_edit={should_edit}, "
                f"should_force_send={should_force_send}"
            )

            # OPTIMIZATION: Skip READY notification for delivery orders only
            # READY is mostly internal for delivery (courier pickup), but it's important for pickup
            if target_status == OrderStatus.READY and order_type in ("delivery", "taxi"):
                should_notify = False
                should_edit = False
                should_force_send = False
                logger.info(
                    f"Skipping READY notification for delivery order#{entity_id}"
                )

            if user_id:
                try:
                    from app.core.websocket import get_websocket_manager

                    customer_unified_min = build_unified_order_payload(
                        kind="order_status_changed",
                        role="customer",
                        entity_type=entity_type,
                        entity_id=entity_id,
                        entity_ids=[entity_id],
                        is_cart=is_cart,
                        order_type=order_type,
                        status=target_status,
                        payment_status=normalized_payment_status,
                        pickup_code=pickup_code,
                        delivery_address=delivery_address,
                        store={"id": int(store_id)} if store_id else None,
                        customer={"id": int(user_id)} if user_id else None,
                        courier={"phone": courier_phone} if courier_phone else None,
                        amounts={"delivery_fee": int(delivery_price or 0)},
                    )
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
                                "unified": customer_unified_min,
                            },
                        },
                    )
                except Exception as ws_error:
                    logger.warning(f"WebSocket notify failed for status change: {ws_error}")

            if store_id:
                partner_unified_min = build_unified_order_payload(
                    kind="order_status_changed",
                    role="partner",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    entity_ids=[entity_id],
                    is_cart=is_cart,
                    order_type=order_type,
                    status=target_status,
                    payment_status=normalized_payment_status,
                    pickup_code=pickup_code,
                    delivery_address=delivery_address,
                    store={"id": int(store_id)},
                    customer={"id": int(user_id)} if user_id else None,
                    courier={"phone": courier_phone} if courier_phone else None,
                    amounts={"delivery_fee": int(delivery_price or 0)},
                )
                try:
                    from app.api.websocket_manager import get_connection_manager

                    store_ws = get_connection_manager()
                    await store_ws.notify_order_status(
                        int(store_id),
                        int(entity_id),
                        target_status,
                        unified=partner_unified_min,
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
                                "unified": partner_unified_min,
                            },
                            priority=0,
                        )
                    )
                except Exception as notify_error:
                    logger.warning(f"Store status notification failed: {notify_error}")

            if should_notify or should_edit or should_force_send:
                store = self.db.get_store(store_id) if store_id else None
                store_name = store.get("name", "") if isinstance(store, dict) else ""
                store_address = store.get("address", "") if isinstance(store, dict) else ""

                customer_lang = self.db.get_user_language(user_id)
                currency = None
                cart_items = None
                if is_cart and cart_items_json:
                    try:
                        import json

                        cart_items = (
                            json.loads(cart_items_json)
                            if isinstance(cart_items_json, str)
                            else cart_items_json
                        )
                    except Exception:
                        cart_items = None

                if not cart_items and offer_id:
                    item_title = ""
                    item_price = None
                    if hasattr(self.db, "get_offer"):
                        offer = self.db.get_offer(int(offer_id))
                        if isinstance(offer, dict):
                            item_title = offer.get("title", "")
                            item_price = offer.get("discount_price", None)
                        else:
                            item_title = getattr(offer, "title", "") if offer else ""
                            item_price = getattr(offer, "discount_price", None) if offer else None

                    if not item_title:
                        item_title = "Mahsulot" if customer_lang == "uz" else "Товар"

                    if item_price is None and total_price is not None and quantity:
                        try:
                            item_price = int((float(total_price) - float(delivery_price)) / quantity)
                        except Exception:
                            item_price = 0

                    cart_items = [
                        {
                            "title": item_title,
                            "quantity": int(quantity or 1),
                            "price": int(item_price or 0),
                        }
                    ]

                photo_ids = self._collect_photos_from_items(cart_items)
                customer_photo = None
                if len(photo_ids) > 1:
                    customer_photo = await self._build_collage_photo(photo_ids)
                if not customer_photo and photo_ids:
                    customer_photo = photo_ids[0]
                if not customer_photo and offer_id:
                    try:
                        customer_photo = self._get_offer_photo(int(offer_id))
                    except (TypeError, ValueError):
                        customer_photo = None

                group_order_ids = None
                group_statuses: list[str] | None = None
                orders_for_group = None
                if entity_type == "order" and existing_message_id:
                    if hasattr(self.db, "get_orders_by_customer_message_id"):
                        try:
                            orders_for_group = self.db.get_orders_by_customer_message_id(
                                int(existing_message_id)
                            )
                        except Exception as group_err:
                            logger.debug(f"Failed to load grouped orders: {group_err}")
                    elif user_id and hasattr(self.db, "get_user_orders"):
                        try:
                            orders_for_group = self.db.get_user_orders(int(user_id)) or []
                        except Exception as group_err:
                            logger.debug(f"Failed to load grouped orders: {group_err}")

                if orders_for_group:
                    try:
                        grouped_ids: list[int] = []
                        grouped_statuses: list[str] = []
                        for order in orders_for_group:
                            if not isinstance(order, dict):
                                continue
                            if order.get("customer_message_id") != existing_message_id:
                                continue
                            oid = order.get("order_id") or order.get("id")
                            if oid is not None:
                                grouped_ids.append(int(oid))
                            raw_status = order.get("order_status") or order.get("status")
                            if raw_status:
                                grouped_statuses.append(
                                    OrderStatus.normalize(str(raw_status))
                                )
                        if grouped_ids:
                            group_order_ids = grouped_ids
                        if grouped_statuses:
                            group_statuses = grouped_statuses
                    except Exception as group_err:
                        logger.debug(f"Failed to load grouped order ids: {group_err}")

                is_grouped = False
                aggregated_status = target_status
                if cart_items:
                    currency = "so'm" if customer_lang == "uz" else "сум"
                    is_grouped = bool(group_order_ids and len(group_order_ids) > 1)
                    if is_grouped and group_statuses:
                        unique_statuses = set(group_statuses)
                        if unique_statuses == {OrderStatus.COMPLETED}:
                            aggregated_status = OrderStatus.COMPLETED
                        elif OrderStatus.REJECTED in unique_statuses:
                            aggregated_status = OrderStatus.REJECTED
                        elif OrderStatus.CANCELLED in unique_statuses:
                            aggregated_status = OrderStatus.CANCELLED
                        elif OrderStatus.DELIVERING in unique_statuses:
                            aggregated_status = OrderStatus.DELIVERING
                        elif OrderStatus.READY in unique_statuses:
                            aggregated_status = OrderStatus.READY
                        elif OrderStatus.PREPARING in unique_statuses:
                            aggregated_status = OrderStatus.PREPARING
                        elif OrderStatus.PENDING in unique_statuses:
                            aggregated_status = OrderStatus.PENDING

                    msg = NotificationTemplates.customer_cart_status_update(
                        lang=customer_lang,
                        order_id=entity_id,
                        status=aggregated_status,
                        order_type=order_type,
                        items=cart_items,
                        currency=currency,
                        is_cart=is_cart or is_grouped,
                        order_ids=group_order_ids,
                        store_name=store_name,
                        store_address=store_address,
                        delivery_address=delivery_address,
                        delivery_price=delivery_price,
                        pickup_code=pickup_code,
                        reject_reason=reject_reason,
                        courier_phone=courier_phone,
                    )
                else:
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

                amounts_payload = {"delivery_fee": int(delivery_price or 0)}
                if total_price is not None:
                    amounts_payload["subtotal"] = int(total_price or 0)
                    amounts_payload["total"] = int(total_price or 0) + int(delivery_price or 0)
                if currency:
                    amounts_payload["currency"] = currency

                customer_unified_full = build_unified_order_payload(
                    kind="order_status_changed",
                    role="customer",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    entity_ids=group_order_ids or [entity_id],
                    is_cart=is_cart or is_grouped,
                    order_type=order_type,
                    status=aggregated_status,
                    payment_status=normalized_payment_status,
                    pickup_code=pickup_code,
                    delivery_address=delivery_address,
                    store={
                        "id": int(store_id) if store_id else None,
                        "name": store_name,
                        "address": store_address,
                    },
                    customer={"id": int(user_id)} if user_id else None,
                    courier={"phone": courier_phone} if courier_phone else None,
                    items=cart_items,
                    amounts=amounts_payload,
                )

                if should_notify:


                    try:
                        notif_title = (
                            f"Buyurtma #{entity_id}" if customer_lang == "uz" else f"Заказ #{entity_id}"
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
                                    "unified": customer_unified_full,
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
                elif target_status == OrderStatus.READY and order_type == "pickup":
                    # "Received" button for pickup orders when ready
                    # v24+: all orders in unified table, use customer_received_
                    kb = InlineKeyboardBuilder()
                    received_text = "✅ Oldim" if customer_lang == "uz" else "✅ Получил"
                    kb.button(text=received_text, callback_data=f"customer_received_{entity_id}")
                    reply_markup = kb.as_markup()
                # Try to EDIT existing message first (live status update)
                # This reduces spam - customer sees ONE message that updates
                allow_telegram_updates = (
                    self.telegram_order_notifications or should_edit or should_force_send
                )

                if allow_telegram_updates:
                    message_sent = None
                    edit_success = False

                    if should_edit and existing_message_id:
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
                            logger.info(f"Edited CAPTION for {entity_type}#{entity_id}")
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
                                logger.info(f"Edited TEXT for {entity_type}#{entity_id}")
                            except Exception as text_error:
                                logger.warning(
                                    "Both edit methods failed for {}#{}: caption={}, text={}".format(
                                        entity_type,
                                        entity_id,
                                        caption_error,
                                        text_error,
                                    )
                                )

                    if not edit_success and (
                        should_force_send
                        or (self.telegram_order_notifications and should_notify)
                    ):
                        # Send new message only if edit failed or no existing message
                        try:
                            if customer_photo:
                                try:
                                    message_sent = await self.bot.send_photo(
                                        user_id,
                                        photo=customer_photo,
                                        caption=msg,
                                        parse_mode="HTML",
                                        reply_markup=reply_markup,
                                    )
                                except Exception as photo_err:
                                    logger.warning(
                                        f"Failed to send status photo to customer {user_id}: {photo_err}"
                                    )
                            if not message_sent:
                                message_sent = await self.bot.send_message(
                                    user_id, msg, parse_mode="HTML", reply_markup=reply_markup
                                )
                            logger.info(f"Sent NEW message for {entity_type}#{entity_id}")
                            # Save message_id for future edits - ALWAYS save to maintain live update chain
                            if message_sent:
                                if entity_type == "order" and hasattr(
                                    self.db, "set_order_customer_message_id"
                                ):
                                    self.db.set_order_customer_message_id(
                                        entity_id, message_sent.message_id
                                    )
                                    logger.info(
                                        "Saved message_id={} for order#{}".format(
                                            message_sent.message_id, entity_id
                                        )
                                    )
                                elif entity_type == "booking" and hasattr(
                                    self.db, "set_booking_customer_message_id"
                                ):
                                    self.db.set_booking_customer_message_id(
                                        entity_id, message_sent.message_id
                                    )
                                    logger.info(
                                        "Saved message_id={} for booking#{}".format(
                                            message_sent.message_id, entity_id
                                        )
                                    )
                        except Exception as e:
                            logger.error(f"Failed to notify customer {user_id}: {e}")

            # Update seller message in Telegram if it exists (partner bot sync) if it exists (partner bot sync)
            if entity_type == "order":
                try:
                    seller_message_id = (
                        entity.get("seller_message_id")
                        if isinstance(entity, dict)
                        else getattr(entity, "seller_message_id", None)
                    )
                    if store_id:
                        store = self.db.get_store(store_id) if store_id else None
                        owner_id = store.get("owner_id") if isinstance(store, dict) else None
                        if owner_id and (seller_message_id or self.force_telegram_sync):
                            seller_lang = self.db.get_user_language(owner_id)
                            currency = "so'm" if seller_lang == "uz" else "sum"

                            customer_name = None
                            customer_phone = None
                            if user_id:
                                customer = (
                                    self.db.get_user_model(user_id)
                                    if hasattr(self.db, "get_user_model")
                                    else self.db.get_user(user_id)
                                    if hasattr(self.db, "get_user")
                                    else None
                                )
                                if isinstance(customer, dict):
                                    customer_name = customer.get("first_name") or customer.get("name")
                                    customer_phone = customer.get("phone")
                                else:
                                    customer_name = getattr(customer, "first_name", None) if customer else None
                                    customer_phone = getattr(customer, "phone", None) if customer else None

                            resolved_order_type = order_type or (
                                "delivery" if delivery_address else "pickup"
                            )

                            items: list[dict] = []
                            total = 0

                            cart_items_json = (
                                entity.get("cart_items")
                                if isinstance(entity, dict)
                                else getattr(entity, "cart_items", None)
                            )
                            if cart_items_json:
                                try:
                                    import json

                                    cart_items = (
                                        json.loads(cart_items_json)
                                        if isinstance(cart_items_json, str)
                                        else cart_items_json
                                    )
                                    for item in cart_items or []:
                                        qty = int(item.get("quantity", 1))
                                        price = int(item.get("price", 0))
                                        title = item.get("title", "")
                                        item_offer_id = item.get("offer_id")
                                        item_photo = item.get("photo") or item.get("photo_id")
                                        items.append(
                                            {
                                                "title": title,
                                                "quantity": qty,
                                                "price": price,
                                                "offer_id": item_offer_id,
                                                "photo": item_photo,
                                            }
                                        )
                                        total += price * qty
                                except Exception:
                                    pass
                            else:
                                offer_id = (
                                    entity.get("offer_id")
                                    if isinstance(entity, dict)
                                    else getattr(entity, "offer_id", None)
                                )
                                quantity = (
                                    entity.get("quantity", 1)
                                    if isinstance(entity, dict)
                                    else getattr(entity, "quantity", 1)
                                )
                                if offer_id:
                                    offer = (
                                        self.db.get_offer(offer_id)
                                        if hasattr(self.db, "get_offer")
                                        else None
                                    )
                                    title = offer.get("title", "") if isinstance(offer, dict) else ""
                                    price = (
                                        offer.get("discount_price", 0) if isinstance(offer, dict) else 0
                                    )
                                    offer_photo = None
                                    if isinstance(offer, dict):
                                        offer_photo = offer.get("photo") or offer.get("photo_id")
                                    else:
                                        offer_photo = getattr(offer, "photo", None) if offer else None
                                        if not offer_photo:
                                            offer_photo = (
                                                getattr(offer, "photo_id", None) if offer else None
                                            )
                                    items.append(
                                        {
                                            "title": title,
                                            "quantity": int(quantity or 1),
                                            "price": int(price or 0),
                                            "offer_id": int(offer_id),
                                            "photo": offer_photo,
                                        }
                                    )
                                    total = int(price or 0) * int(quantity or 1)

                            delivery_price = 0
                            if resolved_order_type in ("delivery", "taxi"):
                                raw_delivery = (
                                    entity.get("delivery_price")
                                    if isinstance(entity, dict)
                                    else getattr(entity, "delivery_price", None)
                                )
                                if raw_delivery is None and isinstance(store, dict):
                                    raw_delivery = store.get("delivery_price", 0)
                                try:
                                    delivery_price = int(raw_delivery or 0)
                                except Exception:
                                    delivery_price = 0

                            seller_text = NotificationTemplates.seller_status_update(
                                lang=seller_lang,
                                order_id=entity_id,
                                status=target_status,
                                order_type=resolved_order_type,
                                items=items or None,
                                customer_name=customer_name,
                                customer_phone=customer_phone,
                                delivery_address=delivery_address,
                                total=total,
                                delivery_price=delivery_price,
                                currency=currency,
                            )
                            photo_ids = self._collect_photos_from_items(items)
                            seller_photo = None
                            if len(photo_ids) > 1:
                                seller_photo = await self._build_collage_photo(photo_ids)
                            if not seller_photo and photo_ids:
                                seller_photo = photo_ids[0]
                            if not seller_photo and offer_id:
                                try:
                                    seller_photo = self._get_offer_photo(int(offer_id))
                                except (TypeError, ValueError):
                                    seller_photo = None

                            kb = InlineKeyboardBuilder()
                            if resolved_order_type in ("delivery", "taxi"):
                                if target_status in (OrderStatus.PENDING, OrderStatus.PREPARING):
                                    if seller_lang == "uz":
                                        kb.button(
                                            text="Topshirishga tayyor",
                                            callback_data=f"order_ready_{entity_id}",
                                        )
                                    else:
                                        kb.button(
                                            text="Gotov k peredache",
                                            callback_data=f"order_ready_{entity_id}",
                                        )
                                elif target_status == OrderStatus.READY:
                                    if seller_lang == "uz":
                                        kb.button(
                                            text="Kuryerga topshirdim",
                                            callback_data=f"order_delivering_{entity_id}",
                                        )
                                    else:
                                        kb.button(
                                            text="Peredal kureru",
                                            callback_data=f"order_delivering_{entity_id}",
                                        )
                                elif target_status == OrderStatus.DELIVERING:
                                    if seller_lang == "uz":
                                        kb.button(
                                            text="Topshirildi",
                                            callback_data=f"order_complete_{entity_id}",
                                        )
                                    else:
                                        kb.button(
                                            text="Vydano",
                                            callback_data=f"order_complete_{entity_id}",
                                        )
                            else:
                                if target_status in (
                                    OrderStatus.PENDING,
                                    OrderStatus.PREPARING,
                                    OrderStatus.READY,
                                    OrderStatus.DELIVERING,
                                ):
                                    if seller_lang == "uz":
                                        kb.button(
                                            text="Topshirildi",
                                            callback_data=f"order_complete_{entity_id}",
                                        )
                                    else:
                                        kb.button(
                                            text="Vydano",
                                            callback_data=f"order_complete_{entity_id}",
                                        )

                            reply_markup = kb.as_markup() if kb.buttons else None

                            if seller_message_id:
                                try:
                                    await self.bot.edit_message_caption(
                                        chat_id=owner_id,
                                        message_id=seller_message_id,
                                        caption=seller_text,
                                        parse_mode="HTML",
                                        reply_markup=reply_markup,
                                    )
                                except Exception:
                                    try:
                                        await self.bot.edit_message_text(
                                            chat_id=owner_id,
                                            message_id=seller_message_id,
                                            text=seller_text,
                                            parse_mode="HTML",
                                            reply_markup=reply_markup,
                                        )
                                    except Exception as edit_error:
                                        logger.warning(
                                            f"Failed to update seller message for order#{entity_id}: {edit_error}"
                                        )
                            elif self.force_telegram_sync:
                                try:
                                    sent_msg = None
                                    if seller_photo:
                                        try:
                                            sent_msg = await self.bot.send_photo(
                                                owner_id,
                                                photo=seller_photo,
                                                caption=seller_text,
                                                parse_mode="HTML",
                                                reply_markup=reply_markup,
                                            )
                                        except Exception as photo_err:
                                            logger.warning(
                                                f"Failed to send status photo to seller {owner_id}: {photo_err}"
                                            )
                                    if not sent_msg:
                                        sent_msg = await self.bot.send_message(
                                            owner_id,
                                            seller_text,
                                            parse_mode="HTML",
                                            reply_markup=reply_markup,
                                        )
                                    if sent_msg and hasattr(self.db, "set_order_seller_message_id"):
                                        self.db.set_order_seller_message_id(
                                            entity_id, sent_msg.message_id
                                        )
                                except Exception as send_error:
                                    logger.warning(
                                        f"Failed to send seller message for order#{entity_id}: {send_error}"
                                    )
                except Exception as seller_error:
                    logger.warning(
                        f"Seller message update skipped for order#{entity_id}: {seller_error}"
                    )

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
