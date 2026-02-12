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

from app.domain.offer_rules import validate_offer_prices


class OfferCreate(BaseModel):
    """Model for creating a new offer."""
    
    store_id: int = Field(..., gt=0, description="ID РјР°РіР°Р·РёРЅР°")
    title: str = Field(..., min_length=1, max_length=255, description="РќР°Р·РІР°РЅРёРµ С‚РѕРІР°СЂР°")
    description: Optional[str] = Field(None, max_length=2000, description="РћРїРёСЃР°РЅРёРµ С‚РѕРІР°СЂР°")
    
    # Prices in SUMS - stored as INTEGER
    original_price: int = Field(..., gt=0, description="РћСЂРёРіРёРЅР°Р»СЊРЅР°СЏ С†РµРЅР° РІ РєРѕРїРµР№РєР°С…")
    discount_price: int = Field(..., gt=0, description="Р¦РµРЅР° СЃРѕ СЃРєРёРґРєРѕР№ РІ РєРѕРїРµР№РєР°С…")
    
    quantity: float = Field(default=1, gt=0, description="РљРѕР»РёС‡РµСЃС‚РІРѕ")
    unit: str = Field(default="piece", max_length=20, description="Р•РґРёРЅРёС†Р° РёР·РјРµСЂРµРЅРёСЏ")
    category: str = Field(default="other", max_length=50, description="РљР°С‚РµРіРѕСЂРёСЏ")
    
    # Proper time types (not strings)
    available_from: time = Field(..., description="Р”РѕСЃС‚СѓРїРЅРѕ СЃ (РІСЂРµРјСЏ)")
    available_until: time = Field(..., description="Р”РѕСЃС‚СѓРїРЅРѕ РґРѕ (РІСЂРµРјСЏ)")
    expiry_date: date = Field(..., description="РЎСЂРѕРє РіРѕРґРЅРѕСЃС‚Рё (РґР°С‚Р°)")
    
    # Photo as Telegram file_id (consistent naming)
    photo_id: Optional[str] = Field(None, max_length=255, description="Telegram file_id С„РѕС‚Рѕ")
    
    status: str = Field(default="active", pattern="^(active|inactive|out_of_stock|sold_out)$")
    
    @model_validator(mode='after')
    def validate_prices(self):
        """Validate pricing rules (strict min discount, no silent rounding)."""
        validate_offer_prices(self.original_price, self.discount_price, require_both=True)
        return self
    
    @field_validator('expiry_date')
    @classmethod
    def expiry_must_be_future(cls, v: date) -> date:
        """Validate that expiry date is in the future."""
        if v < date.today():
            raise ValueError('РЎСЂРѕРє РіРѕРґРЅРѕСЃС‚Рё РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ РІ РїСЂРѕС€Р»РѕРј')
        return v
    
    @model_validator(mode='after')
    def validate_time_order(self):
        """Validate time window (allow overnight ranges)."""
        if self.available_from == self.available_until:
            raise ValueError('Р’СЂРµРјСЏ РЅР°С‡Р°Р»Р° Рё РѕРєРѕРЅС‡Р°РЅРёСЏ РЅРµ РґРѕР»Р¶РЅС‹ СЃРѕРІРїР°РґР°С‚СЊ')
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
        
        raise ValueError(f'РќРµРІРµСЂРЅС‹Р№ С„РѕСЂРјР°С‚ РІСЂРµРјРµРЅРё: {v}. РСЃРїРѕР»СЊР·СѓР№С‚Рµ HH:MM')
    
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
        
        raise ValueError(f'РќРµРІРµСЂРЅС‹Р№ С„РѕСЂРјР°С‚ РґР°С‚С‹: {v}. РСЃРїРѕР»СЊР·СѓР№С‚Рµ YYYY-MM-DD РёР»Рё DD.MM.YYYY')


class OfferUpdate(BaseModel):
    """Model for updating an existing offer (all fields optional)."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    
    original_price: Optional[int] = Field(None, gt=0)
    discount_price: Optional[int] = Field(None, gt=0)
    
    quantity: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = Field(None, max_length=20)
    category: Optional[str] = Field(None, max_length=50)
    
    available_from: Optional[time] = None
    available_until: Optional[time] = None
    expiry_date: Optional[date] = None
    
    photo_id: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, pattern="^(active|inactive|out_of_stock|sold_out)$")
    
    @model_validator(mode='after')
    def validate_prices(self):
        """Validate pricing if both prices are present in the payload."""
        if self.original_price is not None and self.discount_price is not None:
            validate_offer_prices(self.original_price, self.discount_price, require_both=True)
        return self
    
    @field_validator('expiry_date')
    @classmethod
    def expiry_must_be_future(cls, v: Optional[date]) -> Optional[date]:
        """Validate expiry date if provided."""
        if v is not None and v < date.today():
            raise ValueError('РЎСЂРѕРє РіРѕРґРЅРѕСЃС‚Рё РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ РІ РїСЂРѕС€Р»РѕРј')
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
    original_price: float = Field(..., description="РћСЂРёРіРёРЅР°Р»СЊРЅР°СЏ С†РµРЅР° РІ СЂСѓР±Р»СЏС…")
    discount_price: float = Field(..., description="Р¦РµРЅР° СЃРѕ СЃРєРёРґРєРѕР№ РІ СЂСѓР±Р»СЏС…")
    
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

