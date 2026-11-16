from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Base


class IpReachabilityStateModel(Base):
    __tablename__ = "ip_reachability_state"

    ip: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pending_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    last_results: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
