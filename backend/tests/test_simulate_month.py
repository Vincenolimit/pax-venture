from fastapi.testclient import TestClient

from app import main


def _fake_month_result():
    return {
        "your_move": {
            "source": "Board of Directors",
            "title": "BATTERY DEAL CLEARED",
            "body": "The CEO secured a narrow cell supply agreement. Finance accepted the deposit because production risk fell.",
        },
        "competitor_events": [
            {
                "name": "Tesla",
                "action": "Tesla pulled forward fleet discounts to defend enterprise accounts.",
                "cash_delta": -100_000,
                "revenue_delta": 40_000,
                "market_cap_delta": 250_000,
            }
        ],
        "world_events": [
            {
                "source": "Reuters EV Desk",
                "title": "CELL PRICES TIGHTEN",
                "body": "Battery suppliers warned smaller automakers that delivery windows are slipping.",
                "severity": "warning",
            }
        ],
        "cash_delta": -200_000,
        "revenue_delta": 75_000,
        "market_cap_delta": 500_000,
        "initiative_updates": [
            {
                "name": "Battery Supply Program",
                "monthly_cash_delta": -25_000,
                "monthly_revenue_delta": 10_000,
                "monthly_market_cap_delta": 40_000,
                "duration_months": 6,
            }
        ],
        "next_inbox": [
            {"sender": "CFO", "subject": "Deposit posted", "body": "Cash impact is visible this month."},
            {"sender": "Supplier", "subject": "Cells reserved", "body": "The supplier wants volume clarity."},
        ],
        "memory_patch": {
            "threads": [{"label": "Battery supply", "summary": "Cells reserved with a deposit"}],
            "competitors": [{"name": "Tesla", "summary": "Defended fleet buyers with discounts"}],
            "world": [{"summary": "Battery supply is tightening"}],
            "summary": "M1: Battery supply became the operating thread.",
        },
    }


def test_simulate_accepts_single_action_applies_result_and_persists(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "STORE_PATH", tmp_path / "games.json")
    main.games.clear()

    async def fake_resolve_month(client, game, action_text):
        assert action_text == "Secure batteries."
        return _fake_month_result()

    monkeypatch.setattr(main, "resolve_month", fake_resolve_month)
    client = TestClient(main.app)

    created = client.post("/api/game", json={"company_name": "Pax Motors", "ceo_name": "Vincent"}).json()
    response = client.post(f"/api/game/{created['id']}/simulate", json={"text": "Secure batteries."})

    assert response.status_code == 200
    state = response.json()
    assert state["month"] == 1
    assert state["cash"] == 800_000
    assert state["revenue"] == 125_000
    assert state["history"][0]["decision"] == "Secure batteries."
    assert state["history"][0]["competitor_events"][0]["name"] == "Tesla"
    assert state["history"][0]["world_events"][0]["title"] == "CELL PRICES TIGHTEN"
    assert state["inbox"][0]["subject"] == "Deposit posted"
    assert state["memory"]["threads"][0]["label"] == "Battery supply"
    assert (tmp_path / "games.json").exists()
