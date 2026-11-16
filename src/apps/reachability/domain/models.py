from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class IpState:
    ip: str
    status: str | None  # accepted: ok | partial | blocked; None until first confirmed
    pending_status: str | None
    pending_count: int


@dataclass(frozen=True)
class Transition:
    ip: str
    previous: str | None
    current: str


@dataclass(frozen=True)
class IpStateRow:
    ip: str
    status: str
    last_results: dict[str, str | None]
    changed_at: datetime | None
    checked_at: datetime
