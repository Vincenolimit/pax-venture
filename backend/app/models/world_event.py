from sqlalchemy import Integer, TEXT, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class WorldEvent(Base):
    __tablename__ = "world_events"
    __table_args__ = (CheckConstraint("severity IN ('minor','major','crisis')", name="ck_world_severity"),)

    id: Mapped[str] = mapped_column(TEXT, primary_key=True)
    industry_id: Mapped[str] = mapped_column(TEXT, ForeignKey("industries.id"), nullable=False)
    fire_at_month: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_months: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(TEXT, nullable=False)
    narrative_seed: Mapped[str] = mapped_column(TEXT, nullable=False)
    mechanical_effects: Mapped[str] = mapped_column(TEXT, nullable=False)
