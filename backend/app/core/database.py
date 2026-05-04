import json
import uuid
from pathlib import Path

from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import DATABASE_URL
from app.models import Base, Industry, WorldEvent

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session():
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("""
            CREATE VIEW IF NOT EXISTS leaderboard AS
            SELECT id as player_id, company_name, cash, revenue, market_share,
                   RANK() OVER (ORDER BY cash DESC, revenue DESC, market_share DESC) as rank
            FROM players
        """))

    async with SessionLocal() as session:
        exists = await session.scalar(select(Industry).where(Industry.id == "automotive"))
        if not exists:
            prompt = (Path(__file__).resolve().parents[1] / "prompts" / "automotive.md").read_text(encoding="utf-8")
            session.add(Industry(
                id="automotive",
                name="Automotive",
                schema_version=1,
                prompt_version=1,
                system_prompt_template=prompt,
                starting_state_json=json.dumps({"cash": 18000000, "revenue": 0, "market_share": 5.0, "employees": 50}),
                financial_constants=json.dumps({"payroll_per_employee": 30000, "base_overhead": 180000}),
                flag_vocabulary=json.dumps(["ev_platform_launched", "european_expansion", "battery_supply_secured", "recall_risk", "ipo_filed", "union_negotiation_active", "regulatory_investigation", "strategic_partnership", "factory_constructed"]),
                intent_taxonomy=json.dumps(["cost_cut", "hire", "layoff", "rd_invest", "launch_product", "acquire", "pricing", "partnership", "factory_invest", "fundraise", "restructure"]),
                relationship_keys=json.dumps(["board", "suppliers", "government", "union"]),
                relationship_vocab=json.dumps({"board": ["pleased", "neutral", "concerned", "hostile"], "suppliers": ["strong", "stable", "strained", "broken"], "government": ["favorable", "neutral", "hostile"], "union": ["aligned", "neutral", "tense", "striking"]}),
                sender_vocab=json.dumps(["Board", "CFO", "COO", "CTO", "Market", "Supplier", "Regulator", "Union", "Rival"]),
                category_vocab=json.dumps(["info", "warning", "opportunity", "crisis", "board"]),
                employees_change_clamp=json.dumps([-10, 20]),
                cash_impact_clamp=json.dumps([-5000000, 3000000]),
                revenue_impact_clamp=json.dumps([-2000000, 5000000]),
                market_impact_clamp=json.dumps([-3.0, 3.0]),
                recommended_models=json.dumps({"cheap": "qwen/qwen3.6-plus", "balanced": "qwen/qwen3.6-plus", "premium": "qwen/qwen3.6-plus"}),
                enabled=True,
            ))

        count_world = await session.scalar(select(func.count()).select_from(WorldEvent))
        if not count_world:
            events = [
                ("chip_shortage_2026", 3, 2, "major", "Global semiconductor shortage hits automotive supply.", {"global": {"revenue_multiplier": 0.88}, "competitors": {"all": {"revenue_multiplier": 0.92}}}),
                ("eu_emissions_2026", 6, 12, "major", "EU enacts stricter emissions regulation; non-compliant OEMs face fines.", {"requires_flag": "ev_platform_launched", "if_missing_flag_penalty": {"cash_delta_per_month": -150000, "market_share_drift": -0.1}}),
                ("rare_earth_crisis", 9, 2, "minor", "Rare earth export restrictions disrupt EV motor production.", {"global": {"cash_delta_per_month": -80000}, "competitors": {"by_template": {"greenwheel": {"base_growth_delta": -0.04}}}}),
                ("macro_downturn_2027", 12, 4, "crisis", "Global recession compresses auto demand.", {"global": {"revenue_multiplier": 0.80}, "competitors": {"all": {"revenue_multiplier": 0.85}}}),
                ("trade_war_tariffs", 15, 6, "major", "US-China tariffs spike on auto components.", {"global": {"cash_delta_per_month": -120000}}),
                ("union_strike_wave", 18, 2, "minor", "Industry-wide labor unrest.", {"requires_flag": "union_negotiation_active", "if_missing_flag_penalty": {"revenue_multiplier": 0.90}}),
                ("solid_state_breakthrough", 21, 6, "major", "A solid-state battery breakthrough is announced.", {"requires_flag": "battery_supply_secured", "if_missing_flag_penalty": {"market_share_drift": -0.3}}),
                ("recession_bottom", 24, 3, "crisis", "Recession trough; cheapest financing in a decade.", {"global": {"cash_delta_per_month": 50000}, "competitors": {"all": {"revenue_multiplier": 0.95}}}),
            ]
            for e in events:
                session.add(WorldEvent(id=e[0], industry_id="automotive", fire_at_month=e[1], duration_months=e[2], severity=e[3], narrative_seed=e[4], mechanical_effects=json.dumps(e[5])))

        await session.commit()
