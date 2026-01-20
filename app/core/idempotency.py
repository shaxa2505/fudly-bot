"""
Idempotency helpers for order creation.

Stores request hashes and cached responses to prevent duplicate orders.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_IDEMPOTENCY_READY = False


def normalize_idempotency_key(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def build_request_hash(payload: dict[str, Any]) -> str:
    """Generate a stable hash for a request payload."""
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _ensure_idempotency_table(db: Any) -> bool:
    global _IDEMPOTENCY_READY
    if _IDEMPOTENCY_READY:
        return True
    if not hasattr(db, "get_connection"):
        return False
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idempotency_key TEXT NOT NULL,
                    user_id BIGINT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_body TEXT,
                    status_code INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (idempotency_key, user_id)
                )
                """
            )
        _IDEMPOTENCY_READY = True
        return True
    except Exception as exc:
        logger.warning("Failed to ensure idempotency table: %s", exc)
        return False


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "get"):
        return row.get(key)
    try:
        return row[index]
    except Exception:
        return None


def _fetch_idempotency_record(db: Any, key: str, user_id: int) -> tuple[str | None, str | None, int | None] | None:
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT request_hash, response_body, status_code
            FROM idempotency_keys
            WHERE idempotency_key = %s AND user_id = %s
            """,
            (key, int(user_id)),
        )
        row = cursor.fetchone()
        if not row:
            return None
        request_hash = _row_value(row, "request_hash", 0)
        response_body = _row_value(row, "response_body", 1)
        status_code = _row_value(row, "status_code", 2)
        return (
            str(request_hash) if request_hash is not None else None,
            str(response_body) if response_body is not None else None,
            int(status_code) if status_code is not None else None,
        )


def check_or_reserve_key(
    db: Any,
    key: str | None,
    user_id: int,
    request_hash: str,
) -> dict[str, Any]:
    """Return cached response or reserve idempotency key for processing."""
    key = normalize_idempotency_key(key)
    if not key:
        return {"status": "skip"}
    if not _ensure_idempotency_table(db):
        return {"status": "skip"}

    for _ in range(2):
        existing = _fetch_idempotency_record(db, key, user_id)
        if existing:
            stored_hash, response_body, status_code = existing
            if stored_hash and stored_hash != request_hash:
                return {
                    "status": "conflict",
                    "payload": {"detail": "Idempotency key reuse with different payload"},
                    "status_code": 409,
                }
            if response_body and status_code is not None:
                try:
                    payload = json.loads(response_body)
                except Exception:
                    payload = {"detail": "Cached response unavailable"}
                return {"status": "cached", "payload": payload, "status_code": int(status_code)}
            return {
                "status": "in_progress",
                "payload": {"detail": "Request in progress"},
                "status_code": 409,
            }

        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO idempotency_keys (idempotency_key, user_id, request_hash)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (key, int(user_id), request_hash),
                )
                if cursor.rowcount > 0:
                    return {"status": "reserved", "key": key}
        except Exception as exc:
            logger.warning("Failed to reserve idempotency key: %s", exc)
            return {"status": "skip"}

    return {"status": "conflict", "payload": {"detail": "Idempotency conflict"}, "status_code": 409}


def store_idempotency_response(
    db: Any,
    key: str | None,
    user_id: int,
    request_hash: str,
    payload: dict[str, Any],
    status_code: int,
) -> None:
    key = normalize_idempotency_key(key)
    if not key:
        return
    if not _ensure_idempotency_table(db):
        return
    try:
        response_body = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        return

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE idempotency_keys
                SET response_body = %s, status_code = %s
                WHERE idempotency_key = %s AND user_id = %s AND request_hash = %s
                """,
                (
                    response_body,
                    int(status_code),
                    key,
                    int(user_id),
                    request_hash,
                ),
            )
    except Exception as exc:
        logger.warning("Failed to store idempotency response: %s", exc)
