"""
Optimized delivery order flow - single card UX.

Flow: Click delivery → Single card with qty/address/payment → Confirm → Done
- Saves last delivery address
- Single message updated at each step
- Minimal notifications

This module is the main entry point. Partner handlers are in a separate module:
- delivery_partner.py - Partner order confirmation/rejection
- delivery_ui.py - UI builders (cards, keyboards)
"""
from __future__ import annotations

import os
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.constants import OFFERS_PER_PAGE
from app.core.utils import get_offer_field, get_store_field
from app.keyboards import main_menu_customer
from app.services.unified_order_service import (
    OrderItem,
    get_unified_order_service,
    init_unified_order_service,
)
from database_protocol import DatabaseProtocol
from handlers.common.states import OrderDelivery
from handlers.common.utils import (
    get_appropriate_menu as _get_appropriate_menu,
)
from handlers.common.utils import (
    is_main_menu_button,
)

# Import UI builders from separate module
from handlers.customer.orders.delivery_ui import (
    build_delivery_address_keyboard,
    build_delivery_card_text,
    build_delivery_payment_keyboard,
    build_delivery_qty_keyboard,
)
from localization import get_text
from logging_config import logger

router = Router()

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None
# Toggle Telegram Payments (Click via Telegram Bot Payments)
ENABLE_TELEGRAM_PAYMENTS = (
    os.getenv("ENABLE_TELEGRAM_PAYMENTS", "0").strip().lower() in {"1", "true", "yes"}
)


def setup_dependencies(
    database: DatabaseProtocol, bot_instance: Any, view_mode_dict: dict[int, str] | None = None
) -> None:
    """Setup module dependencies. view_mode_dict is deprecated and ignored."""
    global db, bot
    db = database
    bot = bot_instance


def get_appropriate_menu(user_id: int, lang: str) -> Any:
    """Get appropriate menu based on user view mode."""
    if not db:
        return main_menu_customer(lang)
    return _get_appropriate_menu(user_id, lang, db)


def _t(lang: str, ru: str, uz: str) -> str:
    return ru if lang == "ru" else uz


def _service_unavailable(lang: str) -> str:
    return _t(
        lang,
        "Сервис временно недоступен. Попробуйте позже.",
        "Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring.",
    )


def _lang_code(user: types.User | None) -> str:
    code = (user.language_code or "ru") if user else "ru"
    return "uz" if code.startswith("uz") else "ru"


# =============================================================================
# CUSTOMER HANDLERS
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
        await callback.answer(get_text(lang, "error"), show_alert=True)
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
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Check delivery enabled
    if not get_store_field(store, "delivery_enabled", 0):
        msg = "Yetkazib berish mavjud emas" if lang == "uz" else "Доставка недоступна"
        await callback.answer(msg, show_alert=True)
        return

    # Get details
    price = get_offer_field(offer, "discount_price", 0)
    title = get_offer_field(offer, "title", "")
    store_name = get_store_field(store, "name", "")
    delivery_price = get_store_field(store, "delivery_price", 15000)
    min_order = get_store_field(store, "min_order_amount", 0)

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


