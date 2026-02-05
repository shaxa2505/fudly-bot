"""Store settings handlers - photo upload, store info management."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.geocoding import reverse_geocode_store
from database_protocol import DatabaseProtocol
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router(name="store_settings")


class StoreSettingsStates(StatesGroup):
    """States for store settings."""

    waiting_photo = State()
    waiting_location = State()
    waiting_admin_contact = State()  # Waiting for admin contact/username
    waiting_click_merchant_id = State()
    waiting_click_service_id = State()
    waiting_click_secret_key = State()
    waiting_payme_merchant_id = State()
    waiting_payme_secret_key = State()


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


def verify_store_owner(user_id: int, store_id: int) -> bool:
    """Verify that user is owner of the store."""
    if not db:
        return False
    store = db.get_store(store_id)
    if not store:
        return False
    # Handle both dict and tuple
    if isinstance(store, dict):
        return store.get("owner_id") == user_id
    # Tuple: assume owner_id is at index 2
    return len(store) > 2 and store[2] == user_id


def store_settings_keyboard(
    store_id: int,
    lang: str = "ru",
    has_photo: bool = False,
    has_location: bool = False,
    is_owner: bool = True,
) -> types.InlineKeyboardMarkup:
    """Store settings keyboard."""
    builder = InlineKeyboardBuilder()

    if has_photo:
        photo_text = "Изменить фото" if lang == "ru" else "Rasmni o'zgartirish"
        remove_photo_text = "Удалить фото" if lang == "ru" else "Rasmni o'chirish"
        builder.button(text=photo_text, callback_data=f"store_change_photo_{store_id}")
        builder.button(text=remove_photo_text, callback_data=f"store_remove_photo_{store_id}")
    else:
        photo_text = "Добавить фото" if lang == "ru" else "Rasm qo'shish"
        builder.button(text=photo_text, callback_data=f"store_change_photo_{store_id}")

    # Geolocation
    if has_location:
        location_text = "Изменить локацию" if lang == "ru" else "Joylashuvni o'zgartirish"
    else:
        location_text = "Добавить локацию" if lang == "ru" else "Joylashuv qo'shish"
    builder.button(text=location_text, callback_data=f"store_location_setup_{store_id}")

    # Payment integrations (only for owner)
    if is_owner:
        payment_text = "Онлайн оплата" if lang == "ru" else "Onlayn to'lov"
        builder.button(text=payment_text, callback_data=f"store_payment_settings_{store_id}")

        # Store admins management (only for owner)
        admins_text = "Сотрудники" if lang == "ru" else "Xodimlar"
        builder.button(text=admins_text, callback_data=f"store_admins_{store_id}")

    back_text = "Назад" if lang == "ru" else "Orqaga"
    builder.button(text=back_text, callback_data="store_settings_back")

    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "my_store_settings")
async def show_store_settings(callback: types.CallbackQuery) -> None:
    """Show store settings menu."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    user_id = callback.from_user.id

    # Get user's stores (owned + admin access)
    stores = db.get_user_accessible_stores(user_id)
    active_stores = [s for s in stores if s.get("status") in ("active", "approved")]

    if not active_stores:
        await callback.answer(
            "У вас нет активного магазина" if lang == "ru" else "Sizda faol do'kon yo'q",
            show_alert=True,
        )
        return

    store = active_stores[0]
    store_id = store.get("store_id")
    store_name = store.get("name", "Магазин")
    has_photo = bool(store.get("photo"))
    has_location = bool(store.get("latitude") and store.get("longitude"))
    is_owner = store.get("user_role") == "owner" or store.get("owner_id") == user_id

    role_text = "" if is_owner else (" (сотрудник)" if lang == "ru" else " (xodim)")

    geo_set = "O'rnatilgan" if has_location else "O'rnatilmagan"
    if lang == "ru":
        text = (
            f"<b>Настройки магазина{role_text}</b>\n\n"
            f"<b>{store_name}</b>\n\n"
            f"Фото: {'Загружено' if has_photo else 'Не загружено'}\n"
            f"Геолокация: {'Установлена' if has_location else 'Не установлена'}"
        )
    else:
        text = (
            f"<b>Do'kon sozlamalari{role_text}</b>\n\n"
            f"<b>{store_name}</b>\n\n"
            f"Rasm: {'Yuklangan' if has_photo else 'Yuklanmagan'}\n"
            f"Geolokatsiya: {geo_set}"
        )

    # Show current photo if exists
    if has_photo and callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
        try:
            await bot.send_photo(
                callback.from_user.id,
                photo=store.get("photo"),
                caption=text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(
                    store_id, lang, has_photo, has_location, is_owner
                ),
            )
        except Exception:
            await bot.send_message(
                callback.from_user.id,
                text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(
                    store_id, lang, has_photo, has_location, is_owner
                ),
            )
    else:
        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(
                    store_id, lang, has_photo, has_location, is_owner
                ),
            )
        except Exception:
            await callback.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(
                    store_id, lang, has_photo, has_location, is_owner
                ),
            )

    await callback.answer()


