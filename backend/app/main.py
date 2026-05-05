import hashlib
import json
import os
import random
import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def _load_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip("\"' ")
        os.environ.setdefault(k, v)


_load_env()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.getenv("PAX_QWEN_MODEL", "qwen/qwen3.6-plus")
DATA_DIR = Path(os.getenv("PAX_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data")))
STORE_PATH = DATA_DIR / "games.json"

STARTING_CASH = 1_000_000
STARTING_REVENUE = 50_000
STARTUP_REVENUE_MULTIPLE = 20
ACTIVE_COMPETITOR_ACTIONS_PER_MONTH = 3
DEFAULT_REVENUE_MULTIPLE = 2
MARKET_CAP_CASH_WEIGHT = 0.5
COMPETITOR_MEMORY_LIMIT = 24
COMPETITORS = [
    {
        "name": "Tesla",
        "cash": 37_000_000_000,
        "revenue": 8_200_000_000,
        "market_cap": 1_454_000_000_000,
        "revenue_multiple": 14.8,
    },
    {
        "name": "Toyota",
        "cash": 64_000_000_000,
        "revenue": 26_000_000_000,
        "market_cap": 276_940_000_000,
        "revenue_multiple": 0.9,
    },
    {
        "name": "BYD",
        "cash": 22_000_000_000,
        "revenue": 12_100_000_000,
        "market_cap": 137_740_000_000,
        "revenue_multiple": 0.95,
    },
    {
        "name": "Xiaomi Auto",
        "cash": 18_000_000_000,
        "revenue": 8_500_000_000,
        "market_cap": 102_340_000_000,
        "revenue_multiple": 1.0,
    },
    {
        "name": "Hyundai",
        "cash": 24_000_000_000,
        "revenue": 13_000_000_000,
        "market_cap": 89_540_000_000,
        "revenue_multiple": 0.57,
    },
]

_SECTION = {
    "type": "string",
    "maxLength": 520,
    "description": "One in-world event card formatted as 'SOURCE | HEADLINE: 2-3 tight sentences.'",
}

_INITIATIVE = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "name",
        "monthly_cash_delta",
        "monthly_revenue_delta",
        "monthly_market_cap_delta",
        "duration_months",
    ],
    "properties": {
        "name": {"type": "string", "maxLength": 60},
        "monthly_cash_delta": {"type": "number"},
        "monthly_revenue_delta": {"type": "number"},
        "monthly_market_cap_delta": {"type": "number"},
        "duration_months": {"type": "integer", "minimum": 1, "maximum": 36},
    },
}

PLAYER_TOOL = {
    "type": "function",
    "function": {
        "name": "resolve_player",
        "description": "Resolve the player's month as three Pax-Historia-style event cards plus financial impact.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "your_move",
                "competitor_spotlight",
                "market",
                "cash_delta",
                "revenue_delta",
                "market_cap_delta",
                "initiative_updates",
            ],
            "properties": {
                "your_move": _SECTION,
                "competitor_spotlight": _SECTION,
                "market": _SECTION,
                "cash_delta": {"type": "number"},
                "revenue_delta": {"type": "number"},
                "market_cap_delta": {"type": "number"},
                "initiative_updates": {"type": "array", "maxItems": 3, "items": _INITIATIVE},
            },
        },
    },
}

COMPETITOR_TOOL = {
    "type": "function",
    "function": {
        "name": "resolve_competitor",
        "description": "Decide what this competitor did this month and its financial impact.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["action", "cash_delta", "revenue_delta"],
            "properties": {
                "action": {"type": "string", "maxLength": 140},
                "cash_delta": {"type": "number"},
                "revenue_delta": {"type": "number"},
            },
        },
    },
}

PLAYER_SYSTEM = (
    "You are the in-world event engine of Pax Venture, a CEO sandbox in the EV automotive industry. "
    "Resolve ONE month in the immersive event-card tone of Pax Historia: words become actions, actors react, "
    "and the world reports what changed.\n\n"
    "Respond as THREE in-world event-card strings. Each field must be formatted exactly as "
    "'SOURCE | HEADLINE: body'. SOURCE is a real actor or desk, not the AI and not the UI "
    "(examples: Board of Directors, CFO Office, Reuters EV Desk, Tesla Fleet Desk, Ministry of Transport, Supplier Council). "
    "HEADLINE is a concrete news-style event title. Body is 2-3 tight sentences with no filler:\n"
    "1. your_move - the outcome of the player's actions this month, addressed to or about the CEO when appropriate.\n"
    "2. competitor_spotlight - pick ONE competitor from competitor_actions_this_month and tell that story by name.\n"
    "3. market - broader industry signal, customer behavior, regulation, labor, suppliers, or capital markets.\n\n"
    "Use the supplied memory. If MEMORY names the CEO, remember and address them naturally. "
    "If actions contain identity/canon statements, absorb them as memory; do not treat identity as capital allocation. "
    "Maintain rival continuity. If competitor_memory or active competitor initiatives mention an acquisition, launch program, "
    "factory buildout, pricing campaign, or supplier move, treat it as an ongoing thread that can progress, stall, or compound. "
    "Do not write future competitor spotlights as if earlier rival moves never happened. "
    "Use grounded monthly magnitudes (tens of thousands for modest deals; hundreds of thousands for major launches). "
    "Cash delta is net of operating costs (baseline burn roughly equals revenue unless the player did something costly or revenue-generating). "
    "Market cap delta is investor re-rating for strategy, credibility, and risk. "
    "Do not mention exact dollar amounts, final cash/revenue/market-cap totals, impact chips, schemas, prompts, or simulation internals. "
    "If an action starts a long-running strategy like AGI, factories, R&D, autonomy, or expansion, add an initiative_update. "
    "Initiatives are recurring plans: they keep affecting the company every future month until their duration ends. "
    "If the player gives no new action, do not invent a new initiative; active initiatives are applied automatically. "
    "Be decisive and varied; not every month is break-even."
)

