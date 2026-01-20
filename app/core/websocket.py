"""
WebSocket handler for real-time notifications.

Provides WebSocket endpoint for web clients to receive
real-time updates about bookings, offers, etc.
"""
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from weakref import WeakSet

from aiohttp import WSMsgType, web
from aiohttp.client_exceptions import ClientConnectionResetError

from app.core.notifications import (
    Notification,
    NotificationService,
)

logger = logging.getLogger(__name__)


@dataclass
class WebSocketClient:
    """Represents a connected WebSocket client."""

    ws: web.WebSocketResponse
    user_id: int | None = None
    store_id: int | None = None
    connected_at: datetime = None

    def __post_init__(self):
        if self.connected_at is None:
            self.connected_at = datetime.utcnow()

    __hash__ = object.__hash__

    async def send(self, data: dict) -> bool:
        """Send data to client."""
        try:
            if not self.ws.closed:
                await self.ws.send_json(data)
                return True
        except Exception as e:
            logger.error(f"Failed to send to WebSocket: {e}")
        return False

    async def send_notification(self, notification: Notification) -> bool:
        """Send notification to client."""
        return await self.send({"type": "notification", "payload": notification.to_dict()})


class WebSocketManager:
    """
    Manages WebSocket connections and message routing.

    Features:
    - Connection tracking by user_id
    - Automatic cleanup of disconnected clients
    - Integration with NotificationService pub/sub
    - Heartbeat/ping-pong support
    """

    _instance: Optional["WebSocketManager"] = None

    def __init__(self):
        self._clients: dict[int, set[WebSocketClient]] = {}  # user_id -> clients
        self._all_clients: WeakSet[WebSocketClient] = WeakSet()
        self._notification_service: NotificationService | None = None
        self._heartbeat_interval = 30  # seconds
        self._cleanup_task: asyncio.Task | None = None

    @classmethod
    def get_instance(cls) -> "WebSocketManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_notification_service(self, service: NotificationService) -> None:
        """Set notification service for pub/sub integration."""
        self._notification_service = service

    async def start(self) -> None:
        """Start background tasks."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("WebSocketManager started")

    async def stop(self) -> None:
        """Stop background tasks and close all connections."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        for client in list(self._all_clients):
            await self._disconnect(client)

        logger.info("WebSocketManager stopped")

    async def _cleanup_loop(self) -> None:
        """Periodically cleanup disconnected clients."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._cleanup_stale_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    async def _cleanup_stale_connections(self) -> None:
        """Remove disconnected clients."""
        for user_id, clients in list(self._clients.items()):
            for client in list(clients):
                if client.ws.closed:
                    clients.discard(client)
            if not clients:
                del self._clients[user_id]

    async def connect(
        self, ws: web.WebSocketResponse, user_id: int | None = None, store_id: int | None = None
    ) -> WebSocketClient:
        """Register a new WebSocket connection."""
        client = WebSocketClient(ws=ws, user_id=user_id, store_id=store_id)
        self._all_clients.add(client)

        if user_id:
            if user_id not in self._clients:
                self._clients[user_id] = set()
            self._clients[user_id].add(client)

            # Subscribe to user's notifications
            if self._notification_service:
                await self._notification_service.subscribe_user(user_id, client.send_notification)

        if store_id:
            # Subscribe to store notifications (partner panel)
            if self._notification_service:
                await self._notification_service.subscribe_store(
                    int(store_id), client.send_notification
                )

        logger.info(f"WebSocket connected: user_id={user_id}, store_id={store_id}")

        # Send welcome message
        await client.send(
            {
                "type": "connected",
                "payload": {
                    "user_id": user_id,
                    "store_id": store_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            }
        )

        return client

    async def _disconnect(self, client: WebSocketClient) -> None:
        """Handle client disconnection."""
        if client.user_id:
            if client.user_id in self._clients:
                self._clients[client.user_id].discard(client)
                if not self._clients[client.user_id]:
                    del self._clients[client.user_id]

            # Unsubscribe from notifications
            if self._notification_service:
                await self._notification_service.unsubscribe_user(
                    client.user_id, client.send_notification
                )

        if client.store_id and self._notification_service:
            try:
                await self._notification_service.unsubscribe_store(
                    int(client.store_id), client.send_notification
                )
            except Exception:
                pass

        if not client.ws.closed:
            await client.ws.close()

        logger.info(f"WebSocket disconnected: user_id={client.user_id}")

    async def send_to_user(self, user_id: int, data: dict) -> int:
        """Send data to all connections of a user."""
        sent = 0
        clients = self._clients.get(user_id, set())

        for client in list(clients):
            if await client.send(data):
                sent += 1
            elif client.ws.closed:
                clients.discard(client)

        return sent

    async def broadcast(self, data: dict) -> int:
        """Broadcast data to all connected clients."""
        sent = 0
        for client in list(self._all_clients):
            if await client.send(data):
                sent += 1
        return sent

    def get_connected_users(self) -> set[int]:
        """Get set of connected user IDs."""
        return set(self._clients.keys())

    def get_connection_count(self) -> int:
        """Get total number of connections."""
        return sum(len(clients) for clients in self._clients.values())

    def get_stats(self) -> dict:
        """Get WebSocket statistics."""
        return {
            "total_connections": self.get_connection_count(),
            "unique_users": len(self._clients),
            "users": list(self._clients.keys()),
        }


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """
    WebSocket endpoint handler.

    Query params:
    - user_id: User's Telegram ID
    - store_id: Store ID (for store owners)
    - token: Authentication token (optional)

    Messages:
    - Client can send: ping, subscribe, unsubscribe
    - Server sends: notification, pong, connected, error
    """
    ws = web.WebSocketResponse(heartbeat=30)
    try:
        await ws.prepare(request)
    except ClientConnectionResetError:
        return ws

    manager = WebSocketManager.get_instance()

    # Get user info from query params
    user_id = request.query.get("user_id")
    store_id = request.query.get("store_id")
    init_data = request.query.get("init_data") or request.headers.get("X-Telegram-Init-Data")

    authenticated_user_id = None
    if init_data:
        authenticated_user_id = _get_authenticated_user_id(init_data)
        logger.debug(
            f"WebSocket auth attempt: init_data={'present' if init_data else 'missing'}, authenticated_user_id={authenticated_user_id}"
        )

    environment = os.getenv("ENVIRONMENT", "production").lower()
    is_dev = environment in ("development", "dev", "local", "test")

    # In dev mode OR if user_id provided with store ownership, allow connection
    if not authenticated_user_id:
        if is_dev and user_id:
            # Dev mode: trust user_id from query params
            logger.info(f"WebSocket: dev mode allowing user_id={user_id}")
            try:
                authenticated_user_id = int(user_id)
            except ValueError:
                pass

        if not authenticated_user_id:
            # Debug level - this is expected when users open Partner Panel outside Telegram
            logger.debug(
                f"WebSocket auth skipped: is_dev={is_dev}, user_id={user_id}, has_init_data={bool(init_data)}"
            )
            await ws.send_json({"type": "error", "message": "Authentication required"})
            await ws.close()
            return ws

    if authenticated_user_id is not None:
        if user_id:
            try:
                if int(user_id) != authenticated_user_id:
                    await ws.send_json({"type": "error", "message": "User mismatch"})
                    await ws.close()
                    return ws
            except ValueError:
                await ws.send_json({"type": "error", "message": "Invalid user_id"})
                await ws.close()
                return ws
        user_id = authenticated_user_id
    elif user_id:
        try:
            user_id = int(user_id)
        except ValueError:
            await ws.send_json({"type": "error", "message": "Invalid user_id"})
            await ws.close()
            return ws

    if store_id:
        try:
            store_id = int(store_id)
        except ValueError:
            store_id = None

    if store_id and authenticated_user_id is not None and not is_dev:
        db = request.app.get("db") if hasattr(request, "app") else None
        if not _user_can_access_store(db, store_id, authenticated_user_id):
            await ws.send_json({"type": "error", "message": "Access denied"})
            await ws.close()
            return ws

    # Register connection
    client = await manager.connect(ws, user_id, store_id)

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await _handle_client_message(client, data)
                except json.JSONDecodeError:
                    await client.send({"type": "error", "message": "Invalid JSON"})

            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")
                break

    except Exception as e:
        logger.error(f"WebSocket handler error: {e}")

    finally:
        try:
            await manager._disconnect(client)
        except ClientConnectionResetError:
            pass

    return ws


def _get_authenticated_user_id(init_data: str) -> int | None:
    """Validate Telegram initData and return user_id."""
    if not init_data:
        return None

    # Try proper validation first
    try:
        from app.api.webapp.common import settings, validate_init_data
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"WebSocket auth import failed: {exc}")
        return None

    try:
        validated = validate_init_data(init_data, settings.bot_token)
        if validated:
            user = validated.get("user")
            if isinstance(user, dict):
                try:
                    return int(user.get("id"))
                except (TypeError, ValueError):
                    return None
    except Exception as e:
        logger.debug(f"init_data validation failed: {e}")
        return None

    return None


def _user_can_access_store(db: Any, store_id: int, user_id: int) -> bool:
    """Verify that user owns or administers the store."""
    if not db:
        return False

    if hasattr(db, "is_store_admin"):
        try:
            if db.is_store_admin(store_id, user_id):
                return True
        except Exception:
            pass

    if hasattr(db, "get_store_owner"):
        try:
            owner = db.get_store_owner(store_id)
            if isinstance(owner, dict):
                owner_id = owner.get("owner_id")
            else:
                owner_id = owner
            if owner_id is not None and int(owner_id) == user_id:
                return True
        except Exception:
            pass

    if hasattr(db, "get_store_by_owner"):
        try:
            store = db.get_store_by_owner(user_id)
            if store:
                store_id_val = (
                    store.get("store_id")
                    if isinstance(store, dict)
                    else store[0]
                    if isinstance(store, tuple)
                    else None
                )
                if store_id_val is not None and int(store_id_val) == store_id:
                    return True
        except Exception:
            pass

    if hasattr(db, "get_user_stores"):
        try:
            stores = db.get_user_stores(user_id) or []
            for store in stores:
                store_id_val = (
                    store.get("store_id")
                    if isinstance(store, dict)
                    else store[0]
                    if isinstance(store, tuple)
                    else None
                )
                if store_id_val is not None and int(store_id_val) == store_id:
                    return True
        except Exception:
            pass

    return False


async def _handle_client_message(client: WebSocketClient, data: dict) -> None:
    """Handle incoming client message."""
    msg_type = data.get("type")

    if msg_type == "ping":
        await client.send({"type": "pong", "timestamp": datetime.utcnow().isoformat()})

    elif msg_type == "subscribe":
        # Handle subscription requests
        channel = data.get("channel")
        logger.debug(f"Subscribe request: {channel}")
        await client.send({"type": "subscribed", "channel": channel})

    elif msg_type == "unsubscribe":
        channel = data.get("channel")
        logger.debug(f"Unsubscribe request: {channel}")
        await client.send({"type": "unsubscribed", "channel": channel})

    else:
        await client.send({"type": "error", "message": f"Unknown message type: {msg_type}"})


def setup_websocket_routes(app: web.Application) -> None:
    """Add WebSocket routes to aiohttp app."""
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/ws/notifications", websocket_handler)

    # Stats endpoint
    async def ws_stats(request: web.Request) -> web.Response:
        manager = WebSocketManager.get_instance()
        return web.json_response(manager.get_stats())

    app.router.add_get("/ws/stats", ws_stats)


# Global getter
def get_websocket_manager() -> WebSocketManager:
    """Get WebSocket manager singleton."""
    return WebSocketManager.get_instance()
