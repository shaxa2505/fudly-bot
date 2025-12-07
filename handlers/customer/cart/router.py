"""Cart handlers - add to cart, view cart, checkout."""
from __future__ import annotations

import html
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import main_menu_customer, phone_request_keyboard
from handlers.common.states import OrderDelivery, Registration
from localization import get_text

from .storage import CartItem, cart_storage

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


router = Router(name="cart")

# Module dependencies
db: Any = None
bot: Any = None


def setup_dependencies(database: Any, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


def _esc(val: Any) -> str:
    """HTML-escape helper."""
    if val is None:
        return ""
    return html.escape(str(val))


# ===================== CART KEYBOARDS =====================


def build_cart_item_keyboard(
    lang: str,
    offer_id: int,
    quantity: int,
    max_qty: int,
) -> InlineKeyboardBuilder:
    """Build keyboard for cart item: [−] [qty] [+] and remove."""
    kb = InlineKeyboardBuilder()

    minus_enabled = quantity > 1
    plus_enabled = quantity < max_qty

    minus_text = "➖" if minus_enabled else "⬜"
    plus_text = "➕" if plus_enabled else "⬜"

    kb.button(
        text=minus_text,
        callback_data=f"cart_qty_{offer_id}_{quantity - 1}" if minus_enabled else "cart_noop",
    )
    kb.button(text=f"📦 {quantity}", callback_data="cart_noop")
    kb.button(
        text=plus_text,
        callback_data=f"cart_qty_{offer_id}_{quantity + 1}" if plus_enabled else "cart_noop",
    )

    # Remove button
    remove_text = "🗑 Удалить" if lang == "ru" else "🗑 O'chirish"
    kb.button(text=remove_text, callback_data=f"cart_remove_{offer_id}")

    kb.adjust(3, 1)
    return kb


def build_cart_keyboard(lang: str, has_items: bool) -> InlineKeyboardBuilder:
    """Build main cart keyboard with improved empty state CTA."""
    kb = InlineKeyboardBuilder()

    if has_items:
        # Checkout button
        checkout_text = "✅ Оформить заказ" if lang == "ru" else "✅ Buyurtma berish"
        kb.button(text=checkout_text, callback_data="cart_checkout")

        # Clear cart
        clear_text = "🗑 Очистить корзину" if lang == "ru" else "🗑 Savatni tozalash"
        kb.button(text=clear_text, callback_data="cart_clear")

        # Continue shopping
        continue_text = "🔙 Продолжить покупки" if lang == "ru" else "🔙 Xaridni davom ettirish"
        kb.button(text=continue_text, callback_data="cart_continue")

        kb.adjust(1)
    else:
        # Empty cart - show CTA to browse offers
        cta_text = get_text(lang, "cart_empty_cta")
        kb.button(text=cta_text, callback_data="cart_browse_offers")
        kb.adjust(1)

    return kb


def build_add_to_cart_keyboard(
    lang: str,
    offer_id: int,
    store_id: int,
    quantity: int,
    max_qty: int,
) -> InlineKeyboardBuilder:
    """Build keyboard for adding item to cart with quantity selection."""
    kb = InlineKeyboardBuilder()

    # Quantity controls - use ▫️ for disabled state instead of ugly ⬜
    minus_enabled = quantity > 1
    plus_enabled = quantity < max_qty

    minus_text = "➖" if minus_enabled else "▫️"
    plus_text = "➕" if plus_enabled else "▫️"

    kb.button(
        text=minus_text,
        callback_data=f"addcart_qty_{offer_id}_{quantity - 1}" if minus_enabled else "cart_noop",
    )
    kb.button(text=f"📦 {quantity}", callback_data="cart_noop")
    kb.button(
        text=plus_text,
        callback_data=f"addcart_qty_{offer_id}_{quantity + 1}" if plus_enabled else "cart_noop",
    )

    # Add to cart button
    add_text = "🛒 В корзину" if lang == "ru" else "🛒 Savatga"
    kb.button(text=add_text, callback_data=f"addcart_confirm_{offer_id}_{quantity}")

    # Back button
    back_text = "◀️ Назад" if lang == "ru" else "◀️ Orqaga"
    kb.button(text=back_text, callback_data=f"addcart_cancel_{store_id}")

    kb.adjust(3, 1, 1)
    return kb


# ===================== CART TEXT BUILDERS =====================


def build_cart_text(lang: str, items: list[CartItem]) -> str:
    """Build cart view text with improved empty state."""
    if not items:
        # Use localized empty state from localization.py
        return get_text(lang, "cart_empty")

    currency = "so'm" if lang == "uz" else "сум"
    lines = [f"🛒 <b>{'Savat' if lang == 'uz' else 'Корзина'}</b>\n"]

    total = 0
    for i, item in enumerate(items, 1):
        subtotal = item.price * item.quantity
        total += subtotal

        lines.append(f"\n<b>{i}. {_esc(item.title)}</b>")
        lines.append(f"   {item.quantity} × {item.price:,} = <b>{subtotal:,}</b> {currency}")
        lines.append(f"   🏪 {_esc(item.store_name)}")

    lines.append("\n" + "─" * 25)
    total_label = "JAMI" if lang == "uz" else "ИТОГО"
    lines.append(f"💵 <b>{total_label}: {total:,} {currency}</b>")

    return "\n".join(lines)


def build_add_cart_text(
    lang: str,
    title: str,
    price: int,
    quantity: int,
    original_price: int = 0,
    store_name: str = "",
    max_qty: int = 99,
) -> str:
    """Build text for add-to-cart selection."""
    currency = "so'm" if lang == "uz" else "сум"
    header = "Savatga qo'shing" if lang == "uz" else "Добавить в корзину"

    lines = [f"🛒 <b>{header}</b>\n"]
    lines.append(f"📦 <b>{_esc(title)}</b>")

    if original_price and original_price > price:
        discount_pct = int((1 - price / original_price) * 100)
        lines.append(f"<s>{original_price:,}</s> → <b>{price:,}</b> {currency} (-{discount_pct}%)")
    else:
        lines.append(f"💰 <b>{price:,}</b> {currency}")

    if store_name:
        lines.append(f"\n🏪 {_esc(store_name)}")

    lines.append("")
    lines.append("─" * 25)
    qty_label = "Miqdor" if lang == "uz" else "Количество"
    lines.append(f"📦 {qty_label}: <b>{quantity}</b>")

    subtotal = price * quantity
    lines.append(f"💵 {subtotal:,} {currency}")

    if quantity >= max_qty:
        max_text = "Maks. miqdor" if lang == "uz" else "Макс. кол-во"
        lines.append(f"⚠️ {max_text}")

    return "\n".join(lines)


# ===================== HANDLERS =====================


@router.message(F.text.in_(["🛒 Корзина", "🛒 Savat"]))
async def show_cart(message: types.Message, state: FSMContext) -> None:
    """Show cart contents."""
    if not db or not message.from_user:
        return

    await state.clear()
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    items = cart_storage.get_cart(user_id)
    text = build_cart_text(lang, items)
    kb = build_cart_keyboard(lang, len(items) > 0)

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


async def view_cart_message(message: types.Message, state: FSMContext) -> None:
    """Show cart from regular message (for menu button)."""
    if not db:
        return

    await state.clear()
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    items = cart_storage.get_cart(user_id)
    text = build_cart_text(lang, items)
    kb = build_cart_keyboard(lang, len(items) > 0)

    # Show cart with inline keyboard
    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    
    # Update main menu with correct cart count
    cart_count = cart_storage.get_cart_count(user_id)
    await message.answer(
        get_text(lang, "main_menu"),
        reply_markup=main_menu_customer(lang, cart_count),
    )


@router.callback_query(F.data == "view_cart")
async def view_cart_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Show cart from callback."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    items = cart_storage.get_cart(user_id)
    text = build_cart_text(lang, items)
    kb = build_cart_keyboard(lang, len(items) > 0)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "cart_noop")
