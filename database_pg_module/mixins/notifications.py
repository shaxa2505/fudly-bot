"""
Notification-related database operations.
"""
from __future__ import annotations

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class NotificationMixin:
    """Mixin for notification-related database operations."""

    def add_notification(self, user_id: int, type: str, title: str, message: str):
        """Add notification."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO notifications (user_id, type, title, message)
                VALUES (%s, %s, %s, %s)
            ''', (user_id, type, title, message))

    def get_user_notifications(self, user_id: int, unread_only: bool = False):
        """Get user notifications."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if unread_only:
                cursor.execute('''
                    SELECT * FROM notifications 
                    WHERE user_id = %s AND is_read = 0 
                    ORDER BY created_at DESC
                ''', (user_id,))
            else:
                cursor.execute('''
                    SELECT * FROM notifications 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC
                ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def mark_notification_read(self, notification_id: int):
        """Mark notification as read."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE notifications SET is_read = 1 WHERE notification_id = %s', 
                         (notification_id,))
