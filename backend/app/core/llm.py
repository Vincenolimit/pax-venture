"""LLM client for game orchestration — generates events, decisions, outcomes."""

from openai import AsyncOpenAI
from app.core.config import settings
from pathlib import Path
import json


client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL,
)


async def generate_month_events(player_id: str, month: int, fiche_content: str, recent_decisions: list[str]) -> list[dict]:
    """Generate inbox messages for a new month based on player's Fiche 10."""
    
    system_prompt = f"""You are the game engine for Pax Venture, a business simulation.
You generate realistic business events, market news, and decision points.
You adapt events based on the player's profile and past decisions.

Player's Fiche 10:
{fiche_content}

Current month: {month}
Recent decisions: {', '.join(recent_decisions[-3:]) if recent_decisions else 'None yet'}

Generate 3-5 inbox messages for this month. Each message should be:
- Realistic and specific to their industry and situation
- Varied in category (market news, board requests, opportunities, crises)
- Some requiring action, some informational

Respond in JSON format:
{{
  "messages": [
    {{
      "sender": "Board|Market|Supplier|Competitor|Regulator|System",
      "subject": "Subject line",
      "body": "Email body (2-3 sentences, specific and actionable)",
      "category": "info|warning|opportunity|crisis|board",
      "requires_action": true/false
    }}
  ]
}}"""

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "system", "content": system_prompt}],
        max_tokens=settings.LLM_MAX_TOKENS,
        response_format={"type": "json_object"},
        temperature=0.8,
    )

    result = json.loads(response.choices[0].message.content)
    return result.get("messages", [])


async def resolve_decision(player_id: str, month: int, decision_text: str, fiche_content: str, current_cash: float) -> dict:
    """Resolve a player's decision — generate the outcome."""
    
    system_prompt = f"""You are the game engine for Pax Venture, a business simulation.
You resolve the player's business decisions and determine their consequences.

Player's Fiche 10:
{fiche_content}

Current month: {month}
Current cash: ${current_cash:,.0f}
Player's decision: {decision_text}

Determine the realistic outcome. Be specific about financial impacts.
Consequences should be proportional to the decision's ambition and risk.

Respond in JSON format:
{{
  "outcome": "Narrative description of what happened (2-3 sentences)",
  "cash_impact": -500000,  // Positive = money gained, Negative = money spent
  "revenue_impact": 200000,  // Change in monthly revenue
  "market_impact": 0.5,  // Change in market share percentage
  "new_events": [  // Optional: 0-2 new inbox messages triggered by this decision
    {{
      "sender": "Sender name",
      "subject": "Subject",
      "body": "Body",
      "category": "info|warning|opportunity|crisis|board",
      "requires_action": true/false
    }}
  ]
}}"""

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "system", "content": system_prompt}],
        max_tokens=settings.LLM_MAX_TOKENS,
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    return json.loads(response.choices[0].message.content)


async def update_fiche(player_id: str, month: int, fiche_content: str, decision: str, outcome: str) -> str:
    """Update the player's Fiche 10 after a decision is resolved."""
    
    system_prompt = f"""You are the game engine for Pax Venture.
Update the player's Fiche 10 markdown profile with their latest decision and outcome.

Current Fiche 10:
{fiche_content}

Month {month} Decision: {decision}
Month {month} Outcome: {outcome}

Update the Track Record and Key Metrics sections. Add any relevant LLM Notes.
Keep the markdown format identical. Do not remove any existing sections."""

    fiche_path = settings.PLAYERS_DIR / f"{player_id}.md"
    
    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "system", "content": system_prompt}],
        max_tokens=settings.LLM_MAX_TOKENS,
        temperature=0.3,  # Low temperature for factual updates
    )

    updated_content = response.choices[0].message.content
    fiche_path.write_text(updated_content)
    return updated_content