COMPETITOR_SYSTEM = (
    "You simulate ONE competitor in an EV automotive market for one month. "
    "Given your state and the player's actions this month, decide ONE realistic action you took and its financial impact. "
    "Use grounded monthly magnitudes (tens of thousands for normal moves, hundreds of thousands for major plays). "
    "Cash delta is net of operating costs. React to player threats and opportunities. Action: one short sentence."
)


games: dict[str, dict[str, Any]] = {}


class NewGameBody(BaseModel):
    company_name: str = "Pax Motors"
    ceo_name: str | None = None


class ActionBody(BaseModel):
    text: str


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def default_memory(company_name: str, ceo_name: str = "") -> dict[str, Any]:
    identity = {"company_name": company_name}
    if ceo_name:
        identity["ceo_name"] = ceo_name
    return {
        "identity": identity,
        "canon": [],
        "competitors": {},
        "tone": "Pax-Historia-style in-world event briefings: actor, date, headline, consequence.",
        "updated_at": now_iso(),
    }


def new_game_state(company_name: str, ceo_name: str = "") -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:12],
        "company_name": company_name,
        "month": 0,
        "cash": STARTING_CASH,
        "revenue": STARTING_REVENUE,
        "market_cap": market_cap(STARTING_CASH, STARTING_REVENUE),
        "actions": [],
        "initiatives": [],
        "competitors": [{**c, "initiatives": []} for c in COMPETITORS],
        "history": [],
        "memory": default_memory(company_name, ceo_name.strip()),
        "llm_calls": [],
    }


def market_cap(cash: float, monthly_revenue: float, revenue_multiple: float = STARTUP_REVENUE_MULTIPLE) -> float:
    annualized_revenue = max(0.0, float(monthly_revenue)) * 12
    return round(max(0.0, float(cash)) + annualized_revenue * revenue_multiple, 2)


def company_market_cap(company: dict[str, Any]) -> float:
    if "market_cap" in company:
        return round(max(0.0, float(company["market_cap"])), 2)
    return market_cap(company["cash"], company["revenue"])


def ensure_game_shape(g: dict[str, Any]) -> dict[str, Any]:
    g.setdefault("actions", [])
    g.setdefault("history", [])
    g.setdefault("initiatives", [])
    g.setdefault("market_cap", market_cap(g.get("cash", STARTING_CASH), g.get("revenue", STARTING_REVENUE)))
    g.setdefault("memory", default_memory(g.get("company_name", "Pax Motors")))
    g.setdefault("llm_calls", [])
    memory = g["memory"]
    memory.setdefault("identity", {})
    memory["identity"].setdefault("company_name", g.get("company_name", "Pax Motors"))
    memory.setdefault("canon", [])
    memory.setdefault("competitors", {})
    memory.setdefault("tone", "Pax-Historia-style in-world event briefings.")
    memory.setdefault("updated_at", now_iso())
    for initiative in g.get("initiatives", []):
        initiative.setdefault("started_month", 0)
        initiative.setdefault("elapsed_months", 0)
        initiative.setdefault("last_action", "")
    for comp in g.get("competitors", []):
        comp.setdefault("initiatives", [])
        comp.setdefault("market_cap", market_cap(comp.get("cash", 0), comp.get("revenue", 0), comp.get("revenue_multiple", DEFAULT_REVENUE_MULTIPLE)))
        for initiative in comp.get("initiatives", []):
            initiative.setdefault("started_month", 0)
            initiative.setdefault("elapsed_months", 0)
            initiative.setdefault("last_action", "")
    if g.get("history") and not memory.get("competitors"):
        rebuild_competitor_memory_from_history(g)
    return g


def load_games() -> dict[str, dict[str, Any]]:
    if not STORE_PATH.exists():
        return {}
    try:
        raw = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    stored = raw.get("games", raw) if isinstance(raw, dict) else {}
    if not isinstance(stored, dict):
        return {}
    return {str(game_id): ensure_game_shape(game) for game_id, game in stored.items() if isinstance(game, dict)}


def save_games() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = STORE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps({"games": games}, indent=2), encoding="utf-8")
    tmp_path.replace(STORE_PATH)


