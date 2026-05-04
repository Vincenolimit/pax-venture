import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.cache import build_cached_system_block, build_dynamic_block
from app.core.config import COMPETITOR_TEMPLATES, PROMPT_VERSION, QWEN_MODEL, SCHEMA_VERSION
from app.core.database import get_session
from app.core.openrouter import call_tool
from app.core.seed import derive_seed
from app.core.tools import INBOX_TOOL, RESOLVE_TOOL
from app.core.validators import validate_generate_inbox_emails, validate_resolve_decision
from app.models.llm_call import LLMCall
from app.models import Competitor, Decision, DecisionEmbedding, Event, Flag, Industry, Memory, Message, Player, Relationship, Snapshot, Thread
from app.services.autopsy import generate_autopsy, latest_autopsy
from app.services.competitors import apply_posture_transitions, end_month_competitor_tick, seeded_rng
from app.services.cost import within_cost_cap
from app.services.embeddings import embed, retrieve
from app.services.events import append_event, find_by_idem
from app.services.memory import compact_memory
from app.services.projection import build_state, rebuild_player_columns
from app.services.world import apply_mechanical_effects, pending_for_month

router = APIRouter(prefix="/api/v1")


def _resolve_model(industry: Industry, tier: str) -> str:
    _ = industry
    _ = tier
    return QWEN_MODEL


def _sse_error_payload(code: str, message: str, retryable: bool, idempotency_key: str) -> dict:
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "idempotency_key": idempotency_key,
    }


@router.post("/players")
async def create_player(body: dict, session: AsyncSession = Depends(get_session), idempotency_key: str = Header(..., alias="Idempotency-Key")):
    industry = await session.get(Industry, body["industry_id"])
    if not industry or not industry.enabled:
        raise HTTPException(status_code=404, detail="Industry unavailable")
    pid = uuid.uuid4().hex[:16]
    start = json.loads(industry.starting_state_json)
    session.add(
        Player(
            id=pid,
            industry_id=industry.id,
            name=body["name"],
            company_name=body["company_name"],
            style=body.get("style", "balanced"),
            risk_tolerance=body.get("risk_tolerance", "medium"),
            model_tier=body.get("model_tier", "balanced"),
            cash=start["cash"],
            revenue=start["revenue"],
            market_share=start["market_share"],
            employees=start["employees"],
            cost_cap_usd=body.get("cost_cap_usd"),
        )
    )
    session.add(Memory(player_id=pid, recent="", period_summary="", origin_story="", period_start=0, period_end=0))
    rel_vocab = json.loads(industry.relationship_vocab)
    for key in json.loads(industry.relationship_keys):
        session.add(Relationship(player_id=pid, key=key, value=rel_vocab[key][min(1, len(rel_vocab[key]) - 1)]))
    for tpl in COMPETITOR_TEMPLATES:
        session.add(Competitor(id=f"p{pid}:{tpl['template_id']}", player_id=pid, industry_id=industry.id, template_id=tpl["template_id"], name=tpl["name"], cash=tpl["cash"], revenue=tpl["revenue"], market_share=tpl["market_share"], expenses=tpl["expenses"], base_growth=tpl["base_growth"], volatility=tpl["volatility"], posture="OBSERVING"))
    await append_event(session, pid, "MONTH_STARTED", "kernel", {"month": 0}, month=0, idempotency_key=idempotency_key)
    await session.commit()
    return await build_state(session, pid)


