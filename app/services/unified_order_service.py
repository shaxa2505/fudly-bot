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
    READY       → Ready for pickup/delivery (pickup customers are notified)
    DELIVERING  → In transit (delivery only)
    COMPLETED   → Order completed
    REJECTED    → Rejected by seller
    CANCELLED   → Cancelled by customer

NOTIFICATION STRATEGY (Optimized v2):
    - Minimize spam by skipping READY notifications for delivery
    - Use visual progress bars for better UX
    - Pickup: READY → COMPLETED (2 notifications)
    - Delivery: PREPARING → DELIVERING → COMPLETED (3 notifications)
"""
from __future__ import annotations

import html
import io
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
from typing import Any, Literal

from aiogram import Bot
from aiogram.types import BufferedInputFile, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image

from app.core.geocoding import geocode_store_address
from app.core.constants import DEFAULT_DELIVERY_RADIUS_KM
from app.core.sanitize import sanitize_phone
from app.core.security import validator
from app.core.utils import UZB_TZ, get_uzb_time, get_order_field
from app.core.notifications import Notification, NotificationType, get_notification_service
from app.integrations.payment_service import get_payment_service
from app.domain.order import OrderStatus, PaymentStatus
from app.domain.order_labels import status_label
from app.services.notification_builder import NotificationBuilder
from app.services.notification_unified import build_unified_order_payload
from localization import get_text

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


def _delivery_cash_enabled() -> bool:
    return os.getenv("FUDLY_DELIVERY_CASH_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _parse_coord(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.pi / 180.0
    x = (lon2 - lon1) * rad * math.cos((lat1 + lat2) * rad / 2.0)
    y = (lat2 - lat1) * rad
    return math.hypot(x, y) * 6371.0


def _parse_time_value(value: object) -> dt_time | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.replace(".", ":")
    if "T" in raw:
        raw = raw.split("T", 1)[1]
    raw = raw.strip()
    if re.fullmatch(r"\d{1,2}", raw):
        raw = f"{int(raw):02d}:00"
    elif re.fullmatch(r"\d{1,2}:\d{1,2}", raw):
        parts = raw.split(":", 1)
        raw = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return None


def _parse_time_range_from_text(value: object) -> tuple[dt_time | None, dt_time | None]:
    if not value:
        return None, None
    raw = str(value)
    match = re.search(r"(\d{1,2}:\d{2}).*(\d{1,2}:\d{2})", raw)
    if not match:
        return None, None
    start = _parse_time_value(match.group(1))
    end = _parse_time_value(match.group(2))
    return start, end


def _is_time_in_window(start: dt_time | None, end: dt_time | None, now: dt_time) -> bool:
    if not start or not end:
        return True
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def _get_store_hours_raw(store: Any) -> str | None:
    if not store:
        return None
    if isinstance(store, dict):
        working_hours = store.get("working_hours") or store.get("work_time")
        if not working_hours and store.get("open_time") and store.get("close_time"):
            working_hours = f"{store.get('open_time')} - {store.get('close_time')}"
        return working_hours
    working_hours = getattr(store, "working_hours", None) or getattr(store, "work_time", None)
    if not working_hours:
        open_time = getattr(store, "open_time", None)
        close_time = getattr(store, "close_time", None)
        if open_time and close_time:
            working_hours = f"{open_time} - {close_time}"
    return working_hours


def _get_store_time_range_label(store: Any) -> str | None:
    raw = _get_store_hours_raw(store)
    if not raw:
        return None
    start, end = _parse_time_range_from_text(raw)
    if start and end:
        return f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
    if start:
        return start.strftime("%H:%M")
    if end:
        return end.strftime("%H:%M")
    return None


def _is_store_open_now(store: Any) -> bool:
    raw = _get_store_hours_raw(store)
    if not raw:
        return True
    start, end = _parse_time_range_from_text(raw)
    if not start or not end:
        return True
    current = get_uzb_time().time()
    return _is_time_in_window(start, end, current)


def set_order_status_direct(db: Any, order_id: int, status: str) -> bool:
    """Update order status directly via DB adapter (legacy fallback)."""
    if not db or not hasattr(db, "update_order_status"):
        return False
    try:
        db.update_order_status(order_id, status)
        return True
    except Exception as exc:
        logger.error(f"Direct order status update failed for #{order_id}: {exc}")
        return False


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


@dataclass
class StatusUpdateContext:
    """Normalized context for status updates."""

    entity_id: int
    entity_type: Literal["order", "booking"]
    entity: Any
    user_id: int | None
    store_id: int | None
    pickup_code: str | None
    current_status_raw: str | None
    order_type: str | None
    payment_method: str | None
    payment_status: str | None
    payment_proof_photo_id: str | None
    delivery_address: str | None
    delivery_price: int
    is_cart: bool
    cart_items_json: Any
    offer_id: int | None
    quantity: int
    total_price: int | None
    item_title: str | None
    item_price: int | None
    item_original_price: int | None


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
    def _status_emoji(status: str | None) -> str:
        normalized = (
            OrderStatus.normalize(str(status).strip().lower()) if status else OrderStatus.PENDING
        )
        return {
            OrderStatus.PENDING: "⏳",
            OrderStatus.PREPARING: "✅",
            OrderStatus.READY: "🕒",
            OrderStatus.DELIVERING: "🚚",
            OrderStatus.COMPLETED: "✔",
            OrderStatus.CANCELLED: "❌",
            OrderStatus.REJECTED: "❌",
        }.get(normalized, "📦")

    @staticmethod
    def _format_created_time(value: Any | None) -> str | None:
        if not value:
            return None
        base_time = None
        if isinstance(value, datetime):
            base_time = value
        elif isinstance(value, str):
            try:
                base_time = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:
                base_time = None
        if base_time is None:
            base_time = get_uzb_time()
        elif base_time.tzinfo is None:
            base_time = base_time.replace(tzinfo=UZB_TZ)
        return base_time.astimezone(UZB_TZ).strftime("%H:%M")

    @staticmethod
    def _seller_status_label(status: str, lang: str, order_type: str) -> str:
        normalized = OrderStatus.normalize(str(status))
        if order_type == "delivery":
            if normalized == OrderStatus.READY:
                return get_text(lang, "seller_status_ready_delivery")
            if normalized == OrderStatus.DELIVERING:
                return get_text(lang, "seller_status_handed_over")
        return status_label(normalized, lang, order_type)

    @staticmethod
    def _seller_status_hint(status: str, lang: str, order_type: str) -> str | None:
        normalized = OrderStatus.normalize(str(status))
        if order_type == "pickup":
            if normalized == OrderStatus.PREPARING:
                return get_text(lang, "seller_hint_pickup_preparing")
            if normalized == OrderStatus.READY:
                return get_text(lang, "seller_hint_pickup_ready")
        if order_type == "delivery":
            if normalized == OrderStatus.PREPARING:
                return get_text(lang, "seller_hint_delivery_preparing")
            if normalized == OrderStatus.READY:
                return get_text(lang, "seller_hint_delivery_ready")
        return None

    @staticmethod
    def _build_seller_card(
        *,
        lang: str,
        order_id: int,
        status: str,
        order_type: str,
        items: list[dict] | None,
        customer_name: str | None,
        customer_phone: str | None,
        total: int | None,
        delivery_price: int,
        currency: str,
        created_at: Any | None = None,
    ) -> str:
        normalized_type = "delivery" if order_type == "taxi" else (order_type or "delivery")
        display_type = "pickup" if normalized_type == "pickup" else "delivery"

        type_label = (
            get_text(lang, "order_type_pickup")
            if display_type == "pickup"
            else get_text(lang, "order_type_delivery")
        )
        status_text = NotificationTemplates._seller_status_label(status, lang, display_type)
        status_emoji = NotificationTemplates._status_emoji(status)
        created_time = NotificationTemplates._format_created_time(created_at)

        safe_name = html.escape(str(customer_name)) if customer_name else "—"
        safe_phone = html.escape(str(customer_phone)) if customer_phone else "—"

        items_total = int(total or 0)
        if items_total <= 0 and items:
            try:
                items_total = sum(
                    int(item.get("price") or 0) * int(item.get("quantity") or 1)
                    for item in items
                )
            except Exception:
                items_total = int(total or 0)

        delivery_fee = int(delivery_price or 0) if display_type == "delivery" else 0
        grand_total = items_total + (delivery_fee if display_type == "delivery" else 0)

        label_order = get_text(lang, "label_order")
        label_status = get_text(lang, "label_status")
        label_created = get_text(lang, "label_created")
        label_customer = get_text(lang, "label_customer")
        label_phone = get_text(lang, "phone")
        label_items = get_text(lang, "label_items")
        label_amount = get_text(lang, "label_amount")
        label_items_cost = get_text(lang, "label_items_cost")
        label_delivery = get_text(lang, "label_delivery_fee")
        label_total = get_text(lang, "label_total")

        def _fmt_money(value: int) -> str:
            return f"{int(value):,}".replace(",", " ")

        lines: list[str] = [
            f"📦 {label_order} #{order_id} — {type_label}",
            f"{label_status}: {status_emoji} <b>{status_text}</b>",
        ]
        if created_time:
            lines.append(f"⏱ {label_created}: {created_time}")

        lines.extend(
            [
                "",
                f"👤 {label_customer}: {safe_name}",
                f"📞 {label_phone}: {safe_phone}",
                "",
                f"🛒 {label_items}:",
            ]
        )

        if items:
            for item in items:
                title = html.escape(str(item.get("title") or ""))
                qty = int(item.get("quantity") or 1)
                lines.append(f"• {title} ×{qty}")
        else:
            lines.append("• —")

        lines.extend(
            [
                "",
                f"💰 {label_amount}:",
                f"{label_items_cost}: {_fmt_money(items_total)} {currency}",
            ]
        )
        if display_type == "delivery":
            lines.append(f"{label_delivery}: {_fmt_money(delivery_fee)} {currency}")
        lines.append(f"{label_total}: {_fmt_money(grand_total)} {currency}")

        hint = NotificationTemplates._seller_status_hint(status, lang, display_type)
        if hint:
            lines.append("")
            lines.append(hint)

        return "\n".join(lines)

    @staticmethod
    def _build_customer_card(
        *,
        lang: str,
        order_id: int,
        status: str,
        order_type: str | None,
        total: int | None,
        delivery_price: int = 0,
        currency: str = "UZS",
        store_name: str | None = None,
        store_address: str | None = None,
        delivery_address: str | None = None,
        pickup_code: str | None = None,
        reject_reason: str | None = None,
        ready_until: str | None = None,
        items: list[dict] | None = None,
    ) -> str:
        normalized_type = "delivery" if order_type == "taxi" else (order_type or "delivery")
        display_type = "pickup" if normalized_type == "pickup" else "delivery"

        status_text = status_label(status, lang, display_type)
        normalized_status = OrderStatus.normalize(str(status).strip().lower())
        if reject_reason and normalized_status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
            status_text = f"{status_text} — {reject_reason}"

        total_value = int(total or 0)
        if total_value <= 0 and items:
            try:
                total_value = sum(
                    int(item.get("price") or 0) * int(item.get("quantity") or 1)
                    for item in items
                )
            except Exception:
                total_value = int(total or 0)
        if normalized_type in ("delivery", "taxi") and delivery_price:
            if total_value:
                total_value += int(delivery_price)
            else:
                total_value = int(delivery_price)

        order_label = get_text(lang, "label_order")
        status_label_text = get_text(lang, "label_status")
        amount_label = get_text(lang, "label_amount")
        type_label = get_text(lang, "label_order_type")
        pickup_type = get_text(lang, "order_type_pickup")
        delivery_type = get_text(lang, "order_type_delivery")
        store_label = get_text(lang, "label_store")
        address_label = get_text(lang, "address")
        pickup_code_label = get_text(lang, "label_pickup_code")
        pickup_until_label = get_text(lang, "label_pickup_until")

        type_value = pickup_type if display_type == "pickup" else delivery_type
        address_value = (
            delivery_address if display_type == "delivery" else store_address
        )

        lines = [
            f"📄 {order_label} #{order_id}",
            "",
            f"{status_label_text}: {NotificationTemplates._status_emoji(status)} <b>{status_text}</b>",
        ]

        if total_value > 0:
            lines.append(f"{amount_label}: <b>{total_value:,} {currency}</b>")
        if type_value:
            lines.append(f"{type_label}: {type_value}")
        if ready_until:
            lines.append(f"{pickup_until_label}: <b>{ready_until}</b>")

        if store_name or address_value:
            lines.append("")
            if store_name:
                lines.append(f"📍 {store_label}: {html.escape(str(store_name))}")
            if address_value:
                lines.append(f"{address_label}: {html.escape(str(address_value))}")

        if pickup_code and display_type == "pickup":
            lines.append(f"🔐 {pickup_code_label}")
            lines.append(f"<code>{html.escape(str(pickup_code))}</code>")

        return "\n".join(lines)


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
        comment: str | None = None,
        map_url: str | None = None,
        payment_status: str | None = None,
        payment_proof_photo_id: str | None = None,
        created_at: Any | None = None,
    ) -> str:
        "Build seller notification for new order."
        order_ids_int = [int(x) for x in order_ids if x]
        order_id_value = (
            int(order_ids_int[0])
            if order_ids_int
            else int(order_ids[0]) if order_ids else 0
        )
        return NotificationTemplates._build_seller_card(
            lang=lang,
            order_id=order_id_value,
            status=OrderStatus.PENDING,
            order_type=order_type,
            items=items,
            customer_name=customer_name,
            customer_phone=customer_phone,
            total=total,
            delivery_price=delivery_price,
            currency=currency,
            created_at=created_at,
        )


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
        store_phone: str | None = None,
        awaiting_payment: bool = False,
    ) -> str:
        "Build customer notification for order creation."
        pickup_code = pickup_codes[0] if pickup_codes else None
        order_ids_int = [int(x) for x in order_ids if x]
        order_id_value = (
            int(order_ids_int[0])
            if order_ids_int
            else int(order_ids[0]) if order_ids else 0
        )
        return NotificationTemplates._build_customer_card(
            lang=lang,
            order_id=order_id_value,
            status=OrderStatus.PENDING,
            order_type=order_type,
            total=total,
            delivery_price=delivery_price,
            currency=currency,
            store_name=store_name,
            store_address=store_address,
            delivery_address=delivery_address,
            pickup_code=pickup_code,
            items=items,
        )


    def customer_status_update(
        lang: str,
        order_id: int | str,
        status: str,
        order_type: str,
        store_name: str | None = None,
        store_phone: str | None = None,
        store_address: str | None = None,
        pickup_code: str | None = None,
        reject_reason: str | None = None,
        courier_phone: str | None = None,
        items: list[dict] | None = None,
        delivery_address: str | None = None,
        delivery_price: int = 0,
        total: int | None = None,
        currency: str = "UZS",
        order_ids: list[int] | None = None,
        is_cart: bool = False,
        payment_method: str | None = None,
        payment_status: str | None = None,
        payment_proof_photo_id: str | None = None,
        ready_until: str | None = None,
    ) -> str:
        """Build customer notification for status update."""
        return NotificationTemplates._build_customer_card(
            lang=lang,
            order_id=int(order_id) if isinstance(order_id, str) else order_id,
            status=status,
            order_type=order_type,
            total=total,
            delivery_price=delivery_price,
            currency=currency,
            store_name=store_name,
            store_address=store_address,
            delivery_address=delivery_address,
            pickup_code=pickup_code,
            reject_reason=reject_reason,
            ready_until=ready_until,
            items=items,
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
        store_phone: str | None = None,
        store_address: str | None = None,
        delivery_address: str | None = None,
        delivery_price: int = 0,
        pickup_code: str | None = None,
        reject_reason: str | None = None,
        courier_phone: str | None = None,
        payment_method: str | None = None,
        payment_status: str | None = None,
        payment_proof_photo_id: str | None = None,
        ready_until: str | None = None,
    ) -> str:
        """Build cart summary status message for customers."""
        return NotificationTemplates._build_customer_card(
            lang=lang,
            order_id=int(order_id) if isinstance(order_id, str) else order_id,
            status=status,
            order_type=order_type,
            total=None,
            delivery_price=delivery_price,
            currency=currency,
            store_name=store_name,
            store_address=store_address,
            delivery_address=delivery_address,
            pickup_code=pickup_code,
            reject_reason=reject_reason,
            ready_until=ready_until,
            items=items,
        )

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
        payment_method: str | None = None,
        payment_status: str | None = None,
        payment_proof_photo_id: str | None = None,
        created_at: Any | None = None,
    ) -> str:
        """Build seller notification with a clean status layout."""
        return NotificationTemplates._build_seller_card(
            lang=lang,
            order_id=int(order_id) if isinstance(order_id, str) else order_id,
            status=status,
            order_type=order_type,
            items=items,
            customer_name=customer_name,
            customer_phone=customer_phone,
            total=total,
            delivery_price=delivery_price,
            currency=currency,
            created_at=created_at,
        )


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

    async def _flag_refund_required(
        self,
        ctx: StatusUpdateContext,
        target_status: str,
        reject_reason: str | None = None,
    ) -> None:
        """Mark order as refund-required and notify admins."""
        if ctx.entity_type != "order":
            return

        reason_label = "rejected" if target_status == OrderStatus.REJECTED else "cancelled"
        comment = f"refund_required:{reason_label}"
        if reject_reason:
            comment = f"{comment} ({reject_reason})"

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE orders
                    SET cancel_reason = COALESCE(cancel_reason, %s),
                        cancel_comment = CASE
                            WHEN cancel_comment IS NULL OR cancel_comment = '' THEN %s
                            ELSE cancel_comment || ' | ' || %s
                        END
                    WHERE order_id = %s
                    """,
                    ("refund_required", comment, comment, int(ctx.entity_id)),
                )
        except Exception as e:
            logger.warning(f"Failed to mark refund_required for order #{ctx.entity_id}: {e}")

        admin_ids: list[int] = []
        try:
            if hasattr(self.db, "get_admin_ids"):
                admin_ids = self.db.get_admin_ids() or []
        except Exception:
            admin_ids = []

        if not admin_ids:
            try:
                admin_env = os.getenv("ADMIN_ID")
                if admin_env:
                    admin_ids = [int(admin_env)]
            except Exception:
                admin_ids = []

        if not admin_ids or not self.bot:
            return

        payment_method = PaymentStatus.normalize_method(ctx.payment_method)
        total = int(ctx.total_price or 0)
        order_type = ctx.order_type or "delivery"

        text = (
            "⚠️ Refund required\n"
            f"Order: #{int(ctx.entity_id)}\n"
            f"Status: {reason_label}\n"
            f"Payment: {payment_method}\n"
            f"Order type: {order_type}\n"
            f"Total: {total}\n"
        )
        if reject_reason:
            text += f"Reason: {reject_reason}\n"

        for admin_id in admin_ids[:3]:
            try:
                await self.bot.send_message(admin_id, text)
            except Exception as e:
                logger.warning(
                    "Failed to notify admin %s about refund for order %s: %s",
                    admin_id,
                    ctx.entity_id,
                    e,
                )

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

    @staticmethod
    def _pickup_ready_expiry_hours() -> int:
        try:
            value = int(os.environ.get("PICKUP_READY_EXPIRY_HOURS", "2"))
        except Exception:
            value = 2
        return max(1, value)

    def _format_pickup_ready_until(self, updated_at: Any | None) -> str | None:
        hours = self._pickup_ready_expiry_hours()
        if hours <= 0:
            return None

        base_time = None
        if isinstance(updated_at, datetime):
            base_time = updated_at
        elif isinstance(updated_at, str) and updated_at:
            try:
                base_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except Exception:
                base_time = None

        if base_time is None:
            base_time = get_uzb_time()
        elif base_time.tzinfo is None:
            base_time = base_time.replace(tzinfo=UZB_TZ)

        ready_until = base_time + timedelta(hours=hours)
        return ready_until.astimezone(UZB_TZ).strftime("%H:%M")

    def _build_customer_notification(
        self,
        *,
        lang: str,
        order_id: int,
        order_type: str | None,
        status: str,
        reject_reason: str | None,
        courier_phone: str | None,
    ) -> str | None:
        normalized_status = OrderStatus.normalize(str(status))
        normalized_type = "delivery" if order_type == "taxi" else (order_type or "delivery")
        is_pickup = normalized_type == "pickup"

        key = None
        if normalized_status == OrderStatus.PREPARING:
            key = "notification_order_confirmed"
        elif is_pickup and normalized_status == OrderStatus.READY:
            key = "notification_order_ready_pickup"
        elif not is_pickup and normalized_status == OrderStatus.DELIVERING:
            key = "notification_order_delivering"
        elif normalized_status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
            pickup_reason = get_text(lang, "pickup_ready_expired_reason")
            if is_pickup and reject_reason and pickup_reason and reject_reason.strip() == pickup_reason.strip():
                key = "notification_order_cancelled_pickup_expired"
            else:
                key = "notification_order_cancelled"

        if not key:
            return None

        try:
            if key == "notification_order_ready_pickup":
                hours = self._pickup_ready_expiry_hours()
                text = get_text(lang, key).format(order_id=order_id, hours=hours)
            else:
                text = get_text(lang, key).format(order_id=order_id)
        except Exception:
            text = None

        if not text:
            return None

        if normalized_status == OrderStatus.DELIVERING and courier_phone:
            courier_label = get_text(lang, "label_courier")
            text = f"{text}\n{courier_label}: {courier_phone}"

        return text

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

    def _error_result(
        self,
        error_message: str,
        failed_items: list[OrderItem] | None = None,
    ) -> OrderResult:
        return OrderResult(
            success=False,
            order_ids=[],
            booking_ids=[],
            pickup_codes=[],
            total_items=0,
            total_price=0,
            delivery_price=0,
            grand_total=0,
            error_message=error_message,
            failed_items=failed_items,
        )

    @staticmethod
    def _calc_items_payload(items: list[OrderItem]) -> list[dict[str, int]]:
        return [
            {"title": item.title, "price": item.price, "quantity": item.quantity}
            for item in items
        ]

    @staticmethod
    def _build_db_items(items: list[OrderItem], is_delivery: bool) -> list[dict[str, Any]]:
        return [
            {
                "offer_id": item.offer_id,
                "store_id": item.store_id,
                "quantity": item.quantity,
                "price": item.price,
                "original_price": item.original_price,
                "delivery_price": item.delivery_price if is_delivery else 0,
                "title": item.title,
                "store_name": item.store_name,
                "store_address": item.store_address,
            }
            for item in items
        ]

    async def _notify_customer_on_create(
        self,
        user_id: int,
        items: list[OrderItem],
        order_type: str,
        delivery_address: str | None,
        payment_method: str,
        order_ids: list[int],
        booking_ids: list[int],
        pickup_codes: list[str],
        total_price: int,
        delivery_price: int,
        customer_name: str,
        customer_phone: str,
        customer_lang: str,
        currency: str,
        customer_notifications: bool,
        telegram_enabled: bool,
        notifications_enabled: bool,
    ) -> None:
        # Send notification/event to customer (WebApp sync always; Telegram optional)
        publish_customer_event = bool(user_id)
        send_card = bool(user_id) and telegram_enabled
        if not (send_card or publish_customer_event):
            return

        all_ids = [str(x) for x in (order_ids + booking_ids)]
        items_for_template = self._calc_items_payload(items)
        store_id = items[0].store_id if items else None

        store_phone = None
        if store_id and hasattr(self.db, "get_store"):
            try:
                store = self.db.get_store(store_id)
                if isinstance(store, dict):
                    store_phone = store.get("phone")
                else:
                    store_phone = getattr(store, "phone", None)
            except Exception:
                store_phone = None

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
            store_phone=store_phone,
            total=total_price,
            delivery_price=delivery_price,
            currency=currency,
        )

        entity_ids_raw = [x for x in (order_ids + booking_ids) if x]
        entity_ids = [int(x) for x in entity_ids_raw]
        entity_id = entity_ids[0] if entity_ids else None
        entity_type = "order" if order_ids else "booking"

        reply_markup = self._build_customer_reply_markup(
            target_status=OrderStatus.PENDING,
            new_status=OrderStatus.PENDING,
            order_type=order_type,
            customer_lang=customer_lang,
            entity_id=entity_id or 0,
            entity_type=entity_type,
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
        if send_card:
            try:
                if customer_photo:
                    try:
                        sent_msg = await self.bot.send_photo(
                            user_id,
                            photo=customer_photo,
                            caption=customer_msg,
                            parse_mode="HTML",
                            reply_markup=reply_markup,
                        )
                    except Exception as photo_err:
                        logger.warning(
                            f"Failed to send customer photo for {user_id}: {photo_err}"
                        )
                if not sent_msg:
                    sent_msg = await self.bot.send_message(
                        user_id, customer_msg, parse_mode="HTML", reply_markup=reply_markup
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
                elif booking_ids and hasattr(self.db, "set_booking_customer_message_id"):
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
                title_html = get_text(customer_lang, "cart_order_created_title")
                title = re.sub(r"<[^>]+>", "", title_html)
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
                            "unified": unified_payload,
                        },
                    },
                )
            except Exception as ws_error:
                logger.warning(
                    f"WebSocket notify failed for order create: {ws_error}"
                )


    async def create_order(
        self,
        user_id: int,
        items: list[OrderItem],
        order_type: str,
        delivery_address: str | None = None,
        delivery_lat: float | None = None,
        delivery_lon: float | None = None,
        comment: str | None = None,
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
            return self._error_result("No items provided")
        if any(int(getattr(item, "quantity", 0) or 0) <= 0 for item in items):
            return self._error_result("Invalid item quantity")

        is_delivery = order_type in ("delivery", "taxi")
        normalized_order_type = "delivery" if order_type == "taxi" else order_type
        if is_delivery and not delivery_address:
            return self._error_result("Delivery address required")

        if is_delivery and delivery_address and (delivery_lat is None or delivery_lon is None):
            try:
                geo = await geocode_store_address(delivery_address, None)
                if geo:
                    delivery_lat = geo.get("latitude")
                    delivery_lon = geo.get("longitude")
            except Exception as geo_err:
                logger.warning("Delivery geocode failed in create_order: %s", geo_err)

        payment_method = PaymentStatus.normalize_method(payment_method)
        if is_delivery and payment_method == "cash" and not _delivery_cash_enabled():
            return self._error_result("Cash is not allowed for delivery orders")
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

        store_id = next(iter(store_ids))
        store = self.db.get_store(store_id) if hasattr(self.db, "get_store") else None
        store_phone_raw = None
        if store:
            if isinstance(store, dict):
                store_phone_raw = store.get("phone")
            else:
                store_phone_raw = getattr(store, "phone", None)
        store_phone = sanitize_phone(store_phone_raw)
        if not store_phone or not validator.validate_phone(store_phone):
            lang = "ru"
            if hasattr(self.db, "get_user_language"):
                try:
                    lang = self.db.get_user_language(user_id) or "ru"
                except Exception:
                    lang = "ru"
            return self._error_result(get_text(lang, "store_phone_required_for_orders"))
        if store and not _is_store_open_now(store):
            time_range = _get_store_time_range_label(store)
            detail = "Store is closed now"
            if time_range:
                detail = f"{detail}. Order time: {time_range}"
            return self._error_result(detail)
        if is_delivery and store:
            store_delivery_enabled = (
                store.get("delivery_enabled")
                if isinstance(store, dict)
                else getattr(store, "delivery_enabled", None)
            )
            if store_delivery_enabled is not None and not bool(store_delivery_enabled):
                return self._error_result("Yetkazib berish mavjud emas")

            store_lat = _parse_coord(
                store.get("latitude") if isinstance(store, dict) else getattr(store, "latitude", None)
            )
            store_lon = _parse_coord(
                store.get("longitude") if isinstance(store, dict) else getattr(store, "longitude", None)
            )
            if store_lat is None or store_lon is None:
                return self._error_result("Do'kon geolokatsiyasi o'rnatilmagan")

            delivery_lat_val = _parse_coord(delivery_lat)
            delivery_lon_val = _parse_coord(delivery_lon)
            if delivery_lat_val is None or delivery_lon_val is None:
                return self._error_result("Yetkazib berish manzilini xaritada belgilang")

            radius_raw = (
                store.get("delivery_radius_km")
                if isinstance(store, dict)
                else getattr(store, "delivery_radius_km", None)
            )
            radius_km = _parse_coord(radius_raw)
            if radius_km is None or radius_km <= 0:
                radius_km = float(DEFAULT_DELIVERY_RADIUS_KM)

            distance_km = _distance_km(store_lat, store_lon, delivery_lat_val, delivery_lon_val)
            if distance_km > radius_km:
                return self._error_result(
                    f"Yetkazib berish radiusi {radius_km:.0f} km. Masofa: {distance_km:.1f} km"
                )

        # Normalize and enforce: sellers should only see paid/cash orders
        if not PaymentStatus.is_cleared(
            PaymentStatus.initial_for_method(payment_method),
            payment_method=payment_method,
            payment_proof_photo_id=payment_proof,
        ):
            notify_sellers = False

        # Prepare items for database
        db_items = self._build_db_items(items, is_delivery)

        # Create orders using appropriate method based on type
        if order_type == "pickup":
            # Use booking system for pickup
            result = await self._create_pickup_orders(user_id, db_items, payment_method)
        else:
            # Use order system for delivery
            result = await self._create_delivery_orders(
                user_id,
                db_items,
                delivery_address,
                payment_method,
                order_type,
                delivery_lat=delivery_lat,
                delivery_lon=delivery_lon,
                comment=comment,
            )

        if not result.get("success"):
            error_msg = result.get("error", "Failed to create orders")
            friendly_error = self._normalize_creation_error(error_msg, items)
            return self._error_result(
                friendly_error,
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
                order_type=normalized_order_type,
                delivery_address=delivery_address,
                delivery_lat=delivery_lat,
                delivery_lon=delivery_lon,
                comment=comment,
                payment_method=payment_method,
                customer_name=customer_name,
                customer_phone=customer_phone,
                send_telegram=telegram_enabled,
            )

        await self._notify_customer_on_create(
            user_id=user_id,
            items=items,
            order_type=order_type,
            delivery_address=delivery_address,
            payment_method=payment_method,
            order_ids=order_ids,
            booking_ids=booking_ids,
            pickup_codes=pickup_codes,
            total_price=total_price,
            delivery_price=delivery_price,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_lang=customer_lang,
            currency=currency,
            customer_notifications=customer_notifications,
            telegram_enabled=telegram_enabled,
            notifications_enabled=notifications_enabled,
        )

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
                        "original_price": int(item.get("original_price") or item.get("price") or 0),
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

    @staticmethod
    def _build_cart_items_payload(items: list[dict]) -> list[dict[str, Any]]:
        return [
            {
                "offer_id": int(item["offer_id"]),
                "quantity": int(item.get("quantity", 1)),
                "price": int(item.get("price", 0)),
                "title": item.get("title", ""),
                "original_price": int(item.get("original_price") or item.get("price") or 0),
            }
            for item in items
        ]

    @staticmethod
    def _build_store_orders_for_delivery(
        items: list[dict],
        *,
        order_id: int,
        store_id: int,
        delivery_price: int,
    ) -> list[dict[str, Any]]:
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
        return store_orders

    @staticmethod
    def _format_created_orders_response(result: dict) -> dict:
        created_orders = result.get("created_orders", [])
        return {
            "success": True,
            "order_ids": [o.get("order_id") for o in created_orders if o.get("order_id")],
            "booking_ids": [],
            "pickup_codes": [o.get("pickup_code") for o in created_orders if o.get("pickup_code")],
            "stores_orders": result.get("stores_orders", {}),
            "failed_items": result.get("failed_items"),
        }

    async def _create_delivery_orders(
        self,
        user_id: int,
        items: list[dict],
        delivery_address: str,
        payment_method: str,
        order_type: str = "delivery",
        delivery_lat: float | None = None,
        delivery_lon: float | None = None,
        comment: str | None = None,
    ) -> dict:
        """Create delivery orders."""
        try:
            normalized_order_type = "delivery" if order_type == "taxi" else order_type
            # Cart delivery must be a SINGLE order row (per store) to keep payment/proof/admin flow consistent.
            if (
                len(items) > 1
                and hasattr(self.db, "create_cart_order_atomic")
                and items
                and items[0].get("store_id")
            ):
                store_id = int(items[0]["store_id"])
                delivery_price = int(items[0].get("delivery_price") or 0)

                cart_items = self._build_cart_items_payload(items)

                ok, order_id, _pickup_code, error_reason = self.db.create_cart_order_atomic(
                    user_id=user_id,
                    store_id=store_id,
                    cart_items=cart_items,
                    delivery_address=delivery_address,
                    delivery_lat=delivery_lat,
                    delivery_lon=delivery_lon,
                    comment=comment,
                    delivery_price=delivery_price,
                    payment_method=payment_method,
                    order_type=normalized_order_type,
                )

                if not ok or not order_id:
                    return {
                        "success": False,
                        "error": error_reason or "Failed to create cart delivery order",
                    }

                store_orders = self._build_store_orders_for_delivery(
                    items,
                    order_id=int(order_id),
                    store_id=store_id,
                    delivery_price=delivery_price,
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
                order_type=normalized_order_type,
                delivery_address=delivery_address,
                delivery_lat=delivery_lat,
                delivery_lon=delivery_lon,
                comment=comment,
                payment_method=payment_method,
            )

            created_orders = result.get("created_orders", [])
            if not created_orders:
                return {
                    "success": False,
                    "error": "No orders created",
                    "failed_items": result.get("failed_items"),
                }

            return self._format_created_orders_response(result)
        except Exception as e:
            logger.error(f"Failed to create delivery orders: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _collect_order_ids(store_orders: list[dict]) -> tuple[list[str], list[int]]:
        order_ids: list[str] = []
        order_id_ints: list[int] = []
        seen_order_ids: set[int] = set()
        for order in store_orders:
            oid = order.get("order_id")
            if not oid:
                continue
            oid_int = int(oid)
            if oid_int in seen_order_ids:
                continue
            seen_order_ids.add(oid_int)
            order_ids.append(str(oid_int))
            order_id_ints.append(oid_int)
        return order_ids, order_id_ints

    @staticmethod
    def _collect_pickup_codes(store_orders: list[dict]) -> list[str]:
        pickup_codes: list[str] = []
        seen_codes: set[str] = set()
        for order in store_orders:
            code = order.get("pickup_code")
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            pickup_codes.append(code)
        return pickup_codes

    async def _resolve_delivery_map(
        self,
        *,
        is_delivery: bool,
        delivery_address: str | None,
        delivery_lat: float | None,
        delivery_lon: float | None,
    ) -> tuple[str | None, str | None]:
        map_url = None
        static_map_url = None
        lat_val = None
        lon_val = None
        if is_delivery and (delivery_lat is not None and delivery_lon is not None):
            try:
                lat_val = float(delivery_lat)
                lon_val = float(delivery_lon)
            except (TypeError, ValueError):
                lat_val = None
                lon_val = None
        elif is_delivery and delivery_address:
            try:
                geo = await geocode_store_address(delivery_address, None)
                if geo:
                    lat_val = float(geo.get("latitude"))
                    lon_val = float(geo.get("longitude"))
            except Exception as geo_err:
                logger.warning("Delivery geocode failed: %s", geo_err)
        if lat_val is not None and lon_val is not None:
            map_url = (
                "https://www.openstreetmap.org/?mlat="
                f"{lat_val:.6f}&mlon={lon_val:.6f}#map=18/{lat_val:.6f}/{lon_val:.6f}"
            )
            static_map_url = (
                "https://staticmap.openstreetmap.de/staticmap.php"
                f"?center={lat_val:.6f},{lon_val:.6f}"
                f"&zoom=17&size=640x360&markers={lat_val:.6f},{lon_val:.6f},red-pushpin"
            )
        return map_url, static_map_url

    @staticmethod
    def _build_seller_keyboard(
        seller_lang: str,
        first_order_id: int,
        order_type: str | None,
        map_url: str | None,
    ) -> InlineKeyboardBuilder:
        kb = InlineKeyboardBuilder()
        is_delivery = order_type in ("delivery", "taxi")
        kb.button(
            text=get_text(seller_lang, "btn_order_accept"),
            callback_data=f"order_confirm_{first_order_id}",
        )
        kb.button(
            text=get_text(seller_lang, "btn_order_reject"),
            callback_data=f"order_reject_{first_order_id}",
        )
        if map_url and is_delivery:
            kb.button(text=get_text(seller_lang, "btn_map"), url=map_url)
            kb.adjust(2, 1)
        else:
            kb.adjust(2)
        return kb

    async def _notify_sellers_new_order(
        self,
        stores_orders: dict[int, list[dict]],
        order_type: str,
        delivery_address: str | None,
        delivery_lat: float | None,
        delivery_lon: float | None,
        comment: str | None,
        payment_method: str,
        customer_name: str,
        customer_phone: str,
        payment_status: str | None = None,
        payment_proof_photo_id: str | None = None,
        send_telegram: bool | None = None,
    ) -> None:
        """Send order notifications to sellers, grouped by store."""
        telegram_enabled = (
            self.telegram_order_notifications if send_telegram is None else send_telegram
        )
        normalized_order_type = "delivery" if order_type == "taxi" else order_type
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
                is_delivery = order_type in ("delivery", "taxi")

                # Calculate store totals
                store_total = sum(o["price"] * o["quantity"] for o in store_orders)
                store_delivery = store_orders[0].get("delivery_price", 0) if is_delivery else 0

                # Build notification
                order_ids, order_id_ints = self._collect_order_ids(store_orders)
                pickup_codes = self._collect_pickup_codes(store_orders)
                map_url, _ = await self._resolve_delivery_map(
                    is_delivery=is_delivery,
                    delivery_address=delivery_address,
                    delivery_lat=delivery_lat,
                    delivery_lon=delivery_lon,
                )
                created_at = None
                if order_id_ints and hasattr(self.db, "get_order"):
                    try:
                        order_row = self.db.get_order(int(order_id_ints[0]))
                        created_at = get_order_field(order_row, "created_at")
                    except Exception:
                        created_at = None

                seller_text = NotificationTemplates.seller_new_order(
                    lang=seller_lang,
                    order_ids=order_ids,
                    pickup_codes=pickup_codes,
                    items=store_orders,
                    order_type=normalized_order_type,
                    delivery_address=delivery_address,
                    comment=comment,
                    map_url=map_url,
                    payment_method=payment_method,
                    payment_status=payment_status,
                    payment_proof_photo_id=payment_proof_photo_id,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    total=store_total,
                    delivery_price=store_delivery,
                    currency=currency,
                    created_at=created_at,
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
                    order_type=normalized_order_type,
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
                kb = self._build_seller_keyboard(
                    seller_lang=seller_lang,
                    first_order_id=first_order_id,
                    order_type=normalized_order_type,
                    map_url=map_url,
                )

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

    def _get_order_payment_context(self, order: Any) -> dict[str, Any]:
        if isinstance(order, dict):
            return {
                "store_id": order.get("store_id"),
                "delivery_address": order.get("delivery_address"),
                "delivery_lat": order.get("delivery_lat"),
                "delivery_lon": order.get("delivery_lon"),
                "comment": order.get("comment"),
                "order_type": order.get("order_type"),
                "payment_method": order.get("payment_method"),
                "pickup_code": order.get("pickup_code"),
                "cart_items_json": order.get("cart_items"),
                "offer_id": order.get("offer_id"),
                "quantity": order.get("quantity", 1),
                "customer_id": order.get("user_id"),
                "seller_message_id": order.get("seller_message_id"),
                "current_status": order.get("order_status"),
                "delivery_price": int(order.get("delivery_price", 0) or 0),
            }
        return {
            "store_id": getattr(order, "store_id", None),
            "delivery_address": getattr(order, "delivery_address", None),
            "delivery_lat": getattr(order, "delivery_lat", None),
            "delivery_lon": getattr(order, "delivery_lon", None),
            "comment": getattr(order, "comment", None),
            "order_type": getattr(order, "order_type", None),
            "payment_method": getattr(order, "payment_method", None),
            "pickup_code": getattr(order, "pickup_code", None),
            "cart_items_json": getattr(order, "cart_items", None),
            "offer_id": getattr(order, "offer_id", None),
            "quantity": getattr(order, "quantity", 1),
            "customer_id": getattr(order, "user_id", None),
            "seller_message_id": getattr(order, "seller_message_id", None),
            "current_status": getattr(order, "order_status", None),
            "delivery_price": int(getattr(order, "delivery_price", 0) or 0),
        }

    def _build_payment_items(
        self,
        *,
        order_id: int,
        store_id: int | None,
        store: Any,
        order_type: str,
        cart_items_json: Any,
        offer_id: int | None,
        quantity: int,
        pickup_code: str | None,
        order_delivery_price: int,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        store_name = store.get("name", "") if isinstance(store, dict) else ""
        store_address = store.get("address", "") if isinstance(store, dict) else ""
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
            return items

        if offer_id:
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
                    "delivery_price": int(order_delivery_price or 0),
                }
            )
        return items

    async def confirm_payment(self, order_id: int) -> bool:
        """Mark payment as confirmed and notify seller if not yet notified."""
        try:
            if not hasattr(self.db, "get_order"):
                return False

            order = self.db.get_order(order_id)
            if not order:
                return False

            ctx = self._get_order_payment_context(order)
            store_id = ctx["store_id"]
            delivery_address = ctx["delivery_address"]
            delivery_lat = ctx["delivery_lat"]
            delivery_lon = ctx["delivery_lon"]
            comment = ctx["comment"]
            order_type = ctx["order_type"]
            payment_method = ctx["payment_method"]
            pickup_code = ctx["pickup_code"]
            cart_items_json = ctx["cart_items_json"]
            offer_id = ctx["offer_id"]
            quantity = ctx["quantity"]
            customer_id = ctx["customer_id"]
            seller_message_id = ctx["seller_message_id"]
            current_status = ctx["current_status"]
            order_delivery_price = ctx["delivery_price"]

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
            normalized_order_type = "delivery" if order_type == "taxi" else order_type

            store = self.db.get_store(store_id) if store_id else None
            items = self._build_payment_items(
                order_id=order_id,
                store_id=store_id,
                store=store,
                order_type=normalized_order_type,
                cart_items_json=cart_items_json,
                offer_id=offer_id,
                quantity=quantity,
                pickup_code=pickup_code,
                order_delivery_price=order_delivery_price,
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
                order_type=normalized_order_type,
                delivery_address=delivery_address,
                delivery_lat=delivery_lat,
                delivery_lon=delivery_lon,
                comment=comment,
                payment_method=PaymentStatus.normalize_method(payment_method),
                payment_status=PaymentStatus.CONFIRMED,
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

    def _get_status_update_context(
        self,
        entity_id: int,
        entity_type: Literal["order", "booking"],
    ) -> StatusUpdateContext | None:
        """Load entity and normalize status update context."""
        # IMPORTANT: orders and bookings may still live in different tables at runtime.
        # Respect entity_type to avoid updating a wrong record on id collision.
        if entity_type == "booking":
            if not hasattr(self.db, "get_booking"):
                logger.warning("DB layer does not support bookings")
                return None

            entity = self.db.get_booking(entity_id)
            if not entity:
                logger.warning(f"Booking not found: #{entity_id}")
                return None

            if isinstance(entity, dict):
                user_id = entity.get("user_id")
                store_id = entity.get("store_id")
                pickup_code = entity.get("booking_code") or entity.get("pickup_code")
                current_status_raw = entity.get("status") or entity.get("order_status")
                payment_proof_photo_id = entity.get("payment_proof_photo_id")
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
                payment_proof_photo_id = getattr(entity, "payment_proof_photo_id", None)
                is_cart = int(getattr(entity, "is_cart_booking", 0) or 0) == 1
                cart_items_json = getattr(entity, "cart_items", None)
                offer_id = getattr(entity, "offer_id", None)
                quantity = int(getattr(entity, "quantity", 1) or 1)

            return StatusUpdateContext(
                entity_id=entity_id,
                entity_type=entity_type,
                entity=entity,
                user_id=user_id,
                store_id=store_id,
                pickup_code=pickup_code,
                current_status_raw=current_status_raw,
                order_type="pickup",
                payment_method=None,
                payment_status=None,
                payment_proof_photo_id=payment_proof_photo_id,
                delivery_address=None,
                delivery_price=0,
                is_cart=is_cart,
                cart_items_json=cart_items_json,
                offer_id=offer_id,
                quantity=quantity,
                total_price=None,
                item_title=None,
                item_price=None,
                item_original_price=None,
            )

        if not hasattr(self.db, "get_order"):
            logger.warning("DB layer does not support orders")
            return None

        entity = self.db.get_order(entity_id)
        if not entity:
            logger.warning(f"Order not found: #{entity_id}")
            return None

        if isinstance(entity, dict):
            user_id = entity.get("user_id")
            store_id = entity.get("store_id")
            pickup_code = entity.get("pickup_code")
            current_status_raw = entity.get("order_status")
            order_type = entity.get("order_type")
            payment_method = entity.get("payment_method")
            payment_status = entity.get("payment_status")
            payment_proof_photo_id = entity.get("payment_proof_photo_id")
            delivery_address = entity.get("delivery_address")
            delivery_price = int(entity.get("delivery_price") or 0)
            is_cart = int(entity.get("is_cart_order") or 0) == 1
            cart_items_json = entity.get("cart_items")
            offer_id = entity.get("offer_id")
            quantity = int(entity.get("quantity") or 1)
            total_price = entity.get("total_price")
            item_title = entity.get("item_title")
            item_price = entity.get("item_price")
            item_original_price = entity.get("item_original_price")

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
            payment_proof_photo_id = getattr(entity, "payment_proof_photo_id", None)
            delivery_address = getattr(entity, "delivery_address", None)
            delivery_price = int(getattr(entity, "delivery_price", 0) or 0)
            is_cart = int(getattr(entity, "is_cart_order", 0) or 0) == 1
            cart_items_json = getattr(entity, "cart_items", None)
            offer_id = getattr(entity, "offer_id", None)
            quantity = int(getattr(entity, "quantity", 1) or 1)
            total_price = getattr(entity, "total_price", None)
            item_title = getattr(entity, "item_title", None)
            item_price = getattr(entity, "item_price", None)
            item_original_price = getattr(entity, "item_original_price", None)
            if not order_type:
                order_type = "delivery" if delivery_address else "pickup"

        return StatusUpdateContext(
            entity_id=entity_id,
            entity_type=entity_type,
            entity=entity,
            user_id=user_id,
            store_id=store_id,
            pickup_code=pickup_code,
            current_status_raw=current_status_raw,
            order_type=order_type,
            payment_method=payment_method,
            payment_status=payment_status,
            payment_proof_photo_id=payment_proof_photo_id,
            delivery_address=delivery_address,
            delivery_price=delivery_price,
            is_cart=is_cart,
            cart_items_json=cart_items_json,
            offer_id=offer_id,
            quantity=quantity,
            total_price=total_price,
            item_title=item_title,
            item_price=item_price,
            item_original_price=item_original_price,
        )

    def _apply_status_update(
        self,
        ctx: StatusUpdateContext,
        target_status: str,
        current_status_raw: str | None,
        terminal_statuses: set[str],
    ) -> tuple[bool, bool]:
        """Persist status change. Returns (update_ok, short_circuit)."""
        update_ok = True
        if target_status in [OrderStatus.REJECTED, OrderStatus.CANCELLED]:
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    if ctx.entity_type == "booking":
                        if current_status_raw is not None:
                            cursor.execute(
                                "UPDATE bookings SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE booking_id = %s AND status = %s",
                                (target_status, ctx.entity_id, current_status_raw),
                            )
                        else:
                            cursor.execute(
                                "UPDATE bookings SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE booking_id = %s",
                                (target_status, ctx.entity_id),
                            )
                    else:
                        if current_status_raw is not None:
                            cursor.execute(
                                "UPDATE orders SET order_status = %s, updated_at = CURRENT_TIMESTAMP WHERE order_id = %s AND order_status = %s",
                                (target_status, ctx.entity_id, current_status_raw),
                            )
                        else:
                            cursor.execute(
                                "UPDATE orders SET order_status = %s, updated_at = CURRENT_TIMESTAMP WHERE order_id = %s",
                                (target_status, ctx.entity_id),
                            )
                    update_ok = cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to update status atomically: {e}")
                return False, False

            if not update_ok:
                latest = (
                    self.db.get_booking(ctx.entity_id)
                    if ctx.entity_type == "booking"
                    else self.db.get_order(ctx.entity_id)
                )
                latest_status_raw = None
                if isinstance(latest, dict):
                    latest_status_raw = (
                        latest.get("status")
                        if ctx.entity_type == "booking"
                        else latest.get("order_status")
                    )
                else:
                    latest_status_raw = (
                        getattr(latest, "status", None)
                        if ctx.entity_type == "booking"
                        else getattr(latest, "order_status", None)
                    )

                latest_status = (
                    OrderStatus.normalize(str(latest_status_raw))
                    if latest_status_raw
                    else None
                )
                if latest_status in terminal_statuses:
                    logger.info(
                        f"STATUS_UPDATE skipped due to race: #{ctx.entity_id} status={latest_status}"
                    )
                    return False, True
                return False, False
        else:
            if ctx.entity_type == "booking":
                if not hasattr(self.db, "update_booking_status"):
                    logger.warning("DB layer does not support update_booking_status")
                    return False, False
                self.db.update_booking_status(ctx.entity_id, target_status)
            else:
                if not hasattr(self.db, "update_order_status"):
                    logger.warning("DB layer does not support update_order_status")
                    return False, False
                self.db.update_order_status(ctx.entity_id, target_status)

        return True, False

    @staticmethod
    def _get_existing_message_id(entity: Any) -> int | None:
        if isinstance(entity, dict):
            return entity.get("customer_message_id")
        return getattr(entity, "customer_message_id", None)

    def _load_cart_items(
        self,
        is_cart: bool,
        cart_items_json: Any,
    ) -> list[dict[str, Any]] | None:
        if not is_cart or not cart_items_json:
            return None
        try:
            import json

            return (
                json.loads(cart_items_json)
                if isinstance(cart_items_json, str)
                else cart_items_json
            )
        except Exception:
            return None

    def _build_single_item_cart(
        self,
        *,
        offer_id: int,
        quantity: int,
        customer_lang: str,
        total_price: int | None,
        delivery_price: int,
        item_title: str | None = None,
        item_price: int | None = None,
    ) -> list[dict[str, Any]]:
        item_title = item_title or ""
        if hasattr(self.db, "get_offer"):
            if not item_title or item_price is None:
                offer = self.db.get_offer(int(offer_id))
                if isinstance(offer, dict):
                    item_title = item_title or offer.get("title", "")
                    if item_price is None:
                        item_price = offer.get("discount_price", None)
                else:
                    item_title = item_title or (getattr(offer, "title", "") if offer else "")
                    if item_price is None:
                        item_price = (
                            getattr(offer, "discount_price", None) if offer else None
                        )

        if not item_title:
            item_title = "Mahsulot" if customer_lang == "uz" else "Товар"

        if item_price is None and total_price is not None and quantity:
            try:
                item_price = int((float(total_price) - float(delivery_price)) / quantity)
            except Exception:
                item_price = 0

        return [
            {
                "offer_id": int(offer_id),
                "title": item_title,
                "quantity": int(quantity or 1),
                "price": int(item_price or 0),
            }
        ]

    def _load_grouped_orders(
        self,
        *,
        entity_type: str,
        existing_message_id: int | None,
        user_id: int | None,
    ) -> tuple[list[int] | None, list[str] | None]:
        if entity_type != "order" or not existing_message_id:
            return None, None

        orders_for_group = None
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
                        grouped_statuses.append(OrderStatus.normalize(str(raw_status)))
                return grouped_ids or None, grouped_statuses or None
            except Exception as group_err:
                logger.debug(f"Failed to load grouped order ids: {group_err}")
        return None, None

    @staticmethod
    def _aggregate_group_status(
        target_status: str,
        group_statuses: list[str] | None,
    ) -> str:
        if not group_statuses:
            return target_status
        unique_statuses = set(group_statuses)
        if unique_statuses == {OrderStatus.COMPLETED}:
            return OrderStatus.COMPLETED
        if OrderStatus.REJECTED in unique_statuses:
            return OrderStatus.REJECTED
        if OrderStatus.CANCELLED in unique_statuses:
            return OrderStatus.CANCELLED
        if OrderStatus.DELIVERING in unique_statuses:
            return OrderStatus.DELIVERING
        if OrderStatus.READY in unique_statuses:
            return OrderStatus.READY
        if OrderStatus.PREPARING in unique_statuses:
            return OrderStatus.PREPARING
        if OrderStatus.PENDING in unique_statuses:
            return OrderStatus.PENDING
        return target_status

    def _prepare_customer_status_message(
        self,
        *,
        entity_id: int,
        entity_type: str,
        order_type: str | None,
        store_name: str,
        store_phone: str | None,
        store_address: str,
        delivery_address: str | None,
        delivery_price: int,
        pickup_code: str | None,
        reject_reason: str | None,
        courier_phone: str | None,
        customer_lang: str,
        is_cart: bool,
        cart_items_json: Any,
        offer_id: int | None,
        quantity: int,
        total_price: int | None,
        item_title: str | None,
        item_price: int | None,
        existing_message_id: int | None,
        user_id: int | None,
        target_status: str,
        payment_method: str | None = None,
        payment_status: str | None = None,
        payment_proof_photo_id: str | None = None,
        ready_until: str | None = None,
    ) -> tuple[str, list[dict[str, Any]] | None, str | None, str, list[int] | None, bool]:
        normalized_order_type = "delivery" if order_type == "taxi" else (order_type or "delivery")
        currency = None
        cart_items = self._load_cart_items(is_cart, cart_items_json)
        if not cart_items and offer_id:
            cart_items = self._build_single_item_cart(
                offer_id=offer_id,
                quantity=quantity,
                customer_lang=customer_lang,
                total_price=total_price,
                delivery_price=delivery_price,
                item_title=item_title,
                item_price=item_price,
            )

        group_order_ids, group_statuses = self._load_grouped_orders(
            entity_type=entity_type,
            existing_message_id=existing_message_id,
            user_id=user_id,
        )

        is_grouped = False
        aggregated_status = target_status
        if cart_items:
            currency = "so'm" if customer_lang == "uz" else "сум"
            is_grouped = bool(group_order_ids and len(group_order_ids) > 1)
            if is_grouped and group_statuses:
                aggregated_status = self._aggregate_group_status(
                    target_status,
                    group_statuses,
                )

            msg = NotificationTemplates.customer_cart_status_update(
                lang=customer_lang,
                order_id=entity_id,
                status=aggregated_status,
                order_type=normalized_order_type,
                items=cart_items,
                currency=currency,
                is_cart=is_cart or is_grouped,
                order_ids=group_order_ids,
                store_name=store_name,
                store_phone=store_phone,
                store_address=store_address,
                delivery_address=delivery_address,
                delivery_price=delivery_price,
                pickup_code=pickup_code,
                reject_reason=reject_reason,
                courier_phone=courier_phone,
                payment_method=payment_method,
                payment_status=payment_status,
                payment_proof_photo_id=payment_proof_photo_id,
                ready_until=ready_until,
            )
        else:
            if currency is None:
                currency = "so'm" if customer_lang == "uz" else "сум"
            msg = NotificationTemplates.customer_status_update(
                lang=customer_lang,
                order_id=entity_id,
                status=target_status,
                order_type=normalized_order_type,
                store_name=store_name,
                store_phone=store_phone,
                store_address=store_address,
                pickup_code=pickup_code,
                reject_reason=reject_reason,
                courier_phone=courier_phone,
                items=cart_items,
                delivery_address=delivery_address,
                delivery_price=delivery_price,
                total=total_price,
                currency=currency,
                order_ids=group_order_ids,
                is_cart=is_cart,
                payment_method=payment_method,
                payment_status=payment_status,
                payment_proof_photo_id=payment_proof_photo_id,
                ready_until=ready_until,
            )

        return msg, cart_items, currency, aggregated_status, group_order_ids, is_grouped

    @staticmethod
    def _build_customer_reply_markup(
        *,
        target_status: str,
        new_status: str,
        order_type: str | None,
        customer_lang: str,
        entity_id: int,
        entity_type: str,
    ) -> Any:
        _ = new_status, entity_type
        normalized_type = "delivery" if order_type == "taxi" else (order_type or "delivery")
        kb = InlineKeyboardBuilder()
        if normalized_type == "delivery" and target_status == OrderStatus.DELIVERING:
            kb.button(
                text=get_text(customer_lang, "btn_order_received"),
                callback_data=f"customer_received_{entity_id}",
            )
        webapp_url = os.getenv("WEBAPP_URL", "").strip()
        if webapp_url:
            order_url = f"{webapp_url.rstrip('/')}/order/{entity_id}"
            kb.button(text=get_text(customer_lang, "btn_open_order"), web_app=WebAppInfo(url=order_url))
        else:
            kb.button(text=get_text(customer_lang, "btn_open_order"), callback_data=f"open_order_{entity_id}")
        kb.button(text=get_text(customer_lang, "btn_back_menu"), callback_data="back_to_menu")
        kb.adjust(1)
        return kb.as_markup()

    def _build_click_payment_reply_markup(
        self,
        *,
        order_ids: list[int],
        total_price: int,
        user_id: int,
        store_id: int | None,
        lang: str,
    ) -> Any:
        """Build inline Click payment button for unpaid delivery orders."""
        if not order_ids or not user_id:
            return None

        order_id = int(order_ids[0])

        payment_service = get_payment_service()
        if hasattr(payment_service, "set_database"):
            payment_service.set_database(self.db)

        credentials = None
        try:
            if store_id:
                credentials = payment_service.get_store_credentials(int(store_id), "click")
        except Exception:
            credentials = None

        if not credentials and not payment_service.click_enabled:
            return None

        order_total = None
        order_row = None
        try:
            if hasattr(self.db, "get_order"):
                order_row = self.db.get_order(int(order_id))
                if order_row:
                    if isinstance(order_row, dict):
                        order_total = order_row.get("total_price")
                        payment_status_raw = order_row.get("payment_status")
                        payment_method_raw = order_row.get("payment_method")
                    else:
                        order_total = getattr(order_row, "total_price", None)
                        payment_status_raw = getattr(order_row, "payment_status", None)
                        payment_method_raw = getattr(order_row, "payment_method", None)

                    normalized_status = PaymentStatus.normalize(
                        payment_status_raw, payment_method=payment_method_raw
                    )
                    if normalized_status == PaymentStatus.CONFIRMED:
                        return None
        except Exception:
            order_total = None

        amount = int(order_total or total_price or 0)
        if order_row:
            def _get_field(row, name, default=None):
                if isinstance(row, dict):
                    return row.get(name, default)
                return getattr(row, name, default)

            order_type = str(_get_field(order_row, "order_type", "") or "").lower()
            if not order_type:
                order_type = "delivery" if _get_field(order_row, "delivery_address") else "pickup"
            is_delivery = order_type in ("delivery", "taxi")
            if is_delivery:
                items_total = 0
                cart_items_raw = _get_field(order_row, "cart_items")
                if cart_items_raw:
                    try:
                        import json

                        cart_items = (
                            json.loads(cart_items_raw)
                            if isinstance(cart_items_raw, str)
                            else cart_items_raw
                        )
                    except Exception:
                        cart_items = None
                    if isinstance(cart_items, list):
                        for item in cart_items:
                            try:
                                price = int(item.get("price") or 0)
                            except Exception:
                                price = 0
                            try:
                                qty = int(item.get("quantity") or 1)
                            except Exception:
                                qty = 1
                            items_total += price * qty
                if items_total <= 0:
                    try:
                        qty = int(_get_field(order_row, "quantity", 1) or 1)
                    except Exception:
                        qty = 1
                    try:
                        price = int(_get_field(order_row, "item_price", 0) or 0)
                    except Exception:
                        price = 0
                    items_total = max(0, price * qty)
                if items_total > 0:
                    amount = items_total
        if amount <= 0:
            return None

        return_url = None
        try:
            webapp_url = os.getenv("WEBAPP_URL", "").strip()
            if webapp_url:
                return_url = f"{webapp_url.rstrip('/')}/order/{order_id}"
        except Exception:
            return_url = None

        try:
            payment_url = payment_service.generate_click_url(
                order_id=int(order_id),
                amount=int(amount),
                return_url=return_url,
                user_id=int(user_id),
                store_id=int(store_id) if store_id else 0,
            )
        except Exception as e:
            logger.error(f"Failed to generate Click link for order #{order_id}: {e}")
            return None

        kb = InlineKeyboardBuilder()
        kb.button(text=get_text(lang, "delivery_payment_click_button"), url=payment_url)
        return kb.as_markup()

    async def _send_or_edit_customer_message(
        self,
        *,
        user_id: int,
        entity_type: str,
        entity_id: int,
        msg: str,
        customer_photo: BufferedInputFile | str | None,
        reply_markup: Any,
        should_edit: bool,
        should_send: bool,
        existing_message_id: int | None,
        group_order_ids: list[int] | None = None,
    ) -> None:
        # Telegram caption limit is 1024 chars; keep photo updates from failing on long text.
        safe_caption = msg if len(msg) <= 1000 else msg[:1000].rstrip() + "..."
        if not (should_edit or should_send):
            return

        message_sent = None
        edit_success = False

        if should_edit and existing_message_id:
            logger.info(
                f"Trying to edit message {existing_message_id} for #{entity_id}"
            )

            try:
                await self.bot.edit_message_caption(
                    chat_id=user_id,
                    message_id=existing_message_id,
                    caption=safe_caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                edit_success = True
                logger.info(f"Edited CAPTION for {entity_type}#{entity_id}")
            except Exception as caption_error:
                logger.debug(f"Caption edit failed: {caption_error}")

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

        if not edit_success and should_send:
            try:
                if customer_photo:
                    try:
                        message_sent = await self.bot.send_photo(
                            user_id,
                            photo=customer_photo,
                            caption=safe_caption,
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
                if message_sent:
                    if entity_type == "order" and hasattr(
                        self.db, "set_order_customer_message_id"
                    ):
                        target_ids = group_order_ids or [entity_id]
                        for order_id in target_ids:
                            try:
                                self.db.set_order_customer_message_id(
                                    int(order_id), message_sent.message_id
                                )
                            except Exception as save_err:
                                logger.warning(
                                    "Failed to update customer_message_id for order %s: %s",
                                    order_id,
                                    save_err,
                                )
                        logger.info(
                            "Saved message_id={} for order_ids={}".format(
                                message_sent.message_id, target_ids
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

    def _get_seller_message_id(self, entity: Any) -> int | None:
        if isinstance(entity, dict):
            return entity.get("seller_message_id")
        return getattr(entity, "seller_message_id", None)

    def _load_customer_contact(self, user_id: int | None) -> tuple[str | None, str | None]:
        if not user_id:
            return None, None
        customer = (
            self.db.get_user_model(user_id)
            if hasattr(self.db, "get_user_model")
            else self.db.get_user(user_id)
            if hasattr(self.db, "get_user")
            else None
        )
        if isinstance(customer, dict):
            return customer.get("first_name") or customer.get("name"), customer.get("phone")
        return (
            getattr(customer, "first_name", None) if customer else None,
            getattr(customer, "phone", None) if customer else None,
        )

    def _build_seller_items_for_status(
        self,
        entity: Any,
    ) -> tuple[list[dict[str, Any]], int, int | None]:
        items: list[dict[str, Any]] = []
        total = 0
        cart_items_json = (
            entity.get("cart_items") if isinstance(entity, dict) else getattr(entity, "cart_items", None)
        )
        if cart_items_json:
            cart_items = self._load_cart_items(True, cart_items_json) or []
            for item in cart_items:
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
            return items, total, None

        offer_id = (
            entity.get("offer_id") if isinstance(entity, dict) else getattr(entity, "offer_id", None)
        )
        quantity = (
            entity.get("quantity", 1) if isinstance(entity, dict) else getattr(entity, "quantity", 1)
        )
        if offer_id:
            offer = self.db.get_offer(offer_id) if hasattr(self.db, "get_offer") else None
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
                    "title": title,
                    "quantity": int(quantity or 1),
                    "price": int(price or 0),
                    "offer_id": int(offer_id),
                    "photo": offer_photo,
                }
            )
            total = int(price or 0) * int(quantity or 1)
        return items, total, offer_id if offer_id else None

    @staticmethod
    def _resolve_seller_delivery_price(
        entity: Any,
        store: Any,
        resolved_order_type: str | None,
    ) -> int:
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
        return delivery_price

    @staticmethod
    def _build_seller_status_keyboard(
        seller_lang: str,
        resolved_order_type: str | None,
        target_status: str,
        entity_id: int,
        map_url: str | None = None,
    ) -> InlineKeyboardBuilder:
        kb = InlineKeyboardBuilder()
        rows: list[int] = []
        is_delivery = resolved_order_type in ("delivery", "taxi")

        if is_delivery:
            if target_status == OrderStatus.PENDING:
                kb.button(
                    text=get_text(seller_lang, "btn_order_accept"),
                    callback_data=f"order_confirm_{entity_id}",
                )
                kb.button(
                    text=get_text(seller_lang, "btn_order_reject"),
                    callback_data=f"order_reject_{entity_id}",
                )
                rows.append(2)
            elif target_status == OrderStatus.PREPARING:
                kb.button(
                    text=get_text(seller_lang, "btn_ready_for_delivery"),
                    callback_data=f"order_ready_{entity_id}",
                )
                rows.append(1)
            elif target_status == OrderStatus.READY:
                kb.button(
                    text=get_text(seller_lang, "btn_enter_courier_phone"),
                    callback_data=f"order_delivering_{entity_id}",
                )
                kb.button(
                    text=get_text(seller_lang, "btn_skip"),
                    callback_data=f"skip_courier_phone_{entity_id}",
                )
                rows.append(2)
        else:
            if target_status == OrderStatus.PENDING:
                kb.button(
                    text=get_text(seller_lang, "btn_order_accept"),
                    callback_data=f"order_confirm_{entity_id}",
                )
                kb.button(
                    text=get_text(seller_lang, "btn_order_reject"),
                    callback_data=f"order_reject_{entity_id}",
                )
                rows.append(2)
            elif target_status == OrderStatus.PREPARING:
                kb.button(
                    text=get_text(seller_lang, "btn_ready_for_pickup"),
                    callback_data=f"order_ready_{entity_id}",
                )
                rows.append(1)
            elif target_status == OrderStatus.READY:
                kb.button(
                    text=get_text(seller_lang, "btn_mark_issued"),
                    callback_data=f"order_complete_{entity_id}",
                )
                rows.append(1)

        if map_url and is_delivery and target_status in (
            OrderStatus.PENDING,
            OrderStatus.PREPARING,
            OrderStatus.READY,
        ):
            kb.button(text=get_text(seller_lang, "btn_map"), url=map_url)
            rows.append(1)

        if rows:
            kb.adjust(*rows)
        return kb

    async def _resolve_seller_photo(
        self,
        items: list[dict[str, Any]],
        offer_id: int | None,
    ) -> BufferedInputFile | str | None:
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
        return seller_photo

    async def _send_or_edit_seller_status_message(
        self,
        *,
        owner_id: int,
        seller_message_id: int | None,
        seller_text: str,
        reply_markup: Any,
        seller_photo: BufferedInputFile | str | None,
        entity_id: int,
    ) -> None:
        # Telegram caption limit is 1024 chars; avoid edit/send failures on long text.
        safe_caption = seller_text if len(seller_text) <= 1000 else seller_text[:1000].rstrip() + "..."
        if seller_message_id:
            try:
                await self.bot.edit_message_caption(
                    chat_id=owner_id,
                    message_id=seller_message_id,
                    caption=safe_caption,
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
            return

        if not self.force_telegram_sync:
            return

        try:
            sent_msg = None
            if seller_photo:
                try:
                    sent_msg = await self.bot.send_photo(
                        owner_id,
                        photo=seller_photo,
                        caption=safe_caption,
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

    async def _notify_status_change(
        self,
        ctx: StatusUpdateContext,
        target_status: str,
        normalized_payment_status: str,
        notify_customer: bool,
        reject_reason: str | None,
        courier_phone: str | None,
        new_status: str,
    ) -> None:
        entity = ctx.entity
        entity_type = ctx.entity_type
        entity_id = ctx.entity_id
        user_id = ctx.user_id
        store_id = ctx.store_id
        pickup_code = ctx.pickup_code
        order_type = ctx.order_type
        delivery_address = ctx.delivery_address
        delivery_price = ctx.delivery_price
        is_cart = ctx.is_cart
        cart_items_json = ctx.cart_items_json
        offer_id = ctx.offer_id
        quantity = ctx.quantity
        total_price = ctx.total_price

        normalized_order_type = order_type or ("delivery" if delivery_address else "pickup")
        if normalized_order_type == "taxi":
            normalized_order_type = "delivery"

        notifications_enabled = self._notifications_enabled(user_id)
        existing_message_id = self._get_existing_message_id(entity)
        should_edit = bool(existing_message_id) and bool(user_id)
        should_send_card = (
            bool(user_id)
            and not existing_message_id
            and (self.force_telegram_sync or self.telegram_order_notifications)
        )
        should_send_notification = bool(user_id) and bool(notify_customer) and notifications_enabled

        ready_until = None
        if normalized_order_type == "pickup" and target_status == OrderStatus.READY:
            ready_until = self._format_pickup_ready_until(get_uzb_time())

        customer_lang = self.db.get_user_language(user_id) if user_id else "ru"
        critical_text = (
            self._build_customer_notification(
                lang=customer_lang,
                order_id=entity_id,
                order_type=normalized_order_type,
                status=target_status,
                reject_reason=reject_reason,
                courier_phone=courier_phone,
            )
            if should_send_notification
            else None
        )

        logger.info(
            "Notification check for #%s: status=%s, order_type=%s, notify_customer=%s, "
            "user_id=%s, edit_card=%s, send_card=%s, critical=%s",
            entity_id,
            target_status,
            normalized_order_type,
            notify_customer,
            user_id,
            should_edit,
            should_send_card,
            bool(critical_text),
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
                    order_type=normalized_order_type,
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
                            "order_type": normalized_order_type,
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
                order_type=normalized_order_type,
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
                            "order_type": normalized_order_type,
                            "unified": partner_unified_min,
                        },
                        priority=0,
                    )
                )
            except Exception as notify_error:
                logger.warning(f"Store status notification failed: {notify_error}")

        if critical_text and user_id:
            try:
                await self.bot.send_message(int(user_id), critical_text)
            except Exception as notify_error:
                logger.warning(
                    "Failed to send critical notification for %s#%s: %s",
                    entity_type,
                    entity_id,
                    notify_error,
                )

        if should_edit or should_send_card:
            store = self.db.get_store(store_id) if store_id else None
            store_name = store.get("name", "") if isinstance(store, dict) else ""
            store_address = store.get("address", "") if isinstance(store, dict) else ""
            store_phone = (
                store.get("phone") if isinstance(store, dict) else getattr(store, "phone", None)
            )

            (
                msg,
                cart_items,
                currency,
                aggregated_status,
                group_order_ids,
                is_grouped,
            ) = self._prepare_customer_status_message(
                entity_id=entity_id,
                entity_type=entity_type,
                order_type=normalized_order_type,
                store_name=store_name,
                store_phone=store_phone,
                store_address=store_address,
                delivery_address=delivery_address,
                delivery_price=delivery_price,
                pickup_code=pickup_code,
                reject_reason=reject_reason,
                courier_phone=courier_phone,
                customer_lang=customer_lang,
                is_cart=is_cart,
                cart_items_json=cart_items_json,
                offer_id=offer_id,
                quantity=quantity,
                total_price=total_price,
                item_title=ctx.item_title,
                item_price=ctx.item_price,
                existing_message_id=existing_message_id,
                user_id=user_id,
                target_status=target_status,
                payment_method=ctx.payment_method,
                payment_status=ctx.payment_status,
                payment_proof_photo_id=ctx.payment_proof_photo_id,
                ready_until=ready_until,
            )

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

            group_order_ids, group_statuses = self._load_grouped_orders(
                entity_type=entity_type,
                existing_message_id=existing_message_id,
                user_id=user_id,
            )

            is_grouped = False
            aggregated_status = target_status
            if cart_items:
                currency = "so'm" if customer_lang == "uz" else "сум"
                is_grouped = bool(group_order_ids and len(group_order_ids) > 1)
                if is_grouped and group_statuses:
                    aggregated_status = self._aggregate_group_status(
                        target_status,
                        group_statuses,
                    )

                msg = NotificationTemplates.customer_cart_status_update(
                    lang=customer_lang,
                    order_id=entity_id,
                    status=aggregated_status,
                    order_type=normalized_order_type,
                    items=cart_items,
                    currency=currency,
                    is_cart=is_cart or is_grouped,
                    order_ids=group_order_ids,
                    store_name=store_name,
                    store_phone=store_phone,
                    store_address=store_address,
                    delivery_address=delivery_address,
                    delivery_price=delivery_price,
                    pickup_code=pickup_code,
                    reject_reason=reject_reason,
                    courier_phone=courier_phone,
                    payment_method=ctx.payment_method,
                    payment_status=ctx.payment_status,
                    payment_proof_photo_id=ctx.payment_proof_photo_id,
                    ready_until=ready_until,
                )
            else:
                if currency is None:
                    currency = "so'm" if customer_lang == "uz" else "сум"
                msg = NotificationTemplates.customer_status_update(
                    lang=customer_lang,
                    order_id=entity_id,
                    status=target_status,
                    order_type=normalized_order_type,
                    store_name=store_name,
                    store_phone=store_phone,
                    store_address=store_address,
                    pickup_code=pickup_code,
                    reject_reason=reject_reason,
                    courier_phone=courier_phone,
                    items=cart_items,
                    delivery_address=delivery_address,
                    delivery_price=delivery_price,
                    total=total_price,
                    currency=currency,
                    order_ids=group_order_ids,
                    is_cart=is_cart,
                    payment_method=ctx.payment_method,
                    payment_status=ctx.payment_status,
                    payment_proof_photo_id=ctx.payment_proof_photo_id,
                    ready_until=ready_until,
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
                order_type=normalized_order_type,
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
            if critical_text:
                try:
                    order_label = get_text(customer_lang, "label_order")
                    notif_title = f"{order_label} #{entity_id}"
                    if target_status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
                        notif_type = NotificationType.BOOKING_CANCELLED
                    elif target_status in (OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.DELIVERING):
                        notif_type = NotificationType.BOOKING_CONFIRMED
                    else:
                        notif_type = NotificationType.SYSTEM_ANNOUNCEMENT

                    notification_service = get_notification_service()
                    await notification_service.notify_user(
                        Notification(
                            type=notif_type,
                            recipient_id=int(user_id),
                            title=notif_title,
                            message=critical_text,
                            data={
                                "order_id": entity_id,
                                "status": target_status,
                                "order_type": normalized_order_type,
                                "entity_type": entity_type,
                                "unified": customer_unified_full,
                            },
                            priority=0,
                        )
                    )
                except Exception as notify_error:
                    logger.warning(
                        "Notification service failed for %s#%s: %s",
                        entity_type,
                        entity_id,
                        notify_error,
                    )

            # Add buttons for customer based on status
            reply_markup = self._build_customer_reply_markup(
                target_status=target_status,
                new_status=new_status,
                order_type=normalized_order_type,
                customer_lang=customer_lang,
                entity_id=entity_id,
                entity_type=entity_type,
            )

            await self._send_or_edit_customer_message(
                user_id=int(user_id),
                entity_type=entity_type,
                entity_id=entity_id,
                msg=msg,
                customer_photo=customer_photo,
                reply_markup=reply_markup,
                should_edit=should_edit,
                should_send=should_send_card,
                existing_message_id=existing_message_id,
                group_order_ids=group_order_ids,
            )

        # Send rating prompt once the order is completed.
        if (
            user_id
            and entity_type == "order"
            and target_status == OrderStatus.COMPLETED
        ):
            try:
                already_rated = False
                if hasattr(self.db, "has_rated_order"):
                    already_rated = bool(self.db.has_rated_order(int(entity_id)))
                if not already_rated:
                    prompt = (
                        f"{get_text(customer_lang, 'order_completed_thanks')}\n"
                        f"{get_text(customer_lang, 'order_rating_prompt')}"
                    )
                    kb = InlineKeyboardBuilder()
                    for i in range(1, 6):
                        kb.button(text="⭐" * i, callback_data=f"rate_order_{entity_id}_{i}")
                    kb.adjust(5)
                    await self.bot.send_message(
                        int(user_id),
                        prompt,
                        parse_mode="HTML",
                        reply_markup=kb.as_markup(),
                    )
            except Exception as notify_error:
                logger.warning(
                    "Failed to send rating prompt for order %s: %s",
                    entity_id,
                    notify_error,
                )

        # Update seller message in Telegram if it exists (partner bot sync) if it exists (partner bot sync)
        if entity_type == "order":
            try:
                seller_message_id = self._get_seller_message_id(entity)
                if store_id:
                    store = self.db.get_store(store_id) if store_id else None
                    owner_id = store.get("owner_id") if isinstance(store, dict) else None
                    if owner_id and (seller_message_id or self.force_telegram_sync):
                        seller_lang = self.db.get_user_language(owner_id)
                        currency = "so'm" if seller_lang == "uz" else "sum"

                        customer_name, customer_phone = self._load_customer_contact(user_id)

                        resolved_order_type = order_type or (
                            "delivery" if delivery_address else "pickup"
                        )

                        items, total, offer_id = self._build_seller_items_for_status(entity)
                        delivery_price = self._resolve_seller_delivery_price(
                            entity,
                            store,
                            resolved_order_type,
                        )
                        created_at = get_order_field(entity, "created_at")
                        map_url = None
                        if resolved_order_type in ("delivery", "taxi") and target_status in (
                            OrderStatus.PENDING,
                            OrderStatus.PREPARING,
                            OrderStatus.READY,
                        ):
                            if isinstance(entity, dict):
                                delivery_lat = entity.get("delivery_lat")
                                delivery_lon = entity.get("delivery_lon")
                            else:
                                delivery_lat = getattr(entity, "delivery_lat", None)
                                delivery_lon = getattr(entity, "delivery_lon", None)
                            map_url, _ = await self._resolve_delivery_map(
                                is_delivery=True,
                                delivery_address=delivery_address,
                                delivery_lat=delivery_lat,
                                delivery_lon=delivery_lon,
                            )

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
                            payment_method=ctx.payment_method,
                            payment_status=normalized_payment_status,
                            payment_proof_photo_id=ctx.payment_proof_photo_id,
                            created_at=created_at,
                        )
                        seller_photo = await self._resolve_seller_photo(items, offer_id)

                        kb = self._build_seller_status_keyboard(
                            seller_lang=seller_lang,
                            resolved_order_type=resolved_order_type,
                            target_status=target_status,
                            entity_id=entity_id,
                            map_url=map_url,
                        )
                        reply_markup = kb.as_markup() if kb.buttons else None

                        await self._send_or_edit_seller_status_message(
                            owner_id=owner_id,
                            seller_message_id=seller_message_id,
                            seller_text=seller_text,
                            reply_markup=reply_markup,
                            seller_photo=seller_photo,
                            entity_id=entity_id,
                        )
            except Exception as seller_error:
                logger.warning(
                    f"Seller message update skipped for order#{entity_id}: {seller_error}"
                )

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
            ctx = self._get_status_update_context(
                entity_id=entity_id,
                entity_type=entity_type,
            )
            if not ctx:
                return False

            # Normalize statuses and enforce safe transitions/idempotence
            current_status = (
                OrderStatus.normalize(str(ctx.current_status_raw))
                if ctx.current_status_raw
                else None
            )
            target_status = OrderStatus.normalize(str(new_status))
            normalized_payment_method = PaymentStatus.normalize_method(ctx.payment_method)
            normalized_payment_status = PaymentStatus.normalize(
                ctx.payment_status, payment_method=ctx.payment_method
            )
            terminal_statuses = {
                OrderStatus.COMPLETED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
            }

            payment_cleared = (
                normalized_payment_method == "cash"
                or PaymentStatus.is_cleared(
                    ctx.payment_status,
                    payment_method=ctx.payment_method,
                    payment_proof_photo_id=ctx.payment_proof_photo_id,
                )
            )
            if target_status in (
                OrderStatus.READY,
                OrderStatus.DELIVERING,
                OrderStatus.COMPLETED,
            ) and not payment_cleared:
                logger.info(
                    f"STATUS_UPDATE blocked due to unpaid order: #{entity_id} "
                    f"status={current_status} -> {target_status}, "
                    f"payment_status={normalized_payment_status}, method={normalized_payment_method}"
                )
                return False

            # Idempotent update: requested status already set
            if current_status == target_status:
                logger.info(f"STATUS_UPDATE no-op (already {target_status}): #{entity_id}")
                return True

            if (
                ctx.entity_type == "order"
                and normalized_payment_method in ("click", "payme")
                and normalized_payment_status != PaymentStatus.CONFIRMED
                and target_status not in (OrderStatus.CANCELLED, OrderStatus.REJECTED)
            ):
                logger.info(
                    "STATUS_UPDATE blocked: payment not confirmed for #%s (target=%s)",
                    entity_id,
                    target_status,
                )
                return False

            # Do not move away from terminal statuses (completed/cancelled/rejected)
            if current_status in terminal_statuses and target_status != current_status:
                logger.info(
                    f"STATUS_UPDATE ignored for terminal entity: #{entity_id} "
                    f"status={current_status} -> {target_status}"
                )
                return True

            if target_status == OrderStatus.DELIVERING:
                if ctx.order_type not in ("delivery", "taxi"):
                    logger.info(
                        f"STATUS_UPDATE invalid delivering for pickup: #{entity_id} order_type={ctx.order_type}"
                    )
                    return False

            update_ok, short_circuit = self._apply_status_update(
                ctx=ctx,
                target_status=target_status,
                current_status_raw=ctx.current_status_raw,
                terminal_statuses=terminal_statuses,
            )
            if short_circuit:
                return True
            if not update_ok:
                return False

            # Restore quantity if rejected or cancelled
            if target_status in [OrderStatus.REJECTED, OrderStatus.CANCELLED] and (
                current_status not in [OrderStatus.REJECTED, OrderStatus.CANCELLED]
            ):
                if update_ok:
                    await self._restore_quantities(ctx.entity, ctx.entity_type)
                if (
                    ctx.entity_type == "order"
                    and normalized_payment_status == PaymentStatus.CONFIRMED
                ):
                    await self._flag_refund_required(
                        ctx=ctx,
                        target_status=target_status,
                        reject_reason=reject_reason,
                    )

            await self._notify_status_change(
                ctx=ctx,
                target_status=target_status,
                normalized_payment_status=normalized_payment_status,
                notify_customer=notify_customer,
                reject_reason=reject_reason,
                courier_phone=courier_phone,
                new_status=new_status,
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
                pickup_time = entity.get("pickup_time")
                store_id = entity.get("store_id")
            else:
                is_cart = (
                    getattr(entity, "is_cart_order", 0) == 1
                    or getattr(entity, "is_cart_booking", 0) == 1
                )
                cart_items_json = getattr(entity, "cart_items", None)
                offer_id = getattr(entity, "offer_id", None)
                quantity = getattr(entity, "quantity", 1)
                pickup_time = getattr(entity, "pickup_time", None)
                store_id = getattr(entity, "store_id", None)

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
                        except Exception as e:
                            logger.warning(
                                "Failed to restore quantity for offer %s (qty=%s): %s",
                                item_offer_id,
                                item_qty,
                                e,
                            )
            elif offer_id:
                try:
                    self.db.increment_offer_quantity_atomic(offer_id, int(quantity))
                except Exception as e:
                    logger.warning(
                        "Failed to restore quantity for offer %s (qty=%s): %s",
                        offer_id,
                        quantity,
                        e,
                    )

            # Release pickup slot capacity for bookings (best-effort).
            if (
                entity_type == "booking"
                and pickup_time
                and store_id
                and hasattr(self.db, "release_pickup_slot")
            ):
                try:
                    self.db.release_pickup_slot(int(store_id), pickup_time, int(quantity or 0))
                except Exception as e:
                    logger.warning(
                        "Failed to release pickup slot for store %s (time=%s, qty=%s): %s",
                        store_id,
                        pickup_time,
                        quantity,
                        e,
                    )

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
        """Seller confirms an order."""
        target_status = OrderStatus.PREPARING
        return await self.update_status(
            entity_id=entity_id,
            entity_type=entity_type,
            new_status=target_status,
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
        reason: str | None = None,
    ) -> bool:
        """Customer cancels an order."""
        return await self.update_status(
            entity_id=entity_id,
            entity_type=entity_type,
            new_status=OrderStatus.CANCELLED,
            notify_customer=True,
            reject_reason=reason,
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
