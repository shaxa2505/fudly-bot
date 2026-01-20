"""PostgreSQL-based FSM storage for persistent state management."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

# Thread pool for running sync DB operations without blocking event loop
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="fsm_db_")


class PostgreSQLStorage(BaseStorage):
    """PostgreSQL-based FSM storage using existing database connection pool.

    Uses ThreadPoolExecutor to run synchronous database operations
    without blocking the asyncio event loop.
    """

    def __init__(self, db):
        """Initialize with database instance."""
        self.db = db

    async def _run_in_executor(self, func, *args):
        """Run synchronous function in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, partial(func, *args))

    def _set_state_sync(self, user_id: int, chat_id: int, state_str: str | None) -> None:
        """Synchronous set_state implementation."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO fsm_states (user_id, chat_id, state, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, chat_id)
                DO UPDATE SET state = EXCLUDED.state, updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, chat_id, state_str),
            )

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        """Set state for user."""
        user_id = key.user_id
        chat_id = key.chat_id
        state_str = state.state if state else None
        await self._run_in_executor(self._set_state_sync, user_id, chat_id, state_str)

    def _get_state_sync(self, user_id: int, chat_id: int) -> str | None:
        """Synchronous get_state implementation."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT state FROM fsm_states WHERE user_id = %s AND chat_id = %s",
                (user_id, chat_id),
            )
            result = cursor.fetchone()
            return str(result[0]) if result and result[0] else None

    async def get_state(self, key: StorageKey) -> str | None:
        """Get state for user."""
        result = await self._run_in_executor(self._get_state_sync, key.user_id, key.chat_id)
        return str(result) if result else None

    def _set_data_sync(self, user_id: int, chat_id: int, data_json: str) -> None:
        """Synchronous set_data implementation."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO fsm_states (user_id, chat_id, data, updated_at)
                VALUES (%s, %s, %s::jsonb, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, chat_id)
                DO UPDATE SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, chat_id, data_json),
            )

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        """Set data for user."""
        data_json = json.dumps(data)
        await self._run_in_executor(self._set_data_sync, key.user_id, key.chat_id, data_json)

    def _get_data_sync(self, user_id: int, chat_id: int) -> dict[str, Any]:
        """Synchronous get_data implementation."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data FROM fsm_states WHERE user_id = %s AND chat_id = %s",
                (user_id, chat_id),
            )
            result = cursor.fetchone()
            if result and result[0]:
                # PostgreSQL JSONB returns dict directly, not string
                if isinstance(result[0], dict):
                    return dict(result[0])
                data = json.loads(result[0])
                return dict(data) if isinstance(data, dict) else {}
            return {}

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        """Get data for user."""
        result = await self._run_in_executor(self._get_data_sync, key.user_id, key.chat_id)
        return dict(result) if isinstance(result, dict) else {}

    async def close(self) -> None:
        """Close storage (database connection managed elsewhere)."""
        _executor.shutdown(wait=False)
