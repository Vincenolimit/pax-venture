# Pax Venture — MVP Engineering Doc

**Goal**: Validate that a month-by-month CEO simulation driven purely by LLM chat is fun and addictive. Ship the minimum that proves the core loop works. Nothing else.

---

## 1. Product Definition

### What Is This
A solo business simulation game. You're the CEO of an automotive company. Each turn = 1 month. You read emails, chat your decisions to an LLM, and watch the consequences unfold. Compete against AI-run companies on a leaderboard.

### What It Is NOT
- Not multiplayer (MVP is solo vs AI)
- Not a dashboard with buttons and sliders
- Not a full economic simulation
- Not a UI-heavy game

### The Core Loop

```
┌──────────────────────────────────────────────────────┐
│  START MONTH                                         │
│  ├── LLM generates 3-5 contextual emails             │
│  ├── Player reads inbox                             │
│  ├── Player chats decisions (free text, no buttons)  │
│  ├── LLM resolves each decision → narrative + $      │
│  ├── Memory compacted (state JSON + hierarchical)    │
│  └── Repeat until player hits "End Month"            │
│                                                      │
│  END MONTH                                          │
│  ├── Financials calculated (cash, revenue, burn)    │
│  ├── Leaderboard updated                            │
│  └── If cash < $0 → GAME OVER (elimination)         │
└──────────────────────────────────────────────────────┘
```

### The 3 Hooks (Why People Come Back)

| Hook | How It Hits |
|------|-------------|
| **Numbers** | Cash position changes after every decision. Revenue trending up/down. Market share as a % against competitors. Number go up = dopamine. |
| **Narrative** | The LLM doesn't just give you numbers — it tells a story. "Your CFO warns that cash reserves won't last 3 months at this burn rate." vs "After 6 months of R&D, your EV platform just won a government tender worth $50M." |
| **Competition** | AI competitors on the leaderboard. You see them pulling ahead. You see them fumble. "NovaTech just recalled 40,000 vehicles — their stock dropped 15%." Your rank matters. |

---

## 2. Architecture

### Stack

```
┌─────────────────────────────────┐
│  React 19 + Vite               │  Single-page, no scrolling.
│  CSS Modules (no UI library)    │  3 panels: Inbox | Chat | Sidebar
└────────────┬────────────────────┘
             │ REST (no WebSocket for MVP)
             │
┌────────────▼────────────────────┐
│  FastAPI                         │
│  ├── /api/v1/*                   │  Game state, inbox, decisions
│  ├── SQLite (aiosqlite)          │  Single file DB, no infrastructure
│  └── OpenRouter client           │  Model routing via OpenRouter API
│  └── 3-Layer Memory Engine      │  Structured state + hierarchical memory
└────────────┬────────────────────┘
             │
┌────────────▼────────────────────┐
│  OpenRouter                      │
│  └── Model routing by task       │  Events: haiku-class (cheap)
│                                   │  Decisions: sonnet-class
│                                   │  Memory compaction: haiku-class
│  Total per month: ~$0.04         │
└─────────────────────────────────┘
```

### Why This Stack

| Choice | Why |
|--------|-----|
| **No auth** | Solo game. One browser tab = one game. localStorage holds player_id. |
| **SQLite** | Zero infrastructure. One file. Perfect for MVP. Upgrade to Postgres later if needed. |
| **No WebSocket** | MVP doesn't need real-time. The game is turn-based. |
| **OpenRouter** | One API key, any model. Route cheap models for emails, better models for key moments. |
| **No UI library** | Dark theme, 3 panels, CSS is ~300 lines. MUI would add 2MB for nothing. |
| **3-Layer Memory** | Fixed ~1,300 tokens regardless of game length. No context explosion at month 47. |

---

## 3. Memory Architecture

### The Problem

At month 47, a naive "append everything to the Fiche 10" approach produces 15,000+ tokens of linear history. The LLM loses the thread, costs explode, and continuity degrades.

**Solution: 3-Layer Memory** — fixed ~1,300 tokens regardless of game length.

### Layer 1: Structured State JSON (~800 tokens, always in-context)

Deterministic. No LLM needed. Updated after every decision via code.