@router.post("/players/{player_id}/start-month")
async def start_month(player_id: str, session: AsyncSession = Depends(get_session), idempotency_key: str = Header(..., alias="Idempotency-Key")):
    async def stream():
        try:
            player = await session.get(Player, player_id)
            if not player:
                raise HTTPException(status_code=404, detail="Player not found")
            month = player.current_month + 1
            if await find_by_idem(session, player_id, idempotency_key):
                yield {"event": "done", "data": json.dumps({"replayed": True})}
                return
            industry = await session.get(Industry, player.industry_id)
            memory = await session.get(Memory, player.id)
            worlds = await pending_for_month(session, player.industry_id, month)
            state = await build_state(session, player.id)
            system = build_cached_system_block(industry, memory, worlds)
            dynamic = build_dynamic_block(state, memory.recent, [], [], [], "Call the generate_inbox_emails tool now.")
            model = _resolve_model(industry, player.model_tier)
            result = await call_tool("generate_inbox_emails", model, [{"role": "system", "content": system}, {"role": "user", "content": dynamic}], INBOX_TOOL, cache_control_on_system=True, seed=derive_seed(player.id, month, 1), session=session, player_id=player.id)
            cleaned, _ = validate_generate_inbox_emails(industry, result.args)
            for em in cleaned["emails"]:
                msg = Message(player_id=player.id, month=month, sender=em["sender"], subject=em["subject"], body=em["body"], category=em["category"], requires_action=em["requires_action"], prompt_version=PROMPT_VERSION)
                session.add(msg)
                await session.flush()
                yield {"event": "email", "data": json.dumps({"id": msg.id, "sender": msg.sender, "subject": msg.subject, "body": msg.body, "category": msg.category})}
            await append_event(session, player.id, "EMAILS_GENERATED", "llm", {"count": len(cleaned["emails"])}, month=month)
            await append_event(session, player.id, "MONTH_STARTED", "kernel", {"month": month}, month=month, idempotency_key=idempotency_key)
            await session.commit()
            yield {"event": "done", "data": json.dumps({"month": month, "emails": cleaned["emails"], "cost_usd": result.cost_usd})}
        except HTTPException as exc:
            yield {"event": "error", "data": json.dumps(_sse_error_payload("INTERNAL_ERROR", str(exc.detail), False, idempotency_key))}
        except Exception as exc:
            yield {"event": "error", "data": json.dumps(_sse_error_payload("INTERNAL_ERROR", f"Unexpected streaming failure: {str(exc)[:220]}", True, idempotency_key))}

    return EventSourceResponse(stream())


@router.post("/players/{player_id}/decide")
async def decide(player_id: str, body: dict, session: AsyncSession = Depends(get_session), idempotency_key: str = Header(..., alias="Idempotency-Key")):
    async def stream():
        try:
            player = await session.get(Player, player_id)
            if not player:
                raise HTTPException(status_code=404, detail="Player not found")
            month = player.current_month + 1
            if player.game_over:
                raise HTTPException(status_code=409, detail="Game is over")
            if not within_cost_cap(player, 0.10):
                raise HTTPException(status_code=402, detail="Cost cap reached")
            if await find_by_idem(session, player_id, idempotency_key):
                yield {"event": "result", "data": json.dumps({"replayed": True})}
                return
            industry = await session.get(Industry, player.industry_id)
            memory = await session.get(Memory, player.id)
            inbox = (await session.scalars(select(Message).where(Message.player_id == player.id, Message.month == month))).all()
            state = await build_state(session, player.id)
            retrieved = await retrieve(session, player.id, body["text"])
            dynamic = build_dynamic_block(state, memory.recent, [], [f"M{r['decision_id']} {r['decision_text'][:60]}" for r in retrieved], [f"[{m.id}] {m.subject}" for m in inbox], f"Call the resolve_decision tool now.\n{body['text']}")
            model = _resolve_model(industry, player.model_tier)
            result = await call_tool("resolve_decision", model, [{"role": "system", "content": [{"type": "text", "text": industry.system_prompt_template}]}, {"role": "user", "content": dynamic}], RESOLVE_TOOL, cache_control_on_system=True, seed=derive_seed(player.id, month, 1), session=session, player_id=player.id)
            active_threads = (await session.scalars(select(Thread).where(Thread.player_id == player.id, Thread.status == "active"))).all()
            cleaned, _ = validate_resolve_decision(industry, result.args, [t.label for t in active_threads])
            for token in cleaned["narrative"].split(" "):
                yield {"event": "narrative.chunk", "data": json.dumps({"text": token + " "})}
            decision = Decision(player_id=player.id, month=month, seq_in_month=1, decision_text=body["text"], inbox_ref_ids=json.dumps(body.get("inbox_ref_ids", [])), narrative=cleaned["narrative"], importance=cleaned["importance"], cash_impact=cleaned["cash_impact"], revenue_impact=cleaned["revenue_impact"], market_impact=cleaned["market_impact"], employees_change=cleaned["employees_change"], prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION, model=model, seed=derive_seed(player.id, month, 1), cost_usd=result.cost_usd, latency_ms=result.latency_ms, cache_hit=(result.cached_tokens > 0))
            session.add(decision)
            await session.flush()
            session.add(DecisionEmbedding(decision_id=decision.id, player_id=player.id, model="voyage-3-lite", dim=512, vector=(await embed(session, body["text"]))))
            await append_event(session, player.id, "DECISION_PROPOSED", "player", {"text": body["text"]}, month=month)
            await append_event(session, player.id, "DECISION_RESOLVED", "llm", cleaned, month=month, idempotency_key=idempotency_key, model=model, seed=derive_seed(player.id, month, 1))
            await rebuild_player_columns(session, player.id)
            player.cost_spent_usd += result.cost_usd
            await session.commit()
            yield {"event": "result", "data": json.dumps({**cleaned, "updated_state": await build_state(session, player.id), "cost_usd": result.cost_usd})}
        except HTTPException as exc:
            yield {"event": "error", "data": json.dumps(_sse_error_payload("INTERNAL_ERROR", str(exc.detail), False, idempotency_key))}
        except Exception as exc:
            yield {"event": "error", "data": json.dumps(_sse_error_payload("INTERNAL_ERROR", f"Unexpected streaming failure: {str(exc)[:220]}", True, idempotency_key))}

    return EventSourceResponse(stream())


