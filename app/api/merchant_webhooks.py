"""
Uzum Merchant API webhook endpoints.

Implements partner-side webhooks (/check, /create, /confirm, /reverse, /status)
with Basic Auth as required by Uzum Bank.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.async_db import AsyncDBProxy
from app.api.rate_limit import limiter
from app.domain.order import PaymentStatus

router = APIRouter(prefix="/api/merchant", tags=["merchant"])
security = HTTPBasic()
_db: Any = None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _is_dev_env() -> bool:
    return os.getenv("ENVIRONMENT", "production").lower() in ("development", "dev", "local", "test")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


async def _require_signature(request: Request) -> None:
    """Optional HMAC signature verification for merchant webhooks."""
    secret = os.getenv("UZUM_MERCHANT_WEBHOOK_SECRET")
    require_sig = _env_flag("UZUM_MERCHANT_REQUIRE_SIGNATURE", False)
    if not secret:
        if require_sig and not _is_dev_env():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Merchant webhook signature not configured",
            )
        return

    signature = request.headers.get("X-Uzum-Signature") or request.headers.get("X-Signature")
    if not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")

    body = await request.body()
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")


def _require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Validate Basic Auth credentials."""
    environment = os.getenv("ENVIRONMENT", "production").lower()
    is_dev = environment in ("development", "dev", "local", "test")

    default_user = "fudly_merchant"
    default_pass = "Fudly#Uzum_2024!pQ7s"
    expected_user = os.getenv("UZUM_MERCHANT_LOGIN")
    expected_pass = os.getenv("UZUM_MERCHANT_PASSWORD")

    if not expected_user or not expected_pass:
        if is_dev:
            expected_user = expected_user or default_user
            expected_pass = expected_pass or default_pass
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Merchant credentials not configured",
            )

    if not is_dev and (
        expected_user == default_user or expected_pass == default_pass
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Merchant credentials not configured",
        )

    if not (
        secrets.compare_digest(credentials.username, expected_user)
        and secrets.compare_digest(credentials.password, expected_pass)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _get(data: dict, key: str, default: Any = None) -> Any:
    return data.get(key, default) if isinstance(data, dict) else default


def _require_db():
    if _db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    return _db


def set_merchant_db(db: Any) -> None:
    """Called from api_server to inject DB."""
    global _db
    if db is None:
        _db = None
        return
    if not isinstance(db, AsyncDBProxy):
        db = AsyncDBProxy(db)
    _db = db


def _extract_order_id(params: dict) -> int | None:
    """Expect params.account (string/int) to carry order_id."""
    if not isinstance(params, dict):
        return None
    account = params.get("account") or params.get("order_id")
    if account is None:
        return None
    try:
        return int(account)
    except (TypeError, ValueError):
        return None


async def _fetch_transaction(db, trans_id: str):
    try:
        return await db.get_uzum_transaction(trans_id)
    except Exception:
        return None


def _normalize_tx_status(raw_status: Any) -> str:
    return str(raw_status or "").strip().upper()


def _payment_is_confirmed(order: Any) -> bool:
    if not order:
        return False
    payment_status = PaymentStatus.normalize(
        order.get("payment_status") if isinstance(order, dict) else getattr(order, "payment_status", None),
        payment_method=order.get("payment_method") if isinstance(order, dict) else getattr(order, "payment_method", None),
        payment_proof_photo_id=order.get("payment_proof_photo_id")
        if isinstance(order, dict)
        else getattr(order, "payment_proof_photo_id", None),
    )
    return payment_status == PaymentStatus.CONFIRMED


def _allow_reverse_after_confirm() -> bool:
    return _env_flag("UZUM_ALLOW_REVERSE_AFTER_CONFIRM", False)


@router.post("/check")
@limiter.limit("120/minute")
async def check(
    payload: dict,
    request: Request,
    _: str = Depends(_require_auth),
    __: None = Depends(_require_signature),
    db=Depends(_require_db),
) -> dict:
    """Webhook: validate if payment is possible."""
    service_id = _get(payload, "serviceId")
    timestamp = _get(payload, "timestamp", _now_ms())
    params = _get(payload, "params", {})
    order_id = _extract_order_id(params)

    if not (service_id and order_id):
        raise HTTPException(status_code=400, detail="Missing serviceId or account (order_id)")

    order = await db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=400, detail="Order not found")
    if _payment_is_confirmed(order):
        raise HTTPException(status_code=409, detail="Order already paid")

    return {
        "serviceId": service_id,
        "timestamp": timestamp,
        "status": "OK",
        "data": {k: {"value": str(v)} for k, v in params.items()},
    }


