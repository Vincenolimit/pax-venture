import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event


async def append_event(session: AsyncSession, player_id: str, kind: str, source: str, payload: dict, *, month: int, idempotency_key: str | None = None, parent_event_id: int | None = None, prompt_version: int = 1, schema_version: int = 1, model: str | None = None, seed: int | None = None) -> Event:
    max_seq = await session.scalar(select(func.coalesce(func.max(Event.seq_in_month), 0)).where(Event.player_id == player_id, Event.month == month))
    event = Event(player_id=player_id, month=month, seq_in_month=(max_seq or 0) + 1, kind=kind, source=source, payload_json=json.dumps(payload), idempotency_key=idempotency_key, parent_event_id=parent_event_id, prompt_version=prompt_version, schema_version=schema_version, model=model, seed=seed)
    session.add(event)
    await session.flush()
    return event


async def find_by_idem(session: AsyncSession, player_id: str, key: str):
    return await session.scalar(select(Event).where(Event.player_id == player_id, Event.idempotency_key == key).order_by(Event.id.desc()))
