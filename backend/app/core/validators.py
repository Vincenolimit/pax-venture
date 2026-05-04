import json


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def validate_generate_inbox_emails(industry, args, active_threads=None, flags=None, active_world_event_ids=None):
    warnings = []
    emails = args.get("emails", [])
    sender_vocab = set(json.loads(industry.sender_vocab))
    category_vocab = set(json.loads(industry.category_vocab))
    valid = []
    for email in emails:
        if email.get("sender") not in sender_vocab or email.get("category") not in category_vocab:
            warnings.append("vocab_violation")
            continue
        email["subject"] = email.get("subject", "")[:80]
        email["body"] = email.get("body", "")[:300]
        valid.append(email)
    if valid and not (valid[0].get("sender") == "Board" and valid[0].get("category") == "board"):
        valid.insert(0, {"sender": "Board", "subject": "Welcome from the Board", "body": "Deliver disciplined growth and preserve cash runway.", "category": "board", "requires_action": True, "references": {"thread_label": "board_confidence"}})
    return {"emails": valid[:5]}, warnings


def validate_resolve_decision(industry, args, active_threads=None):
    warnings = []
    clamps = {
        "cash_impact": json.loads(industry.cash_impact_clamp),
        "revenue_impact": json.loads(industry.revenue_impact_clamp),
        "market_impact": json.loads(industry.market_impact_clamp),
        "employees_change": json.loads(industry.employees_change_clamp),
    }
    cleaned = dict(args)
    for k, (lo, hi) in clamps.items():
        original = cleaned.get(k, 0)
        cleaned[k] = _clamp(original, lo, hi)
        if original != cleaned[k]:
            warnings.append(f"clamped_{k}")
    cleaned["narrative"] = cleaned.get("narrative", "")[:500]
    if "cash_impact" in cleaned and args.get("cash_impact", 0) and abs(cleaned["cash_impact"] - args.get("cash_impact", 0)) / max(1, abs(args.get("cash_impact", 0))) >= 0.5:
        cleaned["narrative"] += " (Note: scope reduced)"

    allowed_flags = set(json.loads(industry.flag_vocabulary))
    cleaned["flag_updates"] = {k: v for k, v in cleaned.get("flag_updates", {}).items() if k in allowed_flags}

    rel_keys = set(json.loads(industry.relationship_keys))
    rel_vocab = json.loads(industry.relationship_vocab)
    rel = {}
    for k, v in cleaned.get("relationship_updates", {}).items():
        if k in rel_keys and v in rel_vocab.get(k, []):
            rel[k] = v
        else:
            warnings.append("relationship_vocab_violation")
    cleaned["relationship_updates"] = rel
    cleaned["new_threads"] = [{"label": t.get("label", "")[:40], "importance": t.get("importance", 0.5)} for t in cleaned.get("new_threads", [])[:2]]

    active = {t.lower() for t in (active_threads or [])}
    cleaned["closed_threads"] = [t for t in cleaned.get("closed_threads", []) if t.lower() in active]
    return cleaned, warnings


def validate_compact_memory(_industry, args, should_rewrite_period=False, should_rewrite_origin=False, prior=None):
    prior = prior or {}
    cleaned = dict(args)
    cleaned["recent_line"] = cleaned.get("recent_line", "")[:120]
    cleaned["period_summary"] = (cleaned.get("period_summary", "")[:300] if should_rewrite_period else prior.get("period_summary", ""))
    cleaned["origin_story"] = (cleaned.get("origin_story", "")[:160] if should_rewrite_origin else prior.get("origin_story", ""))
    return cleaned, []
