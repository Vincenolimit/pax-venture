import uuid

import pytest


@pytest.mark.asyncio
async def test_create_player_and_start_month_sse(client):
    player = await client.post(
        "/api/v1/players",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"industry_id": "automotive", "name": "ceo", "company_name": "co", "style": "aggressive", "risk_tolerance": "high", "model_tier": "balanced", "cost_cap_usd": None},
    )
    assert player.status_code == 200
    pid = player.json()["player"]["id"]

    res = await client.post(f"/api/v1/players/{pid}/start-month", headers={"Idempotency-Key": str(uuid.uuid4())})
    assert res.status_code == 200
    assert "event: done" in res.text


@pytest.mark.asyncio
async def test_actions_resolve_when_month_is_simulated(client):
    player = await client.post(
        "/api/v1/players",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"industry_id": "automotive", "name": "ceo", "company_name": "co", "style": "aggressive", "risk_tolerance": "high", "model_tier": "balanced", "cost_cap_usd": None},
    )
    pid = player.json()["player"]["id"]
    starting_cash = player.json()["player"]["cash"]

    await client.post(f"/api/v1/players/{pid}/start-month", headers={"Idempotency-Key": str(uuid.uuid4())})
    action = await client.post(
        f"/api/v1/players/{pid}/actions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"text": "Cut cost and push EV platform", "inbox_ref_ids": []},
    )
    assert action.status_code == 200
    assert action.json()["action"]["text"] == "Cut cost and push EV platform"

    queued = await client.get(f"/api/v1/players/{pid}/actions")
    assert queued.status_code == 200
    assert [row["text"] for row in queued.json()["actions"]] == ["Cut cost and push EV platform"]

    before_sim = await client.get(f"/api/v1/players/{pid}/state")
    assert before_sim.json()["player"]["cash"] == starting_cash

    ended = await client.post(f"/api/v1/players/{pid}/end-month", headers={"Idempotency-Key": str(uuid.uuid4())})
    assert ended.status_code == 200
    body = ended.json()
    assert "month" in body
    assert "cash" in body
    assert body["decision"]["actions"] == ["Cut cost and push EV platform"]
    assert body["actions_resolved"][0]["text"] == "Cut cost and push EV platform"

    next_month_actions = await client.get(f"/api/v1/players/{pid}/actions")
    assert next_month_actions.json()["actions"] == []
