"""Cart checkout and back-to-menu handlers."""
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import main_menu_customer
from app.services.unified_order_service import (
    OrderItem,
    OrderResult,
    get_unified_order_service,
)
from localization import get_text

from .common import esc
from . import common
from .storage import cart_storage


def register(router: Router) -> None:
    """Register checkout-related cart handlers on the given router."""

    @router.callback_query(F.data == "cart_clear")
    async def cart_clear(callback: types.CallbackQuery) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        cart_storage.clear_cart(user_id)

        text = "🗑 Корзина очищена" if lang == "ru" else "🗑 Savat tozalandi"

        try:
            await callback.message.edit_text(text, parse_mode="HTML")
        except Exception:
            pass

        await callback.answer()

    @router.callback_query(F.data == "cart_checkout")
    async def cart_checkout(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        items = cart_storage.get_cart(user_id)
        if not items:
            await callback.answer(
                "Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True
            )
            return

        low_stock_warnings = []
        for item in items:
            if item.max_quantity < 5 and item.quantity > (item.max_quantity * 0.5):
                low_stock_warnings.append(
                    (
                        f"⚠️ {item.title}: осталось всего {item.max_quantity} {item.unit}"
                        if lang == "ru"
                        else f"⚠️ {item.title}: faqat {item.max_quantity} {item.unit} qoldi"
                    )
                )

        if low_stock_warnings:
            warning_text = "\n".join(low_stock_warnings)
            warning_text += "\n\n" + (
                "Товар заканчивается! Рекомендуем оформить заказ как можно скорее."
                if lang == "ru"
                else "Mahsulot tugayapti! Tezroq buyurtma berishni tavsiya qilamiz."
            )
            try:
                await callback.message.answer(warning_text, parse_mode="HTML")
            except Exception:
                pass

        # Require phone number before checkout
        user = common.db.get_user_model(user_id)
        if not user or not getattr(user, "phone", None):
            from app.keyboards import phone_request_keyboard
            from handlers.common.states import Registration

            await callback.message.answer(
                (
                    "📱 Для оформления заказа укажите номер телефона"
                    if lang == "ru"
                    else "📱 Buyurtma berish uchun telefon raqamingizni kiriting"
                ),
                reply_markup=phone_request_keyboard(lang),
            )
            await state.update_data(pending_cart_checkout=True)
            await state.set_state(Registration.phone)
            await callback.answer()
            return
        
        # Enforce single-store cart
        stores = {item.store_id for item in items}
        if len(stores) > 1:
            await callback.answer(
                (
                    "Можно оформить заказ только из одного магазина"
                    if lang == "ru"
                    else "Faqat bitta do'kondan buyurtma berish mumkin"
                ),
                show_alert=True,
            )
            return

        store_id = items[0].store_id
        store = common.db.get_store(store_id)
        delivery_enabled = items[0].delivery_enabled
        delivery_price = items[0].delivery_price

        currency = "so'm" if lang == "uz" else "сум"
        total = int(sum(item.price * item.quantity for item in items))

        lines: list[str] = [f"📋 <b>{'Buyurtma' if lang == 'uz' else 'Заказ'}</b>\n"]
        lines.append(f"🏪 {esc(items[0].store_name)}\n")

        for item in items:
            subtotal = int(item.price * item.quantity)
            lines.append(f"• {esc(item.title)} × {item.quantity} = {subtotal:,} {currency}")

        lines.append("\n" + "─" * 25)
        lines.append(
            f"💵 <b>{'Jami' if lang == 'uz' else 'Итого'}: {total:,} {currency}</b>"
        )
        store = common.db.get_store(store_id)
        if delivery_enabled:
            lines.append(
                f"🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}"
            )

        text = "\n".join(lines)

        kb = InlineKeyboardBuilder()

        if delivery_enabled:
            kb.button(
                text="🏪 Самовывоз" if lang == "ru" else "🏪 O'zim olib ketaman",
                callback_data="cart_confirm_pickup",
            )
            kb.button(
                text="🚚 Доставка" if lang == "ru" else "🚚 Yetkazish",
                callback_data="cart_confirm_delivery",
            )
            kb.adjust(2)
        else:
            kb.button(
                text="✅ Подтвердить" if lang == "ru" else "✅ Tasdiqlash",
                callback_data="cart_confirm_pickup",
            )

        kb.button(
            text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga",
            callback_data="back_to_cart",
        )

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

        await callback.answer()

    @router.callback_query(F.data == "cart_confirm_pickup")
    async def cart_confirm_pickup(callback: types.CallbackQuery) -> None:
        """Create a pickup order from the cart and show a clear confirmation."""

        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        items = cart_storage.get_cart(user_id)
        if not items:
            await callback.answer(
                "Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True
            )
            return

        order_service = get_unified_order_service()
        if not order_service:
            await callback.answer(
                (
                    "❌ Система заказов недоступна"
                    if lang == "ru"
                    else "❌ Buyurtma xizmati mavjud emas"
                ),
                show_alert=True,
            )
            return

        order_items: list[OrderItem] = []
        for item in items:
            order_items.append(
                OrderItem(
                    offer_id=item.offer_id,
                    store_id=item.store_id,
                    title=item.title,
                    price=int(item.price),
                    original_price=int(item.price),
                    quantity=int(item.quantity),
                    store_name=item.store_name,
                    store_address=item.store_address,
                    delivery_price=0,
                )
            )

        try:
            result: OrderResult = await order_service.create_order(
                user_id=user_id,
                items=order_items,
                order_type="pickup",
                delivery_address=None,
                payment_method="cash",
                notify_customer=True,
                notify_sellers=True,
            )
        except Exception as e:  # pragma: no cover - defensive logging
            from logging_config import logger

            logger.error(f"Failed to create unified pickup order from cart: {e}")
            await callback.answer(
                (
                    "❌ Не удалось создать заказ"
                    if lang == "ru"
                    else "❌ Buyurtma yaratib bo'lmadi"
                ),
                show_alert=True,
            )
            return

        if not result.success:
            msg = result.error_message or (
                "❌ Не удалось создать заказ"
                if lang == "ru"
                else "❌ Buyurtma yaratib bo'lmadi"
            )
            await callback.answer(msg, show_alert=True)
            return

        cart_storage.clear_cart(user_id)

        # UnifiedOrderService уже отправил клиенту подробное сообщение
        # "ЗАКАЗ ОФОРМЛЕН" с кодом и инструкциями.
        # Здесь оставляем только короткий попап для ощущения завершённости.

        # Short popup for continuity
        await callback.answer("✅", show_alert=False)

    @router.callback_query(F.data == "back_to_menu")
    async def back_to_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        await state.clear()

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        cart_count = cart_storage.get_cart_count(user_id)

        text = "🏠 Главное меню" if lang == "ru" else "🏠 Asosiy menyu"

        await callback.message.answer(text, reply_markup=main_menu_customer(lang, cart_count))
        await callback.answer()
