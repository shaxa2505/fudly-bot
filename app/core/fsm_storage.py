"""
Enhanced PostgreSQL FSM Storage with TTL, chat_id support, and async operations.

Improvements over original:
1. Composite key (user_id + chat_id) - prevents state mixing across chats
2. TTL support - auto-expire abandoned states
3. Better async handling
4. State metadata tracking
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

logger = logging.getLogger("fudly.fsm")


def _utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class EnhancedPostgreSQLStorage(BaseStorage):
    """
    PostgreSQL-based FSM storage with enhanced features.

    Features:
    - Composite key (user_id:chat_id) for proper isolation
    - TTL-based expiration for abandoned states
    - Metadata tracking (created_at, updated_at, state_history)
    - Graceful fallback for sync database connections
    """

    DEFAULT_TTL_HOURS = 24  # States expire after 24 hours of inactivity

    def __init__(self, db: Any, ttl_hours: int = DEFAULT_TTL_HOURS):
        """
        Initialize storage.

        Args:
            db: Database instance with get_connection() method
            ttl_hours: Hours until state expires (default: 24)
        """
        self.db = db
        self.ttl = timedelta(hours=ttl_hours)
        self._ensure_table()

    def _make_key(self, key: StorageKey) -> str:
        """Create composite key from user_id and chat_id."""
        return f"{key.user_id}:{key.chat_id}"

    def _ensure_table(self) -> None:
        """Ensure fsm_states table exists with new schema."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # Check if expires_at column exists
                cursor.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'fsm_states' AND column_name = 'expires_at'
                """
                )
                if not cursor.fetchone():
                    # Add new columns if they don't exist
                    logger.info("Upgrading fsm_states table schema...")
                    cursor.execute(
                        """
                        ALTER TABLE fsm_states
                        ADD COLUMN IF NOT EXISTS chat_id BIGINT,
                        ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP,
                        ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        ADD COLUMN IF NOT EXISTS state_name TEXT
                    """
                    )
                    conn.commit()
                    logger.info("✅ FSM table schema upgraded")

                # Ensure composite unique index on (user_id, chat_id)
                try:
                    cursor.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS fsm_states_user_chat_idx
                        ON fsm_states (user_id, chat_id)
                        """
                    )
                    conn.commit()
                except Exception as index_err:
                    logger.warning(f"Could not ensure FSM unique index: {index_err}")
        except Exception as e:
            logger.warning(f"Could not upgrade fsm_states schema: {e}")

    def _calculate_expiry(self) -> datetime:
        """Calculate expiration timestamp."""
        return _utc_now() + self.ttl

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        """
        Set state for user in specific chat.

        Args:
            key: StorageKey with user_id and chat_id
            state: State to set (None to clear)
        """
        user_id = key.user_id
        chat_id = key.chat_id

        # Extract state string
        if state is None:
            state_str = None
            state_name = None
        elif isinstance(state, State):
            state_str = state.state
            state_name = state_str.split(":")[-1] if state_str else None
        else:
            state_str = str(state) if state else None
            state_name = state_str.split(":")[-1] if state_str else None

        expires_at = self._calculate_expiry()

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO fsm_states (user_id, chat_id, state, state_name, expires_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, chat_id)
                    DO UPDATE SET
                        state = EXCLUDED.state,
                        state_name = EXCLUDED.state_name,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, chat_id, state_str, state_name, expires_at),
                )
                conn.commit()

            if state_str:
                logger.debug(f"FSM state set: user={user_id}, chat={chat_id}, state={state_name}")
            else:
                logger.debug(f"FSM state cleared: user={user_id}, chat={chat_id}")

        except Exception as e:
            logger.error(f"Failed to set FSM state: {e}")

    async def get_state(self, key: StorageKey) -> str | None:
        """
        Get current state for user.

        Returns None if state doesn't exist or has expired.
        """
        user_id = key.user_id
        chat_id = key.chat_id

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT state FROM fsm_states
                    WHERE user_id = %s AND chat_id = %s
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    """,
                    (user_id, chat_id),
                )
                result = cursor.fetchone()
                if result:
                    state_value: str | None = result[0]
                    return state_value
                return None
        except Exception as e:
            logger.error(f"Failed to get FSM state: {e}")
            return None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        """
        Set FSM data for user.

        Data is stored as JSONB for efficient querying.
        """
        user_id = key.user_id
        chat_id = key.chat_id

        # Add metadata to data
        data_with_meta: dict[str, Any] = {
            **data,
            "_updated_at": _utc_now().isoformat(),
        }
        data_json = json.dumps(data_with_meta, default=str)
        expires_at = self._calculate_expiry()

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO fsm_states (user_id, chat_id, data, expires_at, updated_at)
                    VALUES (%s, %s, %s::jsonb, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, chat_id)
                    DO UPDATE SET
                        data = EXCLUDED.data,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, chat_id, data_json, expires_at),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to set FSM data: {e}")

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        """
        Get FSM data for user.

        Returns empty dict if data doesn't exist or has expired.
        """
        user_id = key.user_id
        chat_id = key.chat_id

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT data FROM fsm_states
                    WHERE user_id = %s AND chat_id = %s
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    """,
                    (user_id, chat_id),
                )
                result = cursor.fetchone()

                if result and result[0]:
                    raw_data: Any = result[0]
                    # Handle both dict and string responses
                    if isinstance(raw_data, dict):
                        # Remove internal metadata before returning
                        data_dict = cast(dict[str, Any], raw_data)
                        filtered: dict[str, Any] = {
                            k: v for k, v in data_dict.items() if not k.startswith("_")
                        }
                        return filtered
                    data_result: dict[str, Any] = json.loads(str(raw_data))
                    return data_result
                return {}
        except Exception as e:
            logger.error(f"Failed to get FSM data: {e}")
            return {}

    async def close(self) -> None:
        """Close storage (database connection managed elsewhere)."""
        pass

    # ========== Extended Methods ==========

    async def get_state_info(self, key: StorageKey) -> dict[str, Any] | None:
        """
        Get full state info including metadata.

        Returns:
            Dict with state, data, created_at, updated_at, expires_at
            or None if not found
        """
        user_id = key.user_id
        chat_id = key.chat_id

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT state, state_name, data, created_at, updated_at, expires_at
                    FROM fsm_states
                    WHERE user_id = %s AND chat_id = %s
                    """,
                    (user_id, chat_id),
                )
                result = cursor.fetchone()

                if result:
                    return {
                        "state": result[0],
                        "state_name": result[1],
                        "data": result[2] or {},
                        "created_at": result[3],
                        "updated_at": result[4],
                        "expires_at": result[5],
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to get FSM state info: {e}")
            return None

    async def cleanup_expired(self) -> int:
        """
        Remove expired FSM states.

        Returns:
            Number of deleted rows
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM fsm_states
                    WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP
                    """
                )
                deleted: int = cursor.rowcount or 0
                conn.commit()

                if deleted > 0:
                    logger.info(f"🧹 Cleaned up {deleted} expired FSM states")
                return deleted
        except Exception as e:
            logger.error(f"Failed to cleanup expired FSM states: {e}")
            return 0

    async def get_active_states_count(self) -> dict[str, int]:
        """
        Get count of active states by state name.

        Returns:
            Dict mapping state_name to count
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT state_name, COUNT(*)
                    FROM fsm_states
                    WHERE state IS NOT NULL
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    GROUP BY state_name
                    """
                )
                return {row[0]: row[1] for row in cursor.fetchall() if row[0]}
        except Exception as e:
            logger.error(f"Failed to get active states count: {e}")
            return {}


# Alias for backward compatibility
PostgreSQLStorage = EnhancedPostgreSQLStorage
