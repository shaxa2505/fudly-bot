from __future__ import annotations

import html
import re
from typing import Any

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.notifications import Notification, NotificationType, get_notification_service
from app.core.sanitize import sanitize_phone
from app.core.security import validator
from app.services.unified_order_service import OrderItem, get_unified_order_service

from .common import (
    CreateOrderRequest,
    OrderResponse,
    get_current_user,
    get_db,
    get_val,
    logger,
    normalize_price,
    settings,
)

router = APIRouter()


class CancelOrderResponse(BaseModel):
    success: bool
    status: str


def _require_user_id(user: dict[str, Any]) -> int:
    user_id = int(user.get("id") or 0)
    if user_id == 0:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def _update_phone_if_valid(db: Any, user_id: int, raw_phone: str | None) -> None:
    if not raw_phone:
        return
    sanitized_phone = sanitize_phone(raw_phone)
    if not sanitized_phone or not validator.validate_phone(sanitized_phone):
        return
    try:
        if hasattr(db, "update_user_phone"):
            user_model = db.get_user_model(user_id)
            current_phone = get_val(user_model, "phone") if user_model else None
            if not current_phone or current_phone != sanitized_phone:
                db.update_user_phone(user_id, sanitized_phone)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Could not update user phone for {user_id}: {e}")


def _resolve_required_phone(db: Any, user_id: int, raw_phone: str | None) -> str:
    candidate = (raw_phone or "").strip()
    if candidate:
        _update_phone_if_valid(db, user_id, candidate)
        return candidate
    user_model = db.get_user_model(user_id) if hasattr(db, "get_user_model") else None
    stored_phone = (get_val(user_model, "phone") if user_model else None) or ""
    stored_phone = str(stored_phone).strip()
    if not stored_phone:
        raise HTTPException(status_code=400, detail="Phone is required")
    return stored_phone


def _load_offers_and_store(
    items: list[Any], db: Any
) -> tuple[dict[int, Any], int]:
    if not items:
        raise HTTPException(status_code=400, detail="No items provided")
    offers_by_id: dict[int, Any] = {}
    store_ids: set[int] = set()
    for item in items:
        offer = db.get_offer(item.offer_id) if hasattr(db, "get_offer") else None
        if not offer:
            raise HTTPException(
                status_code=400, detail=f"Offer not found: {item.offer_id}"
            )
        offers_by_id[item.offer_id] = offer
        store_id = int(get_val(offer, "store_id") or 0)
        if store_id:
            store_ids.add(store_id)

    if len(store_ids) > 1:
        raise HTTPException(status_code=400, detail="Only one store per order is supported")
    if not store_ids:
        raise HTTPException(status_code=400, detail="Invalid store data")

    return offers_by_id, next(iter(store_ids))


def _validate_min_order(
    db: Any,
    store_id: int,
    items: list[Any],
    offers_by_id: dict[int, Any],
) -> None:
    total_check = 0.0
    for item in items:
        offer = offers_by_id.get(item.offer_id)
        if not offer:
            continue
        price = normalize_price(get_val(offer, "discount_price", 0))
        total_check += price * item.quantity

    store_check = db.get_store(store_id) if hasattr(db, "get_store") else None
    if not store_check:
        return
    min_order = normalize_price(get_val(store_check, "min_order_amount", 0))
    if min_order > 0 and total_check < min_order:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum order amount: {min_order}. Your total: {total_check}",
        )


