"""Guard tests for direct status updates and booking creation.

These tests ensure that low-level operations like
`update_order_status`, `update_booking_status` and
`create_booking_atomic` are only used from an explicit set of
modules. This helps prevent new ad-hoc status changes from
appearing in random handlers without review.
"""
from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

# NOTE: these allowlists intentionally include all current
# call sites (handlers, services, DB layer, tests, scripts).
# If you add a new direct usage, update the allowlist
# consciously or prefer going through UnifiedOrderService.

UPDATE_ORDER_ALLOWED = {
    "handlers/customer/orders/delivery.py",
    "handlers/common/unified_order/seller.py",
    "handlers/common/unified_order/customer.py",
    "handlers/customer/orders/my_orders.py",
    "handlers/customer/payments.py",
    "handlers/seller/order_management.py",
    "handlers/customer/orders/delivery_partner.py",
    "handlers/seller/management/orders.py",
    "handlers/customer/orders/delivery_admin.py",
    "database_protocol.py",
    "database.py",
    "database_pg_module/mixins/orders.py",
}

UPDATE_BOOKING_ALLOWED = {
    "handlers/common/unified_order/seller.py",
    "handlers/common/unified_order/customer.py",
    "handlers/customer/orders/my_orders.py",
    "tests/test_validation.py",
    "tests/test_integration.py",
    "tests/test_e2e_booking_flow.py",
    "handlers/seller/management/orders.py",
    "handlers/customer/payments.py",
    "handlers/bookings/partner.py",
    "bot.py",
    "database_protocol.py",
    "database.py",
    "app/services/booking_service.py",
    "database_pg_module/mixins/bookings.py",
}

CREATE_BOOKING_ATOMIC_ALLOWED = {
    "handlers/bookings/customer.py",
    "app/api/webapp/routes_orders.py",
    "app/core/webhook_server.py",
    "tests/test_validation.py",
    "tests/test_integration.py",
    "tests/test_e2e_booking_flow.py",
    "tests/test_booking_race_condition.py",
    "scripts/smoke_test_pickup.py",
    "database_protocol.py",
    "database.py",
    "app/services/booking_service.py",
    "database_pg_module/mixins/bookings.py",
}


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if ".venv" in path.parts or "env" in path.parts:
            continue
        yield path


@pytest.mark.parametrize(
    "needle, allowed",
    [
        ("update_order_status(", UPDATE_ORDER_ALLOWED),
        ("update_booking_status(", UPDATE_BOOKING_ALLOWED),
        ("create_booking_atomic(", CREATE_BOOKING_ATOMIC_ALLOWED),
    ],
)
def test_direct_status_operations_only_in_allowed_files(needle: str, allowed: set[str]) -> None:
    offenders: list[str] = []

    for path in _iter_python_files(ROOT):
        text = path.read_text(encoding="utf-8")
        if needle in text:
            rel = path.relative_to(ROOT).as_posix()
            if rel not in allowed:
                offenders.append(rel)

    assert not offenders, (
        f"Direct call '{needle}' found in unexpected files: " + ", ".join(sorted(set(offenders)))
    )