@router.callback_query(F.data.startswith("dlv_cancel_"))
async def dlv_cancel_order(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
) -> None:
    """Cancel delivery order with order_id - cancel the pending order."""
    if not callback.from_user:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Get order_id from callback
    try:
        order_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        order_id = 0

    await state.clear()

    # Cancel the order if exists
    if order_id > 0:
        try:
            order_service = get_unified_order_service()
            if not order_service:
                order_service = init_unified_order_service(db, callback.bot)
            if order_service:
                await order_service.cancel_order(order_id, "order")
            else:
                logger.warning("UnifiedOrderService unavailable for cancel_order")
            logger.info(f"User {user_id} cancelled order #{order_id}")
        except Exception as e:
            logger.error(f"Failed to cancel order #{order_id}: {e}")

    # Delete current message
    try:
        await callback.message.delete()
    except Exception:
        pass

    msg = "Bekor qilindi." if lang == "uz" else "Отменено."
    await callback.message.answer(msg, reply_markup=main_menu_customer(lang))
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
    region = getattr(user, "region", None) if user else None
    district = getattr(user, "district", None) if user else None
    latitude = getattr(user, "latitude", None) if user else None
    longitude = getattr(user, "longitude", None) if user else None
    search_city = normalize_city(city)
    search_region = normalize_city(region) if region else None
    search_district = normalize_city(district) if district else None

    offer_service = OfferService(db)
    result = offer_service.list_hot_offers(
        search_city,
        limit=OFFERS_PER_PAGE,
        offset=last_page * OFFERS_PER_PAGE,
        region=search_region,
        district=search_district,
        latitude=latitude,
        longitude=longitude,
    )

    if not result.items:
        # No offers - show main menu
        msg = "Bekor qilindi." if lang == "uz" else "Отменено."
        await callback.message.answer(msg, reply_markup=main_menu_customer(lang))
        await callback.answer()
        return

    # Build hot offers list
    from app.keyboards.offers import hot_offers_compact_keyboard
    from app.templates.offers import render_hot_offers_list

    total_pages = (result.total + OFFERS_PER_PAGE - 1) // OFFERS_PER_PAGE
    text = render_hot_offers_list(
        lang, city, result.items, result.total, "", offset=last_page * OFFERS_PER_PAGE
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
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    data = await state.get_data()
    max_qty = data.get("max_qty", 1)
    price = data.get("price", 0)

    if new_qty < 1 or new_qty > max_qty:
        await callback.answer(get_text(lang, "error"), show_alert=True)
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

    min_order = int(data.get("min_order", 0) or 0)
    price = int(data.get("price", 0) or 0)
    quantity = int(data.get("quantity", 1) or 1)

    if min_order > 0 and (price * quantity) < min_order:
        currency = "so'm" if lang == "uz" else "сум"
        msg = _t(
            lang,
            f"Минимальная сумма доставки: {min_order:,} {currency}",
            f"Minimal summa: {min_order:,} {currency}",
        )
        await callback.answer(msg, show_alert=True)
        return

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
    """Use saved address and go to payment - CREATE ORDER HERE."""
    if not callback.from_user:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    data = await state.get_data()
    saved_address = data.get("saved_address")

    if not saved_address:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await state.update_data(address=saved_address)

    # Don't create order yet - wait for payment method selection (Click)
    logger.info(f"User {user_id} selected saved address, waiting for payment selection")

    await state.set_state(OrderDelivery.payment_method_select)

    offer_id = data.get("offer_id")
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
        hint = "\n\n<b>Manzilni yozing:</b>\n<i>Misol: Chilanzar, 5-mavze, 10-uy</i>"
    else:
        hint = "\n\n<b>Введите адрес:</b>\n<i>Пример: Чиланзар, 5-массив, дом 10</i>"

    text += hint

    # Keyboard: Back to address options + full cancel
    kb = InlineKeyboardBuilder()
    try:
        offer_id = int((callback.data or "").split("_")[-1])
    except (ValueError, IndexError):
        offer_id = 0

    back_text = "Orqaga" if lang == "uz" else "Назад"
    cancel_text = "Bekor qilish" if lang == "uz" else "Отмена"
    if offer_id:
        kb.button(text=back_text, callback_data=f"dlv_back_address_{offer_id}")
    kb.button(text=cancel_text, callback_data="dlv_cancel")

    if offer_id:
        kb.adjust(1, 1)
    else:
        kb.adjust(1)

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
async def dlv_address_input(message: types.Message, state: FSMContext) -> None:
    """Handle address text input for delivery orders (Tez buyurtma, etc.)."""
    if not message.from_user:
        return

    # Use module-level db to avoid DI issues
    global db
    if not db:
        await message.answer(_service_unavailable(_lang_code(message.from_user)))
        return

    lang = db.get_user_language(message.from_user.id)
    text = (message.text or "").strip()

    # Check main menu
    if is_main_menu_button(text):
        await state.clear()
        return

    # Check cancel
    if any(c in text.lower() for c in ["отмена", "bekor"]) or text.startswith("/"):
        await state.clear()
        msg = "Bekor qilindi." if lang == "uz" else "Отменено."
        await message.answer(msg, reply_markup=main_menu_customer(lang))
        return

    # Validate address length
    if len(text) < 10:
        msg = "Manzil juda qisqa." if lang == "uz" else "Адрес слишком короткий."
        await message.answer(msg)
        return

    # Save address
    await state.update_data(address=text, awaiting_address_input=False)
    logger.info(f"User {message.from_user.id} entered delivery address: {text[:30]}...")

    # Save as last address for user
    try:
        db.save_delivery_address(message.from_user.id, text)
    except Exception as e:
        logger.warning(f"Could not save address: {e}")

    data = await state.get_data()
    offer_id = data.get("offer_id")
    store_id = data.get("store_id")
    quantity = data.get("quantity", 1)
    delivery_price = data.get("delivery_price", 0)
    user_id = message.from_user.id

    # Don't create order yet - wait for payment method selection (Click)
    logger.info(f"User {user_id} saved address, waiting for payment selection")

    await state.set_state(OrderDelivery.payment_method_select)
    logger.info(f"User {message.from_user.id} moved to payment method selection state")

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
    """Process Click payment - order already created after address input."""
    if not callback.from_user:
        await callback.answer()
        return

    # Import lazily to avoid circular imports
    from handlers.customer import payments as telegram_payments

    data = await state.get_data()
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    logger.info(f"User {user_id} selected Click payment")
    logger.info(f"FSM data: {data}")

    # Payments must be enabled and provider token configured
    if not ENABLE_TELEGRAM_PAYMENTS or not telegram_payments.PROVIDER_TOKEN:
        msg = (
            "Click временно недоступен. Попробуйте позже."
            if lang != "uz"
            else "Click vaqtincha mavjud emas. Keyinroq urinib ko'ring."
        )
        logger.warning("Telegram Payments disabled or token missing for Click")
        await callback.answer(msg, show_alert=True)
        return

    # Ensure we have address and other required data
    address = data.get("address")
    if not address:
        logger.error("? No address in state for Click payment")
        await _return_to_address_step(callback.message, state, data, lang)
        await callback.answer(get_text(lang, "cart_delivery_address_prompt"), show_alert=True)
        return

    # Create order if not created yet
    order_id = data.get("order_id")
    if not order_id:
        order_service = get_unified_order_service()
        if not order_service and bot:
            order_service = init_unified_order_service(db, bot)
        if not order_service:
            logger.warning("UnifiedOrderService unavailable for Click")
            await callback.answer(get_text(lang, "system_error"), show_alert=True)
            return

        try:
            offer_id = data.get("offer_id")
            store_id = data.get("store_id")
            quantity = int(data.get("quantity", 1))
            delivery_price = int(data.get("delivery_price", 0))

            offer = db.get_offer(offer_id)
            store = db.get_store(store_id)

            title = get_offer_field(offer, "title", "")
            price = int(get_offer_field(offer, "discount_price", 0))
            offer_photo = get_offer_field(offer, "photo") or get_offer_field(offer, "photo_id")
            store_name = get_store_field(store, "name", "")
            store_address = get_store_field(store, "address", "")

            order_item = OrderItem(
                offer_id=int(offer_id),
                store_id=int(store_id),
                title=title,
                price=price,
                original_price=price,
                quantity=quantity,
                store_name=store_name,
                store_address=store_address,
                photo=offer_photo,
                delivery_price=delivery_price,
            )

            order_type = data.get("order_type", "delivery")
            result = await order_service.create_order(
                user_id=user_id,
                items=[order_item],
                order_type=order_type,
                delivery_address=address if order_type == "delivery" else None,
                payment_method="click",
                notify_customer=False,
                notify_sellers=False,
            )

            if not (result.success and result.order_ids):
                logger.error(
                    "Failed to create order before Telegram invoice: %s", result.error_message
                )
                await callback.answer(get_text(lang, "system_error"), show_alert=True)
                return

            order_id = result.order_ids[0]
            await state.update_data(order_id=order_id, payment_method="click")
            logger.info(f"Created order #{order_id} before sending Telegram invoice")
        except Exception as e:
            logger.error(f"Error creating order before Telegram invoice: {e}", exc_info=True)
            await callback.answer(get_text(lang, "system_error"), show_alert=True)
            return

    # Send Telegram invoice
    try:
        items = [
            {
                "title": data.get("title", ""),
                "quantity": int(data.get("quantity", 1)),
                "price": int(data.get("price", 0)),
            }
        ]
        delivery_cost = int(data.get("delivery_price", 0))
        store_name = data.get("store_name", "")

        await telegram_payments.create_order_invoice(
            chat_id=user_id,
            order_id=int(order_id),
            items=items,
            delivery_cost=delivery_cost,
            store_name=store_name,
        )
        logger.info(f"Sent Telegram invoice for order #{order_id}")
    except Exception as e:
        logger.error(f"Failed to send Telegram invoice: {e}", exc_info=True)
        await callback.answer(get_text(lang, "system_error"), show_alert=True)
        return

    # Remove inline keyboard to prevent duplicate taps and clear state
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.clear()

    # Notify user to pay the invoice
    notify_text = (
        "Счёт отправлен. Нажмите «Оплатить» в сообщении выше."
        if lang != "uz"
        else "Hisob yuborildi. Yuqoridagi xabarda «To'lash» tugmasini bosing."
    )
    try:
        await callback.message.answer(notify_text)
    except Exception:
        pass

    await callback.answer()


async def _return_to_address_step(message: types.Message, state: FSMContext, data: dict, lang: str) -> None:
    offer_id = data.get("offer_id")
    if not offer_id:
        await state.clear()
        await message.answer(get_text(lang, "system_error"), reply_markup=main_menu_customer(lang))
        return

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
    kb = build_delivery_address_keyboard(lang, int(offer_id), data.get("saved_address"))

    try:
        if message.photo:
            await message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb.as_markup())
        else:
            await message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass

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

    if any(c in text.lower() for c in ["отмена", "bekor"]) or text.startswith("/"):
        await state.clear()
        msg = "Bekor qilindi." if lang == "uz" else "Отменено."
        await message.answer(msg, reply_markup=main_menu_customer(lang))
        return

    # Try to parse quantity
    try:
        qty = int(text)
        data = await state.get_data()
        max_qty = data.get("max_qty", 1)
        min_order = int(data.get("min_order", 0) or 0)
        price = int(data.get("price", 0) or 0)


        if qty < 1 or qty > max_qty:
            raise ValueError()

        if min_order > 0 and (price * qty) < min_order:
            currency = "so'm" if lang == "uz" else "сум"
            msg = _t(
                lang,
                f"Минимальная сумма доставки: {min_order:,} {currency}",
                f"Minimal summa: {min_order:,} {currency}",
            )
            await message.answer(msg)
            return

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
        msg = "Raqam kiriting." if lang == "uz" else "Введите число."
        await message.answer(msg)
