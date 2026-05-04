# Pax Venture — Engineering RFC v2 (Elite)

**Status**: DRAFT — supersedes v1.
**Vision**: Pax Historia, mais en version entreprise. Tu es CEO, l'LLM est le moteur du jeu, le chat est ton seul input. Interface: 1 inbox pour les news, 1 cash position, 1 leaderboard. Mois par mois, cash < $0 = élimination.
**Architecture**: Option A — LLM-as-engine, full state in prompt, structured output via tool-calling, multi-model routing through OpenRouter. Multi-industry data layout from day one; automotive content only for MVP.
**Rule**: Solo, chat-only input, cash < $0 = elimination.

---

## 0. Changes from v1 (audit-driven)

### Correctness fixes
| ID | Change |
|----|--------|
| A1 | End-of-month now applies `cash += revenue - burn_rate`. v1 forgot to add revenue, forcing game-over by M4. |
| A2 | `players.{cash, revenue, market_share, employees}` are projections of the `events` log. The Layer 1 state JSON is a view rebuilt on read, never persisted with numeric duplicates. |
| A3 | New `monthly_snapshots` table makes `revenue_trend` and `cash_runway` implementable. |
| A4 | `cash_trend` renamed to `cash_runway`, redefined as the numeric ratio `cash / burn_rate` and bucketed `comfortable | healthy | tight | critical`. |
| A5 | Memory compaction is end-of-month only (one Haiku call per month, not per decision). |
| A6 | `start_month` no longer increments `current_month`; only `end_month` does. |
| A7 | `employees_change` clamped per decision (industry-tunable, automotive default `[-10, +20]`). |
| A8 | `flag_updates` validated against the industry's closed flag vocabulary. Unknown flags rejected and logged. |
| A9 | LLM returns `closed_threads`. Threads are first-class rows with `importance`, `status`, `opened_at_month`. |
| A10 | `importance` drives memory compaction priority and thread eviction order. |

### Architecture upgrades
| ID | Change |
|----|--------|
| B1 | Prompt caching on the system + industry + long-memory block (`cache_control: ephemeral`). Target ≥85% input-token cache hit ratio mid-game. |
| B2 | All structured output via tool-calling (OpenAI function-call format), not prompted JSON. |
| B3 | SSE streaming on `/decide` and `/start-month`. |
| B4 | Competitors react to player flag transitions via pure-code FSM (`OBSERVING | DEFENSIVE | AGGRESSIVE | STRUGGLING`). Stochastic noise applied within posture. |
| B5 | Top-3 competitor summaries injected into the LLM context on every call. |
| B6 | `world_events` calendar — deterministic mechanical effects + narrative seeds the LLM must weave into emails. |
| B7 | Embedding index over decisions. Top-k retrieval injected into the resolve prompt. |
| B8 | `Idempotency-Key` header required on `/decide`, `/start-month`, `/end-month`. |
| B9 | `(prompt_version, schema_version, model, seed)` stamped on every event. |
| B10 | Server-side enforcement of every string-length limit and closed enum. Validators are first-class. |
| B11 | `llm_calls` telemetry table — tokens, $, latency, cache hits per call. |

### Multi-industry
| ID | Change |
|----|--------|
| C1 | `industries` table; all content (system prompt, financial constants, flag set, competitors, world events, intents) FKs to it. |
| C2 | Per-player competitors (`competitors.player_id` + `industries.id` composite scope). |
| C3 | `messages.parent_message_id` for threading. |

### New product layers
- **Multi-model routing** via OpenRouter (player-selectable: `cheap | balanced | premium`).
- **Game-over autopsy** — Sonnet generates a shareable end-of-game card.
- **Compression hook** (bear-1.1-equivalent) reserved as Phase 2; data layout supports it now.

---

## 1. Architectural pillars

These are invariants. Anything later that contradicts them is wrong, not them.

1. **The LLM is the engine.** Every numeric and qualitative game effect originates in an LLM tool call. The kernel enforces clamps, runs deterministic side-effect simulations (competitors, world events, end_month arithmetic), and persists.
2. **Tool-calling, not prompted JSON.** Structured output uses native function-calling via OpenRouter's OpenAI-compatible API. JSON validity is a guarantee, not a hope.
3. **Event-sourced.** `events` is append-only and authoritative. Every other numeric column is a projection. Replay, undo, A/B prompt comparisons, balance simulation in CI all fall out for free.
4. **Prompt caching by default.** The system + industry + long-memory block is `cache_control: ephemeral`. Cache hit ratio is a tracked metric; <70% mid-game triggers an alert.
5. **Multi-model routing.** Every LLM call accepts a model id. Defaults per call type. Player picks one of three tiers.
6. **Multi-industry from day one.** No industry-specific constants live in code. `industries` rows hold every variable. MVP ships one row.
7. **Idempotent at the request level.** Every mutating endpoint accepts `Idempotency-Key`. Replay = same response, no duplicate effect.
8. **Deterministic stamping.** Every event records `(prompt_version, schema_version, model, seed)`. Same script + same versions = same outcome.
9. **Streaming first.** Narrative streams over SSE; impacts commit at stream end.
10. **Closed vocabularies, server-validated.** Flags, intents, relationship enums, message categories — all closed sets per industry, validated server-side.
11. **Importance-weighted memory.** Compaction, thread eviction, retrieval weighting use `importance`.
12. **Embeddings for long-game coherence.** Every decision embedded; resolves retrieve top-k similar past decisions.
13. **Cost telemetry as a feature.** Per-call $ visible to the player; per-game cap configurable.
14. **No constraints enforced by prose.** Length and shape constraints live in tool schemas + post-call validators, never in system-prompt sentences.
15. **Reproducibility over cleverness.** When in doubt: store more (events, seeds, embeddings) and project less.

---

## 2. Core loop

```
SCENE: PLAYER STARTS MONTH N (POST /start-month, idempotency-keyed, SSE)
  → kernel: scheduled_world_events ← load(industry, month=N)
  → kernel: apply_mechanical_effects(scheduled_world_events)   # affects state used in prompt
  → llm: generate_inbox_emails(Haiku, tool="generate_inbox_emails")
        cached:  system + industry + period_summary + origin_story
        dynamic: state_view + recent + active_threads + flags + relationships
                 + competitor_briefs (top 3) + scheduled_world_events
        constraint: at least 1 email references an active thread or flag
                    at least 1 email weaves the world event narrative seed (if any)
  → events: EMAILS_GENERATED, MONTH_STARTED
  → stream: emails as they generate

SCENE: PLAYER SUBMITS A DECISION (POST /decide, 1..10 per month, SSE)
  → idempotency check on Idempotency-Key (return cached response if hit)
  → kernel: retrieve top-3 similar past decisions via embeddings
  → llm: resolve_decision(Sonnet, tool="resolve_decision")
        cached:  system + industry + period_summary + origin_story
        dynamic: state_view + recent + month's emails so far + competitor_briefs
                 + retrieved_past_decisions + decision_text
  → server validators:
        clamp(cash_impact, revenue_impact, market_impact, employees_change)
        validate flag_updates against industry.flag_vocab
        truncate strings to schema limits
  → events: DECISION_PROPOSED, DECISION_RESOLVED
  → kernel: embed decision text, insert into decision_embeddings
  → kernel: fire competitor reactive triggers (pure code, FSM transition)
  → events: COMPETITOR_REACTED (0..N)
  → stream: narrative chunk-by-chunk, then final {impacts, updated_state}
  → no memory compaction here

SCENE: PLAYER ENDS MONTH (POST /end-month, idempotency-keyed)
  → kernel:
       payroll  = employees * industry.payroll_per_employee
       overhead = industry.base_overhead
       burn     = payroll + overhead
       cash    += revenue - burn
  → events: MONTH_ENDED, FINANCES_APPLIED
  → kernel: simulate_competitors(industry) — posture-driven + stochastic
  → events: COMPETITOR_TICK (per competitor)
  → kernel: take monthly_snapshot (cash, revenue, market_share, employees, leaderboard)
  → llm: compact_memory(Haiku, tool="compact_memory")  — once per month
  → events: MEMORY_COMPACTED
  → kernel: rebuild leaderboard projection
  → kernel: increment current_month
  → kernel: check elimination
       if cash < 0:
         events: ELIMINATED
         llm: generate_autopsy(Sonnet, tool="autopsy_summary")
         events: AUTOPSY_GENERATED

CONSTRAINTS
  - Chat is the only input. No buttons except Start Month, End Month, Model Picker.
  - 1..10 decisions per month.
  - Each decision resolved immediately, streamed.
  - All mutations go through events. State columns are projections.
```