def telemetry_summary(g: dict[str, Any]) -> dict[str, Any]:
    calls = g.get("llm_calls", [])
    prompt_tokens = sum(int(c.get("prompt_tokens", 0) or 0) for c in calls)
    cached_tokens = sum(int(c.get("cached_tokens", 0) or 0) for c in calls)
    completion_tokens = sum(int(c.get("completion_tokens", 0) or 0) for c in calls)
    return {
        "call_count": len(calls),
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "completion_tokens": completion_tokens,
        "cache_hit_rate": round(cached_tokens / prompt_tokens, 4) if prompt_tokens else 0,
        "last_call": calls[-1] if calls else None,
    }


NAME_STOPWORDS = {
    "going",
    "launching",
    "building",
    "planning",
    "investing",
    "hiring",
    "cutting",
    "opening",
    "expanding",
    "buying",
    "selling",
    "testing",
}


def title_name(value: str) -> str:
    parts = [p for p in re.split(r"(\s+|-)", value.strip()) if p]
    return "".join(p if p.isspace() or p == "-" else p[:1].upper() + p[1:].lower() for p in parts)


def title_role(value: str) -> str:
    role = " ".join(value.strip().split())
    role = re.sub(r"\bceo\b", "CEO", role, flags=re.IGNORECASE)
    role = re.sub(r"\bcfo\b", "CFO", role, flags=re.IGNORECASE)
    role = re.sub(r"\bcto\b", "CTO", role, flags=re.IGNORECASE)
    return role


def remember_fact(g: dict[str, Any], key: str, value: str) -> None:
    ensure_game_shape(g)
    value = " ".join(value.strip().split())
    if not value:
        return
    g["memory"]["identity"][key] = value[:120]
    if key == "company_name":
        g["company_name"] = value[:80]
    g["memory"]["updated_at"] = now_iso()


def remember_canon(g: dict[str, Any], fact: str) -> None:
    ensure_game_shape(g)
    fact = " ".join(fact.strip().split())[:220]
    if not fact:
        return
    canon = [c for c in g["memory"].get("canon", []) if c != fact]
    canon.append(fact)
    g["memory"]["canon"] = canon[-18:]
    g["memory"]["updated_at"] = now_iso()


def remember_competitor_event(g: dict[str, Any], month: int, action: dict[str, Any]) -> None:
    name = str(action.get("name", "")).strip()
    summary = " ".join(str(action.get("action", "")).split())[:220]
    if not name or not summary:
        return
    memory = g.setdefault("memory", default_memory(g.get("company_name", "Pax Motors")))
    competitors = memory.setdefault("competitors", {})
    rival = competitors.setdefault(name, {"timeline": []})
    initiative = str(action.get("initiative", "") or action.get("continuing_initiative", "")).strip()
    status = str(action.get("initiative_status", "") or ("opened" if initiative else "acted"))
    entry = {
        "month": int(month),
        "status": status,
        "initiative": initiative,
        "summary": summary,
    }
    timeline = [
        e
        for e in rival.get("timeline", [])
        if not (int(e.get("month", 0)) == entry["month"] and e.get("summary") == entry["summary"])
    ]
    timeline.append(entry)
    rival["timeline"] = timeline[-COMPETITOR_MEMORY_LIMIT:]
    rival["last_seen_month"] = int(month)
    if initiative:
        rival["last_initiative"] = initiative
    memory["updated_at"] = now_iso()


def rebuild_competitor_memory_from_history(g: dict[str, Any]) -> None:
    memory = g.setdefault("memory", default_memory(g.get("company_name", "Pax Motors")))
    memory["competitors"] = {}
    for h in g.get("history", []):
        month = int(h.get("month", 0) or 0)
        for action in h.get("competitor_actions", []) or []:
            remember_competitor_event(g, month, action)


def extract_memory_from_text(g: dict[str, Any], text: str) -> list[dict[str, str]]:
    updates: list[dict[str, str]] = []
    normalized = " ".join(text.strip().split())
    if not normalized:
        return updates

    named = re.search(r"\b(?:my name is|call me)\s+([a-z][a-z'-]{1,30})\b", normalized, re.IGNORECASE)
    if named and named.group(1).lower() not in NAME_STOPWORDS:
        ceo_name = title_name(named.group(1))
        remember_fact(g, "ceo_name", ceo_name)
        updates.append({"key": "ceo_name", "value": ceo_name})

    intro = re.search(
        r"\b(?:i am|i'm|im)\s+([a-z][a-z'-]{1,30})(?:\s+(?:the\s+)?((?:new\s+)?(?:ceo|founder|chair|president|owner|operator|leader)[^.!?]{0,60}))?",
        normalized,
        re.IGNORECASE,
    )
    if intro and intro.group(1).lower() not in NAME_STOPWORDS:
        ceo_name = title_name(intro.group(1))
        remember_fact(g, "ceo_name", ceo_name)
        updates.append({"key": "ceo_name", "value": ceo_name})
        if intro.group(2):
            role = title_role(intro.group(2))
            company_match = re.search(r"\bof\s+([A-Za-z0-9][A-Za-z0-9 &.'-]{1,80})$", role)
            if company_match:
                remember_fact(g, "company_name", company_match.group(1).strip())
                updates.append({"key": "company_name", "value": company_match.group(1).strip()})
                role = role[: company_match.start()].strip()
            if role:
                remember_fact(g, "ceo_role", role)
                updates.append({"key": "ceo_role", "value": role})

    company = re.search(
        r"\b(?:my company is|our company is|company name is|we are called)\s+([A-Za-z0-9][A-Za-z0-9 &.'-]{1,80})",
        normalized,
        re.IGNORECASE,
    )
    if company:
        company_name = company.group(1).strip(" .")
        remember_fact(g, "company_name", company_name)
        updates.append({"key": "company_name", "value": company_name})

    if re.search(r"\b(?:remember|our strategy|our mission|we are known for|never forget)\b", normalized, re.IGNORECASE):
        remember_canon(g, f"M{g.get('month', 0) + 1} canon: {normalized}")
        updates.append({"key": "canon", "value": normalized[:120]})

    return updates


