from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class UserTrafficSnapshotInfo:
    user_uuid: str
    username: str
    used_bytes: int
    recorded_at: datetime


@dataclass(frozen=True)
class UserTrafficDailyInfo:
    user_uuid: str
    username: str
    date: date
    bytes_consumed: int
    anomaly_alerted: bool
