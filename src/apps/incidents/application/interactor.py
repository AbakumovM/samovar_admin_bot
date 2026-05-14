from src.apps.incidents.application.interfaces.gateway import IncidentGateway
from src.apps.incidents.application.interfaces.view import IncidentView
from src.apps.incidents.domain.commands import (
    CloseIncident,
    EscalateIncident,
    OpenIncident,
    RecordRestartAttempt,
    RecordSnapshot,
)
from src.apps.incidents.domain.models import IncidentInfo, NodeStatsSnapshotInfo


class IncidentInteractor:
    def __init__(self, gateway: IncidentGateway, view: IncidentView) -> None:
        self._gateway = gateway
        self._view = view

    async def open_incident(self, cmd: OpenIncident) -> IncidentInfo:
        return await self._gateway.open_incident(cmd)

    async def close_incident(self, cmd: CloseIncident) -> IncidentInfo:
        return await self._gateway.close_incident(cmd)

    async def record_restart_attempt(self, cmd: RecordRestartAttempt) -> IncidentInfo:
        return await self._gateway.record_restart_attempt(cmd)

    async def escalate_incident(self, cmd: EscalateIncident) -> IncidentInfo:
        return await self._gateway.escalate_incident(cmd)

    async def record_snapshot(self, cmd: RecordSnapshot) -> NodeStatsSnapshotInfo:
        return await self._gateway.record_snapshot(cmd)
