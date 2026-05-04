from sqlalchemy import Integer, REAL, TEXT, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Competitor(Base):
    __tablename__ = "competitors"
    __table_args__ = (CheckConstraint("posture IN ('OBSERVING','DEFENSIVE','AGGRESSIVE','STRUGGLING')", name="ck_comp_posture"),)

    id: Mapped[str] = mapped_column(TEXT, primary_key=True)
    player_id: Mapped[str] = mapped_column(TEXT, ForeignKey("players.id"), nullable=False)
    industry_id: Mapped[str] = mapped_column(TEXT, ForeignKey("industries.id"), nullable=False)
    template_id: Mapped[str] = mapped_column(TEXT, nullable=False)
    name: Mapped[str] = mapped_column(TEXT, nullable=False)
    cash: Mapped[float] = mapped_column(REAL, nullable=False)
    revenue: Mapped[float] = mapped_column(REAL, nullable=False)
    market_share: Mapped[float] = mapped_column(REAL, nullable=False)
    expenses: Mapped[float] = mapped_column(REAL, nullable=False)
    base_growth: Mapped[float] = mapped_column(REAL, nullable=False)
    volatility: Mapped[float] = mapped_column(REAL, nullable=False)
    posture: Mapped[str] = mapped_column(TEXT, nullable=False, default="OBSERVING")
    posture_until_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
