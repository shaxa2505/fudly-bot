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
                return "? Tayyorlanmoqda ? ? Berildi"
            return "? Tayyor ? ? Berildi"
        if step == 1:
            return "? ????????? ? ? ?????"
        return "? ?????? ? ? ?????"

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
                return "? Tayyorlanmoqda ? ? Yo'lda ? ? Yetkazildi"
            if step == 2:
                return "? Tayyor ? ? Yo'lda ? ? Yetkazildi"
            return "? Tayyor ? ? Yo'lda ? ? Yetkazildi"
        if step == 1:
            return "? ????????? ? ? ? ???? ? ? ?????????"
        if step == 2:
            return "? ?????? ? ? ? ???? ? ? ?????????"
        return "? ?????? ? ? ? ???? ? ? ?????????"

    @staticmethod
    def delivery_labels(lang: str) -> str:
        """Labels for delivery progress bar."""
        if lang == "uz":
            return "Tayyorlanmoqda ? Yo'lda ? Yetkazildi"
        return "????????? ? ? ???? ? ?????????"


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
                f"?? <b>{entity.upper()} YUBORILDI</b>

"
                f"?? #{order_id}
"
                f"?? {self._esc(store_name)}

"
                f"? Do'kon tasdiqlashini kuting (5?10 daqiqa)"
            )
        entity = "?????" if self.order_type == "pickup" else "?????"
        return (
            f"?? <b>{entity.upper()} ?????????</b>

"
            f"?? #{order_id}
"
            f"?? {self._esc(store_name)}

"
            f"? ???? ????????????? ???????? (5?10 ???)"
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
                    f"? <b>BRON TASDIQLANDI</b>

"
                    f"{ProgressBar.pickup(1, lang)}

"
                    f"?? #{order_id}
"
                    f"?? {self._esc(store_name)}
"
                    + (f"?? {self._esc(store_address)}
" if store_address else "")
                    + (f"?? <b>Kod: {pickup_code}</b>
" if pickup_code else "")
                    + "
? Tayyor bo'lganda xabar beramiz."
                )
            return (
                f"? <b>????? ????????????</b>

"
                f"{ProgressBar.pickup(1, lang)}

"
                f"?? #{order_id}
"
                f"?? {self._esc(store_name)}
"
                + (f"?? {self._esc(store_address)}
" if store_address else "")
                + (f"?? <b>???: {pickup_code}</b>
" if pickup_code else "")
                + "
? ???????, ????? ????? ???????."
            )
        if lang == "uz":
            return (
                f"? <b>Buyurtma tasdiqlandi</b>

"
                f"{ProgressBar.delivery(1, lang)}
"
                f"{ProgressBar.delivery_labels(lang)}

"
                f"?? #{order_id} ? {self._esc(store_name)}
"
                f"? Tayyorlanmoqda"
            )
        return (
            f"? <b>????? ???????????</b>

"
            f"{ProgressBar.delivery(1, lang)}
"
            f"{ProgressBar.delivery_labels(lang)}

"
            f"?? #{order_id} ? {self._esc(store_name)}
"
            f"? ??????? ?????"
        )

    def build_delivering(self, lang: str, order_id: int, courier_phone: str | None = None) -> str:
        """Build DELIVERING status notification (delivery only)."""
        courier_text = f"
?? {self._esc(courier_phone)}" if courier_phone else ""
        if lang == "uz":
            return (
                f"?? <b>Buyurtma yo'lda</b>

"
                f"{ProgressBar.delivery(2, lang)}
"
                f"{ProgressBar.delivery_labels(lang)}

"
                f"?? #{order_id}
"
                f"? ~30?60 daqiqa"
                + courier_text
            )
        return (
            f"?? <b>????? ? ????</b>

"
            f"{ProgressBar.delivery(2, lang)}
"
            f"{ProgressBar.delivery_labels(lang)}

"
            f"?? #{order_id}
"
            f"? ~30?60 ???"
            + courier_text
        )

    def build_completed(self, lang: str, order_id: int, store_name: str) -> str:
        """Build COMPLETED status notification."""
        if self.order_type == "pickup":
            if lang == "uz":
                return (
                    f"? <b>Buyurtma berildi</b>

"
                    f"{ProgressBar.pickup(2, lang)}

"
                    f"?? #{order_id} ? {self._esc(store_name)}

"
                    f"Rahmat!"
                )
            return (
                f"? <b>????? ?????</b>

"
                f"{ProgressBar.pickup(2, lang)}

"
                f"?? #{order_id} ? {self._esc(store_name)}

"
                f"???????!"
            )
        if lang == "uz":
            return (
                f"? <b>Yetkazildi</b>

"
                f"{ProgressBar.delivery(3, lang)}

"
                f"?? #{order_id} ? {self._esc(store_name)}

"
                f"Rahmat!"
            )
        return (
            f"? <b>????? ?????????</b>

"
            f"{ProgressBar.delivery(3, lang)}

"
            f"?? #{order_id} ? {self._esc(store_name)}

"
            f"???????!"
        )

    def build_rejected(self, lang: str, order_id: int, reason: str | None = None) -> str:
        """Build REJECTED status notification."""
        reason_text = f"{self._esc(reason)}" if reason else ""
        if lang == "uz":
            entity = "Bron" if self.order_type == "pickup" else "Buyurtma"
            return (
                f"? <b>{entity} rad etildi</b>

"
                f"?? #{order_id}
"
                + (f"Sabab: {reason_text}
" if reason_text else "")
            )
        entity = "?????" if self.order_type == "pickup" else "?????"
        return (
            f"? <b>{entity} ????????</b>

"
            f"?? #{order_id}
"
            + (f"???????: {reason_text}
" if reason_text else "")
        )

    def build_cancelled(self, lang: str, order_id: int) -> str:
        """Build CANCELLED status notification."""
        if lang == "uz":
            entity = "Bron" if self.order_type == "pickup" else "Buyurtma"
            return f"? <b>{entity} bekor qilindi</b>
?? #{order_id}"
        entity = "?????" if self.order_type == "pickup" else "?????"
        return f"? <b>{entity} ???????</b>
?? #{order_id}"

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
        return f"?? Order #{order_id} status: {status}"
