from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class UpsertDailyTraffic:
    user_uuid: str
    username: str
    date: date
    delta_bytes: int


@dataclass(frozen=True)
class UpdateLastSnapshot:
    user_uuid: str
    username: str
    used_bytes: int
    recorded_at: datetime


@dataclass(frozen=True)
class MarkAnomalyAlerted:
    user_uuid: str
    date: date


@dataclass(frozen=True)
class AddHourlyTraffic:
    user_uuid: str
    recorded_at: datetime
    delta_bytes: int


@dataclass(frozen=True)
class MarkThresholdsAlerted:
    user_uuid: str
    thresholds_gb: list[int]
    alerted_at: datetime


@dataclass(frozen=True)
class PurgeTrafficHistory:
    before: datetime
