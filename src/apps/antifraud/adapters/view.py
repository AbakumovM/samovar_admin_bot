from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.antifraud.adapters.orm import AntifraudNotifiedUserModel


class PostgresAntifraudCooldownView:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_last_notified_bulk(self, remnawave_ids: list[int]) -> dict[int, datetime]:
        if not remnawave_ids:
            return {}
        result = await self._session.execute(
            select(
                AntifraudNotifiedUserModel.remnawave_id,
                AntifraudNotifiedUserModel.notified_at,
            ).where(AntifraudNotifiedUserModel.remnawave_id.in_(remnawave_ids))
        )
        return {row.remnawave_id: row.notified_at for row in result if row.notified_at is not None}

    async def get_last_soft_notified_bulk(self, remnawave_ids: list[int]) -> dict[int, datetime]:
        if not remnawave_ids:
            return {}
        result = await self._session.execute(
            select(
                AntifraudNotifiedUserModel.remnawave_id,
                AntifraudNotifiedUserModel.soft_notified_at,
            ).where(AntifraudNotifiedUserModel.remnawave_id.in_(remnawave_ids))
        )
        return {
            row.remnawave_id: row.soft_notified_at
            for row in result
            if row.soft_notified_at is not None
        }
