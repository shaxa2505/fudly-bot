"""
WebSocket manager for real-time notifications to partner panel.

Handles:
- Partner connections management
- New order notifications
- Order status updates
- Real-time updates for web panel
"""
import logging
from typing import Dict, Set, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections for partners."""
    
    def __init__(self):
        # store_id → set of WebSocket connections
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        logger.info("✅ ConnectionManager initialized")
    
    async def connect(self, store_id: int, websocket: WebSocket):
        """Connect a partner's WebSocket."""
        await websocket.accept()
        
        if store_id not in self.active_connections:
            self.active_connections[store_id] = set()
        
        self.active_connections[store_id].add(websocket)
        logger.info(f"🔌 Partner connected: store_id={store_id}, total={len(self.active_connections[store_id])}")
    
    def disconnect(self, store_id: int, websocket: WebSocket):
        """Disconnect a partner's WebSocket."""
        if store_id in self.active_connections:
            self.active_connections[store_id].discard(websocket)
            
            # Clean up empty sets
            if not self.active_connections[store_id]:
                del self.active_connections[store_id]
            
            logger.info(f"🔌 Partner disconnected: store_id={store_id}")
    
    async def notify_store(self, store_id: int, message: Dict[str, Any]) -> int:
        """Send notification to all connections for a specific store."""
        if store_id not in self.active_connections:
            logger.debug(f"📡 No active connections for store {store_id}")
            return 0
        
        sent = 0
        dead_connections: list[WebSocket] = []
        
        for websocket in self.active_connections[store_id]:
            try:
                await websocket.send_json(message)
                sent += 1
            except WebSocketDisconnect:
                dead_connections.append(websocket)
            except Exception as e:
                logger.error(f"❌ Failed to send to store {store_id}: {e}")
                dead_connections.append(websocket)
        
        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(store_id, ws)
        
        logger.info(f"📤 Sent notification to {sent} connections (store {store_id})")
        return sent
    
    async def notify_new_order(self, store_id: int, order_data: Dict[str, Any]) -> int:
        """Notify store about new order."""
        message: Dict[str, Any] = {
            "type": "new_order",
            "data": order_data
        }
        return await self.notify_store(store_id, message)
    
    async def notify_order_status(self, store_id: int, order_id: int, new_status: str) -> int:
        """Notify store about order status change."""
        message: Dict[str, Any] = {
            "type": "order_status_changed",
            "data": {
                "order_id": order_id,
                "status": new_status
            }
        }
        return await self.notify_store(store_id, message)
    
    async def notify_order_cancelled(self, store_id: int, order_id: int, reason: str) -> int:
        """Notify store about order cancellation."""
        message: Dict[str, Any] = {
            "type": "order_cancelled",
            "data": {
                "order_id": order_id,
                "reason": reason
            }
        }
        return await self.notify_store(store_id, message)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            "total_stores": len(self.active_connections),
            "total_connections": sum(len(conns) for conns in self.active_connections.values()),
            "stores": {
                store_id: len(conns) 
                for store_id, conns in self.active_connections.items()
            }
        }


# Global instance
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get global ConnectionManager instance."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


def set_connection_manager(manager: ConnectionManager):
    """Set global ConnectionManager instance."""
    global _manager
    _manager = manager
