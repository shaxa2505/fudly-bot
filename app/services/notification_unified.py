"""
Unified notification payloads and renderers.

This module builds a channel-agnostic payload that downstream layers
can render for WebApp or Telegram without duplicating business logic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4


def _iso_now() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


def _normalize_order_type(order_type: str | None) -> str | None:
    if not order_type:
        return None
    normalized = str(order_type).strip().lower()
    if normalized == "taxi":
        return "delivery"
    return normalized


def _normalize_status(status: str | None) -> str | None:
    if not status:
        return None
    normalized = str(status).strip().lower()
    if normalized == "confirmed":
        return "preparing"
    return normalized


def _normalize_items(items: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not items:
        return []
    normalized: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        title = raw.get("title") or raw.get("offer_title") or raw.get("name") or ""
        qty = raw.get("quantity", raw.get("qty", 1)) or 1
        price = raw.get("price", raw.get("unit_price", raw.get("discount_price", 0))) or 0
        try:
            qty_int = int(qty)
        except Exception:
            qty_int = 1
        try:
            price_int = int(price)
        except Exception:
            price_int = 0
        subtotal = raw.get("subtotal")
        if subtotal is None:
            subtotal = price_int * qty_int
        try:
            subtotal_int = int(subtotal)
        except Exception:
            subtotal_int = price_int * qty_int
        item: dict[str, Any] = {
            "title": str(title),
            "qty": qty_int,
            "price": price_int,
            "subtotal": subtotal_int,
        }
        image_url = raw.get("image_url") or raw.get("photo_url") or raw.get("offer_photo_url")
        if image_url:
            item["image_url"] = image_url
        normalized.append(item)
    return normalized


def _normalize_amounts(
    items: list[dict[str, Any]],
    amounts: dict[str, Any] | None,
) -> dict[str, Any]:
    amounts = amounts or {}
    subtotal = amounts.get("subtotal", None)
    delivery_fee = amounts.get("delivery_fee", None)
    total = amounts.get("total", None)
    currency = amounts.get("currency", None)

    if subtotal is None:
        subtotal = sum(int(item.get("subtotal", 0)) for item in items)
    if delivery_fee is None:
        delivery_fee = 0
    if total is None:
        total = int(subtotal) + int(delivery_fee)

    result: dict[str, Any] = {
        "subtotal": int(subtotal or 0),
        "delivery_fee": int(delivery_fee or 0),
        "total": int(total or 0),
    }
    if currency:
        result["currency"] = currency
    return result


def _action(
    action_id: str,
    style: str = "primary",
    requires_confirm: bool = False,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action = {"id": action_id, "style": style}
    if requires_confirm:
        action["requires_confirm"] = True
    if payload:
        action["payload"] = payload
    return action


def _build_actions(
    role: str,
    status: str | None,
    order_type: str | None,
    payment_status: str | None,
    entity_id: int | None,
    entity_ids: list[int] | None,
    is_cart: bool,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    payload: dict[str, Any] = {}
    if entity_id is not None:
        payload["order_id"] = int(entity_id)
    if entity_ids:
        payload["order_ids"] = [int(x) for x in entity_ids]

    if role == "customer":
        if payment_status == "awaiting_payment":
            actions.append(_action("pay_now", payload=payload))
            actions.append(_action("support", style="secondary", payload=payload))
        elif payment_status == "awaiting_proof":
            actions.append(_action("upload_proof", payload=payload))
            actions.append(_action("support", style="secondary", payload=payload))
        elif payment_status == "payment_rejected":
            actions.append(_action("retry_payment", payload=payload))
            actions.append(_action("support", style="secondary", payload=payload))
        else:
            if status in ("ready", "delivering"):
                actions.append(_action("received_order", payload=payload))
                if order_type == "delivery":
                    actions.append(_action("track_order", style="secondary", payload=payload))
            elif status == "pending":
                actions.append(_action("open_order", payload=payload))
                if not is_cart:
                    actions.append(
                        _action("cancel_order", style="danger", requires_confirm=True, payload=payload)
                    )
            elif status == "completed":
                actions.append(_action("rate_order", payload=payload))

    if role == "partner":
        if status == "pending":
            actions.append(_action("confirm_order", payload=payload))
            actions.append(
                _action("reject_order", style="danger", requires_confirm=True, payload=payload)
            )
        elif status == "ready":
            if order_type == "delivery":
                actions.append(_action("handover_to_courier", payload=payload))
            else:
                actions.append(_action("mark_completed", payload=payload))
        elif status == "preparing" and order_type == "pickup":
            actions.append(_action("mark_ready_pickup", payload=payload))

    return actions


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, raw in value.items():
            compacted = _compact(raw)
            if compacted is None:
                continue
            if compacted == {} or compacted == [] or compacted == "":
                continue
            cleaned[key] = compacted
        return cleaned
    if isinstance(value, list):
        cleaned_list = [_compact(item) for item in value]
        cleaned_list = [item for item in cleaned_list if item not in (None, {}, [], "")]
        return cleaned_list
    return value


def build_unified_order_payload(
    *,
    kind: str,
    role: str,
    entity_type: str,
    entity_id: int | None = None,
    entity_ids: list[int] | None = None,
    is_cart: bool = False,
    order_type: str | None = None,
    status: str | None = None,
    payment_status: str | None = None,
    pickup_code: str | None = None,
    delivery_address: str | None = None,
    store: dict[str, Any] | None = None,
    customer: dict[str, Any] | None = None,
    courier: dict[str, Any] | None = None,
    items: Iterable[dict[str, Any]] | None = None,
    amounts: dict[str, Any] | None = None,
    timing: dict[str, Any] | None = None,
    actions: list[dict[str, Any]] | None = None,
    created_at: str | None = None,
    priority: int = 0,
) -> dict[str, Any]:
    normalized_type = _normalize_order_type(order_type)
    normalized_status = _normalize_status(status)
    normalized_items = _normalize_items(items)
    normalized_amounts = _normalize_amounts(normalized_items, amounts)

    ids = entity_ids or ([entity_id] if entity_id is not None else [])
    if ids:
        ids = [int(x) for x in ids if x is not None]

    payment_status_normalized = (
        str(payment_status).strip().lower() if payment_status is not None else None
    )
    payload: dict[str, Any] = {
        "id": str(uuid4()),
        "kind": kind,
        "role": role,
        "priority": int(priority or 0),
        "created_at": created_at or _iso_now(),
        "entity": {
            "type": entity_type,
            "id": int(entity_id) if entity_id is not None else None,
            "ids": ids,
            "is_cart": bool(is_cart),
        },
        "order": {
            "type": normalized_type,
            "status": normalized_status,
            "payment_status": payment_status_normalized,
            "pickup_code": pickup_code,
            "delivery_address": delivery_address,
            "store": store or None,
            "customer": customer or None,
            "courier": courier or None,
            "items": normalized_items,
            "amounts": normalized_amounts,
        },
        "timing": timing or {},
    }

    if actions is None:
        actions = _build_actions(
            role=role,
            status=normalized_status,
            order_type=normalized_type,
            payment_status=payment_status,
            entity_id=entity_id,
            entity_ids=ids,
            is_cart=is_cart,
        )
    payload["actions"] = actions or []

    return _compact(payload)


def render_plain(payload: dict[str, Any]) -> tuple[str, str]:
    """Render a minimal plain-text fallback from unified payload."""
    entity = payload.get("entity", {})
    order = payload.get("order", {})
    order_id = entity.get("id") or (entity.get("ids") or [None])[0]
    order_type = order.get("type")
    status = order.get("status") or order.get("payment_status")
    amounts = order.get("amounts", {})
    total = amounts.get("total")
    currency = amounts.get("currency")

    title = f"Order #{order_id}" if order_id else "Order update"
    parts: list[str] = []
    if status:
        parts.append(f"Status: {status}")
    if order_type:
        parts.append(f"Type: {order_type}")
    if total is not None:
        if currency:
            parts.append(f"Total: {total} {currency}")
        else:
            parts.append(f"Total: {total}")

    return title, " | ".join(parts)