async def cart_noop(callback: types.CallbackQuery) -> None:
    """No-op for disabled buttons."""
    await callback.answer()


@router.callback_query(F.data == "cart_browse_offers")
async def cart_browse_offers(callback: types.CallbackQuery, state: FSMContext) -> None:
    """CTA button from empty cart - go to hot offers."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Delete cart message and redirect to hot offers
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Simulate clicking "Hot offers" button
    from aiogram.types import Message

    # Send a synthetic message to trigger hot offers handler
    # or just send the main menu and let user click
    await callback.message.answer(
        "🔥 " + get_text(lang, "hot_offers_title"),
        parse_mode="HTML",
        reply_markup=main_menu_customer(lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cart_qty_"))
async def cart_update_quantity(callback: types.CallbackQuery) -> None:
    """Update cart item quantity."""
    if not db or not callback.message or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        parts = callback.data.split("_")
        offer_id = int(parts[2])
        new_qty = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    if new_qty <= 0:
        cart_storage.remove_item(user_id, offer_id)
    else:
        cart_storage.update_quantity(user_id, offer_id, new_qty)

    # Refresh cart view
    items = cart_storage.get_cart(user_id)
    text = build_cart_text(lang, items)
    kb = build_cart_keyboard(lang, len(items) > 0)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        logger.debug(f"Could not edit cart message: {e}")
    await callback.answer()


@router.callback_query(F.data.startswith("cart_remove_"))
async def cart_remove_item(callback: types.CallbackQuery) -> None:
    """Remove item from cart."""
    if not db or not callback.message or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        offer_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    cart_storage.remove_item(user_id, offer_id)

    # Refresh cart
    items = cart_storage.get_cart(user_id)
    text = build_cart_text(lang, items)
    kb = build_cart_keyboard(lang, len(items) > 0)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        logger.debug(f"Could not edit cart message: {e}")

    await callback.answer("✓ Удалено" if lang == "ru" else "✓ O'chirildi")


@router.callback_query(F.data == "cart_clear")
async def cart_clear(callback: types.CallbackQuery) -> None:
    """Clear entire cart."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    cart_storage.clear_cart(user_id)

    text = build_cart_text(lang, [])
    kb = build_cart_keyboard(lang, False)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        logger.debug(f"Could not edit cart message: {e}")

    await callback.answer("🗑 Корзина очищена" if lang == "ru" else "🗑 Savat tozalandi")