```json
{
  "company": "Vento Motors",
  "ceo": "Vincenzo",
  "style": "aggressive",
  "risk_tolerance": "high",
  "month": 47,
  "cash": 14200000,
  "revenue": 8500000,
  "market_share": 12.3,
  "employees": 340,
  "burn_rate": 2100000,
  "revenue_trend": "growing",
  "cash_trend": "stable",
  "key_relationships": {
    "board": "pleased",
    "suppliers": "strained_after_battery_contract",
    "government": "favorable_EV_subsidy"
  },
  "active_threads": [
    "EV_platform_launch_M42",
    "European_expansion",
    "board_demands_profitability"
  ],
  "flags": {
    "ev_platform_launched": true,
    "european_expansion": true,
    "battery_supply_secured": true,
    "recall_risk": false
  }
}
```

This replaces 47 lines of "M1: cash $8.2M, Revenue $1.5M → ..." with one compact object. **80-95% token reduction vs. linear history.**

### Layer 2: Hierarchical Memory (~500 tokens, always in-context)

3 granularity levels. Managed by Haiku after each decision:

```
## Recent (M45-M47, verbatim)
- M45: Acquired battery supplier for $3.2M → supply chain secured, board approves
- M46: EV platform launched → $1.8M revenue in first month, market share +2.1%
- M47: European expansion delayed by regulatory hurdles → $400K in legal fees

## Period Summary (M20-M44)
European expansion drove revenue from $3M to $7M, but burned cash reserves.
Board demanded profitability by M30. CEO pivoted from marketing to R&D in M28.
Key supplier deal with CATL in M22 secured battery supply. Recall in M33 cost $1.2M.

## Origin Story (M1-M19)
Founded as budget sedan maker. Early R&D underfunded. Key pivot: EV platform
decision in M15 after board pressure. Market share grew from 5% to 8%.
```

**Compaction rules:**
- Last 3 months → verbatim (1 line per decision)
- M4 to M-20 → 1 paragraph summary, recompressed every 5 months
- M21+ → 1-2 sentence archive, recompressed every 10 months

### Layer 3: Important Events DB (SQLite, on-demand retrieval)

Not in-context by default. Retrieved when the player references a past event.

```sql
decisions
  importance REAL DEFAULT 0.5    -- 0-1 scale, scored by LLM at resolution time

-- High importance (>= 0.8): "Acquired battery supplier", "Launched EV platform"
-- Low importance (< 0.3): "Cut marketing by 5%", "Hired 2 engineers"
```

If the player asks "What happened with the battery deal?", the game retrieves the full decision from SQLite and injects it into context for that turn only.

### Token Budget Comparison

| Approach | M1 | M10 | M24 | M47 |
|----------|----|----|----|----|
| **Linear Fiche 10** (old) | 500 | 2,000 | 5,000 | 15,000+ |
| **3-Layer Memory** (new) | 1,300 | 1,300 | 1,300 | 1,300 |
| **Full conversation history** (naive) | 1,000 | 10,000 | 30,000 | 100,000+ |

**Fixed cost. No context explosion. Works at month 5 or month 50.**

### Research Sources

| Technique | Source | Applied As |
|-----------|--------|------------|
| Structured State Tracking | MemoryBank, Wang et al. 2024 | Layer 1 (JSON state) |
| Hierarchical Memory Summarization | Recallen, StreaK 2024-25 | Layer 2 (3-level compression) |
| Importance-Weighted Memory | Generative Agents, Park 2023-24 | Layer 3 (importance scoring) |
| MemGPT virtual memory paging | Packer et al. 2024 | On-demand retrieval from DB |

---

## 4. Data Model

### SQLite Tables (6 tables, zero joins in the hot path)