@router.post("/create")
@limiter.limit("120/minute")
async def create(
    payload: dict,
    request: Request,
    _: str = Depends(_require_auth),
    __: None = Depends(_require_signature),
    db=Depends(_require_db),
) -> dict:
    """Webhook: create a payment transaction."""
    service_id = _get(payload, "serviceId")
    trans_id = _get(payload, "transId") or str(uuid.uuid4())
    params = _get(payload, "params", {})
    amount = _get(payload, "amount")
    order_id = _extract_order_id(params)

    if not (service_id and trans_id and order_id and amount):
        raise HTTPException(status_code=400, detail="Missing required fields")

    order = await db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=400, detail="Order not found")
    if _payment_is_confirmed(order):
        raise HTTPException(status_code=409, detail="Order already paid")

    # Prevent duplicate transId
    existing = await _fetch_transaction(db, trans_id)
    if existing:
        existing_status = _normalize_tx_status(existing.get("status"))
        existing_order_id = int(existing.get("order_id") or 0)
        existing_amount = int(existing.get("amount") or 0)
        existing_service_id = str(existing.get("service_id") or "")
        if existing_order_id and existing_order_id != int(order_id):
            raise HTTPException(status_code=400, detail="Transaction order mismatch")
        if existing_service_id and str(service_id) != existing_service_id:
            raise HTTPException(status_code=400, detail="ServiceId mismatch")
        if existing_amount and int(amount) != existing_amount:
            raise HTTPException(status_code=400, detail="Amount mismatch")
        return {
            "serviceId": service_id,
            "transId": trans_id,
            "status": existing_status or "CREATED",
            "transTime": _now_ms(),
            "data": {k: {"value": str(v)} for k, v in params.items()},
            "amount": existing_amount or amount,
        }

    try:
        await db.create_uzum_transaction(
            trans_id=trans_id,
            order_id=order_id,
            service_id=service_id,
            amount=int(amount),
            status="CREATED",
            payload=payload,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to persist transaction")

    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": "CREATED",
        "transTime": _now_ms(),
        "data": {k: {"value": str(v)} for k, v in params.items()},
        "amount": amount,
    }