@router.callback_query(F.data.startswith("store_change_photo_"))
async def request_store_photo(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Request new store photo."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    store_id = int(callback.data.replace("store_change_photo_", ""))

    # Verify store ownership
    if not verify_store_owner(callback.from_user.id, store_id):
        await callback.answer("Нет доступа" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    await state.update_data(store_id=store_id)
    await state.set_state(StoreSettingsStates.waiting_photo)

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(text="Отмена" if lang == "ru" else "Bekor qilish", callback_data="store_photo_cancel")

    text = (
        "<b>Загрузка фото магазина</b>\n\n"
        "Отправьте фото вашего магазина или витрины.\n"
        "Это поможет покупателям узнать ваш магазин!"
        if lang == "ru"
        else "<b>Do'kon fotosuratini yuklash</b>\n\n"
        "Do'koningiz yoki vitrina fotosuratini yuboring.\n"
        "Bu xaridorlarga do'koningizni tanishga yordam beradi!"
    )

    try:
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=cancel_kb.as_markup()
        )
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=cancel_kb.as_markup())

    await callback.answer()


@router.message(StoreSettingsStates.waiting_photo, F.photo)
async def handle_store_photo(message: types.Message, state: FSMContext) -> None:
    """Handle store photo upload."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    data = await state.get_data()
    store_id = data.get("store_id")

    if not store_id:
        await state.clear()
        await message.answer("Error: store not found")
        return

    # Get photo file_id
    photo_id = message.photo[-1].file_id

    # Update store photo
    try:
        db.update_store_photo(store_id, photo_id)

        await state.clear()

        success_text = (
            "<b>Фото магазина обновлено</b>\n\nТеперь покупатели смогут видеть ваш магазин."
            if lang == "ru"
            else "<b>Do'kon rasmi yangilandi</b>\n\nEndi xaridorlar do'koningizni ko'rishlari mumkin."
        )

        # Show updated photo with back button
        back_kb = InlineKeyboardBuilder()
        back_kb.button(
            text="Настройки магазина" if lang == "ru" else "Do'kon sozlamalari",
            callback_data="my_store_settings",
        )

        await message.answer_photo(
            photo=photo_id,
            caption=success_text,
            parse_mode="HTML",
            reply_markup=back_kb.as_markup(),
        )

        logger.info(f"Store {store_id} photo updated by user {message.from_user.id}")

    except Exception as e:
        logger.error(f"Failed to update store photo: {e}")
        await message.answer(
            "Ошибка при загрузке фото" if lang == "ru" else "Rasm yuklashda xatolik"
        )


@router.callback_query(F.data == "store_photo_cancel")
async def cancel_photo_upload(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel photo upload."""
    await state.clear()

    if not db:
        await callback.answer("Cancelled")
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    # Return to store settings
    stores = db.get_user_accessible_stores(callback.from_user.id)
    active_stores = [s for s in stores if s.get("status") in ("active", "approved")]

    if active_stores:
        store = active_stores[0]
        store_id = store.get("store_id")
        store_name = store.get("name", "Магазин")
        has_photo = bool(store.get("photo"))
        has_location = bool(store.get("latitude") and store.get("longitude"))

        text = (
            f"<b>Настройки магазина</b>\n\n"
            f"<b>{store_name}</b>\n\n"
            f"Фото: {'Загружено' if has_photo else 'Не загружено'}\n"
            f"Геолокация: {'Установлена' if has_location else 'Не установлена'}"
            if lang == "ru"
            else f"<b>Do'kon sozlamalari</b>\n\n"
            f"<b>{store_name}</b>\n\n"
            f"Rasm: {'Yuklangan' if has_photo else 'Yuklanmagan'}\n"
            f"Geolokatsiya: {'Ornatilgan' if has_location else 'Ornatilmagan'}"
        )

        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(store_id, lang, has_photo, has_location),
            )
        except Exception:
            pass

    await callback.answer()


