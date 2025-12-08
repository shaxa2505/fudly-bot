"""Customer order history - view past orders and repeat them."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.common.utils import html_escape as _esc

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


router = Router(name="order_history")

# Module dependencies
db: Any = None
bot: Any = None
cart_storage: Any = None


def setup_dependencies(database: Any, bot_instance: Any, cart_storage_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot, cart_storage
    db = database
    bot = bot_instance
    cart_storage = cart_storage_instance


@router.message(F.text.in_(["📋 Мои заказы", "📋 Buyurtmalarim"]))
async def my_orders_history(message: types.Message) -> None:
    """Show user's order history."""
    if not db or not message.from_user:
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    # Get user's completed orders (last 15)
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    o.order_id,
                    o.pickup_code,
                    o.created_at,
                    o.delivery_address,
                    o.total_price,
                    o.is_cart_order,
                    o.cart_items,
                    off.title as offer_title,
                    s.name as store_name
                FROM orders o
                LEFT JOIN offers off ON o.offer_id = off.offer_id
                LEFT JOIN stores s ON o.store_id = s.store_id
                WHERE o.user_id = %s
                  AND o.status IN ('completed', 'confirmed', 'pending')
                ORDER BY o.created_at DESC
                LIMIT 15
            """,
                (user_id,),
            )
            orders = cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to get order history for user {user_id}: {e}")
        await message.answer(
            "❌ Ошибка загрузки истории" if lang == "ru" else "❌ Tarix yuklanmadi",
            parse_mode="HTML",
        )
        return

    if not orders:
        await message.answer(
            "📋 История заказов пуста\n\nВы ещё не делали заказов."
            if lang == "ru"
            else "📋 Buyurtmalar tarixi bo'sh\n\nSiz hali buyurtma qilmadingiz.",
            parse_mode="HTML",
        )
        return

    # Build history list
    text_lines = [f"📋 <b>{'Buyurtmalar tarixi' if lang == 'uz' else 'История заказов'}</b>\n"]
    currency = "so'm" if lang == "uz" else "сум"

    kb = InlineKeyboardBuilder()

    for i, order in enumerate(orders[:10], 1):
        # Parse order data
        if hasattr(order, "get"):
            order_id = order.get("order_id")
            code = order.get("pickup_code")
            created = order.get("created_at")
            address = order.get("delivery_address")
            total = order.get("total_price", 0)
            is_cart = int(order.get("is_cart_order") or 0)
            cart_items_json = order.get("cart_items")
            offer_title = order.get("offer_title", "Заказ")
            store_name = order.get("store_name", "Магазин")
        else:
            order_id = order[0]
            code = order[1]
            created = order[2]
            address = order[3]
            total = order[4]
            is_cart = int(order[5] if len(order) > 5 else 0)
            cart_items_json = order[6] if len(order) > 6 else None
            offer_title = order[7] if len(order) > 7 else "Заказ"
            store_name = order[8] if len(order) > 8 else "Магазин"

        # Format date
        date_str = (
            created.strftime("%d.%m.%Y") if hasattr(created, "strftime") else str(created)[:10]
        )

        # Build order card
        if is_cart:
            # Cart order - show multiple items
            text_lines.append(f"\n<b>{i}. 🛒 {_esc(store_name)}</b>")

            # Parse cart items
            if cart_items_json:
                try:
                    import json

                    cart_items = (
                        json.loads(cart_items_json)
                        if isinstance(cart_items_json, str)
                        else cart_items_json
                    )
                    item_count = len(cart_items)
                    text_lines.append(
                        f"   📦 {item_count} {'mahsulot' if lang == 'uz' else 'товар(ов)'}"
                    )
                except Exception:
                    text_lines.append(f"   📦 {'Savat' if lang == 'uz' else 'Корзина'}")
            else:
                text_lines.append(f"   📦 {'Savat' if lang == 'uz' else 'Корзина'}")
        else:
            # Single item order
            text_lines.append(f"\n<b>{i}. {_esc(offer_title)}</b>")
            text_lines.append(f"   🏪 {_esc(store_name)}")

        text_lines.append(f"   💰 {total:,} {currency}")
        text_lines.append(f"   📅 {date_str}")

        if address:
            delivery_label = "Yetkazish" if lang == "uz" else "Доставка"
            text_lines.append(f"   🚚 {delivery_label}")
        else:
            pickup_label = "Olib ketish" if lang == "uz" else "Самовывоз"
            text_lines.append(f"   🏪 {pickup_label}")

        # Add repeat button
        kb.button(text=f"🔄 {i}" if i <= 5 else f"{i}", callback_data=f"repeat_order_{order_id}")

    text = "\n".join(text_lines)

    # Arrange buttons: 5 per row
    kb.adjust(5)

    # Add pagination hint if more than 10
    if len(orders) > 10:
        text += f"\n\n{'Va yana' if lang == 'uz' else 'И ещё'} {len(orders) - 10}..."

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("repeat_order_"))
async def repeat_order(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Repeat previous order - add items to cart."""
    if not db or not callback.message or not cart_storage:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True)
        return

    # Get order details
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    o.is_cart_order,
                    o.cart_items,
                    o.offer_id,
                    o.quantity,
                    o.store_id,
                    off.title,
                    off.discount_price,
                    off.quantity as available_qty,
                    off.unit,
                    s.name as store_name,
                    s.address as store_address
                FROM orders o
                LEFT JOIN offers off ON o.offer_id = off.offer_id
                LEFT JOIN stores s ON o.store_id = s.store_id
                WHERE o.order_id = %s AND o.user_id = %s
            """,
                (order_id, user_id),
            )
            order = cursor.fetchone()
    except Exception as e:
        logger.error(f"Failed to get order {order_id}: {e}")
        await callback.answer("❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True)
        return

    if not order:
        await callback.answer(
            "❌ Заказ не найден" if lang == "ru" else "❌ Buyurtma topilmadi", show_alert=True
        )
        return

    # Parse order
    if hasattr(order, "get"):
        is_cart = int(order.get("is_cart_order") or 0)
        cart_items_json = order.get("cart_items")
        offer_id = order.get("offer_id")
        quantity = order.get("quantity", 1)
        store_id = order.get("store_id")
        title = order.get("title", "Товар")
        price = order.get("discount_price", 0)
        available = order.get("available_qty", 0)
        unit = order.get("unit", "шт")
        store_name = order.get("store_name", "Магазин")
        store_address = order.get("store_address", "")
    else:
        is_cart = int(order[0] if order[0] else 0)
        cart_items_json = order[1]
        offer_id = order[2]
        quantity = order[3]
        store_id = order[4]
        title = order[5] if len(order) > 5 else "Товар"
        price = order[6] if len(order) > 6 else 0
        available = order[7] if len(order) > 7 else 0
        unit = order[8] if len(order) > 8 else "шт"
        store_name = order[9] if len(order) > 9 else "Магазин"
        store_address = order[10] if len(order) > 10 else ""

    added_count = 0

    if is_cart and cart_items_json:
        # Repeat cart order - add all items
        try:
            import json

            cart_items = (
                json.loads(cart_items_json) if isinstance(cart_items_json, str) else cart_items_json
            )

            for item in cart_items:
                item_offer_id = item.get("offer_id")

                # Check if offer still exists
                offer = db.get_offer(item_offer_id)
                if offer and offer.get("status") == "active":
                    from handlers.bookings.utils import get_offer_field

                    cart_storage.add_item(
                        user_id=user_id,
                        offer_id=item_offer_id,
                        store_id=store_id,
                        title=get_offer_field(offer, "title", item.get("title", "Товар")),
                        price=get_offer_field(offer, "discount_price", item.get("price", 0)),
                        quantity=item.get("quantity", 1),
                        original_price=get_offer_field(offer, "original_price", 0),
                        max_quantity=get_offer_field(offer, "quantity", 1),
                        store_name=store_name,
                        store_address=store_address,
                        unit=get_offer_field(offer, "unit", "шт"),
                    )
                    added_count += 1
        except Exception as e:
            logger.error(f"Failed to parse cart items for order {order_id}: {e}")
    else:
        # Single item order
        if offer_id:
            offer = db.get_offer(offer_id)
            if offer and offer.get("status") == "active":
                cart_storage.add_item(
                    user_id=user_id,
                    offer_id=offer_id,
                    store_id=store_id,
                    title=title,
                    price=price,
                    quantity=min(quantity, available),
                    max_quantity=available,
                    store_name=store_name,
                    store_address=store_address,
                    unit=unit,
                )
                added_count = 1

    if added_count > 0:
        cart_count = cart_storage.get_cart_count(user_id)
        text = (
            f"✅ Добавлено в корзину: {added_count} товар(ов)\n\n🛒 В корзине: {cart_count}"
            if lang == "ru"
            else f"✅ Savatga qo'shildi: {added_count} ta mahsulot\n\n🛒 Savatda: {cart_count}"
        )

        kb = InlineKeyboardBuilder()
        kb.button(
            text="🛒 Перейти в корзину" if lang == "ru" else "🛒 Savatga o'tish",
            callback_data="view_cart",
        )

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await callback.answer(
            "⚠️ Товары из этого заказа больше не доступны"
            if lang == "ru"
            else "⚠️ Bu buyurtmadagi mahsulotlar endi mavjud emas",
            show_alert=True,
        )

    await callback.answer()
