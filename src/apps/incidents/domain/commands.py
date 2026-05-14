from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class OpenIncident:
    node_uuid: str
    node_name: str
    started_at: datetime
    last_status_message: str


@dataclass(frozen=True)
class CloseIncident:
    incident_id: UUID
    resolved_at: datetime


@dataclass(frozen=True)
class RecordRestartAttempt:
    incident_id: UUID


@dataclass(frozen=True)
class EscalateIncident:
    incident_id: UUID


@dataclass(frozen=True)
class RecordSnapshot:
    node_uuid: str
    captured_at: datetime
    users_online: int
    traffic_used_bytes: int
    xray_uptime: int
    is_connected: bool
