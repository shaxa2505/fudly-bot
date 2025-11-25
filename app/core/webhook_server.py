"""Webhook server for production deployment."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from aiogram import Bot, Dispatcher, types
from aiohttp import web

from app.core.metrics import metrics as app_metrics
from app.core.notifications import get_notification_service
from app.core.websocket import get_websocket_manager, setup_websocket_routes
from logging_config import logger


async def create_webhook_app(
    bot: Bot,
    dp: Dispatcher,
    webhook_path: str,
    secret_token: str | None,
    metrics: dict[str, int],
    db: Any,
) -> web.Application:
    """Create aiohttp web application with webhook handlers."""
    app = web.Application()

    async def webhook_handler(request: web.Request) -> web.Response:
        """Handle incoming Telegram updates via webhook."""
        import time

        start_ts = time.time()

        # Only allow POST requests
        if request.method != "POST":
            return web.Response(status=405, text="Method Not Allowed")

        try:
            logger.info(f"Webhook request received from {request.remote}")

            # Verify secret token if configured
            if secret_token:
                hdr = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
                if hdr != secret_token:
                    logger.warning("Invalid secret token")
                    metrics["updates_errors"] += 1
                    return web.Response(status=403, text="Forbidden")

            # Parse JSON
            try:
                update_data = await request.json()
            except Exception as json_e:
                logger.error(f"Webhook JSON parse error: {repr(json_e)}")
                metrics["webhook_json_errors"] += 1
                return web.Response(status=200, text="OK")

            logger.debug(f"Raw update: {update_data}")

            # Validate Update structure
            try:
                telegram_update = types.Update.model_validate(update_data)
            except Exception as validate_e:
                logger.error(f"Webhook validation error: {repr(validate_e)}")
                metrics["webhook_validation_errors"] += 1
                return web.Response(status=200, text="OK")

            # Process update
            await dp.feed_update(bot, telegram_update)
            metrics["updates_received"] += 1
            proc_ms = int((time.time() - start_ts) * 1000)
            logger.info(f"Update processed successfully ({proc_ms}ms)")
            return web.Response(status=200, text="OK")

        except Exception as e:
            logger.error(f"Webhook unexpected error: {repr(e)}", exc_info=True)
            metrics["webhook_unexpected_errors"] += 1
            metrics["updates_errors"] += 1
            return web.Response(status=200, text="OK")

    async def health_check(request: web.Request) -> web.Response:
        """Comprehensive health check endpoint."""
        try:
            # Check database connection
            db_healthy = True
            db_error = None
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            except Exception as e:
                db_healthy = False
                db_error = str(e)

            status = {
                "status": "healthy" if db_healthy else "degraded",
                "bot": "Fudly",
                "timestamp": datetime.now().isoformat(),
                "components": {
                    "database": {
                        "status": "healthy" if db_healthy else "unhealthy",
                        "error": db_error,
                    },
                    "bot": {"status": "healthy"},
                },
            }

            # Add metrics
            status["metrics"] = {
                "updates_received": metrics.get("updates_received", 0),
                "updates_errors": metrics.get("updates_errors", 0),
                "error_rate": round(
                    metrics.get("updates_errors", 0)
                    / max(metrics.get("updates_received", 1), 1)
                    * 100,
                    2,
                ),
            }

            http_status = 200 if db_healthy else 503
            return web.json_response(status, status=http_status)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return web.json_response({"status": "error", "error": str(e)}, status=500)

    async def version_info(request: web.Request) -> web.Response:
        """Return version and configuration info."""
        return web.json_response(
            {"app": "Fudly", "mode": "webhook", "ts": datetime.now().isoformat(timespec="seconds")}
        )

    def _prometheus_metrics_text() -> str:
        """Generate Prometheus-style metrics text."""
        # Use new metrics module for comprehensive metrics
        return app_metrics.export_prometheus()

    async def metrics_prom(request: web.Request) -> web.Response:
        """Return Prometheus-style metrics."""
        text = _prometheus_metrics_text()
        return web.Response(text=text, content_type="text/plain; version=0.0.4; charset=utf-8")

    async def metrics_json(request: web.Request) -> web.Response:
        """Return metrics as JSON."""
        # Combine old metrics with new summary
        combined = dict(metrics)
        combined.update(app_metrics.get_summary())
        return web.json_response(combined)

    async def webhook_get(request: web.Request) -> web.Response:
        """Handle GET requests to webhook endpoint (sanity check)."""
        return web.Response(text="OK", status=200)

    async def docs_handler(request: web.Request) -> web.Response:
        """Serve Swagger UI for API documentation."""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Fudly Bot API Documentation</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <style>
        body { margin: 0; padding: 0; }
        .swagger-ui .topbar { display: none; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({
            url: '/openapi.yaml',
            dom_id: '#swagger-ui',
            presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
            layout: "BaseLayout"
        });
    </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def openapi_spec_handler(request: web.Request) -> web.Response:
        """Serve OpenAPI specification."""
        import os

        spec_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "openapi.yaml")
        try:
            with open(spec_path, encoding="utf-8") as f:
                spec = f.read()
            return web.Response(text=spec, content_type="application/x-yaml")
        except FileNotFoundError:
            return web.Response(text="OpenAPI spec not found", status=404)

    # Register routes
    path_main = webhook_path if webhook_path.startswith("/") else f"/{webhook_path}"
    path_alt = path_main.rstrip("/") + "/"

    app.router.add_post(path_main, webhook_handler)
    app.router.add_post(path_alt, webhook_handler)
    app.router.add_get(path_main, webhook_get)
    app.router.add_get(path_alt, webhook_get)
    app.router.add_get("/health", health_check)
    app.router.add_get("/version", version_info)
    app.router.add_get("/metrics", metrics_prom)
    app.router.add_get("/metrics.json", metrics_json)
    app.router.add_get("/docs", docs_handler)
    app.router.add_get("/openapi.yaml", openapi_spec_handler)
    app.router.add_get("/", health_check)  # Railway health check

    # Setup WebSocket routes for real-time notifications
    setup_websocket_routes(app)

    # Initialize notification service
    redis_url = None  # Can be configured via env
    notification_service = get_notification_service(redis_url)
    notification_service.set_telegram_bot(bot)

    # Initialize WebSocket manager
    ws_manager = get_websocket_manager()
    ws_manager.set_notification_service(notification_service)

    # Store services in app for access in handlers
    app["notification_service"] = notification_service
    app["websocket_manager"] = ws_manager

    return app


async def run_webhook_server(
    app: web.Application,
    port: int,
) -> web.AppRunner:
    """Start webhook server and return runner for cleanup."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info(f"🌐 Webhook server started on port {port}")
    return runner
