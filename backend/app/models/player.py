from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, REAL, TEXT, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        CheckConstraint("model_tier IN ('cheap','balanced','premium')", name="ck_players_model_tier"),
    )

    id: Mapped[str] = mapped_column(TEXT, primary_key=True)
    industry_id: Mapped[str] = mapped_column(TEXT, ForeignKey("industries.id"), nullable=False)
    name: Mapped[str] = mapped_column(TEXT, nullable=False)
    company_name: Mapped[str] = mapped_column(TEXT, nullable=False)
    style: Mapped[str] = mapped_column(TEXT, nullable=False)
    risk_tolerance: Mapped[str] = mapped_column(TEXT, nullable=False)
    model_tier: Mapped[str] = mapped_column(TEXT, nullable=False, default="balanced")
    current_month: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cash: Mapped[float] = mapped_column(REAL, nullable=False)
    revenue: Mapped[float] = mapped_column(REAL, nullable=False, default=0)
    market_share: Mapped[float] = mapped_column(REAL, nullable=False)
    employees: Mapped[int] = mapped_column(Integer, nullable=False)
    game_over: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eliminated_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_cap_usd: Mapped[float | None] = mapped_column(REAL, nullable=True)
    cost_spent_usd: Mapped[float] = mapped_column(REAL, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
