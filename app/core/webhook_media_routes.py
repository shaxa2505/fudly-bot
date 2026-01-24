"""Photo and payment card routes for webhook Mini App API."""
from __future__ import annotations

from typing import Any

from aiohttp import web

from app.core.webhook_api_utils import add_cors_headers
from app.core.webhook_helpers import get_photo_url
from logging_config import logger


def build_media_handlers(bot: Any, db: Any):
    async def api_get_photo(request: web.Request) -> web.Response:
        """GET /api/v1/photo/{file_id} - Get photo URL from Telegram file_id and redirect."""
        file_id = request.match_info.get("file_id")
        if not file_id:
            return add_cors_headers(web.json_response({"error": "file_id required"}, status=400))

        try:
            photo_url = await get_photo_url(bot, file_id)
            if photo_url:
                raise web.HTTPFound(location=photo_url)
            return add_cors_headers(web.json_response({"error": "File not found"}, status=404))
        except web.HTTPFound:
            raise  # Re-raise redirect
        except Exception as e:
            logger.error(f"API get photo error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_get_payment_card(request: web.Request) -> web.Response:
        """GET /api/v1/payment-card/{store_id} - Get payment card for store."""
        store_id = request.match_info.get("store_id")
        try:
            payment_card = None
            payment_instructions = None

            # Try store-specific payment card first
            if store_id and hasattr(db, "get_payment_card"):
                try:
                    store_payment = db.get_payment_card(int(store_id))
                    if store_payment:
                        payment_card = store_payment
                        if isinstance(store_payment, dict):
                            payment_instructions = store_payment.get("payment_instructions")
                except Exception as e:
                    logger.warning(f"Failed to get store payment card: {e}")

            # Fallback to platform payment card
            if not payment_card and hasattr(db, "get_platform_payment_card"):
                payment_card = db.get_platform_payment_card()

            # Default payment card if not configured
            if not payment_card:
                payment_card = {
                    "card_number": "8600 1234 5678 9012",
                    "card_holder": "FUDLY",
                    "payment_instructions": "Chekni yuklashni unutmang!",
                }

            # Normalize payment card format
            if isinstance(payment_card, dict):
                card_number = payment_card.get("card_number", "")
                card_holder = payment_card.get("card_holder", "")
                if not payment_instructions:
                    payment_instructions = payment_card.get("payment_instructions")
            elif isinstance(payment_card, (tuple, list)) and len(payment_card) > 1:
                card_number = payment_card[1] if len(payment_card) > 1 else str(payment_card[0])
                card_holder = payment_card[2] if len(payment_card) > 2 else ""
            else:
                card_number = str(payment_card)
                card_holder = ""

            return add_cors_headers(
                web.json_response(
                    {
                        "card_number": card_number,
                        "card_holder": card_holder,
                        "payment_instructions": payment_instructions,
                    }
                )
            )
        except Exception as e:
            logger.error(f"API get payment card error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    return api_get_photo, api_get_payment_card
