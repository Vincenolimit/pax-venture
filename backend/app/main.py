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
MAX_INITIATIVE_MONTHS = 120
MAX_CASH_DELTA = 5_000_000
MAX_REVENUE_DELTA = 5_000_000
MAX_MARKET_CAP_DELTA = 25_000_000
MEMORY_LIST_LIMIT = 8
INBOX_LIMIT = 4
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

COMPETITOR_ACTIONS = [
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

COMPETITOR_CONTINUATIONS = [
    "{name}'s {initiative} moved from announcement into supplier contracts.",
    "{name} kept {initiative} alive with a second operating milestone.",
    "{name} expanded {initiative} after early market feedback.",
    "{name}'s finance team doubled down on {initiative} instead of letting it fade.",
    "{name} hit a visible checkpoint on {initiative}, forcing rivals to account for it.",
]

STRATEGIC_ACTION_BLUEPRINTS = [
    {
        "category": "robotics",
        "keywords": ("robot", "robotics", "automation", "automate", "factory robot", "industrial robot"),
        "name": "Robotics Platform",
        "horizon_months": 120,
        "phase": "charter",
        "thesis": "Build a decade-scale robotics capability that compounds through factory automation, autonomy talent, and lower production variance.",
        "cash_floor": 40_000,
        "cash_ceiling": 180_000,
        "cash_rate": 0.018,
        "revenue_rate": 0.6,
        "market_cap_rate": 0.004,
        "milestones": [
            {"month": 1, "label": "Robotics charter funded"},
            {"month": 3, "label": "Core robotics team hired"},
            {"month": 6, "label": "Prototype automation cell running"},
            {"month": 12, "label": "Pilot line robotics integrated"},
            {"month": 24, "label": "Manufacturing learning loop visible"},
            {"month": 60, "label": "Robotics capability becomes a cost moat"},
            {"month": 120, "label": "Ten-year robotics thesis matures"},
        ],
    },
    {
        "category": "autonomy",
        "keywords": ("autonomy", "autonomous", "self driving", "self-driving", "ai", "agi", "ai driver", "adas", "r&d"),
        "name": "Autonomy Software Platform",
        "horizon_months": 96,
        "phase": "research",
        "thesis": "Turn autonomy from a feature bet into a software platform with data, safety validation, and fleet-learning loops.",
        "cash_floor": 35_000,
        "cash_ceiling": 160_000,
        "cash_rate": 0.016,
        "revenue_rate": 0.45,
        "market_cap_rate": 0.0035,
        "milestones": [
            {"month": 1, "label": "Autonomy roadmap locked"},
            {"month": 4, "label": "Safety validation pod staffed"},
            {"month": 9, "label": "Fleet data pipeline online"},
            {"month": 18, "label": "Driver-assist pilot shipped"},
            {"month": 48, "label": "Software margin starts compounding"},
            {"month": 96, "label": "Autonomy platform reaches maturity"},
        ],
    },
    {
        "category": "manufacturing",
        "keywords": ("new factory", "factory build", "build factory", "manufacturing", "plant", "production line", "gigafactory", "assembly line"),
        "name": "Manufacturing Scale Program",
        "horizon_months": 60,
        "phase": "planning",
        "thesis": "Create a durable manufacturing advantage through plant design, supplier coordination, and process learning.",
        "cash_floor": 45_000,
        "cash_ceiling": 220_000,
        "cash_rate": 0.02,
        "revenue_rate": 0.8,
        "market_cap_rate": 0.003,
        "milestones": [
            {"month": 1, "label": "Manufacturing plan approved"},
            {"month": 3, "label": "Supplier map rebuilt"},
            {"month": 9, "label": "Pilot capacity unlocked"},
            {"month": 18, "label": "Unit economics improve"},
            {"month": 36, "label": "Scale playbook becomes repeatable"},
            {"month": 60, "label": "Manufacturing program matures"},
        ],
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
        "kind": {"type": "string", "maxLength": 40},
        "category": {"type": "string", "maxLength": 40},
        "phase": {"type": "string", "maxLength": 60},
        "thesis": {"type": "string", "maxLength": 220},
        "horizon_months": {"type": "integer", "minimum": 1, "maximum": MAX_INITIATIVE_MONTHS},
        "monthly_cash_delta": {"type": "number"},
        "monthly_revenue_delta": {"type": "number"},
        "monthly_market_cap_delta": {"type": "number"},
        "duration_months": {"type": "integer", "minimum": 1, "maximum": MAX_INITIATIVE_MONTHS},
        "milestones": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["month", "label"],
                "properties": {
                    "month": {"type": "integer", "minimum": 1, "maximum": MAX_INITIATIVE_MONTHS},
                    "label": {"type": "string", "maxLength": 80},
                },
            },
        },
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

_EVENT_CARD_OBJECT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["source", "title", "body"],
    "properties": {
        "source": {"type": "string", "maxLength": 80},
        "title": {"type": "string", "maxLength": 90},
        "body": {"type": "string", "maxLength": 420},
        "severity": {"type": "string", "maxLength": 40},
    },
}

_INBOX_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sender", "subject", "body"],
    "properties": {
        "sender": {"type": "string", "maxLength": 60},
        "subject": {"type": "string", "maxLength": 90},
        "body": {"type": "string", "maxLength": 360},
        "category": {"type": "string", "maxLength": 40},
    },
}

