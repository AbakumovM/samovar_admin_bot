from dataclasses import dataclass
from datetime import datetime
from typing import Literal

GroupingMode = Literal["ip", "subnet", "asn"]


@dataclass(frozen=True)
class IpSighting:
    ip: str
    last_seen: datetime


@dataclass(frozen=True)
class NodeUserConnections:
    user_id: int
    ips: tuple[IpSighting, ...]


@dataclass(frozen=True)
class NodeConnectionsResult:
    node_uuid: str
    node_name: str
    ok: bool
    users: tuple[NodeUserConnections, ...] = ()
    failure_reason: str | None = None


@dataclass(frozen=True)
class AggregatedIp:
    ip: str
    node_names: tuple[str, ...]
    last_seen: datetime
    asn: int | None = None
    asn_org: str | None = None


@dataclass(frozen=True)
class FlaggedUser:
    remnawave_id: int
    username: str
    telegram_id: int | None
    ip_count: int
    group_count: int
    grouping_mode: GroupingMode
    ips: tuple[AggregatedIp, ...]
    hwid_device_limit: int
    threshold: int
    is_hard: bool
    ru_node_ip_count: int = 0
    ru_node_threshold: int = 0
    no_active_payment: bool | None = None
    criteria_matched: int = 0
