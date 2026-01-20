from __future__ import annotations

import os

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from .common import _photo_cache, logger, settings

router = APIRouter()
_legacy_bot_token = (
    os.getenv("LEGACY_TELEGRAM_BOT_TOKEN")
    or os.getenv("OLD_TELEGRAM_BOT_TOKEN")
    or os.getenv("PHOTO_FALLBACK_BOT_TOKEN")
)


async def _resolve_photo_url(file_id: str) -> str | None:
    """Try to resolve photo URL using primary bot token and optional legacy token."""
    if file_id in _photo_cache:
        return _photo_cache[file_id]

    tokens = [settings.bot_token]
    if _legacy_bot_token and _legacy_bot_token != settings.bot_token:
        tokens.append(_legacy_bot_token)

    for token in tokens:
        bot = Bot(token=token)
        try:
            file = await bot.get_file(file_id)
            if file and file.file_path:
                url = f"https://api.telegram.org/file/bot{token}/{file.file_path}"
                _photo_cache[file_id] = url
                if token != settings.bot_token:
                    logger.info("Photo served via legacy bot token")
                return url
        except TelegramAPIError:
            logger.debug("Bot token failed to fetch photo_id %s", file_id, exc_info=True)
        except Exception:
            logger.debug("Unexpected error fetching photo %s", file_id, exc_info=True)
        finally:
            await bot.session.close()

    return None


@router.get("/photo/{file_id:path}")
async def get_photo(file_id: str):
    """Convert Telegram file_id to actual photo URL and redirect.

    If the file_id is invalid or Telegram does not return a file,
    a 404 error is raised.
    """
    if not file_id or len(file_id) < 10:
        raise HTTPException(status_code=404, detail="Invalid file_id")

    url = await _resolve_photo_url(file_id)
    if url:
        return RedirectResponse(url=url)

    raise HTTPException(status_code=404, detail="Photo not found")
