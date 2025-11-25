"""
User command handlers (start, language selection, city selection, cancel actions).
"""
from typing import Optional, Any, Callable
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database_protocol import DatabaseProtocol
from localization import get_text, get_cities
from app.keyboards import city_keyboard, main_menu_seller, main_menu_customer, language_keyboard, phone_request_keyboard
from handlers.common.utils import user_view_mode, has_approved_store
from handlers.common.states import Registration

router = Router(name='commands')


@router.message(F.text.in_([get_text('ru', 'my_city'), get_text('uz', 'my_city')]))
async def change_city(message: types.Message, state: Optional[FSMContext] = None, db: DatabaseProtocol = None):
    if not db:
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
        stats_text = f"\n\n📊 В вашем городе:\n🏪 Магазинов: {stores_count}\n🍽 Предложений: {offers_count}"
    except:
        pass
    
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✏️ Изменить город" if lang == 'ru' else "✏️ Shaharni o'zgartirish",
        callback_data="change_city"
    )
    builder.button(
        text="◀️ Назад" if lang == 'ru' else "◀️ Orqaga",
        callback_data="back_to_menu"
    )
    builder.adjust(1)
    
    await message.answer(
        f"{get_text(lang, 'your_city')}: {current_city}{stats_text}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "change_city")
async def show_city_selection(callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol):
    """Show list of cities for selection."""
    lang = db.get_user_language(callback.from_user.id)
    await callback.message.edit_text(
        get_text(lang, 'choose_city'),
        reply_markup=city_keyboard(lang)
    )


@router.callback_query(F.data == "back_to_menu")
async def back_to_main_menu(callback: types.CallbackQuery, db: DatabaseProtocol):
    """Return to main menu."""
    lang = db.get_user_language(callback.from_user.id)
    user = db.get_user_model(callback.from_user.id)
    user_role = user.role if user else 'customer'
    
    if user_view_mode is not None and user_role == 'seller':
        if callback.from_user.id not in user_view_mode:
            user_view_mode[callback.from_user.id] = 'seller'
    
    menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)
    
    await callback.message.delete()
    await callback.message.answer(
        get_text(lang, 'main_menu') if 'main_menu' in dir() else "Главное меню",
        reply_markup=menu
    )
    await callback.answer()


@router.message(F.text.in_(get_cities('ru') + get_cities('uz')))
async def change_city_text(message: types.Message, state: Optional[FSMContext] = None, db: DatabaseProtocol = None):
    """Quick city change handler (without FSM state)."""
    if not db:
        return
    
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    user = db.get_user_model(user_id)
    new_city = message.text
    
    db.update_user_city(user_id, new_city)
    
    user_role = user.role or 'customer' if user else 'customer'
    menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)
    
    await message.answer(
        f"✅ Город изменён на <b>{new_city}</b>" if lang == 'ru' else f"✅ Shahar <b>{new_city}</b>ga o'zgartirildi",
        parse_mode="HTML",
        reply_markup=menu
    )


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    user = db.get_user_model(message.from_user.id)
    
    if not user:
        await message.answer(
            get_text('ru', 'welcome'),
            parse_mode="HTML"
        )
        await message.answer(
            get_text('ru', 'choose_language'),
            reply_markup=language_keyboard()
        )
        return
    
    lang = db.get_user_language(message.from_user.id)
    user_phone = user.phone
    user_city = user.city
    user_role = user.role or 'customer'
    
    if not user_phone:
        await message.answer(
            get_text(lang, 'welcome_phone_step'),
            parse_mode="HTML",
            reply_markup=phone_request_keyboard(lang)
        )
        await state.set_state(Registration.phone)
        return
    
    if user_view_mode is not None and user_role == 'seller':
        user_view_mode[message.from_user.id] = 'seller'
    
    menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)
    await message.answer(
        get_text(lang, 'welcome_back', name=message.from_user.first_name, city=user_city or 'Ташкент'),
        parse_mode="HTML",
        reply_markup=menu
    )


