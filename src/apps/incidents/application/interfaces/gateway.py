from typing import Protocol

from src.apps.incidents.domain.commands import (
    CloseIncident,
    EscalateIncident,
    OpenIncident,
    RecordRestartAttempt,
    RecordSnapshot,
)
from src.apps.incidents.domain.models import IncidentInfo, NodeStatsSnapshotInfo


class IncidentGateway(Protocol):
    async def open_incident(self, cmd: OpenIncident) -> IncidentInfo: ...
    async def close_incident(self, cmd: CloseIncident) -> IncidentInfo: ...
    async def record_restart_attempt(self, cmd: RecordRestartAttempt) -> IncidentInfo: ...
    async def escalate_incident(self, cmd: EscalateIncident) -> IncidentInfo: ...
    async def record_snapshot(self, cmd: RecordSnapshot) -> NodeStatsSnapshotInfo: ...
