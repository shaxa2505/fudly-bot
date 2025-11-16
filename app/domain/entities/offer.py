"""Offer entity model."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.domain.value_objects import ProductUnit


class Offer(BaseModel):
    """Offer entity with type-safe fields."""
    
    offer_id: Optional[int] = Field(None, description="Offer ID (auto-generated)")
    store_id: int = Field(..., description="Store ID")
    title: str = Field(..., min_length=2, max_length=200, description="Product title")
    description: Optional[str] = Field(None, max_length=1000, description="Product description")
    original_price: int = Field(..., gt=0, description="Original price in sum")
    discounted_price: int = Field(..., gt=0, description="Discounted price in sum")
    quantity: int = Field(..., ge=0, description="Available quantity")
    unit: ProductUnit = Field("шт", description="Unit of measurement")
    category: Optional[str] = Field(None, description="Product category")
    photo_url: Optional[str] = Field(None, description="Product photo URL")
    
    pickup_time_start: Optional[str] = Field(None, description="Pickup time start (HH:MM)")
    pickup_time_end: Optional[str] = Field(None, description="Pickup time end (HH:MM)")
    expires_at: Optional[datetime] = Field(None, description="Offer expiration time")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    
    class Config:
        """Pydantic config."""
        from_attributes = True
    
    @field_validator('discounted_price')
    @classmethod
    def validate_discount(cls, v: int, values) -> int:
        """Validate that discounted price is less than original."""
        if 'original_price' in values.data and v >= values.data['original_price']:
            raise ValueError("Discounted price must be less than original price")
        return v
    
    @property
    def discount_percentage(self) -> int:
        """Calculate discount percentage."""
        if self.original_price == 0:
            return 0
        return int(((self.original_price - self.discounted_price) / self.original_price) * 100)
    
    @property
    def is_available(self) -> bool:
        """Check if offer is available (has quantity)."""
        return self.quantity > 0
    
    @property
    def is_expired(self) -> bool:
        """Check if offer has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def reduce_quantity(self, amount: int = 1) -> None:
        """Reduce available quantity."""
        if amount > self.quantity:
            raise ValueError(f"Cannot reduce quantity by {amount}, only {self.quantity} available")
        self.quantity -= amount
    
    def increase_quantity(self, amount: int = 1) -> None:
        """Increase available quantity."""
        self.quantity += amount
    
    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "offer_id": self.offer_id,
            "store_id": self.store_id,
            "title": self.title,
            "description": self.description,
            "original_price": self.original_price,
            "discounted_price": self.discounted_price,
            "quantity": self.quantity,
            "unit": self.unit,
            "category": self.category,
            "photo_url": self.photo_url,
            "pickup_time_start": self.pickup_time_start,
            "pickup_time_end": self.pickup_time_end,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def from_db_row(cls, row: tuple | dict) -> Offer:
        """Create Offer from database row.
        
        Args:
            row: Database row as tuple or dict
            
        Returns:
            Offer instance
        """
        if isinstance(row, dict):
            return cls(**row)
        
        # Tuple format: (offer_id, store_id, title, description, original_price, discounted_price, 
        #                quantity, unit, category, photo_url, pickup_time_start, pickup_time_end, 
        #                expires_at, created_at)
        return cls(
            offer_id=row[0] if len(row) > 0 else None,
            store_id=row[1] if len(row) > 1 else 0,
            title=row[2] if len(row) > 2 else "Product",
            description=row[3] if len(row) > 3 else None,
            original_price=row[4] if len(row) > 4 else 0,
            discounted_price=row[5] if len(row) > 5 else 0,
            quantity=row[6] if len(row) > 6 else 0,
            unit=row[7] if len(row) > 7 else "шт",
            category=row[8] if len(row) > 8 else None,
            photo_url=row[9] if len(row) > 9 else None,
            pickup_time_start=row[10] if len(row) > 10 else None,
            pickup_time_end=row[11] if len(row) > 11 else None,
            expires_at=row[12] if len(row) > 12 else None,
            created_at=row[13] if len(row) > 13 else None,
        )
