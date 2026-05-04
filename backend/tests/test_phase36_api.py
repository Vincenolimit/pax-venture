import uuid

import pytest


@pytest.mark.asyncio
async def test_patch_player_and_cost_endpoints(client):
    player = await client.post(
        "/api/v1/players",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"industry_id": "automotive", "name": "ceo", "company_name": "co", "style": "aggressive", "risk_tolerance": "high", "model_tier": "balanced"},
    )
    pid = player.json()["player"]["id"]

    patched = await client.patch(f"/api/v1/players/{pid}", json={"model_tier": "premium", "cost_cap_usd": 4.5})
    assert patched.status_code == 200
    assert patched.json()["model_tier"] == "premium"
    assert patched.json()["cost_cap_usd"] == 4.5

    cost = await client.get(f"/api/v1/players/{pid}/cost")
    assert cost.status_code == 200
    assert "cost_spent_usd" in cost.json()
    assert "cap_percent" in cost.json()


@pytest.mark.asyncio
async def test_admin_health_endpoint(client):
    res = await client.get("/api/v1/admin/health")
    assert res.status_code == 200
    body = res.json()
    assert "cache_hit_ratio_mean" in body
    assert "sample_size" in body
    assert "cache_healthy" in body


@pytest.mark.asyncio
async def test_end_month_idempotency_replay(client):
    player = await client.post(
        "/api/v1/players",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"industry_id": "automotive", "name": "ceo", "company_name": "co", "style": "aggressive", "risk_tolerance": "high", "model_tier": "balanced"},
    )
    pid = player.json()["player"]["id"]
    await client.post(f"/api/v1/players/{pid}/start-month", headers={"Idempotency-Key": str(uuid.uuid4())})

    key = str(uuid.uuid4())
    first = await client.post(f"/api/v1/players/{pid}/end-month", headers={"Idempotency-Key": key})
    second = await client.post(f"/api/v1/players/{pid}/end-month", headers={"Idempotency-Key": key})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


@pytest.mark.asyncio
async def test_autopsy_endpoint_returns_payload(client):
    player = await client.post(
        "/api/v1/players",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"industry_id": "automotive", "name": "ceo", "company_name": "co", "style": "aggressive", "risk_tolerance": "high", "model_tier": "balanced"},
    )
    pid = player.json()["player"]["id"]
    res = await client.get(f"/api/v1/players/{pid}/autopsy")
    assert res.status_code == 200
    body = res.json()
    assert "headline" in body
    assert "arc_summary" in body


@pytest.mark.asyncio
async def test_state_and_messages_endpoints(client):
    player = await client.post(
        "/api/v1/players",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"industry_id": "automotive", "name": "ceo", "company_name": "co", "style": "aggressive", "risk_tolerance": "high", "model_tier": "balanced"},
    )
    pid = player.json()["player"]["id"]

    state = await client.get(f"/api/v1/players/{pid}/state")
    assert state.status_code == 200
    assert state.json()["player"]["id"] == pid

    await client.post(f"/api/v1/players/{pid}/start-month", headers={"Idempotency-Key": str(uuid.uuid4())})
    inbox = await client.get(f"/api/v1/players/{pid}/messages")
    assert inbox.status_code == 200
    assert isinstance(inbox.json()["messages"], list)
    if inbox.json()["messages"]:
        mid = inbox.json()["messages"][0]["id"]
        patched = await client.patch(f"/api/v1/players/{pid}/messages/{mid}", json={"is_read": True})
        assert patched.status_code == 200
        assert patched.json()["is_read"] is True
