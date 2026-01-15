"""
Notification Builder - unified customer status notifications.

Provides a single interface for both pickup and delivery orders
with a concise, readable layout.
"""
from __future__ import annotations

import html
from typing import Literal


class NotificationBuilder:
    """
    Unified notification builder for customer status updates.
    """

    def __init__(self, order_type: Literal["pickup", "delivery"]):
        """Initialize builder for a specific order type."""
        self.order_type = order_type

    def _esc(self, text: str | None) -> str:
        """HTML-escape helper."""
        return html.escape(str(text)) if text else ""

    def _type_label(self, lang: str) -> str:
        if lang == "uz":
            return "Olib ketish" if self.order_type == "pickup" else "Yetkazib berish"
        return "Самовывоз" if self.order_type == "pickup" else "Доставка"

    def _title_label(self, lang: str) -> str:
        return "Buyurtma" if lang == "uz" else "Заказ"

    def _status_label(self, status: str, lang: str) -> str:
        pickup = {
            "pending": "Tasdiq kutilmoqda" if lang == "uz" else "Ожидает подтверждения",
            "preparing": "Tayyorlanmoqda" if lang == "uz" else "Готовится",
            "ready": "Tayyor" if lang == "uz" else "Готов к выдаче",
            "delivering": "Yo'lda" if lang == "uz" else "В пути",
            "completed": "Berildi" if lang == "uz" else "Выдано",
            "rejected": "Rad etildi" if lang == "uz" else "Отклонён",
            "cancelled": "Bekor qilindi" if lang == "uz" else "Отменён",
        }
        delivery = {
            "pending": "Tasdiq kutilmoqda" if lang == "uz" else "Ожидает подтверждения",
            "preparing": "Tayyorlanmoqda" if lang == "uz" else "Готовится",
            "ready": "Tayyor" if lang == "uz" else "Собран",
            "delivering": "Yo'lda" if lang == "uz" else "В пути",
            "completed": "Yetkazildi" if lang == "uz" else "Доставлено",
            "rejected": "Rad etildi" if lang == "uz" else "Отклонён",
            "cancelled": "Bekor qilindi" if lang == "uz" else "Отменён",
        }
        table = delivery if self.order_type == "delivery" else pickup
        return table.get(status, status)

    def _build_message(
        self,
        status: str,
        lang: str,
        order_id: int,
        store_name: str = "",
        store_address: str | None = None,
        pickup_code: str | None = None,
        reject_reason: str | None = None,
        courier_phone: str | None = None,
    ) -> str:
        type_label = self._type_label(lang)
        title_label = self._title_label(lang)

        lines: list[str] = [f"🧾 {title_label} #{order_id} — {type_label}"]

        if store_name:
            store_label = "Do'kon" if lang == "uz" else "Магазин"
            lines.append(f"{store_label}: {self._esc(store_name)}")

        if self.order_type == "pickup":
            if store_address:
                addr_label = "Manzil" if lang == "uz" else "Адрес"
                lines.append(f"{addr_label}: {self._esc(store_address)}")
            if pickup_code:
                code_label = "Kod" if lang == "uz" else "Код"
                lines.append(f"{code_label}: <b>{self._esc(pickup_code)}</b>")
        else:
            if courier_phone and status == "delivering":
                courier_label = "Kuryer" if lang == "uz" else "Курьер"
                lines.append(f"{courier_label}: {self._esc(courier_phone)}")

        lines.append("")

        status_label = self._status_label(status, lang)
        status_caption = "Holat" if lang == "uz" else "Статус"
        lines.append(f"{status_caption}: {status_label}")

        if reject_reason and status in ("rejected", "cancelled"):
            reason_label = "Sabab" if lang == "uz" else "Причина"
            lines.append(f"{reason_label}: {self._esc(reject_reason)}")

        if status == "completed":
            lines.append("")
            lines.append("Rahmat!" if lang == "uz" else "Спасибо за заказ!")

        return "\n".join(lines)

    def build_pending(self, lang: str, order_id: int, store_name: str) -> str:
        return self._build_message("pending", lang, order_id, store_name)

    def build_preparing(
        self,
        lang: str,
        order_id: int,
        store_name: str,
        store_address: str | None = None,
        pickup_code: str | None = None,
    ) -> str:
        return self._build_message(
            "preparing",
            lang,
            order_id,
            store_name=store_name,
            store_address=store_address,
            pickup_code=pickup_code,
        )

    def build_ready(
        self,
        lang: str,
        order_id: int,
        store_name: str,
        store_address: str | None = None,
        pickup_code: str | None = None,
    ) -> str:
        return self._build_message(
            "ready",
            lang,
            order_id,
            store_name=store_name,
            store_address=store_address,
            pickup_code=pickup_code,
        )

    def build_delivering(
        self,
        lang: str,
        order_id: int,
        courier_phone: str | None = None,
        store_name: str | None = None,
    ) -> str:
        return self._build_message(
            "delivering",
            lang,
            order_id,
            store_name=store_name or "",
            courier_phone=courier_phone,
        )

    def build_completed(self, lang: str, order_id: int, store_name: str) -> str:
        return self._build_message("completed", lang, order_id, store_name=store_name)

    def build_rejected(self, lang: str, order_id: int, reason: str | None = None) -> str:
        return self._build_message(
            "rejected",
            lang,
            order_id,
            reject_reason=reason,
        )

    def build_cancelled(self, lang: str, order_id: int) -> str:
        return self._build_message("cancelled", lang, order_id)

    def build(
        self,
        status: str,
        lang: str,
        order_id: int,
        store_name: str = "",
        store_address: str | None = None,
        pickup_code: str | None = None,
        reject_reason: str | None = None,
        courier_phone: str | None = None,
    ) -> str:
        """Build notification for any status."""
        if status == "pending":
            return self.build_pending(lang, order_id, store_name)
        if status == "preparing":
            return self.build_preparing(lang, order_id, store_name, store_address, pickup_code)
        if status == "ready":
            return self.build_ready(lang, order_id, store_name, store_address, pickup_code)
        if status == "delivering":
            return self.build_delivering(lang, order_id, courier_phone, store_name)
        if status == "completed":
            return self.build_completed(lang, order_id, store_name)
        if status == "rejected":
            return self.build_rejected(lang, order_id, reject_reason)
        if status == "cancelled":
            return self.build_cancelled(lang, order_id)
        return f"Order #{order_id} status: {status}"
