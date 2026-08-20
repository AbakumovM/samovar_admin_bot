from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MarkNotified:
    remnawave_id: int
    notified_at: datetime
