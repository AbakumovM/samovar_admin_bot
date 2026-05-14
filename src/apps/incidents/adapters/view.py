from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.incidents.adapters.orm import IncidentModel, NodeStatsSnapshotModel
from src.apps.incidents.domain.models import IncidentInfo


def _to_incident_info(m: IncidentModel) -> IncidentInfo:
    return IncidentInfo(
        id=m.id,
        node_uuid=m.node_uuid,
        node_name=m.node_name,
        started_at=m.started_at,
        resolved_at=m.resolved_at,
        last_status_message=m.last_status_message,
        restart_attempts=m.restart_attempts,
        escalated=m.escalated,
        downtime_seconds=m.downtime_seconds,
    )


class PostgresIncidentView:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_open_incident(self, node_uuid: str) -> IncidentInfo | None:
        result = await self._session.execute(
            select(IncidentModel)
            .where(
                IncidentModel.node_uuid == node_uuid,
                IncidentModel.resolved_at.is_(None),
            )
            .order_by(IncidentModel.started_at.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return _to_incident_info(model) if model else None

    async def count_recent_incidents(
        self, node_uuid: str, window_minutes: int
    ) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        result = await self._session.execute(
            select(func.count())
            .select_from(IncidentModel)
            .where(
                IncidentModel.node_uuid == node_uuid,
                IncidentModel.started_at >= cutoff,
            )
        )
        return result.scalar_one()

    async def get_recent_incidents(self, limit: int) -> list[IncidentInfo]:
        result = await self._session.execute(
            select(IncidentModel)
            .order_by(IncidentModel.started_at.desc())
            .limit(limit)
        )
        return [_to_incident_info(m) for m in result.scalars().all()]

    async def get_incidents_by_node(
        self, node_uuid: str, limit: int
    ) -> list[IncidentInfo]:
        result = await self._session.execute(
            select(IncidentModel)
            .where(IncidentModel.node_uuid == node_uuid)
            .order_by(IncidentModel.started_at.desc())
            .limit(limit)
        )
        return [_to_incident_info(m) for m in result.scalars().all()]

    async def get_node_uptime_percent(self, node_uuid: str, days: int) -> float:
        period_seconds = days * 86400
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(func.coalesce(func.sum(IncidentModel.downtime_seconds), 0))
            .where(
                IncidentModel.node_uuid == node_uuid,
                IncidentModel.started_at >= cutoff,
                IncidentModel.resolved_at.is_not(None),
            )
        )
        total_downtime: int = result.scalar_one()
        uptime_pct = max(0.0, (1 - total_downtime / period_seconds) * 100)
        return round(uptime_pct, 2)

    async def get_worst_nodes(
        self, days: int, limit: int
    ) -> list[tuple[str, str, int, float]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(
                IncidentModel.node_uuid,
                IncidentModel.node_name,
                func.count().label("incident_count"),
            )
            .where(IncidentModel.started_at >= cutoff)
            .group_by(IncidentModel.node_uuid, IncidentModel.node_name)
            .order_by(func.count().desc())
            .limit(limit)
        )
        rows = result.all()
        out = []
        for node_uuid, node_name, count in rows:
            uptime = await self.get_node_uptime_percent(node_uuid, days)
            out.append((node_uuid, node_name, count, uptime))
        return out

    async def get_incidents_by_period(self, days: int) -> list[IncidentInfo]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(IncidentModel)
            .where(IncidentModel.started_at >= cutoff)
            .order_by(IncidentModel.started_at.desc())
        )
        return [_to_incident_info(m) for m in result.scalars().all()]
