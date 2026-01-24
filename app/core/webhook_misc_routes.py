"""Misc Mini App API routes for webhook server (debug + health)."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from aiohttp import web

from app.core.webhook_api_utils import add_cors_headers

def build_misc_handlers(db: Any):
    async def api_debug(request: web.Request) -> web.Response:
        """GET /api/v1/debug - Debug database info (dev only)."""
        # Security: only allow in non-production environments
        environment = os.getenv("ENVIRONMENT", "production").lower()
        if environment not in ("development", "dev", "local", "test"):
            return web.json_response({"error": "Not available"}, status=404)

        try:
            info = {
                "db_type": type(db).__name__,
                "has_get_hot_offers": hasattr(db, "get_hot_offers"),
                "has_get_store_offers": hasattr(db, "get_store_offers"),
            }

            # Try to count offers directly
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM offers")
                    info["total_offers"] = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM offers WHERE status = 'active'")
                    info["active_offers"] = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM stores")
                    info["total_stores"] = cursor.fetchone()[0]
                    cursor.execute(
                        "SELECT COUNT(*) FROM stores WHERE status = 'active' OR status = 'approved'"
                    )
                    info["active_stores"] = cursor.fetchone()[0]
            except Exception as e:
                info["db_error"] = str(e)

            # Check photo_id in offers
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT offer_id, title, photo_id FROM offers WHERE photo_id IS NOT NULL LIMIT 5"
                    )
                    rows = cursor.fetchall()
                    info["offers_with_photos"] = [
                        {"id": r[0], "title": r[1], "photo_id": r[2]} for r in rows
                    ]
            except Exception as e:
                info["photo_check_error"] = str(e)

            return add_cors_headers(web.json_response(info))
        except Exception as e:
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_health(request: web.Request) -> web.Response:
        """GET /api/v1/health - API health check."""
        return add_cors_headers(
            web.json_response(
                {
                    "status": "ok",
                    "service": "fudly-webapp-api",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )

    return api_debug, api_health
