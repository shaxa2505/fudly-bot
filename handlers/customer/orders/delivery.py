"""
Optimized delivery order flow - single card UX.

Flow: Click delivery → Single card with qty/address/payment → Confirm → Done
- Saves last delivery address
- Single message updated at each step
- Minimal notifications
"""
from __future__ import annotations

import html
import os
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.utils import get_offer_field, get_store_field
from app.keyboards import main_menu_customer, main_menu_seller
from database_protocol import DatabaseProtocol
from handlers.common.states import OrderDelivery
from handlers.common.utils import is_main_menu_button
from localization import get_text
from logging_config import logger

router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


def _esc(val: Any) -> str:
    """HTML-escape helper."""
    return html.escape(str(val)) if val else ""


def get_appropriate_menu(user_id: int, lang: str) -> Any:
    """Get appropriate menu based on user view mode."""
    from handlers.common import user_view_mode

    if user_view_mode and user_view_mode.get(user_id) == "seller":
        return main_menu_seller(lang)
    return main_menu_customer(lang)


# =============================================================================
# DELIVERY ORDER CARD BUILDERS
# =============================================================================


def build_delivery_card_text(
    lang: str,
    title: str,
    price: int,
    quantity: int,
    max_qty: int,
    store_name: str,
    delivery_price: int,
    address: str | None,
    step: str,  # "qty" | "address" | "payment" | "processing"
) -> str:
    """Build delivery order card text."""
    currency = "so'm" if lang == "uz" else "сум"

    subtotal = price * quantity
    total = subtotal + delivery_price

    lines = [
        f"🚚 <b>{'Yetkazib berish' if lang == 'uz' else 'Доставка'}</b>",
        "",
        f"🛒 <b>{_esc(title)}</b>",
        f"🏪 {_esc(store_name)}",
        "",
        "─" * 24,
    ]

    # Price info
    lines.append(f"💰 {'Narxi' if lang == 'uz' else 'Цена'}: {price:,} {currency}")
    lines.append(
        f"📦 {'Miqdor' if lang == 'uz' else 'Кол-во'}: <b>{quantity}</b> {'dona' if lang == 'uz' else 'шт'}"
    )
    lines.append(f"🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}")
    lines.append("─" * 24)
    lines.append(f"💵 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total:,} {currency}</b>")
    lines.append("")

    # Address section
    if address:
        lines.append(f"📍 {_esc(address)}")

    # Step-specific hints
    if step == "qty":
        hint = "👇 Miqdorni tanlang" if lang == "uz" else "👇 Выберите количество"
        lines.append(f"\n<i>{hint}</i>")
    elif step == "address":
        hint = (
            "📍 Manzilni kiriting yoki tanlang" if lang == "uz" else "📍 Введите адрес или выберите"
        )
        lines.append(f"\n<i>{hint}</i>")
    elif step == "payment":
        hint = "💳 To'lov usulini tanlang" if lang == "uz" else "💳 Выберите способ оплаты"
        lines.append(f"\n<i>{hint}</i>")
    elif step == "processing":
        hint = "⏳ Jarayonda..." if lang == "uz" else "⏳ Обработка..."
        lines.append(f"\n<i>{hint}</i>")

    return "\n".join(lines)


def build_delivery_qty_keyboard(
    lang: str,
    offer_id: int,
    quantity: int,
    max_qty: int,
) -> InlineKeyboardBuilder:
    """Build quantity selection keyboard for delivery."""
    kb = InlineKeyboardBuilder()

    # Row 1: [-] [qty] [+]
    minus_ok = quantity > 1
    plus_ok = quantity < max_qty

    kb.button(
        text="➖" if minus_ok else "⬜",
        callback_data=f"dlv_qty_{offer_id}_{quantity - 1}" if minus_ok else "dlv_noop",
    )
    kb.button(text=f"📦 {quantity}", callback_data="dlv_noop")
    kb.button(
        text="➕" if plus_ok else "⬜",
        callback_data=f"dlv_qty_{offer_id}_{quantity + 1}" if plus_ok else "dlv_noop",
    )

    # Row 2: Continue
    next_text = "📍 Davom etish" if lang == "uz" else "📍 Продолжить"
    kb.button(text=next_text, callback_data=f"dlv_to_address_{offer_id}")

    # Row 3: Cancel
    cancel_text = "❌ Bekor" if lang == "uz" else "❌ Отмена"
    kb.button(text=cancel_text, callback_data="dlv_cancel")

    kb.adjust(3, 1, 1)
    return kb


