from __future__ import annotations

from app.domain.order import PaymentStatus
from app.domain.order_fsm import validate_order_transition


def _validate(
    current_status: str,
    target_status: str,
    *,
    order_type: str,
    payment_method: str = "cash",
    payment_status: str | None = None,
):
    return validate_order_transition(
        current_status=current_status,
        target_status=target_status,
        order_type=order_type,
        payment_method=payment_method,
        payment_status=payment_status,
        payment_proof_photo_id=None,
    )


def test_delivery_happy_path_transitions_allowed() -> None:
    assert _validate("pending", "confirmed", order_type="delivery").allowed
    assert _validate("preparing", "ready", order_type="delivery").allowed
    assert _validate("ready", "delivering", order_type="delivery").allowed
    assert _validate("delivering", "completed", order_type="delivery").allowed


def test_delivery_pending_to_completed_is_blocked() -> None:
    result = _validate("pending", "completed", order_type="delivery")
    assert not result.allowed


def test_pickup_ready_to_delivering_is_blocked() -> None:
    result = _validate("ready", "delivering", order_type="pickup")
    assert not result.allowed


def test_terminal_status_transition_is_blocked() -> None:
    result = _validate("completed", "preparing", order_type="delivery")
    assert not result.allowed


def test_unpaid_order_cannot_move_to_ready_delivering_completed() -> None:
    result_ready = _validate(
        "preparing",
        "ready",
        order_type="delivery",
        payment_method="click",
        payment_status=PaymentStatus.AWAITING_PAYMENT,
    )
    assert not result_ready.allowed

    result_delivering = _validate(
        "ready",
        "delivering",
        order_type="delivery",
        payment_method="click",
        payment_status=PaymentStatus.AWAITING_PAYMENT,
    )
    assert not result_delivering.allowed

    result_completed = _validate(
        "delivering",
        "completed",
        order_type="delivery",
        payment_method="click",
        payment_status=PaymentStatus.AWAITING_PAYMENT,
    )
    assert not result_completed.allowed

