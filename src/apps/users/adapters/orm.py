from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Base


class UserTrafficLastSnapshotModel(Base):
    __tablename__ = "user_traffic_last_snapshot"

    user_uuid: Mapped[str] = mapped_column(String(255), primary_key=True)
    username: Mapped[str] = mapped_column(String(255))
    used_bytes: Mapped[int] = mapped_column(BigInteger)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserTrafficDailyModel(Base):
    __tablename__ = "user_traffic_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_uuid: Mapped[str] = mapped_column(String(255), index=True)
    username: Mapped[str] = mapped_column(String(255))
    date: Mapped[date] = mapped_column(Date, index=True)
    bytes_consumed: Mapped[int] = mapped_column(BigInteger, default=0)
    anomaly_alerted: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("user_uuid", "date", name="uq_user_traffic_daily"),
    )