def build_delivery_address_keyboard(
    lang: str,
    offer_id: int,
    saved_address: str | None,
) -> InlineKeyboardBuilder:
    """Build address selection keyboard."""
    kb = InlineKeyboardBuilder()

    # If user has saved address - show button to use it
    if saved_address:
        short_addr = saved_address[:30] + "..." if len(saved_address) > 30 else saved_address
        kb.button(text=f"📍 {short_addr}", callback_data=f"dlv_use_saved_{offer_id}")

    # Manual input button
    manual_text = "✏️ Yangi manzil" if lang == "uz" else "✏️ Новый адрес"
    kb.button(text=manual_text, callback_data=f"dlv_new_address_{offer_id}")

    # Back and Cancel
    back_text = "⬅️ Orqaga" if lang == "uz" else "⬅️ Назад"
    cancel_text = "❌ Bekor" if lang == "uz" else "❌ Отмена"
    kb.button(text=back_text, callback_data=f"dlv_back_qty_{offer_id}")
    kb.button(text=cancel_text, callback_data="dlv_cancel")

    if saved_address:
        kb.adjust(1, 1, 2)
    else:
        kb.adjust(1, 2)

    return kb


def build_delivery_payment_keyboard(
    lang: str,
    offer_id: int,
) -> InlineKeyboardBuilder:
    """Build payment method selection keyboard."""
    kb = InlineKeyboardBuilder()

    # Payment options
    click_text = "💳 Click" if lang == "uz" else "💳 Click"
    card_text = "🏦 Kartaga o'tkazma" if lang == "uz" else "🏦 Перевод на карту"

    kb.button(text=click_text, callback_data=f"dlv_pay_click_{offer_id}")
    kb.button(text=card_text, callback_data=f"dlv_pay_card_{offer_id}")

    # Back and Cancel
    back_text = "⬅️ Orqaga" if lang == "uz" else "⬅️ Назад"
    cancel_text = "❌ Bekor" if lang == "uz" else "❌ Отмена"
    kb.button(text=back_text, callback_data=f"dlv_back_address_{offer_id}")
    kb.button(text=cancel_text, callback_data="dlv_cancel")

    kb.adjust(2, 2)
    return kb


# =============================================================================
# HANDLERS
# =============================================================================


