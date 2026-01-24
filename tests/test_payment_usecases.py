"""Tests for payment-related application use cases."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.application.orders.confirm_payment import confirm_payment
from app.application.orders.reject_payment import reject_payment
from app.application.orders.submit_payment_proof import submit_payment_proof
from app.domain.order import PaymentStatus


class DummyRepo:
    def __init__(self, order: dict | None):
        self.order = order
        self.updated: list[tuple[int, str, str | None]] = []

    def get_order(self, order_id: int):
        if not self.order:
            return None
        return self.order if self.order.get("order_id") == order_id else None

    def get_field(self, row, key: str, default=None):
        if row is None:
            return default
        return row.get(key, default)

    def update_payment_status(self, order_id: int, status: str, photo_id: str | None = None):
        self.updated.append((order_id, status, photo_id))


@dataclass
class DummyOrderService:
    ok: bool = True

    def __post_init__(self):
        self.confirmed: list[int] = []
        self.updated: list[dict] = []

    async def confirm_payment(self, order_id: int) -> bool:
        self.confirmed.append(order_id)
        return self.ok

    async def update_status(self, **kwargs):
        self.updated.append(kwargs)


@pytest.mark.asyncio
async def test_confirm_payment_success():
    order = {
        "order_id": 1,
        "payment_status": PaymentStatus.PROOF_SUBMITTED,
        "payment_method": "card",
    }
    repo = DummyRepo(order)
    service = DummyOrderService(ok=True)

    result = await confirm_payment(1, repo=repo, order_service=service)

    assert result.ok is True
    assert service.confirmed == [1]


@pytest.mark.asyncio
async def test_confirm_payment_already_processed():
    order = {
        "order_id": 1,
        "payment_status": PaymentStatus.CONFIRMED,
        "payment_method": "card",
    }
    repo = DummyRepo(order)
    service = DummyOrderService(ok=True)

    result = await confirm_payment(1, repo=repo, order_service=service)

    assert result.ok is False
    assert result.error_key == "already_processed"
    assert service.confirmed == []


@pytest.mark.asyncio
async def test_reject_payment_updates_status():
    order = {
        "order_id": 2,
        "payment_status": PaymentStatus.PROOF_SUBMITTED,
        "payment_method": "card",
    }
    repo = DummyRepo(order)
    service = DummyOrderService(ok=True)

    result = await reject_payment(2, repo=repo, order_service=service)

    assert result.ok is True
    assert repo.updated == [(2, PaymentStatus.REJECTED, None)]
    assert service.updated


@pytest.mark.asyncio
async def test_submit_payment_proof_forbidden():
    order = {
        "order_id": 3,
        "user_id": 10,
        "payment_status": PaymentStatus.AWAITING_PROOF,
        "payment_method": "card",
    }
    repo = DummyRepo(order)

    result = await submit_payment_proof(
        3,
        actor_user_id=11,
        proof_file_id="file_1",
        repo=repo,
    )

    assert result.ok is False
    assert result.error_key == "forbidden"
    assert repo.updated == []


@pytest.mark.asyncio
async def test_submit_payment_proof_success():
    order = {
        "order_id": 4,
        "user_id": 10,
        "payment_status": PaymentStatus.AWAITING_PROOF,
        "payment_method": "card",
    }
    repo = DummyRepo(order)

    result = await submit_payment_proof(
        4,
        actor_user_id=10,
        proof_file_id="file_2",
        repo=repo,
    )

    assert result.ok is True
    assert repo.updated == [(4, PaymentStatus.PROOF_SUBMITTED, "file_2")]


@pytest.mark.asyncio
async def test_submit_payment_proof_not_allowed():
    order = {
        "order_id": 5,
        "user_id": 10,
        "payment_status": PaymentStatus.AWAITING_PAYMENT,
        "payment_method": "click",
    }
    repo = DummyRepo(order)

    result = await submit_payment_proof(
        5,
        actor_user_id=10,
        proof_file_id="file_3",
        repo=repo,
    )

    assert result.ok is False
    assert result.error_key == "not_allowed"
    assert repo.updated == []
