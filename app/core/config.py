"""Environment-driven configuration objects for the bot."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

from dotenv import load_dotenv


def _str_to_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"true", "1", "yes", "y"}


@dataclass(slots=True)
class WebhookConfig:
    enabled: bool
    url: str
    path: str
    port: int
    secret_token: str


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_id: int
    database_url: str | None
    redis_url: str | None
    webhook: WebhookConfig

    @property
    def telegram_bot_token(self) -> str:
        """Alias for bot_token for backward compatibility."""
        return self.bot_token


def load_settings() -> Settings:
    """Load environment variables once and expose typed settings."""
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

    admin_id = int(os.getenv("ADMIN_ID", "0"))
    database_url = os.getenv("DATABASE_URL")
    redis_url = os.getenv("REDIS_URL")

    # Smart webhook detection: auto-enable on Railway/Heroku if URL provided
    use_webhook = _str_to_bool(os.getenv("USE_WEBHOOK", "false"))
    webhook_url = os.getenv("WEBHOOK_URL", "")

    # Auto-enable webhook if WEBHOOK_URL is set and USE_WEBHOOK not explicitly disabled
    if webhook_url and not os.getenv("USE_WEBHOOK"):
        use_webhook = True

    # Disable webhook if URL is missing even if USE_WEBHOOK=true
    if use_webhook and not webhook_url:
        print("⚠️ USE_WEBHOOK=true but WEBHOOK_URL is empty, falling back to polling")
        use_webhook = False

    # Generate SECRET_TOKEN automatically for webhook security if not provided
    secret_token = os.getenv("SECRET_TOKEN", "")
    if use_webhook and not secret_token:
        secret_token = secrets.token_urlsafe(32)
        print("⚠️ SECRET_TOKEN not set, auto-generated for webhook security")

    webhook = WebhookConfig(
        enabled=use_webhook,
        url=webhook_url,
        path=os.getenv("WEBHOOK_PATH", "/webhook"),
        port=int(os.getenv("PORT", "8080")),
        secret_token=secret_token,
    )

    return Settings(
        bot_token=token,
        admin_id=admin_id,
        database_url=database_url,
        redis_url=redis_url,
        webhook=webhook,
    )
