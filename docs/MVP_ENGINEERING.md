# Pax Venture — MVP RFC

**Status**: DRAFT  
**Goal**: Validate that a month-by-month CEO simulation driven by LLM chat is addictive.  
**Rule**: Solo, automotive, chat-only input, cash < $0 = elimination.

---

## 1. Core Loop

```
START_MONTH
  → LLM generates 3-5 emails (Haiku)
  → Player reads inbox
  → Player types decision (free text)
  → LLM resolves decision (Sonnet) → narrative + financial impacts + importance score
  → Memory compacted (Haiku)
  → Repeat until player clicks END_MONTH
END_MONTH
  → Apply monthly payroll & overhead
  → Update competitor states (formula)
  → Recalculate leaderboard
  → Check cash < $0 → GAME OVER
```

**Constraints**:
- Chat is the ONLY input. No buttons, no dropdowns, no sliders (except Start/End Month).
- Player can submit 1-10 decisions per month.
- Each decision is resolved immediately (no queuing).

---

## 2. Data Model

### players

```sql
CREATE TABLE players (
    id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    name          TEXT NOT NULL,
    company_name  TEXT NOT NULL,
    style         TEXT NOT NULL DEFAULT 'balanced'
                  CHECK(style IN ('aggressive','balanced','conservative','innovation')),
    risk_tolerance TEXT NOT NULL DEFAULT 'medium'
                  CHECK(risk_tolerance IN ('low','medium','high')),
    current_month  INTEGER NOT NULL DEFAULT 0,
    cash           REAL NOT NULL DEFAULT 10000000,
    revenue        REAL NOT NULL DEFAULT 0,
    market_share   REAL NOT NULL DEFAULT 5.0,
    employees      INTEGER NOT NULL DEFAULT 50,
    game_over      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Note**: `cash`, `revenue`, `market_share`, `employees` live in `players` (the source of truth). `game_states.state_json` holds the LLM-facing denormalized view (relationships, flags, threads) — NOT duplicated numeric fields.

### game_states (Layer 1 — LLM context, denormalized)

```sql
CREATE TABLE game_states (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   TEXT NOT NULL UNIQUE REFERENCES players(id),
    state_json  TEXT NOT NULL,  -- See Section 3 for frozen schema
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### memories (Layer 2 — hierarchical text)

```sql
CREATE TABLE memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       TEXT NOT NULL UNIQUE REFERENCES players(id),
    recent          TEXT NOT NULL DEFAULT '',  -- Last 3 months, 1 line per decision
    period_summary  TEXT NOT NULL DEFAULT '',  -- 1 paragraph covering M4 to current-3
    period_start    INTEGER NOT NULL DEFAULT 0,
    period_end      INTEGER NOT NULL DEFAULT 0,
    origin_story    TEXT NOT NULL DEFAULT '',  -- 1-2 sentences for oldest months
    origin_end      INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### messages (inbox)

```sql
CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       TEXT NOT NULL REFERENCES players(id),
    month           INTEGER NOT NULL,
    sender          TEXT NOT NULL,  -- "Board"|"CFO"|"Market"|"Supplier"|"Regulator"|"Rival"
    subject         TEXT NOT NULL,
    body            TEXT NOT NULL,
    category        TEXT NOT NULL CHECK(category IN ('info','warning','opportunity','crisis','board')),
    is_read         BOOLEAN NOT NULL DEFAULT FALSE,
    requires_action BOOLEAN NOT NULL DEFAULT FALSE
);
```

### decisions

```sql
CREATE TABLE decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       TEXT NOT NULL REFERENCES players(id),
    month           INTEGER NOT NULL,
    decision_text   TEXT NOT NULL,
    outcome         TEXT NOT NULL,         -- Narrative result
    importance      REAL NOT NULL DEFAULT 0.5 CHECK(importance BETWEEN 0 AND 1),
    cash_impact     REAL NOT NULL DEFAULT 0,
    revenue_impact  REAL NOT NULL DEFAULT 0,
    market_impact   REAL NOT NULL DEFAULT 0
);
```

### competitors

```sql
CREATE TABLE competitors (
    id            TEXT PRIMARY KEY,  -- "novatech"|"autovista"|"drivex"|"greenwheel"
    name          TEXT NOT NULL,
    style         TEXT NOT NULL,
    base_growth   REAL NOT NULL,     -- Monthly revenue growth rate (e.g. 0.08)
    volatility    REAL NOT NULL,     -- Std dev of noise (e.g. 0.05)
    expenses      REAL NOT NULL,     -- Fixed monthly expenses
    cash          REAL NOT NULL,
    revenue       REAL NOT NULL DEFAULT 0,
    market_share  REAL NOT NULL DEFAULT 0
);
```

**Seeded on player creation:**

| id | name | style | base_growth | volatility | expenses | cash | revenue | market_share |
|----|------|-------|-------------|------------|----------|------|---------|-------------|
| novatech | NovaTech | aggressive | 0.08 | 0.05 | 1200000 | 15000000 | 3000000 | 12.0 |
| autovista | AutoVista | conservative | 0.05 | 0.02 | 1800000 | 20000000 | 5000000 | 18.0 |
| drivex | DriveX | balanced | 0.06 | 0.04 | 900000 | 12000000 | 2000000 | 8.0 |
| greenwheel | GreenWheel | innovation | 0.10 | 0.07 | 600000 | 8000000 | 1000000 | 3.0 |

### leaderboard (pre-computed cache)

```sql
CREATE TABLE leaderboard (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id     TEXT NOT NULL,       -- player.id or competitor.id
    company_name  TEXT NOT NULL,
    entity_type   TEXT NOT NULL CHECK(entity_type IN ('player','competitor')),
    cash          REAL NOT NULL,
    revenue       REAL NOT NULL,
    market_share  REAL NOT NULL,
    current_month INTEGER NOT NULL,
    rank          INTEGER NOT NULL
);
```

---

## 3. Layer 1 — Frozen JSON Schema

This is the exact shape sent to the LLM on every call. **All fields are required.**

```json
{
    "company": "string",
    "ceo": "string",
    "style": "aggressive|balanced|conservative|innovation",
    "risk_tolerance": "low|medium|high",
    "month": "integer >= 0",
    "cash": "number",
    "revenue": "number >= 0",
    "market_share": "number 0-100",
    "employees": "integer >= 1",
    "burn_rate": "number >= 0",
    "revenue_trend": "growing|stable|declining",
    "cash_trend": "growing|stable|declining|critical",
    "key_relationships": {
        "board": "pleased|neutral|concerned|hostile",
        "suppliers": "string (free text, max 40 chars)",
        "government": "favorable|neutral|hostile"
    },
    "active_threads": ["string (max 5 items)"],
    "flags": {
        "ev_platform_launched": "boolean",
        "european_expansion": "boolean",
        "battery_supply_secured": "boolean",
        "recall_risk": "boolean"
    }
}
```

**Deterministic updates** (no LLM needed):
- `cash` += `cash_impact` from last decision
- `revenue` += `revenue_impact` from last decision
- `market_share` += `market_impact` from last decision
- `employees` is LLM-driven (returned in resolve_decision output)
- `burn_rate` = `payroll + overhead` (formula, see Section 6)
- `revenue_trend`: "growing" if last 3 months revenue increased, "declining" if decreased, else "stable"
- `cash_trend`: "growing" if cash > 2× burn_rate, "stable" if cash > burn_rate, "critical" if cash < burn_rate, "declining" otherwise
- `key_relationships`, `active_threads`, `flags`: updated by `compact_memory` LLM call

**Initial state on creation:**
```json
{
    "company": "{from_player_input}",
    "ceo": "{from_player_input}",
    "style": "{from_player_input}",
    "risk_tolerance": "{from_player_input}",
    "month": 0,
    "cash": 10000000,
    "revenue": 0,
    "market_share": 5.0,
    "employees": 50,
    "burn_rate": 2700000,
    "revenue_trend": "stable",
    "cash_trend": "growing",
    "key_relationships": {"board": "neutral", "suppliers": "stable", "government": "neutral"},
    "active_threads": [],
    "flags": {"ev_platform_launched": false, "european_expansion": false, "battery_supply_secured": false, "recall_risk": false}
}
```

---

## 4. LLM Contracts

### 4a. generate_events (Haiku) — called on Start Month

**Input**: System prompt (Section 5) + Layer 1 state JSON + Layer 2 memory text + `current_month`

**Output** (strict JSON schema):
```json
{
    "emails": [
        {
            "sender": "CFO|Board|Market|Supplier|Regulator|Rival",
            "subject": "string (max 80 chars)",
            "body": "string (max 300 chars, in-character email text)",
            "category": "info|warning|opportunity|crisis|board",
            "requires_action": "boolean"
        }
    ]
}
```
- Always generate 3-5 emails.
- At least 1 email must reference an `active_thread` or `flag` from the state.
- At month 1, first email is always from the Board welcoming the new CEO.

### 4b. resolve_decision (Sonnet) — called on each player message

**Input**: System prompt + Layer 1 + Layer 2 + current month's inbox emails + `decision_text`

**Output** (strict JSON schema):
```json
{
    "narrative": "string (max 500 chars, dramatic business outcome)",
    "cash_impact": "number (negative = cost, positive = gain)",
    "revenue_impact": "number (monthly revenue change, 0 if no immediate effect)",
    "market_impact": "number (percentage points, typically -2.0 to +2.0)",
    "importance": "number 0-1 (0.8+ = major event like acquisition, < 0.3 = minor adjustment)",
    "employees_change": "integer (net headcount change, 0 if no change)",
    "relationship_updates": {
        "board": "pleased|neutral|concerned|hostile (only if changed)",
        "suppliers": "string (only if changed)",
        "government": "favorable|neutral|hostile (only if changed)"
    },
    "new_threads": ["string (0-2 new active threads, max 40 chars each)"],
    "flag_updates": {
        "flag_name": "boolean (only flags that change)"
    }
}
```

### 4c. compact_memory (Haiku) — called after each decision

**Input**: Current `recent` + `period_summary` + `origin_story` + new decision line (month, text, outcome)

**Output** (strict JSON schema):
```json
{
    "recent": "string (last 3 months, 1 line per month, format: 'M{n}: {one_line_summary}')",
    "period_summary": "string (1 paragraph, max 200 chars)",
    "origin_story": "string (1-2 sentences, max 120 chars)"
}
```

**Compaction trigger rules** (deterministic, no LLM judgment):
- `recent`: Keep lines for months `[current-2, current-1, current]`. Always exactly 3 lines (or fewer if month < 3). When a 4th line would be added, the oldest line is absorbed into `period_summary`.
- `period_summary`: Re-summarized by Haiku when `current_month >= recent_oldest_month + 5`. That is, every 5 months, the LLM rewrites the period summary to cover a wider span.
- `origin_story`: Re-summarized when `period_summary` would cover more than 20 months. Always 1-2 sentences.

---

## 5. System Prompt (Frozen)

```
You are the game engine for Pax Venture, an automotive business simulation.
You generate realistic, specific, dramatic business events.

