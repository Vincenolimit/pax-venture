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
async def test_decide_and_end_month_flow(client):
    player = await client.post(
        "/api/v1/players",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"industry_id": "automotive", "name": "ceo", "company_name": "co", "style": "aggressive", "risk_tolerance": "high", "model_tier": "balanced", "cost_cap_usd": None},
    )
    pid = player.json()["player"]["id"]

    await client.post(f"/api/v1/players/{pid}/start-month", headers={"Idempotency-Key": str(uuid.uuid4())})
    decide = await client.post(
        f"/api/v1/players/{pid}/decide",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"text": "Cut cost and push EV platform", "inbox_ref_ids": []},
    )
    assert decide.status_code == 200
    assert "event: result" in decide.text

    ended = await client.post(f"/api/v1/players/{pid}/end-month", headers={"Idempotency-Key": str(uuid.uuid4())})
    assert ended.status_code == 200
    body = ended.json()
    assert "month" in body
    assert "cash" in body
