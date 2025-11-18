"""PostgreSQL-based FSM storage for persistent state management."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey


class PostgreSQLStorage(BaseStorage):
    """PostgreSQL-based FSM storage using existing database connection."""

    def __init__(self, db):
        """Initialize with database instance."""
        self.db = db

    async def set_state(
        self, key: StorageKey, state: StateType = None
    ) -> None:
        """Set state for user."""
        user_id = key.user_id
        state_str = state.state if state else None
        
        cursor = self.db.conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO fsm_states (user_id, state, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id)
                DO UPDATE SET state = EXCLUDED.state, updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, state_str)
            )
            self.db.conn.commit()
        finally:
            cursor.close()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        """Get state for user."""
        user_id = key.user_id
        
        cursor = self.db.conn.cursor()
        try:
            cursor.execute(
                "SELECT state FROM fsm_states WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            cursor.close()

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        """Set data for user."""
        user_id = key.user_id
        data_json = json.dumps(data)
        
        cursor = self.db.conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO fsm_states (user_id, data, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id)
                DO UPDATE SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, data_json)
            )
            self.db.conn.commit()
        finally:
            cursor.close()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        """Get data for user."""
        user_id = key.user_id
        
        cursor = self.db.conn.cursor()
        try:
            cursor.execute(
                "SELECT data FROM fsm_states WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            if result and result[0]:
                return json.loads(result[0])
            return {}
        finally:
            cursor.close()

    async def close(self) -> None:
        """Close storage (database connection managed elsewhere)."""
        pass
