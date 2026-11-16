from datetime import datetime

from sqlalchemy import String, any_, bindparam, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.reachability.adapters.orm import IpReachabilityStateModel
from src.apps.reachability.domain.models import IpState, IpStateRow


class PostgresReachabilityView:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_states(self, ips: list[str]) -> dict[str, IpState]:
        if not ips:
            return {}
        # One array bind instead of an IN-list: asyncpg caps a query at 32767 params.
        ip_array = bindparam(
            "ips",
            ips,
            type_=ARRAY(String),
        )
        result = await self._session.execute(
            select(IpReachabilityStateModel).where(IpReachabilityStateModel.ip == any_(ip_array))
        )
        return {
            m.ip: IpState(m.ip, m.status, m.pending_status, m.pending_count)
            for m in result.scalars().all()
        }

    async def list_not_ok(self) -> list[IpStateRow]:
        result = await self._session.execute(
            select(IpReachabilityStateModel)
            .where(IpReachabilityStateModel.status.in_(["partial", "blocked"]))
            .order_by(IpReachabilityStateModel.changed_at.desc())
        )
        return [
            IpStateRow(
                ip=m.ip,
                status=str(m.status),
                last_results=dict(m.last_results or {}),
                changed_at=m.changed_at,
                checked_at=m.checked_at,
            )
            for m in result.scalars().all()
        ]

    async def last_checked_at(self) -> datetime | None:
        result = await self._session.execute(select(func.max(IpReachabilityStateModel.checked_at)))
        return result.scalar_one_or_none()
