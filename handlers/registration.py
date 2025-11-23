"""
User registration handlers (phone and city collection)
"""
from aiogram import Router, types, F
from aiogram import types as _ai_types


async def _safe_edit_reply_markup(msg_like, **kwargs) -> None:
    """Edit reply markup if message is accessible (Message), otherwise ignore."""
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
    # If message is not accessible, caller should handle fallback (e.g., callback.answer)
    return
from aiogram.fsm.context import FSMContext

from handlers.common import Registration
from database_protocol import DatabaseProtocol
from localization import get_text, get_cities
from app.keyboards import city_keyboard, city_inline_keyboard, phone_request_keyboard, main_menu_customer
from app.core.security import validator, rate_limiter, secure_user_input, logger

router = Router()


def setup(dp_or_router, db, get_text, get_cities, city_keyboard, phone_request_keyboard, main_menu_customer, 
          validator, rate_limiter, logger, secure_user_input):
    """Setup registration handlers with dependencies"""
    # Kept for backward compatibility
    pass
    
@router.message(Registration.phone, F.contact)
async def process_phone(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    """Process phone number with improved messaging."""
    if not db:
        await message.answer("System error")
        return
    assert db is not None
    assert message.from_user is not None
    assert message.contact is not None
    lang = db.get_user_language(message.from_user.id)
    phone = message.contact.phone_number
    
    # Validate phone format
    if not validator.validate_phone(phone):
        await message.answer(
            "❌ Неверный формат номера. Используйте кнопку ниже." if lang == 'ru' else "❌ Telefon raqami noto'g'ri. Quyidagi tugmadan foydalaning.",
            reply_markup=phone_request_keyboard(lang)
        )
        return
    
    # Save phone
    db.update_user_phone(message.from_user.id, phone)
    
    # Ask for city with improved text
    # Prefer inline city selection to avoid free-text ambiguity; keep text fallback handler
    await state.set_state(Registration.city)
    try:
        await message.answer(
            get_text(lang, "welcome_city_step"),
            parse_mode="HTML",
            reply_markup=city_inline_keyboard(lang)
        )
    except Exception:
        # Fallback to reply keyboard if inline fails for some clients
        await message.answer(
            get_text(lang, "welcome_city_step"),
            parse_mode="HTML",
            reply_markup=city_keyboard(lang)
        )


@router.callback_query(F.data.startswith("reg_city_"))
async def registration_city_callback(callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol):
    """Handle city selection from inline keyboard during registration."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return
    assert db is not None
    assert callback.from_user is not None

    # Ensure user is in the registration city state to avoid cross-handling
    current_state = await state.get_state()
    if current_state != Registration.city:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    try:
        raw = callback.data or ""
        parts = raw.split("_", 2)
        city = parts[2] if len(parts) > 2 else ""
        if not city:
            raise ValueError("empty city")
    except Exception:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Accept selection and save to user profile
    try:
        db.update_user_city(callback.from_user.id, city)
    except Exception:
        # Non-fatal: still clear state and continue
        pass

    await state.clear()
    try:
        await _safe_answer_or_send(callback.message, callback.from_user.id, get_text(lang, "registration_complete"), parse_mode="HTML", reply_markup=main_menu_customer(lang))
    except Exception:
        try:
            await callback.answer(get_text(lang, "registration_complete"), show_alert=True)
        except Exception:
            pass
    await callback.answer()

@router.message(Registration.city)
@secure_user_input
async def process_city(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    """Handle city selection (now used only when changing city from profile)"""
    if not db:
        await message.answer("System error")
        return
    assert db is not None
    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    
    # Rate limiting check
    try:
        if not rate_limiter.is_allowed(message.from_user.id, 'city_selection', max_requests=5, window_seconds=60):
            await message.answer(get_text(lang, 'rate_limit_exceeded'))
            return
    except Exception as e:
        logger.warning(f"Rate limiter error: {e}")
    
    cities = get_cities(lang)
    raw_text = message.text or ""
    city_text = validator.sanitize_text(raw_text.replace("📍 ", "").strip())
    
    # Validate city input
    if not validator.validate_city(city_text):
        await message.answer(get_text(lang, 'invalid_city'))
        return
    
    if city_text in cities:
        if db:
            db.update_user_city(message.from_user.id, city_text)
        await state.clear()
        
        # Compact confirmation
        await message.answer(
            get_text(lang, "registration_complete"),
            parse_mode="HTML",
            reply_markup=main_menu_customer(lang)
        )
