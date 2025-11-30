"""Store settings handlers - photo upload, store info management."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database_protocol import DatabaseProtocol
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router(name="store_settings")


class StoreSettingsStates(StatesGroup):
    """States for store settings."""

    waiting_photo = State()


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


def store_settings_keyboard(
    store_id: int, lang: str = "ru", has_photo: bool = False
) -> types.InlineKeyboardMarkup:
    """Store settings keyboard."""
    builder = InlineKeyboardBuilder()

    if has_photo:
        photo_text = "📸 Изменить фото" if lang == "ru" else "📸 Rasmni o'zgartirish"
        remove_photo_text = "🗑 Удалить фото" if lang == "ru" else "🗑 Rasmni o'chirish"
        builder.button(text=photo_text, callback_data=f"store_change_photo_{store_id}")
        builder.button(text=remove_photo_text, callback_data=f"store_remove_photo_{store_id}")
    else:
        photo_text = "📸 Добавить фото" if lang == "ru" else "📸 Rasm qo'shish"
        builder.button(text=photo_text, callback_data=f"store_change_photo_{store_id}")

    back_text = "◀️ Назад" if lang == "ru" else "◀️ Orqaga"
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

    # Get user's store
    stores = db.get_user_stores(callback.from_user.id)
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

    text = (
        f"⚙️ <b>Настройки магазина</b>\n\n"
        f"🏪 <b>{store_name}</b>\n\n"
        f"📸 Фото: {'✅ Загружено' if has_photo else '❌ Не загружено'}"
        if lang == "ru"
        else f"⚙️ <b>Do'kon sozlamalari</b>\n\n"
        f"🏪 <b>{store_name}</b>\n\n"
        f"📸 Rasm: {'✅ Yuklangan' if has_photo else '❌ Yuklanmagan'}"
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
                reply_markup=store_settings_keyboard(store_id, lang, has_photo),
            )
        except Exception:
            await bot.send_message(
                callback.from_user.id,
                text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(store_id, lang, has_photo),
            )
    else:
        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(store_id, lang, has_photo),
            )
        except Exception:
            await callback.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(store_id, lang, has_photo),
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
    await state.update_data(store_id=store_id)
    await state.set_state(StoreSettingsStates.waiting_photo)

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(
        text="❌ Отмена" if lang == "ru" else "❌ Bekor qilish", callback_data="store_photo_cancel"
    )

    text = (
        "📸 <b>Загрузка фото магазина</b>\n\n"
        "Отправьте фото вашего магазина или витрины.\n"
        "Это поможет покупателям узнать ваш магазин!"
        if lang == "ru"
        else "📸 <b>Do'kon fotosuratini yuklash</b>\n\n"
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
            "✅ <b>Фото магазина обновлено!</b>\n\n" "Теперь покупатели смогут видеть ваш магазин."
            if lang == "ru"
            else "✅ <b>Do'kon rasmi yangilandi!</b>\n\n"
            "Endi xaridorlar do'koningizni ko'rishlari mumkin."
        )

        # Show updated photo with back button
        back_kb = InlineKeyboardBuilder()
        back_kb.button(
            text="⚙️ Настройки магазина" if lang == "ru" else "⚙️ Do'kon sozlamalari",
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
            "❌ Ошибка при загрузке фото" if lang == "ru" else "❌ Rasm yuklashda xatolik"
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
    stores = db.get_user_stores(callback.from_user.id)
    active_stores = [s for s in stores if s.get("status") in ("active", "approved")]

    if active_stores:
        store = active_stores[0]
        store_id = store.get("store_id")
        store_name = store.get("name", "Магазин")
        has_photo = bool(store.get("photo"))

        text = (
            f"⚙️ <b>Настройки магазина</b>\n\n"
            f"🏪 <b>{store_name}</b>\n\n"
            f"📸 Фото: {'✅ Загружено' if has_photo else '❌ Не загружено'}"
            if lang == "ru"
            else f"⚙️ <b>Do'kon sozlamalari</b>\n\n"
            f"🏪 <b>{store_name}</b>\n\n"
            f"📸 Rasm: {'✅ Yuklangan' if has_photo else '❌ Yuklanmagan'}"
        )

        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(store_id, lang, has_photo),
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

    try:
        db.update_store_photo(store_id, None)

        # Show updated settings
        stores = db.get_user_stores(callback.from_user.id)
        active_stores = [s for s in stores if s.get("status") in ("active", "approved")]

        if active_stores:
            store = active_stores[0]
            store_name = store.get("name", "Магазин")

            text = (
                f"⚙️ <b>Настройки магазина</b>\n\n"
                f"🏪 <b>{store_name}</b>\n\n"
                f"📸 Фото: ❌ Не загружено\n\n"
                f"✅ Фото удалено"
                if lang == "ru"
                else f"⚙️ <b>Do'kon sozlamalari</b>\n\n"
                f"🏪 <b>{store_name}</b>\n\n"
                f"📸 Rasm: ❌ Yuklanmagan\n\n"
                f"✅ Rasm o'chirildi"
            )

            try:
                await callback.message.delete()
            except Exception:
                pass

            await bot.send_message(
                callback.from_user.id,
                text,
                parse_mode="HTML",
                reply_markup=store_settings_keyboard(store_id, lang, False),
            )

        await callback.answer("✅ Фото удалено" if lang == "ru" else "✅ Rasm o'chirildi")
        logger.info(f"Store {store_id} photo removed by user {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Failed to remove store photo: {e}")
        await callback.answer("❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True)


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
        "🏠 Главное меню" if lang == "ru" else "🏠 Asosiy menyu",
        reply_markup=main_menu_seller(lang),
    )

    await callback.answer()
