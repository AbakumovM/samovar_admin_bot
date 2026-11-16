from datetime import datetime
from typing import Protocol

from src.apps.reachability.domain.models import IpState


class ReachabilityGateway(Protocol):
    async def save_state(
        self,
        state: IpState,
        last_results: dict[str, str | None],
        checked_at: datetime,
        changed: bool,
    ) -> None: ...
