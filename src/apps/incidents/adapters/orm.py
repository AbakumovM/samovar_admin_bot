import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Base


class IncidentModel(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    node_uuid: Mapped[str] = mapped_column(String(255), index=True)
    node_name: Mapped[str] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status_message: Mapped[str] = mapped_column(String(1024))
    restart_attempts: Mapped[int] = mapped_column(Integer, default=0)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    downtime_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)


class NodeStatsSnapshotModel(Base):
    __tablename__ = "node_stats_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    node_uuid: Mapped[str] = mapped_column(String(255), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    users_online: Mapped[int] = mapped_column(Integer)
    traffic_used_bytes: Mapped[int] = mapped_column(BigInteger)
    xray_uptime: Mapped[int] = mapped_column(Integer)
    is_connected: Mapped[bool] = mapped_column(Boolean)