```sql
-- Player state (single row per game)
players
  id TEXT PK
  name TEXT, company_name TEXT
  industry TEXT DEFAULT 'automotive'
  style TEXT DEFAULT 'balanced'       -- aggressive | balanced | conservative | innovation
  risk_tolerance TEXT DEFAULT 'medium'
  current_month INT DEFAULT 0
  cash REAL DEFAULT 10000000
  revenue REAL DEFAULT 0
  market_share REAL DEFAULT 5.0
  employees INT DEFAULT 50
  created_at TIMESTAMP

-- Structured game state (Layer 1 memory — JSON blob)
game_states
  id INT PK AUTOINCREMENT
  player_id TEXT FK → players.id      -- 1:1 with player
  state_json TEXT                      -- the full JSON object (Layer 1)
  updated_at TIMESTAMP

-- Hierarchical memory (Layer 2 memory — markdown text)
memories
  id INT PK AUTOINCREMENT
  player_id TEXT FK → players.id      -- 1:1 with player
  recent TEXT                          -- last 3 months verbatim
  period_summary TEXT                  -- 1 paragraph for M4 to M-20
  origin_story TEXT                    -- 1-2 sentences for oldest months
  period_start INT                     -- month where period_summary begins
  period_end INT                       -- month where period_summary ends
  updated_at TIMESTAMP

-- Inbox messages
messages
  id INT PK AUTOINCREMENT
  player_id TEXT FK → players.id
  month INT
  sender TEXT                         -- "Board", "CFO", "Market", "Supplier", "Regulator"
  subject TEXT
  body TEXT
  category TEXT                       -- info | warning | opportunity | crisis | board
  is_read BOOLEAN DEFAULT FALSE
  requires_action BOOLEAN DEFAULT FALSE

-- Player decisions (free text + LLM outcome + importance)
decisions
  id INT PK AUTOINCREMENT
  player_id TEXT FK → players.id
  month INT
  decision_text TEXT                   -- what the player typed
  outcome TEXT                         -- narrative result
  importance REAL DEFAULT 0.5          -- 0-1, scored by LLM
  cash_impact REAL DEFAULT 0
  revenue_impact REAL DEFAULT 0
  market_impact REAL DEFAULT 0

-- AI competitors (pre-seeded, formula-driven)
competitors
  id TEXT PK                           -- "novatech", "autovista", "drivex"
  name TEXT
  style TEXT
  base_growth REAL
  volatility REAL
  cash REAL
  revenue REAL
  market_share REAL
```

### What Changed vs. Original Design

| Before | After | Why |
|--------|-------|-----|
| `monthly_reports` table | Removed | `game_states` JSON + `memories` replaces it with less schema |
| `leaderboard` table | Removed | Denormalized — computed on the fly from players + competitors |
| Fiche 10 `.md` file | `game_states` JSON + `memories` table | Structured state is more compact and deterministic |
| `decisions.importance` | New field | Enables importance-weighted retrieval (Layer 3) |
| `competitors.cash/revenue/market_share` | New fields | Competitors need persistent state between months |

---

## 5. API Endpoints (8 endpoints, that's it)

```
POST   /api/v1/players                    → Create player + game state + memory
GET    /api/v1/players/{id}               → Get player state
GET    /api/v1/players/{id}/memory        → Get 3-layer memory (state JSON + hierarchical text)

POST   /api/v1/players/{id}/start-month   → Generate inbox emails, advance month
POST   /api/v1/players/{id}/decide         → Submit free-text decision, get outcome + compact memory
POST   /api/v1/players/{id}/end-month      → Close month, update financials

GET    /api/v1/players/{id}/inbox          → List inbox messages
GET    /api/v1/leaderboard                 → Player + AI competitors, sorted by cash
```

**No auth, no sessions, no tokens.** Player ID stored in localStorage. That's it for MVP.

---

## 6. LLM Integration

### OpenRouter Configuration

```python
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Model routing by task (cost-optimized)
MODEL_EVENTS    = "anthropic/claude-3.5-haiku"   # Cheap, fast, generates emails
MODEL_DECIDE    = "anthropic/claude-3.5-sonnet"   # Better reasoning for outcomes
MODEL_COMPACT   = "anthropic/claude-3.5-haiku"    # Memory compaction, cheap is fine
```

### LLM Calls Per Month

| Call | When | Model | Input | Output |
|------|------|-------|-------|--------|
| **generate_events** | Player clicks "Start Month" | Haiku | Layer 1 (state JSON) + Layer 2 (memory) + month | 3-5 inbox emails (JSON) |
| **resolve_decision** | Player sends chat message | Sonnet | Layer 1 + Layer 2 + current state + decision text | Narrative + financial impacts + importance score (JSON) |
| **compact_memory** | After each decision | Haiku | Current memory + new event | Updated recent/summary/archive text |

