"""Common cart dependencies and small helpers.

This module centralizes shared globals (db, bot) and simple helpers
used across cart submodules.
"""
from __future__ import annotations

from typing import Any

import html

from app.core.utils import get_offer_field, get_store_field
from localization import get_text

from .storage import cart_storage

# These will be set from `setup_dependencies` in `router.py`.
db: Any = None
bot: Any = None


def setup_dependencies(database: Any, bot_instance: Any) -> None:
    """Initialize shared cart dependencies (database, bot)."""
    global db, bot
    db = database
    bot = bot_instance


def esc(val: Any) -> str:
    """HTML-escape helper used in cart texts."""
    if val is None:
        return ""
    return html.escape(str(val))


def refresh_cart_items(user_id: int, lang: str) -> tuple[list[str], bool]:
    """Refresh cart items from DB and return update notices."""
    if not db:
        return [], False

    items = cart_storage.get_cart(user_id)
    if not items:
        return [], False

    updates: list[str] = []
    changed = False

    store_id = items[0].store_id
    store = db.get_store(store_id) if hasattr(db, "get_store") else None
    delivery_enabled = bool(get_store_field(store, "delivery_enabled", False))
    delivery_price = int(get_store_field(store, "delivery_price", 0) or 0)
    delivery_changed = False

    can_refresh_offer = hasattr(db, "get_offer")

    for item in list(items):
        if item.delivery_enabled and not delivery_enabled:
            delivery_changed = True

        offer = db.get_offer(item.offer_id) if can_refresh_offer else None
        if not can_refresh_offer:
            item.delivery_enabled = bool(delivery_enabled)
            item.delivery_price = delivery_price if delivery_enabled else 0
            if store:
                store_name = get_store_field(store, "name", item.store_name)
                store_address = get_store_field(store, "address", item.store_address)
                if store_name:
                    item.store_name = str(store_name)
                if store_address:
                    item.store_address = str(store_address)
            continue
        if not offer:
            cart_storage.remove_item(user_id, item.offer_id)
            updates.append(get_text(lang, "cart_item_removed", title=esc(item.title)))
            changed = True
            continue

        offer_store_id = get_offer_field(offer, "store_id", item.store_id)
        if offer_store_id is not None:
            try:
                if int(offer_store_id) != int(item.store_id):
                    cart_storage.remove_item(user_id, item.offer_id)
                    updates.append(get_text(lang, "cart_item_removed", title=esc(item.title)))
                    changed = True
                    continue
            except Exception:
                pass

        offer_qty = int(get_offer_field(offer, "quantity", item.max_quantity) or 0)
        if offer_qty <= 0:
            cart_storage.remove_item(user_id, item.offer_id)
            updates.append(get_text(lang, "cart_item_removed", title=esc(item.title)))
            changed = True
            continue

        if item.quantity > offer_qty:
            item.quantity = offer_qty
            updates.append(
                get_text(
                    lang,
                    "cart_item_qty_updated",
                    title=esc(item.title),
                    qty=offer_qty,
                    unit=esc(item.unit),
                )
            )
            changed = True

        item.max_quantity = offer_qty

        new_price = int(
            get_offer_field(offer, "discount_price", 0)
            or get_offer_field(offer, "price", 0)
            or get_offer_field(offer, "original_price", item.price)
            or item.price
        )
        if new_price <= 0:
            new_price = item.price
        if new_price != item.price:
            currency = "so'm" if lang == "uz" else "сум"
            price_str = f"{new_price:,}".replace(",", " ")
            updates.append(
                get_text(
                    lang,
                    "cart_item_price_updated",
                    title=esc(item.title),
                    price=price_str,
                    currency=currency,
                )
            )
            item.price = new_price
            changed = True

        new_original = int(
            get_offer_field(offer, "original_price", item.original_price or new_price) or new_price
        )
        if new_original:
            item.original_price = new_original

        unit = get_offer_field(offer, "unit", item.unit)
        if unit:
            item.unit = str(unit)
        expiry = get_offer_field(offer, "expiry_date", item.expiry_date)
        if expiry:
            item.expiry_date = str(expiry)

        if store:
            store_name = get_store_field(store, "name", item.store_name)
            store_address = get_store_field(store, "address", item.store_address)
            if store_name:
                item.store_name = str(store_name)
            if store_address:
                item.store_address = str(store_address)

        item.delivery_enabled = bool(delivery_enabled)
        item.delivery_price = delivery_price if delivery_enabled else 0

    if delivery_changed and not delivery_enabled:
        updates.append(get_text(lang, "cart_delivery_unavailable"))
        changed = True

    return updates, changed
