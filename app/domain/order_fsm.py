"""Order status transition rules (single source of truth)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.domain.order import OrderStatus, PaymentStatus


ALLOWED_TRANSITIONS: Mapping[str, frozenset[str]] = {
    OrderStatus.PENDING: frozenset(
        {
            OrderStatus.PREPARING,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
        }
    ),
    OrderStatus.PREPARING: frozenset(
        {
            OrderStatus.READY,
            OrderStatus.CANCELLED,
        }
    ),
    OrderStatus.READY: frozenset(
        {
            OrderStatus.DELIVERING,
            OrderStatus.COMPLETED,
        }
    ),
    OrderStatus.DELIVERING: frozenset({OrderStatus.COMPLETED}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
}

TERMINAL_STATUSES = frozenset(
    {
        OrderStatus.COMPLETED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
    }
)

PAYMENT_REQUIRED_STATUSES = frozenset(
    {
        OrderStatus.READY,
        OrderStatus.DELIVERING,
        OrderStatus.COMPLETED,
    }
)


@dataclass(frozen=True, slots=True)
class TransitionValidationResult:
    allowed: bool
    reason: str | None = None


def _normalize_order_type(order_type: str | None) -> str:
    return "delivery" if str(order_type or "").strip().lower() in {"delivery", "taxi"} else "pickup"


def validate_order_transition(
    *,
    current_status: str | None,
    target_status: str,
    order_type: str | None,
    payment_method: str | None,
    payment_status: str | None,
    payment_proof_photo_id: str | None = None,
) -> TransitionValidationResult:
    """Validate terminal/payment/type guards and FSM transition matrix."""
    if not target_status:
        return TransitionValidationResult(False, "Новый статус не указан.")

    target = OrderStatus.normalize(str(target_status).strip().lower())
    current = (
        OrderStatus.normalize(str(current_status).strip().lower())
        if current_status is not None
        else None
    )
    normalized_type = _normalize_order_type(order_type)

    if target not in ALLOWED_TRANSITIONS:
        return TransitionValidationResult(False, f"Неподдерживаемый статус: {target}")

    if current is not None and current not in ALLOWED_TRANSITIONS:
        return TransitionValidationResult(False, f"Неподдерживаемый текущий статус: {current}")

    if current == target:
        return TransitionValidationResult(True)

    if current in TERMINAL_STATUSES:
        return TransitionValidationResult(
            False,
            f"Нельзя изменить терминальный статус '{current}'.",
        )

    if current is not None:
        allowed_targets = ALLOWED_TRANSITIONS.get(current, frozenset())
        if target not in allowed_targets:
            return TransitionValidationResult(
                False,
                f"Переход '{current} -> {target}' запрещён.",
            )

    payment_method_norm = PaymentStatus.normalize_method(payment_method)
    payment_cleared = payment_method_norm == "cash" or PaymentStatus.is_cleared(
        payment_status,
        payment_method=payment_method,
        payment_proof_photo_id=payment_proof_photo_id,
    )
    if target in PAYMENT_REQUIRED_STATUSES and not payment_cleared:
        return TransitionValidationResult(
            False,
            "Нельзя перевести заказ в этот статус до подтверждения оплаты.",
        )

    if target == OrderStatus.DELIVERING and normalized_type != "delivery":
        return TransitionValidationResult(False, "Статус 'delivering' доступен только для доставки.")

    if (
        normalized_type == "delivery"
        and current == OrderStatus.READY
        and target == OrderStatus.COMPLETED
    ):
        return TransitionValidationResult(
            False,
            "Для доставки сначала переведите заказ в статус 'delivering'.",
        )

    return TransitionValidationResult(True)