### System Prompt (Core Engine)

The prompt receives the 3-layer memory structure, not a flat file:

```
You are the game engine for Pax Venture, an automotive business simulation.
You generate realistic, specific, dramatic business events.

GAME STATE (always accurate):
{state_json}

RECENT EVENTS (last 3 months, detailed):
{recent_verbatim}

PERIOD SUMMARY (M{start}-M{end}):
{period_summary}

ORIGIN STORY (M1-M{early_end}):
{origin_story}

ACTIVE THREADS:
{active_threads_list}

CRITICAL RULES:
1. Be specific to the automotive industry (models, suppliers, factories, regulations)
2. Numbers must be realistic — a $10M company doesn't win $500M contracts
3. Consequences cascade — a hiring freeze in month 3 affects morale in month 5
4. Cash is king — track it ruthlessly. If it goes negative, the game ends
5. The player is not a superhero — bad decisions should hurt
6. Generate drama: rivalries, market shifts, supply chain crises, government regulation
7. Every email should feel like it arrived on a real CEO's desk
8. Reference active threads and past events from the memory above — continuity matters
9. Output an importance score (0-1) for every decision resolution

INDUSTRY CONTEXT:
- Global automotive market, EV transition happening
- Traditional OEMs fighting Tesla and Chinese entrants
- Supply chain fragility (chips, batteries, rare earth)
- Regulatory pressure (emissions, safety, tariffs)
- Consumer sentiment shifting toward sustainability

Never break character. Never give meta-commentary about the simulation.
```

### Competitor AI (No LLM — Pure Formula)

Competitors don't need LLM calls. They run on simple math:

```python
def simulate_competitor(comp, month):
    base = comp.base_growth       # e.g. 0.08 = 8% monthly growth
    noise = random.gauss(0, comp.volatility)
    month_effect = 0.02 * math.sin(month * 0.5)  # seasonal cycle
    
    revenue_multiplier = 1 + base + noise + month_effect
    
    # Seed the initial state
    comp.revenue *= revenue_multiplier
    comp.cash += comp.revenue - comp.expenses
    comp.market_share += random.gauss(0, 0.3)  # small random walk
    
    # Quarterly disaster chance (3% per quarter)
    if month % 3 == 0 and random.random() < 0.03:
        disaster_scale = random.uniform(0.1, 0.3)
        comp.cash *= (1 - disaster_scale)
        comp.market_share *= (1 - disaster_scale * 0.5)
```

This gives the leaderboard organic movement without burning LLM tokens.

---

## 7. UI Layout (Single Screen, No Scroll)

```
┌─────────────────────────────────────────────────────────────────┐
│  PAX VENTURE                              Month 4  │ $7.2M  │
├───────────────────────────────────┬─────────────────────────────┤
│                                   │  CASH POSITION              │
│  INBOX                            │  Cash: $7,200,000           │
│  ─────────────────────────────   │  Revenue: $2.1M/mo         │
│  👔 Board | Q4 targets           │  Market: 7.2%              │
│     "Revenue is below..."   [!]  │  Status: Burn rate high    │
│  📨 Market | EV subsidy news      │                             │
│     "The government just..."      │  ── YOUR COMPANY ──         │
│  💡 Supplier | Battery deal       │  Vento Motors              │
│     "CATL offers 15%..."          │  Style: Aggressive         │
│  🔥 Crisis | Plant fire           │  Risk: High                │
│     "A fire broke out..."    [!]  │                             │
│                                   ├─────────────────────────────┤
│  ── SELECTED EMAIL ──             │  LEADERBOARD                │
│  From: Board of Directors         │  #1 NovaTech   $28.4M      │
│                                   │  #2 AutoVista  $19.1M      │
│  "Revenue is 15% below Q4         │  #3 DriveX     $14.7M     │
│   targets. The board demands      │  #4 ▸ YOU      $7.2M      │
│   a cost reduction plan by        │  #5 GreenWheel  $3.8M      │
│   end of month or we consider     │                             │
│   leadership changes."             │  [Cash] [Revenue] [Mkt%]  │
│                                   │                             │
│  Action required — respond        │                             │
│  below                            │                             │
├───────────────────────────────────┤                             │
│  DECISIONS                        │                             │
│                                   │                             │
│  You: I'll cut marketing by 30%  │                             │
│  and redirect that to R&D for     │                             │
│  the EV platform.                 │                             │
│                                   │                             │
│  Result: Bold gamble. Marketing   │                             │
│  cut executed. $480K saved. R&D   │                             │
│  team expands to 12 engineers.   │                             │
│  Board noted the restructuring    │                             │
│  positively.                      │                             │
│  Cash: -$480K  Revenue: +$120K   │                             │
│                                   │                             │
│  ┌─────────────────────────────┐ │                             │
│  │ Describe your next move...   │ │                             │
│  └───────────────────────── [→] ┘ │                             │
│                                   │                             │
│  [Start Month 5]    [End Month]   │                             │
└───────────────────────────────────┴─────────────────────────────┘
```

