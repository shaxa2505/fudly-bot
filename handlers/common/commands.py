"""
User command handlers (start, language selection, city selection, cancel actions).
Optimized registration flow - minimal messages, all in one card.
"""
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import (
    city_inline_keyboard,
    language_keyboard,
    main_menu_customer,
    main_menu_seller,
    phone_request_keyboard,
)
from database_protocol import DatabaseProtocol
from handlers.common.states import ConfirmOrder, Registration
from handlers.common.utils import (
    get_user_view_mode,
    has_approved_store,
    set_user_view_mode,
    user_view_mode,
)
from localization import get_cities, get_text

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# Type alias for booking/offer dict
RowDict = dict[str, Any]

router = Router(name="commands")


async def handle_qr_pickup(message: types.Message, db: DatabaseProtocol, booking_code: str):
    """Handle QR code scan for pickup confirmation."""
    logger.info(f"🔗 handle_qr_pickup called: booking_code='{booking_code}'")
    if not message.from_user:
        return
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    logger.info(f"🔗 handle_qr_pickup: user={user_id}, lang={lang}")

    # Find booking by code
    booking = db.get_booking_by_code(booking_code)
    logger.info(f"🔗 handle_qr_pickup: get_booking_by_code result: {booking}")

    if not booking:
        # Try numeric ID
        try:
            booking_id = int(booking_code)
            booking = db.get_booking(booking_id)
        except ValueError:
            pass

    if not booking:
        await message.answer("❌ Бронирование не найдено" if lang == "ru" else "❌ Bron topilmadi")
        return

    # Get booking details
    if isinstance(booking, dict):
        booking_id = booking.get("booking_id")
        status = booking.get("status")
        offer_id = booking.get("offer_id")
        customer_id = booking.get("user_id")
        quantity = booking.get("quantity", 1)
        code = booking.get("code", "")
    else:
        booking_id = booking[0] if len(booking) > 0 else None
        status = booking[3] if len(booking) > 3 else None
        offer_id = booking[1] if len(booking) > 1 else None
        customer_id = booking[2] if len(booking) > 2 else None
        quantity = booking[4] if len(booking) > 4 else 1
        code = booking[9] if len(booking) > 9 else ""

    # Check if user is the store owner
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = None
    offer_title = "Товар"
    if isinstance(offer, dict):
        store_id = offer.get("store_id")
        offer_title = offer.get("title", "Товар")
    elif offer and len(offer) > 1:
        store_id = offer[1]
        offer_title = offer[2] if len(offer) > 2 else "Товар"

    store = db.get_store(store_id) if store_id else None
    owner_id = None
    store_name = "Магазин"
    if isinstance(store, dict):
        owner_id = store.get("owner_id")
        store_name = store.get("name", "Магазин")
    elif store and len(store) > 1:
        owner_id = store[1]
        store_name = store[2] if len(store) > 2 else "Магазин"

    # Get customer info
    customer = db.get_user_model(customer_id) if customer_id else None
    customer_name = "Клиент"
    customer_phone = ""
    if customer:
        customer_name = customer.name or "Клиент"
        customer_phone = customer.phone or ""

    # Check permissions
    is_owner = user_id == owner_id
    is_customer = user_id == customer_id

    # Status emoji and text
    status_info = {
        "pending": ("⏳", "Ожидает подтверждения" if lang == "ru" else "Tasdiqlash kutilmoqda"),
        "confirmed": ("✅", "Подтверждён" if lang == "ru" else "Tasdiqlangan"),
        "completed": ("🎉", "Выдан" if lang == "ru" else "Berilgan"),
        "cancelled": ("❌", "Отменён" if lang == "ru" else "Bekor qilingan"),
    }
    status_emoji, status_text = status_info.get(status, ("📦", status))

    if status == "completed":
        await message.answer(
            f"✅ {'Этот заказ уже выдан' if lang == 'ru' else 'Bu buyurtma allaqachon berilgan'}"
        )
        return

    if status == "cancelled":
        await message.answer(
            f"❌ {'Этот заказ отменён' if lang == 'ru' else 'Bu buyurtma bekor qilingan'}"
        )
        return

    if is_owner:
        # Owner scanned - show order details and complete button
        kb = InlineKeyboardBuilder()
        kb.button(
            text="✅ Выдать заказ" if lang == "ru" else "✅ Buyurtmani berish",
            callback_data=f"complete_booking_{booking_id}",
        )
        kb.adjust(1)

        if lang == "ru":
            text = (
                f"📦 <b>СКАНИРОВАНИЕ QR-КОДА</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"🎫 Бронь: <b>#{booking_id}</b>\n"
                f"📝 Код: <code>{code or booking_code}</code>\n"
                f"{status_emoji} Статус: <b>{status_text}</b>\n\n"
                f"📦 Товар: <b>{offer_title}</b>\n"
                f"🔢 Количество: <b>{quantity} шт.</b>\n\n"
                f"👤 Клиент: {customer_name}\n"
            )
            if customer_phone:
                text += f"📱 Телефон: <code>{customer_phone}</code>\n"
            text += "\n━━━━━━━━━━━━━━━━━━\n"
            text += "👆 Нажмите кнопку для подтверждения выдачи"
        else:
            text = (
                f"📦 <b>QR-KOD SKANERLASH</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"🎫 Bron: <b>#{booking_id}</b>\n"
                f"📝 Kod: <code>{code or booking_code}</code>\n"
                f"{status_emoji} Holat: <b>{status_text}</b>\n\n"
                f"📦 Mahsulot: <b>{offer_title}</b>\n"
                f"🔢 Miqdor: <b>{quantity} dona</b>\n\n"
                f"👤 Mijoz: {customer_name}\n"
            )
            if customer_phone:
                text += f"📱 Telefon: <code>{customer_phone}</code>\n"
            text += "\n━━━━━━━━━━━━━━━━━━\n"
            text += "👆 Berilganini tasdiqlash uchun tugmani bosing"

        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    elif is_customer:
        # Customer scanned their own QR - just show status
        if lang == "ru":
            text = (
                f"📦 <b>Ваша бронь #{booking_id}</b>\n\n"
                f"{status_emoji} Статус: <b>{status_text}</b>\n"
                f"📦 Товар: {offer_title}\n"
                f"🏪 Магазин: {store_name}\n\n"
                f"💡 Покажите этот QR-код продавцу для получения заказа."
            )
        else:
            text = (
                f"📦 <b>Sizning broningiz #{booking_id}</b>\n\n"
                f"{status_emoji} Holat: <b>{status_text}</b>\n"
                f"📦 Mahsulot: {offer_title}\n"
                f"🏪 Do'kon: {store_name}\n\n"
                f"💡 Buyurtmani olish uchun bu QR kodni sotuvchiga ko'rsating."
            )
        await message.answer(text, parse_mode="HTML")
    else:
        # Someone else scanned
        await message.answer(
            "⚠️ Вы не являетесь владельцем этого заказа или магазина"
            if lang == "ru"
            else "⚠️ Siz bu buyurtma yoki do'kon egasi emassiz"
        )


