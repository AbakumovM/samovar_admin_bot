from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.users.adapters.orm import UserTrafficDailyModel, UserTrafficLastSnapshotModel
from src.apps.users.domain.models import UserTrafficDailyInfo, UserTrafficSnapshotInfo


def _to_snapshot_info(m: UserTrafficLastSnapshotModel) -> UserTrafficSnapshotInfo:
    return UserTrafficSnapshotInfo(
        user_uuid=m.user_uuid,
        username=m.username,
        used_bytes=m.used_bytes,
        recorded_at=m.recorded_at,
    )


def _to_daily_info(m: UserTrafficDailyModel) -> UserTrafficDailyInfo:
    return UserTrafficDailyInfo(
        user_uuid=m.user_uuid,
        username=m.username,
        date=m.date,
        bytes_consumed=m.bytes_consumed,
        anomaly_alerted=m.anomaly_alerted,
    )


class PostgresUserTrafficView:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_last_snapshot(self, user_uuid: str) -> UserTrafficSnapshotInfo | None:
        result = await self._session.execute(
            select(UserTrafficLastSnapshotModel).where(
                UserTrafficLastSnapshotModel.user_uuid == user_uuid
            )
        )
        m = result.scalar_one_or_none()
        return _to_snapshot_info(m) if m else None

    async def get_top_traffic(self, days: int, limit: int) -> list[UserTrafficDailyInfo]:
        cutoff = date.today() - timedelta(days=days - 1)
        result = await self._session.execute(
            select(
                UserTrafficDailyModel.user_uuid,
                UserTrafficDailyModel.username,
                func.sum(UserTrafficDailyModel.bytes_consumed).label("total"),
            )
            .where(UserTrafficDailyModel.date >= cutoff)
            .group_by(UserTrafficDailyModel.user_uuid, UserTrafficDailyModel.username)
            .order_by(func.sum(UserTrafficDailyModel.bytes_consumed).desc())
            .limit(limit)
        )
        today = date.today()
        return [
            UserTrafficDailyInfo(
                user_uuid=row.user_uuid,
                username=row.username,
                date=today,
                bytes_consumed=row.total,
                anomaly_alerted=False,
            )
            for row in result.all()
        ]

    async def get_top_traffic_today(self, limit: int) -> list[UserTrafficDailyInfo]:
        result = await self._session.execute(
            select(UserTrafficDailyModel)
            .where(UserTrafficDailyModel.date == date.today())
            .order_by(UserTrafficDailyModel.bytes_consumed.desc())
            .limit(limit)
        )
        return [_to_daily_info(m) for m in result.scalars().all()]

    async def get_today_unalerted(self) -> list[UserTrafficDailyInfo]:
        result = await self._session.execute(
            select(UserTrafficDailyModel).where(
                UserTrafficDailyModel.date == date.today(),
                UserTrafficDailyModel.anomaly_alerted.is_(False),
            )
        )
        return [_to_daily_info(m) for m in result.scalars().all()]

    async def get_avg_daily_7d(self, user_uuid: str) -> float:
        cutoff = date.today() - timedelta(days=7)
        result = await self._session.execute(
            select(func.avg(UserTrafficDailyModel.bytes_consumed)).where(
                UserTrafficDailyModel.user_uuid == user_uuid,
                UserTrafficDailyModel.date >= cutoff,
                UserTrafficDailyModel.date < date.today(),
            )
        )
        avg = result.scalar_one_or_none()
        return float(avg or 0)

    async def get_user_traffic_by_days(
        self, username: str, days: int
    ) -> list[UserTrafficDailyInfo]:
        cutoff = date.today() - timedelta(days=days - 1)
        result = await self._session.execute(
            select(UserTrafficDailyModel)
            .where(
                UserTrafficDailyModel.username == username,
                UserTrafficDailyModel.date >= cutoff,
            )
            .order_by(UserTrafficDailyModel.date.asc())
        )
        return [_to_daily_info(m) for m in result.scalars().all()]