@router.callback_query(F.data.startswith("store_remove_photo_"))
async def remove_store_photo(callback: types.CallbackQuery) -> None:
    """Remove store photo."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    store_id = int(callback.data.replace("store_remove_photo_", ""))

    # Verify store ownership
    if not verify_store_owner(callback.from_user.id, store_id):
        await callback.answer("Нет доступа" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    try:
        db.update_store_photo(store_id, None)

        # Show updated settings
        stores = db.get_user_accessible_stores(callback.from_user.id)
        active_stores = [s for s in stores if s.get("status") in ("active", "approved")]

        if active_stores:
            store = active_stores[0]
            store_name = store.get("name", "Магазин")
            has_location = bool(store.get("latitude") and store.get("longitude"))

            text = (
                f"<b>Настройки магазина</b>\n\n"
                f"<b>{store_name}</b>\n\n"
                f"Фото: Не загружено\n"
                f"Геолокация: {'Установлена' if has_location else 'Не установлена'}\n\n"
                f"Фото удалено"
                if lang == "ru"
                else f"<b>Do'kon sozlamalari</b>\n\n"
                f"<b>{store_name}</b>\n\n"
                f"Rasm: Yuklanmagan\n"
                f"Geolokatsiya: {'Ornatilgan' if has_location else 'Ornatilmagan'}\n\n"
                f"Rasm o'chirildi"
            )

            try:
                await callback.message.delete()
            except Exception:
                pass

            await bot.send_message(
                callback.from_user.id,
                text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(store_id, lang, False, has_location),
            )

        await callback.answer("Фото удалено" if lang == "ru" else "Rasm o'chirildi")
        logger.info(f"Store {store_id} photo removed by user {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Failed to remove store photo: {e}")
        await callback.answer("Ошибка" if lang == "ru" else "Xatolik", show_alert=True)


@router.callback_query(F.data == "store_settings_back")
async def back_from_settings(callback: types.CallbackQuery) -> None:
    """Go back from store settings."""
    if not db:
        await callback.answer()
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    from app.keyboards import main_menu_seller

    try:
        await callback.message.delete()
    except Exception:
        pass

    await bot.send_message(
        callback.from_user.id,
        "Главное меню" if lang == "ru" else "Asosiy menyu",
        reply_markup=main_menu_seller(lang, user_id=callback.from_user.id),
    )

    await callback.answer()


# ===================== GEOLOCATION SETTINGS =====================


@router.callback_query(F.data.startswith("store_location_setup_"))
async def setup_store_location(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start store location setup - request user to send location."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    assert callback.data is not None
    lang = db.get_user_language(callback.from_user.id)

    store_id = int(callback.data.replace("store_location_setup_", ""))

    # Verify store ownership
    if not verify_store_owner(callback.from_user.id, store_id):
        await callback.answer("Нет доступа" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    # Save store_id to state
    await state.update_data(store_id=store_id)
    await state.set_state(StoreSettingsStates.waiting_location)

    text = (
        "<b>Установка геолокации магазина</b>\n\n"
        "Отправьте геолокацию вашего магазина.\n\n"
        "Вы можете:\n"
        "- Отправить текущую геолокацию (через меню вложений)\n"
        "- Выбрать точку на карте"
        if lang == "ru"
        else "<b>Do'kon geolokatsiyasini o'rnatish</b>\n\n"
        "Do'koningiz joylashuvini yuboring.\n\n"
        "Siz:\n"
        "- Hozirgi joylashuvingizni yuborishingiz mumkin (ilova menyusi orqali)\n"
        "- Xaritadan nuqta tanlashingiz mumkin"
    )

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(
        text="Отмена" if lang == "ru" else "Bekor qilish",
        callback_data="store_location_cancel",
    )

    try:
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=cancel_kb.as_markup()
        )
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=cancel_kb.as_markup())

    await callback.answer()


@router.message(StoreSettingsStates.waiting_location, F.location)
async def handle_store_location(message: types.Message, state: FSMContext) -> None:
    """Handle store location message."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
    assert message.location is not None
    lang = db.get_user_language(message.from_user.id)

    data = await state.get_data()
    store_id = data.get("store_id")

    if not store_id:
        await state.clear()
        await message.answer("Error: store not found")
        return

    latitude = message.location.latitude
    longitude = message.location.longitude

    # Update store location
    try:
        region = None
        district = None
        try:
            geo = await reverse_geocode_store(latitude, longitude)
            if geo:
                region = geo.get("region")
                district = geo.get("district")
        except Exception as e:
            logger.warning(f"Reverse geocode failed for store {store_id}: {e}")

        db.update_store_location(store_id, latitude, longitude, region=region, district=district)

        await state.clear()

        success_text = (
            f"<b>Геолокация магазина установлена</b>\n\n"
            f"Координаты: {latitude:.6f}, {longitude:.6f}\n\n"
            f"Теперь ваш магазин будет отображаться на карте."
            if lang == "ru"
            else f"<b>Do'kon geolokatsiyasi o'rnatildi</b>\n\n"
            f"Koordinatalar: {latitude:.6f}, {longitude:.6f}\n\n"
            f"Endi do'koningiz xaritada ko'rinadi."
        )

        # Show back button
        back_kb = InlineKeyboardBuilder()
        back_kb.button(
            text="Настройки магазина" if lang == "ru" else "Do'kon sozlamalari",
            callback_data="my_store_settings",
        )

        await message.answer(success_text, parse_mode="HTML", reply_markup=back_kb.as_markup())

        logger.info(
            f"Store {store_id} location updated to ({latitude}, {longitude}) by user {message.from_user.id}"
        )

    except Exception as e:
        logger.error(f"Failed to update store location: {e}")
        await message.answer(
            "Ошибка при сохранении геолокации"
            if lang == "ru"
            else "Geolokatsiyani saqlashda xatolik"
        )


