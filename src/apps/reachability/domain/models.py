from dataclasses import dataclass


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
