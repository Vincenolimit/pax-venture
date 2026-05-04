INBOX_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_inbox_emails",
        "description": "Generate this month's inbox of 3-5 in-character emails for the CEO.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["emails"],
            "properties": {
                "emails": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["sender", "subject", "body", "category", "requires_action", "references"],
                        "properties": {
                            "sender": {"type": "string"},
                            "subject": {"type": "string", "maxLength": 80},
                            "body": {"type": "string", "maxLength": 300},
                            "category": {"type": "string"},
                            "requires_action": {"type": "boolean"},
                            "references": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "thread_label": {"type": "string"},
                                    "flag_name": {"type": "string"},
                                    "world_event_id": {"type": "string"},
                                    "parent_message_id": {"type": "integer"},
                                },
                            },
                        },
                    },
                }
            },
        },
    },
}

RESOLVE_TOOL = {
    "type": "function",
    "function": {
        "name": "resolve_decision",
        "description": "Resolve a CEO decision: produce dramatic narrative and the resulting state changes.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "narrative",
                "cash_impact",
                "revenue_impact",
                "market_impact",
                "importance",
                "employees_change",
                "relationship_updates",
                "new_threads",
                "closed_threads",
                "flag_updates",
            ],
            "properties": {
                "narrative": {"type": "string", "maxLength": 500},
                "cash_impact": {"type": "number"},
                "revenue_impact": {"type": "number"},
                "market_impact": {"type": "number"},
                "importance": {"type": "number", "minimum": 0, "maximum": 1},
                "employees_change": {"type": "integer"},
                "relationship_updates": {"type": "object", "additionalProperties": {"type": "string"}},
                "new_threads": {
                    "type": "array",
                    "maxItems": 2,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["label", "importance"],
                        "properties": {
                            "label": {"type": "string", "maxLength": 40},
                            "importance": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                    },
                },
                "closed_threads": {"type": "array", "items": {"type": "string", "maxLength": 40}},
                "flag_updates": {"type": "object", "additionalProperties": {"type": "boolean"}},
            },
        },
    },
}

COMPACT_TOOL = {
    "type": "function",
    "function": {
        "name": "compact_memory",
        "description": "Roll up the last month into the hierarchical memory.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["recent_line", "period_summary", "origin_story"],
            "properties": {
                "recent_line": {"type": "string", "maxLength": 120},
                "period_summary": {"type": "string", "maxLength": 300},
                "origin_story": {"type": "string", "maxLength": 160},
            },
        },
    },
}

AUTOPSY_TOOL = {
    "type": "function",
    "function": {
        "name": "autopsy_summary",
        "description": "Generate a shareable end-of-game summary card.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["headline", "arc_summary", "pivotal_decisions", "cause_of_death", "board_quote"],
            "properties": {
                "headline": {"type": "string", "maxLength": 80},
                "arc_summary": {"type": "string", "maxLength": 600},
                "pivotal_decisions": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["month", "one_liner", "verdict"],
                        "properties": {
                            "month": {"type": "integer"},
                            "one_liner": {"type": "string", "maxLength": 120},
                            "verdict": {"type": "string", "enum": ["brilliant", "sound", "risky", "fatal"]},
                        },
                    },
                },
                "cause_of_death": {"type": "string", "maxLength": 120},
                "board_quote": {"type": "string", "maxLength": 160},
            },
        },
    },
}
