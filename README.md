# Pax Venture

**Business simulation — you're the CEO. Decide. Compete. Dominate.**

Month-by-month competitive business sim where you queue CEO actions, then simulate the month. One interface: **Inbox** (emails/events) + **Action Plan** + **Leaderboard** + **Cash Position**. Each player has a **Fiche 10** — a markdown profile the LLM reads to tailor decisions and events.

## Concept

- **Turn-based**: Each turn = 1 month. React to inbox, queue actions, see results.
- **LLM-powered**: The AI plays the role of market, board, competitors, regulators. It reads your Fiche 10 to personalize the experience.
- **Competitive**: Leaderboard shows cash, revenue, and market position vs other players.
- **Minimal UI**: Single screen — no page scrolling. Football Manager style.

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.12, FastAPI, SQLAlchemy, SQLite |
| Frontend | React 19, Vite, CSS Modules |
| AI | OpenAI-compatible API (structured output) |
| Real-time | WebSocket for live updates |

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Architecture

```
backend/
  app/
    api/          # REST + WebSocket endpoints
    core/         # Config, security, LLM client
    models/       # SQLAlchemy models
    services/     # Business logic (game engine, LLM orchestrator)
frontend/
  src/
    components/   # Inbox, Leaderboard, CashPanel, ActionPanel
    hooks/        # useWebSocket, useChat, useGame
    pages/        # MainGame (single-screen layout)
data/
  players/       # Fiche 10 markdown profiles (one per player)
```

## Fiche 10 Format

Each player gets a `data/players/{player_id}.md` file:

```markdown
# Fiche 10 — Acme Corp

## CEO Profile
- Name: Player Name
- Style: Aggressive growth | Conservative | Innovation-first
- Risk tolerance: High / Medium / Low

## Company
- Industry: Automotive / Tech / Retail / Energy
- Founded: Month 1
- Starting cash: $10M

## Track Record
- Month 1: Revenue $2M, Cash $8M, Decision: Expand to Europe
- Month 2: Revenue $3M, Cash $6M, Decision: Launch new product line

## Key Metrics
- Revenue trend: Growing
- Cash burn: $2M/month
- Market position: Challenger

## LLM Notes
- Responds well to bold moves
- Tends to overinvest in R&D
- Has a rivalry with Player X
```

The LLM reads this file each turn to generate contextual events, opponents' moves, and realistic consequences.

## Game Flow

1. **Month starts** → Inbox populates with emails (market news, board requests, supplier offers)
2. **Player queues actions** (invest, cut costs, hire, expand, etc.)
3. **Player submits "Simulate Month"** → LLM reads the action plan and simulates outcomes
4. **Results arrive** → Cash updates, leaderboard shifts, new events trigger
5. **Repeat** — 12-24 month campaign, highest cash wins
