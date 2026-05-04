"""API routes — REST endpoints + WebSocket for real-time updates."""

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.models.game import Player, Message, Decision, MonthlyReport
from app.services.game_engine import (
    create_player, start_month, submit_decision, end_month, get_leaderboard
)
from pydantic import BaseModel
from typing import Optional


router = APIRouter()


# --- Schemas ---

class PlayerCreate(BaseModel):
    name: str
    company_name: str
    industry: str = "automotive"
    style: str = "balanced"
    risk_tolerance: str = "medium"

class DecisionSubmit(BaseModel):
    decision_text: str


# --- Player endpoints ---

@router.post("/players", response_model=dict)
async def create_new_player(player: PlayerCreate, session: AsyncSession = Depends(get_session)):
    p = await create_player(
        session, player.name, player.company_name,
        player.industry, player.style, player.risk_tolerance
    )
    return {
        "id": p.id, "name": p.name, "company_name": p.company_name,
        "industry": p.industry, "cash": p.cash, "current_month": p.current_month,
    }


@router.get("/players/{player_id}", response_model=dict)
async def get_player(player_id: str, session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    result = await session.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(404, "Player not found")
    return {
        "id": player.id, "name": player.name, "company_name": player.company_name,
        "industry": player.industry, "cash": player.cash, "revenue": player.revenue,
        "market_share": player.market_share, "current_month": player.current_month,
        "style": player.style, "risk_tolerance": player.risk_tolerance,
    }


# --- Inbox endpoints ---

@router.get("/players/{player_id}/inbox", response_model=list)
async def get_inbox(player_id: str, session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    result = await session.execute(
        select(Message)
        .where(Message.player_id == player_id)
        .order_by(Message.month.desc(), Message.created_at.desc())
    )
    messages = result.scalars().all()
    return [
        {
            "id": m.id, "month": m.month, "sender": m.sender,
            "subject": m.subject, "body": m.body, "category": m.category,
            "is_read": m.is_read, "requires_action": m.requires_action,
        }
        for m in messages
    ]


@router.post("/players/{player_id}/inbox/{message_id}/read")
async def mark_read(player_id: str, message_id: int, session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    result = await session.execute(
        select(Message).where(Message.id == message_id, Message.player_id == player_id)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(404, "Message not found")
    msg.is_read = True
    await session.commit()
    return {"status": "read"}


# --- Game state endpoints ---

@router.post("/players/{player_id}/start-month")
async def advance_month(player_id: str, session: AsyncSession = Depends(get_session)):
    """Start a new month — generates inbox messages."""
    try:
        messages = await start_month(session, player_id)
        return {
            "month": messages[0].month if messages else 0,
            "new_messages": [
                {
                    "id": m.id, "sender": m.sender, "subject": m.subject,
                    "body": m.body, "category": m.category,
                    "requires_action": m.requires_action,
                }
                for m in messages
            ],
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/players/{player_id}/decide")
async def make_decision(player_id: str, body: DecisionSubmit, session: AsyncSession = Depends(get_session)):
    """Submit a decision for the current month."""
    try:
        result = await submit_decision(session, player_id, body.decision_text)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/players/{player_id}/end-month")
async def finish_month(player_id: str, session: AsyncSession = Depends(get_session)):
    """End the current month — generates monthly report."""
    try:
        report = await end_month(session, player_id)
        return {
            "month": report.month, "cash": report.cash,
            "revenue": report.revenue, "expenses": report.expenses,
            "profit": report.profit, "market_share": report.market_share,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


# --- Leaderboard ---

@router.get("/leaderboard")
async def leaderboard(session: AsyncSession = Depends(get_session)):
    return await get_leaderboard(session)


# --- Fiche 10 ---

@router.get("/players/{player_id}/fiche")
async def get_fiche(player_id: str):
    from app.core.config import settings
    fiche_path = settings.PLAYERS_DIR / f"{player_id}.md"
    if not fiche_path.exists():
        raise HTTPException(404, "Fiche not found")
    return {"player_id": player_id, "content": fiche_path.read_text()}


# --- WebSocket for live updates ---

@router.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    await websocket.accept()
    try:
        while True:
            # Keep connection alive, push updates when events happen
            data = await websocket.receive_text()
            # Could handle real-time decision input here
            await websocket.send_json({"status": "connected", "player_id": player_id})
    except WebSocketDisconnect:
        pass