@router.callback_query(F.data.startswith("order_delivery_"))
async def start_delivery_order(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Start delivery order - show single card with quantity selection."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    max_qty = get_offer_field(offer, "quantity", 0)
    if max_qty <= 0:
        await callback.answer(get_text(lang, "no_offers"), show_alert=True)
        return

    store_id = get_offer_field(offer, "store_id")
    store = db.get_store(store_id)
    if not store:
        await callback.answer("❌", show_alert=True)
        return

    # Check delivery enabled
    if not get_store_field(store, "delivery_enabled", 0):
        msg = "Yetkazib berish mavjud emas" if lang == "uz" else "Доставка недоступна"
        await callback.answer(f"❌ {msg}", show_alert=True)
        return

    # Get details
    price = get_offer_field(offer, "discount_price", 0)
    title = get_offer_field(offer, "title", "")
    store_name = get_store_field(store, "name", "")
    delivery_price = get_store_field(store, "delivery_price", 15000)
    min_order = get_store_field(store, "min_order_amount", 0)

    # Check min order for single item
    if min_order > 0 and price < min_order:
        currency = "so'm" if lang == "uz" else "сум"
        msg = (
            f"Min. buyurtma: {min_order:,} {currency}"
            if lang == "uz"
            else f"Мин. заказ: {min_order:,} {currency}"
        )
        await callback.answer(f"❌ {msg}", show_alert=True)
        return

    # Get saved address
    saved_address = None
    try:
        saved_address = db.get_last_delivery_address(user_id)
    except Exception:
        pass

    # Get offer photo
    offer_photo = get_offer_field(offer, "photo", None)

    # Save to state
    await state.update_data(
        offer_id=offer_id,
        store_id=store_id,
        quantity=1,
        max_qty=max_qty,
        price=price,
        title=title,
        store_name=store_name,
        delivery_price=delivery_price,
        min_order=min_order,
        saved_address=saved_address,
        address=None,
        offer_photo=offer_photo,
    )
    await state.set_state(OrderDelivery.quantity)

    # Build and show card
    text = build_delivery_card_text(
        lang, title, price, 1, max_qty, store_name, delivery_price, None, "qty"
    )
    kb = build_delivery_qty_keyboard(lang, offer_id, 1, max_qty)

    # Update existing message
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        # Fallback: delete and send new
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    await callback.answer()


@router.callback_query(F.data == "dlv_noop")
async def dlv_noop(callback: types.CallbackQuery) -> None:
    """No-op for disabled buttons."""
    await callback.answer()


@router.callback_query(F.data == "dlv_cancel")
async def dlv_cancel(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Cancel delivery order - return to hot offers list."""
    data = await state.get_data()
    last_page = data.get("last_hot_page", 0)
    await state.clear()

    lang = db.get_user_language(callback.from_user.id) if db else "ru"
    user_id = callback.from_user.id

    # Delete current message
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Return to hot offers list
    from app.core.utils import normalize_city
    from app.services.offer_service import OfferService

    user = db.get_user_model(user_id)
    city = user.city if user else "Ташкент"
    search_city = normalize_city(city)

    offer_service = OfferService(db)
    per_page = 5
    result = offer_service.list_hot_offers(search_city, limit=per_page, offset=last_page * per_page)

    if not result.items:
        # No offers - show main menu
        msg = "❌ Bekor qilindi" if lang == "uz" else "❌ Отменено"
        await callback.message.answer(msg, reply_markup=main_menu_customer(lang))
        await callback.answer()
        return

    # Build hot offers list
    from app.keyboards.offers import hot_offers_compact_keyboard
    from app.templates.offers import render_hot_offers_list

    total_pages = (result.total + per_page - 1) // per_page
    select_hint = "👆 Выберите товар" if lang == "ru" else "👆 Mahsulotni tanlang"
    text = render_hot_offers_list(
        lang, city, result.items, result.total, select_hint, offset=last_page * per_page
    )
    kb = hot_offers_compact_keyboard(lang, result.items, last_page, total_pages)

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("dlv_qty_"))
async def dlv_change_qty(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Change quantity."""
    if not callback.from_user:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)

    try:
        parts = callback.data.split("_")
        offer_id = int(parts[2])
        new_qty = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    data = await state.get_data()
    max_qty = data.get("max_qty", 1)
    min_order = data.get("min_order", 0)
    price = data.get("price", 0)

    if new_qty < 1 or new_qty > max_qty:
        await callback.answer("❌", show_alert=True)
        return

    # Check min order
    if min_order > 0 and (price * new_qty) < min_order:
        currency = "so'm" if lang == "uz" else "сум"
        msg = f"Min: {min_order:,} {currency}"
        await callback.answer(f"❌ {msg}", show_alert=True)
        return

    await state.update_data(quantity=new_qty)

    # Rebuild card
    text = build_delivery_card_text(
        lang,
        data.get("title", ""),
        price,
        new_qty,
        max_qty,
        data.get("store_name", ""),
        data.get("delivery_price", 0),
        None,
        "qty",
    )
    kb = build_delivery_qty_keyboard(lang, offer_id, new_qty, max_qty)

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data.startswith("dlv_to_address_"))
async def dlv_to_address(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Move to address selection step."""
    if not callback.from_user:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    offer_id = data.get("offer_id")

    await state.set_state(OrderDelivery.address)

    # Build card with address step
    text = build_delivery_card_text(
        lang,
        data.get("title", ""),
        data.get("price", 0),
        data.get("quantity", 1),
        data.get("max_qty", 1),
        data.get("store_name", ""),
        data.get("delivery_price", 0),
        None,
        "address",
    )
    kb = build_delivery_address_keyboard(lang, offer_id, data.get("saved_address"))

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data.startswith("dlv_back_qty_"))
async def dlv_back_to_qty(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Go back to quantity selection."""
    if not callback.from_user:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    offer_id = data.get("offer_id")

    await state.set_state(OrderDelivery.quantity)

    text = build_delivery_card_text(
        lang,
        data.get("title", ""),
        data.get("price", 0),
        data.get("quantity", 1),
        data.get("max_qty", 1),
        data.get("store_name", ""),
        data.get("delivery_price", 0),
        None,
        "qty",
    )
    kb = build_delivery_qty_keyboard(
        lang, offer_id, data.get("quantity", 1), data.get("max_qty", 1)
    )

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data.startswith("dlv_use_saved_"))
async def dlv_use_saved_address(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Use saved address and go to payment."""
    if not callback.from_user:
        await callback.answer()
        return

    data = await state.get_data()
    saved_address = data.get("saved_address")

    if not saved_address:
        await callback.answer("❌", show_alert=True)
        return

    await state.update_data(address=saved_address)

    # Go to payment
    lang = db.get_user_language(callback.from_user.id)
    offer_id = data.get("offer_id")

    await state.set_state(OrderDelivery.payment_method_select)

    text = build_delivery_card_text(
        lang,
        data.get("title", ""),
        data.get("price", 0),
        data.get("quantity", 1),
        data.get("max_qty", 1),
        data.get("store_name", ""),
        data.get("delivery_price", 0),
        saved_address,
        "payment",
    )
    kb = build_delivery_payment_keyboard(lang, offer_id)

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data.startswith("dlv_new_address_"))
async def dlv_new_address(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Request new address input."""
    if not callback.from_user:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)

    # Keep card but ask for text input
    await state.set_state(OrderDelivery.address)
    await state.update_data(awaiting_address_input=True)

    # Add hint to card
    data = await state.get_data()

    text = build_delivery_card_text(
        lang,
        data.get("title", ""),
        data.get("price", 0),
        data.get("quantity", 1),
        data.get("max_qty", 1),
        data.get("store_name", ""),
        data.get("delivery_price", 0),
        None,
        "address",
    )

    # Show input hint
    if lang == "uz":
        hint = "\n\n✏️ <b>Manzilni yozing:</b>\n<i>Misol: Chilanzar, 5-mavze, 10-uy</i>"
    else:
        hint = "\n\n✏️ <b>Введите адрес:</b>\n<i>Пример: Чиланзар, 5-массив, дом 10</i>"

    text += hint

    # Keyboard with just cancel
    kb = InlineKeyboardBuilder()
    cancel_text = "❌ Bekor" if lang == "uz" else "❌ Отмена"
    kb.button(text=cancel_text, callback_data="dlv_cancel")

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass

    await callback.answer()