@router.message(F.text.in_([get_text("ru", "my_city"), get_text("uz", "my_city")]))
async def change_city(
    message: types.Message, state: FSMContext | None = None, db: DatabaseProtocol | None = None
):
    if not db or not message.from_user:
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    user = db.get_user_model(user_id)
    current_city = user.city if user else get_cities(lang)[0]
    if not current_city:
        current_city = get_cities(lang)[0]

    stats_text = ""
    try:
        stores_count = len(db.get_stores_by_city(current_city))
        offers_count = len(db.get_active_offers(city=current_city))
        stats_text = (
            f"\n\n📊 В вашем городе:\n🏪 Магазинов: {stores_count}\n🍽 Предложений: {offers_count}"
        )
    except Exception:
        pass

    builder = InlineKeyboardBuilder()
    builder.button(
        text="✏️ Изменить город" if lang == "ru" else "✏️ Shaharni o'zgartirish",
        callback_data="change_city",
    )
    builder.button(text="◀️ Назад" if lang == "ru" else "◀️ Orqaga", callback_data="back_to_menu")
    builder.adjust(1)

    await message.answer(
        f"{get_text(lang, 'your_city')}: {current_city}{stats_text}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "change_city")
async def show_city_selection(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
):
    """Show list of cities for selection."""
    lang = db.get_user_language(callback.from_user.id)
    if callback.message and hasattr(callback.message, "edit_text"):
        # For inline keyboard, send new message instead of editing with reply keyboard
        cities = get_cities(lang)
        builder = InlineKeyboardBuilder()
        for city in cities:
            builder.button(text=city, callback_data=f"select_city:{city}")
        builder.adjust(2)
        await callback.message.edit_text(
            get_text(lang, "choose_city"), reply_markup=builder.as_markup()
        )


@router.message(Command("code"))
async def cmd_code(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    """Handle /code command for manual booking code entry by partner."""
    if not message.from_user:
        return

    lang = db.get_user_language(message.from_user.id)

    # Check if code is provided with command (e.g., /code ABC123)
    if message.text:
        args = message.text.split(maxsplit=1)
        if len(args) > 1:
            booking_code = args[1].strip().upper()
            logger.info(f"📝 Partner {message.from_user.id} entered code manually: {booking_code}")
            await handle_qr_pickup(message, db, booking_code)
            return

    # No code provided - ask for it
    await state.set_state(ConfirmOrder.booking_code)

    prompt_ru = "📝 Введите код бронирования клиента:"
    prompt_uz = "📝 Mijozning bron kodini kiriting:"

    await message.answer(prompt_ru if lang == "ru" else prompt_uz)


@router.message(ConfirmOrder.booking_code)
async def process_booking_code_input(
    message: types.Message, state: FSMContext, db: DatabaseProtocol
):
    """Process manually entered booking code."""
    if not message.from_user or not message.text:
        return

    await state.clear()

    booking_code = message.text.strip().upper()

    # Remove common prefixes if present
    if booking_code.startswith("FUDLY-"):
        booking_code = booking_code.replace("FUDLY-", "")

    logger.info(f"📝 Processing booking code from user {message.from_user.id}: {booking_code}")
    await handle_qr_pickup(message, db, booking_code)


@router.callback_query(F.data == "back_to_menu")
async def back_to_main_menu(callback: types.CallbackQuery, db: DatabaseProtocol):
    """Return to main menu."""
    lang = db.get_user_language(callback.from_user.id)
    user = db.get_user_model(callback.from_user.id)
    user_role = user.role if user else "customer"

    if user_role == "seller":
        current_mode = get_user_view_mode(callback.from_user.id, db)
        if current_mode != "seller":
            set_user_view_mode(callback.from_user.id, "seller", db)

    menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)

    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(get_text(lang, "main_menu"), reply_markup=menu)
    await callback.answer()


@router.message(F.text.in_(get_cities("ru") + get_cities("uz")))
async def change_city_text(
    message: types.Message, state: FSMContext | None = None, db: DatabaseProtocol | None = None
):
    """Quick city change handler (without FSM state)."""
    if not db or not message.from_user or not message.text:
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    user = db.get_user_model(user_id)
    new_city = message.text

    db.update_user_city(user_id, new_city)

    user_role = user.role or "customer" if user else "customer"
    menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)

    await message.answer(
        f"✅ Город изменён на <b>{new_city}</b>"
        if lang == "ru"
        else f"✅ Shahar <b>{new_city}</b>ga o'zgartirildi",
        parse_mode="HTML",
        reply_markup=menu,
    )