def memory_context(g: dict[str, Any]) -> dict[str, Any]:
    ensure_game_shape(g)
    identity = g["memory"].get("identity", {})
    recent = []
    for h in g.get("history", [])[-5:]:
        card = h.get("your_move") or {}
        label = card.get("title") or "Unlabeled event"
        recent.append(f"M{h.get('month')}: {label}")
    return {
        "identity": identity,
        "tone": g["memory"].get("tone"),
        "canon": g["memory"].get("canon", [])[-8:],
        "competitor_memory": competitor_memory_context(g),
        "recent_events": recent,
    }


def competitor_memory_context(g: dict[str, Any]) -> list[str]:
    memory = g.get("memory", {}).get("competitors", {})
    lines = []
    for name, rival in memory.items():
        for event in rival.get("timeline", [])[-3:]:
            initiative = event.get("initiative")
            label = f"{event.get('status', 'acted')} {initiative}" if initiative else event.get("status", "acted")
            lines.append(f"M{event.get('month')}: {name} {label}: {event.get('summary')}")
    return lines[-10:]


def public_state(g: dict[str, Any]) -> dict[str, Any]:
    ensure_game_shape(g)
    ranking = [
        {
            "name": g["company_name"],
            "cash": g["cash"],
            "revenue": g["revenue"],
            "market_cap": company_market_cap(g),
            "initiatives": len(g.get("initiatives", [])),
            "is_player": True,
        }
    ] + [
        {
            "name": c["name"],
            "cash": c["cash"],
            "revenue": c["revenue"],
            "market_cap": company_market_cap(c),
            "initiatives": len(c.get("initiatives", [])),
            "is_player": False,
        }
        for c in g["competitors"]
    ]
    leaderboard = sorted(
        ranking,
        key=lambda r: r["market_cap"],
        reverse=True,
    )
    return {
        "id": g["id"],
        "company_name": g["company_name"],
        "month": g["month"],
        "cash": g["cash"],
        "revenue": g["revenue"],
        "market_cap": company_market_cap(g),
        "actions": list(g["actions"]),
        "initiatives": [dict(i) for i in g["initiatives"]],
        "competitors": [dict(c) for c in g["competitors"]],
        "history": list(g["history"]),
        "leaderboard": leaderboard,
        "memory": dict(g.get("memory", {})),
        "telemetry": telemetry_summary(g),
    }


def _parse_tool_args(raw: dict, tool_name: str) -> dict:
    msg = (raw.get("choices") or [{}])[0].get("message") or {}
    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        args = tool_calls[0].get("function", {}).get("arguments")
        return json.loads(args) if isinstance(args, str) else (args or {})
    content = msg.get("content") or ""
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    s, e = content.find("{"), content.rfind("}")
    if s == -1 or e <= s:
        raise HTTPException(status_code=502, detail=f"LLM returned no parsable JSON for {tool_name}")
    return json.loads(content[s : e + 1])


async def _call_llm(
    client: httpx.AsyncClient,
    messages: list[dict],
    tool: dict,
    *,
    max_tokens: int,
    call_type: str,
    game: dict[str, Any] | None = None,
) -> dict:
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not set")
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    schema = tool["function"]["parameters"]
    started = time.perf_counter()
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
        "reasoning": {"effort": "none"},
        "provider": {
            "sort": "latency",
            "preferred_max_latency": {"p90": 3},
            "require_parameters": True,
        },
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": tool["function"]["name"],
                "strict": True,
                "schema": schema,
            },
        },
    }
    resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
    used_retry = False
    if not resp.is_success:
        used_retry = True
        retry = {
            **payload,
            "response_format": {"type": "json_object"},
            "messages": messages
            + [{"role": "user", "content": f"Return ONLY a JSON object matching the {tool['function']['name']} schema. No prose, no code fences."}],
        }
        resp = await client.post(OPENROUTER_URL, headers=headers, json=retry)
        if not resp.is_success:
            raise HTTPException(status_code=502, detail=f"LLM error {resp.status_code}: {resp.text[:200]}")
    raw = resp.json()
    if game is not None:
        usage = raw.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        cached_tokens = int(details.get("cached_tokens", 0) or 0)
        telemetry = {
            "ts": now_iso(),
            "call_type": call_type,
            "model": raw.get("model") or MODEL,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
            "cached_tokens": cached_tokens,
            "cache_write_tokens": int(details.get("cache_write_tokens", 0) or 0),
            "cache_hit_rate": round(cached_tokens / prompt_tokens, 4) if prompt_tokens else 0,
            "retry": used_retry,
        }
        game.setdefault("llm_calls", []).append(telemetry)
    return _parse_tool_args(raw, tool["function"]["name"])


