"""Booking entity model."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.value_objects import BookingStatus


class Booking(BaseModel):
    """Booking entity with type-safe fields."""

    booking_id: int | None = Field(None, description="Booking ID (auto-generated)")
    user_id: int = Field(..., description="User's Telegram ID")
    offer_id: int = Field(..., description="Offer ID")
    store_id: int = Field(..., description="Store ID")
    quantity: float = Field(..., gt=0, description="Booked quantity")
    total_price: int = Field(..., gt=0, description="Total price in sum")
    status: BookingStatus = Field(BookingStatus.PENDING, description="Booking status")
    rating: int | None = Field(None, ge=1, le=5, description="User rating (1-5)")
    created_at: datetime | None = Field(None, description="Booking creation time")
    completed_at: datetime | None = Field(None, description="Booking completion time")

    class Config:
        """Pydantic config."""

        from_attributes = True
        use_enum_values = True

    @property
    def is_active(self) -> bool:
        """Check if booking is active (pending or confirmed)."""
        return self.status in (BookingStatus.PENDING, BookingStatus.CONFIRMED)

    @property
    def is_completed(self) -> bool:
        """Check if booking is completed."""
        return self.status == BookingStatus.COMPLETED

    @property
    def is_cancelled(self) -> bool:
        """Check if booking is cancelled."""
        return self.status == BookingStatus.CANCELLED

    @property
    def can_be_rated(self) -> bool:
        """Check if booking can be rated."""
        return self.is_completed and self.rating is None

    def complete(self) -> None:
        """Mark booking as completed."""
        self.status = BookingStatus.COMPLETED
        self.completed_at = datetime.now()

    def cancel(self) -> None:
        """Cancel booking."""
        if self.is_completed:
            raise ValueError("Cannot cancel completed booking")
        self.status = BookingStatus.CANCELLED

    def rate(self, rating: int) -> None:
        """Add rating to completed booking."""
        if not self.is_completed:
            raise ValueError("Can only rate completed bookings")
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5")
        self.rating = rating

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "booking_id": self.booking_id,
            "user_id": self.user_id,
            "offer_id": self.offer_id,
            "store_id": self.store_id,
            "quantity": self.quantity,
            "total_price": self.total_price,
            "status": self.status.value if isinstance(self.status, BookingStatus) else self.status,
            "rating": self.rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_db_row(cls, row: tuple | dict) -> Booking:
        """Create Booking from database row.

        Args:
            row: Database row as tuple or dict

        Returns:
            Booking instance
        """
        if isinstance(row, dict):
            return cls(**row)

        # Tuple format: (booking_id, user_id, offer_id, store_id, quantity, total_price,
        #                status, rating, created_at, completed_at)
        return cls(
            booking_id=row[0] if len(row) > 0 else None,
            user_id=row[1] if len(row) > 1 else 0,
            offer_id=row[2] if len(row) > 2 else 0,
            store_id=row[3] if len(row) > 3 else 0,
            quantity=float(row[4]) if len(row) > 4 and row[4] is not None else 1.0,
            total_price=row[5] if len(row) > 5 else 0,
            status=row[6] if len(row) > 6 else BookingStatus.PENDING,
            rating=row[7] if len(row) > 7 else None,
            created_at=row[8] if len(row) > 8 else None,
            completed_at=row[9] if len(row) > 9 else None,
        )

    @classmethod
    def create(
        cls,
        user_id: int,
        offer_id: int,
        store_id: int,
        quantity: float,
        total_price: int,
    ) -> Booking:
        """Factory method to create a new booking."""
        return cls(
            user_id=user_id,
            offer_id=offer_id,
            store_id=store_id,
            quantity=quantity,
            total_price=total_price,
            status=BookingStatus.PENDING,
            created_at=datetime.now(),
        )
