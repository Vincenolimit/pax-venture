import asyncio

import pytest
from sqlalchemy import select

from app.core.database import init_db, SessionLocal
from app.models import Industry, WorldEvent


@pytest.mark.asyncio
async def test_init_db_seeds_industry_and_world_events():
    await init_db()
    async with SessionLocal() as session:
        industries = (await session.scalars(select(Industry))).all()
        worlds = (await session.scalars(select(WorldEvent))).all()
    assert len(industries) == 1
    assert len(worlds) == 8