@router.post("/orders", response_model=OrderResponse)
async def create_order(
    order: CreateOrderRequest, db=Depends(get_db), user: dict = Depends(get_current_user)
):
    """Create a new order from Mini App and notify partner."""

    bot_instance: Bot | None = None

    try:
        user_id = _require_user_id(user)
        if order.user_id and order.user_id != user_id:
            logger.warning(
                "create_order user mismatch: initData=%s payload=%s", user_id, order.user_id
            )
            raise HTTPException(status_code=403, detail="User mismatch")

        try:
            bot_instance = Bot(token=settings.bot_token)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Could not create bot instance: {e}")

        resolved_phone = _resolve_required_phone(db, user_id, order.phone)

        offers_by_id, store_id = _load_offers_and_store(order.items, db)

        is_delivery = bool(order.delivery_address and order.delivery_address.strip())
        payment_method = (order.payment_method or "").strip().lower()
        if not payment_method:
            payment_method = "click" if is_delivery else "cash"

        if is_delivery and payment_method == "cash":
            raise HTTPException(
                status_code=400,
                detail="Cash is not allowed for delivery orders",
            )

        if is_delivery and payment_method == "card":
            raise HTTPException(
                status_code=400,
                detail="Card payments for delivery require proof upload",
            )

        if is_delivery:
            _validate_min_order(db, store_id, order.items, offers_by_id)

        created_items: list[dict[str, Any]] = []

        order_service = get_unified_order_service()

        # If unified service is available, use it as a single entry point
        if order_service and hasattr(db, "create_cart_order"):
            order_items: list[OrderItem] = []
            for item in order.items:
                offer = offers_by_id.get(item.offer_id)
                if not offer:
                    continue

                price = int(normalize_price(get_val(offer, "discount_price", 0)))
                offer_store_id = int(get_val(offer, "store_id"))
                offer_title = get_val(offer, "title", "Товар")
                store = db.get_store(offer_store_id) if hasattr(db, "get_store") else None
                store_name = get_val(store, "name", "") if store else ""
                store_address = get_val(store, "address", "") if store else ""
                delivery_price = 0
                if is_delivery and store:
                    delivery_price = int(normalize_price(get_val(store, "delivery_price", 1500000)))

                order_items.append(
                    OrderItem(
                        offer_id=item.offer_id,
                        store_id=offer_store_id,
                        title=offer_title,
                        price=price,
                        original_price=price,
                        quantity=item.quantity,
                        store_name=store_name,
                        store_address=store_address,
                        delivery_price=delivery_price,
                    )
                )

            try:
                from app.services.unified_order_service import OrderResult  # type: ignore

                result: OrderResult = await order_service.create_order(
                    user_id=user_id,
                    items=order_items,
                    order_type="delivery" if is_delivery else "pickup",
                    delivery_address=order.delivery_address if is_delivery else None,
                    payment_method=payment_method,
                    notify_customer=False,
                    notify_sellers=True,
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Unified order service failed for webapp order: {e}")
                result = None

            if result and result.success:
                # Map unified result back to old created_items shape
                if is_delivery:
                    oid = result.order_ids[0] if result.order_ids else 0
                    delivery_price = int(order_items[0].delivery_price) if order_items else 0
                    for idx, item_obj in enumerate(order_items):
                        total = (item_obj.price * item_obj.quantity) + (delivery_price if idx == 0 else 0)
                        created_items.append(
                            {
                                "id": oid,
                                "type": "order",
                                "offer_id": item_obj.offer_id,
                                "quantity": item_obj.quantity,
                                "total": total,
                                "offer_title": item_obj.title,
                                "store_id": item_obj.store_id,
                            }
                        )
                        logger.info(f"✅ Created unified delivery ORDER {oid} for user {user_id}")
                else:
                    pickup_code = result.pickup_codes[0] if result.pickup_codes else None
                    oid = result.order_ids[0] if result.order_ids else 0
                    for item_obj in order_items:
                        total = item_obj.price * item_obj.quantity
                        created_items.append(
                            {
                                "id": oid,
                                "type": "order",
                                "offer_id": item_obj.offer_id,
                                "quantity": item_obj.quantity,
                                "total": total,
                                "offer_title": item_obj.title,
                                "store_id": item_obj.store_id,
                                "pickup_code": pickup_code,
                            }
                        )
                        logger.info(f"✅ Created unified pickup ORDER {oid} for user {user_id}")
            else:
                logger.error(
                    "Unified order service returned failure for webapp order: %s",
                    result.error_message if result else "no result",
                )
                # No fallback - UnifiedOrderService is the only way
                raise HTTPException(
                    status_code=500, 
                    detail=result.error_message or "Failed to create order"
                )

        # UnifiedOrderService already notifies sellers (Telegram + WebSocket).

        order_id = created_items[0]["id"] if created_items else 0
        total_amount = sum(b["total"] for b in created_items)
        total_items = sum(b["quantity"] for b in created_items)

        if bot_instance and created_items and user_id:
            try:
                customer_lang = (
                    db.get_user_language(user_id) if hasattr(db, "get_user_language") else "ru"
                )
                currency = "so'm" if customer_lang == "uz" else "сум"

                if customer_lang == "uz":
                    order_type_uz = "🚚 Yetkazish" if is_delivery else "🏪 O'zi olib ketadi"
                    confirm_msg = "✅ <b>Buyurtma qabul qilindi!</b>\n\n"
                    confirm_msg += f"📦 #{order_id}\n"
                    confirm_msg += f"{order_type_uz}\n\n"
                    confirm_msg += "<b>Mahsulotlar:</b>\n"
                    for item in created_items:
                        confirm_msg += f"• {item['offer_title']} × {item['quantity']}\n"
                    confirm_msg += f"\n💰 <b>Jami: {int(total_amount):,} {currency}</b>\n\n"
                    if is_delivery and order.delivery_address:
                        confirm_msg += f"📍 {order.delivery_address}\n\n"
                    confirm_msg += "⏳ Sotuvchi tasdiqlashini kutamiz..."
                else:
                    order_type_ru = "🚚 Доставка" if is_delivery else "🏪 Самовывоз"
                    confirm_msg = "✅ <b>Заказ оформлен!</b>\n\n"
                    confirm_msg += f"📦 #{order_id}\n"
                    confirm_msg += f"{order_type_ru}\n\n"
                    confirm_msg += "<b>Товары:</b>\n"
                    for item in created_items:
                        confirm_msg += f"• {item['offer_title']} × {item['quantity']}\n"
                    confirm_msg += f"\n💰 <b>Итого: {int(total_amount):,} {currency}</b>\n\n"
                    if is_delivery and order.delivery_address:
                        confirm_msg += f"📍 {order.delivery_address}\n\n"
                    confirm_msg += "⏳ Ожидаем подтверждения продавца..."

                await bot_instance.send_message(user_id, confirm_msg, parse_mode="HTML")
                logger.info(f"✅ Sent order confirmation to customer {user_id}")

                try:
                    notification_service = get_notification_service()
                    title = (
                        "Buyurtma qabul qilindi"
                        if customer_lang == "uz"
                        else "Заказ принят"
                    )
                    plain_msg = re.sub(r"<[^>]+>", "", confirm_msg)
                    await notification_service.notify_user(
                        Notification(
                            type=NotificationType.NEW_BOOKING,
                            recipient_id=int(user_id),
                            title=title,
                            message=plain_msg,
                            data={"order_id": order_id, "status": "pending"},
                            priority=0,
                        )
                    )
                except Exception as notify_error:  # pragma: no cover - defensive
                    logger.warning(f"Notification service failed: {notify_error}")
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"Failed to send confirmation to customer: {e}")

        logger.info(
            "ORDER_CREATED: id=%s, user=%s, type=%s, total=%s, items=%s, source=webapp_api",
            order_id,
            user_id,
            "delivery" if is_delivery else "pickup",
            int(total_amount),
            total_items,
        )

        return OrderResponse(
            order_id=order_id, status="pending", total=total_amount, items_count=total_items
        )

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error creating order: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        if bot_instance:
            try:
                await bot_instance.session.close()
            except Exception:  # pragma: no cover - defensive
                pass


