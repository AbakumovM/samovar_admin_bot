from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Base


class MutedNodeModel(Base):
    __tablename__ = "muted_nodes"

    node_uuid: Mapped[str] = mapped_column(String(255), primary_key=True)
    muted_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    muted_by_telegram_id: Mapped[int] = mapped_column(BigInteger)
