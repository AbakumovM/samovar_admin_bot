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