_MEMORY_PATCH = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "facts": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "value"],
                "properties": {
                    "key": {"type": "string", "maxLength": 60},
                    "value": {"type": "string", "maxLength": 160},
                },
            },
        },
        "threads": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "summary"],
                "properties": {
                    "label": {"type": "string", "maxLength": 60},
                    "summary": {"type": "string", "maxLength": 220},
                    "status": {"type": "string", "maxLength": 40},
                },
            },
        },
        "competitors": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "summary"],
                "properties": {
                    "name": {"type": "string", "maxLength": 80},
                    "summary": {"type": "string", "maxLength": 220},
                },
            },
        },
        "world": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["summary"],
                "properties": {"summary": {"type": "string", "maxLength": 220}},
            },
        },
        "summary": {"type": "string", "maxLength": 220},
    },
}

MONTH_TOOL = {
    "type": "function",
    "function": {
        "name": "resolve_month",
        "description": "Resolve one monthly CEO decision as the full game engine: player result, rivals, world, inbox, memory, and numeric effects.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "your_move",
                "competitor_events",
                "world_events",
                "cash_delta",
                "revenue_delta",
                "market_cap_delta",
                "initiative_updates",
                "next_inbox",
                "memory_patch",
            ],
            "properties": {
                "your_move": _EVENT_CARD_OBJECT,
                "competitor_events": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "action"],
                        "properties": {
                            "name": {"type": "string", "maxLength": 80},
                            "action": {"type": "string", "maxLength": 220},
                            "source": {"type": "string", "maxLength": 80},
                            "title": {"type": "string", "maxLength": 90},
                            "body": {"type": "string", "maxLength": 420},
                            "cash_delta": {"type": "number"},
                            "revenue_delta": {"type": "number"},
                            "market_cap_delta": {"type": "number"},
                            "initiative_update": _INITIATIVE,
                        },
                    },
                },
                "world_events": {"type": "array", "minItems": 1, "maxItems": 2, "items": _EVENT_CARD_OBJECT},
                "cash_delta": {"type": "number"},
                "revenue_delta": {"type": "number"},
                "market_cap_delta": {"type": "number"},
                "initiative_updates": {"type": "array", "maxItems": 3, "items": _INITIATIVE},
                "next_inbox": {"type": "array", "minItems": 2, "maxItems": 4, "items": _INBOX_ITEM},
                "memory_patch": _MEMORY_PATCH,
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
    "Strategic decisions must not disappear after one month. If an action starts robotics, autonomy, AI, factories, R&D, expansion, "
    "or any multi-year operating bet, add an initiative_update with a realistic long horizon. Robotics and autonomy can be 60-120 months; "
    "factory and scale programs can be 36-60 months. Early months should usually burn cash, create milestones, and only later create revenue. "
    "Initiatives are recurring plans: they keep affecting the company every future month until their duration ends, and future cards should "
    "reference their phase, milestones, pressure, and compounding consequences. "
    "If the player gives no new action, do not invent a new initiative; active initiatives are applied automatically. "
    "Be decisive and varied; not every month is break-even."
)

COMPETITOR_SYSTEM = (
    "You simulate ONE competitor in an EV automotive market for one month. "
    "Given your state and the player's actions this month, decide ONE realistic action you took and its financial impact. "
    "Use grounded monthly magnitudes (tens of thousands for normal moves, hundreds of thousands for major plays). "
    "Cash delta is net of operating costs. React to player threats and opportunities. Action: one short sentence."
)

MONTH_SYSTEM = (
    "You are the engine of Pax Venture, a month-by-month CEO simulation in the EV automotive industry. "
    "Resolve exactly one month from the CEO order. The player writes the action, and you decide what actually happens: "
    "financial impact, rival moves, world events, future inbox, and memory. Be concrete, in-world, and consequential. "
    "Use event-card prose with real actors such as Board of Directors, CFO Office, Reuters EV Desk, Supplier Council, "
    "Regulator Desk, Tesla Strategy, Toyota Strategy, BYD Strategy, or Union Desk. "
    "Long-term bets must become initiative_updates only when the decision deserves a recurring plan. "
    "Do not mention schemas, prompts, the UI, or being an AI. Do not let every decision be good."
)


games: dict[str, dict[str, Any]] = {}


class NewGameBody(BaseModel):
    company_name: str = "Pax Motors"
    ceo_name: str | None = None


class ActionBody(BaseModel):
    text: str


class SimulateBody(BaseModel):
    text: str | None = None


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def possessive(value: str) -> str:
    clean = value.strip() or "company"
    return f"{clean}'" if clean.endswith("s") else f"{clean}'s"


def initial_inbox(company_name: str) -> list[dict[str, str]]:
    return [
        {
            "sender": "Board",
            "subject": "First monthly operating plan",
            "body": f"The board wants one clear CEO order for {possessive(company_name)} next month.",
            "category": "board",
        },
        {
            "sender": "CFO",
            "subject": "Cash discipline",
            "body": "The company has room to move, but every month should show why the spend matters.",
            "category": "finance",
        },
    ]