@router.callback_query(F.data == "store_location_cancel")
async def cancel_location_setup(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel location setup."""
    await state.clear()

    if not db:
        await callback.answer("Cancelled")
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    # Return to store settings
    stores = db.get_user_accessible_stores(callback.from_user.id)
    active_stores = [s for s in stores if s.get("status") in ("active", "approved")]

    if active_stores:
        store = active_stores[0]
        store_id = store.get("store_id")
        store_name = store.get("name", "Магазин")
        has_photo = bool(store.get("photo"))
        has_location = bool(store.get("latitude") and store.get("longitude"))

        text = (
            f"<b>Настройки магазина</b>\n\n"
            f"<b>{store_name}</b>\n\n"
            f"Фото: {'Загружено' if has_photo else 'Не загружено'}\n"
            f"Геолокация: {'Установлена' if has_location else 'Не установлена'}"
            if lang == "ru"
            else f"<b>Do'kon sozlamalari</b>\n\n"
            f"<b>{store_name}</b>\n\n"
            f"Rasm: {'Yuklangan' if has_photo else 'Yuklanmagan'}\n"
            f"Geolokatsiya: {'Ornatilgan' if has_location else 'Ornatilmagan'}"
        )

        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(store_id, lang, has_photo, has_location),
            )
        except Exception:
            pass

    await callback.answer()


# ===================== PAYMENT INTEGRATION SETTINGS =====================


def payment_settings_keyboard(
    store_id: int, lang: str = "ru", integrations: list = None
) -> types.InlineKeyboardMarkup:
    """Payment settings keyboard."""
    builder = InlineKeyboardBuilder()
    integrations = integrations or []

    # Check which integrations are configured
    click_configured = any(i.get("provider") == "click" for i in integrations)
    payme_configured = any(i.get("provider") == "payme" for i in integrations)

    if click_configured:
        click_text = "Click (настроен)" if lang == "ru" else "Click (sozlangan)"
        builder.button(text=click_text, callback_data=f"store_click_view_{store_id}")
    else:
        click_text = "Подключить Click" if lang == "ru" else "Click ulash"
        builder.button(text=click_text, callback_data=f"store_click_setup_{store_id}")

    if payme_configured:
        payme_text = "Payme (настроен)" if lang == "ru" else "Payme (sozlangan)"
        builder.button(text=payme_text, callback_data=f"store_payme_view_{store_id}")
    else:
        payme_text = "Подключить Payme" if lang == "ru" else "Payme ulash"
        builder.button(text=payme_text, callback_data=f"store_payme_setup_{store_id}")

    back_text = "Назад" if lang == "ru" else "Orqaga"
    builder.button(text=back_text, callback_data="my_store_settings")

    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data.startswith("store_payment_settings_"))
async def show_payment_settings(callback: types.CallbackQuery) -> None:
    """Show payment integration settings."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    store_id = int(callback.data.replace("store_payment_settings_", ""))

    # Verify store ownership
    if not verify_store_owner(callback.from_user.id, store_id):
        await callback.answer("Нет доступа" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    # Get current integrations
    try:
        integrations = db.get_store_payment_integrations(store_id)
    except Exception:
        integrations = []

    text = (
        "<b>Настройки онлайн оплаты</b>\n\n"
        "Подключите Click или Payme чтобы покупатели могли "
        "оплачивать заказы онлайн. Деньги поступят напрямую на ваш счёт.\n\n"
        "<b>Как подключить:</b>\n"
        "1. Зарегистрируйтесь как мерчант в Click/Payme\n"
        "2. Получите API ключи в личном кабинете\n"
        "3. Введите их здесь"
        if lang == "ru"
        else "<b>Onlayn to'lov sozlamalari</b>\n\n"
        "Click yoki Payme-ni ulang, shunda xaridorlar buyurtmalarni "
        "onlayn to'lashi mumkin. Pul to'g'ridan-to'g'ri hisobingizga tushadi.\n\n"
        "<b>Qanday ulash mumkin:</b>\n"
        "1. Click/Payme-da merchant sifatida ro'yxatdan o'ting\n"
        "2. Shaxsiy kabinetdan API kalitlarini oling\n"
        "3. Ularni shu yerga kiriting"
    )

    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=payment_settings_keyboard(store_id, lang, integrations),
        )
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data.startswith("store_click_setup_"))
async def setup_click_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start Click setup."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    store_id = int(callback.data.replace("store_click_setup_", ""))

    # Verify store ownership
    if not verify_store_owner(callback.from_user.id, store_id):
        await callback.answer("Нет доступа" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    await state.update_data(store_id=store_id, provider="click")
    await state.set_state(StoreSettingsStates.waiting_click_merchant_id)

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(
        text="Отмена" if lang == "ru" else "Bekor qilish",
        callback_data=f"store_payment_settings_{store_id}",
    )

    text = (
        "<b>Подключение Click</b>\n\n"
        "Шаг 1/3: Введите ваш <b>Merchant ID</b>\n\n"
        "Его можно найти в личном кабинете Click Merchant:\n"
        "merchant.click.uz → Настройки → API"
        if lang == "ru"
        else "<b>Click ulash</b>\n\n"
        "1-qadam: <b>Merchant ID</b>-ni kiriting\n\n"
        "Uni Click Merchant shaxsiy kabinetida topish mumkin:\n"
        "merchant.click.uz → Sozlamalar → API"
    )

    try:
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=cancel_kb.as_markup()
        )
    except Exception:
        pass

    await callback.answer()


@router.message(StoreSettingsStates.waiting_click_merchant_id)
async def handle_click_merchant_id(message: types.Message, state: FSMContext) -> None:
    """Handle Click merchant ID input."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    merchant_id = message.text.strip() if message.text else ""

    if not merchant_id or len(merchant_id) < 3:
        await message.answer(
            "Введите корректный Merchant ID"
            if lang == "ru"
            else "To'g'ri Merchant ID kiriting"
        )
        return

    await state.update_data(click_merchant_id=merchant_id)
    await state.set_state(StoreSettingsStates.waiting_click_service_id)

    data = await state.get_data()
    store_id = data.get("store_id")

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(
        text="Отмена" if lang == "ru" else "Bekor qilish",
        callback_data=f"store_payment_settings_{store_id}",
    )

    text = (
        "Merchant ID сохранён\n\nШаг 2/3: Введите ваш <b>Service ID</b>"
        if lang == "ru"
        else "Merchant ID saqlandi\n\n2-qadam: <b>Service ID</b>-ni kiriting"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=cancel_kb.as_markup())


@router.message(StoreSettingsStates.waiting_click_service_id)
async def handle_click_service_id(message: types.Message, state: FSMContext) -> None:
    """Handle Click service ID input."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    service_id = message.text.strip() if message.text else ""

    if not service_id or len(service_id) < 3:
        await message.answer(
            "Введите корректный Service ID"
            if lang == "ru"
            else "To'g'ri Service ID kiriting"
        )
        return

    await state.update_data(click_service_id=service_id)
    await state.set_state(StoreSettingsStates.waiting_click_secret_key)

    data = await state.get_data()
    store_id = data.get("store_id")

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(
        text="Отмена" if lang == "ru" else "Bekor qilish",
        callback_data=f"store_payment_settings_{store_id}",
    )

    text = (
        "Service ID сохранён\n\n"
        "Шаг 3/3: Введите ваш <b>Secret Key</b>\n\n"
        "Храните ключ в секрете."
        if lang == "ru"
        else "Service ID saqlandi\n\n"
        "3-qadam: <b>Secret Key</b>-ni kiriting\n\n"
        "Kalitni sir saqlang."
    )

    await message.answer(text, parse_mode="HTML", reply_markup=cancel_kb.as_markup())


