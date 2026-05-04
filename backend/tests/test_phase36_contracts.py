import uuid

import pytest

from app.core.seed import compute_seed


def test_compute_seed_is_stable_and_bounded():
    a = compute_seed("p1", 3, 7)
    b = compute_seed("p1", 3, 7)
    c = compute_seed("p1", 3, 8)
    assert a == b
    assert a != c
    assert 0 <= a <= 0xFFFFFFFF


@pytest.mark.asyncio
async def test_leaderboard_endpoint_exists(client):
    player = await client.post(
        "/api/v1/players",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"industry_id": "automotive", "name": "ceo", "company_name": "co", "style": "aggressive", "risk_tolerance": "high", "model_tier": "balanced"},
    )
    assert player.status_code == 200
    res = await client.get("/api/v1/leaderboard")
    assert res.status_code == 200
    assert "rows" in res.json()


@pytest.mark.asyncio
async def test_patch_player_rejects_negative_cost_cap(client):
    player = await client.post(
        "/api/v1/players",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"industry_id": "automotive", "name": "ceo", "company_name": "co", "style": "aggressive", "risk_tolerance": "high", "model_tier": "balanced"},
    )
    pid = player.json()["player"]["id"]
    patched = await client.patch(f"/api/v1/players/{pid}", json={"cost_cap_usd": -1})
    assert patched.status_code == 400


@pytest.mark.asyncio
async def test_start_month_streams_error_event_for_missing_player(client):
    res = await client.post(f"/api/v1/players/missing/start-month", headers={"Idempotency-Key": str(uuid.uuid4())})
    assert res.status_code == 200
    assert "event: error" in res.text
