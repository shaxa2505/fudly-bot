"""Shared status label helpers for orders/bookings UI."""
from __future__ import annotations

from app.domain.order import OrderStatus


def normalize_order_status(status: str | None) -> str:
    """Normalize legacy or empty statuses into unified OrderStatus values."""
    if not status:
        return OrderStatus.PENDING
    status_str = str(status).strip().lower()
    if status_str == "active":
        return OrderStatus.PENDING
    try:
        return OrderStatus.normalize(status_str)
    except Exception:
        return status_str


def status_label(
    status: str | None,
    lang: str,
    order_type: str | None = None,
) -> str:
    """Return localized label for an order status."""
    normalized = normalize_order_status(status)
    order_type_norm = (order_type or "delivery").strip().lower()
    if order_type_norm not in ("delivery", "pickup"):
        order_type_norm = "delivery"

    pickup = {
        "pending": "Tasdiq kutilmoqda" if lang == "uz" else "Ожидает подтверждения",
        "preparing": "Tasdiqlangan" if lang == "uz" else "Подтверждён",
        "ready": "Olib ketishga tayyor" if lang == "uz" else "Готов к выдаче",
        "delivering": "Yo'lda" if lang == "uz" else "В пути",
        "completed": "Olib ketildi" if lang == "uz" else "Получен",
        "rejected": "Bekor qilingan" if lang == "uz" else "Отменён",
        "cancelled": "Bekor qilingan" if lang == "uz" else "Отменён",
    }
    delivery = {
        "pending": "Tasdiq kutilmoqda" if lang == "uz" else "Ожидает подтверждения",
        "preparing": "Tasdiqlangan" if lang == "uz" else "Подтверждён",
        "ready": "Tasdiqlangan" if lang == "uz" else "Подтверждён",
        "delivering": "Yo'lda" if lang == "uz" else "В пути",
        "completed": "Yetkazildi" if lang == "uz" else "Доставлен",
        "rejected": "Bekor qilingan" if lang == "uz" else "Отменён",
        "cancelled": "Bekor qilingan" if lang == "uz" else "Отменён",
    }

    table = delivery if order_type_norm == "delivery" else pickup
    return table.get(normalized, normalized)


def status_emoji(status: str | None) -> str:
    """Return emoji marker for status (currently uniform)."""
    _ = status
    return "•"