@router.callback_query(F.data.startswith("lang_"))
async def choose_language(callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol):
    lang = callback.data.split("_")[1]
    user = db.get_user_model(callback.from_user.id)
    
    if not user:
        db.add_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
        db.update_user_language(callback.from_user.id, lang)
        await callback.message.edit_text(get_text(lang, 'language_changed'))
        await callback.message.answer(
            get_text(lang, 'welcome_phone_step'),
            parse_mode="HTML",
            reply_markup=phone_request_keyboard(lang)
        )
        await state.set_state(Registration.phone)
        return
    
    db.update_user_language(callback.from_user.id, lang)
    await callback.message.edit_text(get_text(lang, 'language_changed'))
    
    user_phone = user.phone
    user_city = user.city
    
    if not user_phone:
        await callback.message.answer(
            get_text(lang, 'welcome_phone_step'),
            parse_mode="HTML",
            reply_markup=phone_request_keyboard(lang)
        )
        await state.set_state(Registration.phone)
        return
    
    user_role = user.role or 'customer'
    menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)
    await callback.message.answer(
        get_text(lang, 'welcome_back', name=callback.from_user.first_name, city=user_city or 'Ташкент'),
        parse_mode="HTML",
        reply_markup=menu
    )


@router.message(F.text.contains("Отмена") | F.text.contains("Bekor qilish"))
async def cancel_action(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    lang = db.get_user_language(message.from_user.id)
    current_state = await state.get_state()
    
    if current_state in ['Registration:phone', 'Registration:city']:
        user = db.get_user_model(message.from_user.id)
        user_phone = user.phone if user else None
        if not user or not user_phone:
            await message.answer(
                "❌ Регистрация обязательна для использования бота.\n\n"
                "📱 Пожалуйста, поделитесь номером телефона.",
                reply_markup=phone_request_keyboard(lang)
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
    role = user.role if user else 'customer'
    
    if current_state and str(current_state).startswith("RegisterStore"):
        await message.answer(
            get_text(lang, 'operation_cancelled'),
            reply_markup=main_menu_customer(lang)
        )
        return
    
    if role == "seller":
        if not has_approved_store(message.from_user.id, db):
            role = "customer"
            preferred_menu = "customer"
    
    view_override = user_view_mode.get(message.from_user.id)
    target = preferred_menu or view_override or ("seller" if role == "seller" else "customer")
    menu = main_menu_seller(lang) if target == "seller" else main_menu_customer(lang)

    await message.answer(
        get_text(lang, 'operation_cancelled'),
        reply_markup=menu
    )


@router.callback_query(F.data == "cancel_offer")
async def cancel_offer_callback(callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol):
    """Handler for offer creation cancel button."""
    lang = db.get_user_language(callback.from_user.id)
    await state.clear()
    
    await callback.message.edit_text(
        f"❌ {'Создание товара отменено' if lang == 'ru' else 'Mahsulot yaratish bekor qilindi'}",
        parse_mode="HTML"
    )
    
    await callback.message.answer(
        get_text(lang, 'operation_cancelled'),
        reply_markup=main_menu_seller(lang)
    )
    
    await callback.answer()


@router.message(Command("mybookings"))
async def my_bookings_command(message: types.Message, db: DatabaseProtocol = None):
    """Show ALL user bookings with cancel buttons - for debugging stuck bookings."""
    if not db:
        return
    
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    
    # Get ALL bookings (not just active)
    bookings = db.get_user_bookings(user_id) or []
    
    if not bookings:
        await message.answer(
            "📋 У вас нет бронирований.\n\n/mybookings - проверить брони"
            if lang == "ru" else
            "📋 Sizda bronlar yo'q.\n\n/mybookings - bronlarni tekshirish"
        )
        return
    
    # Count by status
    status_counts = {}
    for b in bookings:
        status = b.get('status') if isinstance(b, dict) else 'unknown'
        status_counts[status] = status_counts.get(status, 0) + 1
    
    text = f"📋 <b>Все ваши бронирования ({len(bookings)})</b>\n\n"
    text += f"Статусы: {status_counts}\n\n"
    
    builder = InlineKeyboardBuilder()
    
    for b in bookings[:10]:  # Max 10
        if isinstance(b, dict):
            booking_id = b.get('booking_id')
            status = b.get('status', 'unknown')
            title = b.get('title', 'Товар')[:20]
            
            status_emoji = {
                'pending': '⏳',
                'confirmed': '✅', 
                'active': '🔵',
                'completed': '✔️',
                'cancelled': '❌'
            }.get(status, '❓')
            
            text += f"{status_emoji} #{booking_id} | {status} | {title}\n"
            
            # Add cancel button for non-completed/cancelled bookings
            if status not in ['completed', 'cancelled']:
                builder.button(
                    text=f"❌ Отменить #{booking_id}",
                    callback_data=f"force_cancel_{booking_id}"
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
    lang = db.get_user_language(user_id)
    
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
    
    booking_user_id = booking.get('user_id') if isinstance(booking, dict) else booking[2]
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
            except:
                pass
        
        # Get updated bookings count
        bookings = db.get_user_bookings(user_id) or []
        active = [b for b in bookings if isinstance(b, dict) and b.get('status') in ('pending', 'confirmed', 'active')]
        await callback.message.answer(f"✅ Отменено! Активных броней: {len(active)}\n\n/mybookings - посмотреть все")
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
                (user_id,)
            )
            all_bookings = cursor.fetchall()
            
            text = f"📊 <b>Ваши бронирования (user_id: {user_id})</b>\n\n"
            
            if all_bookings:
                for b in all_bookings:
                    bid, status = b[0], b[1]
                    emoji = {'pending': '⏳', 'confirmed': '✅', 'active': '🔵', 
                             'completed': '✔️', 'cancelled': '❌'}.get(status, '❓')
                    text += f"{emoji} #{bid} - <code>{status}</code>\n"
            else:
                text += "📭 Нет бронирований\n"
            
            # Now cancel all active ones
            cursor.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE user_id = %s AND status IN ('active', 'pending', 'confirmed') RETURNING booking_id",
                (user_id,)
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
            cursor.execute("""
                SELECT booking_id, status, offer_id, quantity, created_at 
                FROM bookings 
                WHERE user_id = %s 
                ORDER BY booking_id DESC
            """, (user_id,))
            all_bookings = cursor.fetchall()
            
            # Count active bookings
            cursor.execute("""
                SELECT COUNT(*) 
                FROM bookings 
                WHERE user_id = %s AND status IN ('active', 'pending', 'confirmed')
            """, (user_id,))
            active_count = cursor.fetchone()[0]
            
            text = f"🔍 <b>Диагностика базы данных</b>\n\n"
            text += f"👤 User ID: <code>{user_id}</code>\n"
            text += f"📊 Всего бронирований: {len(all_bookings)}\n"
            text += f"⚡ Активных (pending/confirmed/active): <b>{active_count}</b>\n\n"
            
            if all_bookings:
                text += "<b>Все брони:</b>\n"
                for b in all_bookings[:15]:  # Max 15
                    bid, status, offer_id, qty, created = b
                    emoji = {'pending': '⏳', 'confirmed': '✅', 'active': '🔵', 
                             'completed': '✔️', 'cancelled': '❌'}.get(status, '❓')
                    text += f"{emoji} #{bid} | <code>{status}</code> | offer:{offer_id}\n"
            else:
                text += "📭 Нет бронирований в базе\n"
            
            text += f"\n💡 Лимит: {active_count}/3"
            if active_count >= 3:
                text += " (⚠️ ДОСТИГНУТ)"
            
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

