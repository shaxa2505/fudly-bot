"""PostgreSQL-based FSM storage for persistent state management."""
from __future__ import annotations

import json
from typing import Any

from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey


class PostgreSQLStorage(BaseStorage):
    """PostgreSQL-based FSM storage using existing database connection pool."""

    def __init__(self, db):
        """Initialize with database instance."""
        self.db = db

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        """Set state for user."""
        user_id = key.user_id
        state_str = state.state if state else None

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO fsm_states (user_id, state, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id)
                DO UPDATE SET state = EXCLUDED.state, updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, state_str),
            )

    async def get_state(self, key: StorageKey) -> str | None:
        """Get state for user."""
        user_id = key.user_id

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT state FROM fsm_states WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        """Set data for user."""
        user_id = key.user_id
        # PostgreSQL JSONB column needs JSON string, not dict
        data_json = json.dumps(data)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO fsm_states (user_id, data, updated_at)
                VALUES (%s, %s::jsonb, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id)
                DO UPDATE SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, data_json),
            )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        """Get data for user."""
        user_id = key.user_id

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM fsm_states WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            if result and result[0]:
                # PostgreSQL JSONB returns dict directly, not string
                if isinstance(result[0], dict):
                    return result[0]
                return json.loads(result[0])
            return {}

    async def close(self) -> None:
        """Close storage (database connection managed elsewhere)."""
        pass