async def resolve_player(client: httpx.AsyncClient, g: dict[str, Any], competitor_results: list[dict]) -> dict:
    history_lines = [f"M{h['month']}: {h['your_move']['title']}" for h in g["history"][-3:]]
    payload = {
        "company_name": g["company_name"],
        "month": g["month"] + 1,
        "cash": g["cash"],
        "revenue_per_month": g["revenue"],
        "market_cap": company_market_cap(g),
        "competitors": [
            {
                "name": c["name"],
                "cash": c["cash"],
                "revenue": c["revenue"],
                "market_cap": company_market_cap(c),
                "active_initiatives": [
                    {
                        "name": i["name"],
                        "started_month": i.get("started_month"),
                        "remaining_months": i.get("remaining_months"),
                        "elapsed_months": i.get("elapsed_months", 0),
                        "last_action": i.get("last_action", ""),
                    }
                    for i in c.get("initiatives", [])
                ],
            }
            for c in g["competitors"]
        ],
        "competitor_actions_this_month": [
            {
                "name": r["name"],
                "action": r["action"],
                "initiative": r.get("initiative") or (r.get("initiative_update") or {}).get("name", ""),
                "initiative_status": r.get("initiative_status", ""),
            }
            for r in competitor_results
        ],
        "active_initiatives": g["initiatives"],
        "memory": memory_context(g),
        "recent_history": history_lines,
        "actions_this_month": g["actions"] or ["(no actions)"],
    }
    return await _call_llm(
        client,
        [
            {"role": "system", "content": PLAYER_SYSTEM},
            {"role": "user", "content": f"{json.dumps(payload, separators=(',', ':'))}\n\nReturn resolve_player JSON."},
        ],
        PLAYER_TOOL,
        max_tokens=520,
        call_type="resolve_player",
        game=g,
    )


async def resolve_competitor(client: httpx.AsyncClient, g: dict[str, Any], comp: dict) -> dict:
    payload = {
        "you": {"name": comp["name"], "cash": comp["cash"], "revenue": comp["revenue"]},
        "player": {"name": g["company_name"], "cash": g["cash"], "revenue": g["revenue"]},
        "player_actions_this_month": g["actions"] or ["(no actions)"],
    }
    return await _call_llm(
        client,
        [
            {"role": "system", "content": COMPETITOR_SYSTEM},
            {"role": "user", "content": f"{json.dumps(payload, indent=2)}\n\nCall resolve_competitor."},
        ],
        COMPETITOR_TOOL,
        max_tokens=200,
        call_type="resolve_competitor",
    )


def _section(value: Any) -> dict:
    if isinstance(value, dict):
        source = str(value.get("source", ""))[:80]
        title = str(value.get("title", value.get("headline", "")))[:90]
        body = str(value.get("body", ""))[:420]
        return {"source": source, "title": title, "body": body}
    if isinstance(value, str):
        text = " ".join(value.split())
        for sep in (":", " - ", " -- "):
            if sep in text:
                title, body = text.split(sep, 1)
                source = ""
                if "|" in title:
                    source, title = title.split("|", 1)
                return {"source": source.strip()[:80], "title": title.strip()[:90], "body": body.strip()[:420]}
        words = text.split()
        return {"source": "", "title": " ".join(words[:6])[:90], "body": text[:420]}
    return {"source": "", "title": "", "body": ""}


