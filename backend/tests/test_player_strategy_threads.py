from app.main import (
    apply_active_initiatives,
    apply_month_result,
    new_game_state,
    quiet_player_result,
)


def _one_month_player_result():
    return {
        "your_move": "Board | ROBOTICS INVESTMENT APPROVED: The company spent money and investors noticed.",
        "competitor_spotlight": "Tesla Desk | RIVAL WATCH: Tesla watched the move.",
        "market": "Reuters EV Desk | MARKET NOTE: Suppliers tracked the order.",
        "cash_delta": -50_000,
        "revenue_delta": 12_000,
        "market_cap_delta": 900_000,
        "initiative_updates": [],
    }


def _robotics_initiative():
    return {
        "name": "Robotics Platform",
        "kind": "strategic_thesis",
        "category": "robotics",
        "phase": "charter",
        "thesis": "Build a decade-scale robotics capability.",
        "duration_months": 120,
        "horizon_months": 120,
        "monthly_cash_delta": -120_000,
        "monthly_revenue_delta": 0,
        "monthly_market_cap_delta": 200_000,
        "milestones": [{"month": 1, "label": "Robotics charter funded"}],
        "last_action": "The LLM converted the order into a multi-year robotics thesis.",
    }


def test_robotics_action_becomes_ten_year_strategy_only_from_llm_initiative_update():
    game = new_game_state("Pax Motors", "Vincent")
    result = {**_one_month_player_result(), "initiative_updates": [_robotics_initiative()]}

    apply_month_result(game, result, "Invest in robotics and factory automation as a 10 year plan.")

    assert game["initiatives"]
    robotics = game["initiatives"][0]
    assert robotics["name"] == "Robotics Platform"
    assert robotics["kind"] == "strategic_thesis"
    assert robotics["category"] == "robotics"
    assert robotics["horizon_months"] == 120
    assert "multi-year robotics thesis" in robotics["last_action"]


def test_robotics_strategy_keeps_affecting_later_months_and_narrative():
    game = new_game_state("Pax Motors", "Vincent")
    result = {**_one_month_player_result(), "initiative_updates": [_robotics_initiative()]}

    apply_month_result(game, result, "Invest in robotics and factory automation as a 10 year plan.")
    initiative_effect = apply_active_initiatives(game)
    quiet_result = quiet_player_result(game, initiative_effect, [])

    assert initiative_effect["names"] == ["Robotics Platform"]
    assert initiative_effect["cash_delta"] < 0
    assert initiative_effect["milestones"][0]["label"] == "Robotics charter funded"
    assert game["initiatives"][0]["remaining_months"] == 119
    assert game["initiatives"][0]["phase"] == "charter"
    assert "Robotics Platform" in quiet_result["your_move"]
    assert "earlier decision kept changing the company" in quiet_result["your_move"]
