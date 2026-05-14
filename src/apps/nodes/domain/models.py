from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NodeInfo:
    uuid: str
    name: str
    address: str
    country_code: str
    provider: str
    is_connected: bool
    is_connecting: bool
    is_disabled: bool
    last_status_change: datetime
    last_status_message: str
    xray_uptime: int
    users_online: int
    traffic_used_bytes: int