### Interaction Rules

1. **Chat is the ONLY input** — no buttons, no dropdowns, no sliders
2. **Start Month** button generates the inbox (the only "system" action)
3. **End Month** button closes the month and calculates financials
4. Player can make **multiple decisions per month** (each resolved immediately)
5. Each decision shows the **narrative outcome + financial impact** inline
6. Game over screen when **cash < $0** — "Your company has gone bankrupt"

---

## 8. Game Mechanics

### Starting State

| Metric | Value |
|--------|-------|
| Starting cash | $10,000,000 |
| Starting revenue | $0/month |
| Starting market share | 5.0% |
| Starting employees | 50 |
| Industry | Automotive |

### Monthly Economics (Base)

The LLM decides specific impacts, but the base economy provides guardrails:

```
Base monthly expenses:
  - Payroll: $50K/employee × employee_count
  - Overhead: $200K (office, admin, legal)
  - Total base burn at start: ~$2.7M/month

Revenue is entirely LLM-driven based on decisions.
The LLM must respect realistic scaling:
  - M1-M3: $0-2M/month (ramp-up)
  - M4-M8: $1-5M/month (growth)
  - M9-M12: $3-10M/month (maturity or failure)
```

### Elimination Rule

**Cash < $0 = Game Over.** No bailouts, no second chances.

The LLM is instructed: "If the player's cash would go below $0 after this decision, warn them in the narrative that they are dangerously close to bankruptcy."

### Victory

No explicit win condition. The game ends when:
- Player goes bankrupt (cash < $0) → **GAME OVER** screen
- Player chooses to stop → final leaderboard ranking

Implicit goal: survive 24 months with the most cash.

---

## 9. Competitor Profiles (Pre-seeded AI)

| ID | Name | Style | Base Growth | Volatility | Starting Cash |
|----|------|-------|-------------|------------|---------------|
| novatech | NovaTech | Aggressive | 8% | 5% | $15M |
| autovista | AutoVista | Conservative | 5% | 2% | $20M |
| drivex | DriveX | Balanced | 6% | 4% | $12M |
| greenwheel | GreenWheel | Innovation | 10% | 7% | $8M |

Formula-driven. No LLM calls. They provide benchmark and leaderboard drama.

Quarterly disaster events (3% chance) add narrative: recalls, CEO scandals, supply chain failures.

---

## 10. LLM Cost Estimate

Per month of gameplay:

| Call | Tokens In | Tokens Out | Model | Cost |
|------|-----------|------------|-------|------|
| generate_events | ~1,800 | ~500 | Haiku | ~$0.003 |
| resolve_decision (×3 avg) | ~1,800 × 3 | ~300 × 3 | Sonnet | ~$0.027 |
| compact_memory (×3 avg) | ~1,000 × 3 | ~400 × 3 | Haiku | ~$0.006 |
| **Total per month** | | | | **~$0.036** |
| **Full 24-month game** | | | | **~$0.86** |
| **Full 50-month game** | | | | **~$1.80** |