def _stable_rng(*parts: str) -> random.Random:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def resolve_competitors_locally(g: dict[str, Any]) -> list[dict]:
    actions = [
        ("Fleet Defense", "{name} launched a fleet-defense pricing program to protect commercial buyers.", -0.025, 0.018, -0.0015, 3),
        ("Trust Campaign", "{name} opened a trust campaign around range anxiety and service reliability.", -0.018, 0.01, 0.001, 4),
        ("Dealer Push", "{name} signed a regional dealer incentive program.", -0.02, 0.014, 0.0008, 3),
        ("Launch Delay", "{name} delayed a costly launch and preserved cash.", 0.012, -0.006, -0.001, 2),
        ("Charging Bundle", "{name} bundled charging credits into a new EV lease program.", -0.022, 0.02, 0.0012, 4),
        ("Supplier Squeeze", "{name} pushed supplier terms to protect gross margin.", 0.01, -0.003, -0.0005, 3),
        ("Battery Supplier Acquisition", "{name} moved to acquire a distressed battery-controls supplier.", -0.04, 0.028, 0.0016, 6),
        ("Autonomy Launch Program", "{name} launched an autonomy software program for fleet customers.", -0.035, 0.024, 0.002, 5),
        ("Factory Conversion", "{name} started converting an older plant for lower-cost EV production.", -0.045, 0.03, 0.0014, 7),
    ]
    continuations = [
        "{name}'s {initiative} moved from announcement into supplier contracts.",
        "{name} kept {initiative} alive with a second operating milestone.",
        "{name} expanded {initiative} after early market feedback.",
        "{name}'s finance team doubled down on {initiative} instead of letting it fade.",
        "{name} hit a visible checkpoint on {initiative}, forcing rivals to account for it.",
    ]
    month = str(g["month"] + 1)
    action_plan = " | ".join(g["actions"] or ["no actions"])
    count = min(ACTIVE_COMPETITOR_ACTIONS_PER_MONTH, len(g["competitors"]))
    selection_rng = _stable_rng(g["id"], month, "active-competitors", action_plan)
    active_names = {
        comp["name"] for comp in selection_rng.sample(g["competitors"], k=count)
    }
    results = []
    for comp in g["competitors"]:
        if comp["name"] not in active_names:
            continue
        rng = _stable_rng(g["id"], month, comp["name"], action_plan)
        cash_delta = round(rng.uniform(-0.65, 0.85) * comp["revenue"] - rng.uniform(8_000, 28_000), 2)
        revenue_delta = round(rng.uniform(-0.08, 0.11) * comp["revenue"], 2)
        revenue_multiple = float(comp.get("revenue_multiple", DEFAULT_REVENUE_MULTIPLE))
        market_cap_delta = round(cash_delta * MARKET_CAP_CASH_WEIGHT + revenue_delta * 12 * revenue_multiple, 2)
        active_initiatives = [i for i in comp.get("initiatives", []) if int(i.get("remaining_months", 0)) > 0]
        if active_initiatives:
            initiative = rng.choice(active_initiatives)
            initiative_name = str(initiative.get("name", "Rival Program"))
            text = rng.choice(continuations).format(name=comp["name"], initiative=initiative_name)
            results.append(
                {
                    "name": comp["name"],
                    "action": text,
                    "cash_delta": cash_delta,
                    "revenue_delta": revenue_delta,
                    "market_cap_delta": market_cap_delta,
                    "initiative": initiative_name,
                    "initiative_status": "continued",
                }
            )
            initiative["last_action"] = text
            continue
        initiative_name, text, cash_rate, revenue_rate, market_cap_rate, duration = rng.choice(actions)
        action = text.format(name=comp["name"])
        results.append(
            {
                "name": comp["name"],
                "action": action,
                "cash_delta": cash_delta,
                "revenue_delta": revenue_delta,
                "market_cap_delta": market_cap_delta,
                "initiative": initiative_name,
                "initiative_status": "opened",
                "initiative_update": {
                    "name": initiative_name,
                    "monthly_cash_delta": round(cash_rate * comp["revenue"], 2),
                    "monthly_revenue_delta": round(revenue_rate * comp["revenue"], 2),
                    "monthly_market_cap_delta": round(market_cap_rate * company_market_cap(comp), 2),
                    "duration_months": duration,
                    "last_action": action,
                },
            }
        )
    return results


def apply_entity_initiatives(entity: dict[str, Any]) -> dict[str, Any]:
    effect = {"cash_delta": 0.0, "revenue_delta": 0.0, "market_cap_delta": 0.0, "names": []}
    active = []
    for initiative in entity.get("initiatives", []):
        effect["cash_delta"] += float(initiative.get("monthly_cash_delta", 0))
        effect["revenue_delta"] += float(initiative.get("monthly_revenue_delta", 0))
        effect["market_cap_delta"] += float(initiative.get("monthly_market_cap_delta", 0))
        effect["names"].append(initiative["name"])
        initiative["elapsed_months"] = int(initiative.get("elapsed_months", 0)) + 1
        initiative["remaining_months"] = int(initiative.get("remaining_months", 0)) - 1
        if initiative["remaining_months"] > 0:
            active.append(initiative)
    entity["initiatives"] = active
    entity["cash"] += effect["cash_delta"]
    entity["revenue"] = max(0.0, entity["revenue"] + effect["revenue_delta"])
    entity["market_cap"] = max(0.0, company_market_cap(entity) + effect["market_cap_delta"])
    return effect


def apply_active_initiatives(g: dict[str, Any]) -> dict[str, Any]:
    return apply_entity_initiatives(g)


def apply_competitor_initiatives(g: dict[str, Any]) -> dict[str, dict[str, Any]]:
    effects = {}
    for comp in g["competitors"]:
        effect = apply_entity_initiatives(comp)
        if effect["names"]:
            effects[comp["name"]] = effect
    return effects


