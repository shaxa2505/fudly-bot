"""
Notification Builder - Unified notification templates for pickup and delivery orders.

This module eliminates code duplication by providing a clean interface
for building customer notifications based on order type and status.
"""
from typing import Literal


class ProgressBar:
    """Visual progress indicators for order tracking."""

    @staticmethod
    def pickup(step: int, lang: str) -> str:
        """
        2-step progress for pickup orders.

        Steps:
            1. PREPARING: Preparing
            2. COMPLETED: Picked up
        """
        if lang == "uz":
            if step == 1:
                return "Tayyorlanmoqda -> Berildi"
            return "Tayyor -> Berildi"
        if step == 1:
            return "Готовится -> Выдано"
        return "Готово -> Выдано"

    @staticmethod
    def delivery(step: int, lang: str) -> str:
        """
        3-step progress for delivery orders.

        Steps:
            1. PREPARING: Preparing
            2. DELIVERING: In transit
            3. COMPLETED: Delivered
        """
        if lang == "uz":
            if step == 1:
                return "Tayyorlanmoqda -> Yo'lda -> Yetkazildi"
            if step == 2:
                return "Tayyor -> Yo'lda -> Yetkazildi"
            return "Tayyor -> Yo'lda -> Yetkazildi"
        if step == 1:
            return "Готовится -> В пути -> Доставлено"
        if step == 2:
            return "Готово -> В пути -> Доставлено"
        return "Готово -> В пути -> Доставлено"

    @staticmethod
    def delivery_labels(lang: str) -> str:
        """Labels for delivery progress bar."""
        if lang == "uz":
            return "Tayyorlanmoqda -> Yo'lda -> Yetkazildi"
        return "Готовится -> В пути -> Доставлено"


