from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Base


class AntifraudNotifiedUserModel(Base):
    __tablename__ = "antifraud_notified_users"

    remnawave_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    soft_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AntifraudViolationCountModel(Base):
    __tablename__ = "antifraud_violation_counts"

    remnawave_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    count: Mapped[int] = mapped_column(Integer)
    window_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
