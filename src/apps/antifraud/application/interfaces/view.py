from datetime import datetime
from typing import Protocol


class AntifraudCooldownView(Protocol):
    async def get_last_notified_bulk(
        self, remnawave_ids: list[int]
    ) -> dict[int, datetime]: ...
    async def get_last_soft_notified_bulk(
        self, remnawave_ids: list[int]
    ) -> dict[int, datetime]: ...
