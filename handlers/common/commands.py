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
    except Exception as e:
        logger.debug("Could not load city stats: %s", e)

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


@router.callback_query(F.data.startswith("select_city:"))
async def handle_city_selection(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
):
    """Handle city selection from inline keyboard."""
    if not callback.data or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    city = callback.data.split(":", 1)[1] if ":" in callback.data else ""

    if not city:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    db.update_user_city(callback.from_user.id, city)
    await state.clear()

    user = db.get_user_model(callback.from_user.id)
    user_role = user.role if user else "customer"
    menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)

    try:
        await callback.message.edit_text(
            f"✅ {'Shahar tanlandi' if lang == 'uz' else 'Город выбран'}: {city}"
        )
    except Exception as e:
        logger.debug("Could not edit city confirmation: %s", e)

    await callback.message.answer(
        get_text(lang, "welcome_back", name=callback.from_user.first_name, city=city),
        parse_mode="HTML",
        reply_markup=menu,
    )
    await callback.answer()


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
        except Exception as e:
            logger.debug("Could not delete message in back_to_menu: %s", e)
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
    """Build welcome message for new users."""
    return (
        f"🎉 <b>{'Fudly ga xush kelibsiz!' if lang == 'uz' else 'Добро пожаловать в Fudly!'}</b>\n\n"
        f"{'Biz nima qilamiz' if lang == 'uz' else 'Что мы делаем'}:\n"
        f"💰 {'Oziq-ovqat chegirmalarini 70% gacha topish' if lang == 'uz' else 'Находим скидки на еду до 70%'}\n"
        f"🏪 {'Yaqin doʻkonlardan eng yaxshi takliflar' if lang == 'uz' else 'Лучшие предложения из магазинов рядом'}\n"
        f"♻️ {'Isrof qilinadigan oziq-ovqatni saqlaymiz' if lang == 'uz' else 'Спасаем еду от списания'}\n\n"
        f"{'Qanday ishlaydi' if lang == 'uz' else 'Как это работает'}:\n"
        f"1️⃣ {'Taklifni tanlang' if lang == 'uz' else 'Выберите товар'}\n"
        f"2️⃣ {'Savatga qoʻshing' if lang == 'uz' else 'Добавьте в корзину'}\n"
        f"3️⃣ {'Doʻkondan oling yoki yetkazib bering' if lang == 'uz' else 'Заберите или закажите доставку'}\n\n"
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

    # NEW USER - create immediately and show welcome card with language selection
    if not user:
        # Create user right away to avoid duplicate welcome on second /start
        db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
        await message.answer(
            build_welcome_card("ru"), parse_mode="HTML", reply_markup=build_welcome_keyboard()
        )
        return

    lang = db.get_user_language(message.from_user.id)
    user_city = user.city
    user_role = user.role or "customer"

    # User exists but hasn't selected city yet - show city selection
    if not user_city:
        await message.answer(
            get_text(lang, "choose_city"),
            parse_mode="HTML",
            reply_markup=city_inline_keyboard(lang),
        )
        # DON'T set state - city is selected via inline buttons only
        await state.clear()
        return

    # Phone is optional - user can browse without it
    # Phone will be requested only when placing an order

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
    """Step 1: Language selected → show city selection (skip phone, ask at checkout)."""
    if not callback.data or not callback.message:
        await callback.answer()
        return

    lang = callback.data.split("_")[2]  # reg_lang_ru → ru

    # User should already exist from /start, but create if somehow missing
    user = db.get_user_model(callback.from_user.id)
    if not user:
        db.add_user(
            callback.from_user.id, callback.from_user.username, callback.from_user.first_name
        )

    db.update_user_language(callback.from_user.id, lang)

    # Show city selection instead of phone request
    try:
        await callback.message.edit_text(
            get_text(lang, "choose_city"),
            parse_mode="HTML",
            reply_markup=city_inline_keyboard(lang),
        )
    except Exception as e:
        logger.debug("Could not edit city selection: %s", e)

    # DON'T set state - city is selected via inline buttons only
    await state.clear()
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
        # Redirect to new registration flow - show city selection
        db.add_user(
            callback.from_user.id, callback.from_user.username, callback.from_user.first_name
        )
        db.update_user_language(callback.from_user.id, lang)

        try:
            await callback.message.edit_text(
                get_text(lang, "choose_city"),
                parse_mode="HTML",
                reply_markup=city_inline_keyboard(lang),
            )
        except Exception as e:
            logger.debug("Could not edit city selection: %s", e)

        # DON'T set state - city is selected via inline buttons only
        await state.clear()
        await callback.answer()
        return

    db.update_user_language(callback.from_user.id, lang)

    try:
        lang_name = "O'zbekcha" if lang == "uz" else "Русский"
        await callback.message.edit_text(
            f"✅ {'Til oʻzgartirildi' if lang == 'uz' else 'Язык изменён'}: {lang_name}"
        )
    except Exception as e:
        logger.debug("Could not edit language confirmation: %s", e)

    user_city = user.city
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