def upsert_initiatives(entity: dict[str, Any], updates: list[dict], *, current_month: int = 0) -> None:
    by_name = {i["name"].lower(): i for i in entity.get("initiatives", [])}
    for raw in updates[:3]:
        name = str(raw.get("name", "")).strip()[:60]
        if not name:
            continue
        existing = by_name.get(name.lower(), {})
        initiative = {
            "name": name,
            "monthly_cash_delta": float(raw.get("monthly_cash_delta", 0)),
            "monthly_revenue_delta": float(raw.get("monthly_revenue_delta", 0)),
            "monthly_market_cap_delta": float(raw.get("monthly_market_cap_delta", 0)),
            "remaining_months": max(1, min(36, int(raw.get("duration_months", 1)))),
            "started_month": int(raw.get("started_month") or existing.get("started_month") or current_month or 0),
            "elapsed_months": int(existing.get("elapsed_months", 0)),
            "last_action": str(raw.get("last_action") or existing.get("last_action") or "")[:220],
        }
        by_name[name.lower()] = initiative
    entity["initiatives"] = list(by_name.values())


def ceo_address(g: dict[str, Any]) -> str:
    ceo = g.get("memory", {}).get("identity", {}).get("ceo_name")
    return f"{ceo}, " if ceo else ""


def quiet_player_result(g: dict[str, Any], initiative_effect: dict, competitor_results: list[dict]) -> dict[str, Any]:
    if initiative_effect["names"]:
        names = ", ".join(initiative_effect["names"])
        your_move = (
            "CEO Office | EXISTING PROGRAMS KEEP RUNNING: "
            f"{ceo_address(g)}no new order crossed the desk this month. {names} kept moving through finance and operations, "
            "so the company still felt the weight of earlier commitments."
        )
    else:
        your_move = (
            "CEO Office | HOLDING PATTERN: "
            f"{ceo_address(g)}no new CEO order was issued, so {g['company_name']} held its current course. "
            "The absence of a fresh move gave rivals and customers a quiet month to reassess the company."
        )

    spotlight = competitor_results[0] if competitor_results else {"name": "Competitors", "action": "Competitors held position."}
    return {
        "your_move": your_move,
        "competitor_spotlight": f"{spotlight['name']} Strategy Desk | RIVAL MOVE RECORDED: {spotlight['action']}",
        "market": (
            "Reuters EV Desk | MARKET KEEPS MOVING: Fleet buyers, suppliers, and investors kept adjusting around the company. "
            "The month produced no single shock, but the competitive field did not pause."
        ),
        "cash_delta": 0,
        "revenue_delta": 0,
        "market_cap_delta": 0,
        "initiative_updates": [],
    }


def normalize_player_result(g: dict[str, Any], player_result: dict[str, Any]) -> dict[str, Any]:
    if not g["actions"]:
        return player_result

    cash_delta = float(player_result.get("cash_delta", 0) or 0)
    revenue_delta = float(player_result.get("revenue_delta", 0) or 0)
    market_cap_delta = float(player_result.get("market_cap_delta", 0) or 0)
    if abs(cash_delta) + abs(revenue_delta) + abs(market_cap_delta) >= 1:
        return player_result

    action_plan = " ".join(g["actions"]).lower()
    is_deep_tech = any(word in action_plan for word in ("agi", "robot", "robotics", "automation", "autonomy", "ai", "r&d"))
    initiative_name = "Robotics R&D" if "robot" in action_plan else "Strategic Initiative"
    spend = 200_000 if is_deep_tech else 60_000
    value_delta = 500_000 if is_deep_tech else 120_000

    updates = list(player_result.get("initiative_updates") or [])
    if updates:
        first = updates[0]
        initiative_name = str(first.get("name") or initiative_name)[:60]
        spend = abs(float(first.get("monthly_cash_delta", 0) or -spend)) or spend
        value_delta = abs(float(first.get("monthly_market_cap_delta", 0) or value_delta)) or value_delta
    elif is_deep_tech:
        updates.append(
            {
                "name": initiative_name,
                "monthly_cash_delta": -150_000,
                "monthly_revenue_delta": 0,
                "monthly_market_cap_delta": 250_000,
                "duration_months": 6,
            }
        )

    return {
        **player_result,
        "your_move": (
            f"Board of Directors | {initiative_name.upper()} AUTHORIZED: "
            f"{ceo_address(g)}the board treated the order as a real operating program, not a slogan. "
            "Finance booked the spend immediately while investors credited the company for choosing a sharper lane."
        ),
        "cash_delta": -spend,
        "revenue_delta": 0,
        "market_cap_delta": value_delta,
        "initiative_updates": updates,
    }


