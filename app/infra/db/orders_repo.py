"""Orders repository adapter for application use cases."""
from __future__ import annotations

from typing import Any

from database_protocol import DatabaseProtocol


def _get_field(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if hasattr(row, "get"):
        try:
            return row.get(key, default)
        except Exception:
            pass
    return getattr(row, key, default)


class OrdersRepository:
    def __init__(self, db: DatabaseProtocol):
        self._db = db

    def get_field(self, row: Any, key: str, default: Any = None) -> Any:
        return _get_field(row, key, default)

    def get_order(self, order_id: int) -> Any | None:
        if not self._db or not hasattr(self._db, "get_order"):
            return None
        return self._db.get_order(order_id)

    def update_payment_status(self, order_id: int, status: str, photo_id: str | None = None) -> None:
        if hasattr(self._db, "update_payment_status"):
            self._db.update_payment_status(order_id, status, photo_id)
        elif photo_id and hasattr(self._db, "update_order_payment_proof"):
            self._db.update_order_payment_proof(order_id, photo_id)

    def set_order_status(self, order_id: int, status: str) -> bool:
        try:
            from app.services.unified_order_service import set_order_status_direct
        except Exception:
            return False
        return set_order_status_direct(self._db, order_id, status)

    def get_store(self, store_id: int | None) -> Any | None:
        if not store_id or not hasattr(self._db, "get_store"):
            return None
        return self._db.get_store(store_id)

    def get_offer(self, offer_id: int | None) -> Any | None:
        if not offer_id or not hasattr(self._db, "get_offer"):
            return None
        return self._db.get_offer(offer_id)

    def get_user(self, user_id: int | None) -> Any | None:
        if not user_id or not hasattr(self._db, "get_user"):
            return None
        return self._db.get_user(user_id)

    def get_user_model(self, user_id: int | None) -> Any | None:
        if not user_id or not hasattr(self._db, "get_user_model"):
            return None
        return self._db.get_user_model(user_id)
