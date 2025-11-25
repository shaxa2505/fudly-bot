"""Store entity model."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.value_objects import StoreStatus


class Store(BaseModel):
    """Store entity with type-safe fields."""

    store_id: int | None = Field(None, description="Store ID (auto-generated)")
    owner_id: int = Field(..., description="Owner's Telegram user ID")
    name: str = Field(..., min_length=2, max_length=100, description="Store name")
    address: str = Field(..., min_length=5, max_length=200, description="Store address")
    city: str = Field(..., description="Store city")
    category: str = Field(..., description="Business category")
    status: StoreStatus = Field(StoreStatus.PENDING, description="Approval status")
    phone: str | None = Field(None, description="Store contact phone")
    description: str | None = Field(None, max_length=500, description="Store description")

    # Delivery settings
    delivery_enabled: bool = Field(False, description="Delivery available")
    delivery_price: int = Field(15000, description="Delivery price in sum")
    min_order_amount: int = Field(30000, description="Minimum order amount in sum")

    created_at: datetime | None = Field(None, description="Creation timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True
        use_enum_values = True

    @property
    def is_active(self) -> bool:
        """Check if store is approved and active."""
        return self.status == StoreStatus.ACTIVE

    @property
    def is_pending(self) -> bool:
        """Check if store is pending approval."""
        return self.status == StoreStatus.PENDING

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "store_id": self.store_id,
            "owner_id": self.owner_id,
            "name": self.name,
            "address": self.address,
            "city": self.city,
            "category": self.category,
            "status": self.status.value if isinstance(self.status, StoreStatus) else self.status,
            "phone": self.phone,
            "description": self.description,
            "delivery_enabled": int(self.delivery_enabled),
            "delivery_price": self.delivery_price,
            "min_order_amount": self.min_order_amount,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_db_row(cls, row: tuple | dict) -> Store:
        """Create Store from database row.

        Args:
            row: Database row as tuple or dict

        Returns:
            Store instance
        """
        if isinstance(row, dict):
            return cls(**row)

        # Tuple format varies, handle common patterns
        # (store_id, owner_id, name, city, address, category, status, phone, description, ...)
        return cls(
            store_id=row[0] if len(row) > 0 else None,
            owner_id=row[1] if len(row) > 1 else 0,
            name=row[2] if len(row) > 2 else "Store",
            city=row[3] if len(row) > 3 else "Ташкент",
            address=row[4] if len(row) > 4 else "",
            category=row[5] if len(row) > 5 else "restaurant",
            status=row[6] if len(row) > 6 else StoreStatus.PENDING,
            phone=row[7] if len(row) > 7 else None,
            description=row[8] if len(row) > 8 else None,
            delivery_enabled=bool(row[9]) if len(row) > 9 else False,
            delivery_price=row[10] if len(row) > 10 else 15000,
            min_order_amount=row[11] if len(row) > 11 else 30000,
            created_at=row[12] if len(row) > 12 else None,
        )
