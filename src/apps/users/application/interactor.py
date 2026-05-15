from src.apps.users.application.interfaces.gateway import UserTrafficGateway
from src.apps.users.domain.commands import MarkAnomalyAlerted, UpdateLastSnapshot, UpsertDailyTraffic


class UserTrafficInteractor:
    def __init__(self, gateway: UserTrafficGateway) -> None:
        self._gateway = gateway

    async def upsert_daily_traffic(self, cmd: UpsertDailyTraffic) -> None:
        await self._gateway.upsert_daily_traffic(cmd)

    async def update_last_snapshot(self, cmd: UpdateLastSnapshot) -> None:
        await self._gateway.update_last_snapshot(cmd)

    async def mark_anomaly_alerted(self, cmd: MarkAnomalyAlerted) -> None:
        await self._gateway.mark_anomaly_alerted(cmd)
