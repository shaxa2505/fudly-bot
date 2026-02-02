"""
Real-time notification system with Pub/Sub pattern.

Supports:
- In-memory pub/sub for single instance
- Redis pub/sub for multi-instance deployments
- WebSocket connections for web clients
- Telegram push notifications
"""
import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Types of notifications."""

    # Booking notifications
    NEW_BOOKING = "new_booking"
    BOOKING_CONFIRMED = "booking_confirmed"
    BOOKING_CANCELLED = "booking_cancelled"
    BOOKING_COMPLETED = "booking_completed"
    BOOKING_EXPIRED = "booking_expired"

    # Offer notifications
    NEW_OFFER = "new_offer"
    OFFER_UPDATED = "offer_updated"
    OFFER_SOLD_OUT = "offer_sold_out"
    OFFER_EXPIRING = "offer_expiring"

    # Store notifications
    STORE_VERIFIED = "store_verified"
    STORE_REJECTED = "store_rejected"
    NEW_RATING = "new_rating"

    # System notifications
    SYSTEM_ANNOUNCEMENT = "system_announcement"
    MAINTENANCE = "maintenance"


@dataclass
class Notification:
    """Notification payload."""

    type: NotificationType
    recipient_id: int  # user_id or store_id
    title: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    priority: int = 0  # 0=normal, 1=high, 2=urgent

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type.value,
            "recipient_id": self.recipient_id,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "priority": self.priority,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Notification":
        """Create from dictionary."""
        return cls(
            type=NotificationType(data["type"]),
            recipient_id=data["recipient_id"],
            title=data["title"],
            message=data["message"],
            data=data.get("data", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            priority=data.get("priority", 0),
        )


# Type for notification handlers
NotificationHandler = Callable[[Notification], Awaitable[None]]


class PubSubBackend(ABC):
    """Abstract base for pub/sub backends."""

    @abstractmethod
    async def publish(self, channel: str, notification: Notification) -> None:
        """Publish notification to channel."""
        pass

    @abstractmethod
    async def subscribe(self, channel: str, handler: NotificationHandler) -> None:
        """Subscribe to channel with handler."""
        pass

    @abstractmethod
    async def unsubscribe(self, channel: str, handler: NotificationHandler) -> None:
        """Unsubscribe handler from channel."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close backend connections."""
        pass


class InMemoryPubSub(PubSubBackend):
    """In-memory pub/sub for single instance deployments."""

    def __init__(self):
        self._subscribers: dict[str, set[NotificationHandler]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, notification: Notification) -> None:
        """Publish to in-memory subscribers."""
        handlers = self._subscribers.get(channel, set()).copy()

        for handler in handlers:
            try:
                await handler(notification)
            except Exception as e:
                logger.error(f"Handler error in channel {channel}: {e}")

    async def subscribe(self, channel: str, handler: NotificationHandler) -> None:
        """Subscribe to channel."""
        async with self._lock:
            if channel not in self._subscribers:
                self._subscribers[channel] = set()
            self._subscribers[channel].add(handler)
            logger.debug(f"Subscribed to {channel}, total: {len(self._subscribers[channel])}")

    async def unsubscribe(self, channel: str, handler: NotificationHandler) -> None:
        """Unsubscribe from channel."""
        async with self._lock:
            if channel in self._subscribers:
                self._subscribers[channel].discard(handler)
                if not self._subscribers[channel]:
                    del self._subscribers[channel]

    async def close(self) -> None:
        """Clear all subscribers."""
        self._subscribers.clear()


