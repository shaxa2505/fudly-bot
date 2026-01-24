"""Use case: submit payment proof for an order."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.order import PaymentStatus


@dataclass
class PaymentProofResult:
    ok: bool
    error_key: str | None = None
    order: Any | None = None
    payment_status: str | None = None


async def submit_payment_proof(
    order_id: int,
    *,
    actor_user_id: int | None,
    proof_file_id: str,
    repo: Any,
) -> PaymentProofResult:
    if not repo:
        return PaymentProofResult(False, "db_error")

    order = repo.get_order(order_id)
    if not order:
        return PaymentProofResult(False, "not_found")

    order_user_id = repo.get_field(order, "user_id")
    if actor_user_id and order_user_id != actor_user_id:
        return PaymentProofResult(False, "forbidden", order=order)

    payment_status = PaymentStatus.normalize(
        repo.get_field(order, "payment_status"),
        payment_method=repo.get_field(order, "payment_method"),
        payment_proof_photo_id=repo.get_field(order, "payment_proof_photo_id"),
    )

    if payment_status == PaymentStatus.PROOF_SUBMITTED:
        return PaymentProofResult(False, "already_submitted", order=order, payment_status=payment_status)
    if payment_status == PaymentStatus.CONFIRMED:
        return PaymentProofResult(False, "already_confirmed", order=order, payment_status=payment_status)
    if payment_status == PaymentStatus.NOT_REQUIRED:
        return PaymentProofResult(False, "not_required", order=order, payment_status=payment_status)
    if payment_status not in (PaymentStatus.AWAITING_PROOF, PaymentStatus.REJECTED):
        return PaymentProofResult(False, "not_allowed", order=order, payment_status=payment_status)

    try:
        repo.update_payment_status(order_id, PaymentStatus.PROOF_SUBMITTED, proof_file_id)
    except Exception:
        return PaymentProofResult(False, "processing_error", order=order, payment_status=payment_status)

    return PaymentProofResult(True, order=order, payment_status=PaymentStatus.PROOF_SUBMITTED)