@router.message(StoreSettingsStates.waiting_click_secret_key)
async def handle_click_secret_key(message: types.Message, state: FSMContext) -> None:
    """Handle Click secret key input and save."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    secret_key = message.text.strip() if message.text else ""

    if not secret_key or len(secret_key) < 5:
        await message.answer(
            "Введите корректный Secret Key"
            if lang == "ru"
            else "To'g'ri Secret Key kiriting"
        )
        return

    data = await state.get_data()
    store_id = data.get("store_id")
    merchant_id = data.get("click_merchant_id")
    service_id = data.get("click_service_id")

    # Save integration
    try:
        db.set_store_payment_integration(
            store_id=store_id,
            provider="click",
            merchant_id=merchant_id,
            secret_key=secret_key,
            service_id=service_id,
        )

        await state.clear()

        # Delete message with secret key for security
        try:
            await message.delete()
        except Exception:
            pass

        text = (
            "<b>Click подключён</b>\n\n"
            "Теперь покупатели могут оплачивать заказы через Click, "
            "и деньги будут поступать на ваш счёт."
            if lang == "ru"
            else "<b>Click ulandi</b>\n\n"
            "Endi xaridorlar Click orqali to'lashi mumkin, "
            "pul sizning hisobingizga tushadi."
        )

        back_kb = InlineKeyboardBuilder()
        back_kb.button(
            text="◀️ Назад" if lang == "ru" else "◀️ Orqaga",
            callback_data=f"store_payment_settings_{store_id}",
        )

        await message.answer(text, parse_mode="HTML", reply_markup=back_kb.as_markup())
        logger.info(f"Click integration configured for store {store_id}")

    except Exception as e:
        logger.error(f"Failed to save Click integration: {e}")
        await message.answer("Ошибка сохранения" if lang == "ru" else "Saqlashda xatolik")


@router.callback_query(F.data.startswith("store_payme_setup_"))
async def setup_payme_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start Payme setup."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    store_id = int(callback.data.replace("store_payme_setup_", ""))

    # Verify store ownership
    if not verify_store_owner(callback.from_user.id, store_id):
        await callback.answer("Нет доступа" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    await state.update_data(store_id=store_id, provider="payme")
    await state.set_state(StoreSettingsStates.waiting_payme_merchant_id)

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(
        text="Отмена" if lang == "ru" else "Bekor qilish",
        callback_data=f"store_payment_settings_{store_id}",
    )

    text = (
        "<b>Подключение Payme</b>\n\n"
        "Шаг 1/2: Введите ваш <b>Merchant ID</b>\n\n"
        "Его можно найти в кабинете Payme Merchant:\n"
        "merchant.payme.uz → Настройки"
        if lang == "ru"
        else "<b>Payme ulash</b>\n\n"
        "1-qadam: <b>Merchant ID</b>-ni kiriting\n\n"
        "Uni Payme Merchant kabinetida topish mumkin:\n"
        "merchant.payme.uz → Sozlamalar"
    )

    try:
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=cancel_kb.as_markup()
        )
    except Exception:
        pass

    await callback.answer()


@router.message(StoreSettingsStates.waiting_payme_merchant_id)
async def handle_payme_merchant_id(message: types.Message, state: FSMContext) -> None:
    """Handle Payme merchant ID input."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    merchant_id = message.text.strip() if message.text else ""

    if not merchant_id or len(merchant_id) < 3:
        await message.answer(
            "Введите корректный Merchant ID"
            if lang == "ru"
            else "To'g'ri Merchant ID kiriting"
        )
        return

    await state.update_data(payme_merchant_id=merchant_id)
    await state.set_state(StoreSettingsStates.waiting_payme_secret_key)

    data = await state.get_data()
    store_id = data.get("store_id")

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(
        text="Отмена" if lang == "ru" else "Bekor qilish",
        callback_data=f"store_payment_settings_{store_id}",
    )

    text = (
        "Merchant ID сохранён\n\n"
        "Шаг 2/2: Введите ваш <b>Secret Key</b>\n\n"
        "Храните ключ в секрете."
        if lang == "ru"
        else "Merchant ID saqlandi\n\n"
        "2-qadam: <b>Secret Key</b>-ni kiriting\n\n"
        "Kalitni sir saqlang."
    )

    await message.answer(text, parse_mode="HTML", reply_markup=cancel_kb.as_markup())


