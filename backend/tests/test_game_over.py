from fastapi.testclient import TestClient

from app import main


def test_cash_below_zero_marks_game_over_and_blocks_more_simulation(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "STORE_PATH", tmp_path / "games.json")
    main.games.clear()

    async def fake_resolve_month(client, game, action_text):
        return {
            "your_move": "Board | CASH CRISIS: The company ran out of money.",
            "competitor_events": [{"name": "Tesla", "action": "Tesla waited out the collapse."}],
            "world_events": [{"source": "Market", "title": "CREDIT CLOSED", "body": "Lenders stepped back."}],
            "cash_delta": -2_000_000,
            "revenue_delta": 0,
            "market_cap_delta": -1_000_000,
            "initiative_updates": [],
            "next_inbox": [],
            "memory_patch": {"summary": "The company ran out of cash."},
        }

    monkeypatch.setattr(main, "resolve_month", fake_resolve_month)
    client = TestClient(main.app)
    created = client.post("/api/game", json={"company_name": "Pax Motors"}).json()

    response = client.post(f"/api/game/{created['id']}/simulate", json={"text": "Spend everything."})
    assert response.status_code == 200
    state = response.json()
    assert state["game_over"] is True
    assert state["autopsy"]["cause"] == "cash_below_zero"
    assert "cash" in state["autopsy"]["board_note"].lower()

    blocked = client.post(f"/api/game/{created['id']}/simulate", json={"text": "Try again."})
    assert blocked.status_code == 409
