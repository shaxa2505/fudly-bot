"""User entity model."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.domain.value_objects import Language, UserRole


class User(BaseModel):
    """User entity with type-safe fields."""

    user_id: int = Field(..., description="Telegram user ID")
    username: str | None = Field(None, description="Telegram username")
    first_name: str = Field(..., description="User's first name")
    phone: str | None = Field(None, description="Phone number")
    city: str = Field(..., description="User's city")
    region: str | None = Field(None, description="User's region")
    district: str | None = Field(None, description="User's district")
    latitude: float | None = Field(None, description="User latitude")
    longitude: float | None = Field(None, description="User longitude")
    region_id: int | None = Field(None, description="User region id")
    district_id: int | None = Field(None, description="User district id")
    language: Language = Field(Language.RUSSIAN, description="Interface language")
    role: UserRole = Field(UserRole.CUSTOMER, description="User role")
    notifications_enabled: bool = Field(True, description="Push notifications enabled")
    created_at: datetime | None = Field(None, description="Registration timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True
        use_enum_values = True

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        """Validate phone number format."""
        if v is None:
            return v
        # Remove common formatting
        phone = (
            v.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        )
        if not phone.isdigit():
            raise ValueError("Phone must contain only digits")
        if len(phone) < 9 or len(phone) > 15:
            raise ValueError("Phone must be between 9 and 15 digits")
        return v

    @property
    def is_seller(self) -> bool:
        """Check if user is a seller."""
        return self.role == UserRole.SELLER

    @property
    def is_admin(self) -> bool:
        """Check if user is an admin."""
        return self.role == UserRole.ADMIN

    @property
    def display_name(self) -> str:
        """Get user's display name."""
        if self.username:
            return f"@{self.username}"
        return self.first_name

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "phone": self.phone,
            "city": self.city,
            "region": self.region,
            "district": self.district,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "region_id": self.region_id,
            "district_id": self.district_id,
            "language": self.language.value
            if isinstance(self.language, Language)
            else self.language,
            "role": self.role.value if isinstance(self.role, UserRole) else self.role,
            "notifications_enabled": self.notifications_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_db_row(cls, row: tuple | dict) -> User:
        """Create User from database row.

        Args:
            row: Database row as tuple or dict

        Returns:
            User instance
        """
        if isinstance(row, dict):
            return cls(**row)

        # Tuple format: (user_id, username, first_name, phone, city, language, role, notifications_enabled, created_at, ...)
        region = None
        district = None
        latitude = None
        longitude = None
        region_id = None
        district_id = None
        if len(row) >= 17:
            region = row[-6]
            district = row[-5]
            latitude = row[-4]
            longitude = row[-3]
            region_id = row[-2]
            district_id = row[-1]
        elif len(row) >= 15:
            region = row[-4]
            district = row[-3]
            latitude = row[-2]
            longitude = row[-1]
        return cls(
            user_id=row[0],
            username=row[1] if len(row) > 1 else None,
            first_name=row[2] if len(row) > 2 else "User",
            phone=row[3] if len(row) > 3 else None,
            city=row[4] if len(row) > 4 else "Ташкент",
            region=region,
            district=district,
            latitude=latitude,
            longitude=longitude,
            region_id=region_id,
            district_id=district_id,
            language=row[5] if len(row) > 5 else Language.RUSSIAN,
            role=row[6] if len(row) > 6 else UserRole.CUSTOMER,
            notifications_enabled=bool(row[7]) if len(row) > 7 else True,
            created_at=row[8] if len(row) > 8 else None,
        )

