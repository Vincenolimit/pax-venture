import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Competitor, Flag, WorldEvent
from app.services.events import append_event


async def pending_for_month(session: AsyncSession, industry_id: str, month: int):
    return (await session.scalars(select(WorldEvent).where(WorldEvent.industry_id == industry_id, WorldEvent.fire_at_month == month))).all()


async def active_for_month(session: AsyncSession, industry_id: str, month: int):
    return (
        await session.scalars(
            select(WorldEvent).where(
                WorldEvent.industry_id == industry_id,
                WorldEvent.fire_at_month <= month,
                month < (WorldEvent.fire_at_month + WorldEvent.duration_months),
            )
        )
    ).all()


async def apply_mechanical_effects(session: AsyncSession, player, month: int, world_events: list[WorldEvent]):
    flags = {f.flag_name: (str(f.flag_value).lower() == "true") for f in (await session.scalars(select(Flag).where(Flag.player_id == player.id))).all()}
    comps = (await session.scalars(select(Competitor).where(Competitor.player_id == player.id))).all()
    for we in world_events:
        effects = json.loads(we.mechanical_effects)
        if "requires_flag" in effects and not flags.get(effects["requires_flag"], False):
            effects = {**effects, **effects.get("if_missing_flag_penalty", {})}

        global_effects = effects.get("global", effects)
        if "revenue_multiplier" in global_effects:
            player.revenue *= global_effects["revenue_multiplier"]
        if "cash_delta_per_month" in global_effects:
            player.cash += global_effects["cash_delta_per_month"]
        if "market_share_drift" in global_effects:
            player.market_share += global_effects["market_share_drift"]

        comp_effects = effects.get("competitors", {})
        if "all" in comp_effects:
            for c in comps:
                if "revenue_multiplier" in comp_effects["all"]:
                    c.revenue *= comp_effects["all"]["revenue_multiplier"]
        by_template = comp_effects.get("by_template", {})
        for c in comps:
            if c.template_id in by_template and "base_growth_delta" in by_template[c.template_id]:
                c.base_growth += by_template[c.template_id]["base_growth_delta"]

        await append_event(session, player.id, "WORLD_EVENT_FIRED", "world", {"event_id": we.id, "cash_delta_per_month": global_effects.get("cash_delta_per_month", 0), "market_share_drift": global_effects.get("market_share_drift", 0), "revenue_multiplier": global_effects.get("revenue_multiplier")}, month=month)
