"""
Mode switching handlers - customer/seller mode toggle.
"""
import logging
from typing import Any

from aiogram import F, Router, types

from app.core.utils import get_field
from handlers.common.utils import set_user_view_mode

logger = logging.getLogger(__name__)

router = Router(name="mode_switch")

# Module-level dependencies
db: Any = None
bot: Any = None
get_text: Any = None
main_menu_customer: Any = None
main_menu_seller: Any = None
booking_filters_keyboard: Any = None


def setup(
    bot_instance: Any,
    db_instance: Any,
    user_view_mode_dict: Any = None,  # Deprecated parameter, ignored
    get_text_func: Any = None,
    main_menu_func: Any = None,
    booking_filters_kb: Any = None,
    main_menu_seller_func: Any = None,
) -> None:
    """Initialize module with bot and database instances."""
    global bot, db, get_text, main_menu_customer, main_menu_seller, booking_filters_keyboard
    bot = bot_instance
    db = db_instance
    get_text = get_text_func
    main_menu_customer = main_menu_func
    main_menu_seller = main_menu_seller_func
    booking_filters_keyboard = booking_filters_kb


@router.message(
    F.text.in_(["📦 Мои заказы", "📦 Mening buyurtmalarim", "📋 Мои заказы", "📋 Buyurtmalarim"])
)
async def my_orders_handler(message: types.Message) -> None:
    """Handler for Orders button - show user's bookings and orders."""
    if not db or not booking_filters_keyboard:
        await message.answer("System error")
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    bookings = db.get_user_bookings(user_id)

    try:
        orders = db.get_user_orders(user_id)
    except Exception:
        orders = []

    if not bookings and not orders:
        empty_title = "У вас пока нет заказов" if lang == "ru" else "Sizda hali buyurtmalar yo'q"
        empty_desc = (
            "Попробуйте раздел Горячее — там товары с лучшими скидками"
            if lang == "ru"
            else "Issiq bo'limini sinab ko'ring — u yerda eng yaxshi chegirmalar"
        )
        text = f"<b>{empty_title}</b>\n\n{empty_desc}"
        await message.answer(text, parse_mode="HTML")
        return

    active_bookings = [b for b in bookings if get_field(b, "status", 3) in ("pending", "confirmed")]
    completed_bookings = [b for b in bookings if get_field(b, "status", 3) == "completed"]
    cancelled_bookings = [b for b in bookings if get_field(b, "status", 3) == "cancelled"]

    active_orders = [
        o
        for o in orders
        if get_field(o, "order_status", 10) in ["pending", "confirmed", "preparing", "delivering"]
    ]
    completed_orders = [o for o in orders if get_field(o, "order_status", 10) == "completed"]
    cancelled_orders = [o for o in orders if get_field(o, "order_status", 10) == "cancelled"]

    text = f"📦 <b>{'Мои заказы' if lang == 'ru' else 'Mening buyurtmalarim'}</b>\n\n"

    if bookings:
        text += f"<b>{'Самовывоз' if lang == 'ru' else 'Olib ketish'}</b>\n"
        text += f"• {'Активные' if lang == 'ru' else 'Faol'} ({len(active_bookings)})\n"
        text += (
            f"• {'Завершённые' if lang == 'ru' else 'Yakunlangan'} ({len(completed_bookings)})\n"
        )
        text += f"• {'Отменённые' if lang == 'ru' else 'Bekor qilingan'} ({len(cancelled_bookings)})\n\n"

    if orders:
        text += f"<b>{'Доставка' if lang == 'ru' else 'Yetkazib berish'}</b>\n"
        text += f"• {'Активные' if lang == 'ru' else 'Faol'} ({len(active_orders)})\n"
        text += f"• {'Завершённые' if lang == 'ru' else 'Yakunlangan'} ({len(completed_orders)})\n"
        text += f"• {'Отменённые' if lang == 'ru' else 'Bekor qilingan'} ({len(cancelled_orders)})"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=booking_filters_keyboard(
            lang,
            len(active_bookings) + len(active_orders),
            len(completed_bookings) + len(completed_orders),
            len(cancelled_bookings) + len(cancelled_orders),
        ),
    )


@router.message(F.text.contains("Режим покупателя") | F.text.contains("Xaridor rejimi"))
async def switch_to_customer(message: types.Message):
    """Switch user to customer mode."""
    if not db or not get_text or not main_menu_customer:
        logger.error("❌ switch_to_customer: dependencies not initialized!")
        await message.answer("System error: dependencies not initialized")
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    logger.info(f"🔄 User {user_id} switching to customer mode")

    set_user_view_mode(user_id, "customer", db)

    await message.answer(
        get_text(lang, "switched_to_customer"), reply_markup=main_menu_customer(lang)
    )

    logger.info(f"✅ User {user_id} switched to customer mode successfully")


@router.message(F.text.contains("Режим партнера") | F.text.contains("Hamkor rejimi"))
async def switch_to_seller(message: types.Message):
    """Switch user to seller mode."""
    if not db or not get_text or not main_menu_seller:
        logger.error("❌ switch_to_seller: dependencies not initialized!")
        await message.answer("System error: dependencies not initialized")
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    user = db.get_user_model(user_id)
    if not user or user.role != "seller":
        await message.answer(
            "Только партнеры могут использовать этот режим"
            if lang == "ru"
            else "Faqat hamkorlar bu rejimdan foydalanishlari mumkin"
        )
        return

    logger.info(f"🔄 User {user_id} switching to seller mode")

    set_user_view_mode(user_id, "seller", db)

    await message.answer(
        "Переключено в режим партнера" if lang == "ru" else "Hamkor rejimiga o'tkazildi",
        reply_markup=main_menu_seller(lang),
    )

    logger.info(f"✅ User {user_id} switched to seller mode successfully")