@router.post("/players/{player_id}/end-month")
async def end_month(player_id: str, session: AsyncSession = Depends(get_session), idempotency_key: str = Header(..., alias="Idempotency-Key")):
    player = await session.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    idem = await find_by_idem(session, player_id, idempotency_key)
    if idem:
        payload = json.loads(idem.payload_json)
        return payload.get("result", {"replayed": True})
    if player.game_over:
        raise HTTPException(status_code=409, detail="Game is over")
    month = player.current_month + 1
    industry = await session.get(Industry, player.industry_id)
    worlds = await pending_for_month(session, player.industry_id, month)
    await apply_mechanical_effects(session, player, month, worlds)
    fin = json.loads(industry.financial_constants)
    burn = player.employees * fin["payroll_per_employee"] + fin["base_overhead"]
    await append_event(session, player.id, "FINANCES_APPLIED", "kernel", {"burn": burn, "revenue": player.revenue}, month=month)
    for comp in (await session.scalars(select(Competitor).where(Competitor.player_id == player.id))).all():
        end_month_competitor_tick(comp, player, month, seeded_rng(player, comp))
    await compact_memory(session, player, industry)
    await rebuild_player_columns(session, player.id)
    rank = int((await session.scalar(select(func.count()).select_from(Player).where(Player.cash > player.cash))) or 0) + 1
    session.add(Snapshot(player_id=player.id, month=month, cash=player.cash, revenue=player.revenue, market_share=player.market_share, employees=player.employees, burn_rate=burn, leaderboard_rank=rank))
    player.current_month += 1
    if player.cash < 0:
        player.game_over = True
        player.eliminated_at = player.current_month
        autopsy = await generate_autopsy(session, player)
        await append_event(session, player.id, "AUTOPSY_GENERATED", "llm", autopsy, month=month)
    result = {"month": player.current_month, "cash": player.cash, "revenue": player.revenue, "market_share": player.market_share, "burn_rate": burn, "employees": player.employees, "game_over": bool(player.game_over), "world_events_fired": [{"event_id": w.id, "severity": w.severity} for w in worlds], "memory_compacted": True}
    await append_event(session, player.id, "MONTH_ENDED", "kernel", {"month": player.current_month, "result": result}, month=month, idempotency_key=idempotency_key)
    await session.commit()
    return result


