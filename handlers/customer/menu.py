"""
Mode switching handlers - customer/seller mode toggle.
"""
import logging
from typing import Any

from aiogram import F, Router, types

from handlers.common.utils import is_customer_menu_button, set_user_view_mode

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


# NOTE: "Мои заказы" handler moved to handlers/customer/orders/my_orders.py for better UX
# This module now only handles mode switching (customer/seller)


@router.message(F.text.func(is_customer_menu_button))
async def switch_to_customer(message: types.Message):
    """Switch user to customer mode."""
    if not db or not get_text or not main_menu_customer:
        logger.error("switch_to_customer: dependencies not initialized!")
        lang_code = (message.from_user.language_code or "ru") if message.from_user else "ru"
        if lang_code.startswith("uz"):
            text = "Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring."
        else:
            text = "Сервис временно недоступен. Попробуйте позже."
        await message.answer(text)
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    user = db.get_user_model(user_id)
    user_role = getattr(user, "role", "customer") if user else "customer"
    if user_role == "store_owner":
        user_role = "seller"
    if user_role == "seller":
        if not main_menu_seller:
            await message.answer(get_text(lang, "customer_mode_disabled"))
            return
        await message.answer(
            get_text(lang, "customer_mode_disabled"),
            reply_markup=main_menu_seller(lang),
        )
        return

    logger.info(f"User {user_id} switching to customer mode")

    set_user_view_mode(user_id, "customer", db)

    await message.answer(
        get_text(lang, "switched_to_customer"), reply_markup=main_menu_customer(lang)
    )

    logger.info(f"User {user_id} switched to customer mode successfully")
