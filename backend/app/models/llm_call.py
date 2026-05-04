from sqlalchemy import Boolean, Integer, REAL, TEXT, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str | None] = mapped_column(TEXT, ForeignKey("players.id"), nullable=True)
    call_type: Mapped[str] = mapped_column(TEXT, nullable=False)
    model: Mapped[str] = mapped_column(TEXT, nullable=False)
    in_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    out_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_hit_ratio: Mapped[float] = mapped_column(REAL, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(REAL, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    ts: Mapped[str] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