class RedisPubSub(PubSubBackend):
    """Redis-based pub/sub for multi-instance deployments."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis = None
        self._pubsub = None
        self._subscribers: dict[str, set[NotificationHandler]] = {}
        self._listener_task: asyncio.Task | None = None
        self._running = False

    async def _ensure_connected(self) -> None:
        """Ensure Redis connection is established."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = await aioredis.from_url(self._redis_url)
                self._pubsub = self._redis.pubsub()
                self._running = True
                self._listener_task = asyncio.create_task(self._listen())
            except ImportError:
                logger.warning("redis package not installed, falling back to in-memory")
                raise

    async def _listen(self) -> None:
        """Listen for Redis pub/sub messages."""
        while self._running and self._pubsub:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] == "message":
                    channel = (
                        message["channel"].decode()
                        if isinstance(message["channel"], bytes)
                        else message["channel"]
                    )
                    data = json.loads(message["data"])
                    notification = Notification.from_dict(data)

                    handlers = self._subscribers.get(channel, set()).copy()
                    for handler in handlers:
                        try:
                            await handler(notification)
                        except Exception as e:
                            logger.error(f"Handler error: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Redis listener error: {e}")
                await asyncio.sleep(1)

    async def publish(self, channel: str, notification: Notification) -> None:
        """Publish to Redis channel."""
        await self._ensure_connected()
        await self._redis.publish(channel, notification.to_json())

    async def subscribe(self, channel: str, handler: NotificationHandler) -> None:
        """Subscribe to Redis channel."""
        await self._ensure_connected()

        if channel not in self._subscribers:
            self._subscribers[channel] = set()
            await self._pubsub.subscribe(channel)

        self._subscribers[channel].add(handler)

    async def unsubscribe(self, channel: str, handler: NotificationHandler) -> None:
        """Unsubscribe from Redis channel."""
        if channel in self._subscribers:
            self._subscribers[channel].discard(handler)
            if not self._subscribers[channel]:
                del self._subscribers[channel]
                if self._pubsub:
                    await self._pubsub.unsubscribe(channel)

    async def close(self) -> None:
        """Close Redis connections."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()


class NotificationService:
    """
    Central notification service.

    Manages pub/sub subscriptions and delivers notifications
    to appropriate handlers (Telegram, WebSocket, etc.).
    """

    _instance: Optional["NotificationService"] = None

    def __init__(self, backend: PubSubBackend | None = None):
        self._backend = backend or InMemoryPubSub()
        self._user_handlers: dict[int, set[NotificationHandler]] = {}
        self._store_handlers: dict[int, set[NotificationHandler]] = {}
        self._global_handlers: set[NotificationHandler] = set()
        self._telegram_bot = None

    @classmethod
    def get_instance(cls, redis_url: str | None = None) -> "NotificationService":
        """Get or create singleton instance."""
        if cls._instance is None:
            if redis_url:
                try:
                    backend = RedisPubSub(redis_url)
                except ImportError:
                    backend = InMemoryPubSub()
            else:
                backend = InMemoryPubSub()
            cls._instance = cls(backend)
        return cls._instance

    def set_telegram_bot(self, bot) -> None:
        """Set Telegram bot for sending notifications."""
        self._telegram_bot = bot

    # Channel naming conventions
    @staticmethod
    def user_channel(user_id: int) -> str:
        """Get channel name for user notifications."""
        return f"user:{user_id}"

    @staticmethod
    def store_channel(store_id: int) -> str:
        """Get channel name for store notifications."""
        return f"store:{store_id}"

    @staticmethod
    def city_channel(city: str) -> str:
        """Get channel name for city-wide notifications."""
        return f"city:{city}"

    @staticmethod
    def global_channel() -> str:
        """Get channel name for global notifications."""
        return "global"

    # Subscription methods
    async def subscribe_user(self, user_id: int, handler: NotificationHandler) -> None:
        """Subscribe to user's notifications."""
        channel = self.user_channel(user_id)
        await self._backend.subscribe(channel, handler)

        if user_id not in self._user_handlers:
            self._user_handlers[user_id] = set()
        self._user_handlers[user_id].add(handler)

    async def unsubscribe_user(self, user_id: int, handler: NotificationHandler) -> None:
        """Unsubscribe from user's notifications."""
        channel = self.user_channel(user_id)
        await self._backend.unsubscribe(channel, handler)

        if user_id in self._user_handlers:
            self._user_handlers[user_id].discard(handler)

    async def subscribe_store(self, store_id: int, handler: NotificationHandler) -> None:
        """Subscribe to store's notifications."""
        channel = self.store_channel(store_id)
        await self._backend.subscribe(channel, handler)

        if store_id not in self._store_handlers:
            self._store_handlers[store_id] = set()
        self._store_handlers[store_id].add(handler)

    async def unsubscribe_store(self, store_id: int, handler: NotificationHandler) -> None:
        """Unsubscribe from store's notifications."""
        channel = self.store_channel(store_id)
        await self._backend.unsubscribe(channel, handler)

        if store_id in self._store_handlers:
            self._store_handlers[store_id].discard(handler)

    async def subscribe_global(self, handler: NotificationHandler) -> None:
        """Subscribe to global notifications."""
        await self._backend.subscribe(self.global_channel(), handler)
        self._global_handlers.add(handler)

    # Publishing methods
    async def notify_user(self, notification: Notification) -> None:
        """Send notification to a user."""
        channel = self.user_channel(notification.recipient_id)
        await self._backend.publish(channel, notification)

        # Also send via Telegram if bot is configured
        if self._telegram_bot and notification.priority >= 1:
            await self._send_telegram_notification(notification)

    async def notify_store(self, notification: Notification) -> None:
        """Send notification to a store owner."""
        channel = self.store_channel(notification.recipient_id)
        await self._backend.publish(channel, notification)

    async def notify_city(self, city: str, notification: Notification) -> None:
        """Send notification to all users in a city."""
        channel = self.city_channel(city)
        await self._backend.publish(channel, notification)

    async def broadcast(self, notification: Notification) -> None:
        """Broadcast notification to all subscribers."""
        await self._backend.publish(self.global_channel(), notification)

    async def _send_telegram_notification(self, notification: Notification) -> None:
        """Send notification via Telegram bot."""
        if not self._telegram_bot:
            return

        try:
            text = f"🔔 *{notification.title}*\n\n{notification.message}"
            await self._telegram_bot.send_message(
                chat_id=notification.recipient_id, text=text, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")

    # Convenience methods for common notifications
    async def notify_new_booking(
        self,
        store_owner_id: int,
        store_name: str,
        offer_title: str,
        booking_code: str,
        customer_name: str,
    ) -> None:
        """Notify store owner about new booking."""
        notification = Notification(
            type=NotificationType.NEW_BOOKING,
            recipient_id=store_owner_id,
            title="Новое бронирование! 🎉",
            message=f"Покупатель {customer_name} забронировал '{offer_title}'\nКод: {booking_code}",
            data={
                "store_name": store_name,
                "offer_title": offer_title,
                "booking_code": booking_code,
                "customer_name": customer_name,
            },
            priority=1,
        )
        await self.notify_user(notification)

    async def notify_booking_confirmed(
        self, user_id: int, store_name: str, offer_title: str, pickup_time: str
    ) -> None:
        """Notify customer about confirmed booking."""
        notification = Notification(
            type=NotificationType.BOOKING_CONFIRMED,
            recipient_id=user_id,
            title="Бронирование подтверждено! ✅",
            message=f"Заберите '{offer_title}' в {store_name}\nВремя: {pickup_time}",
            data={"store_name": store_name, "offer_title": offer_title, "pickup_time": pickup_time},
            priority=1,
        )
        await self.notify_user(notification)

    async def notify_new_offer_in_favorite_store(
        self, user_id: int, store_name: str, offer_title: str, discount_percent: int, offer_id: int
    ) -> None:
        """Notify user about new offer in favorite store."""
        notification = Notification(
            type=NotificationType.NEW_OFFER,
            recipient_id=user_id,
            title=f"Новое предложение в {store_name}! 🆕",
            message=f"'{offer_title}' со скидкой {discount_percent}%",
            data={
                "store_name": store_name,
                "offer_id": offer_id,
                "discount_percent": discount_percent,
            },
            priority=0,
        )
        await self.notify_user(notification)

    async def notify_offer_expiring(
        self, store_owner_id: int, offer_title: str, expires_in_minutes: int
    ) -> None:
        """Notify store owner about expiring offer."""
        notification = Notification(
            type=NotificationType.OFFER_EXPIRING,
            recipient_id=store_owner_id,
            title="Предложение скоро истечёт ⏰",
            message=f"'{offer_title}' истекает через {expires_in_minutes} минут",
            data={"offer_title": offer_title, "expires_in_minutes": expires_in_minutes},
            priority=1,
        )
        await self.notify_user(notification)

    async def notify_store_verified(self, owner_id: int, store_name: str) -> None:
        """Notify store owner about verification."""
        notification = Notification(
            type=NotificationType.STORE_VERIFIED,
            recipient_id=owner_id,
            title="Магазин верифицирован! 🎊",
            message=f"Ваш магазин '{store_name}' успешно прошёл проверку. Теперь вы можете создавать предложения!",
            data={"store_name": store_name},
            priority=2,
        )
        await self.notify_user(notification)

    async def close(self) -> None:
        """Close notification service."""
        await self._backend.close()
        self._user_handlers.clear()
        self._store_handlers.clear()
        self._global_handlers.clear()


# Global instance getter
def get_notification_service(redis_url: str | None = None) -> NotificationService:
    """Get the notification service singleton."""
    if redis_url is None:
        redis_url = os.getenv("REDIS_URL")
    return NotificationService.get_instance(redis_url)
