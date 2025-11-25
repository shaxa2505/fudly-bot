"""
User-related database operations.
"""
from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class UserMixin:
    """Mixin for user-related database operations."""

    def add_user(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        phone: str | None = None,
        city: str = "Ташкент",
        language: str = "ru",
    ) -> None:
        """Add or update user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (user_id, username, first_name, phone, city, language)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    phone = COALESCE(EXCLUDED.phone, users.phone),
                    city = COALESCE(EXCLUDED.city, users.city),
                    language = EXCLUDED.language
            """,
                (user_id, username, first_name, phone, city, language),
            )
            logger.info(f"User {user_id} added/updated")

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        """Get user by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def update_user_phone(self, user_id: int, phone: str):
        """Update user phone."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET phone = %s WHERE user_id = %s", (phone, user_id))

    def update_user_city(self, user_id: int, city: str):
        """Update user city."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET city = %s WHERE user_id = %s", (city, user_id))

    def update_user_language(self, user_id: int, language: str):
        """Update user language."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET language = %s WHERE user_id = %s", (language, user_id))

    def get_user_language(self, user_id: int) -> str:
        """Get user language."""
        user = self.get_user(user_id)
        return user["language"] if user else "ru"

    def get_user_model(self, user_id: int) -> User | None:
        """Return user as Pydantic model."""
        try:
            from app.domain import User
        except ImportError:
            logger.error("Domain models not available. Install pydantic.")
            return None

        user_dict = self.get_user(user_id)
        if not user_dict:
            return None

        try:
            if not user_dict.get("first_name"):
                user_dict["first_name"] = user_dict.get("username") or ""
            if not user_dict.get("city"):
                user_dict["city"] = "Ташкент"
            if user_dict.get("language") is None:
                user_dict["language"] = "ru"
        except Exception:
            pass

        try:
            return User.from_db_row(user_dict)
        except Exception as e:
            logger.error(f"Failed to convert user {user_id} to model: {e}")
            return None

    def toggle_notifications(self, user_id: int) -> bool:
        """Toggle notifications_enabled flag; return new state."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE users
                SET notifications_enabled = CASE WHEN notifications_enabled = 1 THEN 0 ELSE 1 END
                WHERE user_id = %s
                RETURNING notifications_enabled
            """,
                (user_id,),
            )
            result = cursor.fetchone()
            if result is None:
                return True
            new_val = result[0]
            return new_val == 1

    def update_user_role(self, user_id: int, role: str):
        """Update user role."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET role = %s WHERE user_id = %s", (role, user_id))

    def get_all_users(self):
        """Get all users."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_all_admins(self):
        """Return list of admin user_ids."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE is_admin = 1")
            return [row[0] for row in cursor.fetchall()]

    def set_admin(self, user_id: int):
        """Make user an admin."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_admin = 1, role = %s WHERE user_id = %s", ("admin", user_id)
            )

    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_admin FROM users WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            return bool(result and result[0] == 1)

    def delete_user(self, user_id: int):
        """Delete user and related data."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # First delete related records
            cursor.execute("DELETE FROM notifications WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM favorites WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM ratings WHERE user_id = %s", (user_id,))

            # Get user's stores
            cursor.execute("SELECT store_id FROM stores WHERE owner_id = %s", (user_id,))
            stores = cursor.fetchall()
            for store in stores:
                store_id = store[0]
                cursor.execute("DELETE FROM offers WHERE store_id = %s", (store_id,))
                cursor.execute("DELETE FROM payment_settings WHERE store_id = %s", (store_id,))

            cursor.execute("DELETE FROM stores WHERE owner_id = %s", (user_id,))
            cursor.execute("DELETE FROM bookings WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM orders WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            logger.info(f"User {user_id} and related data deleted")
