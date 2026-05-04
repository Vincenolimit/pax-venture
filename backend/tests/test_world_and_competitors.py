import json
import uuid

import pytest
from sqlalchemy import select

from app.models import Competitor, Flag, Industry, Player, WorldEvent
from app.services.competitors import apply_posture_transitions, end_month_competitor_tick, seeded_rng
from app.services.world import active_for_month, apply_mechanical_effects, pending_for_month


@pytest.mark.asyncio
async def test_world_event_pending_and_active(session):
    pid = await _make_player(session)
    p = await session.get(Player, pid)
    pending = await pending_for_month(session, p.industry_id, 3)
    active = await active_for_month(session, p.industry_id, 4)
    assert any(w.id == "chip_shortage_2026" for w in pending)
    assert any(w.id == "chip_shortage_2026" for w in active)
    expired = await active_for_month(session, p.industry_id, 6)
    assert all(w.id != "chip_shortage_2026" for w in expired)


@pytest.mark.asyncio
async def test_world_event_requires_flag_penalty(session):
    pid = await _make_player(session)
    p = await session.get(Player, pid)
    p.current_month = 6
    world = await session.get(WorldEvent, "eu_emissions_2026")
    cash_before = p.cash
    await apply_mechanical_effects(session, p, 6, [world])
    assert p.cash < cash_before


@pytest.mark.asyncio
async def test_competitor_transition_and_tick(session):
    pid = await _make_player(session)
    player = await session.get(Player, pid)
    comp = (await session.scalars(select(Competitor).where(Competitor.player_id == pid, Competitor.template_id == "novatech"))).one()
    session.add(Flag(player_id=pid, flag_name="ev_platform_launched", flag_value=True))
    await session.flush()
    changed = await apply_posture_transitions(session, comp, player, 3, {"ev_platform_launched": True})
    assert changed
    assert comp.posture == "AGGRESSIVE"
    cash_before = comp.cash
    end_month_competitor_tick(comp, player, 3, seeded_rng(player, comp))
    assert comp.cash != cash_before


async def _make_player(session):
    from app.core.config import COMPETITOR_TEMPLATES

    industry = await session.get(Industry, "automotive")
    start = json.loads(industry.starting_state_json)
    pid = uuid.uuid4().hex[:16]
    session.add(Player(id=pid, industry_id="automotive", name="t", company_name="co", style="s", risk_tolerance="r", cash=start["cash"], revenue=start["revenue"], market_share=start["market_share"], employees=start["employees"]))
    for tpl in COMPETITOR_TEMPLATES:
        session.add(Competitor(id=f"p{pid}:{tpl['template_id']}", player_id=pid, industry_id="automotive", template_id=tpl["template_id"], name=tpl["name"], cash=tpl["cash"], revenue=tpl["revenue"], market_share=tpl["market_share"], expenses=tpl["expenses"], base_growth=tpl["base_growth"], volatility=tpl["volatility"], posture="OBSERVING"))
    await session.commit()
    return pid
