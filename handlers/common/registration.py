"""
User registration handlers (phone and city collection).
"""
from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from app.core.sanitize import sanitize_phone
from app.core.security import logger, rate_limiter, secure_user_input, validator
from app.keyboards import (
    city_inline_keyboard,
    city_keyboard,
    main_menu_customer,
    phone_request_keyboard,
)
from database_protocol import DatabaseProtocol
from handlers.common.states import Registration
from localization import get_text

router = Router(name="registration")


async def _after_phone_saved(
    message: types.Message, state: FSMContext, db: DatabaseProtocol, lang: str
) -> None:
    # Check if there was a pending order (Tez buyurtma) or cart checkout
    data = await state.get_data()
    pending_order = data.get("pending_order")
    pending_cart_checkout = data.get("pending_cart_checkout")

    from aiogram.types import ReplyKeyboardRemove

    # 1) Pending cart checkout: user started cart checkout without phone
    if pending_cart_checkout:
        # Confirm phone saved and hide contact keyboard
        await message.answer(
            "✅ Телефон сохранён!" if lang == "ru" else "✅ Telefon saqlandi!",
            reply_markup=ReplyKeyboardRemove(),
        )

        # Try to show cart again so user can continue checkout
        try:
            from handlers.customer.cart.router import show_cart

            await show_cart(message, state, is_callback=False)
        except Exception as e:  # pragma: no cover - defensive logging
            logger.warning(f"Failed to resume cart after phone: {e}")
            from app.keyboards import main_menu_customer

            await message.answer(
                (
                    "Теперь откройте «Сават» и нажмите «Оформить заказ» заново."
                    if lang == "ru"
                    else "Endi «Savat» ni ochib, qayta «Buyurtma berish» ni bosing."
                ),
                reply_markup=main_menu_customer(lang),
            )

        # Clear state - cart flow will set its own FSM state again
        await state.clear()
        return

    # 2) Pending single-order / Tez buyurtma flow
    if pending_order:
        await message.answer(
            "✅ Телефон сохранён!" if lang == "ru" else "✅ Telefon saqlandi!",
            reply_markup=ReplyKeyboardRemove(),
        )

        # Get order data to show confirmation button
        data = await state.get_data()
        offer_id = data.get("offer_id")
        store_id = data.get("store_id")
        delivery_method = data.get("selected_delivery")

        # Check if we have minimum required data
        if not offer_id or not store_id or not delivery_method:
            # Data incomplete - show menu
            await state.clear()
            from app.keyboards import main_menu_customer

            await message.answer(
                "Продолжите через «Акции»" if lang == "ru" else "Aksiyalar orqali davom eting",
                reply_markup=main_menu_customer(lang),
            )
            return

        # Show confirmation button to continue Tez buyurtma
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        kb = InlineKeyboardBuilder()
        kb.button(
            text="✅ Продолжить" if lang == "ru" else "✅ Davom ettirish",
            callback_data=f"pbook_confirm_{offer_id}",
        )

        await message.answer(
            "Нажмите кнопку ниже, чтобы продолжить:"
            if lang == "ru"
            else "Davom etish uchun tugmani bosing:",
            reply_markup=kb.as_markup(),
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
            f"👉 {'Tanlang' if lang == 'uz' else 'Выберите'}:",
            reply_markup=main_menu_customer(lang),
        )
        return

    # Normal registration flow - show city selection
    city_text = (
        f"✅ {'Telefon saqlandi!' if lang == 'uz' else 'Телефон сохранён!'}\n\n"
        f"🏙 <b>{'Shahringizni tanlang' if lang == 'uz' else 'Выберите ваш город'}</b>\n\n"
        f"{'Yaqin takliflarni ko‘rsatamiz' if lang == 'uz' else 'Покажем предложения рядом'}"
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
        f"👉 {'Tanlang' if lang == 'uz' else 'Выберите'}:",
        reply_markup=city_inline_keyboard(lang),
    )


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

    # Check if there was a pending order (Tez buyurtma) or cart checkout
    data = await state.get_data()
    pending_order = data.get("pending_order")
    pending_cart_checkout = data.get("pending_cart_checkout")

    from aiogram.types import ReplyKeyboardRemove

    # 1) Pending cart checkout: user started cart checkout without phone
    if pending_cart_checkout:
        # Confirm phone saved and hide contact keyboard
        await message.answer(
            "✅ Телефон сохранён!" if lang == "ru" else "✅ Telefon saqlandi!",
            reply_markup=ReplyKeyboardRemove(),
        )

        # Try to show cart again so user can continue checkout
        try:
            from handlers.customer.cart.router import show_cart

            await show_cart(message, state, is_callback=False)
        except Exception as e:  # pragma: no cover - defensive logging
            logger.warning(f"Failed to resume cart after phone: {e}")
            from app.keyboards import main_menu_customer

            await message.answer(
                (
                    "Теперь откройте 🛒 Корзина и нажмите «Оформить заказ» заново."
                    if lang == "ru"
                    else "Endi 🛒 Savat ni ochib, qayta ‘Buyurtma berish’ ni bosing."
                ),
                reply_markup=main_menu_customer(lang),
            )

        # Clear state – cart flow will set its own FSM state again
        await state.clear()
        return

    # 2) Pending single-order / Tez buyurtma flow
    if pending_order:
        await message.answer(
            "✅ Телефон сохранён!" if lang == "ru" else "✅ Telefon saqlandi!",
            reply_markup=ReplyKeyboardRemove(),
        )

        # Get order data to show confirmation button
        data = await state.get_data()
        offer_id = data.get("offer_id")
        store_id = data.get("store_id")
        delivery_method = data.get("selected_delivery")

        # Check if we have minimum required data
        if not offer_id or not store_id or not delivery_method:
            # Data incomplete - show menu
            await state.clear()
            from app.keyboards import main_menu_customer

            await message.answer(
                "⚠️ Продолжите оформление через 🔥 Акции"
                if lang == "ru"
                else "⚠️ 🔥 Aksiyalar orqali davom eting",
                reply_markup=main_menu_customer(lang),
            )
            return

        # Show confirmation button to continue Tez buyurtma
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        kb = InlineKeyboardBuilder()
        kb.button(
            text="✅ Продолжить оформление" if lang == "ru" else "✅ Davom ettirish",
            callback_data=f"pbook_confirm_{offer_id}",
        )

        await message.answer(
            "👇 Нажмите кнопку ниже для продолжения:"
            if lang == "ru"
            else "👇 Davom etish uchun tugmani bosing:",
            reply_markup=kb.as_markup(),
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
        f"🔥 <b>{'Aksiyalar' if lang == 'uz' else 'Акции'}</b> — {'70% gacha chegirmalar' if lang == 'uz' else 'скидки до 70%'}\n"
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
