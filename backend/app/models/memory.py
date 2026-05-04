from sqlalchemy import Integer, TEXT, ForeignKey, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Memory(Base):
    __tablename__ = "memories"

    player_id: Mapped[str] = mapped_column(TEXT, ForeignKey("players.id"), primary_key=True)
    recent: Mapped[str] = mapped_column(TEXT, nullable=False, default="")
    period_summary: Mapped[str] = mapped_column(TEXT, nullable=False, default="")
    origin_story: Mapped[str] = mapped_column(TEXT, nullable=False, default="")
    period_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    period_end: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
