"""
Tests for real-time notification system.
"""
from datetime import datetime

import pytest

from app.core.notifications import (
    InMemoryPubSub,
    Notification,
    NotificationService,
    NotificationType,
    get_notification_service,
)


class TestNotificationType:
    """Test NotificationType enum."""

    def test_booking_types(self):
        """Test booking notification types exist."""
        assert NotificationType.NEW_BOOKING == "new_booking"
        assert NotificationType.BOOKING_CONFIRMED == "booking_confirmed"
        assert NotificationType.BOOKING_CANCELLED == "booking_cancelled"
        assert NotificationType.BOOKING_COMPLETED == "booking_completed"

    def test_offer_types(self):
        """Test offer notification types exist."""
        assert NotificationType.NEW_OFFER == "new_offer"
        assert NotificationType.OFFER_UPDATED == "offer_updated"
        assert NotificationType.OFFER_SOLD_OUT == "offer_sold_out"
        assert NotificationType.OFFER_EXPIRING == "offer_expiring"

    def test_store_types(self):
        """Test store notification types exist."""
        assert NotificationType.STORE_VERIFIED == "store_verified"
        assert NotificationType.STORE_REJECTED == "store_rejected"
        assert NotificationType.NEW_RATING == "new_rating"


class TestNotification:
    """Test Notification dataclass."""

    def test_create_notification(self):
        """Test creating a notification."""
        notification = Notification(
            type=NotificationType.NEW_BOOKING,
            recipient_id=123456,
            title="Test Title",
            message="Test message",
        )

        assert notification.type == NotificationType.NEW_BOOKING
        assert notification.recipient_id == 123456
        assert notification.title == "Test Title"
        assert notification.message == "Test message"
        assert notification.priority == 0
        assert isinstance(notification.created_at, datetime)

    def test_notification_with_data(self):
        """Test notification with custom data."""
        data = {"offer_id": 42, "store_name": "Test Store"}
        notification = Notification(
            type=NotificationType.NEW_OFFER,
            recipient_id=123,
            title="New Offer",
            message="Check it out!",
            data=data,
            priority=1,
        )

        assert notification.data == data
        assert notification.priority == 1

    def test_to_dict(self):
        """Test serialization to dict."""
        notification = Notification(
            type=NotificationType.NEW_BOOKING, recipient_id=123, title="Title", message="Message"
        )

        d = notification.to_dict()

        assert d["type"] == "new_booking"
        assert d["recipient_id"] == 123
        assert d["title"] == "Title"
        assert d["message"] == "Message"
        assert "created_at" in d

    def test_to_json(self):
        """Test serialization to JSON."""
        notification = Notification(
            type=NotificationType.NEW_BOOKING, recipient_id=123, title="Title", message="Message"
        )

        json_str = notification.to_json()

        assert isinstance(json_str, str)
        assert "new_booking" in json_str
        assert "123" in json_str

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "type": "new_booking",
            "recipient_id": 456,
            "title": "Test",
            "message": "Msg",
            "data": {"key": "value"},
            "created_at": "2025-01-01T12:00:00",
            "priority": 2,
        }

        notification = Notification.from_dict(data)

        assert notification.type == NotificationType.NEW_BOOKING
        assert notification.recipient_id == 456
        assert notification.title == "Test"
        assert notification.data == {"key": "value"}
        assert notification.priority == 2


class TestInMemoryPubSub:
    """Test in-memory pub/sub backend."""

    @pytest.fixture
    def pubsub(self):
        """Create fresh pubsub instance."""
        return InMemoryPubSub()

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, pubsub):
        """Test basic subscribe and publish."""
        received = []

        async def handler(notification):
            received.append(notification)

        await pubsub.subscribe("test_channel", handler)

        notification = Notification(
            type=NotificationType.NEW_BOOKING, recipient_id=123, title="Test", message="Msg"
        )

        await pubsub.publish("test_channel", notification)

        assert len(received) == 1
        assert received[0].title == "Test"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, pubsub):
        """Test multiple subscribers on same channel."""
        results1 = []
        results2 = []

        async def handler1(n):
            results1.append(n)

        async def handler2(n):
            results2.append(n)

        await pubsub.subscribe("channel", handler1)
        await pubsub.subscribe("channel", handler2)

        notification = Notification(
            type=NotificationType.NEW_OFFER, recipient_id=1, title="Offer", message="New!"
        )

        await pubsub.publish("channel", notification)

        assert len(results1) == 1
        assert len(results2) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self, pubsub):
        """Test unsubscribe removes handler."""
        received = []

        async def handler(n):
            received.append(n)

        await pubsub.subscribe("channel", handler)
        await pubsub.unsubscribe("channel", handler)

        await pubsub.publish(
            "channel",
            Notification(type=NotificationType.NEW_BOOKING, recipient_id=1, title="T", message="M"),
        )

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_publish_to_nonexistent_channel(self, pubsub):
        """Test publishing to channel with no subscribers."""
        # Should not raise
        await pubsub.publish(
            "nobody",
            Notification(type=NotificationType.NEW_BOOKING, recipient_id=1, title="T", message="M"),
        )

    @pytest.mark.asyncio
    async def test_handler_error_does_not_break_others(self, pubsub):
        """Test that one handler error doesn't break other handlers."""
        results = []

        async def bad_handler(n):
            raise ValueError("Oops!")

        async def good_handler(n):
            results.append(n)

        await pubsub.subscribe("channel", bad_handler)
        await pubsub.subscribe("channel", good_handler)

        await pubsub.publish(
            "channel",
            Notification(type=NotificationType.NEW_BOOKING, recipient_id=1, title="T", message="M"),
        )

        # Good handler should still receive
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_close(self, pubsub):
        """Test close clears subscribers."""

        async def handler(n):
            pass

        await pubsub.subscribe("channel", handler)
        await pubsub.close()

        # Should be empty after close
        assert len(pubsub._subscribers) == 0


