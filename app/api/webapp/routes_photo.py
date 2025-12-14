from __future__ import annotations

from aiogram import Bot
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from .common import _photo_cache, logger, settings

router = APIRouter()


@router.get("/photo/{file_id:path}")
async def get_photo(file_id: str):
    """Convert Telegram file_id to actual photo URL and redirect.

    If the file_id is invalid or Telegram does not return a file,
    a 404 error is raised.
    """
    if not file_id or len(file_id) < 10:
        raise HTTPException(status_code=404, detail="Invalid file_id")

    if file_id in _photo_cache:
        return RedirectResponse(url=_photo_cache[file_id])

    try:
        bot = Bot(token=settings.bot_token)
        try:
            file = await bot.get_file(file_id)
            if file and file.file_path:
                url = f"https://api.telegram.org/file/bot{settings.bot_token}/{file.file_path}"
                _photo_cache[file_id] = url
                return RedirectResponse(url=url)
        finally:
            await bot.session.close()
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"Could not get photo for {file_id[:20]}...: {e}")

    raise HTTPException(status_code=404, detail="Photo not found")
