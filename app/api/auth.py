"""
Telegram Mini App Authentication Endpoint
Validates initData from Telegram WebApp and returns user profile
"""
import hashlib
import hmac
import json
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from app.core.config import load_settings
from database_protocol import DatabaseProtocol

router = APIRouter()
settings = load_settings()


class AuthRequest(BaseModel):
    """Telegram WebApp initData for validation."""
    init_data: str


class UserProfile(BaseModel):
    """User profile response."""
    user_id: int
    username: str | None
    first_name: str
    last_name: str | None
    phone: str | None
    city: str | None
    language: str
    registered: bool
    notifications_enabled: bool


def validate_telegram_webapp_data(init_data: str, bot_token: str) -> dict[str, Any] | None:
    """
    Validate Telegram WebApp initData signature.
    
    Based on: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    
    Args:
        init_data: Raw initData from window.Telegram.WebApp.initData
        bot_token: Telegram Bot Token
    
    Returns:
        Parsed data if valid, None otherwise
    """
    try:
        # Parse query string
        parsed_data = dict(parse_qsl(init_data))
        
        if 'hash' not in parsed_data:
            return None
            
        received_hash = parsed_data.pop('hash')
        
        # Create data-check-string
        data_check_arr = [f"{k}={v}" for k, v in sorted(parsed_data.items())]
        data_check_string = '\n'.join(data_check_arr)
        
        # Compute secret key
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode(),
            digestmod=hashlib.sha256
        ).digest()
        
        # Compute hash
        computed_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Verify hash
        if computed_hash != received_hash:
            return None
            
        # Parse user data
        if 'user' in parsed_data:
            parsed_data['user'] = json.loads(parsed_data['user'])
            
        return parsed_data
        
    except Exception as e:
        print(f"Error validating initData: {e}")
        return None


@router.post("/auth/validate", response_model=UserProfile)
async def validate_auth(
    request: AuthRequest,
    db: DatabaseProtocol = Depends(lambda: None)  # Replace with your DB dependency
) -> UserProfile:
    """
    Validate Telegram WebApp authentication and return user profile.
    
    Usage from Mini App:
    ```javascript
    const initData = window.Telegram.WebApp.initData
    const response = await fetch('/api/v1/auth/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initData })
    })
    ```
    """
    # Validate initData signature
    validated_data = validate_telegram_webapp_data(
        request.init_data, 
        settings.telegram_bot_token
    )
    
    if not validated_data or 'user' not in validated_data:
        raise HTTPException(status_code=401, detail="Invalid authentication data")
    
    telegram_user = validated_data['user']
    user_id = telegram_user['id']
    
    # Check if user exists in database
    user = db.get_user_model(user_id)
    
    if not user:
        # User not registered yet
        return UserProfile(
            user_id=user_id,
            username=telegram_user.get('username'),
            first_name=telegram_user.get('first_name', ''),
            last_name=telegram_user.get('last_name'),
            phone=None,
            city=None,
            language=telegram_user.get('language_code', 'ru'),
            registered=False,
            notifications_enabled=True
        )
    
    # Return existing user profile
    return UserProfile(
        user_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name or telegram_user.get('first_name', ''),
        last_name=user.last_name or telegram_user.get('last_name'),
        phone=user.phone,
        city=user.city,
        language=user.language or 'ru',
        registered=bool(user.phone),  # Считаем зарегистрированным если есть телефон
        notifications_enabled=getattr(user, 'notifications_enabled', True)
    )


@router.get("/user/profile", response_model=UserProfile)
async def get_profile(
    user_id: int,
    db: DatabaseProtocol = Depends(lambda: None)
) -> UserProfile:
    """Get user profile by ID."""
    user = db.get_user_model(user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserProfile(
        user_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name or '',
        last_name=user.last_name,
        phone=user.phone,
        city=user.city,
        language=user.language or 'ru',
        registered=bool(user.phone),
        notifications_enabled=getattr(user, 'notifications_enabled', True)
    )
