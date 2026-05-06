from app.main import apply_memory_patch, build_month_payload, new_game_state


def test_memory_patch_dedupes_and_caps_memory_layers():
    game = new_game_state("Pax Motors", "Vincent")

    for i in range(30):
        apply_memory_patch(
            game,
            {
                "facts": [{"key": "ceo_name", "value": "Vincent"}],
                "threads": [{"label": f"Thread {i}", "summary": f"Update {i}"}],
                "competitors": [{"name": "Tesla", "summary": f"Move {i}"}],
                "world": [{"summary": f"World {i}"}],
                "summary": f"Summary {i}",
            },
        )

    memory = game["memory"]
    assert memory["identity"]["ceo_name"] == "Vincent"
    assert len(memory["threads"]) == 8
    assert len(memory["world"]) == 8
    assert len(memory["recent_summaries"]) == 8
    assert len(memory["competitors"]["Tesla"]["timeline"]) == 24


def test_month_payload_includes_identity_canon_threads_world_and_summaries():
    game = new_game_state("Pax Motors", "Vincent")
    game["memory"]["canon"] = ["M1 canon: keep suppliers close"]
    apply_memory_patch(
        game,
        {
            "threads": [{"label": "Battery program", "summary": "Supplier shortlist open"}],
            "world": [{"summary": "EU emissions pressure is rising"}],
            "summary": "M1: Battery work began.",
        },
    )

    payload = build_month_payload(game, "Secure cells for our EV launch.")

    assert payload["memory"]["identity"]["ceo_name"] == "Vincent"
    assert "keep suppliers close" in payload["memory"]["canon"][0]
    assert payload["memory"]["threads"][0]["label"] == "Battery program"
    assert payload["memory"]["world"][0]["summary"] == "EU emissions pressure is rising"
    assert payload["memory"]["recent_summaries"] == ["M1: Battery work began."]
    assert payload["decision"] == "Secure cells for our EV launch."
