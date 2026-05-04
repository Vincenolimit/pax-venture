from sqlalchemy import Boolean, TEXT, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Flag(Base):
    __tablename__ = "flags"

    player_id: Mapped[str] = mapped_column(TEXT, ForeignKey("players.id"), primary_key=True)
    flag_name: Mapped[str] = mapped_column(TEXT, primary_key=True)
    flag_value: Mapped[bool] = mapped_column(Boolean, nullable=False)
