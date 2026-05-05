import hashlib
import json
import os
import random
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

STARTING_CASH = 1_000_000
STARTING_REVENUE = 50_000
COMPETITORS = [
    {"name": "AutoVista", "cash": 1_200_000, "revenue": 80_000},
    {"name": "NovaTech", "cash": 950_000, "revenue": 65_000},
    {"name": "GreenWheel", "cash": 700_000, "revenue": 45_000},
    {"name": "Iron Motors", "cash": 1_100_000, "revenue": 70_000},
    {"name": "Voltcar", "cash": 800_000, "revenue": 55_000},
]

_SECTION = {
    "type": "string",
    "maxLength": 320,
    "description": "One compact section formatted as 'Short title: 1-2 tight sentences.'",
}

PLAYER_TOOL = {
    "type": "function",
    "function": {
        "name": "resolve_player",
        "description": "Resolve the player's month as three short titled sections plus financial impact.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["your_move", "competitor_spotlight", "market", "cash_delta", "revenue_delta"],
            "properties": {
                "your_move": _SECTION,
                "competitor_spotlight": _SECTION,
                "market": _SECTION,
                "cash_delta": {"type": "number"},
                "revenue_delta": {"type": "number"},
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
    "You are the engine of a CEO simulation in the EV automotive industry. Resolve ONE month for the player.\n\n"
    "Respond as THREE compact titled strings. Each field must be formatted exactly as 'Title: body'. "
    "Titles are punchy and short; bodies are 1-2 short sentences with no filler:\n"
    "1. your_move - outcome of the player's actions this month and the financial impact.\n"
    "2. competitor_spotlight - pick ONE competitor whose move mattered most this month and tell that story by name.\n"
    "3. market - broader industry signal, customer behavior, or external pressure this month.\n\n"
    "Use grounded monthly magnitudes (tens of thousands for modest deals; hundreds of thousands for major launches). "
    "Cash delta is net of operating costs (baseline burn roughly equals revenue unless the player did something costly or revenue-generating). "
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


class ActionBody(BaseModel):
    text: str


def new_game_state(company_name: str) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:12],
        "company_name": company_name,
        "month": 0,
        "cash": STARTING_CASH,
        "revenue": STARTING_REVENUE,
        "actions": [],
        "competitors": [dict(c) for c in COMPETITORS],
        "history": [],
    }


def public_state(g: dict[str, Any]) -> dict[str, Any]:
    leaderboard = sorted(
        [{"name": g["company_name"], "cash": g["cash"], "revenue": g["revenue"], "is_player": True}]
        + [{"name": c["name"], "cash": c["cash"], "revenue": c["revenue"], "is_player": False} for c in g["competitors"]],
        key=lambda r: r["cash"],
        reverse=True,
    )
    return {
        "id": g["id"],
        "company_name": g["company_name"],
        "month": g["month"],
        "cash": g["cash"],
        "revenue": g["revenue"],
        "actions": list(g["actions"]),
        "competitors": [dict(c) for c in g["competitors"]],
        "history": list(g["history"]),
        "leaderboard": leaderboard,
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


async def _call_llm(client: httpx.AsyncClient, messages: list[dict], tool: dict, *, max_tokens: int) -> dict:
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not set")
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    schema = tool["function"]["parameters"]
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
    if not resp.is_success:
        retry = {
            **payload,
            "response_format": {"type": "json_object"},
            "messages": messages
            + [{"role": "user", "content": f"Return ONLY a JSON object matching the {tool['function']['name']} schema. No prose, no code fences."}],
        }
        resp = await client.post(OPENROUTER_URL, headers=headers, json=retry)
        if not resp.is_success:
            raise HTTPException(status_code=502, detail=f"LLM error {resp.status_code}: {resp.text[:200]}")
    return _parse_tool_args(resp.json(), tool["function"]["name"])


async def resolve_player(client: httpx.AsyncClient, g: dict[str, Any]) -> dict:
    history_lines = [f"M{h['month']}: {h['your_move']['title']}" for h in g["history"][-2:]]
    payload = {
        "company_name": g["company_name"],
        "month": g["month"] + 1,
        "cash": g["cash"],
        "revenue_per_month": g["revenue"],
        "competitors": [{"name": c["name"], "cash": c["cash"], "revenue": c["revenue"]} for c in g["competitors"]],
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
        max_tokens=280,
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
    )


def _section(value: Any) -> dict:
    if isinstance(value, dict):
        return {"title": str(value.get("title", ""))[:60], "body": str(value.get("body", ""))[:240]}
    if isinstance(value, str):
        text = " ".join(value.split())
        for sep in (":", " - ", " -- "):
            if sep in text:
                title, body = text.split(sep, 1)
                return {"title": title.strip()[:60], "body": body.strip()[:240]}
        words = text.split()
        return {"title": " ".join(words[:4])[:60], "body": text[:240]}
    return {"title": "", "body": ""}


def _stable_rng(*parts: str) -> random.Random:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def resolve_competitors_locally(g: dict[str, Any]) -> list[dict]:
    actions = [
        "{name} discounted commercial trims to defend fleet buyers.",
        "{name} shifted ad spend toward range anxiety and service reliability.",
        "{name} signed a regional dealer incentive package.",
        "{name} delayed a costly launch and preserved cash.",
        "{name} bundled charging credits into new EV leases.",
        "{name} pushed supplier terms to protect gross margin.",
    ]
    month = str(g["month"] + 1)
    action_plan = " | ".join(g["actions"] or ["no actions"])
    results = []
    for comp in g["competitors"]:
        rng = _stable_rng(g["id"], month, comp["name"], action_plan)
        cash_delta = round(rng.uniform(-0.65, 0.85) * comp["revenue"] - rng.uniform(8_000, 28_000), 2)
        revenue_delta = round(rng.uniform(-0.08, 0.11) * comp["revenue"], 2)
        results.append(
            {
                "action": rng.choice(actions).format(name=comp["name"]),
                "cash_delta": cash_delta,
                "revenue_delta": revenue_delta,
            }
        )
    return results


def apply_resolution(g: dict[str, Any], player_result: dict, competitor_results: list[dict]) -> None:
    g["cash"] += float(player_result.get("cash_delta", 0))
    g["revenue"] += float(player_result.get("revenue_delta", 0))
    competitor_actions = []
    for comp, result in zip(g["competitors"], competitor_results):
        comp["cash"] += float(result.get("cash_delta", 0))
        comp["revenue"] += float(result.get("revenue_delta", 0))
        competitor_actions.append({"name": comp["name"], "action": result.get("action", "")})
    g["month"] += 1
    g["history"].append(
        {
            "month": g["month"],
            "your_move": _section(player_result.get("your_move")),
            "competitor_spotlight": _section(player_result.get("competitor_spotlight")),
            "market": _section(player_result.get("market")),
            "actions": list(g["actions"]),
            "competitor_actions": competitor_actions,
            "player_cash_delta": float(player_result.get("cash_delta", 0)),
            "player_revenue_delta": float(player_result.get("revenue_delta", 0)),
        }
    )
    g["actions"] = []


app = FastAPI(title="Pax Venture")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/game")
def create_game(body: NewGameBody) -> dict[str, Any]:
    g = new_game_state(body.company_name.strip() or "Pax Motors")
    games[g["id"]] = g
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
    g["actions"].append(text)
    return public_state(g)


@app.delete("/api/game/{game_id}/action/{index}")
def remove_action(game_id: str, index: int) -> dict[str, Any]:
    g = games.get(game_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    if 0 <= index < len(g["actions"]):
        g["actions"].pop(index)
    return public_state(g)


@app.post("/api/game/{game_id}/simulate")
async def simulate(game_id: str) -> dict[str, Any]:
    g = games.get(game_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    started = time.perf_counter()
    timeout = httpx.Timeout(60.0, connect=10.0)
    limits = httpx.Limits(max_connections=12, max_keepalive_connections=12)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, http2=False) as client:
        player_result = await resolve_player(client, g)
    apply_resolution(g, player_result, resolve_competitors_locally(g))
    return {**public_state(g), "latency_ms": int((time.perf_counter() - started) * 1000)}
