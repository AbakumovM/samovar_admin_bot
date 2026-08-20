from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.antifraud.adapters.orm import AntifraudNotifiedUserModel, AntifraudViolationCountModel


class PostgresAntifraudGateway:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def mark_notified(self, remnawave_id: int, notified_at: datetime) -> None:
        stmt = (
            insert(AntifraudNotifiedUserModel)
            .values(remnawave_id=remnawave_id, notified_at=notified_at)
            .on_conflict_do_update(
                index_elements=["remnawave_id"],
                set_={"notified_at": notified_at},
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def mark_soft_notified(self, remnawave_id: int, notified_at: datetime) -> None:
        stmt = (
            insert(AntifraudNotifiedUserModel)
            .values(remnawave_id=remnawave_id, soft_notified_at=notified_at)
            .on_conflict_do_update(
                index_elements=["remnawave_id"],
                set_={"soft_notified_at": notified_at},
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def increment_violation_count(
        self, remnawave_id: int, now: datetime, window_seconds: int
    ) -> int:
        """Sliding-window violation counter: increments if the previous window
        hasn't expired, otherwise starts a fresh count of 1. Mirrors
        remnawave-limiter's Redis INCR-with-refreshing-TTL pattern, but as a
        fetch-then-write against Postgres — safe here since the antifraud
        scan is single-writer (no concurrent scans).
        """
        result = await self._session.execute(
            select(AntifraudViolationCountModel).where(
                AntifraudViolationCountModel.remnawave_id == remnawave_id
            )
        )
        row = result.scalar_one_or_none()
        new_count = 1 if row is None or row.window_expires_at <= now else row.count + 1
        expires_at = now + timedelta(seconds=window_seconds)

        stmt = (
            insert(AntifraudViolationCountModel)
            .values(remnawave_id=remnawave_id, count=new_count, window_expires_at=expires_at)
            .on_conflict_do_update(
                index_elements=["remnawave_id"],
                set_={"count": new_count, "window_expires_at": expires_at},
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return new_count

    async def reset_violation_count(self, remnawave_id: int) -> None:
        await self._session.execute(
            delete(AntifraudViolationCountModel).where(
                AntifraudViolationCountModel.remnawave_id == remnawave_id
            )
        )
        await self._session.flush()
