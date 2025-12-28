"""User-specific keyboards."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from localization import get_text


def main_menu_customer(lang: str = "ru", cart_count: int = 0) -> ReplyKeyboardMarkup:
    """Main menu for customers - optimized 5 buttons.

    Args:
        lang: Interface language
        cart_count: Number of items in cart (shown on button)
    """
    import logging
    
    # DEBUG: Check what lang parameter is passed
    logging.info(f"main_menu_customer called with lang={lang!r} (type: {type(lang).__name__})")
    
    # DEBUG: Test get_text() output
    hot_offers_text = get_text(lang, "hot_offers")
    logging.info(f"get_text(lang={lang!r}, 'hot_offers') returned: {hot_offers_text!r}")
    
    builder = ReplyKeyboardBuilder()

    # Row 1: Main action - Hot offers (merged with Establishments concept)
    builder.button(text=hot_offers_text)
    builder.button(text=get_text(lang, "search"))

    # Row 2: Cart with counter + My Orders
    cart_text = get_text(lang, "my_cart")
    if cart_count > 0:
        cart_text = f"{cart_text} ({cart_count})"
    builder.button(text=cart_text)
    builder.button(text=get_text(lang, "my_orders"))

    # Row 3: Profile
    builder.button(text=get_text(lang, "profile"))

    # 2x2x1 layout
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def search_cancel_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Keyboard for cancelling search."""
    builder = ReplyKeyboardBuilder()
    # get_text already returns "❌ Отмена" / "❌ Bekor qilish", no need to add emoji
    builder.button(text=get_text(lang, "cancel"))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def settings_keyboard(
    notifications_enabled: bool,
    lang: str = "ru",
    role: str | None = None,
    current_mode: str = "customer",
) -> InlineKeyboardMarkup:
    """Profile settings keyboard.

    Args:
        notifications_enabled: Whether notifications are enabled
        lang: Interface language
        role: User role ('seller' or 'customer')
        current_mode: Current viewing mode ('seller' or 'customer')
    """
    builder = InlineKeyboardBuilder()

    # For seller show mode switch based on current mode
    if role == "seller":
        if current_mode == "seller":
            # Currently in seller mode - show store settings button
            builder.button(
                text="⚙️ Настройки магазина" if lang == "ru" else "⚙️ Do'kon sozlamalari",
                callback_data="my_store_settings",
            )
            # Show switch to customer mode
            builder.button(
                text="🛒 Режим покупателя" if lang == "ru" else "🛒 Xaridor rejimi",
                callback_data="switch_to_customer",
            )
        else:
            # Currently in customer mode - show switch to seller
            builder.button(
                text="🏪 Режим партнера" if lang == "ru" else "🏪 Hamkor rejimi",
                callback_data="switch_to_seller",
            )
    else:
        # For customer show "Become partner"
        builder.button(text=get_text(lang, "become_partner"), callback_data="become_partner_cb")

    # Notifications
    notif_emoji = "🔔" if notifications_enabled else "🔕"
    notif_status = "Вкл" if notifications_enabled else "Выкл"
    notif_status_uz = "Yoqildi" if notifications_enabled else "O'chirildi"
    notif_text = (
        f"{notif_emoji} Уведомления: {notif_status}"
        if lang == "ru"
        else f"{notif_emoji} Bildirishnomalar: {notif_status_uz}"
    )
    builder.button(text=notif_text, callback_data="toggle_notifications")

    # Change city
    builder.button(
        text="📍 Сменить город" if lang == "ru" else "📍 Shaharni o'zgartirish",
        callback_data="profile_change_city",
    )

    # Change language
    builder.button(
        text="🌐 Изменить язык" if lang == "ru" else "🌐 Tilni o'zgartirish",
        callback_data="change_language",
    )

    # Delete account
    builder.button(
        text="❌ Удалить аккаунт" if lang == "ru" else "❌ Akkauntni o'chirish",
        callback_data="delete_account",
    )

    builder.adjust(1, 1, 1, 1, 1)
    return builder.as_markup()


