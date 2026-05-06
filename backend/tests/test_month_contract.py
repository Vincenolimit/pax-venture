from app.main import validate_month_result


def test_month_result_clamps_numbers_and_adds_required_fallback_cards():
    result = validate_month_result(
        {
            "your_move": "Board | MOONSHOT APPROVED: The CEO overreached, but the board forced a narrower budget.",
            "competitor_events": [],
            "world_events": [],
            "cash_delta": -99_000_000,
            "revenue_delta": 99_000_000,
            "market_cap_delta": 99_000_000,
            "initiative_updates": [],
            "next_inbox": [],
            "memory_patch": {"summary": "The company tried a dramatic moonshot."},
        }
    )

    assert result["cash_delta"] == -5_000_000
    assert result["revenue_delta"] == 5_000_000
    assert result["market_cap_delta"] == 25_000_000
    assert result["competitor_events"][0]["name"] == "Rivals"
    assert result["world_events"][0]["source"] == "Reuters EV Desk"
    assert len(result["next_inbox"]) == 2


def test_month_result_truncates_oversized_strings():
    result = validate_month_result(
        {
            "your_move": {"source": "Board", "title": "A" * 200, "body": "B" * 900},
            "competitor_events": [{"name": "Tesla", "action": "C" * 500}],
            "world_events": [{"source": "Market", "title": "D" * 200, "body": "E" * 900}],
            "cash_delta": 0,
            "revenue_delta": 0,
            "market_cap_delta": 0,
            "initiative_updates": [{"name": "X" * 120, "duration_months": 999}],
            "next_inbox": [{"sender": "Board", "subject": "F" * 200, "body": "G" * 900}],
            "memory_patch": {"summary": "H" * 500},
        }
    )

    assert len(result["your_move"]["title"]) == 90
    assert len(result["your_move"]["body"]) == 420
    assert len(result["competitor_events"][0]["action"]) == 220
    assert len(result["world_events"][0]["body"]) == 420
    assert result["initiative_updates"][0]["duration_months"] == 120
    assert len(result["next_inbox"][0]["subject"]) == 90
    assert len(result["memory_patch"]["summary"]) == 220