@router.callback_query(F.data == "cart_continue")
async def cart_continue_shopping(callback: types.CallbackQuery) -> None:
    """Return to main menu to continue shopping."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    cart_count = cart_storage.get_cart_count(user_id)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        get_text(lang, "main_menu"),
        reply_markup=main_menu_customer(lang, cart_count),
    )
    await callback.answer()


@router.callback_query(F.data == "cart_checkout")
async def cart_checkout(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start checkout flow."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Check if cart is empty
    if cart_storage.is_empty(user_id):
        await callback.answer("Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True)
        return

    # Check if user has phone
    user = db.get_user_model(user_id)
    if not user or not user.phone:
        await callback.message.answer(
            "📱 Для оформления заказа укажите номер телефона"
            if lang == "ru"
            else "📱 Buyurtma berish uchun telefon raqamingizni kiriting",
            reply_markup=phone_request_keyboard(lang),
        )
        await state.update_data(pending_cart_checkout=True)
        await state.set_state(Registration.phone)
        await callback.answer()
        return

    # Check if multiple stores - for now only single store checkout
    stores = cart_storage.get_cart_stores(user_id)
    if len(stores) > 1:
        await callback.answer(
            "Можно оформить заказ только из одного магазина. Удалите лишние товары."
            if lang == "ru"
            else "Faqat bitta do'kondan buyurtma berish mumkin. Ortiqcha mahsulotlarni o'chiring.",
            show_alert=True,
        )
        return

    items = cart_storage.get_cart(user_id)
    total = cart_storage.get_cart_total(user_id)

    # Get store info
    store_id = items[0].store_id
    store = db.get_store(store_id)
    store_name = store.get("name") if isinstance(store, dict) else (store[2] if store else "")
    delivery_enabled = items[0].delivery_enabled
    delivery_price = items[0].delivery_price

    currency = "so'm" if lang == "uz" else "сум"

    # Build checkout summary
    lines = [f"📋 <b>{'Buyurtma' if lang == 'uz' else 'Заказ'}</b>\n"]
    lines.append(f"🏪 {_esc(store_name)}\n")

    for item in items:
        subtotal = item.price * item.quantity
        lines.append(f"• {_esc(item.title)} × {item.quantity} = {subtotal:,} {currency}")

    lines.append("\n" + "─" * 25)
    lines.append(f"💵 <b>{'Jami' if lang == 'uz' else 'Итого'}: {total:,} {currency}</b>")

    if delivery_enabled:
        lines.append(
            f"🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}"
        )

    text = "\n".join(lines)

    # Build checkout keyboard
    kb = InlineKeyboardBuilder()

    if delivery_enabled:
        kb.button(
            text="🏪 Самовывоз" if lang == "ru" else "🏪 O'zim olib ketaman",
            callback_data="checkout_pickup",
        )
        kb.button(
            text="🚚 Доставка" if lang == "ru" else "🚚 Yetkazish",
            callback_data="checkout_delivery",
        )
    else:
        kb.button(
            text="✅ Подтвердить" if lang == "ru" else "✅ Tasdiqlash",
            callback_data="checkout_pickup",
        )

    kb.button(text="◀️ Назад" if lang == "ru" else "◀️ Orqaga", callback_data="view_cart")
    kb.adjust(2 if delivery_enabled else 1, 1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "checkout_pickup")
async def checkout_pickup(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Process pickup order from cart using booking system (same as single orders)."""
    if not db or not bot or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    items = cart_storage.get_cart(user_id)
    if not items:
        await callback.answer("Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True)
        return

    # Create bookings for each item using create_booking_atomic (same as single orders)
    success_bookings: list[dict[str, Any]] = []
    failed_items: list[str] = []

    for item in items:
        try:
            # Use create_booking_atomic which returns (ok, booking_id, code, error_reason)
            ok, booking_id, booking_code, error_reason = db.create_booking_atomic(
                offer_id=item.offer_id,
                user_id=user_id,
                quantity=item.quantity,
            )

            if ok and booking_id and booking_code:
                success_bookings.append(
                    {
                        "booking_id": booking_id,
                        "title": item.title,
                        "quantity": item.quantity,
                        "code": booking_code,
                        "store_name": item.store_name,
                        "store_address": item.store_address,
                        "store_id": item.store_id,
                    }
                )
                logger.info(
                    f"Created pickup booking {booking_id} for user {user_id}, offer {item.offer_id}"
                )
            else:
                logger.error(f"Failed to create booking for offer {item.offer_id}: {error_reason}")
                failed_items.append(item.title)

        except Exception as e:
            logger.error(f"Exception creating booking for offer {item.offer_id}: {e}")
            failed_items.append(item.title)

    if not success_bookings:
        await callback.answer(
            "Ошибка при создании заказа" if lang == "ru" else "Buyurtma yaratishda xatolik",
            show_alert=True,
        )
        return

    # Send notifications to sellers (grouped by store)
    stores_bookings: dict[int, list[dict]] = {}
    for booking in success_bookings:
        store_id = booking["store_id"]
        if store_id not in stores_bookings:
            stores_bookings[store_id] = []
        stores_bookings[store_id].append(booking)

    # Notify each store owner
    for store_id, store_bookings in stores_bookings.items():
        try:
            store = db.get_store(store_id)
            if not store:
                continue

            owner_id = store.get("owner_id") if isinstance(store, dict) else None
            if not owner_id:
                continue

            seller_lang = db.get_user_language(owner_id)
            customer = db.get_user_model(user_id)
            customer_name = customer.first_name if customer else "—"
            customer_phone = customer.phone if customer else "—"

            # Build notification text
            lines = []
            if seller_lang == "uz":
                lines.append("🔔 <b>Yangi bron!</b>\n")
                lines.append(f"👤 {_esc(customer_name)}")
                lines.append(f"📱 {customer_phone}\n")

                for b in store_bookings:
                    lines.append(f"📦 {_esc(b['title'])} × {b['quantity']}")
                    lines.append(f"🎫 Kod: <b>{b['code']}</b>\n")

                lines.append("🏪 O'zim olib ketish")
            else:
                lines.append("🔔 <b>Новое бронирование!</b>\n")
                lines.append(f"👤 {_esc(customer_name)}")
                lines.append(f"📱 {customer_phone}\n")

                for b in store_bookings:
                    lines.append(f"📦 {_esc(b['title'])} × {b['quantity']}")
                    lines.append(f"🎫 Код: <b>{b['code']}</b>\n")

                lines.append("🏪 Самовывоз")

            seller_text = "\n".join(lines)

            # Build keyboard with ALL booking IDs for batch confirmation
            booking_ids = [str(b["booking_id"]) for b in store_bookings]
            booking_ids_str = ",".join(booking_ids)
            kb = InlineKeyboardBuilder()
            confirm_text = "✅ Barchasini qabul qilish" if seller_lang == "uz" else "✅ Подтвердить все"
            reject_text = "❌ Barchasini rad etish" if seller_lang == "uz" else "❌ Отклонить все"
            kb.button(text=confirm_text, callback_data=f"partner_confirm_batch_{booking_ids_str}")
            kb.button(text=reject_text, callback_data=f"partner_reject_batch_{booking_ids_str}")
            kb.adjust(1)

            await bot.send_message(
                owner_id, seller_text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
            logger.info(f"Sent batch booking notification to seller {owner_id} for bookings {booking_ids}")

        except Exception as e:
            logger.error(f"Failed to notify seller for store {store_id}: {e}")

    # Clear cart
    cart_storage.clear_cart(user_id)

    # Build success message for customer
    lines = [f"✅ <b>{'Buyurtma qabul qilindi!' if lang == 'uz' else 'Заказ оформлен!'}</b>\n"]

    for b in success_bookings:
        lines.append(f"\n📦 {_esc(b['title'])} × {b['quantity']}")
        lines.append(f"🎫 <b>Код: {b['code']}</b>")
        lines.append(f"🏪 {_esc(b['store_name'])}")
        if b["store_address"]:
            lines.append(f"📍 {_esc(b['store_address'])}")

    lines.append("")
    lines.append("─" * 25)
    lines.append(
        "👆 Покажите код продавцу при получении"
        if lang == "ru"
        else "👆 Olishda sotuvchiga kodni ko'rsating"
    )

    if failed_items:
        lines.append(
            "\n⚠️ " + ("Не удалось забронировать:" if lang == "ru" else "Bron qilib bo'lmadi:")
        )
        for title in failed_items:
            lines.append(f"  • {_esc(title)}")

    text = "\n".join(lines)

    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception:
        pass

    cart_count = cart_storage.get_cart_count(user_id)
    await callback.message.answer(
        get_text(lang, "main_menu"),
        reply_markup=main_menu_customer(lang, cart_count),
    )
    await callback.answer()


@router.callback_query(F.data == "checkout_delivery")
async def checkout_delivery(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start delivery flow for cart order."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    items = cart_storage.get_cart(user_id)
    if not items:
        await callback.answer("Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True)
        return

    # Store cart data for delivery flow
    await state.update_data(
        cart_checkout=True,
        cart_items=[item.to_dict() for item in items],
    )
    await state.set_state(OrderDelivery.address)

    # Get saved address
    saved_address = None
    try:
        saved_address = db.get_last_delivery_address(user_id)
    except Exception:
        pass

    currency = "so'm" if lang == "uz" else "сум"
    total = sum(item.price * item.quantity for item in items)
    delivery_price = items[0].delivery_price if items else 0

    lines = [
        f"🚚 <b>{'Yetkazish' if lang == 'uz' else 'Доставка'}</b>\n",
        f"💵 {'Mahsulotlar' if lang == 'uz' else 'Товары'}: {total:,} {currency}",
        f"🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}",
        f"💰 <b>{'Jami' if lang == 'uz' else 'Итого'}: {total + delivery_price:,} {currency}</b>",
        "",
        f"📍 {'Manzilingizni kiriting' if lang == 'uz' else 'Введите ваш адрес'}:",
    ]

    if saved_address:
        lines.append(f"\n💾 {'Saqlangan' if lang == 'uz' else 'Сохранённый'}: {saved_address}")

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    if saved_address:
        kb.button(text=f"📍 {saved_address[:30]}", callback_data="cart_use_saved_address")
    kb.button(text="◀️ Назад" if lang == "ru" else "◀️ Orqaga", callback_data="cart_checkout")
    kb.adjust(1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "cart_use_saved_address")
async def cart_use_saved_address(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Use saved address for cart delivery."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Get saved address
    saved_address = None
    try:
        saved_address = db.get_last_delivery_address(user_id)
    except Exception:
        pass

    if not saved_address:
        await callback.answer(
            "Нет сохраненного адреса" if lang == "ru" else "Saqlangan manzil yo'q", show_alert=True
        )
        return

    # Save address to state
    await state.update_data(address=saved_address)

    # Move to payment method selection
    await cart_address_to_payment(callback, state, saved_address)


@router.message(OrderDelivery.address)
async def cart_address_input(message: types.Message, state: FSMContext) -> None:
    """Handle address input for cart delivery."""
    if not db or not message.from_user:
        return

    lang = db.get_user_language(message.from_user.id)
    text = (message.text or "").strip()

    # Check main menu button
    if text in ["🏠 Главное меню", "🏠 Bosh sahifa", "🏠 Asosiy menyu"]:
        await state.clear()
        cart_count = cart_storage.get_cart_count(message.from_user.id)
        await message.answer(
            get_text(lang, "main_menu"),
            reply_markup=main_menu_customer(lang, cart_count),
        )
        return

    # Check cancel
    if any(c in text.lower() for c in ["отмена", "bekor", "❌"]) or text.startswith("/"):
        await state.clear()
        msg = "❌ Bekor qilindi" if lang == "uz" else "❌ Отменено"
        cart_count = cart_storage.get_cart_count(message.from_user.id)
        await message.answer(msg, reply_markup=main_menu_customer(lang, cart_count))
        return

    # Validate address length
    if len(text) < 10:
        msg = (
            "❌ Manzil juda qisqa (min 10 belgi)"
            if lang == "uz"
            else "❌ Адрес слишком короткий (мин 10 символов)"
        )
        await message.answer(msg)
        return

    # Save address
    await state.update_data(address=text)

    # Save as last address for user
    try:
        db.save_delivery_address(message.from_user.id, text)
    except Exception as e:
        logger.warning(f"Could not save address: {e}")

    # Show payment options
    data = await state.get_data()
    items = cart_storage.get_cart(message.from_user.id)

    if not items:
        await message.answer("Корзина пуста" if lang == "ru" else "Savat bo'sh")
        await state.clear()
        return

    currency = "so'm" if lang == "uz" else "сум"
    total = sum(item.price * item.quantity for item in items)
    delivery_price = items[0].delivery_price if items else 0

    payment_text = "To'lov turini tanlang" if lang == "uz" else "Выберите способ оплаты"
    lines = [
        f"✅ <b>{'Manzil saqlandi' if lang == 'uz' else 'Адрес сохранён'}</b>\n",
        f"📍 {_esc(text)}\n",
        f"💵 {'Mahsulotlar' if lang == 'uz' else 'Товары'}: {total:,} {currency}",
        f"🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}",
        f"💰 <b>{'Jami' if lang == 'uz' else 'Итого'}: {total + delivery_price:,} {currency}</b>\n",
        f"💳 {payment_text}:",
    ]

    text_msg = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    kb.button(text="💵 Наличные" if lang == "ru" else "💵 Naqd", callback_data="cart_payment_cash")
    kb.button(text="💳 Карта" if lang == "ru" else "💳 Karta", callback_data="cart_payment_card")
    kb.button(text="◀️ Назад" if lang == "ru" else "◀️ Orqaga", callback_data="checkout_delivery")
    kb.adjust(2, 1)

    await message.answer(text_msg, parse_mode="HTML", reply_markup=kb.as_markup())


async def cart_address_to_payment(
    callback: types.CallbackQuery, state: FSMContext, address: str
) -> None:
    """Helper to transition from address to payment selection."""
    if not db:
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    items = cart_storage.get_cart(user_id)

    if not items:
        await callback.answer("Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True)
        return

    currency = "so'm" if lang == "uz" else "сум"
    total = sum(item.price * item.quantity for item in items)
    delivery_price = items[0].delivery_price if items else 0

    payment_text = "To'lov turini tanlang" if lang == "uz" else "Выберите способ оплаты"
    lines = [
        f"✅ <b>{'Manzil saqlandi' if lang == 'uz' else 'Адрес сохранён'}</b>\n",
        f"📍 {_esc(address)}\n",
        f"💵 {'Mahsulotlar' if lang == 'uz' else 'Товары'}: {total:,} {currency}",
        f"🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}",
        f"💰 <b>{'Jami' if lang == 'uz' else 'Итого'}: {total + delivery_price:,} {currency}</b>\n",
        f"💳 {payment_text}:",
    ]

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    kb.button(text="💵 Наличные" if lang == "ru" else "💵 Naqd", callback_data="cart_payment_cash")
    kb.button(text="💳 Карта" if lang == "ru" else "💳 Karta", callback_data="cart_payment_card")
    kb.button(text="◀️ Назад" if lang == "ru" else "◀️ Orqaga", callback_data="checkout_delivery")
    kb.adjust(2, 1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


# ===================== ADD TO CART (from offer view) =====================


@router.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start add-to-cart flow for an offer."""
    if not db or not callback.message or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        offer_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(
            "Товар не найден" if lang == "ru" else "Mahsulot topilmadi", show_alert=True
        )
        return

    # Get offer details
    def get_field(data: Any, key: str, default: Any = None) -> Any:
        if isinstance(data, dict):
            return data.get(key, default)
        return default

    max_qty = get_field(offer, "quantity", 1)
    if max_qty <= 0:
        await callback.answer(
            "Товар закончился" if lang == "ru" else "Mahsulot tugadi", show_alert=True
        )
        return

    price = get_field(offer, "discount_price", 0)
    original_price = get_field(offer, "original_price", 0)
    title = get_field(offer, "title", "Товар")
    store_id = get_field(offer, "store_id")

    store = db.get_store(store_id) if store_id else None
    store_name = get_field(store, "name", "")

    # Save offer data for add-to-cart flow
    await state.update_data(
        addcart_offer_id=offer_id,
        addcart_store_id=store_id,
        addcart_price=price,
        addcart_original_price=original_price,
        addcart_title=title,
        addcart_max_qty=max_qty,
        addcart_store_name=store_name,
        addcart_quantity=1,
    )

    text = build_add_cart_text(lang, title, price, 1, original_price, store_name, max_qty)
    kb = build_add_to_cart_keyboard(lang, offer_id, store_id, 1, max_qty)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("addcart_qty_"))
async def addcart_update_qty(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Update quantity in add-to-cart flow."""
    if not db or not callback.message or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    data = await state.get_data()

    try:
        parts = callback.data.split("_")
        offer_id = int(parts[2])
        new_qty = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    max_qty = data.get("addcart_max_qty", 99)
    if new_qty < 1 or new_qty > max_qty:
        await callback.answer("❌", show_alert=True)
        return

    await state.update_data(addcart_quantity=new_qty)

    title = data.get("addcart_title", "")
    price = data.get("addcart_price", 0)
    original_price = data.get("addcart_original_price", 0)
    store_name = data.get("addcart_store_name", "")
    store_id = data.get("addcart_store_id", 0)

    text = build_add_cart_text(lang, title, price, new_qty, original_price, store_name, max_qty)
    kb = build_add_to_cart_keyboard(lang, offer_id, store_id, new_qty, max_qty)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        logger.debug(f"Could not edit add-cart message: {e}")
    await callback.answer()


@router.callback_query(F.data == "cart_payment_cash")
async def cart_payment_cash(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Process cart order with cash payment."""
    await finalize_cart_order(callback, state, "cash")


@router.callback_query(F.data == "cart_payment_card")
async def cart_payment_card(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Process cart order with card payment."""
    await finalize_cart_order(callback, state, "card")


async def finalize_cart_order(
    callback: types.CallbackQuery, state: FSMContext, payment_method: str
) -> None:
    """Create delivery orders from cart items (same as single orders)."""
    if not db or not bot or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    cart_items = cart_storage.get_cart(user_id)
    if not cart_items:
        await callback.answer("Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True)
        return

    data = await state.get_data()
    address = data.get("address", "")

    if not address:
        await callback.answer(
            "Адрес не указан" if lang == "ru" else "Manzil ko'rsatilmagan",
            show_alert=True,
        )
        return

    # Create orders for each item using db.create_order (same as single orders)
    success_orders: list[dict[str, Any]] = []
    failed_items: list[str] = []

    for item in cart_items:
        try:
            order_id = db.create_order(
                user_id=user_id,
                store_id=item.store_id,
                offer_id=item.offer_id,
                quantity=item.quantity,
                order_type="delivery",
                delivery_address=address,
                delivery_price=item.delivery_price,
                payment_method=payment_method,
            )

            if order_id:
                # Decrement offer quantity
                db.increment_offer_quantity_atomic(item.offer_id, -int(item.quantity))

                success_orders.append(
                    {
                        "order_id": order_id,
                        "title": item.title,
                        "quantity": item.quantity,
                        "price": item.price,
                        "store_name": item.store_name,
                        "store_id": item.store_id,
                        "delivery_price": item.delivery_price,
                    }
                )
                logger.info(
                    f"Created delivery order {order_id} for user {user_id}, offer {item.offer_id}"
                )
            else:
                logger.error(
                    f"Failed to create order for offer {item.offer_id}: create_order returned None"
                )
                failed_items.append(item.title)

        except Exception as e:
            logger.error(f"Exception creating order for offer {item.offer_id}: {e}")
            failed_items.append(item.title)

    if not success_orders:
        await callback.answer(
            "Ошибка при создании заказа" if lang == "ru" else "Buyurtma yaratishda xatolik",
            show_alert=True,
        )
        return

    # Send notifications to sellers (grouped by store)
    stores_orders: dict[int, list[dict[str, Any]]] = {}
    for order in success_orders:
        store_id = order["store_id"]
        if store_id not in stores_orders:
            stores_orders[store_id] = []
        stores_orders[store_id].append(order)

    # Get customer info
    customer = db.get_user_model(user_id)
    customer_name = customer.first_name if customer else "—"
    customer_phone = customer.phone if customer else "—"

    # Notify each store owner
    for store_id, store_orders in stores_orders.items():
        try:
            store = db.get_store(store_id)
            if not store:
                continue

            owner_id = store.get("owner_id") if isinstance(store, dict) else None
            if not owner_id:
                continue

            seller_lang = db.get_user_language(owner_id)
            currency = "so'm" if seller_lang == "uz" else "сум"

            # Calculate store totals
            store_total = sum(o["price"] * o["quantity"] for o in store_orders)
            store_delivery = store_orders[0].get("delivery_price", 0)

            # Build notification text
            lines = []
            order_ids = [str(o["order_id"]) for o in store_orders]

            if seller_lang == "uz":
                lines.append("🔔 <b>Yangi buyurtma!</b>\n")
                lines.append(f"👤 {_esc(customer_name)}")
                lines.append(f"📱 {customer_phone}")
                lines.append(f"📍 {_esc(address)}\n")

                for o in store_orders:
                    subtotal = o["price"] * o["quantity"]
                    lines.append(f"📦 {_esc(o['title'])} × {o['quantity']}")
                    lines.append(f"   {subtotal:,} {currency}\n")

                lines.append("─" * 25)
                lines.append(f"💵 Mahsulotlar: {store_total:,} {currency}")
                lines.append(f"🚚 Yetkazish: {store_delivery:,} {currency}")
                lines.append(f"💰 <b>Jami: {store_total + store_delivery:,} {currency}</b>\n")
                lines.append(f"💳 To'lov: {payment_method}")
            else:
                lines.append("🔔 <b>Новый заказ!</b>\n")
                lines.append(f"👤 {_esc(customer_name)}")
                lines.append(f"📱 {customer_phone}")
                lines.append(f"📍 {_esc(address)}\n")

                for o in store_orders:
                    subtotal = o["price"] * o["quantity"]
                    lines.append(f"📦 {_esc(o['title'])} × {o['quantity']}")
                    lines.append(f"   {subtotal:,} {currency}\n")

                lines.append("─" * 25)
                lines.append(f"💵 Товары: {store_total:,} {currency}")
                lines.append(f"🚚 Доставка: {store_delivery:,} {currency}")
                lines.append(f"💰 <b>Итого: {store_total + store_delivery:,} {currency}</b>\n")
                lines.append(f"💳 Оплата: {payment_method}")

            seller_text = "\n".join(lines)

            # Build keyboard with ALL order IDs for batch confirmation
            order_ids_str = ",".join(order_ids)
            kb = InlineKeyboardBuilder()
            confirm_text = "✅ Barchasini qabul qilish" if seller_lang == "uz" else "✅ Подтвердить все"
            reject_text = "❌ Barchasini rad etish" if seller_lang == "uz" else "❌ Отклонить все"
            kb.button(text=confirm_text, callback_data=f"partner_confirm_order_batch_{order_ids_str}")
            kb.button(text=reject_text, callback_data=f"partner_reject_order_batch_{order_ids_str}")
            kb.adjust(1)

            await bot.send_message(
                owner_id, seller_text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
            logger.info(f"Sent batch order notification to seller {owner_id} for orders {order_ids}")

        except Exception as e:
            logger.error(f"Failed to notify seller for store {store_id}: {e}")

    # Clear cart and state
    cart_storage.clear_cart(user_id)
    await state.clear()

    # Build customer confirmation
    currency = "so'm" if lang == "uz" else "сум"
    total_items = sum(o["quantity"] for o in success_orders)
    total_price = sum(o["price"] * o["quantity"] for o in success_orders)
    delivery_price = success_orders[0].get("delivery_price", 0) if success_orders else 0
    grand_total = total_price + delivery_price

    lines = []
    if lang == "uz":
        lines.append("✅ <b>Buyurtma qabul qilindi!</b>\n")
        lines.append(f"📦 Mahsulotlar soni: {total_items}\n")

        for o in success_orders:
            subtotal = o["price"] * o["quantity"]
            lines.append(f"• {_esc(o['title'])} × {o['quantity']}")
            lines.append(f"  {subtotal:,} {currency}\n")

        lines.append("─" * 25)
        lines.append(f"💵 Mahsulotlar: {total_price:,} {currency}")
        lines.append(f"🚚 Yetkazish: {delivery_price:,} {currency}")
        lines.append(f"💰 <b>Jami: {grand_total:,} {currency}</b>\n")
        lines.append(f"📍 {_esc(address)}")
        lines.append(f"💳 To'lov: {payment_method}")
    else:
        lines.append("✅ <b>Заказ оформлен!</b>\n")
        lines.append(f"📦 Количество товаров: {total_items}\n")

        for o in success_orders:
            subtotal = o["price"] * o["quantity"]
            lines.append(f"• {_esc(o['title'])} × {o['quantity']}")
            lines.append(f"  {subtotal:,} {currency}\n")

        lines.append("─" * 25)
        lines.append(f"💵 Товары: {total_price:,} {currency}")
        lines.append(f"🚚 Доставка: {delivery_price:,} {currency}")
        lines.append(f"💰 <b>Итого: {grand_total:,} {currency}</b>\n")
        lines.append(f"📍 {_esc(address)}")
        lines.append(f"💳 Оплата: {payment_method}")

    if failed_items:
        lines.append(
            "\n⚠️ " + ("Не удалось оформить:" if lang == "ru" else "Buyurtma berib bo'lmadi:")
        )
        for title in failed_items:
            lines.append(f"  • {_esc(title)}")

    text = "\n".join(lines)

    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception:
        pass

    # Show main menu with updated cart count (should be 0 now)
    cart_count = cart_storage.get_cart_count(user_id)
    await callback.message.answer(
        get_text(lang, "main_menu"),
        reply_markup=main_menu_customer(lang, cart_count),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("addcart_confirm_"))
async def addcart_confirm(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Add item to cart and show confirmation."""
    if not db or not callback.message or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    data = await state.get_data()

    try:
        parts = callback.data.split("_")
        offer_id = int(parts[2])
        quantity = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    # Get offer details from state or fetch fresh
    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(
            "Товар не найден" if lang == "ru" else "Mahsulot topilmadi", show_alert=True
        )
        return

    def get_field(data_obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(data_obj, dict):
            return data_obj.get(key, default)
        return default

    store_id = data.get("addcart_store_id") or get_field(offer, "store_id")
    store = db.get_store(store_id) if store_id else None

    # Add to cart
    cart_storage.add_item(
        user_id=user_id,
        offer_id=offer_id,
        store_id=store_id,
        title=data.get("addcart_title") or get_field(offer, "title", "Товар"),
        price=data.get("addcart_price") or get_field(offer, "discount_price", 0),
        quantity=quantity,
        original_price=data.get("addcart_original_price") or get_field(offer, "original_price", 0),
        max_quantity=data.get("addcart_max_qty") or get_field(offer, "quantity", 99),
        store_name=data.get("addcart_store_name") or get_field(store, "name", ""),
        store_address=get_field(store, "address", ""),
        photo=get_field(offer, "photo"),
        unit=get_field(offer, "unit", "шт"),
        expiry_date=str(get_field(offer, "expiry_date", "")),
        delivery_enabled=get_field(store, "delivery_enabled", 0) == 1,
        delivery_price=get_field(store, "delivery_price", 0),
    )

    await state.clear()

    cart_count = cart_storage.get_cart_count(user_id)

    # Show confirmation
    text = (
        f"✅ Добавлено в корзину!\n\n" f"🛒 В корзине: {cart_count} товар(ов)"
        if lang == "ru"
        else f"✅ Savatga qo'shildi!\n\n" f"🛒 Savatda: {cart_count} ta mahsulot"
    )

    kb = InlineKeyboardBuilder()
    kb.button(
        text="🛒 Перейти в корзину" if lang == "ru" else "🛒 Savatga o'tish",
        callback_data="view_cart",
    )
    kb.button(
        text="🔙 Продолжить покупки" if lang == "ru" else "🔙 Xaridni davom ettirish",
        callback_data="back_to_menu",
    )
    kb.adjust(1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    # Update reply keyboard with new cart count
    await callback.message.answer(
        get_text(lang, "main_menu"),
        reply_markup=main_menu_customer(lang, cart_count),
    )

    await callback.answer("✅ Добавлено!" if lang == "ru" else "✅ Qo'shildi!")


@router.callback_query(F.data.startswith("addcart_cancel_"))
async def addcart_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel add-to-cart and return to main menu."""
    if not db or not callback.message:
        await callback.answer()
        return

    await state.clear()

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        await callback.message.delete()
    except Exception:
        pass

    # Return to main menu
    cart_count = cart_storage.get_cart_count(user_id)
    await callback.message.answer(
        get_text(lang, "main_menu"),
        reply_markup=main_menu_customer(lang, cart_count),
    )

    await callback.answer()
