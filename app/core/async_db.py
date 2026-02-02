"""Async helper wrappers for sync database adapters."""
from __future__ import annotations

from typing import Any, Callable, TypeVar

import anyio

T = TypeVar("T")


class AsyncDBProxy:
    """Proxy that runs sync DB calls in a thread pool."""

    def __init__(self, db: Any):
        self._db = db

    @property
    def sync(self) -> Any:
        """Expose underlying sync DB (use sparingly)."""
        return self._db

    async def run(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run a sync callable in a worker thread."""
        return await anyio.to_thread.run_sync(lambda: func(*args, **kwargs))

    def __getattr__(self, name: str):
        attr = getattr(self._db, name)
        if not callable(attr):
            return attr

        async def _call(*args: Any, **kwargs: Any):
            return await anyio.to_thread.run_sync(lambda: attr(*args, **kwargs))

        return _call

