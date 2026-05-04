from sqlalchemy import TEXT, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Relationship(Base):
    __tablename__ = "relationships"

    player_id: Mapped[str] = mapped_column(TEXT, ForeignKey("players.id"), primary_key=True)
    key: Mapped[str] = mapped_column(TEXT, primary_key=True)
    value: Mapped[str] = mapped_column(TEXT, nullable=False)
