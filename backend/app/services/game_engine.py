"""Core game engine — month progression, state updates, leaderboard."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.game import Player, Message, Decision, MonthlyReport, LeaderboardEntry
from app.core.llm import generate_month_events, resolve_decision, update_fiche
from app.core.config import settings
from pathlib import Path
import uuid


async def create_player(session: AsyncSession, name: str, company_name: str, 
                         industry: str = "automotive", style: str = "balanced",
                         risk_tolerance: str = "medium") -> Player:
    """Create a new player with a Fiche 10."""
    player_id = str(uuid.uuid4())[:8]
    
    player = Player(
        id=player_id,
        name=name,
        company_name=company_name,
        industry=industry,
        style=style,
        risk_tolerance=risk_tolerance,
        cash=settings.STARTING_CASH,
        current_month=0,
    )
    session.add(player)
    
    # Create initial Fiche 10
    fiche_content = f"""# Fiche 10 — {company_name}

## CEO Profile
- Name: {name}
- Style: {style}
- Risk tolerance: {risk_tolerance}

## Company
- Industry: {industry}
- Founded: Month 1
- Starting cash: ${settings.STARTING_CASH:,.0f}

## Track Record
- (No decisions yet)

## Key Metrics
- Revenue: $0
- Cash: ${settings.STARTING_CASH:,.0f}
- Market share: 5.0%

## LLM Notes
- Newly founded company, no track record yet
"""
    fiche_path = settings.PLAYERS_DIR / f"{player_id}.md"
    fiche_path.write_text(fiche_content)
    
    # Create leaderboard entry
    leaderboard = LeaderboardEntry(
        player_id=player_id,
        company_name=company_name,
        cash=settings.STARTING_CASH,
        revenue=0.0,
        market_share=5.0,
        current_month=0,
        rank=0,
    )
    session.add(leaderboard)
    
    await session.commit()
    await session.refresh(player)
    return player


async def start_month(session: AsyncSession, player_id: str) -> list[Message]:
    """Advance to the next month — generate inbox messages."""
    result = await session.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise ValueError(f"Player {player_id} not found")
    
    # Read Fiche 10
    fiche_path = settings.PLAYERS_DIR / f"{player_id}.md"
    fiche_content = fiche_path.read_text() if fiche_path.exists() else ""
    
    # Get recent decisions for context
    result = await session.execute(
        select(Decision)
        .where(Decision.player_id == player_id)
        .order_by(Decision.month.desc())
        .limit(3)
    )
    recent_decisions = [d.decision_text for d in result.scalars().all()]
    
    new_month = player.current_month + 1
    if new_month > settings.MAX_MONTHS:
        raise ValueError(f"Game over! Maximum {settings.MAX_MONTHS} months reached.")
    
    player.current_month = new_month
    
    # Generate events via LLM
    events = await generate_month_events(player_id, new_month, fiche_content, recent_decisions)
    
    messages = []
    for event in events:
        msg = Message(
            player_id=player_id,
            month=new_month,
            sender=event.get("sender", "System"),
            subject=event.get("subject", "Update"),
            body=event.get("body", ""),
            category=event.get("category", "info"),
            requires_action=event.get("requires_action", False),
        )
        session.add(msg)
        messages.append(msg)
    
    await session.commit()
    for msg in messages:
        await session.refresh(msg)
    
    return messages


async def submit_decision(session: AsyncSession, player_id: str, decision_text: str) -> dict:
    """Process a player's decision for the current month."""
    result = await session.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise ValueError(f"Player {player_id} not found")
    
    # Read Fiche 10
    fiche_path = settings.PLAYERS_DIR / f"{player_id}.md"
    fiche_content = fiche_path.read_text() if fiche_path.exists() else ""
    
    # Resolve decision via LLM
    outcome = await resolve_decision(
        player_id, player.current_month, decision_text, fiche_content, player.cash
    )
    
    # Apply impacts
    player.cash += outcome.get("cash_impact", 0)
    player.revenue += outcome.get("revenue_impact", 0)
    player.market_share += outcome.get("market_impact", 0)
    
    # Record decision
    decision = Decision(
        player_id=player_id,
        month=player.current_month,
        decision_text=decision_text,
        outcome=outcome.get("outcome", ""),
        cash_impact=outcome.get("cash_impact", 0),
        revenue_impact=outcome.get("revenue_impact", 0),
        market_impact=outcome.get("market_impact", 0),
    )
    session.add(decision)
    
    # Generate triggered events
    triggered_messages = []
    for event in outcome.get("new_events", []):
        msg = Message(
            player_id=player_id,
            month=player.current_month,
            sender=event.get("sender", "System"),
            subject=event.get("subject", "Update"),
            body=event.get("body", ""),
            category=event.get("category", "info"),
            requires_action=event.get("requires_action", False),
        )
        session.add(msg)
        triggered_messages.append(msg)
    
    # Update Fiche 10
    await update_fiche(player_id, player.current_month, fiche_content, decision_text, outcome.get("outcome", ""))
    
    # Update leaderboard
    await session.execute(
        update(LeaderboardEntry)
        .where(LeaderboardEntry.player_id == player_id)
        .values(
            cash=player.cash,
            revenue=player.revenue,
            market_share=player.market_share,
            current_month=player.current_month,
        )
    )
    
    await session.commit()
    
    return {
        "outcome": outcome.get("outcome", ""),
        "cash_impact": outcome.get("cash_impact", 0),
        "revenue_impact": outcome.get("revenue_impact", 0),
        "market_impact": outcome.get("market_impact", 0),
        "new_cash": player.cash,
        "new_revenue": player.revenue,
        "new_market_share": player.market_share,
        "triggered_events": len(triggered_messages),
    }


async def end_month(session: AsyncSession, player_id: str) -> MonthlyReport:
    """Calculate end-of-month report and advance."""
    result = await session.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise ValueError(f"Player {player_id} not found")
    
    # Calculate monthly financials
    month_decisions = await session.execute(
        select(Decision).where(
            Decision.player_id == player_id,
            Decision.month == player.current_month,
        )
    )
    decisions = month_decisions.scalars().all()
    
    total_cash_impact = sum(d.cash_impact for d in decisions)
    total_revenue_impact = sum(d.revenue_impact for d in decisions)
    
    # Base expenses (scaling with company size)
    base_expenses = 500_000 + (player.current_month * 50_000)
    
    report = MonthlyReport(
        player_id=player_id,
        month=player.current_month,
        cash=player.cash,
        revenue=player.revenue,
        expenses=base_expenses + abs(total_cash_impact) * 0.1,  # 10% overhead on decisions
        profit=player.revenue - base_expenses,
        market_share=player.market_share,
    )
    session.add(report)
    
    await session.commit()
    await session.refresh(report)
    return report


async def get_leaderboard(session: AsyncSession) -> list[dict]:
    """Get sorted leaderboard."""
    result = await session.execute(
        select(LeaderboardEntry)
        .order_by(LeaderboardEntry.cash.desc())
    )
    entries = result.scalars().all()
    
    leaderboard = []
    for rank, entry in enumerate(entries, 1):
        entry.rank = rank
        leaderboard.append({
            "rank": rank,
            "player_id": entry.player_id,
            "company_name": entry.company_name,
            "cash": entry.cash,
            "revenue": entry.revenue,
            "market_share": entry.market_share,
            "current_month": entry.current_month,
        })
    
    await session.commit()
    return leaderboard
