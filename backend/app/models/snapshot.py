from sqlalchemy import Integer, REAL, TEXT, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Snapshot(Base):
    __tablename__ = "monthly_snapshots"

    player_id: Mapped[str] = mapped_column(TEXT, ForeignKey("players.id"), primary_key=True)
    month: Mapped[int] = mapped_column(Integer, primary_key=True)
    cash: Mapped[float] = mapped_column(REAL, nullable=False)
    revenue: Mapped[float] = mapped_column(REAL, nullable=False)
    market_share: Mapped[float] = mapped_column(REAL, nullable=False)
    employees: Mapped[int] = mapped_column(Integer, nullable=False)
    burn_rate: Mapped[float] = mapped_column(REAL, nullable=False)
    leaderboard_rank: Mapped[int] = mapped_column(Integer, nullable=False)
