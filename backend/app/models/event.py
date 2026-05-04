from sqlalchemy import CheckConstraint, Index, Integer, ForeignKey, TEXT, TIMESTAMP, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("source IN ('player','llm','kernel','world','competitor')", name="ck_events_source"),
        Index("idx_events_player_month", "player_id", "month", "seq_in_month"),
        Index("idx_events_idem", "player_id", "idempotency_key", unique=True, sqlite_where=text("idempotency_key IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(TEXT, ForeignKey("players.id"), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    seq_in_month: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[str] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    kind: Mapped[str] = mapped_column(TEXT, nullable=False)
    source: Mapped[str] = mapped_column(TEXT, nullable=False)
    payload_json: Mapped[str] = mapped_column(TEXT, nullable=False)
    parent_event_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("events.id"), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
