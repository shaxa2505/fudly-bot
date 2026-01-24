"""User history handlers for webhook Mini App API."""
from __future__ import annotations

from typing import Any, Callable

from aiohttp import web

from app.core.webhook_api_utils import add_cors_headers
from app.core.webhook_helpers import _is_offer_active
from logging_config import logger


def build_recently_viewed_handlers(
    db: Any,
    get_authenticated_user_id: Callable[[web.Request], int | None],
):
    async def api_add_recently_viewed(request: web.Request) -> web.Response:
        """POST /api/v1/user/recently-viewed - Add offer to recently viewed."""
        try:
            data = await request.json()
            authenticated_user_id = get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(web.json_response({"success": False}))

            user_id = authenticated_user_id
            offer_id = data.get("offer_id")

            if not user_id or not offer_id:
                return add_cors_headers(
                    web.json_response({"error": "user_id and offer_id required"}, status=400)
                )

            if hasattr(db, "add_recently_viewed"):
                db.add_recently_viewed(int(user_id), int(offer_id))
                return add_cors_headers(web.json_response({"success": True}))
            return add_cors_headers(web.json_response({"error": "Feature not available"}, status=501))
        except Exception as e:
            logger.error(f"API add recently viewed error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_get_recently_viewed(request: web.Request) -> web.Response:
        """GET /api/v1/user/recently-viewed - Get user's recently viewed offers."""
        try:
            authenticated_user_id = get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(web.json_response({"offers": []}))

            user_id = authenticated_user_id
            limit = int(request.query.get("limit", "20"))

            if not user_id:
                return add_cors_headers(web.json_response({"error": "user_id required"}, status=400))

            if hasattr(db, "get_recently_viewed"):
                offer_ids = db.get_recently_viewed(int(user_id), limit=limit)
                # Get full offer data for each ID
                formatted_offers = []
                for offer_id in offer_ids:
                    if hasattr(db, "get_offer"):
                        offer = db.get_offer(offer_id)
                        if offer and isinstance(offer, dict) and _is_offer_active(offer):
                            formatted_offers.append(
                                {
                                    "id": offer.get("id") or offer.get("offer_id"),
                                    "name": offer.get("name") or offer.get("title", ""),
                                    "title": offer.get("title") or offer.get("name", ""),
                                    "description": offer.get("description", ""),
                                    "old_price": float(
                                        offer.get("old_price") or offer.get("original_price") or 0
                                    ),
                                    "price": float(
                                        offer.get("price") or offer.get("discount_price") or 0
                                    ),
                                    "original_price": float(
                                        offer.get("original_price") or offer.get("old_price") or 0
                                    ),
                                    "discount_price": float(
                                        offer.get("discount_price") or offer.get("price") or 0
                                    ),
                                    "category_id": offer.get("category_id"),
                                    "store_id": offer.get("store_id"),
                                    "store_name": offer.get("store_name", ""),
                                    "photo": offer.get("photo"),
                                    "photo_id": offer.get("photo_id"),
                                    "quantity": offer.get("quantity", 0),
                                    "available": offer.get("status") == "active"
                                    if offer.get("status")
                                    else True,
                                }
                            )
                return add_cors_headers(web.json_response({"offers": formatted_offers}))
            return add_cors_headers(web.json_response({"offers": []}))
        except Exception as e:
            logger.error(f"API get recently viewed error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    return api_add_recently_viewed, api_get_recently_viewed


def build_search_history_handlers(
    db: Any,
    get_authenticated_user_id: Callable[[web.Request], int | None],
):
    async def api_add_search_history(request: web.Request) -> web.Response:
        """POST /api/v1/user/search-history - Add search query to history."""
        try:
            data = await request.json()
            authenticated_user_id = get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(web.json_response({"success": False}))

            user_id = authenticated_user_id
            query = data.get("query", "").strip()

            if not user_id or not query:
                return add_cors_headers(
                    web.json_response({"error": "user_id and query required"}, status=400)
                )

            if len(query) < 2:
                return add_cors_headers(web.json_response({"error": "Query too short"}, status=400))

            if hasattr(db, "add_search_query"):
                db.add_search_query(int(user_id), query)
                return add_cors_headers(web.json_response({"success": True}))
            return add_cors_headers(web.json_response({"error": "Feature not available"}, status=501))
        except Exception as e:
            logger.error(f"API add search history error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_get_search_history(request: web.Request) -> web.Response:
        """GET /api/v1/user/search-history - Get user's search history."""
        try:
            authenticated_user_id = get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(web.json_response({"history": []}))

            user_id = authenticated_user_id
            limit = int(request.query.get("limit", "10"))

            if not user_id:
                return add_cors_headers(web.json_response({"error": "user_id required"}, status=400))

            if hasattr(db, "get_search_history"):
                history = db.get_search_history(int(user_id), limit=limit)
                return add_cors_headers(web.json_response({"history": history}))
            return add_cors_headers(web.json_response({"history": []}))
        except Exception as e:
            logger.error(f"API get search history error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_clear_search_history(request: web.Request) -> web.Response:
        """DELETE /api/v1/user/search-history - Clear user's search history."""
        try:
            authenticated_user_id = get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(web.json_response({"success": False}))

            if hasattr(db, "clear_search_history"):
                db.clear_search_history(int(authenticated_user_id))
                return add_cors_headers(web.json_response({"success": True}))
            return add_cors_headers(web.json_response({"error": "Feature not available"}, status=501))
        except Exception as e:
            logger.error(f"API clear search history error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    return api_add_search_history, api_get_search_history, api_clear_search_history
