from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class AdminAuthMiddleware(BaseMiddleware):
    def __init__(self, admin_ids: list[int]) -> None:
        self._admin_ids = set(admin_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        if event.from_user is None or event.from_user.id not in self._admin_ids:
            return None
        return await handler(event, data)
