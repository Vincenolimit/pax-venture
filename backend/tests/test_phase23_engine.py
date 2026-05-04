import json
import uuid

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal, init_db
from app.models import Event, Industry, Player
from app.services.events import append_event
from app.services.projection import rebuild_player_columns


@pytest.mark.asyncio
async def test_money_flow_a1_regression():
    await init_db()
    async with SessionLocal() as session:
        industry = await session.get(Industry, "automotive")
        start = json.loads(industry.starting_state_json)
        pid = uuid.uuid4().hex[:16]
        p = Player(id=pid, industry_id="automotive", name="n", company_name="c", style="s", risk_tolerance="r", cash=start["cash"], revenue=start["revenue"], market_share=start["market_share"], employees=start["employees"])
        session.add(p)
        await session.flush()

        await append_event(session, pid, "DECISION_RESOLVED", "llm", {"cash_impact": 0, "revenue_impact": 1000000, "market_impact": 0, "employees_change": 0}, month=1)
        await append_event(session, pid, "FINANCES_APPLIED", "kernel", {"burn": 2700000, "revenue": 1000000}, month=1)
        await append_event(session, pid, "FINANCES_APPLIED", "kernel", {"burn": 2700000, "revenue": 1000000}, month=2)
        await rebuild_player_columns(session, pid)
        await session.commit()

        got = await session.get(Player, pid)
        assert got.cash == start["cash"] + 0 + (1000000 - 2700000) + (1000000 - 2700000)


@pytest.mark.asyncio
async def test_event_idempotency_key_unique():
    await init_db()
    async with SessionLocal() as session:
        industry = await session.get(Industry, "automotive")
        start = json.loads(industry.starting_state_json)
        pid = uuid.uuid4().hex[:16]
        session.add(Player(id=pid, industry_id="automotive", name="n", company_name="c", style="s", risk_tolerance="r", cash=start["cash"], revenue=start["revenue"], market_share=start["market_share"], employees=start["employees"]))
        await session.flush()
        await append_event(session, pid, "MONTH_STARTED", "kernel", {}, month=1, idempotency_key="k1")
        await session.commit()
        with pytest.raises(Exception):
            await append_event(session, pid, "MONTH_STARTED", "kernel", {}, month=1, idempotency_key="k1")
            await session.commit()