GAME STATE:
{state_json}

RECENT EVENTS:
{recent}

PERIOD SUMMARY:
{period_summary}

ORIGIN STORY:
{origin_story}

ACTIVE THREADS:
{active_threads}

RULES:
1. Be specific to the automotive industry (models, suppliers, factories, regulations).
2. Numbers must be realistic for a company starting at $10M. Maximum single revenue impact: +$3M/month. Maximum single cost impact: -$5M. No lottery wins.
3. Consequences cascade — reference past decisions and active threads.
4. Cash < $0 = game over. Warn the player in narrative when cash drops below 2× monthly burn.
5. The player is not a superhero — bad decisions must hurt.
6. Every email should feel like it arrived on a real CEO's desk.
7. Output valid JSON matching the exact schema. No commentary outside JSON.
8. Importance scoring: 0.8+ = acquisition, launch, crisis. 0.3-0.5 = hiring, budget shift. < 0.3 = minor.
9. Revenue scaling: M1-M3: $0-2M/mo. M4-M8: $1-5M/mo. M9-M12: $3-10M/mo. M13+: $5-15M/mo.
10. Never break character. Never give meta-commentary about the simulation.

INDUSTRY CONTEXT:
- Global automotive market, EV transition happening
- Traditional OEMs fighting Tesla and Chinese entrants
- Supply chain fragility (chips, batteries, rare earth)
- Regulatory pressure (emissions, safety, tariffs)
```

---

## 6. Game Mechanics (Frozen Numbers)

### Starting State

| Metric | Value |
|--------|-------|
| Cash | $10,000,000 |
| Revenue | $0/month |
| Market share | 5.0% |
| Employees | 50 |
| Industry | Automotive |

### Monthly Economics (end_month calculation)

```
payroll = employees × 50000        -- $50K/employee/month
overhead = 200000                   -- $200K/month fixed (office, admin, legal)
burn_rate = payroll + overhead     -- stored in game_state

