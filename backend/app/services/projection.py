import json
from statistics import mean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Competitor, Event, Flag, Industry, Memory, Player, Relationship, Snapshot, WorldEvent


def _runway_bucket(cash: float, burn: float) -> str:
    if burn <= 0:
        return "comfortable"
    r = cash / burn
    if r >= 4:
        return "comfortable"
    if r >= 2:
        return "healthy"
    if r >= 1:
        return "tight"
    return "critical"


async def build_state(session: AsyncSession, player_id: str) -> dict:
    p = await session.get(Player, player_id)
    mem = await session.get(Memory, player_id)
    snaps = (await session.scalars(select(Snapshot).where(Snapshot.player_id == player_id).order_by(Snapshot.month.desc()).limit(3))).all()
    comps = (await session.scalars(select(Competitor).where(Competitor.player_id == player_id).order_by(Competitor.market_share.desc()).limit(3))).all()
    flags = (await session.scalars(select(Flag).where(Flag.player_id == player_id))).all()
    rels = (await session.scalars(select(Relationship).where(Relationship.player_id == player_id))).all()
    worlds = (await session.scalars(select(WorldEvent).where(WorldEvent.industry_id == p.industry_id, WorldEvent.fire_at_month <= p.current_month))).all()

    industry = await session.get(Industry, p.industry_id)
    financial = json.loads(industry.financial_constants)
    burn = p.employees * financial["payroll_per_employee"] + financial["base_overhead"]
    trend = "stable"
    if len(snaps) >= 3:
        m = mean([s.revenue for s in snaps])
        if m > 0 and p.revenue > m * 1.1:
            trend = "up"
        elif m > 0 and p.revenue < m * 0.9:
            trend = "down"
    comp_briefs = []
    for c in comps:
        band = "low" if c.revenue < 1_000_000 else ("mid" if c.revenue <= 3_000_000 else "high")
        verb = "presses" if c.posture == "AGGRESSIVE" else "holds"
        comp_briefs.append({"name": c.name, "market_share": c.market_share, "revenue_band": band, "posture": c.posture, "headline": f"{c.name} {verb} this quarter"})

    return {
        "player": {
            "id": p.id,
            "name": p.name,
            "company_name": p.company_name,
            "current_month": p.current_month,
            "cash": p.cash,
            "revenue": p.revenue,
            "market_share": p.market_share,
            "employees": p.employees,
            "model_tier": p.model_tier,
            "cost_cap_usd": p.cost_cap_usd,
            "cost_spent_usd": p.cost_spent_usd,
            "game_over": bool(p.game_over),
            "eliminated_at": p.eliminated_at,
        },
        "derived": {"burn_rate": burn, "cash_runway": _runway_bucket(p.cash, burn), "revenue_trend": trend},
        "memory": {"recent": mem.recent if mem else "", "period_summary": mem.period_summary if mem else "", "origin_story": mem.origin_story if mem else ""},
        "relationships": {r.key: r.value for r in rels},
        "flags": {f.flag_name: (str(f.flag_value).lower() == "true") for f in flags},
        "competitor_briefs": comp_briefs,
        "active_world_events": [{"id": w.id, "severity": w.severity, "narrative_seed": w.narrative_seed} for w in worlds if w.fire_at_month <= p.current_month < w.fire_at_month + w.duration_months],
    }


async def rebuild_player_columns(session: AsyncSession, player_id: str):
    p = await session.get(Player, player_id)
    industry = await session.get(Industry, p.industry_id)
    base = json.loads(industry.starting_state_json)
    cash, revenue, market, employees = base["cash"], base["revenue"], base["market_share"], base["employees"]
    events = (await session.scalars(select(Event).where(Event.player_id == player_id).order_by(Event.month.asc(), Event.seq_in_month.asc()))).all()
    for e in events:
        payload = json.loads(e.payload_json)
        if e.kind == "DECISION_RESOLVED":
            cash += payload.get("cash_impact", 0)
            revenue += payload.get("revenue_impact", 0)
            market += payload.get("market_impact", 0)
            employees += payload.get("employees_change", 0)
        elif e.kind == "FINANCES_APPLIED":
            cash += payload.get("revenue", 0) - payload.get("burn", 0)
        elif e.kind == "WORLD_EVENT_FIRED":
            cash += payload.get("cash_delta_per_month", 0)
            market += payload.get("market_share_drift", 0)
            if payload.get("revenue_multiplier"):
                revenue *= payload["revenue_multiplier"]
    p.cash, p.revenue, p.market_share, p.employees = cash, revenue, market, employees
    await session.flush()
