def within_cost_cap(player, estimated_cost: float) -> bool:
    return (player.cost_cap_usd is None) or (player.cost_spent_usd + estimated_cost <= player.cost_cap_usd)

