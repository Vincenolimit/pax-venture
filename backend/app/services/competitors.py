import math
import random

from app.core.config import POSTURE_RULES
from app.services.events import append_event


def seeded_rng(player, comp) -> random.Random:
    return random.Random(abs(hash((player.id, comp.id, player.current_month))))


async def apply_posture_transitions(session, comp, player, month: int, flags: dict):
    changed = False
    for rule in POSTURE_RULES:
        if comp.template_id == rule["template"] and flags.get(rule["trigger"]):
            comp.posture = rule["posture"]
            comp.posture_until_month = month + rule["duration"]
            changed = True
    if player.market_share >= 12 and comp.template_id == "novatech":
        comp.posture = "DEFENSIVE"
        changed = True
    if player.market_share >= 18 and comp.template_id == "autovista":
        comp.posture = "DEFENSIVE"
        changed = True
    if changed:
        await append_event(session, player.id, "COMPETITOR_REACTED", "competitor", {"competitor_id": comp.id, "posture": comp.posture}, month=month)
    return changed


def end_month_competitor_tick(comp, player, month, rng):
    posture_modifier = {"OBSERVING": 1.00, "DEFENSIVE": 0.85, "AGGRESSIVE": 1.30, "STRUGGLING": 0.60}[comp.posture]
    base = comp.base_growth * posture_modifier
    noise = rng.gauss(0, comp.volatility)
    seasonal = 0.02 * math.sin(month * 0.5)
    comp.revenue *= 1 + base + noise + seasonal
    comp.cash += comp.revenue - comp.expenses
    comp.market_share = max(0.1, comp.market_share + rng.gauss(0, 0.3))
    if month % 3 == 0 and rng.random() < 0.03:
        scale = rng.uniform(0.1, 0.3)
        comp.cash *= 1 - scale
        comp.market_share *= 1 - (scale * 0.5)
