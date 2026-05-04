from sqlalchemy import Boolean, Integer, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Industry(Base):
    __tablename__ = "industries"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    starting_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    financial_constants: Mapped[str] = mapped_column(Text, nullable=False)
    flag_vocabulary: Mapped[str] = mapped_column(Text, nullable=False)
    intent_taxonomy: Mapped[str] = mapped_column(Text, nullable=False)
    relationship_keys: Mapped[str] = mapped_column(Text, nullable=False)
    relationship_vocab: Mapped[str] = mapped_column(Text, nullable=False)
    sender_vocab: Mapped[str] = mapped_column(Text, nullable=False)
    category_vocab: Mapped[str] = mapped_column(Text, nullable=False)
    employees_change_clamp: Mapped[str] = mapped_column(Text, nullable=False)
    cash_impact_clamp: Mapped[str] = mapped_column(Text, nullable=False)
    revenue_impact_clamp: Mapped[str] = mapped_column(Text, nullable=False)
    market_impact_clamp: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_models: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())

