"""
Uzum Merchant API webhook endpoints.

Implements partner-side webhooks (/check, /create, /confirm, /reverse, /status)
with Basic Auth as required by Uzum Bank.
"""
from __future__ import annotations

import os
import secrets
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

router = APIRouter(prefix="/api/merchant", tags=["merchant"])
security = HTTPBasic()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Validate Basic Auth credentials."""
    expected_user = os.getenv("UZUM_MERCHANT_LOGIN", "fudly_merchant")
    expected_pass = os.getenv("UZUM_MERCHANT_PASSWORD", "Fudly#Uzum_2024!pQ7s")

    if not (expected_user and expected_pass):
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


@router.post("/check")
async def check(payload: dict, _: str = Depends(_require_auth)) -> dict:
    """Webhook: validate if payment is possible."""
    service_id = _get(payload, "serviceId")
    timestamp = _get(payload, "timestamp", _now_ms())
    params = _get(payload, "params", {})
    return {
        "serviceId": service_id,
        "timestamp": timestamp,
        "status": "OK",
        "data": {k: {"value": str(v)} for k, v in params.items()},
    }


@router.post("/create")
async def create(payload: dict, _: str = Depends(_require_auth)) -> dict:
    """Webhook: create a payment transaction."""
    service_id = _get(payload, "serviceId")
    trans_id = _get(payload, "transId") or str(uuid.uuid4())
    params = _get(payload, "params", {})
    amount = _get(payload, "amount")
    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": "CREATED",
        "transTime": _now_ms(),
        "data": {k: {"value": str(v)} for k, v in params.items()},
        "amount": amount,
    }


@router.post("/confirm")
async def confirm(payload: dict, _: str = Depends(_require_auth)) -> dict:
    """Webhook: confirm a successful payment."""
    service_id = _get(payload, "serviceId")
    trans_id = _get(payload, "transId") or str(uuid.uuid4())
    amount = _get(payload, "amount")
    params = _get(payload, "data", {})
    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": "CONFIRMED",
        "confirmTime": _now_ms(),
        "data": params,
        "amount": amount,
    }


@router.post("/reverse")
async def reverse(payload: dict, _: str = Depends(_require_auth)) -> dict:
    """Webhook: reverse a payment."""
    service_id = _get(payload, "serviceId")
    trans_id = _get(payload, "transId") or str(uuid.uuid4())
    amount = _get(payload, "amount")
    params = _get(payload, "data", {})
    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": "REVERSED",
        "reverseTime": _now_ms(),
        "data": params,
        "amount": amount,
    }


@router.post("/status")
async def status_check(payload: dict, _: str = Depends(_require_auth)) -> dict:
    """Webhook: check transaction status."""
    service_id = _get(payload, "serviceId")
    trans_id = _get(payload, "transId") or str(uuid.uuid4())
    amount = _get(payload, "amount")
    params = _get(payload, "data", {})
    # For stub purposes return CONFIRMED; adjust to real status lookup if needed.
    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": "CONFIRMED",
        "transTime": _now_ms(),
        "confirmTime": _now_ms(),
        "reverseTime": None,
        "data": params,
        "amount": amount,
    }