def default_memory(company_name: str, ceo_name: str = "") -> dict[str, Any]:
    identity = {"company_name": company_name}
    if ceo_name:
        identity["ceo_name"] = ceo_name
    return {
        "identity": identity,
        "canon": [],
        "recent_summaries": [],
        "threads": [],
        "world": [],
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
        "inbox": initial_inbox(company_name),
        "initiatives": [],
        "competitors": [{**c, "initiatives": []} for c in COMPETITORS],
        "history": [],
        "memory": default_memory(company_name, ceo_name.strip()),
        "llm_calls": [],
        "game_over": False,
        "autopsy": None,
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
    g.setdefault("inbox", initial_inbox(g.get("company_name", "Pax Motors")))
    g.setdefault("history", [])
    g.setdefault("initiatives", [])
    g.setdefault("market_cap", market_cap(g.get("cash", STARTING_CASH), g.get("revenue", STARTING_REVENUE)))
    g.setdefault("memory", default_memory(g.get("company_name", "Pax Motors")))
    g.setdefault("llm_calls", [])
    g.setdefault("game_over", False)
    g.setdefault("autopsy", None)
    memory = g["memory"]
    memory.setdefault("identity", {})
    memory["identity"].setdefault("company_name", g.get("company_name", "Pax Motors"))
    memory.setdefault("canon", [])
    memory.setdefault("recent_summaries", [])
    memory.setdefault("threads", [])
    memory.setdefault("world", [])
    memory.setdefault("competitors", {})
    memory.setdefault("tone", "Pax-Historia-style in-world event briefings.")
    memory.setdefault("updated_at", now_iso())
    for initiative in g.get("initiatives", []):
        initiative.setdefault("started_month", 0)
        initiative.setdefault("elapsed_months", 0)
        initiative.setdefault("last_action", "")
        initiative.setdefault("horizon_months", int(initiative.get("remaining_months", 0)) + int(initiative.get("elapsed_months", 0)))
        initiative.setdefault("milestones", [])
        initiative.setdefault("achieved_milestones", [])
        if initiative.get("kind") == "strategic_thesis":
            initiative.setdefault(
                "phase",
                _strategy_phase(
                    str(initiative.get("category", "")),
                    int(initiative.get("elapsed_months", 0)),
                    int(initiative.get("horizon_months", initiative.get("remaining_months", 1))),
                ),
            )
    for comp in g.get("competitors", []):
        comp.setdefault("initiatives", [])
        comp.setdefault("market_cap", market_cap(comp.get("cash", 0), comp.get("revenue", 0), comp.get("revenue_multiple", DEFAULT_REVENUE_MULTIPLE)))
        for initiative in comp.get("initiatives", []):
            initiative.setdefault("started_month", 0)
            initiative.setdefault("elapsed_months", 0)
            initiative.setdefault("last_action", "")
            initiative.setdefault("horizon_months", int(initiative.get("remaining_months", 0)) + int(initiative.get("elapsed_months", 0)))
    diversify_competitor_threads(g)
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
        "recent_summaries": g["memory"].get("recent_summaries", [])[-8:],
        "threads": g["memory"].get("threads", [])[-8:],
        "world": g["memory"].get("world", [])[-8:],
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


def _clip(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: Any, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, _number(value)))


def _clean_section(value: Any, fallback: str) -> dict[str, str]:
    section = _section(value or fallback)
    return {
        "source": _clip(section.get("source") or "CEO Office", 80),
        "title": _clip(section.get("title") or "MONTHLY UPDATE", 90),
        "body": _clip(section.get("body") or fallback, 420),
    }


def _fallback_inbox(g: dict[str, Any] | None = None) -> list[dict[str, str]]:
    company = (g or {}).get("company_name", "the company")
    return [
        {
            "sender": "Board",
            "subject": "Next month priorities",
            "body": f"The board wants one decisive operating order for {company}.",
            "category": "board",
        },
        {
            "sender": "Market",
            "subject": "Competitive pressure",
            "body": "Rivals and suppliers kept moving; the next order needs a clear tradeoff.",
            "category": "market",
        },
    ]


def _clean_inbox_item(raw: Any) -> dict[str, str]:
    item = raw if isinstance(raw, dict) else {}
    return {
        "sender": _clip(item.get("sender") or "Board", 60),
        "subject": _clip(item.get("subject") or "Next month priorities", 90),
        "body": _clip(item.get("body") or "The board wants one decisive operating order.", 360),
        "category": _clip(item.get("category") or "info", 40),
    }


