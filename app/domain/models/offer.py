"""
Pydantic models for offer (product) data validation.

These models enforce consistent data format across bot and Partner Panel:
- Prices are stored in sums (INTEGER) for precision
- Times use datetime.time objects
- Dates use datetime.date objects
- All validation happens at the API boundary
"""
from datetime import date, datetime, time
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class OfferCreate(BaseModel):
    """Model for creating a new offer."""
    
    store_id: int = Field(..., gt=0, description="ID магазина")
    title: str = Field(..., min_length=1, max_length=255, description="Название товара")
    description: Optional[str] = Field(None, max_length=2000, description="Описание товара")
    
    # Prices in SUMS - stored as INTEGER
    original_price: int = Field(..., ge=0, description="Оригинальная цена в копейках")
    discount_price: int = Field(..., ge=0, description="Цена со скидкой в копейках")
    
    quantity: float = Field(default=1, gt=0, description="Количество")
    unit: str = Field(default="piece", max_length=20, description="Единица измерения")
    category: str = Field(default="other", max_length=50, description="Категория")
    
    # Proper time types (not strings)
    available_from: time = Field(..., description="Доступно с (время)")
    available_until: time = Field(..., description="Доступно до (время)")
    expiry_date: date = Field(..., description="Срок годности (дата)")
    
    # Photo as Telegram file_id (consistent naming)
    photo_id: Optional[str] = Field(None, max_length=255, description="Telegram file_id фото")
    
    status: str = Field(default="active", pattern="^(active|inactive|out_of_stock|sold_out)$")
    
    @field_validator('discount_price')
    @classmethod
    def discount_must_be_less_than_original(cls, v: int, info) -> int:
        """Validate that discount price is not higher than original price."""
        if 'original_price' in info.data and v > info.data['original_price']:
            raise ValueError('Цена со скидкой не может быть больше оригинальной цены')
        return v
    
    @field_validator('expiry_date')
    @classmethod
    def expiry_must_be_future(cls, v: date) -> date:
        """Validate that expiry date is in the future."""
        if v < date.today():
            raise ValueError('Срок годности не может быть в прошлом')
        return v
    
    @model_validator(mode='after')
    def validate_time_order(self):
        """Validate time window (allow overnight ranges)."""
        if self.available_from == self.available_until:
            raise ValueError('Время начала и окончания не должны совпадать')
        return self
    
    @field_validator('available_from', 'available_until', mode='before')
    @classmethod
    def parse_time_flexible(cls, v) -> time:
        """
        Parse time from multiple formats:
        - "HH:MM" string (legacy bot format)
        - "HH:MM:SS" string
        - ISO timestamp "2024-12-17T08:00:00"
        - datetime.time object (already parsed)
        """
        if isinstance(v, time):
            return v
        
        if isinstance(v, str):
            # Handle ISO timestamp format from Partner Panel
            if 'T' in v:
                dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
                return dt.time()
            
            # Handle "HH:MM" or "HH:MM:SS" format
            try:
                parts = v.split(':')
                if len(parts) == 2:
                    return time(int(parts[0]), int(parts[1]))
                elif len(parts) == 3:
                    return time(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                pass
        
        raise ValueError(f'Неверный формат времени: {v}. Используйте HH:MM')
    
    @field_validator('expiry_date', mode='before')
    @classmethod
    def parse_date_flexible(cls, v) -> date:
        """
        Parse date from multiple formats:
        - "YYYY-MM-DD" (ISO format)
        - "DD.MM.YYYY" (Russian format)
        - ISO timestamp "2024-12-17T00:00:00"
        - datetime.date object (already parsed)
        """
        if isinstance(v, date):
            return v
        
        if isinstance(v, str):
            # Handle ISO timestamp
            if 'T' in v:
                dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
                return dt.date()
            
            # Handle ISO date "YYYY-MM-DD"
            if '-' in v:
                try:
                    return datetime.strptime(v[:10], '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            # Handle Russian date "DD.MM.YYYY"
            if '.' in v:
                try:
                    return datetime.strptime(v, '%d.%m.%Y').date()
                except ValueError:
                    pass
        
        raise ValueError(f'Неверный формат даты: {v}. Используйте YYYY-MM-DD или DD.MM.YYYY')


class OfferUpdate(BaseModel):
    """Model for updating an existing offer (all fields optional)."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    
    original_price: Optional[int] = Field(None, ge=0)
    discount_price: Optional[int] = Field(None, ge=0)
    
    quantity: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = Field(None, max_length=20)
    category: Optional[str] = Field(None, max_length=50)
    
    available_from: Optional[time] = None
    available_until: Optional[time] = None
    expiry_date: Optional[date] = None
    
    photo_id: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, pattern="^(active|inactive|out_of_stock|sold_out)$")
    
    @field_validator('discount_price')
    @classmethod
    def discount_must_be_less_than_original(cls, v: Optional[int], info) -> Optional[int]:
        """Validate discount price if both prices are provided."""
        if v is not None and 'original_price' in info.data:
            original = info.data['original_price']
            if original is not None and v > original:
                raise ValueError('Цена со скидкой не может быть больше оригинальной цены')
        return v
    
    @field_validator('expiry_date')
    @classmethod
    def expiry_must_be_future(cls, v: Optional[date]) -> Optional[date]:
        """Validate expiry date if provided."""
        if v is not None and v < date.today():
            raise ValueError('Срок годности не может быть в прошлом')
        return v
    
    # Reuse the same flexible parsers from OfferCreate
    @field_validator('available_from', 'available_until', mode='before')
    @classmethod
    def parse_time_flexible(cls, v) -> Optional[time]:
        if v is None:
            return None
        return OfferCreate.parse_time_flexible(v)
    
    @field_validator('expiry_date', mode='before')
    @classmethod
    def parse_date_flexible(cls, v) -> Optional[date]:
        if v is None:
            return None
        return OfferCreate.parse_date_flexible(v)


class OfferResponse(BaseModel):
    """Model for offer data returned from API."""
    
    offer_id: int
    store_id: int
    title: str
    description: Optional[str]
    
    # Return prices in sums for display
    original_price: float = Field(..., description="Оригинальная цена в рублях")
    discount_price: float = Field(..., description="Цена со скидкой в рублях")
    
    quantity: float
    unit: str
    category: str
    
    available_from: Optional[time]
    available_until: Optional[time]
    expiry_date: Optional[date]
    
    photo_id: Optional[str]
    status: str
    created_at: datetime
    
    @classmethod
    def from_db_row(cls, row: dict) -> "OfferResponse":
        """
        Create OfferResponse from database row.
        Prices are stored in sums (INTEGER), so no conversion is needed.
        """
        # Make a copy to avoid modifying original
        data = dict(row)
        
        return cls(**data)
    
    class Config:
        from_attributes = True  # Allow creating from ORM objects