# ===================== OPTIMIZED REGISTRATION FLOW =====================
# Single card that transforms: Welcome+Lang → Phone → City → Done
# Minimal messages, maximum UX


def build_welcome_card(lang: str = "ru") -> str:
    """Build welcome card text with step indicator."""
    return (
        f"🎉 <b>{'Fudly ga xush kelibsiz!' if lang == 'uz' else 'Добро пожаловать в Fudly!'}</b>\n\n"
        f"💰 {'70% gacha tejang' if lang == 'uz' else 'Экономьте до 70%'}\n"
        f"🏪 {'Yaqin doʻkonlar' if lang == 'uz' else 'Магазины рядом'}\n"
        f"♻️ {'Oziq-ovqat isrofini kamaytiramiz' if lang == 'uz' else 'Сокращаем потери еды'}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🌍 <b>{'Tilni tanlang' if lang == 'uz' else 'Выберите язык'}:</b>"
    )


def build_phone_card(lang: str) -> str:
    """Build phone request card."""
    return (
        f"📱 <b>{'Telefon raqamingiz' if lang == 'uz' else 'Ваш номер телефона'}</b>\n\n"
        f"{'Kerak' if lang == 'uz' else 'Нужен для'}:\n"
        f"• {'Doʻkon siz bilan bogʻlanishi' if lang == 'uz' else 'Связи с магазином'}\n"
        f"• {'Buyurtma haqida xabar' if lang == 'uz' else 'Уведомлений о заказах'}\n\n"
        f"👇 {'Quyidagi tugmani bosing' if lang == 'uz' else 'Нажмите кнопку ниже'}"
    )


