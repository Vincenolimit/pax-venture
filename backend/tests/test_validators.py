import json

from app.core.validators import validate_generate_inbox_emails, validate_resolve_decision
from app.models import Industry


def _industry():
    return Industry(
        id="automotive",
        name="Automotive",
        schema_version=1,
        prompt_version=1,
        system_prompt_template="x",
        starting_state_json="{}",
        financial_constants="{}",
        flag_vocabulary=json.dumps(["ev_platform_launched"]),
        intent_taxonomy="[]",
        relationship_keys=json.dumps(["board"]),
        relationship_vocab=json.dumps({"board": ["pleased", "neutral"]}),
        sender_vocab=json.dumps(["Board", "CFO"]),
        category_vocab=json.dumps(["board", "warning"]),
        employees_change_clamp=json.dumps([-10, 20]),
        cash_impact_clamp=json.dumps([-5000000, 3000000]),
        revenue_impact_clamp=json.dumps([-2000000, 5000000]),
        market_impact_clamp=json.dumps([-3.0, 3.0]),
        recommended_models="{}",
        enabled=True,
    )


def test_inbox_validator_injects_board_and_rejects_vocab():
    ind = _industry()
    cleaned, warnings = validate_generate_inbox_emails(
        ind,
        {
            "emails": [
                {"sender": "Bad", "subject": "x", "body": "y", "category": "warning", "requires_action": True, "references": {}},
                {"sender": "CFO", "subject": "s" * 200, "body": "b" * 500, "category": "warning", "requires_action": True, "references": {}},
            ]
        },
    )
    assert warnings
    assert cleaned["emails"][0]["sender"] == "Board"
    assert len(cleaned["emails"][1]["subject"]) == 80
    assert len(cleaned["emails"][1]["body"]) == 300


def test_resolve_validator_clamps_and_filters_vocab():
    ind = _industry()
    cleaned, warnings = validate_resolve_decision(
        ind,
        {
            "narrative": "n" * 1000,
            "cash_impact": -10_000_000,
            "revenue_impact": 10_000_000,
            "market_impact": 10.0,
            "importance": 0.6,
            "employees_change": 200,
            "relationship_updates": {"board": "pleased", "bad": "x"},
            "new_threads": [{"label": "x" * 100, "importance": 0.2}],
            "closed_threads": ["A", "B"],
            "flag_updates": {"ev_platform_launched": True, "bad_flag": True},
        },
        ["a"],
    )
    assert cleaned["cash_impact"] == -5_000_000
    assert cleaned["revenue_impact"] == 5_000_000
    assert cleaned["market_impact"] == 3.0
    assert cleaned["employees_change"] == 20
    assert cleaned["flag_updates"] == {"ev_platform_launched": True}
    assert cleaned["relationship_updates"] == {"board": "pleased"}
    assert cleaned["closed_threads"] == ["A"]
    assert len(cleaned["new_threads"][0]["label"]) == 40
    assert "scope reduced" in cleaned["narrative"]
    assert warnings