class TestNotificationService:
    """Test notification service."""

    @pytest.fixture
    def service(self):
        """Create fresh service with in-memory backend."""
        # Reset singleton
        NotificationService._instance = None
        return NotificationService(InMemoryPubSub())

    def test_channel_names(self):
        """Test channel name generators."""
        assert NotificationService.user_channel(123) == "user:123"
        assert NotificationService.store_channel(456) == "store:456"
        assert NotificationService.city_channel("Tashkent") == "city:Tashkent"
        assert NotificationService.global_channel() == "global"

    @pytest.mark.asyncio
    async def test_notify_user(self, service):
        """Test sending notification to user."""
        received = []

        async def handler(n):
            received.append(n)

        await service.subscribe_user(123, handler)

        notification = Notification(
            type=NotificationType.BOOKING_CONFIRMED,
            recipient_id=123,
            title="Confirmed",
            message="Your booking is confirmed",
        )

        await service.notify_user(notification)

        assert len(received) == 1
        assert received[0].title == "Confirmed"

    @pytest.mark.asyncio
    async def test_notify_store(self, service):
        """Test sending notification to store."""
        received = []

        async def handler(n):
            received.append(n)

        await service.subscribe_store(42, handler)

        notification = Notification(
            type=NotificationType.NEW_BOOKING,
            recipient_id=42,
            title="New booking",
            message="Someone booked!",
        )

        await service.notify_store(notification)

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_broadcast(self, service):
        """Test broadcasting to all."""
        received = []

        async def handler(n):
            received.append(n)

        await service.subscribe_global(handler)

        notification = Notification(
            type=NotificationType.SYSTEM_ANNOUNCEMENT,
            recipient_id=0,
            title="Announcement",
            message="System maintenance",
        )

        await service.broadcast(notification)

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_notify_new_booking_helper(self, service):
        """Test notify_new_booking convenience method."""
        received = []

        async def handler(n):
            received.append(n)

        await service.subscribe_user(999, handler)

        await service.notify_new_booking(
            store_owner_id=999,
            store_name="Test Store",
            offer_title="Pizza",
            booking_code="ABC123",
            customer_name="John",
        )

        assert len(received) == 1
        assert received[0].type == NotificationType.NEW_BOOKING
        assert "Pizza" in received[0].message
        assert "ABC123" in received[0].message

    @pytest.mark.asyncio
    async def test_notify_booking_confirmed_helper(self, service):
        """Test notify_booking_confirmed convenience method."""
        received = []

        async def handler(n):
            received.append(n)

        await service.subscribe_user(888, handler)

        await service.notify_booking_confirmed(
            user_id=888,
            store_name="Coffee Shop",
            offer_title="Croissants",
            pickup_time="14:00-15:00",
        )

        assert len(received) == 1
        assert received[0].type == NotificationType.BOOKING_CONFIRMED
        assert "Coffee Shop" in received[0].message

    @pytest.mark.asyncio
    async def test_notify_new_offer_helper(self, service):
        """Test notify_new_offer_in_favorite_store helper."""
        received = []

        async def handler(n):
            received.append(n)

        await service.subscribe_user(777, handler)

        await service.notify_new_offer_in_favorite_store(
            user_id=777,
            store_name="Bakery",
            offer_title="Fresh bread",
            discount_percent=50,
            offer_id=123,
        )

        assert len(received) == 1
        assert received[0].type == NotificationType.NEW_OFFER
        assert "50%" in received[0].message

    @pytest.mark.asyncio
    async def test_notify_store_verified_helper(self, service):
        """Test notify_store_verified helper."""
        received = []

        async def handler(n):
            received.append(n)

        await service.subscribe_user(666, handler)

        await service.notify_store_verified(owner_id=666, store_name="New Store")

        assert len(received) == 1
        assert received[0].type == NotificationType.STORE_VERIFIED
        assert received[0].priority == 2  # Urgent

    @pytest.mark.asyncio
    async def test_unsubscribe_user(self, service):
        """Test unsubscribing user."""
        received = []

        async def handler(n):
            received.append(n)

        await service.subscribe_user(123, handler)
        await service.unsubscribe_user(123, handler)

        notification = Notification(
            type=NotificationType.NEW_BOOKING, recipient_id=123, title="Test", message="Test"
        )

        await service.notify_user(notification)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_close(self, service):
        """Test closing service."""

        async def handler(n):
            pass

        await service.subscribe_user(123, handler)
        await service.close()

        assert len(service._user_handlers) == 0


class TestGetNotificationService:
    """Test singleton getter."""

    def setup_method(self):
        """Reset singleton before each test."""
        NotificationService._instance = None

    def test_get_singleton(self):
        """Test getting singleton instance."""
        service1 = get_notification_service()
        service2 = get_notification_service()

        assert service1 is service2

    def test_get_with_redis_url_fallback(self):
        """Test fallback to in-memory when redis not available."""
        # This should not raise, should fallback to in-memory
        service = get_notification_service("redis://localhost:6379")
        assert service is not None
