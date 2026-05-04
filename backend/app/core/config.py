import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"' ")
        existing = os.environ.get(key)
        if existing is None or existing == "":
            os.environ[key] = value


def _load_local_env() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    # Priority: .env (if present), then .env.test
    _load_env_file(backend_root / ".env")
    _load_env_file(backend_root / ".env.test")


_load_local_env()

PROMPT_VERSION = 1
SCHEMA_VERSION = 1
CACHE_TTL = "ephemeral"
PAX_COST_CAP_USD = os.getenv("PAX_COST_CAP_USD")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./pax_venture.db")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _normalize_qwen_model(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return "qwen/qwen3.6-plus"

    lower = value.lower()
    aliases = {
        "qwen": "qwen/qwen3.6-plus",
        "qwen3.6": "qwen/qwen3.6-plus",
        "qwen3.6-plus": "qwen/qwen3.6-plus",
        "qwen/qwen3.6-plus": "qwen/qwen3.6-plus",
        "qwen/qwen3.6-plus-04-02": "qwen/qwen3.6-plus",
        # Free variant has been deprecated on OpenRouter; normalize to paid.
        "qwen3.6-plus:free": "qwen/qwen3.6-plus",
        "qwen/qwen3.6-plus:free": "qwen/qwen3.6-plus",
        "qwen3.6-plus-preview:free": "qwen/qwen3.6-plus",
    }
    if lower in aliases:
        return aliases[lower]

    if value.startswith("openrouter/"):
        value = value[len("openrouter/") :]

    if "/" not in value:
        value = f"qwen/{value}"

    return value


QWEN_MODEL = _normalize_qwen_model(os.getenv("PAX_QWEN_MODEL", "qwen/qwen3.6-plus"))

MODEL_PRICES = {
    "anthropic/claude-haiku-4-5": {"in": 1.0, "in_cached": 0.1, "out": 5.0},
    "anthropic/claude-sonnet-4-6": {"in": 3.0, "in_cached": 0.3, "out": 15.0},
    "anthropic/claude-opus-4-7": {"in": 15.0, "in_cached": 1.5, "out": 75.0},
    "google/gemini-2.5-flash": {"in": 0.3, "in_cached": 0.03, "out": 1.2},
    "voyage/voyage-3-lite": {"in": 0.1, "in_cached": 0.1, "out": 0.1},
    "qwen/qwen3.6-plus": {"in": 0.325, "in_cached": 0.325, "out": 1.95},
    "qwen/qwen3.6-plus:free": {"in": 0.0, "in_cached": 0.0, "out": 0.0},
    "qwen/qwen3.6-plus-preview:free": {"in": 0.0, "in_cached": 0.0, "out": 0.0},
}

POSTURE_RULES = [
    {"trigger": "ev_platform_launched", "template": "novatech", "posture": "AGGRESSIVE", "duration": 3},
    {"trigger": "european_expansion", "template": "autovista", "posture": "DEFENSIVE", "duration": 4},
    {"trigger": "battery_supply_secured", "template": "greenwheel", "posture": "STRUGGLING", "duration": 2},
]

COMPETITOR_TEMPLATES = [
    {"template_id": "autovista", "name": "AutoVista", "cash": 21500000, "revenue": 5150000, "market_share": 18.2, "expenses": 4200000, "base_growth": 0.04, "volatility": 0.03},
    {"template_id": "novatech", "name": "NovaTech", "cash": 17000000, "revenue": 4100000, "market_share": 14.5, "expenses": 3600000, "base_growth": 0.05, "volatility": 0.04},
    {"template_id": "greenwheel", "name": "GreenWheel", "cash": 9000000, "revenue": 2800000, "market_share": 9.3, "expenses": 2400000, "base_growth": 0.03, "volatility": 0.05},
    {"template_id": "ironmotors", "name": "Iron Motors", "cash": 12000000, "revenue": 3500000, "market_share": 11.2, "expenses": 3300000, "base_growth": 0.02, "volatility": 0.02},
]
