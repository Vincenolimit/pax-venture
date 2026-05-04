import json

from sqlalchemy import select

from app.core.config import QWEN_MODEL
from app.core.openrouter import call_tool
from app.core.tools import AUTOPSY_TOOL
from app.models import Decision, Event, Snapshot


async def generate_autopsy(session, player):
    snapshots = (await session.scalars(select(Snapshot).where(Snapshot.player_id == player.id).order_by(Snapshot.month.asc()))).all()
    decisions = (
        await session.scalars(
            select(Decision)
            .where(Decision.player_id == player.id)
            .order_by(Decision.importance.desc())
            .limit(10)
        )
    ).all()
    payload = {
        "final_state": {
            "month": player.current_month,
            "cash": player.cash,
            "revenue": player.revenue,
            "market_share": player.market_share,
            "employees": player.employees,
            "game_over": bool(player.game_over),
        },
        "snapshots": [
            {
                "month": s.month,
                "cash": s.cash,
                "revenue": s.revenue,
                "market_share": s.market_share,
                "employees": s.employees,
                "burn_rate": s.burn_rate,
                "leaderboard_rank": s.leaderboard_rank,
            }
            for s in snapshots
        ],
        "decisions": [
            {"month": d.month, "text": d.decision_text, "narrative": d.narrative, "importance": d.importance}
            for d in decisions
        ],
    }
    result = await call_tool(
        "autopsy_summary",
        QWEN_MODEL,
        [{"role": "user", "content": json.dumps(payload)}],
        AUTOPSY_TOOL,
        cache_control_on_system=False,
        seed=1,
        session=session,
        player_id=player.id,
    )
    await session.flush()
    return result.args


async def latest_autopsy(session, player_id: str):
    event = await session.scalar(
        select(Event)
        .where(Event.player_id == player_id, Event.kind == "AUTOPSY_GENERATED")
        .order_by(Event.id.desc())
    )
    if not event:
        return None
    return json.loads(event.payload_json)

