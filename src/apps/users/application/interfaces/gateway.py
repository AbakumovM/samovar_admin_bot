from typing import Protocol

from src.apps.users.domain.commands import (
    MarkAnomalyAlerted,
    MarkThresholdsAlerted,
    PurgeThresholdAlerts,
    UpdateLastSnapshot,
    UpsertDailyTraffic,
)


class UserTrafficGateway(Protocol):
    async def upsert_daily_traffic(self, cmd: UpsertDailyTraffic) -> None: ...
    async def update_last_snapshot(self, cmd: UpdateLastSnapshot) -> None: ...
    async def mark_anomaly_alerted(self, cmd: MarkAnomalyAlerted) -> None: ...
    async def mark_thresholds_alerted(self, cmd: MarkThresholdsAlerted) -> None: ...
    async def purge_threshold_alerts(self, cmd: PurgeThresholdAlerts) -> None: ...
