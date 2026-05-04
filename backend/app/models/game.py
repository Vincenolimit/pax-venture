from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime, timezone


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    company_name = Column(String, nullable=False)
    industry = Column(String, default="automotive")
    style = Column(String, default="balanced")  # aggressive, conservative, innovation
    risk_tolerance = Column(String, default="medium")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Current state
    current_month = Column(Integer, default=0)
    cash = Column(Float, default=10_000_000.0)
    revenue = Column(Float, default=0.0)
    expenses = Column(Float, default=0.0)
    market_share = Column(Float, default=5.0)
    is_active = Column(Boolean, default=True)

    # Relationships
    messages = relationship("Message", back_populates="player", order_by="Message.created_at")
    decisions = relationship("Decision", back_populates="player", order_by="Decision.month")
    monthly_reports = relationship("MonthlyReport", back_populates="player", order_by="MonthlyReport.month")


class Message(Base):
    """Inbox messages — emails, market news, board requests, etc."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String, ForeignKey("players.id"), nullable=False)
    month = Column(Integer, nullable=False)
    sender = Column(String, nullable=False)  # "Board", "Market", "Supplier", "Competitor", "System"
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    category = Column(String, default="info")  # info, warning, opportunity, crisis, board
    is_read = Column(Boolean, default=False)
    requires_action = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    player = relationship("Player", back_populates="messages")


class Decision(Base):
    """Decisions made by the player each month."""
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String, ForeignKey("players.id"), nullable=False)
    month = Column(Integer, nullable=False)
    decision_text = Column(Text, nullable=False)
    llm_context = Column(Text, default="")  # what the LLM considered
    outcome = Column(Text, default="")  # LLM-generated result
    cash_impact = Column(Float, default=0.0)
    revenue_impact = Column(Float, default=0.0)
    market_impact = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    player = relationship("Player", back_populates="decisions")


class MonthlyReport(Base):
    """End-of-month financial snapshot."""
    __tablename__ = "monthly_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String, ForeignKey("players.id"), nullable=False)
    month = Column(Integer, nullable=False)
    cash = Column(Float, nullable=False)
    revenue = Column(Float, nullable=False)
    expenses = Column(Float, nullable=False)
    profit = Column(Float, nullable=False)
    market_share = Column(Float, nullable=False)
    employees = Column(Integer, default=50)
    summary = Column(Text, default="")

    player = relationship("Player", back_populates="monthly_reports")


class LeaderboardEntry(Base):
    """Denormalized leaderboard for fast queries."""
    __tablename__ = "leaderboard"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String, ForeignKey("players.id"), unique=True)
    company_name = Column(String, nullable=False)
    cash = Column(Float, nullable=False)
    revenue = Column(Float, nullable=False)
    market_share = Column(Float, nullable=False)
    current_month = Column(Integer, nullable=False)
    rank = Column(Integer, default=0)