@router.message(StoreSettingsStates.waiting_payme_secret_key)
async def handle_payme_secret_key(message: types.Message, state: FSMContext) -> None:
    """Handle Payme secret key input and save."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    secret_key = message.text.strip() if message.text else ""

    if not secret_key or len(secret_key) < 5:
        await message.answer(
            "Введите корректный Secret Key"
            if lang == "ru"
            else "To'g'ri Secret Key kiriting"
        )
        return

    data = await state.get_data()
    store_id = data.get("store_id")
    merchant_id = data.get("payme_merchant_id")

    # Save integration
    try:
        db.set_store_payment_integration(
            store_id=store_id,
            provider="payme",
            merchant_id=merchant_id,
            secret_key=secret_key,
        )

        await state.clear()

        # Delete message with secret key for security
        try:
            await message.delete()
        except Exception:
            pass

        text = (
            "<b>Payme подключён</b>\n\n"
            "Теперь покупатели могут оплачивать заказы через Payme, "
            "и деньги будут поступать на ваш счёт."
            if lang == "ru"
            else "<b>Payme ulandi</b>\n\n"
            "Endi xaridorlar Payme orqali to'lashi mumkin, "
            "pul sizning hisobingizga tushadi."
        )

        back_kb = InlineKeyboardBuilder()
        back_kb.button(
            text="Назад" if lang == "ru" else "Orqaga",
            callback_data=f"store_payment_settings_{store_id}",
        )

        await message.answer(text, parse_mode="HTML", reply_markup=back_kb.as_markup())
        logger.info(f"Payme integration configured for store {store_id}")

    except Exception as e:
        logger.error(f"Failed to save Payme integration: {e}")
        await message.answer("Ошибка сохранения" if lang == "ru" else "Saqlashda xatolik")


@router.callback_query(F.data.startswith("store_click_view_"))
async def view_click_integration(callback: types.CallbackQuery) -> None:
    """View Click integration details."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    store_id = int(callback.data.replace("store_click_view_", ""))

    # Verify store ownership
    if not verify_store_owner(callback.from_user.id, store_id):
        await callback.answer("Нет доступа" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    try:
        integration = db.get_store_payment_integration(store_id, "click")
        if not integration:
            await callback.answer("Integration not found", show_alert=True)
            return

        merchant_id = integration.get("merchant_id", "")
        masked_merchant = (
            merchant_id[:4] + "****" + merchant_id[-2:] if len(merchant_id) > 6 else "****"
        )

        text = (
            f"<b>Click подключён</b>\n\n"
            f"Merchant ID: <code>{masked_merchant}</code>\n"
            f"Service ID: настроен\n\n"
            f"Покупатели могут оплачивать через Click."
            if lang == "ru"
            else f"<b>Click ulangan</b>\n\n"
            f"Merchant ID: <code>{masked_merchant}</code>\n"
            f"Service ID: sozlangan\n\n"
            f"Xaridorlar Click orqali to'lashi mumkin."
        )

        builder = InlineKeyboardBuilder()
        builder.button(
            text="Отключить" if lang == "ru" else "O'chirish",
            callback_data=f"store_click_disable_{store_id}",
        )
        builder.button(
            text="Назад" if lang == "ru" else "Orqaga",
            callback_data=f"store_payment_settings_{store_id}",
        )
        builder.adjust(1)

        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error viewing Click integration: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("store_payme_view_"))
