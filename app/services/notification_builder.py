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
            1. PREPARING: Accepted → Waiting for customer
            2. COMPLETED: Customer received
        """
        if lang == "uz":
            if step == 1:
                return "🟢 Qabul qilindi ━━━ ⚪ Topshirildi"
            return "🟢 Qabul qilindi ━━━ 🟢 Topshirildi ✓"
        else:  # ru
            if step == 1:
                return "🟢 Принят ━━━━━━ ⚪ Выдан"
            return "🟢 Принят ━━━━━━ 🟢 Выдан ✓"
    
    @staticmethod
    def delivery(step: int, lang: str) -> str:
        """
        3-step progress for delivery orders.
        
        Steps:
            1. PREPARING: Accepted → Preparing
            2. DELIVERING: In transit
            3. COMPLETED: Delivered
        """
        steps_map = {
            1: "🟢━━⚪━━⚪",
            2: "🟢━━🟢━━⚪",
            3: "🟢━━🟢━━🟢 ✓"
        }
        return steps_map.get(step, "🟢━━⚪━━⚪")
    
    @staticmethod
    def delivery_labels(lang: str) -> str:
        """Labels for delivery progress bar."""
        if lang == "uz":
            return "Qabul │ Yo'lda │ Yetkazildi"
        return "Принят │ В пути │ Доставлен"


class NotificationBuilder:
    """
    Unified notification builder for customer status updates.
    
    Eliminates ~200 lines of duplicated template code by providing
    a single interface for both pickup and delivery orders.
    """
    
    def __init__(self, order_type: Literal["pickup", "delivery"]):
        """
        Initialize builder for specific order type.
        
        Args:
            order_type: "pickup" or "delivery"
        """
        self.order_type = order_type
    
    def _esc(self, text: str) -> str:
        """HTML escape for safe rendering."""
        import html
        return html.escape(str(text)) if text else ""
    
    def build_preparing(
        self,
        lang: str,
        order_id: int,
        store_name: str,
        store_address: str | None = None,
        pickup_code: str | None = None,
    ) -> str:
        """
        Build PREPARING status notification.
        
        Pickup: "Бронь подтверждена! Заберите в течение 2 часов"
        Delivery: "Заказ принят! Готовится..."
        """
        if self.order_type == "pickup":
            if lang == "uz":
                return (
                    f"✅ <b>BRON TASDIQLANDI!</b>\n\n"
                    f"{ProgressBar.pickup(1, lang)}\n\n"
                    f"📦 #{order_id}\n"
                    f"🏪 {self._esc(store_name)}\n"
                    + (f"📍 {self._esc(store_address)}\n" if store_address else "")
                    + (f"🎫 <b>Kod: {pickup_code}</b>\n" if pickup_code else "")
                    + "\n👉 Tayyor bo'lganda xabar beramiz!"
                )
            else:  # ru
                return (
                    f"✅ <b>БРОНЬ ПОДТВЕРЖДЕНА!</b>\n\n"
                    f"{ProgressBar.pickup(1, lang)}\n\n"
                    f"📦 #{order_id}\n"
                    f"🏪 {self._esc(store_name)}\n"
                    + (f"📍 {self._esc(store_address)}\n" if store_address else "")
                    + (f"🎫 <b>Код: {pickup_code}</b>\n" if pickup_code else "")
                    + "\n👉 Сообщим, когда будет готов!"
                )
        else:  # delivery
            if lang == "uz":
                return (
                    f"🎉 <b>Buyurtma qabul qilindi!</b>\n\n"
                    f"{ProgressBar.delivery(1, lang)}\n"
                    f"{ProgressBar.delivery_labels(lang)}\n\n"
                    f"📦 #{order_id} — {self._esc(store_name)}\n"
                    f"👨‍🍳 Tayyorlanmoqda..."
                )
            else:  # ru
                return (
                    f"🎉 <b>Заказ принят!</b>\n\n"
                    f"{ProgressBar.delivery(1, lang)}\n"
                    f"{ProgressBar.delivery_labels(lang)}\n\n"
                    f"📦 #{order_id} — {self._esc(store_name)}\n"
                    f"👨‍🍳 Готовится..."
                )
    
    def build_delivering(
        self,
        lang: str,
        order_id: int,
        courier_phone: str | None = None,
    ) -> str:
        """
        Build DELIVERING status notification (delivery only).
        
        "Заказ в пути! ~30-60 мин"
        """
        courier_text = (
            f"\n📞 {self._esc(courier_phone)}"
            if courier_phone
            else ""
        ) if lang == "uz" else (
            f"\n📞 {self._esc(courier_phone)}"
            if courier_phone
            else ""
        )
        
        if lang == "uz":
            return (
                f"🚚 <b>Buyurtma yo'lda!</b>\n\n"
                f"{ProgressBar.delivery(2, lang)}\n"
                f"{ProgressBar.delivery_labels(lang)}\n\n"
                f"📦 #{order_id}\n"
                f"⏱ ~30-60 daqiqa"
                + courier_text
            )
        else:  # ru
            return (
                f"🚚 <b>Заказ в пути!</b>\n\n"
                f"{ProgressBar.delivery(2, lang)}\n"
                f"{ProgressBar.delivery_labels(lang)}\n\n"
                f"📦 #{order_id}\n"
                f"⏱ ~30-60 мин"
                + courier_text
            )
    
    def build_completed(
        self,
        lang: str,
        order_id: int,
        store_name: str,
    ) -> str:
        """
        Build COMPLETED status notification.
        
        Pickup: "Заказ выдан!"
        Delivery: "Доставлено!"
        """
        if self.order_type == "pickup":
            if lang == "uz":
                return (
                    f"🎊 <b>Buyurtma topshirildi!</b>\n\n"
                    f"{ProgressBar.pickup(2, lang)}\n\n"
                    f"📦 #{order_id} — {self._esc(store_name)}\n\n"
                    f"Rahmat! ⭐"
                )
            else:  # ru
                return (
                    f"🎊 <b>Заказ выдан!</b>\n\n"
                    f"{ProgressBar.pickup(2, lang)}\n\n"
                    f"📦 #{order_id} — {self._esc(store_name)}\n\n"
                    f"Спасибо! ⭐"
                )
        else:  # delivery
            if lang == "uz":
                return (
                    f"🎊 <b>Yetkazildi!</b>\n\n"
                    f"{ProgressBar.delivery(3, lang)}\n\n"
                    f"📦 #{order_id} — {self._esc(store_name)}\n\n"
                    f"Rahmat! ⭐"
                )
            else:  # ru
                return (
                    f"🎊 <b>Доставлено!</b>\n\n"
                    f"{ProgressBar.delivery(3, lang)}\n\n"
                    f"📦 #{order_id} — {self._esc(store_name)}\n\n"
                    f"Спасибо! ⭐"
                )
    
    def build_rejected(
        self,
        lang: str,
        order_id: int,
        reason: str | None = None,
    ) -> str:
        """Build REJECTED status notification."""
        reason_text = f"📝 {self._esc(reason)}" if reason else ""
        reason_label = "Sabab:" if lang == "uz" else "Причина:"
        
        if lang == "uz":
            return (
                f"😔 <b>{'Bron' if self.order_type == 'pickup' else 'Buyurtma'} rad etildi</b>\n\n"
                f"📦 #{order_id}\n"
                + (f"{reason_label} {reason_text}\n" if reason else "")
            )
        else:  # ru
            return (
                f"😔 <b>{'Бронь' if self.order_type == 'pickup' else 'Заказ'} отклонен{'а' if self.order_type == 'pickup' else ''}</b>\n\n"
                f"📦 #{order_id}\n"
                + (f"{reason_label} {reason_text}\n" if reason else "")
            )
    
    def build_cancelled(
        self,
        lang: str,
        order_id: int,
    ) -> str:
        """Build CANCELLED status notification."""
        if lang == "uz":
            entity = "Bron" if self.order_type == "pickup" else "Buyurtma"
            return f"❌ <b>{entity} bekor qilindi</b>\n📦 #{order_id}"
        else:  # ru
            entity = "Бронь" if self.order_type == "pickup" else "Заказ"
            suffix = "а" if self.order_type == "pickup" else ""
            return f"❌ <b>{entity} отменен{suffix}</b>\n📦 #{order_id}"
    
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
        """
        Build notification for any status.
        
        This is the main entry point - routes to specific builders.
        """
        if status == "preparing":
            return self.build_preparing(lang, order_id, store_name, store_address, pickup_code)
        elif status == "delivering":
            return self.build_delivering(lang, order_id, courier_phone)
        elif status == "completed":
            return self.build_completed(lang, order_id, store_name)
        elif status == "rejected":
            return self.build_rejected(lang, order_id, reject_reason)
        elif status == "cancelled":
            return self.build_cancelled(lang, order_id)
        else:
            # Fallback for unknown status
            return f"📦 Order #{order_id} status: {status}"
