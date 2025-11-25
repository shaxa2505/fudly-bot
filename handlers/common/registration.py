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
    """Process phone number with improved messaging."""
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

    await state.set_state(Registration.city)
    try:
        await message.answer(
            get_text(lang, "welcome_city_step"),
            parse_mode="HTML",
            reply_markup=city_inline_keyboard(lang),
        )
    except Exception:
        await message.answer(
            get_text(lang, "welcome_city_step"), parse_mode="HTML", reply_markup=city_keyboard(lang)
        )


@router.callback_query(F.data.startswith("reg_city_"), StateFilter(Registration.city, None))
async def registration_city_callback(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
):
    """Handle city selection from inline keyboard during registration."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    current_state = await state.get_state()
    logger.info(
        f"City callback: user={callback.from_user.id}, state={current_state}, data={callback.data}"
    )

    lang = db.get_user_language(callback.from_user.id)
    try:
        raw = callback.data or ""
        parts = raw.split("_", 2)
        city = parts[2] if len(parts) > 2 else ""
        if not city:
            raise ValueError("empty city")
        logger.info(f"Selected city: {city}")
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

    # Delete old message and send new menu
    try:
        await callback.message.delete()
    except Exception:
        pass

    try:
        await callback.message.answer(
            get_text(lang, "registration_complete"),
            parse_mode="HTML",
            reply_markup=main_menu_customer(lang),
        )
    except Exception as e:
        logger.error(f"Failed to send completion message: {e}")
        try:
            await callback.answer(get_text(lang, "registration_complete"), show_alert=True)
        except Exception:
            pass

    await callback.answer()


@router.message(Registration.city)
@secure_user_input
async def process_city(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    """Handle city selection (now used only when changing city from profile)."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)

    try:
        if not rate_limiter.is_allowed(
            message.from_user.id, "city_selection", max_requests=5, window_seconds=60
        ):
            await message.answer(get_text(lang, "rate_limit_exceeded"))
            return
    except Exception as e:
        logger.warning(f"Rate limiter error: {e}")

    cities = get_cities(lang)
    raw_text = message.text or ""
    city_text = validator.sanitize_text(raw_text.replace("📍 ", "").strip())

    if not validator.validate_city(city_text):
        await message.answer(get_text(lang, "invalid_city"))
        return

    if city_text in cities:
        db.update_user_city(message.from_user.id, city_text)
        await state.clear()

        await message.answer(
            get_text(lang, "registration_complete"),
            parse_mode="HTML",
            reply_markup=main_menu_customer(lang),
        )
