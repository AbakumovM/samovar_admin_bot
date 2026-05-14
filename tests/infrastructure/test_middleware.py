from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, User

from src.infrastructure.telegram.middleware import AdminAuthMiddleware


@pytest.fixture
def middleware() -> AdminAuthMiddleware:
    return AdminAuthMiddleware(admin_ids=[111, 222])


async def test_allowed_admin_passes_through(middleware: AdminAuthMiddleware) -> None:
    handler = AsyncMock(return_value="ok")
    message = MagicMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 111
    data: dict = {}

    result = await middleware(handler, message, data)

    handler.assert_awaited_once()
    assert result == "ok"


async def test_unknown_user_is_blocked(middleware: AdminAuthMiddleware) -> None:
    handler = AsyncMock(return_value="ok")
    message = MagicMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 999
    data: dict = {}

    result = await middleware(handler, message, data)

    handler.assert_not_awaited()
    assert result is None


async def test_no_user_is_blocked(middleware: AdminAuthMiddleware) -> None:
    handler = AsyncMock(return_value="ok")
    message = MagicMock(spec=Message)
    message.from_user = None
    data: dict = {}

    result = await middleware(handler, message, data)

    handler.assert_not_awaited()
