"""Cart routes for webhook Mini App API."""
from __future__ import annotations

import os
from typing import Any

from aiohttp import web

from app.core.webhook_api_utils import add_cors_headers
from app.core.webhook_helpers import _is_offer_active, get_offer_value
from logging_config import logger


def build_cart_handlers(db: Any):
    async def api_calculate_cart(request: web.Request) -> web.Response:
        """GET /api/v1/cart/calculate - Calculate cart totals."""
        offer_ids = request.query.get("offer_ids", "")
        if not offer_ids:
            return add_cors_headers(web.json_response({"error": "offer_ids required"}, status=400))

        price_unit = os.getenv("PRICE_STORAGE_UNIT", "sums").lower()
        convert = (lambda v: float(v or 0) / 100) if price_unit == "kopeks" else (
            lambda v: float(v or 0)
        )

        items = []
        total = 0.0
        items_count = 0

        try:
            for item_str in offer_ids.split(","):
                if ":" not in item_str:
                    continue
                offer_id_str, qty_str = item_str.split(":", 1)
                try:
                    offer_id = int(offer_id_str)
                    quantity = int(qty_str)
                except (TypeError, ValueError):
                    continue

                offer = db.get_offer(offer_id) if hasattr(db, "get_offer") else None
                if not offer or not _is_offer_active(offer):
                    continue

                price = convert(get_offer_value(offer, "discount_price", 0))
                items.append(
                    {
                        "offer_id": offer_id,
                        "quantity": quantity,
                        "title": get_offer_value(offer, "title", ""),
                        "price": price,
                        "photo": get_offer_value(offer, "photo")
                        or get_offer_value(offer, "photo_id"),
                    }
                )
                total += price * quantity
                items_count += quantity

            payload = {"items": items, "total": total, "items_count": items_count}
            return add_cors_headers(web.json_response(payload))
        except Exception as e:
            logger.error(f"API cart calculate error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    return api_calculate_cart
