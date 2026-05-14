from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class IncidentInfo:
    id: UUID
    node_uuid: str
    node_name: str
    started_at: datetime
    resolved_at: datetime | None
    last_status_message: str
    restart_attempts: int
    escalated: bool
    downtime_seconds: int | None


@dataclass(frozen=True)
class NodeStatsSnapshotInfo:
    id: UUID
    node_uuid: str
    captured_at: datetime
    users_online: int
    traffic_used_bytes: int
    xray_uptime: int
    is_connected: bool
