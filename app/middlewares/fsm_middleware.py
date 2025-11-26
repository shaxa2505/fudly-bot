"""
FSM State Middleware.

Provides:
- Warning users about expiring states
- Auto-clear very old states
- State activity tracking
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger("fudly.fsm")


def _utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


class FSMStateMiddleware(BaseMiddleware):
    """
    Middleware for FSM state management.

    Features:
    - Tracks last activity time in state data
    - Warns users about states that will expire soon
    - Auto-clears states that are too old
    """

    def __init__(
        self,
        warning_minutes: int = 30,
        max_age_hours: int = 24,
        db: Any = None,
    ):
        """
        Initialize middleware.

        Args:
            warning_minutes: Minutes of inactivity before warning
            max_age_hours: Hours before auto-clearing state
            db: Database instance for language lookup
        """
        self.warning_delta = timedelta(minutes=warning_minutes)
        self.max_age_delta = timedelta(hours=max_age_hours)
        self.db = db
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process event and track FSM state."""
        state: FSMContext | None = data.get("state")

        if not state:
            return await handler(event, data)

        current_state = await state.get_state()

        if current_state:
            # Check state age
            state_data = await state.get_data()
            last_activity = state_data.get("_fsm_last_activity")

            if last_activity:
                try:
                    last_time = datetime.fromisoformat(last_activity)
                    age = _utc_now() - last_time

                    # Auto-clear very old states
                    if age > self.max_age_delta:
                        logger.info(
                            f"Auto-clearing expired FSM state: {current_state}, "
                            f"age={age.total_seconds() / 3600:.1f}h"
                        )
                        await state.clear()
                        await self._notify_expired(event, data)
                        return await handler(event, data)

                    # Warn about expiring states
                    elif age > self.warning_delta:
                        await self._warn_expiring(event, data, age)

                except (ValueError, TypeError) as e:
                    logger.debug(f"Could not parse last_activity: {e}")

            # Update last activity timestamp
            await state.update_data(_fsm_last_activity=_utc_now().isoformat())

        return await handler(event, data)

    def _get_user_lang(self, event: TelegramObject) -> str:
        """Get user language from event."""
        user_id = None

        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id and self.db:
            try:
                lang: str = self.db.get_user_language(user_id) or "ru"
                return lang
            except Exception:
                pass

        return "ru"

    async def _notify_expired(self, event: TelegramObject, data: dict[str, Any]) -> None:
        """Notify user that their session expired."""
        lang = self._get_user_lang(event)

        if lang == "uz":
            text = (
                "⏰ Sizning sessiyangiz tugadi.\n"
                "Uzoq vaqt javob bermadingiz.\n\n"
                "Iltimos, qaytadan boshlang."
            )
        else:
            text = (
                "⏰ Ваша сессия истекла.\n"
                "Вы долго не отвечали.\n\n"
                "Пожалуйста, начните заново."
            )

        try:
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery) and event.message:
                await event.answer(text, show_alert=True)
        except Exception as e:
            logger.debug(f"Could not send expiry notification: {e}")

    async def _warn_expiring(
        self,
        event: TelegramObject,
        data: dict[str, Any],
        age: timedelta,
    ) -> None:
        """Warn user about expiring session (only once per warning period)."""
        state: FSMContext | None = data.get("state")
        if not state:
            return

        state_data = await state.get_data()

        # Check if we already warned
        last_warning = state_data.get("_fsm_last_warning")
        if last_warning:
            try:
                last_warn_time = datetime.fromisoformat(last_warning)
                # Don't warn again within 10 minutes
                if _utc_now() - last_warn_time < timedelta(minutes=10):
                    return
            except (ValueError, TypeError):
                pass

        # Mark warning sent
        await state.update_data(_fsm_last_warning=_utc_now().isoformat())

        lang = self._get_user_lang(event)
        remaining = self.max_age_delta - age
        remaining_mins = max(1, int(remaining.total_seconds() / 60))

        if lang == "uz":
            text = f"⚠️ Sizning sessiyangiz {remaining_mins} daqiqadan keyin tugaydi."
        else:
            text = f"⚠️ Ваша сессия истечёт через {remaining_mins} мин."

        try:
            if isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=False)
        except Exception as e:
            logger.debug(f"Could not send warning: {e}")


class FSMActivityTracker(BaseMiddleware):
    """
    Simple middleware that tracks FSM state activity.

    Updates _fsm_last_activity in state data on every interaction.
    Use this if you only need activity tracking without warnings.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Update activity timestamp if there's an active state."""
        state: FSMContext | None = data.get("state")

        if state:
            current_state = await state.get_state()
            if current_state:
                await state.update_data(_fsm_last_activity=_utc_now().isoformat())

        return await handler(event, data)