def booking_filters_keyboard(
    lang: str = "ru", active: int = 0, completed: int = 0, cancelled: int = 0
) -> InlineKeyboardMarkup:
    """Booking filters keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=f"⏳ Активные ({active})", callback_data="bookings_active")
    builder.button(text=f"✅ Завершенные ({completed})", callback_data="bookings_completed")
    builder.button(text=f"❌ Отмененные ({cancelled})", callback_data="bookings_cancelled")
    builder.adjust(1)
    return builder.as_markup()


def booking_keyboard(booking_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Booking actions keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=get_text(lang, "cancel_booking"), callback_data=f"cancel_booking_{booking_id}"
    )
    return builder.as_markup()


def booking_rating_keyboard(booking_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Booking rating keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐⭐⭐⭐⭐", callback_data=f"rate_{booking_id}_5")
    builder.button(text="⭐⭐⭐⭐", callback_data=f"rate_{booking_id}_4")
    builder.button(text="⭐⭐⭐", callback_data=f"rate_{booking_id}_3")
    builder.button(text="⭐⭐", callback_data=f"rate_{booking_id}_2")
    builder.button(text="⭐", callback_data=f"rate_{booking_id}_1")
    builder.adjust(1)
    return builder.as_markup()


def business_type_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Business type selection keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "supermarkets"), callback_data="biztype_supermarket")
    builder.button(text=get_text(lang, "restaurants"), callback_data="biztype_restaurant")
    builder.button(text=get_text(lang, "bakeries"), callback_data="biztype_bakery")
    builder.button(text=get_text(lang, "cafes"), callback_data="biztype_cafe")
    builder.button(text=get_text(lang, "pharmacies"), callback_data="biztype_pharmacy")
    builder.adjust(2)
    return builder.as_markup()


def stores_list_keyboard(stores, lang: str = "ru") -> InlineKeyboardMarkup:
    """Stores list keyboard.

    Args:
        stores: List of store tuples. Structure depends on query:
               - From get_stores_by_category: [0]=store_id, [1]=name, [2]=address, [3]=category, [4]=city
               - From get_store/get_user_stores: [0]=store_id, [1]=owner_id, [2]=name, [3]=city, [4]=address, ...
    """
    builder = InlineKeyboardBuilder()
    for store in stores[:10]:
        if len(store) >= 3:
            if len(store) >= 5:
                # get_stores_by_category structure
                store_name = store[1] if len(store) > 1 else "Магазин"
                store_address = store[2] if len(store) > 2 else ""
            else:
                # get_user_stores structure
                store_name = store[2] if len(store) > 2 else "Магазин"
                store_address = store[4] if len(store) > 4 else ""
        else:
            store_name = "Магазин"
            store_address = ""

        store_id = store[0] if len(store) > 0 else 0

        if store_address:
            button_text = f"🏪 {store_name}\n📍 {store_address}"
        else:
            button_text = f"🏪 {store_name}"

        builder.button(text=button_text, callback_data=f"filter_store_{store_id}")

    builder.button(text=f"📋 {get_text(lang, 'available_offers')}", callback_data="filter_all")
    builder.adjust(1)
    return builder.as_markup()


def offers_category_filter(lang: str = "ru", store_id: int | None = None) -> InlineKeyboardMarkup:
    """Inline keyboard with offer category filters.

    Args:
        lang: Language code
        store_id: If provided, generates callbacks for store-specific filtering
    """
    from localization import get_product_categories

    builder = InlineKeyboardBuilder()

    # English category IDs for database - order matches get_product_categories
    category_ids = ["bakery", "dairy", "meat", "fruits", "vegetables", "drinks", "snacks", "frozen"]

    # Эмодзи для категорий - совпадают с партнёрскими
    category_emojis = ["🥖", "🥛", "🥩", "🍎", "🥬", "🥤", "🍿", "🧊"]
    categories = get_product_categories(lang)

    # "All offers" button на всю ширину
    if store_id:
        builder.button(
            text=f"📋 {'Все категории' if lang == 'ru' else 'Barcha toifalar'}",
            callback_data=f"store_cat_{store_id}_all",
        )
    else:
        builder.button(
            text=f"📋 {'Все категории' if lang == 'ru' else 'Barcha toifalar'}",
            callback_data="offers_all",
        )

    # Product categories for filtering with emojis
    for i, category in enumerate(categories):
        emoji = category_emojis[i] if i < len(category_emojis) else "📦"
        cat_id = category_ids[i] if i < len(category_ids) else "other"

        if store_id:
            # Use English category ID in callback for store-specific filtering
            callback_data = f"store_cat_{store_id}_{cat_id}"
        else:
            callback_data = f"offers_cat_{i}"
        builder.button(text=f"{emoji} {category}", callback_data=callback_data)

    # Раскладка: 1 кнопка "Все", затем по 2 категории в ряд
    builder.adjust(1, 2, 2, 2, 2)
    return builder.as_markup()
