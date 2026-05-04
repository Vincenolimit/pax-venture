import json
from app.models.world_event import WorldEvent


def build_cached_system_block(industry, memory, active_world_events: list[WorldEvent]) -> list[dict]:
    active = "\n".join([f"- {e.id} ({e.severity}): {e.narrative_seed}" for e in active_world_events]) or "- none"
    text = industry.system_prompt_template
    replacements = {
        "{{industry_name}}": industry.name,
        "{{sender_vocab}}": industry.sender_vocab,
        "{{category_vocab}}": industry.category_vocab,
        "{{relationship_keys}}": industry.relationship_keys,
        "{{relationship_vocab}}": industry.relationship_vocab,
        "{{flag_vocabulary}}": industry.flag_vocabulary,
        "{{cash_impact_clamp}}": industry.cash_impact_clamp,
        "{{revenue_impact_clamp}}": industry.revenue_impact_clamp,
        "{{market_impact_clamp}}": industry.market_impact_clamp,
        "{{employees_change_clamp}}": industry.employees_change_clamp,
        "{{active_world_events_block}}": active,
        "{{origin_story}}": memory.origin_story,
        "{{period_summary}}": memory.period_summary,
        "{{period_start}}": str(memory.period_start),
        "{{period_end}}": str(memory.period_end),
    }
    for k, v in replacements.items():
        text = text.replace(k, str(v))
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def build_dynamic_block(state, recent, threads, retrieved_decisions, current_emails, instruction) -> str:
    return "\n".join(
        [
            "=== CURRENT STATE ===",
            json.dumps(state),
            "=== RECENT MEMORY ===",
            recent or "",
            "=== ACTIVE THREADS ===",
            "\n".join(threads) if threads else "none",
            "=== RETRIEVED PAST DECISIONS ===",
            "\n".join(retrieved_decisions) if retrieved_decisions else "none",
            "=== THIS MONTH'S INBOX ===",
            "\n".join(current_emails) if current_emails else "none",
            "=== INSTRUCTION ===",
            instruction,
        ]
    )