def _clean_initiative(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = _clip(raw.get("name"), 60)
    if not name:
        return None
    duration = int(_clamp(raw.get("duration_months") or raw.get("remaining_months") or 1, 1, MAX_INITIATIVE_MONTHS))
    horizon = int(_clamp(raw.get("horizon_months") or duration, duration, MAX_INITIATIVE_MONTHS))
    cleaned: dict[str, Any] = {
        "name": name,
        "monthly_cash_delta": _clamp(raw.get("monthly_cash_delta"), -MAX_CASH_DELTA, MAX_CASH_DELTA),
        "monthly_revenue_delta": _clamp(raw.get("monthly_revenue_delta"), -MAX_REVENUE_DELTA, MAX_REVENUE_DELTA),
        "monthly_market_cap_delta": _clamp(raw.get("monthly_market_cap_delta"), -MAX_MARKET_CAP_DELTA, MAX_MARKET_CAP_DELTA),
        "duration_months": duration,
        "horizon_months": horizon,
    }
    for key, limit in (
        ("kind", 40),
        ("category", 40),
        ("phase", 60),
        ("thesis", 220),
        ("last_action", 220),
    ):
        value = _clip(raw.get(key), limit)
        if value:
            cleaned[key] = value
    if isinstance(raw.get("milestones"), list):
        milestones = []
        for milestone in raw["milestones"][:8]:
            if not isinstance(milestone, dict):
                continue
            label = _clip(milestone.get("label"), 80)
            if label:
                milestones.append({"month": int(_clamp(milestone.get("month"), 1, MAX_INITIATIVE_MONTHS)), "label": label})
        if milestones:
            cleaned["milestones"] = milestones
    return cleaned


def _clean_competitor_event(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        raw = {"name": "Rivals", "action": raw}
    raw = raw if isinstance(raw, dict) else {}
    name = _clip(raw.get("name") or "Rivals", 80)
    action = _clip(raw.get("action") or raw.get("body") or "Rivals adjusted their operating plans.", 220)
    section = _clean_section(
        {
            "source": raw.get("source") or f"{name} Strategy Desk",
            "title": raw.get("title") or "RIVAL MOVE RECORDED",
            "body": raw.get("body") or action,
        },
        f"{name} adjusted its plan.",
    )
    event: dict[str, Any] = {
        "name": name,
        "action": action,
        "source": section["source"],
        "title": section["title"],
        "body": section["body"],
        "cash_delta": _clamp(raw.get("cash_delta"), -MAX_CASH_DELTA, MAX_CASH_DELTA),
        "revenue_delta": _clamp(raw.get("revenue_delta"), -MAX_REVENUE_DELTA, MAX_REVENUE_DELTA),
        "market_cap_delta": _clamp(raw.get("market_cap_delta"), -MAX_MARKET_CAP_DELTA, MAX_MARKET_CAP_DELTA),
    }
    initiative = _clean_initiative(raw.get("initiative_update"))
    if initiative:
        event["initiative_update"] = initiative
        event["initiative"] = initiative["name"]
        event["initiative_status"] = "opened"
    elif raw.get("initiative"):
        event["initiative"] = _clip(raw.get("initiative"), 60)
        event["initiative_status"] = _clip(raw.get("initiative_status") or "continued", 40)
    return event


def _clean_world_event(raw: Any) -> dict[str, str]:
    section = _clean_section(raw, "Reuters EV Desk | MARKET KEEPS MOVING: Competitors, suppliers, and regulators kept changing the month.")
    severity = raw.get("severity") if isinstance(raw, dict) else ""
    return {**section, "severity": _clip(severity or "info", 40)}


def _clean_memory_patch(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "facts": [
            {"key": _clip(item.get("key"), 60), "value": _clip(item.get("value"), 160)}
            for item in (raw.get("facts") or [])[:6]
            if isinstance(item, dict) and _clip(item.get("key"), 60) and _clip(item.get("value"), 160)
        ],
        "threads": [
            {
                "label": _clip(item.get("label"), 60),
                "summary": _clip(item.get("summary"), 220),
                "status": _clip(item.get("status") or "active", 40),
            }
            for item in (raw.get("threads") or [])[:6]
            if isinstance(item, dict) and _clip(item.get("label"), 60) and _clip(item.get("summary"), 220)
        ],
        "competitors": [
            {"name": _clip(item.get("name"), 80), "summary": _clip(item.get("summary"), 220)}
            for item in (raw.get("competitors") or [])[:6]
            if isinstance(item, dict) and _clip(item.get("name"), 80) and _clip(item.get("summary"), 220)
        ],
        "world": [
            {"summary": _clip(item.get("summary"), 220)}
            for item in (raw.get("world") or [])[:6]
            if isinstance(item, dict) and _clip(item.get("summary"), 220)
        ],
        "summary": _clip(raw.get("summary"), 220),
    }


def validate_month_result(result: dict[str, Any]) -> dict[str, Any]:
    raw = result if isinstance(result, dict) else {}
    competitor_events = [_clean_competitor_event(item) for item in (raw.get("competitor_events") or [])[:3]]
    if not competitor_events:
        competitor_events = [_clean_competitor_event({"name": "Rivals", "action": "Competitors held position while they read the player's move."})]
    world_events = [_clean_world_event(item) for item in (raw.get("world_events") or [])[:2]]
    if not world_events:
        world_events = [_clean_world_event({"source": "Reuters EV Desk", "title": "MARKET KEEPS MOVING", "body": "Suppliers, buyers, and regulators kept changing the operating context."})]
    inbox = [_clean_inbox_item(item) for item in (raw.get("next_inbox") or [])[:INBOX_LIMIT]]
    while len(inbox) < 2:
        inbox.append(_fallback_inbox()[len(inbox)])
    return {
        "your_move": _clean_section(raw.get("your_move"), "CEO Office | MONTH RESOLVED: The company absorbed the consequences of the order."),
        "competitor_events": competitor_events,
        "world_events": world_events,
        "cash_delta": _clamp(raw.get("cash_delta"), -MAX_CASH_DELTA, MAX_CASH_DELTA),
        "revenue_delta": _clamp(raw.get("revenue_delta"), -MAX_REVENUE_DELTA, MAX_REVENUE_DELTA),
        "market_cap_delta": _clamp(raw.get("market_cap_delta"), -MAX_MARKET_CAP_DELTA, MAX_MARKET_CAP_DELTA),
        "initiative_updates": [i for i in (_clean_initiative(item) for item in (raw.get("initiative_updates") or [])[:3]) if i],
        "next_inbox": inbox,
        "memory_patch": _clean_memory_patch(raw.get("memory_patch")),
    }


def _upsert_limited(items: list[dict[str, Any]], new_item: dict[str, Any], key: str, limit: int = MEMORY_LIST_LIMIT) -> list[dict[str, Any]]:
    needle = str(new_item.get(key, "")).lower()
    kept = [item for item in items if str(item.get(key, "")).lower() != needle]
    kept.append(new_item)
    return kept[-limit:]


def apply_memory_patch(g: dict[str, Any], patch: dict[str, Any]) -> None:
    ensure_game_shape(g)
    patch = _clean_memory_patch(patch)
    for fact in patch["facts"]:
        key = fact["key"]
        value = fact["value"]
        if key == "canon":
            remember_canon(g, value)
        else:
            remember_fact(g, key, value)
    memory = g["memory"]
    for thread in patch["threads"]:
        memory["threads"] = _upsert_limited(memory.get("threads", []), thread, "label")
    for world in patch["world"]:
        memory["world"] = _upsert_limited(memory.get("world", []), world, "summary")
    if patch["summary"]:
        memory["recent_summaries"] = _upsert_limited(
            [{"summary": summary} for summary in memory.get("recent_summaries", [])],
            {"summary": patch["summary"]},
            "summary",
        )
        memory["recent_summaries"] = [item["summary"] for item in memory["recent_summaries"]]
    for competitor in patch["competitors"]:
        remember_competitor_event(
            g,
            int(g.get("month", 0)),
            {
                "name": competitor["name"],
                "action": competitor["summary"],
                "initiative_status": "remembered",
            },
        )
    memory["updated_at"] = now_iso()


def build_month_payload(g: dict[str, Any], action_text: str) -> dict[str, Any]:
    ensure_game_shape(g)
    return {
        "company_name": g["company_name"],
        "month": int(g.get("month", 0)) + 1,
        "decision": _clip(action_text or "Hold current course.", 600),
        "cash": g["cash"],
        "revenue_per_month": g["revenue"],
        "market_cap": company_market_cap(g),
        "current_inbox": [dict(item) for item in g.get("inbox", [])],
        "active_initiatives": [dict(item) for item in g.get("initiatives", [])],
        "competitors": [
            {
                "name": c["name"],
                "cash": c["cash"],
                "revenue": c["revenue"],
                "market_cap": company_market_cap(c),
                "active_initiatives": [dict(i) for i in c.get("initiatives", [])],
            }
            for c in g.get("competitors", [])
        ],
        "memory": memory_context(g),
        "recent_history": g.get("history", [])[-5:],
    }


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
        "inbox": [dict(item) for item in g.get("inbox", [])],
        "initiatives": [dict(i) for i in g["initiatives"]],
        "competitors": [dict(c) for c in g["competitors"]],
        "history": list(g["history"]),
        "leaderboard": leaderboard,
        "memory": dict(g.get("memory", {})),
        "telemetry": telemetry_summary(g),
        "game_over": bool(g.get("game_over")),
        "autopsy": g.get("autopsy"),
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
        "strategic_interpretation": infer_strategic_initiative_updates(g),
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


async def resolve_month(client: httpx.AsyncClient, g: dict[str, Any], action_text: str) -> dict[str, Any]:
    payload = build_month_payload(g, action_text)
    result = await _call_llm(
        client,
        [
            {"role": "system", "content": MONTH_SYSTEM},
            {"role": "user", "content": f"{json.dumps(payload, separators=(',', ':'))}\n\nReturn resolve_month JSON."},
        ],
        MONTH_TOOL,
        max_tokens=1100,
        call_type="resolve_month",
        game=g,
    )
    return validate_month_result(result)


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


def _bounded(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, value))


def _matches_strategy_keyword(action_plan: str, keyword: str) -> bool:
    if " " in keyword or "-" in keyword:
        return keyword in action_plan
    return bool(re.search(rf"\b{re.escape(keyword)}\b", action_plan))


def _strategy_phase(category: str, elapsed_months: int, horizon_months: int) -> str:
    if elapsed_months <= 1:
        return "charter"
    if elapsed_months <= 3:
        return "team buildout"
    if elapsed_months <= 6:
        return "prototype"
    if elapsed_months <= 12:
        return "pilot"
    if elapsed_months <= 24:
        return "integration"
    if elapsed_months <= max(36, horizon_months // 2):
        return "scaling"
    return "compounding"


def infer_strategic_initiative_updates(g: dict[str, Any]) -> list[dict[str, Any]]:
    action_plan = " ".join(g.get("actions") or []).lower()
    if not action_plan:
        return []

    updates = []
    company_value = company_market_cap(g)
    for blueprint in STRATEGIC_ACTION_BLUEPRINTS:
        if not any(_matches_strategy_keyword(action_plan, keyword) for keyword in blueprint["keywords"]):
            continue
        monthly_burn = _bounded(
            max(float(g.get("cash", 0)) * blueprint["cash_rate"], float(g.get("revenue", 0)) * blueprint["revenue_rate"]),
            blueprint["cash_floor"],
            blueprint["cash_ceiling"],
        )
        monthly_value = _bounded(company_value * blueprint["market_cap_rate"], 35_000, 900_000)
        horizon = int(blueprint["horizon_months"])
        updates.append(
            {
                "name": blueprint["name"],
                "kind": "strategic_thesis",
                "category": blueprint["category"],
                "phase": blueprint["phase"],
                "thesis": blueprint["thesis"],
                "horizon_months": horizon,
                "duration_months": horizon,
                "monthly_cash_delta": -round(monthly_burn, 2),
                "monthly_revenue_delta": 0,
                "monthly_market_cap_delta": round(monthly_value, 2),
                "milestones": [dict(milestone) for milestone in blueprint["milestones"]],
                "last_action": (
                    f"{g['company_name']} committed to {blueprint['name']} as a "
                    f"{max(1, horizon // 12)}-year strategic thesis, not a one-month budget line."
                ),
            }
        )
    return updates[:3]


def merge_strategic_updates(
    existing_updates: list[dict[str, Any]],
    strategic_updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(existing_updates)
    for update in strategic_updates:
        update_category = str(update.get("category") or "").lower()
        update_name = _initiative_key(update.get("name"))
        replacement_index = None
        for index, current in enumerate(merged):
            current_name = _initiative_key(current.get("name"))
            current_category = str(current.get("category") or "").lower()
            same_name = bool(update_name and update_name == current_name)
            same_category = bool(update_category and update_category == current_category)
            category_in_name = bool(update_category and update_category in current_name)
            if same_name or same_category or category_in_name:
                replacement_index = index
                break
        if replacement_index is None:
            merged.append(update)
        else:
            current = merged[replacement_index]
            combined = {**current, **update}
            combined["name"] = current.get("name") or update.get("name")
            combined["duration_months"] = max(int(current.get("duration_months", 0) or 0), int(update.get("duration_months", 0) or 0))
            combined["horizon_months"] = max(int(current.get("horizon_months", 0) or 0), int(update.get("horizon_months", 0) or 0))
            merged[replacement_index] = combined
    return merged[:3]


def _initiative_key(name: Any) -> str:
    return " ".join(str(name or "").split()).lower()


def _active_competitor_thread_names(g: dict[str, Any]) -> set[str]:
    names = set()
    for comp in g.get("competitors", []):
        for initiative in comp.get("initiatives", []):
            if int(initiative.get("remaining_months", 0) or 0) > 0:
                key = _initiative_key(initiative.get("name"))
                if key:
                    names.add(key)
    return names


def _take_unused_competitor_action(
    rng: random.Random,
    action_deck: list[tuple[str, str, float, float, float, int]],
    used_thread_names: set[str],
) -> tuple[str, str, float, float, float, int]:
    for index, action in enumerate(action_deck):
        if _initiative_key(action[0]) not in used_thread_names:
            return action_deck.pop(index)
    return rng.choice(COMPETITOR_ACTIONS)


def diversify_competitor_threads(g: dict[str, Any]) -> None:
    used_thread_names: set[str] = set()
    month = str(g.get("month", 0))
    action_deck = list(COMPETITOR_ACTIONS)
    _stable_rng(str(g.get("id", "")), month, "repair-competitor-thread-deck").shuffle(action_deck)

    for comp in g.get("competitors", []):
        repaired = []
        for initiative in comp.get("initiatives", []):
            key = _initiative_key(initiative.get("name"))
            if not key or int(initiative.get("remaining_months", 0) or 0) <= 0:
                repaired.append(initiative)
                continue
            if key in used_thread_names:
                rng = _stable_rng(str(g.get("id", "")), month, comp.get("name", ""), key, "repair-competitor-thread")
                replacement = _take_unused_competitor_action(rng, action_deck, used_thread_names)
                name, _, cash_rate, revenue_rate, market_cap_rate, _ = replacement
                old_name = str(initiative.get("name", "") or "the duplicate thread")
                action = f"{comp['name']} redirected {old_name} resources into {name} to avoid chasing the same lane as rivals."
                initiative = {
                    **initiative,
                    "name": name,
                    "monthly_cash_delta": round(cash_rate * comp["revenue"], 2),
                    "monthly_revenue_delta": round(revenue_rate * comp["revenue"], 2),
                    "monthly_market_cap_delta": round(market_cap_rate * company_market_cap(comp), 2),
                    "last_action": action,
                    "diversified_from": old_name,
                }
                key = _initiative_key(name)
            used_thread_names.add(key)
            repaired.append(initiative)
        comp["initiatives"] = repaired


def resolve_competitors_locally(g: dict[str, Any]) -> list[dict]:
    month = str(g["month"] + 1)
    action_plan = " | ".join(g["actions"] or ["no actions"])
    player_threads = " | ".join(
        f"{initiative.get('name')}:{initiative.get('phase', '')}"
        for initiative in g.get("initiatives", [])
        if initiative.get("kind") == "strategic_thesis"
    )
    if player_threads:
        action_plan = f"{action_plan} | player strategic threads: {player_threads}"
    count = min(ACTIVE_COMPETITOR_ACTIONS_PER_MONTH, len(g["competitors"]))
    selection_rng = _stable_rng(g["id"], month, "active-competitors", action_plan)
    active_names = {
        comp["name"] for comp in selection_rng.sample(g["competitors"], k=count)
    }
    used_thread_names = _active_competitor_thread_names(g)
    action_deck = list(COMPETITOR_ACTIONS)
    _stable_rng(g["id"], month, "new-competitor-thread-deck", action_plan).shuffle(action_deck)
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
            text = rng.choice(COMPETITOR_CONTINUATIONS).format(name=comp["name"], initiative=initiative_name)
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
        initiative_name, text, cash_rate, revenue_rate, market_cap_rate, duration = _take_unused_competitor_action(
            rng,
            action_deck,
            used_thread_names,
        )
        used_thread_names.add(_initiative_key(initiative_name))
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
    effect = {"cash_delta": 0.0, "revenue_delta": 0.0, "market_cap_delta": 0.0, "names": [], "milestones": []}
    active = []
    for initiative in entity.get("initiatives", []):
        cash_delta = float(initiative.get("monthly_cash_delta", 0))
        revenue_delta = float(initiative.get("monthly_revenue_delta", 0))
        market_cap_delta = float(initiative.get("monthly_market_cap_delta", 0))
        next_elapsed = int(initiative.get("elapsed_months", 0)) + 1
        if initiative.get("kind") == "strategic_thesis":
            horizon = int(initiative.get("horizon_months", initiative.get("remaining_months", 1)) or 1)
            phase = _strategy_phase(str(initiative.get("category", "")), next_elapsed, horizon)
            initiative["phase"] = phase
            if next_elapsed >= 6:
                revenue_ramp = min(0.35, max(0.0, (next_elapsed - 5) * 0.025))
                revenue_delta += abs(cash_delta) * revenue_ramp
            achieved = set(initiative.get("achieved_milestones", []) or [])
            reached = []
            for milestone in initiative.get("milestones", []) or []:
                label = str(milestone.get("label", "")).strip()
                if not label or label in achieved:
                    continue
                if int(milestone.get("month", 0) or 0) == next_elapsed:
                    reached.append(label)
                    achieved.add(label)
            if reached:
                milestone_bonus = _bounded(company_market_cap(entity) * 0.0025, 25_000, 750_000)
                market_cap_delta += milestone_bonus
                for label in reached:
                    effect["milestones"].append({"name": initiative["name"], "label": label, "phase": phase})
                initiative["achieved_milestones"] = list(achieved)
                initiative["last_action"] = f"{initiative['name']} reached milestone: {reached[-1]}."
            else:
                initiative["last_action"] = f"{initiative['name']} remained in {phase}; this is a multi-year thesis, not a one-month outcome."
        effect["cash_delta"] += cash_delta
        effect["revenue_delta"] += revenue_delta
        effect["market_cap_delta"] += market_cap_delta
        effect["names"].append(initiative["name"])
        initiative["elapsed_months"] = next_elapsed
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
        duration_months = max(
            1,
            min(
                MAX_INITIATIVE_MONTHS,
                int(raw.get("duration_months") or existing.get("remaining_months") or 1),
            ),
        )
        horizon_months = max(
            duration_months,
            min(
                MAX_INITIATIVE_MONTHS,
                int(raw.get("horizon_months") or existing.get("horizon_months") or duration_months),
            ),
        )
        initiative = {
            "name": name,
            "monthly_cash_delta": float(raw.get("monthly_cash_delta", 0)),
            "monthly_revenue_delta": float(raw.get("monthly_revenue_delta", 0)),
            "monthly_market_cap_delta": float(raw.get("monthly_market_cap_delta", 0)),
            "remaining_months": duration_months,
            "started_month": int(raw.get("started_month") or existing.get("started_month") or current_month or 0),
            "elapsed_months": int(existing.get("elapsed_months", 0)),
            "last_action": str(raw.get("last_action") or existing.get("last_action") or "")[:220],
        }
        optional_fields = (
            "kind",
            "category",
            "phase",
            "thesis",
            "milestones",
            "achieved_milestones",
            "diversified_from",
        )
        for field in optional_fields:
            value = raw.get(field, existing.get(field))
            if value not in (None, "", []):
                initiative[field] = value
        initiative["horizon_months"] = horizon_months
        if initiative.get("kind") == "strategic_thesis":
            initiative.setdefault(
                "phase",
                _strategy_phase(
                    str(initiative.get("category", "")),
                    int(initiative.get("elapsed_months", 0)),
                    horizon_months,
                ),
            )
            initiative.setdefault("milestones", [])
            initiative.setdefault("achieved_milestones", [])
        by_name[name.lower()] = initiative
    entity["initiatives"] = list(by_name.values())


def ceo_address(g: dict[str, Any]) -> str:
    ceo = g.get("memory", {}).get("identity", {}).get("ceo_name")
    return f"{ceo}, " if ceo else ""


def quiet_player_result(g: dict[str, Any], initiative_effect: dict, competitor_results: list[dict]) -> dict[str, Any]:
    if initiative_effect["names"]:
        names = ", ".join(initiative_effect["names"])
        if initiative_effect.get("milestones"):
            milestone = initiative_effect["milestones"][-1]
            your_move = (
                "CEO Office | STRATEGIC MILESTONE REACHED: "
                f"{ceo_address(g)}no new order crossed the desk, but {milestone['name']} advanced anyway. "
                f"{milestone['label']} moved the plan into its {milestone['phase']} phase, so the earlier decision kept changing the company."
            )
        else:
            your_move = (
                "CEO Office | EXISTING PROGRAMS KEEP RUNNING: "
                f"{ceo_address(g)}no new order crossed the desk this month. {names} kept moving through finance and operations, "
                "so the company still felt the weight of earlier commitments instead of resetting to a blank month."
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
    # Legacy compatibility: keep the helper, but do not invent strategy from keywords.
    # Long-term plans now come only from the LLM's initiative_updates.
    cleaned = dict(player_result)
    cleaned["initiative_updates"] = [
        item for item in (_clean_initiative(raw) for raw in (player_result.get("initiative_updates") or [])) if item
    ]
    return cleaned


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


def apply_month_result(g: dict[str, Any], result: dict[str, Any], decision_text: str = "") -> dict[str, Any]:
    ensure_game_shape(g)
    result = validate_month_result(result)
    decision = _clip(decision_text or " | ".join(g.get("actions", [])) or "Hold current course.", 600)
    initiative_effect = apply_active_initiatives(g)
    competitor_initiative_effects = apply_competitor_initiatives(g)

    cash_delta = float(result["cash_delta"])
    revenue_delta = float(result["revenue_delta"])
    market_cap_delta = float(result["market_cap_delta"])
    g["cash"] += cash_delta
    g["revenue"] = max(0.0, g["revenue"] + revenue_delta)
    g["market_cap"] = max(0.0, company_market_cap(g) + market_cap_delta)

    resolution_month = int(g.get("month", 0)) + 1
    upsert_initiatives(g, result["initiative_updates"], current_month=resolution_month)

    competitors_by_name = {comp["name"]: comp for comp in g.get("competitors", [])}
    competitor_events = []
    for event in result["competitor_events"]:
        comp = competitors_by_name.get(event["name"])
        if comp:
            comp["cash"] += float(event.get("cash_delta", 0))
            comp["revenue"] = max(0.0, comp["revenue"] + float(event.get("revenue_delta", 0)))
            comp["market_cap"] = max(0.0, company_market_cap(comp) + float(event.get("market_cap_delta", 0)))
            initiative = event.get("initiative_update")
            if initiative:
                upsert_initiatives(comp, [initiative], current_month=resolution_month)
        competitor_events.append({**event, "recurring_effect": competitor_initiative_effects.get(event["name"])})

    g["month"] = resolution_month
    g["inbox"] = [dict(item) for item in result["next_inbox"]]
    apply_memory_patch(g, result["memory_patch"])

    player_total_cash_delta = cash_delta + float(initiative_effect.get("cash_delta", 0))
    player_total_revenue_delta = revenue_delta + float(initiative_effect.get("revenue_delta", 0))
    player_total_market_cap_delta = market_cap_delta + float(initiative_effect.get("market_cap_delta", 0))
    world_events = [dict(item) for item in result["world_events"]]
    memory_summary = result["memory_patch"].get("summary", "")
    history_entry = {
        "month": g["month"],
        "decision": decision,
        "your_move": dict(result["your_move"]),
        "competitor_events": competitor_events,
        "world_events": world_events,
        "next_inbox": [dict(item) for item in g["inbox"]],
        "memory_summary": memory_summary,
        "actions": [decision],
        "competitor_spotlight": dict(competitor_events[0]) if competitor_events else _section("Rivals | QUIET MONTH: Competitors held position."),
        "competitor_actions": competitor_events,
        "market": dict(world_events[0]) if world_events else _section("Market | STEADY MONTH: The market kept moving."),
        "competitor_initiative_effects": competitor_initiative_effects,
        "initiative_effect": initiative_effect,
        "active_initiatives": [dict(i) for i in g["initiatives"]],
        "player_cash_delta": cash_delta,
        "player_revenue_delta": revenue_delta,
        "player_market_cap_delta": market_cap_delta,
        "player_total_cash_delta": player_total_cash_delta,
        "player_total_revenue_delta": player_total_revenue_delta,
        "player_total_market_cap_delta": player_total_market_cap_delta,
    }
    g["history"].append(history_entry)
    remember_canon(g, f"M{g['month']} CEO order: {decision}")
    if result["your_move"].get("title"):
        remember_canon(g, f"M{g['month']} outcome: {result['your_move']['title']}")
    for event in competitor_events:
        remember_competitor_event(g, g["month"], event)
    for event in world_events:
        g["memory"]["world"] = _upsert_limited(
            g["memory"].get("world", []),
            {"summary": f"M{g['month']}: {event['title']}"},
            "summary",
        )

    if g["cash"] < 0:
        g["game_over"] = True
        g["autopsy"] = {
            "cause": "cash_below_zero",
            "month": g["month"],
            "board_note": f"Cash fell below zero in month {g['month']}. The board closed the game after the company exhausted its runway.",
            "last_decision": decision,
        }
    g["actions"] = []
    return g


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
async def simulate(game_id: str, body: SimulateBody | None = None) -> dict[str, Any]:
    g = games.get(game_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    ensure_game_shape(g)
    if g.get("game_over"):
        raise HTTPException(status_code=409, detail="Game is over")
    action_text = _clip((body.text if body else "") or " | ".join(g.get("actions", [])) or "Hold current course.", 600)
    if body and body.text:
        extract_memory_from_text(g, action_text)
    started = time.perf_counter()
    timeout = httpx.Timeout(60.0, connect=10.0)
    limits = httpx.Limits(max_connections=12, max_keepalive_connections=12)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, http2=False) as client:
        month_result = await resolve_month(client, g, action_text)
    apply_month_result(g, month_result, action_text)
    save_games()
    return {**public_state(g), "latency_ms": int((time.perf_counter() - started) * 1000)}
