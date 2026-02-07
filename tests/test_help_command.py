from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from handlers.common.help import show_help
from handlers.common.utils import user_view_mode


@pytest.mark.asyncio
async def test_help_customer_includes_webapp_link_and_support(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAPP_URL", "https://example.com/miniapp")

    db = MagicMock()
    db.get_user_language.return_value = "ru"
    user = MagicMock()
    user.role = "customer"
    db.get_user_model.return_value = user

    message = MagicMock()
    message.from_user.id = 123
    message.answer = AsyncMock()

    user_view_mode[123] = "customer"

    await show_help(message, db)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "https://example.com/miniapp" in text
    assert "@fudly_support" in text
    assert message.answer.call_args.kwargs.get("parse_mode") == "HTML"