class NotificationBuilder:
    """
    Unified notification builder for customer status updates.

    Provides a single interface for both pickup and delivery orders.
    """

    def __init__(self, order_type: Literal["pickup", "delivery"]):
        """Initialize builder for specific order type."""
        self.order_type = order_type

    def _esc(self, text: str) -> str:
        """HTML escape for safe rendering."""
        import html
        return html.escape(str(text)) if text else ""

    def build_pending(self, lang: str, order_id: int, store_name: str) -> str:
        """
        Build PENDING status notification (waiting for partner confirmation).

        Simple message without progress bar - progress bar appears only after confirmation.
        """
        if lang == "uz":
            entity = "Bron" if self.order_type == "pickup" else "Buyurtma"
            return (
                f"{entity.upper()} YUBORILDI\n\n"
                f"#{order_id}\n"
                f"{self._esc(store_name)}\n\n"
                f"Do'kon tasdiqlashini kuting (5-10 daqiqa)"
            )
        header = "БРОНЬ ОТПРАВЛЕНА" if self.order_type == "pickup" else "ЗАКАЗ ДОСТАВЛЕН"
        return (
            f"{header}\n\n"
            f"#{order_id}\n"
            f"{self._esc(store_name)}\n\n"
            f"???БРОНЬ ОТПРАВЛЕНА??? Бронь??? (5-10 ???)"
        )

    def build_preparing(
        self,
        lang: str,
        order_id: int,
        store_name: str,
        store_address: str | None = None,
        pickup_code: str | None = None,
    ) -> str:
        """Build PREPARING status notification."""
        if self.order_type == "pickup":
            if lang == "uz":
                return (
                    "BRON TASDIQLANDI\n\n"
                    f"{ProgressBar.pickup(1, lang)}\n\n"
                    f"#{order_id}\n"
                    f"{self._esc(store_name)}\n"
                    + (f"{self._esc(store_address)}\n" if store_address else "")
                    + (f"Kod: {pickup_code}\n" if pickup_code else "")
                    + "\nTayyor bo'lganda xabar beramiz."
                )
            return (
                "БРОНЬ ОТПРАВЛЕНА??\n\n"
                f"{ProgressBar.pickup(1, lang)}\n\n"
                f"#{order_id}\n"
                f"{self._esc(store_name)}\n"
                + (f"{self._esc(store_address)}\n" if store_address else "")
                + (f"???: {pickup_code}\n" if pickup_code else "")
                + "\nСообщим, когда будет готово."
            )
        if lang == "uz":
            return (
                "Buyurtma tasdiqlandi\n\n"
                f"{ProgressBar.delivery(1, lang)}\n"
                f"{ProgressBar.delivery_labels(lang)}\n\n"
                f"#{order_id} - {self._esc(store_name)}\n"
                "Tayyorlanmoqda"
            )
        return (
            "БРОНЬ ОТПРАВЛЕНА?\n\n"
            f"{ProgressBar.delivery(1, lang)}\n"
            f"{ProgressBar.delivery_labels(lang)}\n\n"
            f"#{order_id} - {self._esc(store_name)}\n"
            "отклонена"
        )

    def build_delivering(self, lang: str, order_id: int, courier_phone: str | None = None) -> str:
        """Build DELIVERING status notification (delivery only)."""
        if lang == "uz":
            courier_text = f"\nKuryer: {self._esc(courier_phone)}" if courier_phone else ""
            return (
                "Buyurtma yo'lda\n\n"
                f"{ProgressBar.delivery(2, lang)}\n"
                f"{ProgressBar.delivery_labels(lang)}\n\n"
                f"#{order_id}\n"
                "Taxminan 30-60 daqiqa"
                + courier_text
            )
        courier_text = f"\nКурьер: {self._esc(courier_phone)}" if courier_phone else ""
        return (
            "ЗАКАЗ В ПУТИ\n\n"
            f"{ProgressBar.delivery(2, lang)}\n"
            f"{ProgressBar.delivery_labels(lang)}\n\n"
            f"#{order_id}\n"
            "Примерно 30-60 мин"
            + courier_text
        )

    def build_completed(self, lang: str, order_id: int, store_name: str) -> str:
        """Build COMPLETED status notification."""
        if self.order_type == "pickup":
            if lang == "uz":
                return (
                    "Buyurtma berildi\n\n"
                    f"{ProgressBar.pickup(2, lang)}\n\n"
                    f"#{order_id} - {self._esc(store_name)}\n\n"
                    "Rahmat!"
                )
            return (
                "БРОНЬ ВЫДАНА\n\n"
                f"{ProgressBar.pickup(2, lang)}\n\n"
                f"#{order_id} - {self._esc(store_name)}\n\n"
                "Спасибо!"
            )
        if lang == "uz":
            return (
                "Yetkazildi\n\n"
                f"{ProgressBar.delivery(3, lang)}\n\n"
                f"#{order_id} - {self._esc(store_name)}\n\n"
                "Rahmat!"
            )
        return (
            "ЗАКАЗ ДОСТАВЛЕН\n\n"
            f"{ProgressBar.delivery(3, lang)}\n\n"
            f"#{order_id} - {self._esc(store_name)}\n\n"
            "Спасибо!"
        )

    def build_rejected(self, lang: str, order_id: int, reason: str | None = None) -> str:
        """Build REJECTED status notification."""
        reason_text = self._esc(reason) if reason else ""
        if lang == "uz":
            entity = "Bron" if self.order_type == "pickup" else "Buyurtma"
            return (
                f"{entity} rad etildi\n\n"
                f"#{order_id}\n"
                + (f"Sabab: {reason_text}\n" if reason_text else "")
            )
        entity = "Бронь" if self.order_type == "pickup" else "Бронь"
        verb = "отклонена" if self.order_type == "pickup" else "Бронь???"
        return (
            f"{entity} {verb}\n\n"
            f"#{order_id}\n"
            + (f"?Курьер: {reason_text}\n" if reason_text else "")
        )

    def build_cancelled(self, lang: str, order_id: int) -> str:
        """Build CANCELLED status notification."""
        if lang == "uz":
            entity = "Bron" if self.order_type == "pickup" else "Buyurtma"
            return f"{entity} bekor qilindi\n#{order_id}"
        entity = "Бронь" if self.order_type == "pickup" else "Бронь"
        verb = "Бронь???" if self.order_type == "pickup" else "Бронь??"
        return f"{entity} {verb}\n#{order_id}"

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
        if status == "delivering":
            return self.build_delivering(lang, order_id, courier_phone)
        if status == "completed":
            return self.build_completed(lang, order_id, store_name)
        if status == "rejected":
            return self.build_rejected(lang, order_id, reject_reason)
        if status == "cancelled":
            return self.build_cancelled(lang, order_id)
        return f"Order #{order_id} status: {status}"