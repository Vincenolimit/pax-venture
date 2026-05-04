from sqlalchemy import Integer, REAL, TEXT, TIMESTAMP, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Thread(Base):
    __tablename__ = "threads"
    __table_args__ = (CheckConstraint("status IN ('active','resolved','abandoned')", name="ck_threads_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(TEXT, ForeignKey("players.id"), nullable=False)
    label: Mapped[str] = mapped_column(TEXT, nullable=False)
    importance: Mapped[float] = mapped_column(REAL, nullable=False, default=0.5)
    status: Mapped[str] = mapped_column(TEXT, nullable=False, default="active")
    opened_at_month: Mapped[int] = mapped_column(Integer, nullable=False)
    closed_at_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_referenced_month: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
