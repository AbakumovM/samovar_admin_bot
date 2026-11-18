
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.users.adapters.orm import (
    UserTrafficDailyModel,
    UserTrafficLastSnapshotModel,
    UserTrafficThresholdAlertModel,
)
from src.apps.users.domain.commands import (
    MarkAnomalyAlerted,
    MarkThresholdsAlerted,
    PurgeThresholdAlerts,
    UpdateLastSnapshot,
    UpsertDailyTraffic,
)


class PostgresUserTrafficGateway:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_daily_traffic(self, cmd: UpsertDailyTraffic) -> None:
        stmt = (
            pg_insert(UserTrafficDailyModel)
            .values(
                user_uuid=cmd.user_uuid,
                username=cmd.username,
                date=cmd.date,
                bytes_consumed=cmd.delta_bytes,
                anomaly_alerted=False,
            )
            .on_conflict_do_update(
                index_elements=["user_uuid", "date"],
                set_={
                    "bytes_consumed": UserTrafficDailyModel.bytes_consumed + cmd.delta_bytes,
                    "username": cmd.username,
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def update_last_snapshot(self, cmd: UpdateLastSnapshot) -> None:
        stmt = (
            pg_insert(UserTrafficLastSnapshotModel)
            .values(
                user_uuid=cmd.user_uuid,
                username=cmd.username,
                used_bytes=cmd.used_bytes,
                recorded_at=cmd.recorded_at,
            )
            .on_conflict_do_update(
                index_elements=["user_uuid"],
                set_={
                    "username": cmd.username,
                    "used_bytes": cmd.used_bytes,
                    "recorded_at": cmd.recorded_at,
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def mark_anomaly_alerted(self, cmd: MarkAnomalyAlerted) -> None:
        await self._session.execute(
            update(UserTrafficDailyModel)
            .where(
                UserTrafficDailyModel.user_uuid == cmd.user_uuid,
                UserTrafficDailyModel.date == cmd.date,
            )
            .values(anomaly_alerted=True)
        )
        await self._session.flush()

    async def mark_thresholds_alerted(self, cmd: MarkThresholdsAlerted) -> None:
        if not cmd.thresholds_gb:
            return
        stmt = pg_insert(UserTrafficThresholdAlertModel).values(
            [
                {"user_uuid": cmd.user_uuid, "threshold_gb": t, "alerted_at": cmd.alerted_at}
                for t in cmd.thresholds_gb
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_uuid", "threshold_gb"],
            set_={"alerted_at": stmt.excluded.alerted_at},
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def purge_threshold_alerts(self, cmd: PurgeThresholdAlerts) -> None:
        await self._session.execute(
            delete(UserTrafficThresholdAlertModel).where(
                UserTrafficThresholdAlertModel.alerted_at < cmd.before
            )
        )
