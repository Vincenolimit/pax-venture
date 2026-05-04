from sqlalchemy import Boolean, Integer, REAL, TEXT, TIMESTAMP, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (CheckConstraint("importance BETWEEN 0 AND 1", name="ck_decisions_importance"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(TEXT, ForeignKey("players.id"), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    seq_in_month: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_text: Mapped[str] = mapped_column(TEXT, nullable=False)
    inbox_ref_ids: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    narrative: Mapped[str] = mapped_column(TEXT, nullable=False)
    importance: Mapped[float] = mapped_column(REAL, nullable=False)
    cash_impact: Mapped[float] = mapped_column(REAL, nullable=False)
    revenue_impact: Mapped[float] = mapped_column(REAL, nullable=False)
    market_impact: Mapped[float] = mapped_column(REAL, nullable=False)
    employees_change: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(TEXT, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(REAL, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
