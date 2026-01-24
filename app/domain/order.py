"""Order domain types and status enums."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class OrderStatus:
    """Unified order lifecycle statuses."""

    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

    @classmethod
    def normalize(cls, status: str) -> str:
        mapping = {
            "confirmed": cls.PREPARING,
            "new": cls.PENDING,
            "awaiting_payment": cls.PENDING,
            "awaiting_admin_confirmation": cls.PENDING,
            "paid": cls.PENDING,
        }
        return mapping.get(status, status)


class PaymentStatus:
    """Payment lifecycle status stored in orders.payment_status."""

    NOT_REQUIRED = "not_required"
    AWAITING_PAYMENT = "awaiting_payment"
    AWAITING_PROOF = "awaiting_proof"
    PROOF_SUBMITTED = "proof_submitted"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"

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
        if payment_status is None:
            return None

        status = str(payment_status).strip().lower()
        method = cls.normalize_method(payment_method)

        legacy_map = {
            "paid": cls.CONFIRMED,
            "payment_rejected": cls.REJECTED,
            "awaiting_admin_confirmation": cls.PROOF_SUBMITTED,
        }
        if status in legacy_map:
            return legacy_map[status]

        if status in ("pending", ""):
            if method == "cash":
                return cls.NOT_REQUIRED
            if payment_proof_photo_id:
                return cls.PROOF_SUBMITTED
            if method in ("click", "payme"):
                return cls.AWAITING_PAYMENT
            return cls.AWAITING_PROOF

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


@dataclass(frozen=True)
class OrderSnapshot:
    order_id: int
    user_id: int | None
    store_id: int | None
    offer_id: int | None
    order_status: str | None
    payment_status: str | None
    payment_method: str | None
    payment_proof_photo_id: str | None
    order_type: str | None
    total_price: int | None
    delivery_address: str | None
    quantity: int | None
    cart_items: Any | None
    item_title: str | None
    item_price: int | None
    delivery_price: int | None

    @classmethod
    def from_row(
        cls,
        row: Any,
        *,
        get_field: Callable[[Any, str, Any], Any],
    ) -> "OrderSnapshot":
        return cls(
            order_id=int(get_field(row, "order_id", 0)),
            user_id=get_field(row, "user_id"),
            store_id=get_field(row, "store_id"),
            offer_id=get_field(row, "offer_id"),
            order_status=get_field(row, "order_status"),
            payment_status=get_field(row, "payment_status"),
            payment_method=get_field(row, "payment_method"),
            payment_proof_photo_id=get_field(row, "payment_proof_photo_id"),
            order_type=get_field(row, "order_type"),
            total_price=get_field(row, "total_price"),
            delivery_address=get_field(row, "delivery_address"),
            quantity=get_field(row, "quantity"),
            cart_items=get_field(row, "cart_items"),
            item_title=get_field(row, "item_title"),
            item_price=get_field(row, "item_price"),
            delivery_price=get_field(row, "delivery_price"),
        )
