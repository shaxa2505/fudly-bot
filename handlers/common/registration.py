"""
User registration handlers (phone and city collection).
"""
from aiogram import F, Router, types
from aiogram import types as _ai_types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from app.core.security import logger, rate_limiter, secure_user_input, validator
from app.keyboards import (
    city_inline_keyboard,
    city_keyboard,
    main_menu_customer,
    phone_request_keyboard,
)
from database_protocol import DatabaseProtocol
from handlers.common.states import Registration
from localization import get_cities, get_text

router = Router(name="registration")


async def _safe_edit_reply_markup(msg_like, **kwargs) -> None:
    """Edit reply markup if message is accessible, otherwise ignore."""
    if isinstance(msg_like, _ai_types.Message):
        try:
            await msg_like.edit_reply_markup(**kwargs)
        except Exception:
            pass


async def _safe_answer_or_send(msg_like, user_id: int, text: str, **kwargs) -> None:
    """Try to answer via message.answer, fallback to bot.send_message."""
    if isinstance(msg_like, _ai_types.Message):
        try:
            await msg_like.answer(text, **kwargs)
            return
        except Exception:
            pass


@router.message(Registration.phone, F.contact)
async def process_phone(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    """Process phone number - save and continue (order or city selection)."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    phone = message.contact.phone_number

    if not validator.validate_phone(phone):
        await message.answer(
            "❌ Неверный формат номера. Используйте кнопку ниже."
            if lang == "ru"
            else "❌ Telefon raqami noto'g'ri. Quyidagi tugmadan foydalaning.",
            reply_markup=phone_request_keyboard(lang),
        )
        return

    db.update_user_phone(message.from_user.id, phone)

    # Check if there was a pending order
    data = await state.get_data()
    pending_order = data.get("pending_order")
    pending_cart_checkout = data.get("pending_cart_checkout")

    from aiogram.types import ReplyKeyboardRemove

    if pending_cart_checkout:
        # Resume cart checkout flow
        await message.answer(
            "✅ Телефон сохранён! Продолжаем оформление заказа..."
            if lang == "ru"
            else "✅ Telefon saqlandi! Buyurtmani davom ettiramiz...",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.update_data(pending_cart_checkout=False)
        await state.clear()

        # Show cart checkout directly
        from handlers.customer.cart.router import cart_storage
        import html

        def _esc(val):
            if val is None:
                return ""
            return html.escape(str(val))

        items = cart_storage.get_cart(message.from_user.id)
        if items:
            # Trigger checkout flow
            from aiogram.utils.keyboard import InlineKeyboardBuilder

            total = cart_storage.get_cart_total(message.from_user.id)
            currency = "so'm" if lang == "uz" else "сум"
            delivery_enabled = items[0].delivery_enabled if items else False
            delivery_price = items[0].delivery_price if items else 0

            store_name = items[0].store_name if items else ""

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

            await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
        else:
            # Cart is empty
            from handlers.customer.cart.router import main_menu_customer
            await message.answer(
                "🛒 Корзина пуста" if lang == "ru" else "🛒 Savat bo'sh",
                reply_markup=main_menu_customer(lang),
            )
        return

    if pending_order:
        # Resume order flow - user was trying to place an order
        from aiogram.types import ReplyKeyboardRemove

        await message.answer(
            "✅ Телефон сохранён! Продолжаем оформление заказа..."
            if lang == "ru"
            else "✅ Telefon saqlandi! Buyurtmani davom ettiramiz...",
            reply_markup=ReplyKeyboardRemove(),
        )

        # Restore order state and re-trigger confirm
        from handlers.common.states import BookOffer

        await state.update_data(pending_order=False)
        await state.set_state(BookOffer.quantity)

        # Send message to user to click confirm again
        await message.answer(
            "👆 Нажмите кнопку 'Подтвердить' ещё раз"
            if lang == "ru"
            else "👆 Tasdiqlash tugmasini qayta bosing",
        )
        return

    # Check if user already has a city set - skip city selection
    user = db.get_user_model(message.from_user.id)
    if user and user.city:
        # User already has city, complete registration
        await state.clear()

        from aiogram.types import ReplyKeyboardRemove
        from app.keyboards import main_menu_customer

        await message.answer(
            "✅ Телефон сохранён!" if lang == "ru" else "✅ Telefon saqlandi!",
            reply_markup=ReplyKeyboardRemove(),
        )

        # Send main menu
        await message.answer(
            f"👇 {'Tanlang' if lang == 'uz' else 'Выберите'}:",
            reply_markup=main_menu_customer(lang),
        )
        return

    # Normal registration flow - show city selection
    city_text = (
        f"✅ {'Telefon saqlandi!' if lang == 'uz' else 'Телефон сохранён!'}\n\n"
        f"📍 <b>{'Shahringizni tanlang' if lang == 'uz' else 'Выберите ваш город'}</b>\n\n"
        f"{'Yaqin takliflarni koʻrsatamiz' if lang == 'uz' else 'Покажем предложения рядом с вами'}"
    )

    await state.set_state(Registration.city)

    # Remove reply keyboard and show inline cities
    from aiogram.types import ReplyKeyboardRemove

    await message.answer(
        city_text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        f"👇 {'Tanlang' if lang == 'uz' else 'Выберите'}:",
        reply_markup=city_inline_keyboard(lang),
    )


@router.callback_query(F.data.startswith("reg_city_"), StateFilter(Registration.city, None))
async def registration_city_callback(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
):
    """Handle city selection - complete registration."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)

    try:
        raw = callback.data or ""
        parts = raw.split("_", 2)
        city = parts[2] if len(parts) > 2 else ""
        if not city:
            raise ValueError("empty city")
    except Exception as e:
        logger.error(f"City parse error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    try:
        db.update_user_city(callback.from_user.id, city)
        logger.info(f"City updated for user {callback.from_user.id}: {city}")
    except Exception as e:
        logger.error(f"Failed to update city: {e}")

    await state.clear()

    # Edit message to show completion
    user = db.get_user_model(callback.from_user.id)
    name = user.first_name if user else callback.from_user.first_name

    complete_text = (
        f"🎉 <b>{'Tayyor!' if lang == 'uz' else 'Готово!'}</b>\n\n"
        f"👋 {'Xush kelibsiz' if lang == 'uz' else 'Добро пожаловать'}, {name}!\n"
        f"📍 {'Shahar' if lang == 'uz' else 'Город'}: {city}\n\n"
        f"{'Endi siz qila olasiz' if lang == 'uz' else 'Теперь вы можете'}:\n"
        f"🔥 <b>{'Issiq' if lang == 'uz' else 'Горячее'}</b> — {'eng yaxshi chegirmalar' if lang == 'uz' else 'лучшие скидки'}\n"
        f"🏪 <b>{'Doʻkonlar' if lang == 'uz' else 'Заведения'}</b> — {'barcha doʻkonlar' if lang == 'uz' else 'все магазины'}\n"
        f"🔍 <b>{'Qidirish' if lang == 'uz' else 'Поиск'}</b> — {'mahsulot topish' if lang == 'uz' else 'найти товар'}"
    )

    try:
        await callback.message.edit_text(complete_text, parse_mode="HTML")
    except Exception:
        pass

    # Send main menu (single message)
    await callback.message.answer(
        f"👇 {'Tanlang' if lang == 'uz' else 'Выберите'}:",
        reply_markup=main_menu_customer(lang),
    )
    await callback.answer()


# OLD TEXT-BASED CITY HANDLER REMOVED
# City is now selected ONLY via inline buttons (select_city:) in commands.py
# This prevents accidental triggering when user types numbers during registration
