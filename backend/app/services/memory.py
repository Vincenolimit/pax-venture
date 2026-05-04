from sqlalchemy import select

from app.core.config import QWEN_MODEL
from app.core.openrouter import call_tool
from app.core.tools import COMPACT_TOOL
from app.core.validators import validate_compact_memory
from app.models import Decision, Memory
from app.services.events import append_event


async def compact_memory(session, player, industry):
    mem = await session.get(Memory, player.id)
    decisions = (await session.scalars(select(Decision).where(Decision.player_id == player.id, Decision.month == player.current_month).order_by(Decision.importance.desc()).limit(3))).all()
    top_line = "Quiet month" if not decisions else decisions[0].narrative[:120]
    result = await call_tool("compact_memory", QWEN_MODEL, [{"role": "user", "content": top_line}], COMPACT_TOOL, cache_control_on_system=False, seed=1, session=session, player_id=player.id)
    cleaned, _ = validate_compact_memory(industry, result.args, False, False, {"period_summary": mem.period_summary, "origin_story": mem.origin_story})
    lines = [ln for ln in mem.recent.split("\n") if ln.strip()]
    lines.append(cleaned["recent_line"])
    if len(lines) > 3:
        mem.period_summary = (mem.period_summary + " " + lines.pop(0)).strip()[:300]
    mem.recent = "\n".join(lines)
    await append_event(session, player.id, "MEMORY_COMPACTED", "kernel", {"recent": mem.recent}, month=player.current_month)
