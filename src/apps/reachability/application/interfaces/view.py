from datetime import datetime
from typing import Protocol

from src.apps.reachability.domain.models import IpState, IpStateRow


class ReachabilityView(Protocol):
    async def get_states(self, ips: list[str]) -> dict[str, IpState]: ...
    async def list_not_ok(self, checked_since: datetime) -> list[IpStateRow]: ...
    async def last_checked_at(self) -> datetime | None: ...
