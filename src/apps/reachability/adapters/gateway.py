from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.reachability.adapters.orm import IpReachabilityStateModel
from src.apps.reachability.domain.models import IpState


class PostgresReachabilityGateway:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_state(
        self,
        state: IpState,
        last_results: dict[str, str | None],
        checked_at: datetime,
        changed: bool,
    ) -> None:
        values: dict[str, Any] = {
            "status": state.status,
            "pending_status": state.pending_status,
            "pending_count": state.pending_count,
            "last_results": last_results,
            "checked_at": checked_at,
            "notified_at": state.notified_at,
        }
        if changed:
            values["changed_at"] = checked_at
        stmt = pg_insert(IpReachabilityStateModel).values(ip=state.ip, **values)
        stmt = stmt.on_conflict_do_update(index_elements=["ip"], set_=values)
        await self._session.execute(stmt)