cash = cash - burn_rate + revenue  -- applied at end_month
```

### Financial Guards (applied after LLM returns resolve_decision)

```python
# Clamp LLM outputs to prevent absurdity
cash_impact = clamp(decision.cash_impact, -5000000, 3000000)      # max $5M cost, $3M gain
revenue_impact = clamp(decision.revenue_impact, -2000000, 5000000) # revenue can grow faster
market_impact = clamp(decision.market_impact, -3.0, 3.0)           # max ±3 percentage points
```

### End-of-Month Flow

```python
async def end_month(player_id):
    player = get_player(player_id)
    
    # 1. Apply fixed expenses
    payroll = player.employees * 50000
    overhead = 200000
    player.cash -= (payroll + overhead)
    player.revenue -= 0  # revenue unchanged, already tracked via decisions
    
    # 2. Simulate competitors
    for comp in get_competitors():
        simulate_competitor(comp, player.current_month)
    
    # 3. Update leaderboard
    rebuild_leaderboard(player_id)
    
    # 4. Advance month
    player.current_month += 1
    
    # 5. Check elimination
    if player.cash < 0:
        player.game_over = True
    
    # 6. Update game_state Layer 1 (deterministic)
    state = update_state_json(player)
    save(state)
    
    return player
```

### Competitor Simulation (pure formula, no LLM)

```python
def simulate_competitor(comp, month):
    """Called once per competitor at end_month."""
    base = comp.base_growth
    noise = random.gauss(0, comp.volatility)
    seasonal = 0.02 * math.sin(month * 0.5)
    
    comp.revenue *= (1 + base + noise + seasonal)
    comp.cash += comp.revenue - comp.expenses
    comp.market_share = max(0.1, comp.market_share + random.gauss(0, 0.3))
    
    # Quarterly disaster: 3% chance
    if month % 3 == 0 and random.random() < 0.03:
        scale = random.uniform(0.1, 0.3)
        comp.cash *= (1 - scale)
        comp.market_share *= (1 - scale * 0.5)