Token count stays fixed at ~1,300 per call regardless of game length (3-layer memory).
OpenRouter pricing. Can be halved by using Haiku for decisions (less dramatic, more consistent).

---

## 11. File Structure (Final)

```
pax-venture/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, lifespan
│   │   ├── core/
│   │   │   ├── config.py           # Settings (OpenRouter key, model routing)
│   │   │   ├── database.py         # SQLAlchemy async init
│   │   │   └── llm.py              # 3 LLM functions + OpenRouter client
│   │   ├── models/
│   │   │   └── game.py             # Player, Game State, Memory, Message, Decision, Competitor
│   │   ├── services/
│   │   │   ├── game_engine.py      # Start month, decide, end month, leaderboard
│   │   │   ├── memory.py           # 3-layer memory compaction engine
│   │   │   └── competitors.py      # Formula-driven AI competitor simulation
│   │   └── api/
│   │       └── routes.py           # 8 REST endpoints
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # Main layout, state management
│   │   ├── main.jsx                # React root
│   │   ├── components/
│   │   │   ├── CashPanel.jsx       # Cash + metrics
│   │   │   ├── Inbox.jsx           # Email list + detail view
│   │   │   ├── ChatPanel.jsx       # Free-text chat + LLM responses
│   │   │   ├── Leaderboard.jsx     # Player + AI competitors
│   │   │   └── NewPlayerModal.jsx   # Onboarding
│   │   └── styles/
│   │       └── global.css          # Dark theme, Football Manager layout
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── docs/
│   └── MVP_ENGINEERING.md          # This file
└── README.md
```

---

## 12. Implementation Order

### Phase 1: Core Loop + Memory (Days 1-2)
1. **LLM integration** — OpenRouter client, generate_events, resolve_decision
2. **3-Layer Memory engine** — GameState JSON, hierarchical memory, importance scoring
3. **Game engine** — create_player, start_month, submit_decision, end_month
4. **API routes** — all 8 endpoints (replace `/fiche` with `/memory`)

**Validate**: Can I start a game, get emails, chat a decision, and see memory compaction work?

### Phase 2: Frontend (Days 2-3)
5. **Layout** — 3-panel dark theme, no page scroll
6. **Inbox** — list + detail view
7. **Chat panel** — free-text input, LLM responses
8. **Cash panel** — big numbers, month counter

**Validate**: Does the UI feel good? Does the chat feel natural?

### Phase 3: Competition (Day 3)
9. **Competitor simulation** — formula-driven, seeded in DB
10. **Leaderboard** — player + AI, sortable
11. **Memory compaction** — verify hierarchical compression at M10, M20, M40

**Validate**: Does seeing competitors motivate? Does memory stay compact at high months?

### Phase 4: Polish (Day 4)
12. **Elimination screen** — cash < $0 game over
13. **Memory retrieval** — "what happened with X?" searches decisions by importance
14. **Chat history** — show past decisions inline
15. **Error handling** — LLM failures, rate limits

**Validate**: Is the player saying "just one more month"?

---

## 13. What We're NOT Building (Yet)

| Feature | Why Not Now |
|---------|-------------|
| Auth / accounts | localStorage player_id is enough |
| Multiplayer | Solo validates the fun loop first |
| WebSocket | Turn-based, no real-time need |
| Charts / graphs | Numbers in text suffice for MVP |
| Sound / music | Nice-to-have, not core loop |
| Save / load | localStorage or URL parameter for now |
| Mobile responsive | Desktop-first for CEO simulation |
| Multiple industries | Automotive only, validate the mechanic |
| Admin dashboard | Not needed for 10 users |
| Rate limiting | OpenRouter handles it |
| Vector DB / RAG | SQLite + importance scoring suffices for MVP |

---

## 14. Success Metric

**The only question that matters after someone plays 3 months:**

> "Do you want to play another month?"

If yes → the loop works. Iterate on narrative quality and competitor dynamics.
If no → the LLM responses aren't dramatic enough, or the numbers don't create tension.

**Secondary signals:**
- Player reads all emails before deciding (narrative quality)
- Player makes 2+ decisions per month (engagement with chat)
- Player checks leaderboard after end-month (competition works)