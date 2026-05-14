import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.incidents.adapters.orm import IncidentModel, NodeStatsSnapshotModel
from src.apps.incidents.domain.commands import (
    CloseIncident,
    EscalateIncident,
    OpenIncident,
    RecordRestartAttempt,
    RecordSnapshot,
)
from src.apps.incidents.domain.models import IncidentInfo, NodeStatsSnapshotInfo


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


def _to_snapshot_info(m: NodeStatsSnapshotModel) -> NodeStatsSnapshotInfo:
    return NodeStatsSnapshotInfo(
        id=m.id,
        node_uuid=m.node_uuid,
        captured_at=m.captured_at,
        users_online=m.users_online,
        traffic_used_bytes=m.traffic_used_bytes,
        xray_uptime=m.xray_uptime,
        is_connected=m.is_connected,
    )


class PostgresIncidentGateway:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def open_incident(self, cmd: OpenIncident) -> IncidentInfo:
        model = IncidentModel(
            id=uuid.uuid4(),
            node_uuid=cmd.node_uuid,
            node_name=cmd.node_name,
            started_at=cmd.started_at,
            resolved_at=None,
            last_status_message=cmd.last_status_message,
            restart_attempts=0,
            escalated=False,
            downtime_seconds=None,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_incident_info(model)

    async def close_incident(self, cmd: CloseIncident) -> IncidentInfo:
        result = await self._session.execute(
            select(IncidentModel).where(IncidentModel.id == cmd.incident_id)
        )
        model = result.scalar_one()
        downtime = int((cmd.resolved_at - model.started_at).total_seconds())
        model.resolved_at = cmd.resolved_at
        model.downtime_seconds = downtime
        await self._session.flush()
        return _to_incident_info(model)

    async def record_restart_attempt(self, cmd: RecordRestartAttempt) -> IncidentInfo:
        result = await self._session.execute(
            select(IncidentModel).where(IncidentModel.id == cmd.incident_id)
        )
        model = result.scalar_one()
        model.restart_attempts += 1
        await self._session.flush()
        return _to_incident_info(model)

    async def escalate_incident(self, cmd: EscalateIncident) -> IncidentInfo:
        result = await self._session.execute(
            select(IncidentModel).where(IncidentModel.id == cmd.incident_id)
        )
        model = result.scalar_one()
        model.escalated = True
        await self._session.flush()
        return _to_incident_info(model)

    async def record_snapshot(self, cmd: RecordSnapshot) -> NodeStatsSnapshotInfo:
        model = NodeStatsSnapshotModel(
            id=uuid.uuid4(),
            node_uuid=cmd.node_uuid,
            captured_at=cmd.captured_at,
            users_online=cmd.users_online,
            traffic_used_bytes=cmd.traffic_used_bytes,
            xray_uptime=cmd.xray_uptime,
            is_connected=cmd.is_connected,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_snapshot_info(model)
