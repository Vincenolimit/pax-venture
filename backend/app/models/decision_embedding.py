from sqlalchemy import Integer, REAL, TEXT, ForeignKey, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class DecisionEmbedding(Base):
    __tablename__ = "decision_embeddings"

    decision_id: Mapped[int] = mapped_column(Integer, ForeignKey("decisions.id"), primary_key=True)
    player_id: Mapped[str] = mapped_column(TEXT, ForeignKey("players.id"), nullable=False)
    model: Mapped[str] = mapped_column(TEXT, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