@router.message(OrderDelivery.address)
async def dlv_address_input(
    message: types.Message, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Handle address text input."""
    if not message.from_user:
        return

    lang = db.get_user_language(message.from_user.id)
    text = (message.text or "").strip()

    # Check main menu
    if is_main_menu_button(text):
        await state.clear()
        return

    # Check cancel
    if any(c in text.lower() for c in ["отмена", "bekor", "❌"]) or text.startswith("/"):
        await state.clear()
        msg = "❌ Bekor qilindi" if lang == "uz" else "❌ Отменено"
        await message.answer(msg, reply_markup=main_menu_customer(lang))
        return

    # Validate address length
    if len(text) < 10:
        msg = "❌ Manzil juda qisqa" if lang == "uz" else "❌ Адрес слишком короткий"
        await message.answer(msg)
        return

    # Save address
    await state.update_data(address=text, awaiting_address_input=False)

    # Save as last address for user
    try:
        db.save_delivery_address(message.from_user.id, text)
    except Exception as e:
        logger.warning(f"Could not save address: {e}")

    data = await state.get_data()
    offer_id = data.get("offer_id")

    await state.set_state(OrderDelivery.payment_method_select)

    # Send card with payment step
    card_text = build_delivery_card_text(
        lang,
        data.get("title", ""),
        data.get("price", 0),
        data.get("quantity", 1),
        data.get("max_qty", 1),
        data.get("store_name", ""),
        data.get("delivery_price", 0),
        text,
        "payment",
    )
    kb = build_delivery_payment_keyboard(lang, offer_id)

    await message.answer(card_text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("dlv_back_address_"))
async def dlv_back_to_address(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Go back to address selection."""
    if not callback.from_user:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    offer_id = data.get("offer_id")

    await state.set_state(OrderDelivery.address)

    text = build_delivery_card_text(
        lang,
        data.get("title", ""),
        data.get("price", 0),
        data.get("quantity", 1),
        data.get("max_qty", 1),
        data.get("store_name", ""),
        data.get("delivery_price", 0),
        None,
        "address",
    )
    kb = build_delivery_address_keyboard(lang, offer_id, data.get("saved_address"))

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data.startswith("dlv_pay_click_"))
async def dlv_pay_click(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Process Click payment."""
    if not callback.from_user:
        await callback.answer()
        return

    data = await state.get_data()
    lang = db.get_user_language(callback.from_user.id)

    offer_id = data.get("offer_id")
    store_id = data.get("store_id")
    quantity = data.get("quantity", 1)
    address = data.get("address", "")
    price = data.get("price", 0)
    title = data.get("title", "")
    delivery_price = data.get("delivery_price", 0)

    # Create order
    order_id = None
    try:
        order_id = db.create_order(
            user_id=callback.from_user.id,
            store_id=store_id,
            offer_id=offer_id,
            quantity=quantity,
            order_type="delivery",
            delivery_address=address,
            delivery_price=delivery_price,
            payment_method="click",
        )
        if order_id:
            db.increment_offer_quantity_atomic(offer_id, -int(quantity))
            logger.info(f"✅ Created delivery order {order_id} for Click")
    except Exception as e:
        logger.error(f"Failed to create order: {e}")

    if not order_id:
        msg = "❌ Xatolik" if lang == "uz" else "❌ Ошибка"
        await callback.answer(msg, show_alert=True)
        await state.clear()
        return

    # Send Click invoice
    from handlers.customer.payments import send_payment_invoice_for_booking

    try:
        await callback.message.delete()

        invoice_msg = await send_payment_invoice_for_booking(
            user_id=callback.from_user.id,
            booking_id=order_id,
            offer_title=title,
            quantity=quantity,
            unit_price=price,
            delivery_cost=delivery_price,
        )

        if invoice_msg:
            logger.info(f"✅ Click invoice sent for order {order_id}")
            await state.clear()
        else:
            # Fallback to card
            await _switch_to_card_payment(callback.message, state, data, order_id, lang, db)
    except Exception as e:
        logger.error(f"Click invoice error: {e}")
        await _switch_to_card_payment(callback.message, state, data, order_id, lang, db)

    await callback.answer()


async def _switch_to_card_payment(message, state, data, order_id, lang, db):
    """Switch to card payment when Click fails."""
    msg = (
        "⚠️ Click ishlamayapti. Karta orqali to'lang."
        if lang == "uz"
        else "⚠️ Click недоступен. Оплатите картой."
    )
    await message.answer(msg)

    await state.update_data(order_id=order_id, payment_method="card")
    await state.set_state(OrderDelivery.payment_proof)
    await _show_card_payment_details(message, state, lang, db)


@router.callback_query(F.data.startswith("dlv_pay_card_"))
async def dlv_pay_card(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Process card payment - show card details."""
    if not callback.from_user:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    await state.update_data(payment_method="card")
    await state.set_state(OrderDelivery.payment_proof)

    await callback.message.delete()
    await _show_card_payment_details(callback.message, state, lang, db)
    await callback.answer()


async def _show_card_payment_details(
    message: types.Message, state: FSMContext, lang: str, db: DatabaseProtocol
) -> None:
    """Show card payment details - compact version."""
    data = await state.get_data()
    store_id = data.get("store_id")

    # Get payment card
    payment_card = None
    try:
        payment_card = db.get_payment_card(store_id)
    except Exception:
        pass

    if not payment_card:
        try:
            payment_card = db.get_platform_payment_card()
        except Exception:
            pass

    if not payment_card:
        payment_card = {
            "card_number": "8600 1234 5678 9012",
            "card_holder": "FUDLY",
        }

    # Extract card details
    if isinstance(payment_card, dict):
        card_number = payment_card.get("card_number", "")
        card_holder = payment_card.get("card_holder", "—")
    elif isinstance(payment_card, (tuple, list)) and len(payment_card) > 1:
        card_number = payment_card[1]
        card_holder = payment_card[2] if len(payment_card) > 2 else "—"
    else:
        card_number = str(payment_card)
        card_holder = "—"

    # Calculate total
    price = data.get("price", 0)
    quantity = data.get("quantity", 1)
    delivery_price = data.get("delivery_price", 0)
    total = (price * quantity) + delivery_price

    currency = "so'm" if lang == "uz" else "сум"

    # Compact payment message
    if lang == "uz":
        text = (
            f"💳 <b>Kartaga o'tkazing:</b>\n\n"
            f"💰 Summa: <b>{total:,} {currency}</b>\n"
            f"💳 Karta: <code>{card_number}</code>\n"
            f"👤 {card_holder}\n\n"
            f"📸 <i>Chek skrinshotini yuboring</i>"
        )
    else:
        text = (
            f"💳 <b>Переведите на карту:</b>\n\n"
            f"💰 Сумма: <b>{total:,} {currency}</b>\n"
            f"💳 Карта: <code>{card_number}</code>\n"
            f"👤 {card_holder}\n\n"
            f"📸 <i>Отправьте скриншот чека</i>"
        )

    # Cancel button
    kb = InlineKeyboardBuilder()
    cancel_text = "❌ Bekor" if lang == "uz" else "❌ Отмена"
    kb.button(text=cancel_text, callback_data="dlv_cancel")

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.message(OrderDelivery.payment_proof, F.photo)
async def dlv_payment_proof(
    message: types.Message, state: FSMContext, db: DatabaseProtocol, bot: Any
) -> None:
    """Process payment screenshot."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    data = await state.get_data()

    # Check required data
    required = ["offer_id", "store_id", "quantity", "address"]
    if not all(k in data for k in required):
        msg = "❌ Ma'lumotlar yo'qoldi" if lang == "uz" else "❌ Данные потеряны"
        await message.answer(msg, reply_markup=get_appropriate_menu(user_id, lang))
        await state.clear()
        return

    offer_id = data["offer_id"]
    store_id = data["store_id"]
    quantity = data["quantity"]
    address = data["address"]
    price = data.get("price", 0)
    title = data.get("title", "")
    delivery_price = data.get("delivery_price", 0)

    photo_id = message.photo[-1].file_id

    # Create order
    order_id = db.create_order(
        user_id=user_id,
        store_id=store_id,
        offer_id=offer_id,
        quantity=quantity,
        order_type="delivery",
        delivery_address=address,
        delivery_price=delivery_price,
        payment_method="card",
    )

    if not order_id:
        msg = "❌ Xatolik" if lang == "uz" else "❌ Ошибка"
        await message.answer(msg)
        await state.clear()
        return

    db.update_payment_status(order_id, "pending", photo_id)

    # Decrement quantity
    try:
        db.increment_offer_quantity_atomic(offer_id, -int(quantity))
    except Exception as e:
        logger.error(f"Failed to decrement offer: {e}")

    await state.clear()

    # Get store info
    store = db.get_store(store_id)
    store_name = get_store_field(store, "name", "Магазин")
    owner_id = get_store_field(store, "owner_id")

    customer = db.get_user_model(user_id)
    customer_phone = customer.phone if customer else "—"

    total = (price * quantity) + delivery_price
    currency = "so'm" if lang == "uz" else "сум"

    # Notify ADMIN
    if ADMIN_ID > 0:
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Tasdiqlash", callback_data=f"admin_confirm_payment_{order_id}")
        kb.button(text="❌ Rad etish", callback_data=f"admin_reject_payment_{order_id}")
        kb.adjust(2)

        try:
            await bot.send_photo(
                chat_id=ADMIN_ID,
                photo=photo_id,
                caption=(
                    f"💳 <b>Yangi chek!</b>\n\n"
                    f"📦 #{order_id} | {store_name}\n"
                    f"🛒 {title} × {quantity}\n"
                    f"💵 {total:,} {currency}\n"
                    f"📍 {address}\n"
                    f"👤 {message.from_user.first_name}\n"
                    f"📱 <code>{customer_phone}</code>"
                ),
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

    # Confirm to customer - single message
    if lang == "uz":
        confirm_text = (
            f"✅ <b>Buyurtma qabul qilindi!</b>\n\n"
            f"📦 #{order_id}\n"
            f"🛒 {title} × {quantity}\n"
            f"💵 {total:,} {currency}\n"
            f"📍 {address}\n\n"
            f"⏳ To'lov tasdiqlanishi kutilmoqda..."
        )
    else:
        confirm_text = (
            f"✅ <b>Заказ принят!</b>\n\n"
            f"📦 #{order_id}\n"
            f"🛒 {title} × {quantity}\n"
            f"💵 {total:,} {currency}\n"
            f"📍 {address}\n\n"
            f"⏳ Ожидаем подтверждения оплаты..."
        )

    await message.answer(
        confirm_text, parse_mode="HTML", reply_markup=get_appropriate_menu(user_id, lang)
    )


@router.message(OrderDelivery.payment_proof)
async def dlv_payment_proof_invalid(
    message: types.Message, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Handle non-photo in payment proof state."""
    if not message.from_user:
        return

    lang = db.get_user_language(message.from_user.id)
    text = (message.text or "").strip()

    if is_main_menu_button(text):
        await state.clear()
        return

    if any(c in text.lower() for c in ["отмена", "bekor", "❌"]) or text.startswith("/"):
        await state.clear()
        msg = "❌ Bekor qilindi" if lang == "uz" else "❌ Отменено"
        await message.answer(msg, reply_markup=main_menu_customer(lang))
        return

    msg = "📸 Chek rasmini yuboring" if lang == "uz" else "📸 Отправьте фото чека"
    await message.answer(f"❌ {msg}")


# Legacy quantity handler for manual input
@router.message(OrderDelivery.quantity)
async def dlv_quantity_text(
    message: types.Message, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Handle text quantity input (fallback)."""
    if not message.from_user:
        return

    lang = db.get_user_language(message.from_user.id)
    text = (message.text or "").strip()

    if is_main_menu_button(text):
        await state.clear()
        return

    if any(c in text.lower() for c in ["отмена", "bekor", "❌"]) or text.startswith("/"):
        await state.clear()
        msg = "❌ Bekor qilindi" if lang == "uz" else "❌ Отменено"
        await message.answer(msg, reply_markup=main_menu_customer(lang))
        return

    # Try to parse quantity
    try:
        qty = int(text)
        data = await state.get_data()
        max_qty = data.get("max_qty", 1)

        if qty < 1 or qty > max_qty:
            raise ValueError()

        await state.update_data(quantity=qty)

        # Move to address step
        offer_id = data.get("offer_id")

        await state.set_state(OrderDelivery.address)

        card_text = build_delivery_card_text(
            lang,
            data.get("title", ""),
            data.get("price", 0),
            qty,
            max_qty,
            data.get("store_name", ""),
            data.get("delivery_price", 0),
            None,
            "address",
        )
        kb = build_delivery_address_keyboard(lang, offer_id, data.get("saved_address"))

        await message.answer(card_text, parse_mode="HTML", reply_markup=kb.as_markup())

    except ValueError:
        msg = "❌ Raqam kiriting" if lang == "uz" else "❌ Введите число"
        await message.answer(msg)


# =============================================================================
# ADMIN HANDLERS (kept from original)
# =============================================================================


def _get_order_field(order: Any, field: str, index: int = 0) -> Any:
    """Helper to get field from order dict or tuple."""
    if isinstance(order, dict):
        return order.get(field)
    return order[index] if len(order) > index else None


@router.callback_query(F.data.startswith("admin_confirm_payment_"))
async def admin_confirm_payment(
    callback: types.CallbackQuery, db: DatabaseProtocol, bot: Any
) -> None:
    """Admin confirms payment."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌", show_alert=True)
        return

    try:
        order_id = int(callback.data.split("_")[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ Buyurtma topilmadi", show_alert=True)
        return

    db.update_payment_status(order_id, "confirmed")
    db.update_order_status(order_id, "confirmed")

    # Get details
    store_id = _get_order_field(order, "store_id", 2)
    offer_id = _get_order_field(order, "offer_id", 3)
    quantity = _get_order_field(order, "quantity", 4)
    address = _get_order_field(order, "delivery_address", 7)
    customer_id = _get_order_field(order, "user_id", 1)
    payment_photo = _get_order_field(order, "payment_proof_photo_id", 10)

    store = db.get_store(store_id)
    offer = db.get_offer(offer_id)
    customer = db.get_user_model(customer_id)

    owner_id = get_store_field(store, "owner_id") if store else None
    delivery_price = get_store_field(store, "delivery_price", 0) if store else 0

    offer_title = get_offer_field(offer, "title", "Товар") if offer else "Товар"
    offer_price = get_offer_field(offer, "discount_price", 0) if offer else 0

    customer_name = customer.first_name if customer else "—"
    customer_phone = customer.phone if customer else "—"

    total = (offer_price * quantity) + delivery_price

    # Update admin message
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ <b>TASDIQLANDI</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Notify seller
    if owner_id:
        seller_lang = db.get_user_language(owner_id)

        if seller_lang == "uz":
            caption = (
                f"🔔 <b>Yangi buyurtma!</b>\n\n"
                f"📦 #{order_id} | ✅ To'langan\n"
                f"🛒 {offer_title} × {quantity}\n"
                f"💵 {total:,} so'm\n"
                f"📍 {address}\n"
                f"👤 {customer_name}\n"
                f"📱 <code>{customer_phone}</code>\n\n"
                f"🚚 Yetkazib berishni tashkil qiling!"
            )
        else:
            caption = (
                f"🔔 <b>Новый заказ!</b>\n\n"
                f"📦 #{order_id} | ✅ Оплачено\n"
                f"🛒 {offer_title} × {quantity}\n"
                f"💵 {total:,} сум\n"
                f"📍 {address}\n"
                f"👤 {customer_name}\n"
                f"📱 <code>{customer_phone}</code>\n\n"
                f"🚚 Организуйте доставку!"
            )

        try:
            if payment_photo:
                await bot.send_photo(
                    owner_id, photo=payment_photo, caption=caption, parse_mode="HTML"
                )
            else:
                await bot.send_message(owner_id, caption, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify seller: {e}")

    # Notify customer
    if customer_id:
        cust_lang = db.get_user_language(customer_id)
        if cust_lang == "uz":
            text = f"✅ <b>To'lov tasdiqlandi!</b>\n\n📦 #{order_id}\n🚚 Yetkazib berish tashkil qilinmoqda..."
        else:
            text = f"✅ <b>Оплата подтверждена!</b>\n\n📦 #{order_id}\n🚚 Доставка организуется..."

        try:
            await bot.send_message(customer_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify customer: {e}")

    await callback.answer("✅ Tasdiqlandi!", show_alert=True)


@router.callback_query(F.data.startswith("admin_reject_payment_"))
async def admin_reject_payment(
    callback: types.CallbackQuery, db: DatabaseProtocol, bot: Any
) -> None:
    """Admin rejects payment."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌", show_alert=True)
        return

    try:
        order_id = int(callback.data.split("_")[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌", show_alert=True)
        return

    db.update_payment_status(order_id, "rejected")
    db.update_order_status(order_id, "cancelled")

    # Restore quantity
    offer_id = _get_order_field(order, "offer_id", 3)
    quantity = _get_order_field(order, "quantity", 4)
    customer_id = _get_order_field(order, "user_id", 1)

    if offer_id:
        try:
            db.increment_offer_quantity_atomic(offer_id, int(quantity))
        except Exception:
            pass

    # Update admin message
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ <b>RAD ETILDI</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Notify customer
    if customer_id:
        cust_lang = db.get_user_language(customer_id)
        if cust_lang == "uz":
            text = (
                f"❌ <b>To'lov tasdiqlanmadi</b>\n\n📦 #{order_id}\nIltimos, qayta urinib ko'ring."
            )
        else:
            text = (
                f"❌ <b>Оплата не подтверждена</b>\n\n📦 #{order_id}\nПожалуйста, попробуйте снова."
            )

        try:
            await bot.send_message(customer_id, text, parse_mode="HTML")
        except Exception:
            pass

    await callback.answer("❌ Rad etildi", show_alert=True)


@router.callback_query(F.data.startswith("cancel_order_customer_"))
async def cancel_order_customer(
    callback: types.CallbackQuery, db: DatabaseProtocol, bot: Any
) -> None:
    """Customer cancels order."""
    if not callback.from_user:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.split("_")[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌", show_alert=True)
        return

    if _get_order_field(order, "user_id", 1) != callback.from_user.id:
        await callback.answer("❌", show_alert=True)
        return

    status = _get_order_field(order, "status", 3)
    if status not in ["pending", "confirmed"]:
        msg = "Buyurtma allaqachon qayta ishlangan" if lang == "uz" else "Заказ уже обработан"
        await callback.answer(f"❌ {msg}", show_alert=True)
        return

    db.update_order_status(order_id, "cancelled")

    # Restore quantity
    offer_id = _get_order_field(order, "offer_id", 2)
    quantity = _get_order_field(order, "quantity", 4)
    if offer_id:
        try:
            db.increment_offer_quantity_atomic(offer_id, int(quantity))
        except Exception:
            pass

    msg = "Bekor qilindi" if lang == "uz" else "Отменено"
    try:
        await callback.message.edit_text(callback.message.text + f"\n\n❌ {msg}", parse_mode="HTML")
    except Exception:
        pass

    # Notify seller
    store = db.get_store(_get_order_field(order, "store_id", 2))
    if store:
        owner_id = get_store_field(store, "owner_id")
        try:
            await bot.send_message(
                owner_id,
                f"ℹ️ Buyurtma #{order_id} bekor qilindi\n👤 {callback.from_user.first_name}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await callback.answer()


# Backward compatibility
def setup_dependencies(database, bot_instance, view_mode_dict) -> None:
    """Kept for backward compatibility."""
    pass


def can_proceed(user_id: int, action: str) -> bool:
    """Rate limiting - handled by middleware."""
    return True
