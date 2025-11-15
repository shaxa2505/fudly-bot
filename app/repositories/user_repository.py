"""User repository for user-related database operations."""
from __future__ import annotations

from typing import Any, Optional

from app.core.exceptions import DatabaseException, UserNotFoundException
from app.core.utils import get_user_field

from .base import BaseRepository


class UserRepository(BaseRepository):
    """Repository for user-related database operations."""

    def get_user(self, user_id: int) -> Optional[dict[str, Any]]:
        """Get user by ID.

        Args:
            user_id: Telegram user ID

        Returns:
            User data as dict or None if not found

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_user(user_id)
        except Exception as e:
            self._handle_db_error("get_user", e)

    def get_user_or_raise(self, user_id: int) -> dict[str, Any]:
        """Get user by ID or raise exception.

        Args:
            user_id: Telegram user ID

        Returns:
            User data as dict

        Raises:
            UserNotFoundException: If user not found
            DatabaseException: If database operation fails
        """
        user = self.get_user(user_id)
        if not user:
            raise UserNotFoundException(user_id)
        return user

    def add_user(
        self,
        user_id: int,
        language: str = "ru",
        first_name: Optional[str] = None,
        phone: Optional[str] = None,
        city: Optional[str] = None,
    ) -> None:
        """Add new user.

        Args:
            user_id: Telegram user ID
            language: User language code
            first_name: User's first name
            phone: User's phone number
            city: User's city

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.add_user(user_id, language, first_name, phone, city)
        except Exception as e:
            self._handle_db_error("add_user", e)

    def update_user(
        self,
        user_id: int,
        first_name: Optional[str] = None,
        phone: Optional[str] = None,
        city: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        """Update user data.

        Args:
            user_id: Telegram user ID
            first_name: New first name
            phone: New phone number
            city: New city
            language: New language code

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.update_user(user_id, first_name, phone, city, language)
        except Exception as e:
            self._handle_db_error("update_user", e)

    def set_user_role(self, user_id: int, role: str) -> None:
        """Set user role.

        Args:
            user_id: Telegram user ID
            role: New role (customer, seller, admin)

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.set_user_role(user_id, role)
        except Exception as e:
            self._handle_db_error("set_user_role", e)

    def set_user_city(self, user_id: int, city: str) -> None:
        """Set user city.

        Args:
            user_id: Telegram user ID
            city: New city

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.set_user_city(user_id, city)
        except Exception as e:
            self._handle_db_error("set_user_city", e)

    def get_all_users(self) -> list[dict[str, Any]]:
        """Get all users.

        Returns:
            List of user dicts

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_all_users()
        except Exception as e:
            self._handle_db_error("get_all_users", e)
            return []

    def get_users_by_city(self, city: str) -> list[dict[str, Any]]:
        """Get users in specific city.

        Args:
            city: City name

        Returns:
            List of user dicts

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_users_by_city(city)
        except Exception as e:
            self._handle_db_error("get_users_by_city", e)
            return []

    def toggle_notifications(self, user_id: int) -> bool:
        """Toggle user notifications.

        Args:
            user_id: Telegram user ID

        Returns:
            New notification state (True=enabled, False=disabled)

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.toggle_notifications(user_id)
        except Exception as e:
            self._handle_db_error("toggle_notifications", e)
            return False