async def view_payme_integration(callback: types.CallbackQuery) -> None:
    """View Payme integration details."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    store_id = int(callback.data.replace("store_payme_view_", ""))

    # Verify store ownership
    if not verify_store_owner(callback.from_user.id, store_id):
        await callback.answer("Нет доступа" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    try:
        integration = db.get_store_payment_integration(store_id, "payme")
        if not integration:
            await callback.answer("Integration not found", show_alert=True)
            return

        merchant_id = integration.get("merchant_id", "")
        masked_merchant = (
            merchant_id[:4] + "****" + merchant_id[-2:] if len(merchant_id) > 6 else "****"
        )

        text = (
            f"<b>Payme подключён</b>\n\n"
            f"Merchant ID: <code>{masked_merchant}</code>\n\n"
            f"Покупатели могут оплачивать через Payme."
            if lang == "ru"
            else f"<b>Payme ulangan</b>\n\n"
            f"Merchant ID: <code>{masked_merchant}</code>\n\n"
            f"Xaridorlar Payme orqali to'lashi mumkin."
        )

        builder = InlineKeyboardBuilder()
        builder.button(
            text="Отключить" if lang == "ru" else "O'chirish",
            callback_data=f"store_payme_disable_{store_id}",
        )
        builder.button(
            text="Назад" if lang == "ru" else "Orqaga",
            callback_data=f"store_payment_settings_{store_id}",
        )
        builder.adjust(1)

        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error viewing Payme integration: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("store_click_disable_"))
async def disable_click_integration(callback: types.CallbackQuery) -> None:
    """Disable Click integration."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    store_id = int(callback.data.replace("store_click_disable_", ""))

    # Verify store ownership
    if not verify_store_owner(callback.from_user.id, store_id):
        await callback.answer("Нет доступа" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    try:
        db.disable_store_payment_integration(store_id, "click")
        await callback.answer("Click отключён" if lang == "ru" else "Click o'chirildi")

        # Return to payment settings
        integrations = db.get_store_payment_integrations(store_id)
        text = (
            "<b>Настройки онлайн оплаты</b>\n\nClick был отключён."
            if lang == "ru"
            else "<b>Onlayn to'lov sozlamalari</b>\n\nClick o'chirildi."
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=payment_settings_keyboard(store_id, lang, integrations),
        )
        logger.info(f"Click integration disabled for store {store_id}")
    except Exception as e:
        logger.error(f"Error disabling Click: {e}")
        await callback.answer("Error", show_alert=True)


@router.callback_query(F.data.startswith("store_payme_disable_"))
async def disable_payme_integration(callback: types.CallbackQuery) -> None:
    """Disable Payme integration."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    store_id = int(callback.data.replace("store_payme_disable_", ""))

    # Verify store ownership
    if not verify_store_owner(callback.from_user.id, store_id):
        await callback.answer("Нет доступа" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    try:
        db.disable_store_payment_integration(store_id, "payme")
        await callback.answer("Payme отключён" if lang == "ru" else "Payme o'chirildi")

        # Return to payment settings
        integrations = db.get_store_payment_integrations(store_id)
        text = (
            "<b>Настройки онлайн оплаты</b>\n\nPayme был отключён."
            if lang == "ru"
            else "<b>Onlayn to'lov sozlamalari</b>\n\nPayme o'chirildi."
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=payment_settings_keyboard(store_id, lang, integrations),
        )
        logger.info(f"Payme integration disabled for store {store_id}")
    except Exception as e:
        logger.error(f"Error disabling Payme: {e}")
        await callback.answer("Error", show_alert=True)


# ===================== STORE ADMINS MANAGEMENT =====================


def store_admins_keyboard(
    store_id: int, admins: list, lang: str = "ru"
) -> types.InlineKeyboardMarkup:
    """Keyboard for store admins management."""
    builder = InlineKeyboardBuilder()

    # Show current admins with remove button
    for admin in admins:
        user_id = admin.get("user_id")
        name = admin.get("first_name") or admin.get("username") or f"ID:{user_id}"
        remove_text = "Удалить" if lang == "ru" else "O'chirish"
        builder.button(
            text=f"{remove_text} {name}",
            callback_data=f"remove_admin_{store_id}_{user_id}",
        )

    # Add admin button
    add_text = "Добавить сотрудника" if lang == "ru" else "Xodim qo'shish"
    builder.button(text=add_text, callback_data=f"add_admin_{store_id}")

    # Back button
    back_text = "Назад" if lang == "ru" else "Orqaga"
    builder.button(text=back_text, callback_data="my_store_settings")

    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data.startswith("store_admins_"))
async def show_store_admins(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Show store admins management."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    assert callback.data is not None
    lang = db.get_user_language(callback.from_user.id)

    await state.clear()

    store_id = int(callback.data.replace("store_admins_", ""))

    # Check if user is owner
    stores = db.get_user_accessible_stores(callback.from_user.id)
    if not any(s.get("store_id") == store_id for s in stores):
        await callback.answer("Доступ запрещён" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    # Get store admins
    admins = []
    if hasattr(db, "get_store_admins"):
        admins = db.get_store_admins(store_id)

    admin_count = len(admins)

    if lang == "ru":
        hint = (
            "Нажмите на сотрудника чтобы удалить."
            if admins
            else "Добавьте сотрудников чтобы они могли управлять магазином."
        )
        text = f"<b>Сотрудники магазина</b>\n\nВсего сотрудников: <b>{admin_count}</b>\n\n{hint}"
    else:
        hint = (
            "Xodimni oʻchirish uchun ustiga bosing."
            if admins
            else "Xodimlar qoʻshing, ular doʻkonni boshqarishlari mumkin."
        )
        text = f"<b>Doʻkon xodimlari</b>\n\nJami xodimlar: <b>{admin_count}</b>\n\n{hint}"

    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=store_admins_keyboard(store_id, admins, lang),
        )
    except Exception:
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=store_admins_keyboard(store_id, admins, lang),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("add_admin_"))
async def start_add_admin(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start adding a new admin."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    assert callback.data is not None
    lang = db.get_user_language(callback.from_user.id)

    store_id = int(callback.data.replace("add_admin_", ""))

    # Verify store ownership
    if not verify_store_owner(callback.from_user.id, store_id):
        await callback.answer("Нет доступа" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    await state.update_data(store_id=store_id)
    await state.set_state(StoreSettingsStates.waiting_admin_contact)

    text = (
        "<b>Добавление сотрудника</b>\n\n"
        "Перешлите любое сообщение от пользователя, которого хотите добавить.\n\n"
        "Или отправьте его контакт."
        if lang == "ru"
        else "<b>Xodim qo'shish</b>\n\n"
        "Qo'shmoqchi bo'lgan foydalanuvchidan biror xabarni yo'naltiring.\n\n"
        "Yoki uning kontaktini yuboring."
    )

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(
        text="Отмена" if lang == "ru" else "Bekor qilish",
        callback_data=f"store_admins_{store_id}",
    )

    try:
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=cancel_kb.as_markup()
        )
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=cancel_kb.as_markup())

    await callback.answer()


@router.message(
    StoreSettingsStates.waiting_admin_contact,
    F.forward_from | F.contact | ~F.text.startswith("/"),
)
async def process_admin_contact(message: types.Message, state: FSMContext) -> None:
    """Process forwarded message or contact to add admin."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    data = await state.get_data()
    store_id = data.get("store_id")

    if not store_id:
        await state.clear()
        await message.answer("Error: store not found")
        return

    new_admin_id = None
    new_admin_name = None

    # Check if it's a forwarded message
    if message.forward_from:
        new_admin_id = message.forward_from.id
        new_admin_name = message.forward_from.first_name or message.forward_from.username

    # Check if it's a contact
    elif message.contact:
        new_admin_id = message.contact.user_id
        new_admin_name = message.contact.first_name

    if not new_admin_id:
        error_text = (
            "Не удалось определить пользователя.\n\n"
            "Перешлите сообщение от пользователя или отправьте его контакт."
            if lang == "ru"
            else "Foydalanuvchini aniqlab bo'lmadi.\n\n"
            "Foydalanuvchidan xabar yo'naltiring yoki kontaktini yuboring."
        )
        await message.answer(error_text)
        return

    # Check if user exists in database
    user = db.get_user(new_admin_id)
    if not user:
        # Create user
        db.add_user(user_id=new_admin_id, first_name=new_admin_name or "User")

    # Add admin
    try:
        if hasattr(db, "add_store_admin"):
            success = db.add_store_admin(store_id, new_admin_id, message.from_user.id)
            if success:
                await state.clear()

                success_text = (
                    f"<b>Сотрудник добавлен</b>\n\n"
                    f"{new_admin_name or new_admin_id}\n\n"
                    f"Теперь этот пользователь может управлять магазином."
                    if lang == "ru"
                    else f"<b>Xodim qo'shildi</b>\n\n"
                    f"{new_admin_name or new_admin_id}\n\n"
                    f"Endi bu foydalanuvchi do'konni boshqarishi mumkin."
                )

                # Notify the new admin
                try:
                    stores = db.get_user_accessible_stores(message.from_user.id)
                    store = next((s for s in stores if s.get("store_id") == store_id), None)
                    store_name = store.get("name", "Магазин") if store else "Магазин"

                    notify_text = (
                        f"<b>Вы добавлены как сотрудник</b>\n\n"
                        f"Магазин: <b>{store_name}</b>\n\n"
                        f"Теперь вы можете управлять товарами и заказами этого магазина."
                        if lang == "ru"
                        else f"<b>Siz xodim sifatida qo'shildingiz</b>\n\n"
                        f"Do'kon: <b>{store_name}</b>\n\n"
                        f"Endi siz bu do'konning mahsulotlari va buyurtmalarini boshqarishingiz mumkin."
                    )
                    await bot.send_message(new_admin_id, notify_text, parse_mode="HTML")
                except Exception as e:
                    logger.warning(f"Failed to notify new admin: {e}")

                back_kb = InlineKeyboardBuilder()
                back_kb.button(
                    text="К сотрудникам" if lang == "ru" else "Xodimlarga",
                    callback_data=f"store_admins_{store_id}",
                )

                await message.answer(
                    success_text, parse_mode="HTML", reply_markup=back_kb.as_markup()
                )
                logger.info(
                    f"Admin {new_admin_id} added to store {store_id} by {message.from_user.id}"
                )
            else:
                await message.answer(
                    "Не удалось добавить сотрудника"
                    if lang == "ru"
                    else "Xodim qo'shib bo'lmadi"
                )
        else:
            await message.answer("Feature not available")

    except Exception as e:
        logger.error(f"Error adding admin: {e}")
        await message.answer("Ошибка" if lang == "ru" else "Xatolik")


@router.callback_query(F.data.startswith("remove_admin_"))
async def remove_admin(callback: types.CallbackQuery) -> None:
    """Remove an admin from store."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    assert callback.data is not None
    lang = db.get_user_language(callback.from_user.id)

    # Parse: remove_admin_{store_id}_{user_id}
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Error", show_alert=True)
        return

    store_id = int(parts[2])
    admin_user_id = int(parts[3])

    # Check if user is owner
    stores = db.get_user_accessible_stores(callback.from_user.id)
    if not any(s.get("store_id") == store_id for s in stores):
        await callback.answer("Доступ запрещён" if lang == "ru" else "Ruxsat yo'q", show_alert=True)
        return

    try:
        if hasattr(db, "remove_store_admin"):
            db.remove_store_admin(store_id, admin_user_id)

            await callback.answer(
                "Сотрудник удалён" if lang == "ru" else "Xodim o'chirildi"
            )

            # Refresh admins list
            admins = db.get_store_admins(store_id) if hasattr(db, "get_store_admins") else []

            admin_count = len(admins)
            if lang == "ru":
                hint = "Нажмите на сотрудника чтобы удалить." if admins else "Добавьте сотрудников."
                text = f"<b>Сотрудники магазина</b>\n\nВсего сотрудников: <b>{admin_count}</b>\n\n{hint}"
            else:
                hint = "Xodimni oʻchirish uchun ustiga bosing." if admins else "Xodimlar qoʻshing."
                text = (
                    f"<b>Doʻkon xodimlari</b>\n\nJami xodimlar: <b>{admin_count}</b>\n\n{hint}"
                )

            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=store_admins_keyboard(store_id, admins, lang),
            )

            logger.info(
                f"Admin {admin_user_id} removed from store {store_id} by {callback.from_user.id}"
            )

    except Exception as e:
        logger.error(f"Error removing admin: {e}")
        await callback.answer("Ошибка" if lang == "ru" else "Xatolik", show_alert=True)