@router.post("/orders/{order_id}/cancel", response_model=CancelOrderResponse)
async def cancel_order(
    order_id: int,
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
) -> CancelOrderResponse:
    """Cancel order/booking from Mini App (customer)."""
    user_id = _require_user_id(user)

    entity = None
    entity_type = "order"

    if hasattr(db, "get_order"):
        entity = db.get_order(order_id)
        if entity and int(get_val(entity, "user_id", 0)) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

    if entity is None and hasattr(db, "get_booking"):
        entity_type = "booking"
        entity = db.get_booking(order_id)
        if entity and int(get_val(entity, "user_id", 0)) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

    if entity is None:
        raise HTTPException(status_code=404, detail="Order not found")

    current_status = get_val(entity, "order_status") or get_val(entity, "status") or "pending"
    if current_status in ("completed", "cancelled", "rejected"):
        return CancelOrderResponse(success=True, status=str(current_status))

    order_service = get_unified_order_service()
    if not order_service:
        raise HTTPException(status_code=500, detail="Order service unavailable")

    ok = await order_service.cancel_order(order_id, entity_type)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to cancel order")

    return CancelOrderResponse(success=True, status="cancelled")


async def notify_partner_webapp_order(
    bot: Bot,
    db: Any,
    owner_id: int,
    entity_id: int,
    offer_title: str,
    quantity: int,
    total: float,
    user_id: int,
    delivery_address: str | None,
    phone: str | None,
    photo: str | None,
    is_delivery: bool = False,
) -> None:
    """Send notification to partner about new webapp order."""

    partner_lang = db.get_user_language(owner_id) if hasattr(db, "get_user_language") else "uz"
    user = db.get_user(user_id) if hasattr(db, "get_user") else None

    def get_user_val(obj: Any, key: str, default: Any | None = None) -> Any | None:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default) if obj else default

    customer_name = get_user_val(user, "first_name", "Клиент")
    customer_phone = phone or get_user_val(user, "phone", "Не указан")

    def _esc(val: Any) -> str:
        return html.escape(str(val)) if val is not None else ""

    currency = "so'm" if partner_lang == "uz" else "сум"
    unit_label = "dona" if partner_lang == "uz" else "шт"

    if partner_lang == "uz":
        text = (
            f"🔔 <b>YANGI BUYURTMA (Mini App)!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Miqdor: <b>{quantity}</b> {unit_label}\n"
            f"💰 Jami: <b>{int(total):,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Xaridor:</b>\n"
            f"   Ism: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
        )
        if is_delivery:
            text += "\n🚚 <b>Yetkazib berish</b>\n"
            if delivery_address:
                text += f"   📍 {_esc(delivery_address)}\n"
        else:
            text += "\n🏪 <b>O'zi olib ketadi</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━"
        confirm_text = "✅ Tasdiqlash"
        reject_text = "❌ Rad etish"
    else:
        text = (
            f"🔔 <b>НОВЫЙ ЗАКАЗ (Mini App)!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Количество: <b>{quantity}</b> {unit_label}\n"
            f"💰 Итого: <b>{int(total):,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Покупатель:</b>\n"
            f"   Имя: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
        )
        if is_delivery:
            text += "\n🚚 <b>Доставка</b>\n"
            if delivery_address:
                text += f"   📍 {_esc(delivery_address)}\n"
        else:
            text += "\n🏪 <b>Самовывоз</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━"
        confirm_text = "✅ Подтвердить"
        reject_text = "❌ Отклонить"

    kb = InlineKeyboardBuilder()
    if is_delivery:
        kb.button(text=confirm_text, callback_data=f"order_confirm_{entity_id}")
        kb.button(text=reject_text, callback_data=f"order_reject_{entity_id}")
    else:
        kb.button(text=confirm_text, callback_data=f"booking_confirm_{entity_id}")
        kb.button(text=reject_text, callback_data=f"booking_reject_{entity_id}")
    kb.adjust(2)

    try:
        sent_msg = None
        if photo:
            try:
                sent_msg = await bot.send_photo(
                    owner_id,
                    photo=photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            except Exception:  # pragma: no cover - fallback to text
                sent_msg = None

        if not sent_msg:
            sent_msg = await bot.send_message(
                owner_id, text, parse_mode="HTML", reply_markup=kb.as_markup()
            )

        if (
            sent_msg
            and hasattr(db, "set_order_seller_message_id")
            and hasattr(db, "set_booking_seller_message_id")
        ):
            try:
                if is_delivery:
                    db.set_order_seller_message_id(entity_id, sent_msg.message_id)
                    logger.info(
                        "Saved seller_message_id=%s for order#%s",
                        sent_msg.message_id,
                        entity_id,
                    )
                else:
                    db.set_booking_seller_message_id(entity_id, sent_msg.message_id)
                    logger.info(
                        "Saved seller_message_id=%s for booking#%s",
                        sent_msg.message_id,
                        entity_id,
                    )
            except Exception as save_err:  # pragma: no cover - defensive
                logger.error(f"Failed to save seller_message_id: {save_err}")
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Failed to notify partner {owner_id}: {e}")

