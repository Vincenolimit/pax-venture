import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import build_cached_system_block, build_dynamic_block
from app.core.config import PROMPT_VERSION, QWEN_MODEL, SCHEMA_VERSION
from app.core.openrouter import call_tool
from app.core.seed import derive_seed
from app.core.tools import RESOLVE_TOOL
from app.core.validators import validate_resolve_decision
from app.models import Competitor, Decision, DecisionEmbedding, Event, Flag, Industry, Memory, Message, Player, Relationship, Thread, WorldEvent
from app.services.competitors import apply_posture_transitions
from app.services.embeddings import embed, retrieve
from app.services.events import append_event, find_by_idem
from app.services.projection import build_state, rebuild_player_columns


def month_in_play(player: Player) -> int:
    return player.current_month + 1


def action_from_event(event: Event) -> dict:
    payload = json.loads(event.payload_json)
    return {
        "id": event.id,
        "month": event.month,
        "text": payload.get("text", ""),
        "inbox_ref_ids": payload.get("inbox_ref_ids", []),
        "created_at": str(event.ts) if event.ts else None,
    }


async def action_events(session: AsyncSession, player: Player, month: int | None = None) -> list[Event]:
    target_month = month if month is not None else month_in_play(player)
    return (
        await session.scalars(
            select(Event)
            .where(Event.player_id == player.id, Event.month == target_month, Event.kind == "ACTION_SUBMITTED")
            .order_by(Event.seq_in_month.asc(), Event.id.asc())
        )
    ).all()


async def queue_action(session: AsyncSession, player: Player, body: dict, idempotency_key: str) -> tuple[Event, bool]:
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Action text is required")
    if len(text) > 1200:
        raise HTTPException(status_code=400, detail="Action text is too long")
    inbox_ref_ids = [int(v) for v in body.get("inbox_ref_ids", []) if str(v).isdigit()]

    idem = await find_by_idem(session, player.id, idempotency_key)
    if idem:
        if idem.kind != "ACTION_SUBMITTED":
            raise HTTPException(status_code=409, detail="Idempotency key already used for another operation")
        return idem, True

    event = await append_event(
        session,
        player.id,
        "ACTION_SUBMITTED",
        "player",
        {"text": text, "inbox_ref_ids": inbox_ref_ids},
        month=month_in_play(player),
        idempotency_key=idempotency_key,
    )
    return event, False


async def _apply_resolution_side_effects(session: AsyncSession, player: Player, month: int, cleaned: dict) -> None:
    for name, value in cleaned.get("flag_updates", {}).items():
        flag = await session.get(Flag, (player.id, name))
        if flag:
            flag.flag_value = bool(value)
        else:
            session.add(Flag(player_id=player.id, flag_name=name, flag_value=bool(value)))

    for key, value in cleaned.get("relationship_updates", {}).items():
        rel = await session.get(Relationship, (player.id, key))
        if rel:
            rel.value = value

    active_threads = (await session.scalars(select(Thread).where(Thread.player_id == player.id, Thread.status == "active"))).all()
    active_by_label = {t.label.lower(): t for t in active_threads}
    for thread in cleaned.get("new_threads", []):
        label = thread["label"]
        if label.lower() not in active_by_label:
            session.add(
                Thread(
                    player_id=player.id,
                    label=label,
                    importance=thread["importance"],
                    status="active",
                    opened_at_month=month,
                    last_referenced_month=month,
                )
            )
    for label in cleaned.get("closed_threads", []):
        thread = active_by_label.get(label.lower())
        if thread:
            thread.status = "resolved"
            thread.closed_at_month = month
            thread.last_referenced_month = month

    flags = {f.flag_name: bool(f.flag_value) for f in (await session.scalars(select(Flag).where(Flag.player_id == player.id))).all()}
    competitors = (await session.scalars(select(Competitor).where(Competitor.player_id == player.id))).all()
    for comp in competitors:
        await apply_posture_transitions(session, comp, player, month, flags)


async def resolve_month_actions(
    session: AsyncSession,
    player: Player,
    industry: Industry,
    memory: Memory,
    month: int,
    actions: list[Event],
    worlds: list[WorldEvent],
) -> dict | None:
    if not actions:
        return None

    action_lines = []
    action_texts = []
    for index, event in enumerate(actions, start=1):
        payload = json.loads(event.payload_json)
        text = payload.get("text", "").strip()
        action_texts.append(text)
        action_lines.append(f"{index}. {text}")

    action_plan = "\n".join(action_lines)
    inbox = (await session.scalars(select(Message).where(Message.player_id == player.id, Message.month == month))).all()
    state = await build_state(session, player.id)
    retrieved = await retrieve(session, player.id, action_plan)
    active_threads = (await session.scalars(select(Thread).where(Thread.player_id == player.id, Thread.status == "active"))).all()
    dynamic = build_dynamic_block(
        state,
        memory.recent,
        [f"{t.label} ({t.importance:.2f})" for t in active_threads],
        [f"M{r['decision_id']} {r['decision_text'][:90]}" for r in retrieved],
        [f"[{m.id}] {m.subject}: {m.body}" for m in inbox],
        (
            "Call the resolve_decision tool now.\n"
            "Resolve this as one monthly CEO turn. Use the combined action plan, previous decisions, "
            "current world events, competitor posture, relationships, and inbox pressure.\n\n"
            f"MONTHLY ACTION PLAN:\n{action_plan}"
        ),
    )
    result = await call_tool(
        "resolve_decision",
        QWEN_MODEL,
        [{"role": "system", "content": build_cached_system_block(industry, memory, worlds)}, {"role": "user", "content": dynamic}],
        RESOLVE_TOOL,
        cache_control_on_system=True,
        seed=derive_seed(player.id, month, len(actions)),
        session=session,
        player_id=player.id,
    )
    cleaned, _ = validate_resolve_decision(industry, result.args, [t.label for t in active_threads])
    await _apply_resolution_side_effects(session, player, month, cleaned)
    decision = Decision(
        player_id=player.id,
        month=month,
        seq_in_month=1,
        decision_text=action_plan,
        inbox_ref_ids=json.dumps([ref for event in actions for ref in json.loads(event.payload_json).get("inbox_ref_ids", [])]),
        narrative=cleaned["narrative"],
        importance=cleaned["importance"],
        cash_impact=cleaned["cash_impact"],
        revenue_impact=cleaned["revenue_impact"],
        market_impact=cleaned["market_impact"],
        employees_change=cleaned["employees_change"],
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        model=QWEN_MODEL,
        seed=derive_seed(player.id, month, len(actions)),
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        cache_hit=(result.cached_tokens > 0),
    )
    session.add(decision)
    await session.flush()
    session.add(DecisionEmbedding(decision_id=decision.id, player_id=player.id, model="voyage-3-lite", dim=512, vector=(await embed(session, action_plan))))
    await append_event(session, player.id, "DECISION_RESOLVED", "llm", {**cleaned, "actions": action_texts}, month=month, model=QWEN_MODEL, seed=derive_seed(player.id, month, len(actions)))
    player.cost_spent_usd += result.cost_usd
    await rebuild_player_columns(session, player.id)
    return {**cleaned, "actions": action_texts, "cost_usd": result.cost_usd}
