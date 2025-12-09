"""Guard tests for critical order notification texts.

These tests ensure that key phrases like "ЗАКАЗ ОФОРМЛЕН",
"BUYURTMA QABUL QILINDI" and "Заказ принят!" appear only in
explicitly allowed modules. This helps catch accidental new
hard‑coded notifications that bypass UnifiedOrderService
and NotificationTemplates.
"""
from __future__ import annotations

from pathlib import Path

import pytest


# Phrases we want to track strictly
TRACKED_PHRASES = [
    "ЗАКАЗ ОФОРМЛЕН",
    "BUYURTMA QABUL QILINDI",
    "БРОНЬ ПОДТВЕРЖДЕНА",
    "Заказ принят!",
]

# Relative paths (from repo root) where such phrases are allowed.
# If you intentionally add a new hard‑coded notification elsewhere,
# update this allowlist consciously.
ALLOWED_FILES = {
    # Unified templates (source of truth)
    "app/services/unified_order_service.py",
    "app/services/order_service.py",  # legacy
    # Customer flows that show payment / immediate confirmation
    "handlers/customer/cart/payment.py",
    "handlers/customer/orders/delivery.py",
    # WebApp / Mini App integrations
    "app/api/webapp/routes_orders.py",
    "handlers/common/webapp.py",
    "bot.py",  # legacy Mini App callbacks
}


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        # Skip virtualenvs or external dirs if present
        if ".venv" in path.parts or "env" in path.parts:
            continue
        yield path


@pytest.mark.parametrize("phrase", TRACKED_PHRASES)
def test_tracked_phrases_only_in_allowed_files(phrase: str) -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []

    for path in _iter_python_files(root):
        text = path.read_text(encoding="utf-8")
        if phrase in text:
            rel = path.relative_to(root).as_posix()
            if rel not in ALLOWED_FILES:
                offenders.append(rel)

    assert not offenders, (
        f"Phrase '{phrase}' found in unexpected files: " + ", ".join(offenders)
    )