def apply_resolution(
    g: dict[str, Any],
    player_result: dict,
    competitor_results: list[dict],
    initiative_effect: dict,
    competitor_initiative_effects: dict[str, dict[str, Any]],
) -> None:
    g["cash"] += float(player_result.get("cash_delta", 0))
    g["revenue"] = max(0.0, g["revenue"] + float(player_result.get("revenue_delta", 0)))
    g["market_cap"] = max(0.0, company_market_cap(g) + float(player_result.get("market_cap_delta", 0)))
    resolution_month = int(g.get("month", 0)) + 1
    upsert_initiatives(g, player_result.get("initiative_updates") or [], current_month=resolution_month)
    player_cash_delta = float(player_result.get("cash_delta", 0))
    player_revenue_delta = float(player_result.get("revenue_delta", 0))
    player_market_cap_delta = float(player_result.get("market_cap_delta", 0))
    player_total_cash_delta = player_cash_delta + float(initiative_effect.get("cash_delta", 0))
    player_total_revenue_delta = player_revenue_delta + float(initiative_effect.get("revenue_delta", 0))
    player_total_market_cap_delta = player_market_cap_delta + float(initiative_effect.get("market_cap_delta", 0))
    competitors_by_name = {comp["name"]: comp for comp in g["competitors"]}
    competitor_actions = []
    for result in competitor_results:
        comp = competitors_by_name.get(result.get("name"))
        if not comp:
            continue
        comp["cash"] += float(result.get("cash_delta", 0))
        comp["revenue"] = max(0.0, comp["revenue"] + float(result.get("revenue_delta", 0)))
        if "market_cap" in comp:
            comp["market_cap"] = max(0.0, comp["market_cap"] + float(result.get("market_cap_delta", 0)))
        initiative = result.get("initiative_update") or {}
        upsert_initiatives(comp, [initiative] if initiative else [], current_month=resolution_month)
        initiative_name = str(result.get("initiative") or initiative.get("name", "") or "")
        initiative_status = str(result.get("initiative_status") or ("opened" if initiative_name else ""))
        competitor_actions.append(
            {
                "name": comp["name"],
                "action": result.get("action", ""),
                "initiative": initiative_name,
                "initiative_status": initiative_status,
                "cash_delta": float(result.get("cash_delta", 0)),
                "revenue_delta": float(result.get("revenue_delta", 0)),
                "market_cap_delta": float(result.get("market_cap_delta", 0)),
                "recurring_effect": competitor_initiative_effects.get(comp["name"]),
            }
        )
    g["month"] += 1
    history_entry = {
        "month": g["month"],
        "your_move": _section(player_result.get("your_move")),
        "competitor_spotlight": _section(player_result.get("competitor_spotlight")),
        "market": _section(player_result.get("market")),
        "actions": list(g["actions"]),
        "competitor_actions": competitor_actions,
        "competitor_initiative_effects": competitor_initiative_effects,
        "initiative_effect": initiative_effect,
        "active_initiatives": [dict(i) for i in g["initiatives"]],
        "player_cash_delta": player_cash_delta,
        "player_revenue_delta": player_revenue_delta,
        "player_market_cap_delta": player_market_cap_delta,
        "player_total_cash_delta": player_total_cash_delta,
        "player_total_revenue_delta": player_total_revenue_delta,
        "player_total_market_cap_delta": player_total_market_cap_delta,
    }
    g["history"].append(history_entry)
    for action in history_entry["actions"]:
        remember_canon(g, f"M{g['month']} CEO order: {action}")
    if history_entry["your_move"].get("title"):
        remember_canon(g, f"M{g['month']} outcome: {history_entry['your_move']['title']}")
    for action in competitor_actions:
        remember_competitor_event(g, g["month"], action)
    g["actions"] = []


games.update(load_games())


app = FastAPI(title="Pax Venture")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/game")
def create_game(body: NewGameBody) -> dict[str, Any]:
    g = new_game_state(body.company_name.strip() or "Pax Motors", body.ceo_name or "")
    games[g["id"]] = g
    save_games()
    return public_state(g)


@app.get("/api/game/{game_id}")
def get_game(game_id: str) -> dict[str, Any]:
    g = games.get(game_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    return public_state(g)


@app.post("/api/game/{game_id}/action")
def add_action(game_id: str, body: ActionBody) -> dict[str, Any]:
    g = games.get(game_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Action text required")
    if len(text) > 600:
        raise HTTPException(status_code=400, detail="Action too long")
    extract_memory_from_text(g, text)
    g["actions"].append(text)
    save_games()
    return public_state(g)


@app.delete("/api/game/{game_id}/action/{index}")
def remove_action(game_id: str, index: int) -> dict[str, Any]:
    g = games.get(game_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    if 0 <= index < len(g["actions"]):
        g["actions"].pop(index)
        save_games()
    return public_state(g)


@app.post("/api/game/{game_id}/simulate")
async def simulate(game_id: str) -> dict[str, Any]:
    g = games.get(game_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    started = time.perf_counter()
    has_player_actions = bool(g["actions"])
    timeout = httpx.Timeout(60.0, connect=10.0)
    limits = httpx.Limits(max_connections=12, max_keepalive_connections=12)
    initiative_effect = apply_active_initiatives(g)
    competitor_initiative_effects = apply_competitor_initiatives(g)
    competitor_results = resolve_competitors_locally(g)
    if has_player_actions:
        async with httpx.AsyncClient(timeout=timeout, limits=limits, http2=False) as client:
            player_result = await resolve_player(client, g, competitor_results)
        player_result = normalize_player_result(g, player_result)
    else:
        player_result = quiet_player_result(g, initiative_effect, competitor_results)
    apply_resolution(g, player_result, competitor_results, initiative_effect, competitor_initiative_effects)
    save_games()
    return {**public_state(g), "latency_ms": int((time.perf_counter() - started) * 1000)}
