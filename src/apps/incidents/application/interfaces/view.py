from typing import Protocol
from uuid import UUID

from src.apps.incidents.domain.models import IncidentInfo


class IncidentView(Protocol):
    async def get_open_incident(self, node_uuid: str) -> IncidentInfo | None: ...
    async def count_recent_incidents(
        self, node_uuid: str, window_minutes: int
    ) -> int: ...
    async def get_recent_incidents(self, limit: int) -> list[IncidentInfo]: ...
    async def get_incidents_by_node(
        self, node_uuid: str, limit: int
    ) -> list[IncidentInfo]: ...
    async def get_node_uptime_percent(
        self, node_uuid: str, days: int
    ) -> float: ...
    async def get_worst_nodes(
        self, days: int, limit: int
    ) -> list[tuple[str, str, int, float]]: ...
    async def get_incidents_by_period(
        self, days: int
    ) -> list[IncidentInfo]: ...
