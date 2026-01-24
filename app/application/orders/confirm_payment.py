"""Use case: confirm payment proof for an order."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.order import PaymentStatus


@dataclass
class PaymentDecisionResult:
    ok: bool
    error_key: str | None = None
    order: Any | None = None
    payment_status: str | None = None


async def confirm_payment(
    order_id: int,
    *,
    repo: Any,
    order_service: Any | None,
) -> PaymentDecisionResult:
    if not repo:
        return PaymentDecisionResult(False, "db_error")

    order = repo.get_order(order_id)
    if not order:
        return PaymentDecisionResult(False, "not_found")

    payment_status = PaymentStatus.normalize(
        repo.get_field(order, "payment_status"),
        payment_method=repo.get_field(order, "payment_method"),
        payment_proof_photo_id=repo.get_field(order, "payment_proof_photo_id"),
    )

    if payment_status not in (PaymentStatus.PROOF_SUBMITTED, PaymentStatus.AWAITING_PROOF):
        return PaymentDecisionResult(
            False,
            "already_processed",
            order=order,
            payment_status=payment_status,
        )

    if not order_service:
        return PaymentDecisionResult(False, "service_unavailable", order=order)

    ok = await order_service.confirm_payment(order_id)
    if not ok:
        return PaymentDecisionResult(
            False,
            "processing_error",
            order=order,
            payment_status=payment_status,
        )

    return PaymentDecisionResult(True, order=order, payment_status=PaymentStatus.CONFIRMED)
