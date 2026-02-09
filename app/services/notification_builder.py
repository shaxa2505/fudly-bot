"""
Notification Builder - unified order cards for customer/seller updates.

Provides a single interface for pickup and delivery orders with
consistent structure and optional detail blocks.
"""
from __future__ import annotations

import html
import os
from typing import Literal

from app.domain.order import PaymentStatus
from app.domain.order_labels import normalize_order_status, status_label
from localization import get_text


class NotificationBuilder:
    """Unified notification builder for order cards."""

    def __init__(self, order_type: Literal["pickup", "delivery"]):
        """Initialize builder for a specific order type."""
        self.order_type = order_type

    def _esc(self, text: str | None) -> str:
        """HTML-escape helper."""
        return html.escape(str(text)) if text else ""

    def _type_label(self, lang: str) -> str:
        if lang == "uz":
            return "Olib ketish" if self.order_type == "pickup" else "Yetkazib berish"
        return "Самовывоз" if self.order_type == "pickup" else "Доставка"

    def _payment_label(self, lang: str, payment_method: str | None) -> str | None:
        if not payment_method:
            return None
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

    def _payment_status_label(
        self,
        lang: str,
        payment_status: str | None,
        payment_method: str | None,
        *,
        payment_proof_photo_id: str | None = None,
    ) -> str | None:
        if not payment_method:
            return None
        normalized = PaymentStatus.normalize(
            payment_status,
            payment_method=payment_method,
            payment_proof_photo_id=payment_proof_photo_id,
        )
        if normalized is None:
            normalized = PaymentStatus.initial_for_method(payment_method)
        if normalized == PaymentStatus.CONFIRMED:
            return get_text(lang, "payment_status_confirmed")
        if normalized == PaymentStatus.NOT_REQUIRED:
            return get_text(lang, "payment_status_not_required")
        if normalized == PaymentStatus.AWAITING_PAYMENT:
            return get_text(lang, "payment_status_awaiting_payment")
        if normalized == PaymentStatus.AWAITING_PROOF:
            return get_text(lang, "payment_status_awaiting_proof")
        if normalized == PaymentStatus.PROOF_SUBMITTED:
            return get_text(lang, "payment_status_proof_submitted")
        if normalized == PaymentStatus.REJECTED:
            return get_text(lang, "payment_status_rejected")
        return None

    def _status_label(self, status: str, lang: str) -> str:
        return status_label(status, lang, self.order_type)

    def _build_card(
        self,
        *,
        role: Literal["customer", "seller"],
        status: str,
        lang: str,
        order_id: int,
        order_ids: list[int] | None = None,
        is_cart: bool = False,
        store_name: str = "",
        store_phone: str | None = None,
        store_address: str | None = None,
        delivery_address: str | None = None,
        pickup_code: str | None = None,
        reject_reason: str | None = None,
        courier_phone: str | None = None,
        items: list[dict] | None = None,
        delivery_price: int = 0,
        total: int | None = None,
        currency: str = "UZS",
        payment_method: str | None = None,
        payment_status: str | None = None,
        payment_proof_photo_id: str | None = None,
        customer_name: str | None = None,
        customer_phone: str | None = None,
        comment: str | None = None,
        map_url: str | None = None,
        max_items: int = 3,
    ) -> str:
        type_label = self._type_label(lang)
        status_text = self._status_label(status, lang)
        normalized_status = normalize_order_status(status)
        if self.order_type == "pickup" and normalized_status == "preparing":
            normalized_status = "ready"

        group_ids = sorted({int(x) for x in (order_ids or []) if x})
        is_group = bool(is_cart or (len(group_ids) > 1))

        title_label = get_text(lang, "label_cart") if is_group else get_text(lang, "label_order")
        header = (
            f"🧾 {title_label} — {type_label}"
            if is_group
            else f"🧾 {title_label} #{order_id} — {type_label}"
        )

        lines: list[str] = [header]
        if normalized_status in ("cancelled", "rejected"):
            banner_key = "order_cancelled_bold" if normalized_status == "cancelled" else "order_rejected_bold"
            banner = get_text(lang, banner_key)
            if banner:
                lines.append(banner)
        lines.append(f"{get_text(lang, 'label_status')}: {status_text}")

        payment_text = self._payment_label(lang, payment_method)
        payment_status_text = self._payment_status_label(
            lang,
            payment_status,
            payment_method,
            payment_proof_photo_id=payment_proof_photo_id,
        )
        if payment_text:
            if payment_status_text:
                lines.append(f"{payment_text} — <b>{payment_status_text}</b>")
            else:
                lines.append(payment_text)

        if role == "customer" and self.order_type == "pickup" and normalized_status == "ready":
            ready_hours = int(os.getenv("PICKUP_READY_EXPIRY_HOURS", "2"))
            lines.append(
                get_text(lang, "pickup_ready_notice", hours=str(ready_hours))
            )

        if is_group and group_ids:
            max_show = 5
            shown = group_ids[:max_show]
            suffix = f" +{len(group_ids) - max_show}" if len(group_ids) > max_show else ""
            ids_text = ", ".join([f"#{oid}" for oid in shown]) + suffix
            lines.append(f"{get_text(lang, 'label_orders')}: {ids_text}")

        if store_name:
            lines.append(f"{get_text(lang, 'label_store')}: {self._esc(store_name)}")
        if role == "customer" and store_phone:
            lines.append(
                f"{get_text(lang, 'label_store_phone')}: <code>{self._esc(store_phone)}</code>"
            )

        if self.order_type == "delivery":
            if delivery_address:
                lines.append(f"{get_text(lang, 'address')}: {self._esc(delivery_address)}")
            if courier_phone:
                lines.append(
                    f"{get_text(lang, 'label_courier')}: <code>{self._esc(courier_phone)}</code>"
                )
        else:
            if store_address:
                lines.append(f"{get_text(lang, 'address')}: {self._esc(store_address)}")
            if pickup_code:
                lines.append(f"{get_text(lang, 'label_code')}: <b>{self._esc(pickup_code)}</b>")

        if role == "seller":
            if customer_name:
                lines.append(f"{get_text(lang, 'label_customer')}: {self._esc(customer_name)}")
            if customer_phone:
                lines.append(f"{get_text(lang, 'phone')}: <code>{self._esc(customer_phone)}</code>")
            if comment:
                lines.append(f"{get_text(lang, 'label_comment')}: {self._esc(comment)}")
            if map_url:
                open_label = get_text(lang, "label_open")
                lines.append(
                    f"{get_text(lang, 'label_map')}: <a href=\"{html.escape(map_url)}\">{open_label}</a>"
                )

        items_total = 0
        if items:
            items_parts: list[str] = []
            for item in items[:max_items]:
                title = self._esc(item.get("title", ""))
                qty = int(item.get("quantity", 1))
                price = int(item.get("price", 0))
                subtotal = price * qty
                items_total += subtotal
                items_parts.append(f"{title} × {qty}")
            if len(items) > max_items:
                extra = len(items) - max_items
                items_parts.append(get_text(lang, "label_items_more", count=str(extra)))
            lines.append(f"{get_text(lang, 'label_items')}: " + "; ".join(items_parts))

        total_value = int(total or 0)
        if total_value == 0 and items_total:
            total_value = items_total
        if self.order_type == "delivery" and delivery_price:
            delivery_fee_val = int(delivery_price)
            lines.append(
                f"{get_text(lang, 'label_delivery_fee')}: {delivery_fee_val:,} {currency}"
            )
            if total_value:
                # Avoid double-counting delivery if total already includes it.
                if not (items_total and total_value >= (items_total + delivery_fee_val)):
                    total_value += delivery_fee_val
            else:
                total_value = (items_total or 0) + delivery_fee_val

        if total_value:
            lines.append(f"{get_text(lang, 'label_total')}: <b>{total_value:,} {currency}</b>")

        if reject_reason and status in ("rejected", "cancelled"):
            lines.append(f"{get_text(lang, 'label_reason')}: {self._esc(reject_reason)}")

        return "\n".join(lines)

    def build(
        self,
        status: str,
        lang: str,
        order_id: int,
        store_name: str = "",
        store_phone: str | None = None,
        store_address: str | None = None,
        pickup_code: str | None = None,
        reject_reason: str | None = None,
        courier_phone: str | None = None,
        delivery_address: str | None = None,
        items: list[dict] | None = None,
        delivery_price: int = 0,
        total: int | None = None,
        currency: str = "UZS",
        payment_method: str | None = None,
        payment_status: str | None = None,
        payment_proof_photo_id: str | None = None,
        order_ids: list[int] | None = None,
        is_cart: bool = False,
        customer_name: str | None = None,
        customer_phone: str | None = None,
        comment: str | None = None,
        map_url: str | None = None,
        role: Literal["customer", "seller"] = "customer",
    ) -> str:
        """Build notification for any status."""
        return self._build_card(
            role=role,
            status=status,
            lang=lang,
            order_id=order_id,
            order_ids=order_ids,
            is_cart=is_cart,
            store_name=store_name,
            store_phone=store_phone,
            store_address=store_address,
            delivery_address=delivery_address,
            pickup_code=pickup_code,
            reject_reason=reject_reason,
            courier_phone=courier_phone,
            items=items,
            delivery_price=delivery_price,
            total=total,
            currency=currency,
            payment_method=payment_method,
            payment_status=payment_status,
            payment_proof_photo_id=payment_proof_photo_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            comment=comment,
            map_url=map_url,
        )

    def build_created(
        self,
        *,
        lang: str,
        order_id: int,
        order_ids: list[int] | None = None,
        is_cart: bool = False,
        store_name: str = "",
        store_phone: str | None = None,
        store_address: str | None = None,
        delivery_address: str | None = None,
        pickup_code: str | None = None,
        items: list[dict] | None = None,
        delivery_price: int = 0,
        total: int | None = None,
        currency: str = "UZS",
        payment_method: str | None = None,
        payment_status: str | None = None,
        payment_proof_photo_id: str | None = None,
        role: Literal["customer", "seller"] = "customer",
        customer_name: str | None = None,
        customer_phone: str | None = None,
        comment: str | None = None,
        map_url: str | None = None,
    ) -> str:
        """Build a consistent card for order creation."""
        return self._build_card(
            role=role,
            status="pending",
            lang=lang,
            order_id=order_id,
            order_ids=order_ids,
            is_cart=is_cart,
            store_name=store_name,
            store_phone=store_phone,
            store_address=store_address,
            delivery_address=delivery_address,
            pickup_code=pickup_code,
            items=items,
            delivery_price=delivery_price,
            total=total,
            currency=currency,
            payment_method=payment_method,
            payment_status=payment_status,
            payment_proof_photo_id=payment_proof_photo_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            comment=comment,
            map_url=map_url,
        )

    # Backward-compatible helpers
    def build_pending(self, lang: str, order_id: int, store_name: str) -> str:
        return self.build(status="pending", lang=lang, order_id=order_id, store_name=store_name)

    def build_preparing(
        self,
        lang: str,
        order_id: int,
        store_name: str,
        store_address: str | None = None,
        pickup_code: str | None = None,
    ) -> str:
        return self.build(
            status="preparing",
            lang=lang,
            order_id=order_id,
            store_name=store_name,
            store_address=store_address,
            pickup_code=pickup_code,
        )

    def build_ready(
        self,
        lang: str,
        order_id: int,
        store_name: str,
        store_address: str | None = None,
        pickup_code: str | None = None,
    ) -> str:
        return self.build(
            status="ready",
            lang=lang,
            order_id=order_id,
            store_name=store_name,
            store_address=store_address,
            pickup_code=pickup_code,
        )

    def build_delivering(
        self,
        lang: str,
        order_id: int,
        courier_phone: str | None = None,
        store_name: str | None = None,
    ) -> str:
        return self.build(
            status="delivering",
            lang=lang,
            order_id=order_id,
            store_name=store_name or "",
            courier_phone=courier_phone,
        )

    def build_completed(self, lang: str, order_id: int, store_name: str) -> str:
        return self.build(status="completed", lang=lang, order_id=order_id, store_name=store_name)

    def build_rejected(self, lang: str, order_id: int, reason: str | None = None) -> str:
        return self.build(
            status="rejected",
            lang=lang,
            order_id=order_id,
            reject_reason=reason,
        )

    def build_cancelled(self, lang: str, order_id: int) -> str:
        return self.build(status="cancelled", lang=lang, order_id=order_id)


class ProgressBar:
    """Legacy progress bar helpers used by internal dev scripts."""

    @staticmethod
    def pickup(step: int, lang: str) -> str:
        return "■" * max(0, min(step, 2)) + "□" * max(0, 2 - min(step, 2))

    @staticmethod
    def delivery(step: int, lang: str) -> str:
        return "■" * max(0, min(step, 3)) + "□" * max(0, 3 - min(step, 3))

    @staticmethod
    def delivery_labels(lang: str) -> str:
        return "1-2-3" if lang == "uz" else "1-2-3"