@router.post("/confirm")
@limiter.limit("120/minute")
async def confirm(
    payload: dict,
    request: Request,
    _: str = Depends(_require_auth),
    __: None = Depends(_require_signature),
    db=Depends(_require_db),
) -> dict:
    """Webhook: confirm a successful payment."""
    service_id = _get(payload, "serviceId")
    trans_id = _get(payload, "transId")
    amount = _get(payload, "amount")

    if not (service_id and trans_id and amount):
        raise HTTPException(status_code=400, detail="Missing required fields")

    tx = await _fetch_transaction(db, trans_id)
    if not tx:
        raise HTTPException(status_code=400, detail="Transaction not found")

    if str(tx.get("service_id")) != str(service_id):
        raise HTTPException(status_code=400, detail="ServiceId mismatch")

    if int(tx.get("amount") or 0) != int(amount):
        raise HTTPException(status_code=400, detail="Amount mismatch")

    order_id = tx.get("order_id")
    tx_status = _normalize_tx_status(tx.get("status"))
    if tx_status == "CONFIRMED":
        return {
            "serviceId": service_id,
            "transId": trans_id,
            "status": "CONFIRMED",
            "confirmTime": _now_ms(),
            "data": _get(payload, "data", {}),
            "amount": amount,
        }
    if tx_status == "REVERSED":
        raise HTTPException(status_code=409, detail="Transaction reversed")

    order = await db.get_order(order_id) if order_id else None
    if not order:
        raise HTTPException(status_code=400, detail="Order not found")
    try:
        await db.update_uzum_transaction_status(trans_id, "CONFIRMED", payload)
        service = None
        try:
            from app.services.unified_order_service import get_unified_order_service

            service = get_unified_order_service()
        except Exception:
            service = None

        if _payment_is_confirmed(order):
            return {
                "serviceId": service_id,
                "transId": trans_id,
                "status": "CONFIRMED",
                "confirmTime": _now_ms(),
                "data": _get(payload, "data", {}),
                "amount": amount,
            }
        if service and order_id:
            await service.confirm_payment(int(order_id))
        elif hasattr(db, "update_payment_status") and order_id:
            await db.update_payment_status(order_id, "confirmed")
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to update transaction")

    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": "CONFIRMED",
        "confirmTime": _now_ms(),
        "data": _get(payload, "data", {}),
        "amount": amount,
    }


@router.post("/reverse")
@limiter.limit("120/minute")
async def reverse(
    payload: dict,
    request: Request,
    _: str = Depends(_require_auth),
    __: None = Depends(_require_signature),
    db=Depends(_require_db),
) -> dict:
    """Webhook: reverse a payment."""
    service_id = _get(payload, "serviceId")
    trans_id = _get(payload, "transId")

    if not (service_id and trans_id):
        raise HTTPException(status_code=400, detail="Missing required fields")

    tx = await _fetch_transaction(db, trans_id)
    if not tx:
        raise HTTPException(status_code=400, detail="Transaction not found")
    if str(tx.get("service_id")) != str(service_id):
        raise HTTPException(status_code=400, detail="ServiceId mismatch")

    order_id = tx.get("order_id")
    tx_status = _normalize_tx_status(tx.get("status"))
    if tx_status == "REVERSED":
        return {
            "serviceId": service_id,
            "transId": trans_id,
            "status": "REVERSED",
            "reverseTime": _now_ms(),
            "data": _get(payload, "data", {}),
            "amount": _get(payload, "amount"),
        }
    if tx_status == "CONFIRMED" and not _allow_reverse_after_confirm():
        raise HTTPException(status_code=409, detail="Transaction already confirmed")

    order = await db.get_order(order_id) if order_id else None
    if order and _payment_is_confirmed(order) and not _allow_reverse_after_confirm():
        raise HTTPException(status_code=409, detail="Order already paid")
    try:
        await db.update_uzum_transaction_status(trans_id, "REVERSED", payload)
        if hasattr(db, "update_payment_status") and order_id:
            await db.update_payment_status(order_id, "rejected")
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to update transaction")

    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": "REVERSED",
        "reverseTime": _now_ms(),
        "data": _get(payload, "data", {}),
        "amount": _get(payload, "amount"),
    }


@router.post("/status")
@limiter.limit("120/minute")
async def status_check(
    payload: dict,
    request: Request,
    _: str = Depends(_require_auth),
    __: None = Depends(_require_signature),
    db=Depends(_require_db),
) -> dict:
    """Webhook: check transaction status."""
    service_id = _get(payload, "serviceId")
    trans_id = _get(payload, "transId")

    if not (service_id and trans_id):
        raise HTTPException(status_code=400, detail="Missing required fields")

    tx = await _fetch_transaction(db, trans_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": tx.get("status", "CREATED"),
        "transTime": _now_ms(),
        "confirmTime": None if tx.get("status") != "CONFIRMED" else _now_ms(),
        "reverseTime": None if tx.get("status") != "REVERSED" else _now_ms(),
        "data": tx.get("payload") or {},
        "amount": tx.get("amount"),
    }