@router.patch("/players/{player_id}")
async def patch_player(player_id: str, body: dict, session: AsyncSession = Depends(get_session)):
    player = await session.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    if player.game_over:
        raise HTTPException(status_code=409, detail="Game is over")
    if "model_tier" in body:
        if body["model_tier"] not in {"cheap", "balanced", "premium"}:
            raise HTTPException(status_code=400, detail="Invalid model tier")
        player.model_tier = body["model_tier"]
    if "cost_cap_usd" in body:
        if body["cost_cap_usd"] is not None and body["cost_cap_usd"] < 0:
            raise HTTPException(status_code=400, detail="Invalid cost cap")
        player.cost_cap_usd = body["cost_cap_usd"]
    await session.commit()
    return {"id": player.id, "model_tier": player.model_tier, "cost_cap_usd": player.cost_cap_usd}


@router.get("/players/{player_id}/state")
async def get_player_state(player_id: str, session: AsyncSession = Depends(get_session)):
    player = await session.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await build_state(session, player_id)


@router.get("/players/{player_id}/messages")
async def get_messages(player_id: str, month: int | None = Query(default=None), session: AsyncSession = Depends(get_session)):
    player = await session.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    target_month = month if month is not None else player.current_month + 1
    rows = (
        await session.scalars(
            select(Message)
            .where(Message.player_id == player.id, Message.month == target_month)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
    ).all()
    return {
        "player_id": player.id,
        "month": target_month,
        "messages": [
            {
                "id": row.id,
                "sender": row.sender,
                "subject": row.subject,
                "body": row.body,
                "category": row.category,
                "is_read": bool(row.is_read),
                "requires_action": bool(row.requires_action),
            }
            for row in rows
        ],
    }


@router.patch("/players/{player_id}/messages/{message_id}")
async def patch_message(player_id: str, message_id: int, body: dict, session: AsyncSession = Depends(get_session)):
    player = await session.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    message = await session.get(Message, message_id)
    if not message or message.player_id != player.id:
        raise HTTPException(status_code=404, detail="Message not found")
    if "is_read" in body:
        message.is_read = bool(body["is_read"])
    await session.commit()
    return {
        "id": message.id,
        "is_read": bool(message.is_read),
    }


@router.get("/leaderboard")
async def leaderboard(session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(Player.id, Player.company_name, Player.cash, Player.revenue, Player.market_share)
            .order_by(Player.cash.desc(), Player.revenue.desc(), Player.market_share.desc())
        )
    ).all()
    return {
        "rows": [
            {
                "rank": i + 1,
                "player_id": row.id,
                "company_name": row.company_name,
                "cash": row.cash,
                "revenue": row.revenue,
                "market_share": row.market_share,
            }
            for i, row in enumerate(rows)
        ]
    }


@router.get("/players/{player_id}/cost")
async def get_cost(player_id: str, session: AsyncSession = Depends(get_session)):
    player = await session.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    pct = None
    if player.cost_cap_usd:
        pct = min(100.0, (player.cost_spent_usd / player.cost_cap_usd) * 100.0) if player.cost_cap_usd > 0 else 100.0
    return {"player_id": player.id, "cost_spent_usd": player.cost_spent_usd, "cost_cap_usd": player.cost_cap_usd, "cap_percent": pct}


@router.get("/players/{player_id}/autopsy")
async def get_autopsy(player_id: str, session: AsyncSession = Depends(get_session)):
    player = await session.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    autopsy = await latest_autopsy(session, player_id)
    if autopsy:
        return autopsy
    autopsy = await generate_autopsy(session, player)
    await append_event(session, player.id, "AUTOPSY_GENERATED", "llm", autopsy, month=player.current_month)
    await session.commit()
    return autopsy


@router.get("/admin/health")
async def admin_health(session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(func.avg(LLMCall.cache_hit_ratio), func.count(LLMCall.id)).where(LLMCall.call_type != "embedding")
        )
    ).one()
    ratio = float(rows[0] or 0.0)
    count = int(rows[1] or 0)
    return {"cache_hit_ratio_mean": ratio, "sample_size": count, "cache_healthy": ratio >= 0.70 if count else True}
