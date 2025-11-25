"""Base repository with common database operations."""
from __future__ import annotations

from typing import Any, Protocol

from app.core.exceptions import DatabaseException


class DatabaseProtocol(Protocol):
    """Protocol for database operations."""

    def get_connection(self) -> Any:
        """Get database connection."""
        ...


class BaseRepository:
    """Base repository class with common CRUD operations."""

    def __init__(self, db: DatabaseProtocol) -> None:
        """Initialize repository with database instance.

        Args:
            db: Database instance implementing DatabaseProtocol
        """
        self.db = db

    def _handle_db_error(self, operation: str, error: Exception) -> None:
        """Handle database errors consistently.

        Args:
            operation: Name of the operation that failed
            error: Original exception

        Raises:
            DatabaseException: Wrapped database error
        """
        raise DatabaseException(f"Database operation '{operation}' failed: {str(error)}") from error

    def _get_field(self, obj: Any, field_name: str, default: Any = None) -> Any:
        """Safely extract field from object (dict or tuple).

        Args:
            obj: Object to extract field from
            field_name: Name of the field
            default: Default value if field not found

        Returns:
            Field value or default
        """
        if not obj:
            return default
        if isinstance(obj, dict):
            return obj.get(field_name, default)
        return default