```

---

## 7. API Contract

### POST /api/v1/players

**Request:**
```json
{
    "name": "Vincenzo",
    "company_name": "Vento Motors",
    "style": "aggressive",
    "risk_tolerance": "high"
}
```

**Response (201):**
```json
{
    "id": "a1b2c3d4",
    "name": "Vincenzo",
    "company_name": "Vento Motors",
    "style": "aggressive",
    "risk_tolerance": "high",
    "current_month": 0,
    "cash": 10000000,
    "revenue": 0,
    "market_share": 5.0,
    "employees": 50,
    "game_over": false
}
```

Side effects: Creates `game_states` row (initial state), empty `memories` row, seeds 4 competitors.

### GET /api/v1/players/{id}

**Response (200):** Same as POST response above.

### GET /api/v1/players/{id}/memory

**Response (200):**
```json
{
    "state": { ... Layer 1 JSON ... },
    "recent": "M1: Launched budget sedan line → revenue $1.5M\nM2: ...",
    "period_summary": "...",
    "origin_story": "...",
    "active_threads": ["EV_platform_launch"]
}
```

### POST /api/v1/players/{id}/start-month

**Request:** `{}` (no body)

**Response (200):**
```json
{
    "month": 1,
    "emails": [
        {
            "id": 1,
            "sender": "Board",
            "subject": "Welcome to the helm",
            "body": "...",
            "category": "board",
            "requires_action": false
        }
    ]
}
```

Preconditions: `current_month` must be 0 or last month must be ended. Returns 409 if month already started. Increments `current_month`.

### POST /api/v1/players/{id}/decide

**Request:**
```json
{
    "text": "I'll cut marketing by 30% and redirect to R&D for the EV platform."
}
```

**Response (200):**
```json
{
    "narrative": "Bold gamble. Marketing cut executed — $480K saved. R&D team expands to 12 engineers. Board noted the restructuring positively but warns that brand visibility will drop within 2 months.",
    "cash_impact": -480000,
    "revenue_impact": 120000,
    "market_impact": -0.5,
    "importance": 0.7,
    "employees_change": 2,
    "updated_state": { ... Layer 1 JSON (post-decision) ... }
}
```

Preconditions: Month must be started (current_month > 0). Returns 409 if game_over is true.

### POST /api/v1/players/{id}/end-month

**Request:** `{}` (no body)

**Response (200):**
```json
{
    "month": 1,
    "cash": 7620000,
    "revenue": 1620000,
    "market_share": 4.5,
    "burn_rate": 2700000,
    "employees": 52,
    "game_over": false,
    "leaderboard": [
        {"rank": 1, "company_name": "AutoVista", "cash": 21500000, "revenue": 5150000, "market_share": 18.2},
        {"rank": 2, "company_name": "NovaTech", "cash": 16800000, "revenue": 3240000, "market_share": 12.3},
        {"rank": 3, "company_name": "DriveX", "cash": 13200000, "revenue": 2120000, "market_share": 8.3},
        {"rank": 4, "company_name": "Vento Motors", "cash": 7620000, "revenue": 1620000, "market_share": 4.5},
        {"rank": 5, "company_name": "GreenWheel", "cash": 8500000, "revenue": 1100000, "market_share": 3.2}
    ]
}
```

Preconditions: Month must be started. Returns 409 if already ended.

### GET /api/v1/players/{id}/inbox

**Response (200):**
```json
{
    "messages": [
        {
            "id": 1,
            "month": 1,
            "sender": "Board",
            "subject": "Q4 targets review",
            "body": "...",
            "category": "board",
            "is_read": false,
            "requires_action": true
        }
    ]
}
```

### GET /api/v1/leaderboard

**Response (200):** Same `leaderboard` array as in end-month response. No player_id required (global).

---

## 8. Error Handling

| Scenario | HTTP | Response |
|----------|------|----------|
| Player not found | 404 | `{"detail": "Player not found"}` |
| Start month when month already active | 409 | `{"detail": "Month already started"}` |
| Decide when game is over | 409 | `{"detail": "Game is over"}` |
| Decide before start-month | 409 | `{"detail": "Start the month first"}` |
| LLM rate limit (OpenRouter 429) | 502 | `{"detail": "AI service temporarily unavailable. Try again."}` |
| LLM returns invalid JSON | 502 | Retry once with same prompt. If still invalid, return 502 with `{"detail": "AI response error. Try again."}` |
| LLM returns out-of-bounds values | 200 | Apply clamps from Section 6. Return result with clamped values. |

---

## 9. Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Backend | FastAPI + SQLite (aiosqlite) | Zero infra, single file DB |
| Frontend | React 19 + Vite | Fast dev, no SSR needed |
| LLM | OpenRouter (OpenAI-compatible) | One key, any model |
| Model routing | Haiku for events/memory, Sonnet for decisions | Cost optimization |
| Auth | None | localStorage player_id |
| Realtime | None | Turn-based, REST only |

---

## 10. File Structure

```
pax-venture/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, lifespan, error handlers
│   │   ├── core/
│   │   │   ├── config.py           # OPENROUTER_API_KEY, MODEL_* constants
│   │   │   ├── database.py         # SQLAlchemy async, init_db creates tables + seeds competitors
│   │   │   └── llm.py             # generate_events(), resolve_decision(), compact_memory()
│   │   ├── models/
│   │   │   └── game.py            # All 7 SQLAlchemy models
│   │   ├── services/
│   │   │   ├── game_engine.py     # create_player, start_month, submit_decision, end_month
│   │   │   ├── memory.py          # get_memory_context(), update_memory(), compact_memory()
│   │   │   ├── state.py           # build_state_json(), update_state_json(), compute_trends()
│   │   │   └── competitors.py     # simulate_competitor(), seed_competitors(), rebuild_leaderboard()
│   │   └── api/
│   │       └── routes.py          # 8 endpoints, request/response models
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Layout, state, API calls
│   │   ├── main.jsx
│   │   ├── components/
│   │   │   ├── CashPanel.jsx     # Cash, revenue, market share, status
│   │   │   ├── Inbox.jsx         # Email list + detail
│   │   │   ├── ChatPanel.jsx     # Free-text input + LLM responses
│   │   │   ├── Leaderboard.jsx  # 5 competitors + player
│   │   │   └── NewPlayerModal.jsx
│   │   └── styles/
│   │       └── global.css        # Dark theme, no page scroll
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
└── docs/
    └── MVP_ENGINEERING.md        # This file
```

---

## 11. Implementation Order

| Phase | What | Validate |
|-------|------|----------|
| **1** | LLM integration (3 functions) + game engine + API routes + memory compaction | Start game → get emails → decide → see memory compact |
| **2** | Frontend layout + inbox + chat + cash panel | Does it feel like Football Manager? |
| **3** | Competitor simulation + leaderboard | Does competition create urgency? |
| **4** | Game over + error handling + polish | Does the player say "one more month"? |

---

## 12. What We're NOT Building

Auth, multiplayer, WebSocket, charts, sound, save/load, mobile responsive, multiple industries, admin dashboard, rate limiting, vector DB.