"""
User command handlers (start, language selection, city selection, cancel actions).
Optimized registration flow - minimal messages, all in one card.
"""
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.location_data import (
    get_district_label,
    get_districts_for_city_index,
    get_districts_for_region,
    get_region_key_for_city_index,
)
from app.keyboards import (
    city_inline_keyboard,
    language_keyboard,
    main_menu_customer,
    main_menu_seller,
    phone_request_keyboard,
)
from database_protocol import DatabaseProtocol
from handlers.common.states import ChangeCity, ConfirmOrder, Registration
from handlers.common.utils import (
    get_user_view_mode,
    has_approved_store,
    set_user_view_mode,
    user_view_mode,
)
from handlers.common.webapp import get_partner_panel_url
from localization import get_cities, get_text
from app.core.utils import normalize_city

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# Type alias for booking/offer dict
RowDict = dict[str, Any]

router = Router(name="commands")


async def handle_qr_pickup(message: types.Message, db: DatabaseProtocol, booking_code: str):
    """Handle QR/code scan for pickup confirmation (orders + legacy bookings)."""
    logger.info(f"🔗 handle_qr_pickup called: code='{booking_code}'")

    if not message.from_user:
        return

    import json

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    logger.info(f"🔗 handle_qr_pickup: user={user_id}, lang={lang}")

    code_input = (booking_code or "").strip().upper()
    if code_input.startswith("FUDLY-"):
        code_input = code_input.replace("FUDLY-", "")

    entity_type: str | None = None
    entity_id: int | None = None
    status: str | None = None
    store_id: int | None = None
    customer_id: int | None = None
    pickup_code: str | None = None
    store_name: str = "Магазин"
    customer_name: str = "Клиент"
    customer_phone: str = ""

    offer_title: str = "Товар"
    quantity: int = 1
    items_lines: str = ""

    # Prefer unified pickup orders by pickup_code (v24+)
    order = None
    if hasattr(db, "get_order_by_pickup_code"):
        try:
            order = db.get_order_by_pickup_code(code_input)
        except Exception:
            order = None

    if not order:
        try:
            numeric_id = int(code_input)
            order = db.get_order(numeric_id) if hasattr(db, "get_order") else None
        except Exception:
            order = None

    if isinstance(order, dict) and (order.get("order_type") or "pickup") == "pickup":
        entity_type = "order"
        entity_id = order.get("order_id")
        status = order.get("order_status")
        store_id = order.get("store_id")
        customer_id = order.get("user_id")
        pickup_code = order.get("pickup_code") or code_input

        if int(order.get("is_cart_order") or 0) == 1 and order.get("cart_items"):
            try:
                cart_items = (
                    json.loads(order["cart_items"])
                    if isinstance(order["cart_items"], str)
                    else order["cart_items"]
                )
            except Exception:
                cart_items = []

            if cart_items:
                offer_title = "Корзина"
                items_lines = "\n".join(
                    [f"• {it.get('title', 'Товар')} × {it.get('quantity', 1)}" for it in cart_items]
                )
                quantity = len(cart_items)
        else:
            offer_id = order.get("offer_id")
            quantity = int(order.get("quantity") or 1)
            if offer_id:
                offer = db.get_offer(offer_id)
                if isinstance(offer, dict):
                    offer_title = offer.get("title", offer_title)
                elif offer and len(offer) > 2:
                    offer_title = offer[2] if len(offer) > 2 else offer_title

    # Fallback: legacy bookings by code/id
    booking = None
    if not entity_type:
        booking = db.get_booking_by_code(code_input) if hasattr(db, "get_booking_by_code") else None
        if not booking:
            try:
                booking_id = int(code_input)
                booking = db.get_booking(booking_id) if hasattr(db, "get_booking") else None
            except Exception:
                booking = None

        if not booking:
            await message.answer(
                "❌ Бронирование/заказ не найдено" if lang == "ru" else "❌ Buyurtma topilmadi"
            )
            return

        entity_type = "booking"
        if isinstance(booking, dict):
            entity_id = booking.get("booking_id")
            status = booking.get("status")
            offer_id = booking.get("offer_id")
            customer_id = booking.get("user_id")
            quantity = int(booking.get("quantity", 1) or 1)
            pickup_code = booking.get("code") or code_input
        else:
            entity_id = booking[0] if len(booking) > 0 else None
            status = booking[3] if len(booking) > 3 else None
            offer_id = booking[1] if len(booking) > 1 else None
            customer_id = booking[2] if len(booking) > 2 else None
            quantity = int(booking[4] if len(booking) > 4 else 1)
            pickup_code = booking[9] if len(booking) > 9 else code_input

        offer = db.get_offer(offer_id) if offer_id else None
        if isinstance(offer, dict):
            store_id = offer.get("store_id")
            offer_title = offer.get("title", offer_title)
        elif offer and len(offer) > 2:
            store_id = offer[1]
            offer_title = offer[2] if len(offer) > 2 else offer_title

    if not entity_id or not store_id:
        await message.answer(
            "❌ Неверные данные заказа" if lang == "ru" else "❌ Noto'g'ri buyurtma"
        )
        return

    store = db.get_store(store_id) if store_id else None
    owner_id = None
    if isinstance(store, dict):
        owner_id = store.get("owner_id")
        store_name = store.get("name", store_name)
    elif store and len(store) > 2:
        owner_id = store[1]
        store_name = store[2] if len(store) > 2 else store_name

    customer = db.get_user_model(customer_id) if customer_id else None
    if customer:
        customer_name = (
            getattr(customer, "name", None)
            or getattr(customer, "first_name", None)
            or customer_name
        )
        customer_phone = getattr(customer, "phone", None) or ""

    is_owner = user_id == owner_id
    is_customer = user_id == customer_id

    status_info = {
        "pending": ("⏳", "Ожидает подтверждения" if lang == "ru" else "Tasdiqlash kutilmoqda"),
        "confirmed": ("✅", "Подтверждён" if lang == "ru" else "Tasdiqlangan"),
        "preparing": ("👨‍🍳", "Готовится" if lang == "ru" else "Tayyorlanmoqda"),
        "ready": ("📦", "Готово" if lang == "ru" else "Tayyor"),
        "completed": ("🎉", "Выдан" if lang == "ru" else "Berilgan"),
        "rejected": ("❌", "Отклонён" if lang == "ru" else "Rad etildi"),
        "cancelled": ("❌", "Отменён" if lang == "ru" else "Bekor qilingan"),
    }
    status_emoji, status_text = status_info.get(status, ("📦", str(status)))

    if status == "completed":
        await message.answer(
            f"✅ {'Этот заказ уже выдан' if lang == 'ru' else 'Bu buyurtma allaqachon berilgan'}"
        )
        return

    if status in ("cancelled", "rejected"):
        await message.answer(
            f"❌ {'Этот заказ отменён' if lang == 'ru' else 'Bu buyurtma bekor qilingan'}"
        )
        return

    label_ru = "Заказ" if entity_type == "order" else "Бронь"
    label_uz = "Buyurtma" if entity_type == "order" else "Bron"

    if is_owner:
        kb = InlineKeyboardBuilder()
        kb.button(
            text="✅ Выдать заказ" if lang == "ru" else "✅ Buyurtmani berish",
            callback_data=f"order_complete_{entity_id}",
        )
        kb.adjust(1)

        if lang == "ru":
            text = (
                f"📦 <b>СКАНИРОВАНИЕ КОДА</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 {label_ru}: <b>#{entity_id}</b>\n"
                f"📝 Код: <code>{pickup_code or code_input}</code>\n"
                f"{status_emoji} Статус: <b>{status_text}</b>\n\n"
                f"📦 Товар: <b>{offer_title}</b>\n"
            )
            if items_lines:
                text += f"{items_lines}\n"
            text += f"🔢 Количество: <b>{quantity}</b>\n\n"
            text += f"👤 Клиент: {customer_name}\n"
            if customer_phone:
                text += f"📱 Телефон: <code>{customer_phone}</code>\n"
            text += "\n━━━━━━━━━━━━━━━━━━\n"
            text += "👆 Нажмите кнопку для подтверждения выдачи"
        else:
            text = (
                f"📦 <b>KOD SKANERLASH</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 {label_uz}: <b>#{entity_id}</b>\n"
                f"📝 Kod: <code>{pickup_code or code_input}</code>\n"
                f"{status_emoji} Holat: <b>{status_text}</b>\n\n"
                f"📦 Mahsulot: <b>{offer_title}</b>\n"
            )
            if items_lines:
                text += f"{items_lines}\n"
            text += f"🔢 Miqdor: <b>{quantity}</b>\n\n"
            text += f"👤 Mijoz: {customer_name}\n"
            if customer_phone:
                text += f"📱 Telefon: <code>{customer_phone}</code>\n"
            text += "\n━━━━━━━━━━━━━━━━━━\n"
            text += "👆 Berilganini tasdiqlash uchun tugmani bosing"

        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
        return

    if is_customer:
        if lang == "ru":
            text = (
                f"📦 <b>Ваш {label_ru.lower()} #{entity_id}</b>\n\n"
                f"{status_emoji} Статус: <b>{status_text}</b>\n"
                f"📦 Товар: {offer_title}\n"
                f"🏪 Магазин: {store_name}\n\n"
                f"💡 Покажите этот код продавцу для получения заказа."
            )
        else:
            text = (
                f"📦 <b>Sizning {label_uz.lower()} #{entity_id}</b>\n\n"
                f"{status_emoji} Holat: <b>{status_text}</b>\n"
                f"📦 Mahsulot: {offer_title}\n"
                f"🏪 Do'kon: {store_name}\n\n"
                f"💡 Kodni sotuvchiga ko'rsating."
            )
        await message.answer(text, parse_mode="HTML")
        return

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
    stats_city = current_city
    if user and getattr(user, "district", None):
        district_label = get_district_label(user.region or user.city, user.district, lang)
        if district_label:
            current_city = f"{current_city} / {district_label}"

    stats_text = ""
    try:
        stores_count = len(db.get_stores_by_city(stats_city))
        offers_count = len(db.get_active_offers(city=stats_city))
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
    await state.set_state(ChangeCity.city)
    if callback.message and hasattr(callback.message, "edit_text"):
        # For inline keyboard, send new message instead of editing with reply keyboard
        cities = get_cities(lang)
        builder = InlineKeyboardBuilder()
        for idx, city in enumerate(cities):
            builder.button(text=city, callback_data=f"select_city:{idx}")
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
    idx_raw = callback.data.split(":", 1)[1] if ":" in callback.data else ""
    idx: int | None = None
    try:
        cities = get_cities(lang)
        try:
            idx = int(idx_raw)
            if idx < 0 or idx >= len(cities):
                raise IndexError("city index out of range")
            city = cities[idx]
        except ValueError:
            if idx_raw not in cities:
                raise ValueError("city not found")
            city = idx_raw
    except Exception:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    normalized_city = normalize_city(city)
    region_key = get_region_key_for_city_index(idx)
    district_options = get_districts_for_city_index(idx, lang)
    if not district_options:
        district_options = get_districts_for_region(city, lang)
    if district_options:
        region_value = normalize_city(region_key or city)
        await state.update_data(
            region_label=city,
            region_value=region_value,
            region_key=region_key,
        )
        await state.set_state(ChangeCity.district)
        builder = InlineKeyboardBuilder()
        for idx, (label, _value) in enumerate(district_options):
            builder.button(text=f"\U0001F4CD {label}", callback_data=f"select_district:{idx}")
        builder.adjust(2)
        prompt = (
            "🏘 Выберите район/город в области:" if lang == "ru" else "🏘 Viloyatdagi tuman/shaharni tanlang:"
        )
        if callback.message:
            try:
                await callback.message.edit_text(prompt, reply_markup=builder.as_markup())
            except Exception as e:
                logger.debug("Could not edit district prompt: %s", e)
                await callback.message.answer(prompt, reply_markup=builder.as_markup())
        await callback.answer()
        return

    if hasattr(db, "update_user_location"):
        db.update_user_location(
            callback.from_user.id,
            city=normalized_city,
            clear_region=True,
            clear_district=True,
        )
    else:
        db.update_user_city(callback.from_user.id, normalized_city)
    await state.clear()

    user = db.get_user_model(callback.from_user.id)
    user_role = user.role if user else "customer"
    menu = (
        main_menu_seller(lang, webapp_url=get_partner_panel_url(), user_id=callback.from_user.id)
        if user_role == "seller"
        else main_menu_customer(lang)
    )

    try:
        await callback.message.edit_text(get_text(lang, "city_selected", city=city))
    except Exception as e:
        logger.debug("Could not edit city confirmation: %s", e)

    await callback.message.answer(
        get_text(lang, "welcome_back", name=callback.from_user.first_name, city=city),
        parse_mode="HTML",
        reply_markup=menu,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("select_district:"), StateFilter(ChangeCity.district))
