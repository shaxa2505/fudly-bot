"""Payment callback handlers for webhook aiohttp server."""
from __future__ import annotations

from typing import Any

from aiohttp import web

from app.integrations.payment_service import get_payment_service
from logging_config import logger


def build_click_callback(db: Any):
    async def api_click_callback(request: web.Request) -> web.Response:
        """POST /api/v1/payment/click/callback - Click payment callback."""
        try:
            data = None
            try:
                data = await request.post()
            except Exception:
                data = None

            payload: dict[str, Any] = {}
            if data:
                payload = dict(data)
            else:
                try:
                    json_payload = await request.json()
                    if isinstance(json_payload, dict):
                        payload = json_payload
                except Exception:
                    payload = {}

            if not payload:
                try:
                    payload = dict(request.query)
                except Exception:
                    payload = {}

            def _get_value(key: str, default: Any = "") -> Any:
                value = payload.get(key, default)
                if isinstance(value, (list, tuple)):
                    return value[0] if value else default
                return value

            payment_service = get_payment_service()
            if hasattr(payment_service, "set_database"):
                payment_service.set_database(db)

            click_trans_id = _get_value("click_trans_id", "")
            click_paydoc_id = _get_value("click_paydoc_id", "")
            service_id = _get_value("service_id", "")
            merchant_trans_id = _get_value("merchant_trans_id", "")
            amount = _get_value("amount", "0")
            action = _get_value("action", "")
            sign_time = _get_value("sign_time", "")
            sign_string = _get_value("sign_string", "")
            error_raw = _get_value("error", 0)
            try:
                error = int(error_raw or 0)
            except (TypeError, ValueError):
                error = 0

            if action == "0":  # Prepare
                result = await payment_service.process_click_prepare(
                    click_trans_id=click_trans_id,
                    click_paydoc_id=click_paydoc_id,
                    merchant_trans_id=merchant_trans_id,
                    amount=amount,
                    action=action,
                    sign_time=sign_time,
                    sign_string=sign_string,
                    service_id=service_id,
                )
            else:  # Complete
                result = await payment_service.process_click_complete(
                    click_trans_id=click_trans_id,
                    click_paydoc_id=click_paydoc_id,
                    merchant_trans_id=merchant_trans_id,
                    merchant_prepare_id=_get_value("merchant_prepare_id", ""),
                    amount=amount,
                    action=action,
                    sign_time=sign_time,
                    sign_string=sign_string,
                    error=error,
                    service_id=service_id,
                )

            return web.json_response(result)
        except Exception as e:
            logger.error(f"Click callback error: {e}")
            return web.json_response({"error": -1, "error_note": str(e)})

    return api_click_callback


def build_payme_callback():
    async def api_payme_callback(request: web.Request) -> web.Response:
        """POST /api/v1/payment/payme/callback - Payme JSON-RPC callback."""
        try:
            # Verify authorization
            payment_service = get_payment_service()
            auth_header = request.headers.get("Authorization", "")

            if not payment_service.verify_payme_signature(auth_header):
                return web.json_response(
                    {"error": {"code": -32504, "message": "Unauthorized"}, "id": None}, status=401
                )

            data = await request.json()
            method = data.get("method", "")
            params = data.get("params", {})
            request_id = data.get("id")

            result = await payment_service.process_payme_request(method, params, request_id)
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Payme callback error: {e}")
            return web.json_response({"error": {"code": -32400, "message": str(e)}, "id": None})

    return api_payme_callback
