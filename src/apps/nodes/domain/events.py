from dataclasses import dataclass
from datetime import datetime

from src.apps.nodes.domain.models import NodeInfo


@dataclass(frozen=True)
class NodeWentOffline:
    node: NodeInfo
    detected_at: datetime


@dataclass(frozen=True)
class NodeCameOnline:
    node: NodeInfo
    detected_at: datetime


@dataclass(frozen=True)
class NodeEscalated:
    node: NodeInfo
    detected_at: datetime