async def handle_district_selection(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
):
    """Handle district selection from inline keyboard."""
    if not callback.data or not callback.message:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    region_label = data.get("region_label")
    region_key = data.get("region_key")
    region_value = data.get("region_value") or normalize_city(region_key or region_label or "")

    try:
        idx_raw = callback.data.split(":", 1)[1]
        options = get_districts_for_region(region_label or region_value, lang)
        idx = int(idx_raw)
        if idx < 0 or idx >= len(options):
            raise IndexError("district index out of range")
        district_label, district_value = options[idx]
    except Exception:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if hasattr(db, "update_user_location"):
        db.update_user_location(
            callback.from_user.id,
            city=region_value,
            region=region_value,
            district=district_value,
        )
    else:
        db.update_user_city(callback.from_user.id, region_value)

    await state.clear()

    user = db.get_user_model(callback.from_user.id)
    user_role = user.role if user else "customer"
    menu = (
        main_menu_seller(lang, webapp_url=get_partner_panel_url(), user_id=callback.from_user.id)
        if user_role == "seller"
        else main_menu_customer(lang)
    )

    city_display = region_label or region_key or region_value
    if district_label:
        city_display = f"{city_display} / {district_label}"

    try:
        await callback.message.edit_text(get_text(lang, "city_selected", city=city_display))
    except Exception as e:
        logger.debug("Could not edit city confirmation: %s", e)

    await callback.message.answer(
        get_text(lang, "welcome_back", name=callback.from_user.first_name, city=city_display),
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

    menu = (
        main_menu_seller(lang, webapp_url=get_partner_panel_url(), user_id=callback.from_user.id)
        if user_role == "seller"
        else main_menu_customer(lang)
    )

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

    normalized_city = normalize_city(new_city)
    db.update_user_city(user_id, normalized_city)

    user_role = user.role or "customer" if user else "customer"
    menu = (
        main_menu_seller(lang, webapp_url=get_partner_panel_url(), user_id=user_id)
        if user_role == "seller"
        else main_menu_customer(lang)
    )

    await message.answer(
        get_text(lang, "city_changed_confirm", city=new_city),
        parse_mode="HTML",
        reply_markup=menu,
    )


# ===================== OPTIMIZED REGISTRATION FLOW =====================
# Single card that transforms: Welcome+Lang → Phone → City → Done
# Minimal messages, maximum UX


def build_welcome_card(lang: str = "ru") -> str:
    """Build welcome message for new users."""
    if lang == "uz":
        return "Fudly ga xush kelibsiz!\n\nBoshlash uchun tilni tanlang."
    return "Добро пожаловать в Fudly!\n\nЧтобы начать, выберите язык."


def build_phone_card(lang: str) -> str:
    """Build phone request card."""
    return get_text(lang, "welcome_phone_step")


def build_city_card(lang: str) -> str:
    """Build city selection card."""
    return get_text(lang, "choose_city")


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

    user_id = message.from_user.id

    # Clear any active state
    await state.clear()

    # Check for deep link arguments (e.g., /start pickup_CODE or upload_proof_12345)
    if message.text:
        args = message.text.split(maxsplit=1)
        logger.info(f"🔗 /start command from user {user_id}: '{message.text}'")
        if len(args) > 1:
            deep_link = args[1]

            # Handle pickup deep link
            if deep_link.startswith("pickup_"):
                # Ensure user exists even for QR/deep-link starts
                try:
                    user = db.get_user_model(user_id)
                except Exception as e:  # pragma: no cover - defensive logging
                    logger.warning(f"Failed to load user {user_id} for pickup deep-link: {e}")
                    user = None

                if not user:
                    try:
                        db.add_user(
                            user_id, message.from_user.username, message.from_user.first_name
                        )
                        logger.info(f"👤 Created new user {user_id} from pickup deep-link /start")
                    except Exception as e:  # pragma: no cover - defensive logging
                        logger.warning(f"Failed to create user {user_id} on pickup deep-link: {e}")

                booking_code = deep_link.replace("pickup_", "")
                await handle_qr_pickup(message, db, booking_code)
                return

            # Handle payment proof upload deep link
            elif deep_link.startswith("upload_proof_"):
                from aiogram.utils.keyboard import InlineKeyboardBuilder

                try:
                    order_id = int(deep_link.replace("upload_proof_", ""))

                    # Trigger payment proof upload flow via callback
                    kb = InlineKeyboardBuilder()
                    kb.button(
                        text="📸 Yuklash / Загрузить", callback_data=f"upload_proof_{order_id}"
                    )

                    lang = (
                        db.get_user_language(user_id) if hasattr(db, "get_user_language") else "ru"
                    )
                    if lang == "uz":
                        msg = (
                            f"📦 <b>Buyurtma #{order_id}</b>\n\n"
                            f"To'lov chekini yuklash uchun quyidagi tugmani bosing."
                        )
                    else:
                        msg = (
                            f"📦 <b>Заказ #{order_id}</b>\n\n"
                            f"Нажмите кнопку ниже, чтобы загрузить чек об оплате."
                        )

                    await message.answer(msg, reply_markup=kb.as_markup(), parse_mode="HTML")
                    return
                except ValueError:
                    logger.warning(f"Invalid upload_proof deep link: {deep_link}")
                except Exception as e:
                    logger.error(f"Error handling upload_proof deep link: {e}")

    user = db.get_user_model(user_id)

    # NEW USER - create immediately and show welcome card with language selection
    if not user:
        # Create user right away to avoid duplicate welcome on second /start
        db.add_user(user_id, message.from_user.username, message.from_user.first_name)
        logger.info(f"👤 Created new user {user_id} from regular /start")
        await message.answer(
            build_welcome_card("ru"), parse_mode="HTML", reply_markup=build_welcome_keyboard()
        )
        return

    lang = db.get_user_language(user_id)
    user_phone = user.phone if user else None
    if not user_phone:
        await message.answer(
            get_text(lang, "welcome_phone_step"),
            parse_mode="HTML",
            reply_markup=phone_request_keyboard(lang),
        )
        await state.set_state(Registration.phone)
        return

    user_city = user.city
    user_role = user.role or "customer"
    user_phone = user.phone if user else None

    # Require phone early to avoid checkout friction
    if not user_phone:
        await state.set_state(Registration.phone)
        await message.answer(
            get_text(lang, "welcome_phone_step"),
            parse_mode="HTML",
            reply_markup=phone_request_keyboard(lang),
        )
        return

    # User exists but hasn't selected city yet - show city selection
    if not user_city:
        await message.answer(
            get_text(lang, "choose_city"),
            parse_mode="HTML",
            reply_markup=city_inline_keyboard(lang, allow_cancel=False),
        )
        # DON'T set state - city is selected via inline buttons only
        await state.clear()
        return

    # Registered user - show menu
    current_mode = get_user_view_mode(user_id, db)
    if current_mode == "seller" and user_role == "seller":
        menu = main_menu_seller(lang, webapp_url=get_partner_panel_url(), user_id=user_id)
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
    """Step 1: Language selected -> request phone, then city selection."""
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

    # Switch to phone request step
    try:
        await callback.message.edit_text(get_text(lang, "language_changed"), parse_mode="HTML")
    except Exception as e:
        logger.debug("Could not edit language confirmation: %s", e)

    await callback.message.answer(
        get_text(lang, "welcome_phone_step"),
        parse_mode="HTML",
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
        # Redirect to new registration flow - request phone first
        db.add_user(
            callback.from_user.id, callback.from_user.username, callback.from_user.first_name
        )
        db.update_user_language(callback.from_user.id, lang)

        try:
            await callback.message.edit_text(get_text(lang, "language_changed"), parse_mode="HTML")
        except Exception as e:
            logger.debug("Could not edit language confirmation: %s", e)

        await callback.message.answer(
            get_text(lang, "welcome_phone_step"),
            parse_mode="HTML",
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
    except Exception as e:
        logger.debug("Could not edit language confirmation: %s", e)

    user_phone = user.phone if user else None
    if not user_phone:
        await callback.message.answer(
            get_text(lang, "welcome_phone_step"),
            parse_mode="HTML",
            reply_markup=phone_request_keyboard(lang),
        )
        await state.set_state(Registration.phone)
        await callback.answer()
        return

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