---

## 3. Data Model

All tables use SQLite. Numeric columns on `players` are projections of `events`. They exist for query speed; the only legitimate writer is the projection rebuilder.

### 3.1 industries (multi-industry seam)

```sql
CREATE TABLE industries (
    id                      TEXT PRIMARY KEY,                  -- 'automotive' for MVP
    name                    TEXT NOT NULL,
    schema_version          INTEGER NOT NULL,
    prompt_version          INTEGER NOT NULL,
    system_prompt_template  TEXT NOT NULL,                     -- {{var}} placeholders
    starting_state_json     TEXT NOT NULL,                     -- {cash, employees, market_share, ...}
    financial_constants     TEXT NOT NULL,                     -- {payroll_per_employee, base_overhead, ...}
    flag_vocabulary         TEXT NOT NULL,                     -- JSON array of allowed flag names
    intent_taxonomy         TEXT NOT NULL,                     -- JSON array of typical intents (used in few-shot)
    relationship_keys       TEXT NOT NULL,                     -- JSON array (e.g. ["board","suppliers","government"])
    relationship_vocab      TEXT NOT NULL,                     -- JSON {board:["pleased","neutral",...]} per key
    sender_vocab            TEXT NOT NULL,                     -- JSON array of valid email senders
    category_vocab          TEXT NOT NULL,                     -- JSON array of valid message categories
    employees_change_clamp  TEXT NOT NULL,                     -- JSON [-10, 20]
    cash_impact_clamp       TEXT NOT NULL,                     -- JSON [-5000000, 3000000]
    revenue_impact_clamp    TEXT NOT NULL,                     -- JSON [-2000000, 5000000]
    market_impact_clamp     TEXT NOT NULL,                     -- JSON [-3.0, 3.0]
    recommended_models      TEXT NOT NULL,                     -- JSON {cheap:..., balanced:..., premium:...}
    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Automotive seed** (MVP — one row):

```json
{
  "id": "automotive",
  "name": "Automotive",
  "schema_version": 1,
  "prompt_version": 1,
  "starting_state_json": {
    "cash": 10000000, "revenue": 0, "market_share": 5.0, "employees": 50
  },
  "financial_constants": {
    "payroll_per_employee": 50000, "base_overhead": 200000
  },
  "flag_vocabulary": [
    "ev_platform_launched","european_expansion","battery_supply_secured",
    "recall_risk","ipo_filed","union_negotiation_active",
    "regulatory_investigation","strategic_partnership","factory_constructed"
  ],
  "intent_taxonomy": [
    "cost_cut","hire","layoff","rd_invest","launch_product","acquire",
    "pricing","partnership","factory_invest","fundraise","restructure"
  ],
  "relationship_keys": ["board","suppliers","government","union"],
  "relationship_vocab": {
    "board":      ["pleased","neutral","concerned","hostile"],
    "suppliers":  ["strong","stable","strained","broken"],
    "government": ["favorable","neutral","hostile"],
    "union":      ["aligned","neutral","tense","striking"]
  },
  "sender_vocab": ["Board","CFO","COO","CTO","Market","Supplier","Regulator","Union","Rival"],
  "category_vocab": ["info","warning","opportunity","crisis","board"],
  "employees_change_clamp": [-10, 20],
  "cash_impact_clamp":      [-5000000, 3000000],
  "revenue_impact_clamp":   [-2000000, 5000000],
  "market_impact_clamp":    [-3.0, 3.0],
  "recommended_models": {
    "cheap":    "google/gemini-2.5-flash",
    "balanced": "anthropic/claude-haiku-4-5",
    "premium":  "anthropic/claude-sonnet-4-6"
  }
}
```

### 3.2 players

```sql
CREATE TABLE players (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    industry_id     TEXT NOT NULL REFERENCES industries(id),
    name            TEXT NOT NULL,
    company_name    TEXT NOT NULL,
    style           TEXT NOT NULL,                              -- free string at this layer
    risk_tolerance  TEXT NOT NULL,                              -- free string
    model_tier      TEXT NOT NULL DEFAULT 'balanced'
                    CHECK(model_tier IN ('cheap','balanced','premium')),
    current_month   INTEGER NOT NULL DEFAULT 0,
    cash            REAL    NOT NULL,                           -- projection
    revenue         REAL    NOT NULL DEFAULT 0,                 -- projection (monthly rate)
    market_share    REAL    NOT NULL,                           -- projection
    employees       INTEGER NOT NULL,                           -- projection
    game_over       BOOLEAN NOT NULL DEFAULT FALSE,
    eliminated_at   INTEGER NULL,                               -- month
    cost_cap_usd    REAL    NULL,                               -- per-game LLM budget; null = no cap
    cost_spent_usd  REAL    NOT NULL DEFAULT 0,                 -- projection from llm_calls
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_players_industry ON players(industry_id);
```

### 3.3 events (append-only — source of truth)

```sql
CREATE TABLE events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id         TEXT NOT NULL REFERENCES players(id),
    month             INTEGER NOT NULL,
    seq_in_month      INTEGER NOT NULL,                         -- ordering within a month
    ts                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    kind              TEXT NOT NULL,                            -- see EVENT_KINDS below
    source            TEXT NOT NULL CHECK(source IN ('player','llm','kernel','world','competitor')),
    payload_json      TEXT NOT NULL,
    parent_event_id   INTEGER NULL REFERENCES events(id),
    idempotency_key   TEXT NULL,
    prompt_version    INTEGER NULL,
    schema_version    INTEGER NULL,
    model             TEXT NULL,
    seed              INTEGER NULL
);
CREATE INDEX idx_events_player_month ON events(player_id, month, seq_in_month);
CREATE UNIQUE INDEX idx_events_idem ON events(player_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
```

`EVENT_KINDS`:
```
MONTH_STARTED, MONTH_ENDED,
EMAILS_GENERATED,
DECISION_PROPOSED, DECISION_RESOLVED,
FINANCES_APPLIED,
COMPETITOR_TICK, COMPETITOR_REACTED,
WORLD_EVENT_FIRED,
FLAG_CHANGED, THREAD_OPENED, THREAD_CLOSED, RELATIONSHIP_CHANGED,
MEMORY_COMPACTED,
ELIMINATED, AUTOPSY_GENERATED
```

### 3.4 monthly_snapshots

```sql
CREATE TABLE monthly_snapshots (
    player_id      TEXT NOT NULL REFERENCES players(id),
    month          INTEGER NOT NULL,
    cash           REAL NOT NULL,
    revenue        REAL NOT NULL,
    market_share   REAL NOT NULL,
    employees      INTEGER NOT NULL,
    burn_rate      REAL NOT NULL,
    leaderboard_rank INTEGER NOT NULL,
    PRIMARY KEY (player_id, month)
);
```

Written by the projection rebuilder at `MONTH_ENDED`. Used by trends, charts, autopsy.

### 3.5 messages (inbox)

```sql
CREATE TABLE messages (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id         TEXT NOT NULL REFERENCES players(id),
    month             INTEGER NOT NULL,
    sender            TEXT NOT NULL,                            -- validated against industry.sender_vocab
    subject           TEXT NOT NULL,                            -- ≤80 chars (validator)
    body              TEXT NOT NULL,                            -- ≤300 chars (validator)
    category          TEXT NOT NULL,                            -- validated against industry.category_vocab
    is_read           BOOLEAN NOT NULL DEFAULT FALSE,
    requires_action   BOOLEAN NOT NULL DEFAULT FALSE,
    parent_message_id INTEGER NULL REFERENCES messages(id),     -- for threaded follow-ups
    thread_id         INTEGER NULL REFERENCES threads(id),      -- linked active thread, if any
    prompt_version    INTEGER NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_messages_player_month ON messages(player_id, month);
```

### 3.6 decisions

```sql
CREATE TABLE decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       TEXT NOT NULL REFERENCES players(id),
    month           INTEGER NOT NULL,
    seq_in_month    INTEGER NOT NULL,
    decision_text   TEXT NOT NULL,
    inbox_ref_ids   TEXT NULL,                                  -- JSON array of message ids player was responding to
    narrative       TEXT NOT NULL,                              -- ≤500 chars (validator)
    importance      REAL NOT NULL CHECK(importance BETWEEN 0 AND 1),
    cash_impact     REAL NOT NULL,
    revenue_impact  REAL NOT NULL,
    market_impact   REAL NOT NULL,
    employees_change INTEGER NOT NULL,
    prompt_version  INTEGER NOT NULL,
    schema_version  INTEGER NOT NULL,
    model           TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    cost_usd        REAL NOT NULL,
    latency_ms      INTEGER NOT NULL,
    cache_hit       BOOLEAN NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_decisions_player_month ON decisions(player_id, month);
```

### 3.7 decision_embeddings

```sql
CREATE TABLE decision_embeddings (
    decision_id   INTEGER PRIMARY KEY REFERENCES decisions(id),
    player_id     TEXT NOT NULL REFERENCES players(id),
    model         TEXT NOT NULL,                                -- embedding model id
    dim           INTEGER NOT NULL,
    vector        BLOB NOT NULL                                 -- float32 little-endian
);
CREATE INDEX idx_decembed_player ON decision_embeddings(player_id);
```

MVP retrieval: brute-force cosine over `WHERE player_id = ?` (typically <300 rows by M24). Later: `sqlite-vec` extension or migration to a dedicated vector store.

### 3.8 threads (first-class)

```sql
CREATE TABLE threads (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id        TEXT NOT NULL REFERENCES players(id),
    label            TEXT NOT NULL,                             -- ≤40 chars
    importance       REAL NOT NULL DEFAULT 0.5 CHECK(importance BETWEEN 0 AND 1),
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK(status IN ('active','resolved','abandoned')),
    opened_at_month  INTEGER NOT NULL,
    closed_at_month  INTEGER NULL,
    last_referenced_month INTEGER NOT NULL
);
CREATE INDEX idx_threads_player_status ON threads(player_id, status);
```

Eviction policy when active threads > 5:
- Drop the lowest-importance non-active first.
- If all active, drop the one with `last_referenced_month` furthest in the past.
- A dropped active thread is moved to `status='abandoned'`, never deleted.

### 3.9 flags (closed vocabulary, per industry)

```sql
CREATE TABLE flags (
    player_id     TEXT NOT NULL REFERENCES players(id),
    flag_name     TEXT NOT NULL,                                -- must be in industry.flag_vocabulary
    value         BOOLEAN NOT NULL,
    set_at_month  INTEGER NOT NULL,
    PRIMARY KEY (player_id, flag_name)
);
```

### 3.10 relationships

```sql
CREATE TABLE relationships (
    player_id    TEXT NOT NULL REFERENCES players(id),
    key          TEXT NOT NULL,                                 -- must be in industry.relationship_keys
    value        TEXT NOT NULL,                                 -- must be in industry.relationship_vocab[key]
    updated_at_month INTEGER NOT NULL,
    PRIMARY KEY (player_id, key)
);
```

### 3.11 competitors (per-player)

```sql
CREATE TABLE competitors (
    id              TEXT PRIMARY KEY,                           -- 'p<player>:novatech'
    player_id       TEXT NOT NULL REFERENCES players(id),
    industry_id     TEXT NOT NULL REFERENCES industries(id),
    template_id     TEXT NOT NULL,                              -- 'novatech', 'autovista', etc.
    name            TEXT NOT NULL,
    style           TEXT NOT NULL,
    posture         TEXT NOT NULL DEFAULT 'OBSERVING'
                    CHECK(posture IN ('OBSERVING','DEFENSIVE','AGGRESSIVE','STRUGGLING')),
    base_growth     REAL NOT NULL,
    volatility      REAL NOT NULL,
    expenses        REAL NOT NULL,
    cash            REAL NOT NULL,
    revenue         REAL NOT NULL DEFAULT 0,
    market_share    REAL NOT NULL,
    posture_until_month INTEGER NULL                            -- temporary postures
);
CREATE INDEX idx_comp_player ON competitors(player_id);
```

**Automotive competitor templates** (seeded per player on creation):

| template_id | name | style | base_growth | volatility | expenses | cash | revenue | market_share |
|---|---|---|---|---|---|---|---|---|
| novatech | NovaTech | aggressive | 0.08 | 0.05 | 1200000 | 15000000 | 3000000 | 12.0 |
| autovista | AutoVista | conservative | 0.05 | 0.02 | 1800000 | 20000000 | 5000000 | 18.0 |
| drivex | DriveX | balanced | 0.06 | 0.04 | 900000 | 12000000 | 2000000 | 8.0 |
| greenwheel | GreenWheel | innovation | 0.10 | 0.07 | 600000 | 8000000 | 1000000 | 3.0 |

### 3.12 world_events (calendar)

```sql
CREATE TABLE world_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    industry_id         TEXT NOT NULL REFERENCES industries(id),
    fire_at_month       INTEGER NOT NULL,                       -- absolute or pattern-based; MVP uses absolute
    event_id            TEXT NOT NULL,
    severity            TEXT NOT NULL CHECK(severity IN ('minor','major','crisis')),
    narrative_seed      TEXT NOT NULL,                          -- LLM is required to weave this into emails
    mechanical_effects  TEXT NOT NULL,                          -- JSON; see Section 9.4
    duration_months     INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_world_industry_month ON world_events(industry_id, fire_at_month);
```

**Automotive calendar (MVP, M0–M24)** — see Section 10.

### 3.13 leaderboard (view, not table)

```sql
CREATE VIEW leaderboard AS
SELECT
    p.id AS entity_id, p.company_name, 'player' AS entity_type,
    p.cash, p.revenue, p.market_share, p.current_month,
    RANK() OVER (PARTITION BY p.industry_id ORDER BY p.cash + p.revenue * 6 DESC) AS rank
FROM players p WHERE p.game_over = FALSE
UNION ALL
SELECT
    c.id, c.name, 'competitor',
    c.cash, c.revenue, c.market_share,
    (SELECT current_month FROM players WHERE id = c.player_id),
    RANK() OVER (PARTITION BY c.player_id ORDER BY c.cash + c.revenue * 6 DESC)
FROM competitors c;
```

Ranking metric: `cash + revenue × 6` (≈ 6-month cash projection at current revenue rate). Stable, intuitive, no pre-computed cache.

### 3.14 llm_calls (telemetry)

```sql
CREATE TABLE llm_calls (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id         TEXT NULL REFERENCES players(id),
    event_id          INTEGER NULL REFERENCES events(id),
    call_type         TEXT NOT NULL,                            -- generate_inbox|resolve_decision|compact_memory|autopsy|embed
    model             TEXT NOT NULL,
    in_tokens         INTEGER NOT NULL,
    out_tokens        INTEGER NOT NULL,
    cached_tokens     INTEGER NOT NULL DEFAULT 0,
    cost_usd          REAL NOT NULL,
    latency_ms        INTEGER NOT NULL,
    cache_hit_ratio   REAL NULL,
    error             TEXT NULL,
    ts                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_llm_calls_player_ts ON llm_calls(player_id, ts);
```

---

## 4. Layer 1 — State Projection (frozen schema)

This is the exact JSON the LLM sees on every call. **Built on read** from `players` + `flags` + `relationships` + `threads` + `competitors`. Never persisted with numeric duplicates.

```json
{
  "company": "string",
  "ceo": "string",
  "industry": "automotive",
  "style": "string (free)",
  "risk_tolerance": "string (free)",
  "month": "integer >= 0",
  "cash": "number",
  "revenue": "number >= 0",
  "market_share": "number 0-100",
  "employees": "integer >= 1",
  "burn_rate": "number >= 0",
  "cash_runway": "comfortable|healthy|tight|critical",
  "revenue_trend": "growing|stable|declining",
  "relationships": {
    "board": "string from industry.relationship_vocab.board",
    "suppliers": "string from industry.relationship_vocab.suppliers",
    "government": "string from industry.relationship_vocab.government",
    "union": "string from industry.relationship_vocab.union"
  },
  "active_threads": [
    {"label": "string", "importance": "0..1", "opened_at_month": "int"}
  ],
  "flags": {"<flag_name from industry.flag_vocabulary>": "boolean"},
  "competitor_briefs": [
    {"name": "string", "market_share": "number", "revenue_band": "low|mid|high",
     "posture": "OBSERVING|DEFENSIVE|AGGRESSIVE|STRUGGLING",
     "headline": "string max 80 chars (kernel-generated)"}
  ],
  "active_world_events": [
    {"event_id": "string", "severity": "minor|major|crisis",
     "narrative_seed": "string", "months_remaining": "int"}
  ]
}
```

**Derived field rules** (computed at projection time, not by the LLM):
- `burn_rate = employees × industry.financial_constants.payroll_per_employee + industry.financial_constants.base_overhead`
- `cash_runway`: ratio `r = cash / burn_rate`. Buckets: `r ≥ 4 → comfortable`, `r ≥ 2 → healthy`, `r ≥ 1 → tight`, `r < 1 → critical`.
- `revenue_trend`: from `monthly_snapshots`. Compare current revenue vs `mean(last 3 snapshots)`; ±10% threshold.
- `competitor_briefs`: top-3 competitors by `market_share`, plus the player's own posture summary.
- `active_world_events`: those whose `fire_at_month ≤ current_month < fire_at_month + duration_months`.

**Initial state on player creation** (from `industry.starting_state_json`):
```json
{
  "month": 0, "cash": 10000000, "revenue": 0, "market_share": 5.0, "employees": 50,
  "burn_rate": 2700000, "cash_runway": "comfortable", "revenue_trend": "stable",
  "relationships": {"board":"neutral","suppliers":"stable","government":"neutral","union":"neutral"},
  "active_threads": [], "flags": {},
  "competitor_briefs": [/* seeded */], "active_world_events": []
}
```

---

## 5. Memory architecture

Three text layers + one embedding index.

### 5.1 memories table (text layers)

```sql
CREATE TABLE memories (
    player_id        TEXT PRIMARY KEY REFERENCES players(id),
    recent           TEXT NOT NULL DEFAULT '',                  -- last 3 months, 1 line per month
    period_summary   TEXT NOT NULL DEFAULT '',                  -- 1 paragraph, M4..current-3
    period_start     INTEGER NOT NULL DEFAULT 0,
    period_end       INTEGER NOT NULL DEFAULT 0,
    origin_story     TEXT NOT NULL DEFAULT '',                  -- 1-2 sentences
    origin_end       INTEGER NOT NULL DEFAULT 0,
    updated_at_month INTEGER NOT NULL DEFAULT 0
);
```

### 5.2 Compaction triggers (deterministic)

Compaction runs **once at end_month** (Haiku tool call). Deterministic rules decide *what* to feed the LLM:

- `recent` is rebuilt from the just-finished month's decisions: 1 line summarizing the highest-importance decision (or "Quiet month" if none).
- When `recent` would exceed 3 lines (i.e. month ≥ 4), the oldest line is absorbed into `period_summary`. Haiku rewrites `period_summary` to integrate it.
- When `period_summary` would cover more than 20 months, the oldest 5 months are absorbed into `origin_story`. Haiku rewrites `origin_story`.

Importance weighting: when summarizing a month with multiple decisions, the line covers the decision with the highest `importance`. Ties broken by recency.

### 5.3 Embedding retrieval (Layer 4)

On each `resolve_decision`:
1. Embed the new `decision_text` (e.g. `voyage-3-lite` or OpenAI `text-embedding-3-small` via OpenRouter).
2. Cosine-similarity scan against all `decision_embeddings` for this player.
3. Top-3 by similarity, filtered to `decisions.importance ≥ 0.4` to avoid noise.
4. Inject as `retrieved_past_decisions` block in the dynamic prompt (see Section 8.2).

After resolve, the new decision is embedded and inserted.

---

## 6. LLM Contracts (tool-calling)

All calls go through OpenRouter's `/v1/chat/completions` endpoint with `tools` and `tool_choice` set. Tools are forced (`{"type":"function","function":{"name":"..."}}`) — the model must call exactly that tool.

### 6.1 generate_inbox_emails (Haiku, called on `start_month`)

```json
{
  "type": "function",
  "function": {
    "name": "generate_inbox_emails",
    "description": "Generate this month's inbox of 3-5 in-character emails for the CEO.",
    "parameters": {
      "type": "object",
      "additionalProperties": false,
      "required": ["emails"],
      "properties": {
        "emails": {
          "type": "array",
          "minItems": 3, "maxItems": 5,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["sender","subject","body","category","requires_action","references"],
            "properties": {
              "sender":          {"type":"string"},
              "subject":         {"type":"string","maxLength":80},
              "body":            {"type":"string","maxLength":300},
              "category":        {"type":"string"},
              "requires_action": {"type":"boolean"},
              "references": {
                "type": "object",
                "additionalProperties": false,
                "properties": {
                  "thread_label":      {"type":"string"},
                  "flag_name":         {"type":"string"},
                  "world_event_id":    {"type":"string"},
                  "parent_message_id": {"type":"integer"}
                }
              }
            }
          }
        }
      }
    }
  }
}
```

**Server constraints (validated post-call, not in prompt prose)**:
- At least one email's `references` must include either a `thread_label` from active threads, a `flag_name` from set flags, or a `world_event_id` from `active_world_events` if any are present.
- At month 1, the first email **must** have `sender = "Board"` and `category = "board"` — enforced server-side; if missing, prepended deterministically.
- `sender` ∈ `industry.sender_vocab`, `category` ∈ `industry.category_vocab`. Invalid → email rejected (entire batch retried once; if still bad, fall through to a deterministic fallback batch).

### 6.2 resolve_decision (Sonnet, called on each `/decide`)

```json
{
  "type": "function",
  "function": {
    "name": "resolve_decision",
    "description": "Resolve a CEO decision: produce dramatic narrative and the resulting state changes.",
    "parameters": {
      "type": "object",
      "additionalProperties": false,
      "required": ["narrative","cash_impact","revenue_impact","market_impact",
                   "importance","employees_change","relationship_updates",
                   "new_threads","closed_threads","flag_updates"],
      "properties": {
        "narrative":       {"type":"string","maxLength":500},
        "cash_impact":     {"type":"number"},
        "revenue_impact":  {"type":"number"},
        "market_impact":   {"type":"number"},
        "importance":      {"type":"number","minimum":0,"maximum":1},
        "employees_change":{"type":"integer"},
        "relationship_updates": {
          "type": "object",
          "additionalProperties": {"type":"string"}
        },
        "new_threads": {
          "type": "array",
          "maxItems": 2,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["label","importance"],
            "properties": {
              "label":     {"type":"string","maxLength":40},
              "importance":{"type":"number","minimum":0,"maximum":1}
            }
          }
        },
        "closed_threads": {"type":"array","items":{"type":"string","maxLength":40}},
        "flag_updates":   {"type":"object","additionalProperties":{"type":"boolean"}}
      }
    }
  }
}
```

**Server validators (post-call)**:
- Numeric clamps from `industry.{cash,revenue,market,employees}_change_clamp`. Out-of-bounds values are clamped, never rejected (we still need a narrative).
- `flag_updates` keys filtered against `industry.flag_vocabulary`. Unknown keys dropped, logged as `WARN flag_vocab_violation`.
- `relationship_updates` keys filtered against `industry.relationship_keys`; values against `industry.relationship_vocab[key]`. Invalid → dropped + logged.
- `closed_threads` matched case-insensitively against active thread labels; unmatched ignored.
- `narrative`, `new_threads.label` truncated to `maxLength` if over.
- If `cash_impact` would clamp by ≥50%, `narrative` is post-edited deterministically: " (Note: scope reduced)" appended.

### 6.3 compact_memory (Haiku, called once at `end_month`)

```json
{
  "type": "function",
  "function": {
    "name": "compact_memory",
    "description": "Roll up the last month into the hierarchical memory.",
    "parameters": {
      "type": "object",
      "additionalProperties": false,
      "required": ["recent_line","period_summary","origin_story"],
      "properties": {
        "recent_line":    {"type":"string","maxLength":120},
        "period_summary": {"type":"string","maxLength":300},
        "origin_story":   {"type":"string","maxLength":160}
      }
    }
  }
}
```

Inputs: prior `recent` + `period_summary` + `origin_story` + this month's decisions (top-3 by importance) + this month's flag/relationship transitions. The LLM rewrites all three layers; if `period_summary` or `origin_story` aren't due for a rewrite (per Section 5.2 rules), the kernel discards those fields and keeps the previous values.

### 6.4 autopsy_summary (Sonnet, called once on `ELIMINATED` or on player request after M24)

```json
{
  "type": "function",
  "function": {
    "name": "autopsy_summary",
    "description": "Generate a shareable end-of-game summary card.",
    "parameters": {
      "type": "object",
      "additionalProperties": false,
      "required": ["headline","arc_summary","pivotal_decisions","cause_of_death","board_quote"],
      "properties": {
        "headline":       {"type":"string","maxLength":80},
        "arc_summary":    {"type":"string","maxLength":600},
        "pivotal_decisions": {
          "type":"array","minItems":2,"maxItems":4,
          "items":{
            "type":"object",
            "additionalProperties":false,
            "required":["month","one_liner","verdict"],
            "properties":{
              "month":{"type":"integer"},
              "one_liner":{"type":"string","maxLength":120},
              "verdict":{"type":"string","enum":["brilliant","sound","risky","fatal"]}
            }
          }
        },
        "cause_of_death": {"type":"string","maxLength":120},
        "board_quote":    {"type":"string","maxLength":160}
      }
    }
  }
}
```

Inputs: full `monthly_snapshots`, top-10 decisions by `importance`, final state. Result stored as `AUTOPSY_GENERATED` event payload.

---

## 7. Frozen system prompt (Haiku & Sonnet share the cached block)

Stored on `industries.system_prompt_template`. MVP automotive value:

```
You are the engine of Pax Venture, a CEO simulation set in the {{industry_name}} industry.
You generate realistic, specific, dramatic business events. You speak in the voice of the
people who would actually email a CEO: board chairs, CFOs, regulators, suppliers, rivals.

INDUSTRY CONTEXT — {{industry_name}}:
- Global automotive market in EV transition.
- Traditional OEMs fighting Tesla and Chinese entrants.
- Supply chain fragility (chips, batteries, rare earth).
- Regulatory pressure (emissions, safety, tariffs).

CLOSED VOCABULARIES (you MUST use only these values):
- Senders: {{sender_vocab}}
- Categories: {{category_vocab}}
- Relationship keys: {{relationship_keys}}
- Relationship values per key: {{relationship_vocab}}
- Flag names: {{flag_vocabulary}}

NUMERIC RANGES (you should stay within; the system will clamp if you exceed):
- cash_impact: {{cash_impact_clamp}}
- revenue_impact: {{revenue_impact_clamp}}
- market_impact: {{market_impact_clamp}}
- employees_change: {{employees_change_clamp}}

NARRATIVE RULES:
1. Be specific to {{industry_name}} (real-feeling models, suppliers, factories, regulations).
2. Numbers must be realistic for a company starting at $10M cash.
3. Consequences cascade — reference active threads, flags, relationships, world events,
   and the retrieved past decisions you are given.
4. cash < $0 = elimination. Warn the player in narrative when cash_runway is "tight" or "critical".
5. The player is not a superhero — bad decisions hurt. Good decisions take 1-3 months to pay off.
6. Importance: 0.8+ = acquisition / launch / crisis. 0.3-0.5 = hire / budget shift. <0.3 = minor.
7. Revenue scaling: M1-M3 $0-2M/mo; M4-M8 $1-5M; M9-M12 $3-10M; M13+ $5-15M.
8. Never break character. No meta-commentary about being an AI or simulation.
9. Output exclusively via the requested tool call. Do not produce free text.

WORLD EVENTS active this month:
{{active_world_events_block}}

LONG-TERM MEMORY:
ORIGIN: {{origin_story}}
PERIOD SUMMARY ({{period_start}}..{{period_end}}): {{period_summary}}
```

This entire block lives in the **cached** input segment. Player-supplied identifiers (`{{company_name}}`, `{{ceo_name}}`) are passed as a separate small dynamic block to keep the cache reusable across players (cache key is the rendered cached block, so per-industry templates cache separately).

The dynamic block (per call) carries: state JSON, recent memory, current emails, retrieved decisions, decision text or "generate emails" instruction.

---

## 8. Prompt architecture

### 8.1 Cached vs dynamic blocks

| Block | Source | Caching | Approx tokens |
|---|---|---|---|
| **Cached system** | `industries.system_prompt_template` rendered with closed vocabs, numeric ranges, world events block, `origin_story`, `period_summary` | `cache_control: ephemeral` (5-min TTL) | 1500–2500 |
| **Dynamic state** | Layer 1 state JSON | not cached | 400–700 |
| **Dynamic memory** | `recent` (≤3 lines) | not cached | 150–250 |
| **Dynamic context** | Current month's emails + active threads + retrieved past decisions | not cached | 400–800 |
| **Dynamic instruction** | "Resolve this decision: ..." or "Generate this month's inbox" | not cached | 50–200 |

Steady-state input per call: ~2500–4500 tokens, of which 60–75% is cached (mid-game). Anthropic cached input is ~10% of normal cost; the effective per-call input cost is ~25–40% of the uncached equivalent.

### 8.2 Dynamic context block — exact shape

```
=== CURRENT STATE ===
{state_json}

=== RECENT MEMORY ===
{recent}

=== ACTIVE THREADS ===
- {label1} (importance {imp1}, opened M{m1}, last referenced M{r1})
- ...

=== RELATIONSHIPS ===
board: {value}, suppliers: {value}, government: {value}, union: {value}

=== FLAGS ===
{flag_name}: {true|false}, ...

=== COMPETITOR BRIEFS ===
{name} — share {x}%, revenue {band}, posture {posture}: {headline}
...

=== ACTIVE WORLD EVENTS ===
{event_id} ({severity}, {months_remaining} months left): {narrative_seed}
...

=== RETRIEVED PAST DECISIONS ===  (only on resolve_decision)
M{n} — "{decision_text snippet}" → {narrative snippet}
...

=== THIS MONTH'S INBOX ===  (only on resolve_decision)
[{id}] from {sender} — {subject}
{body}

=== INSTRUCTION ===
Call the {tool_name} tool now.
{decision_text if resolve_decision}
```

### 8.3 Compression hook (Phase 2)

The cached block is compressible. Pax Historia (case study) integrated `bear-1.1` at compression ratios `0.2` for Sonnet and `0.05` for Gemini Flash, achieving ~66% input reduction with +5% purchase rate and slightly improved A/B preference.

MVP **does not** ship compression. The integration point is `core/compression.py.compress_cached_block(text, model) -> text`, called immediately before `cache_control` is applied. Phase 2 plugs in any compressor without touching call sites.

### 8.4 Multi-model routing

`core/openrouter.py` exposes:

```python
def call_tool(call_type: str, model: str, messages: list, tool: dict, *,
              cache_control_on_system: bool, seed: int) -> ToolCallResult
```

Defaults per call type, overridden by `players.model_tier`:

| Call type | cheap | balanced (default) | premium |
|---|---|---|---|
| generate_inbox_emails | gemini-2.5-flash | claude-haiku-4-5 | claude-sonnet-4-6 |
| resolve_decision | claude-haiku-4-5 | claude-sonnet-4-6 | claude-opus-4-7 |
| compact_memory | gemini-2.5-flash | claude-haiku-4-5 | claude-haiku-4-5 |
| autopsy_summary | claude-haiku-4-5 | claude-sonnet-4-6 | claude-opus-4-7 |
| embed | voyage-3-lite | voyage-3-lite | voyage-3-lite |

Tier model ids resolved via `industries.recommended_models`. Players can also pass a raw OpenRouter model id (`?model=anthropic/claude-sonnet-4-6`) — server validates against an allowlist.

**Failover**: every call is wrapped with one OpenRouter retry on 5xx/429. If still failing, fall back to the same call type's `cheap` tier model. If that also fails: 502.

---

## 9. Game mechanics (frozen)

### 9.1 Starting state

Loaded from `industries.starting_state_json`. For automotive:

| Metric | Value |
|---|---|
| Cash | $10,000,000 |
| Revenue | $0/month |
| Market share | 5.0% |
| Employees | 50 |
| Burn rate | $2,700,000 |

### 9.2 Money flow (the A1 fix)

Single source of truth in `events.payload_json`:

- **Per-decision** events:
  - `cash` += `cash_impact` (one-time)
  - `revenue` += `revenue_impact` (changes the recurring monthly rate)
  - `market_share` += `market_impact`
  - `employees` += `employees_change`

- **Per-month** events (`MONTH_ENDED → FINANCES_APPLIED`):
  ```
  payroll  = employees × industry.financial_constants.payroll_per_employee
  overhead = industry.financial_constants.base_overhead
  burn     = payroll + overhead
  cash    += revenue - burn
  ```

`revenue` is a metric (current monthly revenue rate), **not money**. It flows into cash at end_month. Decisions that say "we got paid $X this month" use `cash_impact`. Decisions that change recurring revenue use `revenue_impact`.

### 9.3 Clamps (server-side, post-call)

From `industries.*_clamp`:

| Field | Automotive default |
|---|---|
| `cash_impact` | `[-5_000_000, +3_000_000]` |
| `revenue_impact` | `[-2_000_000, +5_000_000]` |
| `market_impact` | `[-3.0, +3.0]` |
| `employees_change` | `[-10, +20]` |

Out-of-bounds values are clamped silently. If clamped by ≥50%, narrative gets " (Note: scope reduced)" appended deterministically.

### 9.4 World events (mechanical effects)

`world_events.mechanical_effects` JSON shape:

```json
{
  "global": {
    "revenue_multiplier": 0.85,
    "cash_delta_per_month": -100000,
    "market_share_drift": -0.2
  },
  "competitors": {
    "all": {"revenue_multiplier": 0.9},
    "by_template": {"greenwheel": {"base_growth_delta": 0.02}}
  },
  "requires_flag": "battery_supply_secured",
  "if_missing_flag_penalty": {"market_share_delta": -1.5}
}
```

Applied at `MONTH_ENDED` in this order: `requires_flag` check → global effects on player → competitor effects → drift updates. Each effect emits a `WORLD_EVENT_FIRED` event with the affected entity in payload.

### 9.5 Reactive competitors (FSM + noise)

```python
def end_month_competitor_tick(comp, player, month, rng):
    apply_posture_transitions(comp, player, month)   # see 9.6

    posture_modifier = {
        'OBSERVING':   1.00,
        'DEFENSIVE':   0.85,
        'AGGRESSIVE':  1.30,
        'STRUGGLING':  0.60,
    }[comp.posture]

    base = comp.base_growth * posture_modifier
    noise = rng.gauss(0, comp.volatility)
    seasonal = 0.02 * math.sin(month * 0.5)
    comp.revenue *= (1 + base + noise + seasonal)
    comp.cash += comp.revenue - comp.expenses
    comp.market_share = max(0.1, comp.market_share + rng.gauss(0, 0.3))

    if month % 3 == 0 and rng.random() < 0.03:
        scale = rng.uniform(0.1, 0.3)
        comp.cash *= (1 - scale)
        comp.market_share *= (1 - scale * 0.5)
```

`rng` is seeded as `hash((player_id, month, comp.id))` for reproducibility.

### 9.6 Posture transitions (pure code, fired on player events)

| Trigger | Transition | Duration |
|---|---|---|
| `flag.ev_platform_launched` becomes `true` | NovaTech → AGGRESSIVE | 3 months |
| `flag.european_expansion` becomes `true` | AutoVista → DEFENSIVE | 4 months |
| Player `market_share` crosses 12.0 | NovaTech → DEFENSIVE | until player drops below 11 |
| Player `market_share` crosses 18.0 | AutoVista → DEFENSIVE | until player drops below 17 |
| Player `cash_runway = critical` for 2 consecutive end_months | All comps → AGGRESSIVE | 1 month |
| `flag.battery_supply_secured` becomes `true` | GreenWheel → STRUGGLING | 2 months |

Transitions are deterministic. They emit `COMPETITOR_REACTED` events.

### 9.7 End-of-month flow (pseudocode)

```python
async def end_month(player_id, idem_key):
    if existing := find_event_by_idem(player_id, idem_key, kind="MONTH_ENDED"):
        return projection_at(existing)

    p = load_player(player_id)
    if p.game_over: raise Conflict("Game is over")
    if not month_is_active(p): raise Conflict("Month not started")

    # 1. Apply world events that fire/expire at this boundary
    apply_world_events(p, p.current_month)

    # 2. Apply finances (the A1 fix)
    payroll  = p.employees * industry.financial_constants.payroll_per_employee
    overhead = industry.financial_constants.base_overhead
    burn     = payroll + overhead
    p.cash  += p.revenue - burn
    record_event("FINANCES_APPLIED", payload={"burn": burn, "revenue": p.revenue})

    # 3. Competitor tick (reactive + stochastic)
    for comp in load_competitors(player_id):
        end_month_competitor_tick(comp, p, p.current_month, seeded_rng(p, comp))
        record_event("COMPETITOR_TICK", ...)

    # 4. Memory compaction (one Haiku call)
    await compact_memory(p)
    record_event("MEMORY_COMPACTED", ...)

    # 5. Snapshot
    take_snapshot(p)

    # 6. Increment month
    p.current_month += 1

    # 7. Elimination check
    if p.cash < 0:
        p.game_over = True
        p.eliminated_at = p.current_month
        record_event("ELIMINATED", ...)
        await generate_autopsy(p)
        record_event("AUTOPSY_GENERATED", ...)

    record_event("MONTH_ENDED", idempotency_key=idem_key)
    return projection(p)
```

---

## 10. World event calendar — automotive (MVP)

Seeded into `world_events` on `init_db`.

| month | id | severity | duration | narrative_seed | mechanical_effects |
|---|---|---|---|---|---|
| 3 | chip_shortage_2026 | major | 2 | "Global semiconductor shortage hits automotive supply." | `{global:{revenue_multiplier:0.88}, competitors:{all:{revenue_multiplier:0.92}}}` |
| 6 | eu_emissions_2026 | major | 12 | "EU enacts stricter emissions regulation; non-compliant OEMs face fines." | `{requires_flag:"ev_platform_launched", if_missing_flag_penalty:{cash_delta_per_month:-150000, market_share_drift:-0.1}}` |
| 9 | rare_earth_crisis | minor | 2 | "Rare earth export restrictions disrupt EV motor production." | `{global:{cash_delta_per_month:-80000}, competitors:{by_template:{greenwheel:{base_growth_delta:-0.04}}}}` |
| 12 | macro_downturn_2027 | crisis | 4 | "Global recession compresses auto demand." | `{global:{revenue_multiplier:0.80}, competitors:{all:{revenue_multiplier:0.85}}}` |
| 15 | trade_war_tariffs | major | 6 | "US-China tariffs spike on auto components." | `{global:{cash_delta_per_month:-120000}}` |
| 18 | union_strike_wave | minor | 2 | "Industry-wide labor unrest; UAW affiliated unions threaten coordinated strike." | `{requires_flag:"union_negotiation_active", if_missing_flag_penalty:{revenue_multiplier:0.90}}` |
| 21 | solid_state_breakthrough | major | 6 | "A solid-state battery breakthrough is announced; first movers see margin advantage." | `{requires_flag:"battery_supply_secured", if_missing_flag_penalty:{market_share_drift:-0.3}}` |
| 24 | recession_bottom | crisis | 3 | "Recession trough; cheapest financing in a decade for the cash-rich." | `{global:{cash_delta_per_month:50000}, competitors:{all:{revenue_multiplier:0.95}}}` |

Calendar is data, not code. Adding events is a row insert.

---

## 11. API contract

Base path: `/api/v1`. All mutating endpoints require `Idempotency-Key` (UUID); GETs do not. SSE endpoints documented as `text/event-stream`.

### 11.1 POST /players

```http
POST /api/v1/players
Idempotency-Key: <uuid>
Content-Type: application/json

{
  "industry_id": "automotive",
  "name": "Vincenzo",
  "company_name": "Vento Motors",
  "style": "aggressive",
  "risk_tolerance": "high",
  "model_tier": "balanced",
  "cost_cap_usd": null
}
```

201 response: full player projection (id, current_month=0, cash, revenue, market_share, employees, model_tier, game_over=false). Side effects: seeds competitors, opens `memories` row, fires `MONTH_STARTED` for month 0 only as far as state init (no emails generated until `/start-month`).

### 11.2 GET /players/{id}

200: same projection as POST response, plus `cost_spent_usd`.

### 11.3 GET /players/{id}/state

200: Layer 1 state JSON (Section 4). Built on read.

### 11.4 GET /players/{id}/memory

200:
```json
{
  "recent": "...", "period_summary": "...", "origin_story": "...",
  "period_start": 0, "period_end": 0, "active_threads": [...]
}
```

### 11.5 POST /players/{id}/start-month

```http
POST /api/v1/players/{id}/start-month
Idempotency-Key: <uuid>
Accept: text/event-stream
```

SSE stream:
```
event: email
data: {"id":1,"sender":"Board","subject":"...","body":"...","category":"board"}
event: email
data: {...}
event: done
data: {"month":1,"emails":[...],"cost_usd":0.0008,"cache_hit_ratio":0.71}
```

Preconditions: prior month must be ended (or `current_month == 0`). 409 if month already started under a different idempotency key.

### 11.6 POST /players/{id}/decide

```http
POST /api/v1/players/{id}/decide
Idempotency-Key: <uuid>
Accept: text/event-stream
Content-Type: application/json

{
  "text": "Cut marketing 30%, redirect to R&D.",
  "inbox_ref_ids": [4, 7],
  "model": null
}
```

SSE stream:
```
event: narrative.chunk
data: {"text":"Bold gamble. Marketing cut executed —"}
event: narrative.chunk
data: {"text":" $480K saved. R&D team expands to 12 engineers..."}
event: result
data: {
  "narrative":"Bold gamble. ...",
  "cash_impact":-480000, "revenue_impact":120000, "market_impact":-0.5,
  "importance":0.7, "employees_change":2,
  "updated_state":{...Layer 1...},
  "cost_usd":0.014, "cache_hit_ratio":0.83, "model":"anthropic/claude-sonnet-4-6"
}
```

Preconditions: month started, not game over, decisions-this-month < 10. Replay of the same `Idempotency-Key` returns the original `result` event without re-calling the LLM.

### 11.7 POST /players/{id}/end-month

```http
POST /api/v1/players/{id}/end-month
Idempotency-Key: <uuid>
```

200:
```json
{
  "month": 1, "cash": 7620000, "revenue": 1620000, "market_share": 4.5,
  "burn_rate": 2700000, "employees": 52, "game_over": false,
  "leaderboard": [
    {"rank":1,"company_name":"AutoVista","cash":21500000,"revenue":5150000,"market_share":18.2},
    ...
  ],
  "world_events_fired": [{"event_id":"chip_shortage_2026","severity":"major"}],
  "memory_compacted": true,
  "cost_usd": 0.0008
}
```

If `game_over=true`: an additional `autopsy` field is included (Section 6.4 schema).

### 11.8 GET /players/{id}/inbox?month=N

200: `{ "messages": [ {id, month, sender, subject, body, category, is_read, requires_action, parent_message_id, thread_id} ] }`. Defaults to current month.

### 11.9 GET /players/{id}/leaderboard

200: same `leaderboard` array as 11.7.

### 11.10 GET /players/{id}/snapshots

200: `{ "snapshots": [ {month, cash, revenue, market_share, employees, burn_rate, leaderboard_rank} ] }`. Used for charts (post-MVP) and the autopsy.

### 11.11 GET /players/{id}/cost

200: `{ "cost_spent_usd": 0.42, "cost_cap_usd": null, "calls": [ {call_type, model, in_tokens, out_tokens, cost_usd, ts} ] }`.

### 11.12 GET /industries

200: array of `{id, name, recommended_models, enabled}`. MVP returns one row.

---

## 12. Error handling

| Scenario | HTTP | Body |
|---|---|---|
| Player not found | 404 | `{"detail":"Player not found"}` |
| Industry not found / disabled | 404 | `{"detail":"Industry unavailable"}` |
| Start month when month already active | 409 | `{"detail":"Month already started"}` |
| Decide when game over | 409 | `{"detail":"Game is over"}` |
| Decide before start_month | 409 | `{"detail":"Start the month first"}` |
| Decide above per-month cap (10) | 409 | `{"detail":"Decision cap reached for this month"}` |
| Per-game cost cap exceeded | 402 | `{"detail":"Game cost cap reached. Raise it in settings to continue."}` |
| Idempotency key collision (different body) | 409 | `{"detail":"Idempotency key reused with different request body"}` |
| OpenRouter 429 | 502 (after retry+failover) | `{"detail":"AI service temporarily unavailable"}` |
| Tool call returns invalid args after retry | 502 | `{"detail":"AI response error"}` |
| Numeric out-of-bounds in tool output | 200 | applied with clamps; logged |
| Closed-vocab violation in tool output | 200 | offending field dropped; logged as `WARN vocab_violation` |
| Email batch fails generation rules after retry | 200 | deterministic fallback batch returned, flagged in telemetry |

All 5xx responses include `request_id` for log correlation.

---

## 13. Cost model & telemetry

### 13.1 Expected per-turn cost (balanced tier, mid-game, with prompt cache)

| Call | Model | In (cached / fresh) | Out | $ |
|---|---|---|---|---|
| generate_inbox_emails (1×/month) | Haiku | 1800 / 600 | 350 | ~$0.0008 |
| resolve_decision (~5×/month) | Sonnet | 2000 / 900 | 350 | ~$0.014 |
| compact_memory (1×/month) | Haiku | 400 / 600 | 250 | ~$0.0005 |
| embed decision (~5×/month) | voyage-3-lite | — | — | ~$0.0001 |
| autopsy_summary (1× per game) | Sonnet | 3000 / 1200 | 600 | ~$0.020 |

**Per month, balanced tier**: ~5 × $0.014 + $0.0008 + $0.0005 + 5 × $0.0001 ≈ **$0.072/month**.
**Per 24-month game, balanced tier**: ≈ **$1.75** (autopsy included).
**Cheap tier**: ≈ **$0.20/game**. **Premium tier**: ≈ **$8/game**.

A `cost_cap_usd` field on `players` (default null) caps a single game; reaching it returns 402 until raised. Defaults can be set per industry.

### 13.2 Telemetry surfaces

Every LLM call writes a row to `llm_calls`. Aggregate views:
- `cost_spent_usd` projection on `players` (sum of `llm_calls.cost_usd`).
- Per-call-type p50/p95 latency, per model.
- Cache hit ratio per call type. Alert if mid-game (`current_month ≥ 4`) ratio < 70%.
- Vocab-violation rate per `(industry_id, prompt_version)` — schema-drift indicator.

---

## 14. Stack

| Component | Choice | Rationale |
|---|---|---|
| Backend | FastAPI + SQLite (aiosqlite) | Zero infra, single file. Event log is fine in SQLite at solo scale. |
| ORM | SQLAlchemy 2.x async | Migrations + typed models. |
| Frontend | React 19 + Vite | Three-panel layout, no SSR. |
| LLM gateway | OpenRouter (OpenAI-compatible) | One key, 28+ models, automatic provider failover. |
| Tool calls | OpenAI function-call format | Supported across all major providers via OpenRouter. |
| Prompt cache | Anthropic `cache_control: ephemeral` | 5-min TTL, ≥1024-token block. |
| Embeddings | voyage-3-lite via OpenRouter | Cheap, 512-dim. |
| Vector search | Brute-force cosine in Python (MVP); `sqlite-vec` (Phase 2) | Player-scoped scans <300 rows. |
| Streaming | SSE | Simpler than WebSocket; one-way is enough. |
| Auth | None | localStorage `player_id`. |
| Compression | None at MVP; bear-1.1-compatible hook in Phase 2 | Pax Historia case study cites 66% reduction. |

---

## 15. File structure

```
pax-venture/
├── backend/
│   ├── app/
│   │   ├── main.py                       # FastAPI app, CORS, lifespan, error handlers, SSE middleware
│   │   ├── core/
│   │   │   ├── config.py                 # OPENROUTER_API_KEY, model defaults
│   │   │   ├── database.py               # async engine, init_db (creates tables, seeds industries+world_events)
│   │   │   ├── openrouter.py             # call_tool(), failover, cost calc
│   │   │   ├── tools.py                  # tool schemas (Section 6) as Python dicts
│   │   │   ├── cache.py                  # cache_control wrapping, hit-ratio tracking
│   │   │   ├── compression.py            # Phase 2 hook (no-op at MVP)
│   │   │   └── validators.py             # all Section 6.x post-call validators
│   │   ├── models/
│   │   │   ├── player.py
│   │   │   ├── event.py
│   │   │   ├── industry.py
│   │   │   ├── memory.py
│   │   │   ├── message.py
│   │   │   ├── decision.py
│   │   │   ├── thread.py
│   │   │   ├── flag.py
│   │   │   ├── relationship.py
│   │   │   ├── competitor.py
│   │   │   ├── world_event.py
│   │   │   ├── snapshot.py
│   │   │   ├── decision_embedding.py
│   │   │   └── llm_call.py
│   │   ├── services/
│   │   │   ├── game_engine.py            # start_month, submit_decision, end_month
│   │   │   ├── projection.py             # build state JSON, rebuild from events
│   │   │   ├── events.py                 # append_event, find_by_idem, replay
│   │   │   ├── memory.py                 # compact_memory orchestration
│   │   │   ├── embeddings.py             # embed, retrieve top-k
│   │   │   ├── competitors.py            # FSM transitions, end_month tick, seed
│   │   │   ├── world.py                  # world event scheduler, mechanical effect application
│   │   │   ├── autopsy.py                # end-of-game LLM call
│   │   │   └── cost.py                   # cap enforcement, projection
│   │   ├── prompts/
│   │   │   └── automotive.md             # system prompt template (rendered into industries row at init)
│   │   └── api/
│   │       ├── routes.py                 # 12 endpoints
│   │       └── sse.py                    # SSE helpers
│   ├── tests/
│   │   ├── test_money_flow.py            # A1 regression
│   │   ├── test_idempotency.py           # B8
│   │   ├── test_clamps.py                # numeric, vocab, length
│   │   ├── test_competitor_fsm.py        # transitions
│   │   ├── test_world_events.py          # mechanical effects
│   │   ├── test_memory_compaction.py     # rollover triggers
│   │   ├── test_projection.py            # event log → state correctness
│   │   └── test_balance_simulation.py    # bot plays 1000 games, expected win-rate band
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                       # 3-panel layout, model picker
│   │   ├── components/
│   │   │   ├── CashPanel.jsx
│   │   │   ├── Inbox.jsx
│   │   │   ├── ChatPanel.jsx             # SSE consumer
│   │   │   ├── Leaderboard.jsx
│   │   │   ├── ModelPicker.jsx
│   │   │   ├── CostBadge.jsx
│   │   │   ├── AutopsyCard.jsx
│   │   │   └── NewPlayerModal.jsx
│   │   ├── lib/sse.js
│   │   └── styles/global.css
│   └── package.json
└── docs/
    └── MVP_ENGINEERING.md
```

---

## 16. Implementation order

| Phase | What | Validation gate |
|---|---|---|
| **0** | DB schema, `industries` seed (automotive), event log + projection rebuild, `monthly_snapshots`, `llm_calls` skeleton | `test_projection.py` passes — events → state is deterministic |
| **1** | OpenRouter wrapper + tool-calling + prompt caching + 4 tool schemas; deterministic email-batch fallback; vocab validators | Manual: `/start-month` returns 3-5 schema-valid emails with cache hit ≥0 on first call, ≥1 on second within 5 min |
| **2** | `/decide` end-to-end with idempotency + clamps + memory `recent` + embedding retrieve+index | `test_idempotency.py`, `test_clamps.py` green; mid-game decision feels coherent |
| **3** | `/end-month` money flow (A1 regression test green), competitor FSM + reactive transitions, world events firing + mechanical effects, memory compaction | `test_money_flow.py` and `test_competitor_fsm.py` green; 24-month bot game produces sensible leaderboard movement |
| **4** | Frontend three-panel + SSE narrative streaming + model picker + cost badge | Does it feel like Football Manager? |
| **5** | Game-over autopsy + autopsy card UI + shareable result | Does the player say "one more game"? |
| **6** | Balance simulation in CI + cache-hit alerting + cost cap UI | Median game length M14–M22 across 1000 bot runs at default difficulty |

Phase 2 (post-MVP) candidates: compression hook, sqlite-vec migration, additional industries, save/load, multiplayer.

---

## 17. What we're NOT building (MVP)

Auth, multiplayer, WebSocket, charts, sound, save/load (event log makes this trivial later), mobile responsive, multiple industries (data layout supports it; only automotive content shipped), admin dashboard, rate limiting, content moderation pipeline (single-player local only), undo (event log makes this trivial later), bear-1.1 compression (hook in place, no-op at MVP).

---

## 18. Open questions (decide before coding Phase 0)

1. **Embedding provider**: Voyage via OpenRouter, OpenAI direct, or local (e.g. `bge-small`)? Voyage is recommended; falls back to OpenAI direct if OR coverage lapses.
2. **Prompt cache TTL**: Anthropic ephemeral (5 min) is the safe default. If we observe <70% hit ratio, evaluate the 1-hour extended TTL (10× write cost, ~12× read window).
3. **Per-game cost cap default**: $0 (off), $1, or $5? Recommendation: off in dev, $5 default for shipped MVP.
4. **`seed` source**: per-decision random `int64`, or derived `hash((player_id, month, seq))`? The latter is replayable; the former matches OpenRouter quirks better. Recommendation: derived, with override.
5. **Autopsy timing**: only on elimination, or also on player-requested "retire" at any month? MVP: elimination only; retire is a one-line addition later.
