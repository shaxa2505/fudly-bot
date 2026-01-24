"""Use case: reject payment proof for an order."""
from __future__ import annotations

from typing import Any

from app.application.orders.confirm_payment import PaymentDecisionResult
from app.domain.order import OrderStatus, PaymentStatus


async def reject_payment(
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

    await order_service.update_status(
        entity_id=order_id,
        entity_type="order",
        new_status=OrderStatus.REJECTED,
        notify_customer=False,
        reject_reason="payment_rejected_by_admin",
    )

    if hasattr(repo, "update_payment_status"):
        repo.update_payment_status(order_id, PaymentStatus.REJECTED)

    return PaymentDecisionResult(True, order=order, payment_status=PaymentStatus.REJECTED)
