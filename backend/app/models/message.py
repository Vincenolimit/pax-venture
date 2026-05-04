from sqlalchemy import Integer, TEXT, TIMESTAMP, ForeignKey, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(TEXT, ForeignKey("players.id"), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    sender: Mapped[str] = mapped_column(TEXT, nullable=False)
    subject: Mapped[str] = mapped_column(TEXT, nullable=False)
    body: Mapped[str] = mapped_column(TEXT, nullable=False)
    category: Mapped[str] = mapped_column(TEXT, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parent_message_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("messages.id"), nullable=True)
    thread_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("threads.id"), nullable=True)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
