from app.main import (
    apply_active_initiatives,
    apply_competitor_initiatives,
    apply_resolution,
    memory_context,
    new_game_state,
    quiet_player_result,
    resolve_competitors_locally,
)


def _solo_competitor_game():
    game = new_game_state("Pax Motors", "Vincent")
    game["id"] = "continuity-test"
    game["competitors"] = [
        {
            "name": "Tesla",
            "cash": 37_000_000_000,
            "revenue": 8_200_000_000,
            "market_cap": 1_454_000_000_000,
            "revenue_multiple": 14.8,
            "initiatives": [],
        }
    ]
    return game


def _simulate_quiet_month(game):
    initiative_effect = apply_active_initiatives(game)
    competitor_effects = apply_competitor_initiatives(game)
    competitor_results = resolve_competitors_locally(game)
    player_result = quiet_player_result(game, initiative_effect, competitor_results)
    apply_resolution(game, player_result, competitor_results, initiative_effect, competitor_effects)
    return competitor_results


def test_active_competitor_initiative_is_continued_before_new_move():
    game = _solo_competitor_game()
    game["competitors"][0]["initiatives"] = [
        {
            "name": "Battery Supplier Acquisition",
            "monthly_cash_delta": -100_000,
            "monthly_revenue_delta": 40_000,
            "monthly_market_cap_delta": 250_000,
            "remaining_months": 4,
            "started_month": 1,
            "elapsed_months": 1,
            "last_action": "Tesla moved to acquire a distressed battery-controls supplier.",
        }
    ]

    apply_competitor_initiatives(game)
    results = resolve_competitors_locally(game)

    assert len(results) == 1
    assert results[0]["initiative"] == "Battery Supplier Acquisition"
    assert results[0]["initiative_status"] == "continued"
    assert "Battery Supplier Acquisition" in results[0]["action"]
    assert "initiative_update" not in results[0]


def test_competitor_actions_are_added_to_player_memory_context():
    game = _solo_competitor_game()

    month_one = _simulate_quiet_month(game)
    month_two = _simulate_quiet_month(game)
    context = memory_context(game)

    assert month_one[0]["initiative_status"] == "opened"
    assert month_two[0]["initiative_status"] == "continued"
    assert context["competitor_memory"]
    assert any("Tesla opened" in line for line in context["competitor_memory"])
    assert any("Tesla continued" in line for line in context["competitor_memory"])
