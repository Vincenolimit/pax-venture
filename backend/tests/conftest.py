import sys
from pathlib import Path
import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal, engine, init_db  # noqa: E402
from app.core.openrouter import ToolCallResult  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def reset_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await init_db()
    yield


@pytest.fixture(autouse=True)
def mock_llm_call_tool(monkeypatch):
    async def _mock_call_tool(call_type, model, messages, tool, *, cache_control_on_system, seed, stream=False, session=None, player_id=None):
        _ = cache_control_on_system
        _ = stream
        _ = session
        _ = player_id
        _ = model
        _ = seed
        _ = tool
        if call_type == "generate_inbox_emails":
            args = {
                "emails": [
                    {
                        "sender": "Board",
                        "subject": "Board check-in",
                        "body": "Protect runway and execute with discipline.",
                        "category": "board",
                        "requires_action": True,
                        "references": {"thread_label": "board_confidence"},
                    },
                    {
                        "sender": "CFO",
                        "subject": "Runway and operating discipline",
                        "body": "Current burn profile requires a clear payback path.",
                        "category": "warning",
                        "requires_action": True,
                        "references": {"flag_name": "ipo_filed"},
                    },
                    {
                        "sender": "Market",
                        "subject": "External pressure update",
                        "body": "Fleet buyers are asking for lower TCO EV options.",
                        "category": "opportunity",
                        "requires_action": True,
                        "references": {"world_event_id": "chip_shortage_2026"},
                    },
                ]
            }
        elif call_type == "resolve_decision":
            prompt_text = str(messages[-1].get("content", "")) if messages else ""
            is_cost_cut = "cut" in prompt_text.lower()
            args = {
                "narrative": "Execution moved the plan forward with measurable traction.",
                "cash_impact": 34532 if is_cost_cut else -105468,
                "revenue_impact": 182898 if is_cost_cut else 262898,
                "market_impact": 0.05 if is_cost_cut else 0.19,
                "importance": 0.61,
                "employees_change": -1 if is_cost_cut else 1,
                "relationship_updates": {"board": "neutral"},
                "new_threads": [{"label": "execution_risk", "importance": 0.55}],
                "closed_threads": [],
                "flag_updates": {},
            }
        elif call_type == "compact_memory":
            args = {
                "recent_line": "M1: disciplined execution with focused priorities.",
                "period_summary": "The team balanced runway protection and measured growth bets.",
                "origin_story": "An automotive challenger shaped by high-pressure tradeoffs.",
            }
        elif call_type == "autopsy_summary":
            args = {
                "headline": "A bold strategy outran the balance sheet",
                "arc_summary": "Momentum was real, but burn and timing broke the runway.",
                "pivotal_decisions": [
                    {"month": 3, "one_liner": "Accelerated expansion before supply stabilized.", "verdict": "risky"},
                    {"month": 6, "one_liner": "Delayed defensive cost controls.", "verdict": "fatal"},
                ],
                "cause_of_death": "Cash runway collapsed before revenue matured.",
                "board_quote": "Ambition was clear. Discipline arrived too late.",
            }
        else:
            args = {}

        return ToolCallResult(
            args=args,
            in_tokens=1200,
            out_tokens=280,
            cached_tokens=300,
            cost_usd=0.0012,
            latency_ms=80,
            model="mock/test-model",
            raw={"mocked": True},
        )

    monkeypatch.setattr("app.api.routes.call_tool", _mock_call_tool)
    monkeypatch.setattr("app.services.memory.call_tool", _mock_call_tool)
    monkeypatch.setattr("app.services.autopsy.call_tool", _mock_call_tool)


@pytest_asyncio.fixture
async def session():
    async with SessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