def build_city_card(lang: str) -> str:
    """Build city selection card."""
    return (
        f"📍 <b>{'Shahringiz' if lang == 'uz' else 'Ваш город'}</b>\n\n"
        f"{'Yaqin doʻkonlar va takliflarni koʻrsatamiz' if lang == 'uz' else 'Покажем магазины и предложения рядом'}\n\n"
        f"👇 {'Roʻyxatdan tanlang' if lang == 'uz' else 'Выберите из списка'}"
    )


def build_welcome_keyboard() -> types.InlineKeyboardMarkup:
    """Welcome keyboard with language buttons."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="reg_lang_ru")
    kb.button(text="🇺🇿 O'zbekcha", callback_data="reg_lang_uz")
    kb.adjust(2)
    return kb.as_markup()


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    if not message.from_user:
        return

    # Clear any active state
    await state.clear()

    # Check for deep link arguments (e.g., /start pickup_CODE)
    if message.text:
        args = message.text.split(maxsplit=1)
        logger.info(f"🔗 /start command from user {message.from_user.id}: '{message.text}'")
        if len(args) > 1:
            deep_link = args[1]
            if deep_link.startswith("pickup_"):
                booking_code = deep_link.replace("pickup_", "")
                await handle_qr_pickup(message, db, booking_code)
                return

    user = db.get_user_model(message.from_user.id)

    # NEW USER - show welcome card with language selection
    if not user:
        await message.answer(
            build_welcome_card("ru"), parse_mode="HTML", reply_markup=build_welcome_keyboard()
        )
        return

    lang = db.get_user_language(message.from_user.id)
    user_phone = user.phone
    user_city = user.city
    user_role = user.role or "customer"

    # No phone - ask for phone
    if not user_phone:
        await message.answer(
            build_phone_card(lang),
            parse_mode="HTML",
            reply_markup=phone_request_keyboard(lang),
        )
        await state.set_state(Registration.phone)
        return

    # Registered user - show menu
    current_mode = get_user_view_mode(message.from_user.id, db)
    if current_mode == "seller" and user_role == "seller":
        menu = main_menu_seller(lang)
    else:
        if current_mode != "customer":
            set_user_view_mode(message.from_user.id, "customer", db)
        menu = main_menu_customer(lang)

    await message.answer(
        get_text(
            lang, "welcome_back", name=message.from_user.first_name, city=user_city or "Ташкент"
        ),
        parse_mode="HTML",
        reply_markup=menu,
    )


@router.callback_query(F.data.startswith("reg_lang_"))
async def registration_choose_language(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
):
    """Step 1: Language selected → ask for phone (edit same message)."""
    if not callback.data or not callback.message:
        await callback.answer()
        return

    lang = callback.data.split("_")[2]  # reg_lang_ru → ru
    user = db.get_user_model(callback.from_user.id)

    # Create user if new
    if not user:
        db.add_user(
            callback.from_user.id, callback.from_user.username, callback.from_user.first_name
        )

    db.update_user_language(callback.from_user.id, lang)

    # Edit welcome message to show phone request
    try:
        await callback.message.edit_text(
            build_phone_card(lang),
            parse_mode="HTML",
            reply_markup=None,  # Remove inline keyboard
        )
    except Exception:
        pass

    # Send phone request with ReplyKeyboard
    await callback.message.answer(
        f"👇 {'Tugmani bosing' if lang == 'uz' else 'Нажмите кнопку'}",
        reply_markup=phone_request_keyboard(lang),
    )

    await state.set_state(Registration.phone)
    await callback.answer()


@router.callback_query(F.data.startswith("lang_"))
async def choose_language(callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol):
    """Legacy language handler (for settings/profile)."""
    if not callback.data or not callback.message:
        await callback.answer()
        return

    lang = callback.data.split("_")[1]
    user = db.get_user_model(callback.from_user.id)

    if not user:
        # Redirect to new registration flow
        db.add_user(
            callback.from_user.id, callback.from_user.username, callback.from_user.first_name
        )
        db.update_user_language(callback.from_user.id, lang)

        try:
            await callback.message.edit_text(
                build_phone_card(lang), parse_mode="HTML", reply_markup=None
            )
        except Exception:
            pass

        await callback.message.answer(
            f"👇 {'Tugmani bosing' if lang == 'uz' else 'Нажмите кнопку'}",
            reply_markup=phone_request_keyboard(lang),
        )
        await state.set_state(Registration.phone)
        await callback.answer()
        return

    db.update_user_language(callback.from_user.id, lang)

    try:
        lang_name = "O'zbekcha" if lang == "uz" else "Русский"
        await callback.message.edit_text(
            f"✅ {'Til oʻzgartirildi' if lang == 'uz' else 'Язык изменён'}: {lang_name}"
        )
    except Exception:
        pass

    user_phone = user.phone
    user_city = user.city

    if not user_phone:
        await callback.message.answer(
            build_phone_card(lang),
            parse_mode="HTML",
            reply_markup=phone_request_keyboard(lang),
        )
        await state.set_state(Registration.phone)
        await callback.answer()
        return

    user_role = user.role or "customer"
    menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)
    await callback.message.answer(
        get_text(
            lang, "welcome_back", name=callback.from_user.first_name, city=user_city or "Ташкент"
        ),
        parse_mode="HTML",
        reply_markup=menu,
    )
    await callback.answer()


@router.message(F.text.in_(["❌ Отмена", "❌ Bekor qilish"]))
async def cancel_action(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    if not message.from_user:
        return

    lang = db.get_user_language(message.from_user.id)
    current_state = await state.get_state()

    if current_state in ["Registration:phone", "Registration:city"]:
        user = db.get_user_model(message.from_user.id)
        user_phone = user.phone if user else None
        if not user or not user_phone:
            await message.answer(
                "❌ Регистрация обязательна для использования бота.\n\n"
                "📱 Пожалуйста, поделитесь номером телефона.",
                reply_markup=phone_request_keyboard(lang),
            )
            return

    await state.clear()

    seller_groups = {"RegisterStore", "CreateOffer", "BulkCreate", "ConfirmOrder"}
    customer_groups = {"Registration", "BookOffer", "ChangeCity"}

    preferred_menu = None
    if current_state:
        try:
            state_group = str(current_state).split(":", 1)[0]
            if state_group in seller_groups:
                preferred_menu = "seller"
            elif state_group in customer_groups:
                preferred_menu = "customer"
        except Exception:
            preferred_menu = None

    user = db.get_user_model(message.from_user.id)
    role = user.role if user else "customer"

    if current_state and str(current_state).startswith("RegisterStore"):
        await message.answer(
            get_text(lang, "operation_cancelled"), reply_markup=main_menu_customer(lang)
        )
        return

    if role == "seller":
        if not has_approved_store(message.from_user.id, db):
            role = "customer"
            preferred_menu = "customer"

    view_override = user_view_mode.get(message.from_user.id)
    target = preferred_menu or view_override or ("seller" if role == "seller" else "customer")
    menu = main_menu_seller(lang) if target == "seller" else main_menu_customer(lang)

    await message.answer(get_text(lang, "operation_cancelled"), reply_markup=menu)


@router.callback_query(F.data == "cancel_offer")
async def cancel_offer_callback(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
):
    """Handler for offer creation cancel button."""
    lang = db.get_user_language(callback.from_user.id)
    await state.clear()

    if callback.message and hasattr(callback.message, "edit_text"):
        await callback.message.edit_text(
            f"❌ {'Создание товара отменено' if lang == 'ru' else 'Mahsulot yaratish bekor qilindi'}",
            parse_mode="HTML",
        )
        await callback.message.answer(
            get_text(lang, "operation_cancelled"), reply_markup=main_menu_seller(lang)
        )

    await callback.answer()


@router.message(Command("mybookings"))
async def my_bookings_command(message: types.Message, db: DatabaseProtocol | None = None):
    """Show ALL user bookings with cancel buttons - for debugging stuck bookings."""
    if not db or not message.from_user:
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    # Get ALL bookings (not just active)
    bookings = db.get_user_bookings(user_id) or []

    if not bookings:
        await message.answer(
            "📋 У вас нет бронирований.\n\n/mybookings - проверить брони"
            if lang == "ru"
            else "📋 Sizda bronlar yo'q.\n\n/mybookings - bronlarni tekshirish"
        )
        return

    # Count by status
    status_counts = {}
    for b in bookings:
        status = b.get("status") if isinstance(b, dict) else "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    text = f"📋 <b>Все ваши бронирования ({len(bookings)})</b>\n\n"
    text += f"Статусы: {status_counts}\n\n"

    builder = InlineKeyboardBuilder()

    for b in bookings[:10]:  # Max 10
        if isinstance(b, dict):
            booking_id = b.get("booking_id")
            status = b.get("status", "unknown")
            title = b.get("title", "Товар")[:20]

            status_emoji = {
                "pending": "⏳",
                "confirmed": "✅",
                "active": "🔵",
                "completed": "✔️",
                "cancelled": "❌",
            }.get(status, "❓")

            text += f"{status_emoji} #{booking_id} | {status} | {title}\n"

            # Add cancel button for non-completed/cancelled bookings
            if status not in ["completed", "cancelled"]:
                builder.button(
                    text=f"❌ Отменить #{booking_id}", callback_data=f"force_cancel_{booking_id}"
                )

    builder.adjust(1)

    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("force_cancel_"))
async def force_cancel_booking(callback: types.CallbackQuery, db: DatabaseProtocol = None):
    """Force cancel any booking."""
    if not db:
        await callback.answer("Ошибка", show_alert=True)
        return

    user_id = callback.from_user.id
    # lang используется ниже для локализации, но сейчас хардкодим русский
    _ = db.get_user_language(user_id)  # noqa: F841

    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("Ошибка ID", show_alert=True)
        return

    # Verify ownership
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer("Бронь не найдена", show_alert=True)
        return

    booking_user_id = booking.get("user_id") if isinstance(booking, dict) else booking[2]
    if booking_user_id != user_id:
        await callback.answer("Это не ваша бронь", show_alert=True)
        return

    # Cancel booking
    try:
        db.cancel_booking(booking_id)
        await callback.answer(f"✅ Бронь #{booking_id} отменена!", show_alert=True)

        # Send new message with updated list
        if callback.message:
            try:
                await callback.message.delete()
            except Exception:
                pass

        # Get updated bookings count
        bookings = db.get_user_bookings(user_id) or []
        active = [
            b
            for b in bookings
            if isinstance(b, dict) and b.get("status") in ("pending", "confirmed", "active")
        ]
        await callback.message.answer(
            f"✅ Отменено! Активных броней: {len(active)}\n\n/mybookings - посмотреть все"
        )
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)


@router.message(Command("cancelall"))
async def cancel_all_bookings(message: types.Message, db: DatabaseProtocol = None):
    """Cancel ALL active bookings for user - with direct SQL."""
    if not db:
        return

    user_id = message.from_user.id

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # First check what's in the DB
            cursor.execute(
                "SELECT booking_id, status FROM bookings WHERE user_id = %s ORDER BY booking_id",
                (user_id,),
            )
            all_bookings = cursor.fetchall()

            text = f"📊 <b>Ваши бронирования (user_id: {user_id})</b>\n\n"

            if all_bookings:
                for b in all_bookings:
                    bid, status = b[0], b[1]
                    emoji = {
                        "pending": "⏳",
                        "confirmed": "✅",
                        "active": "🔵",
                        "completed": "✔️",
                        "cancelled": "❌",
                    }.get(status, "❓")
                    text += f"{emoji} #{bid} - <code>{status}</code>\n"
            else:
                text += "📭 Нет бронирований\n"

            # Now cancel all active ones
            cursor.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE user_id = %s AND status IN ('active', 'pending', 'confirmed') RETURNING booking_id",
                (user_id,),
            )
            cancelled = cursor.fetchall()

            text += f"\n🔧 <b>Отменено: {len(cancelled)} бронирований</b>"
            if cancelled:
                text += f"\nID: {[c[0] for c in cancelled]}"

            text += "\n\n✅ Теперь можете создавать новые брони!"

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("checkdb"))
async def check_db_command(message: types.Message, db: DatabaseProtocol = None):
    """Direct database check for debugging."""
    if not db:
        await message.answer("❌ База данных недоступна")
        return

    user_id = message.from_user.id

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Get ALL bookings for this user with raw data
            cursor.execute(
                """
                SELECT booking_id, status, offer_id, quantity, created_at
                FROM bookings
                WHERE user_id = %s
                ORDER BY booking_id DESC
            """,
                (user_id,),
            )
            all_bookings = cursor.fetchall()

            # Count active bookings
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM bookings
                WHERE user_id = %s AND status IN ('active', 'pending', 'confirmed')
            """,
                (user_id,),
            )
            active_count = cursor.fetchone()[0]

            text = "🔍 <b>Диагностика базы данных</b>\n\n"
            text += f"👤 User ID: <code>{user_id}</code>\n"
            text += f"📊 Всего бронирований: {len(all_bookings)}\n"
            text += f"⚡ Активных (pending/confirmed/active): <b>{active_count}</b>\n\n"

            if all_bookings:
                text += "<b>Все брони:</b>\n"
                for b in all_bookings[:15]:  # Max 15
                    bid, status, offer_id, qty, created = b
                    emoji = {
                        "pending": "⏳",
                        "confirmed": "✅",
                        "active": "🔵",
                        "completed": "✔️",
                        "cancelled": "❌",
                    }.get(status, "❓")
                    text += f"{emoji} #{bid} | <code>{status}</code> | offer:{offer_id}\n"
            else:
                text += "📭 Нет бронирований в базе\n"

            text += f"\n💡 Лимит: {active_count}/3"
            if active_count >= 3:
                text += " (⚠️ ДОСТИГНУТ)"

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
