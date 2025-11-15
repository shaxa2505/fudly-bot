"""Custom exceptions for Fudly Bot."""
from __future__ import annotations


class FudlyException(Exception):
    """Base exception for all Fudly Bot errors."""

    def __init__(self, message: str, *args: object) -> None:
        super().__init__(message, *args)
        self.message = message


class DatabaseException(FudlyException):
    """Database-related errors."""

    pass


class ConnectionPoolException(DatabaseException):
    """Database connection pool errors."""

    pass


class UserNotFoundException(FudlyException):
    """User not found in database."""

    def __init__(self, user_id: int) -> None:
        super().__init__(f"User with ID {user_id} not found")
        self.user_id = user_id


class StoreNotFoundException(FudlyException):
    """Store not found in database."""

    def __init__(self, store_id: int) -> None:
        super().__init__(f"Store with ID {store_id} not found")
        self.store_id = store_id


class OfferNotFoundException(FudlyException):
    """Offer not found in database."""

    def __init__(self, offer_id: int) -> None:
        super().__init__(f"Offer with ID {offer_id} not found")
        self.offer_id = offer_id


class BookingNotFoundException(FudlyException):
    """Booking not found in database."""

    def __init__(self, booking_id: int) -> None:
        super().__init__(f"Booking with ID {booking_id} not found")
        self.booking_id = booking_id


class ValidationException(FudlyException):
    """Input validation errors."""

    pass


class AuthorizationException(FudlyException):
    """Authorization/permission errors."""

    pass


class RateLimitException(FudlyException):
    """Rate limiting errors."""

    def __init__(self, user_id: int, action: str, retry_after: int) -> None:
        super().__init__(f"Rate limit exceeded for user {user_id} on action {action}")
        self.user_id = user_id
        self.action = action
        self.retry_after = retry_after


class ConfigurationException(FudlyException):
    """Configuration errors."""

    pass


class CacheException(FudlyException):
    """Cache-related errors."""

    pass
