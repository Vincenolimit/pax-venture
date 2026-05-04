# Pax Venture — Implementation Plan

**Source of truth**: `docs/MVP_ENGINEERING.md` (RFC v2). This plan is the executable read of that RFC: every task here cites the section it implements. If this plan and the RFC disagree, the RFC wins — fix the plan.

**Current state**: clean slate (post `c347266 chore: remove all scaffolded code`). Only `docs/`, `README.md`, `.gitignore`, `.git`, `.claude` exist.

**Definition of MVP done**: a solo player can create a game, live through 24 months of automotive CEO chat, see emails / cash / leaderboard, get eliminated when cash<0, and receive an LLM-generated autopsy card. Per-game cost ≤ $2 on the balanced tier.

---

## Phase −1 — Decide open questions (RFC §18)

Block Phase 0 on these. Each is a one-line decision recorded back into `MVP_ENGINEERING.md` §18.

| # | Question | Recommendation | Owner action |
|---|---|---|---|
| 1 | Embedding provider | `voyage-3-lite` via OpenRouter; fallback OpenAI `text-embedding-3-small` direct | Confirm OR coverage of voyage; record | GO FOR OPENROUTER
| 2 | Prompt cache TTL | Anthropic ephemeral 5-min by default; revisit if hit ratio < 70% mid-game | Set in code as constant `CACHE_TTL = "ephemeral"` | OK 5MIN
| 3 | Per-game cost cap default | `null` (off) in dev, `5.00` in shipped MVP build | Read from `PAX_COST_CAP_USD` env var; default null | 
| 4 | `seed` source | Derived `hash((player_id, month, seq))` — replayable. Override accepted in test fixtures only | Implement in `core/seed.py` |

Also lock `PROMPT_VERSION = 1`, `SCHEMA_VERSION = 1`. Bump rules: any change to `industries.system_prompt_template` → `prompt_version++`. Any change to a tool schema or DDL → `schema_version++`. Both are stamped on every event (RFC §3.3).

---

## Phase 0 — Foundations (RFC §3, §4, §15)

**Goal**: schema + projection. No LLM, no HTTP yet. Pure data correctness.

### 0.1 Project scaffolding

Create directory tree exactly as RFC §15. Empty `__init__.py` everywhere. Files to create (all empty stubs unless noted):

```
backend/
  app/
    main.py                    # FastAPI() instance only at this phase
    core/{config,database,seed,validators,cache,compression,openrouter,tools}.py
    models/{player,event,industry,memory,message,decision,thread,flag,
            relationship,competitor,world_event,snapshot,
            decision_embedding,llm_call}.py
    services/{game_engine,projection,events,memory,embeddings,
              competitors,world,autopsy,cost}.py
    prompts/automotive.md      # paste system prompt from RFC §7
    api/{routes,sse}.py
  tests/                       # files listed in §0.6
  requirements.txt             # see §0.2
frontend/                      # leave empty until Phase 4
```

### 0.2 Dependencies (`backend/requirements.txt`)

```
fastapi>=0.115
uvicorn[standard]>=0.32
sqlalchemy[asyncio]>=2.0
aiosqlite>=0.20
pydantic>=2.9
httpx>=0.27           # OpenRouter client
sse-starlette>=2.1
numpy>=2.1            # cosine over float32 blobs
pytest>=8
pytest-asyncio>=0.24
pytest-httpx>=0.32    # mock OpenRouter
```

### 0.3 SQLAlchemy models

One model per RFC §3.x table. **Constraints to encode at the ORM level**, not just at DDL:

- `players.model_tier` Enum `('cheap','balanced','premium')` (§3.2).
- `events.source` Enum `('player','llm','kernel','world','competitor')` (§3.3).
- `events` unique partial index on `(player_id, idempotency_key)` where `idempotency_key IS NOT NULL` (§3.3) — declare via `Index(..., sqlite_where=...)`.
- `competitors.posture` Enum (§3.11).
- `monthly_snapshots` composite PK `(player_id, month)` (§3.4).
- `flags` PK `(player_id, flag_name)` (§3.9).
- `relationships` PK `(player_id, key)` (§3.10).
- `threads.status` Enum `('active','resolved','abandoned')` (§3.8).
- `decisions.importance` `CHECK BETWEEN 0 AND 1` (§3.6).
- `decision_embeddings.vector` as `LargeBinary` (float32 LE blob, RFC §3.7).
- `world_events.severity` Enum `('minor','major','crisis')` (§3.12).

`leaderboard` is a `VIEW` (RFC §3.13), not a model. Expressed as raw SQL in `core/database.py:init_db`.

### 0.4 `init_db` (`core/database.py`)

1. Create all tables.
2. Create the `leaderboard` VIEW exactly as RFC §3.13.
3. Insert one `industries` row from `industries_automotive_seed.json` (the JSON in RFC §3.1, "Automotive seed"). System prompt template is loaded from `app/prompts/automotive.md`.
4. Insert all 8 rows of the automotive world-event calendar from RFC §10.
5. Idempotent: re-running on an existing DB is a no-op (skip seeds if rows exist; matched by primary key).

### 0.5 Projection layer (`services/projection.py`, `services/events.py`)

This is the load-bearing piece of Phase 0. Get this wrong and every later phase is wrong.

- `events.append_event(player_id, kind, source, payload, *, month, idempotency_key=None, parent_event_id=None, prompt_version, schema_version, model=None, seed=None)` — append-only writer. Computes `seq_in_month = max(seq_in_month) + 1` for the player+month under a SQLite `BEGIN IMMEDIATE` transaction.
- `events.find_by_idem(player_id, key) -> Event | None` — used for idempotency replay (RFC §11 mutating endpoints).
- `projection.build_state(player_id) -> dict` — produces the exact JSON in RFC §4 (Layer 1). All numeric columns on `players` are read here, **never** computed by the LLM. Derived fields (RFC §4):
  - `burn_rate = employees * payroll_per_employee + base_overhead`
  - `cash_runway` bucketed by ratio (`r ≥ 4 / 2 / 1 / <1`)
  - `revenue_trend`: compare `players.revenue` to `mean(monthly_snapshots.revenue, last 3)`. ±10% threshold; if <3 snapshots exist → `"stable"`.
  - `competitor_briefs`: top-3 by `market_share` from `competitors WHERE player_id=?`. `revenue_band`: `<1M = low`, `1M..3M = mid`, `>3M = high`. `headline` is kernel-generated per template (e.g. `"{name} {posture_verb} this quarter"`).
  - `active_world_events`: `world_events WHERE industry_id=? AND fire_at_month <= current_month < fire_at_month + duration_months`.
- `projection.rebuild_player_columns(player_id)` — replays `events` in `(month, seq_in_month)` order to recompute `players.{cash, revenue, market_share, employees}`. The **only** legitimate writer of those columns (RFC §3, §1 pillar 3).

### 0.6 Tests for Phase 0

- `tests/test_projection.py`
  - Append a hand-built sequence of events; assert projection rebuilt columns match expected.
  - Replay determinism: run rebuild twice, assert identical output.
  - `cash_runway` bucket boundaries: assert each of `comfortable/healthy/tight/critical` triggers at the correct ratio.
  - `revenue_trend` returns `"stable"` when fewer than 3 snapshots.
- `tests/test_idempotency.py` (skeleton — fully exercised in Phase 2)
  - `append_event` with the same `(player_id, idempotency_key)` twice raises an integrity error from the partial-unique index.

**Phase 0 gate**: `pytest tests/test_projection.py` green. `python -c "from app.core.database import init_db; init_db()"` produces a DB with exactly 1 `industries` row, 8 `world_events` rows, and the `leaderboard` view present.

---

## Phase 1 — LLM gateway (RFC §6, §7, §8, §13)

**Goal**: `/start-month` end-to-end with cached prompt and tool-calling. No game loop yet — just generate emails for an existing player + month.

### 1.1 OpenRouter client (`core/openrouter.py`)

```python
async def call_tool(
    call_type: str,            # "generate_inbox_emails" | "resolve_decision" | ...
    model: str,                # resolved OR id, e.g. "anthropic/claude-haiku-4-5"
    messages: list[dict],      # [{"role":"system","content":[...]}, {"role":"user","content":[...]}]
    tool: dict,                # the JSON schema from §6.x
    *,
    cache_control_on_system: bool,
    seed: int,
    stream: bool = False,
) -> ToolCallResult: ...
```

Returns `ToolCallResult(args: dict, in_tokens, out_tokens, cached_tokens, cost_usd, latency_ms, model, raw)`.

Behavior:
- POSTs to `https://openrouter.ai/api/v1/chat/completions` with `tools=[tool]`, `tool_choice={"type":"function","function":{"name":<tool name>}}` (RFC §6 forced tool).
- When `cache_control_on_system=True`, attaches `cache_control: {"type":"ephemeral"}` to the **last block** of the system message. The system content must be supplied as a list-of-blocks, not a string, so caching is per-block (Anthropic requirement).
- Cost calc: `cost_usd = price[model].in * (in_tokens - cached_tokens) / 1e6 + price[model].in_cached * cached_tokens / 1e6 + price[model].out * out_tokens / 1e6`. Prices kept in `core/config.py:MODEL_PRICES` keyed by OR id; one row per model used.
- Failover (RFC §8.4): on 5xx/429 → 1 retry → fall to industry's `recommended_models.cheap` for the same `call_type` → 502 if still failing.
- Every successful or failed call writes a row to `llm_calls` (RFC §3.14).

### 1.2 Tool schemas (`core/tools.py`)

Paste verbatim from RFC §6.1–§6.4. Four module-level dicts: `INBOX_TOOL`, `RESOLVE_TOOL`, `COMPACT_TOOL`, `AUTOPSY_TOOL`. Static — no runtime construction.

### 1.3 Prompt assembly (`core/cache.py`)

- `build_cached_system_block(industry, memory) -> list[block]` — renders RFC §7 template substituting `{{industry_name}}`, `{{sender_vocab}}`, ..., `{{active_world_events_block}}`, `{{origin_story}}`, `{{period_summary}}`. Returns `[{"type":"text","text":..., "cache_control":{"type":"ephemeral"}}]`.
  - `{{active_world_events_block}}` is the rendered list (event_id + severity + narrative_seed) for the current month, computed from `world_events` table — note this means the cached block changes when the active world events set changes, which is fine: cache key is the rendered content.
- `build_dynamic_block(state, recent, threads, retrieved_decisions, current_emails, instruction) -> str` — exact shape from RFC §8.2. Single text block, NOT cached.

### 1.4 Validators (`core/validators.py`)

One callable per RFC §6.x post-call rule. Each takes `(industry, args) -> (cleaned_args, warnings: list[str])`. Warnings are persisted in `llm_calls.error` as JSON when non-empty.

For `generate_inbox_emails` (RFC §6.1):
- Reject email if `sender ∉ industry.sender_vocab` or `category ∉ industry.category_vocab`.
- Truncate `subject`/`body` to schema `maxLength` if oversize (defensive — JSON Schema enforcement is also on).
- Verify ≥1 email's `references` matches an active thread label, set flag, or active world event id; if not, **drop & retry once**; if retry also fails, emit deterministic fallback batch (RFC §12: "Email batch fails generation rules after retry").
- Month-1 first email: must have `sender="Board"` and `category="board"`. If absent, prepend a deterministic "Welcome from the Board" email (RFC §6.1).

For `resolve_decision` (RFC §6.2):
- Clamp 4 numeric fields to industry ranges; record `clamped_pct` per field.
- Drop `flag_updates` keys not in `industry.flag_vocabulary`; log `WARN flag_vocab_violation`.
- Drop `relationship_updates` keys/values not in vocab.
- Match `closed_threads` against active threads case-insensitively; drop unmatched.
- Truncate `narrative` and `new_threads.label` to `maxLength`.
- If `cash_impact` clamped by ≥50%, append " (Note: scope reduced)" to `narrative` (RFC §6.2 last bullet).

For `compact_memory` (RFC §6.3):
- If `period_summary` not due for rewrite (per RFC §5.2 rules), discard returned value, keep prior.
- Same for `origin_story`.

### 1.5 Wiring `/start-month` (RFC §11.5)

`api/routes.py` exposes `POST /api/v1/players/{id}/start-month` returning `text/event-stream`. Stub for now: always month 0→1 transition; full preconditions added in Phase 2. Pipeline:

1. Idempotency check (`events.find_by_idem`).
2. Load player + memory + projection (Phase 0 code).
3. Apply pending world events for `current_month + 1` (delegate to Phase 3 `services/world.py`; for Phase 1 ship a stub that loads but doesn't apply).
4. `cache.build_cached_system_block(...)` + `cache.build_dynamic_block(...)`.
5. `openrouter.call_tool("generate_inbox_emails", ..., cache_control_on_system=True, stream=True)`.
6. Validate; persist messages; emit SSE `email` per message; emit `done`.
7. Append `EMAILS_GENERATED` and `MONTH_STARTED` events.

### 1.6 Tests for Phase 1

- `tests/test_tool_schemas.py` — feed a synthetic minimal valid args dict through each schema with `jsonschema`; assert no error.
- `tests/test_validators.py` — table-driven cases per validator (vocab violations, clamps, length, month-1 board injection).
- Manual gate (RFC §16 phase 1): `curl /start-month` returns 3–5 valid emails. Second call within 5 min shows `cached_tokens > 0` in `llm_calls` row.

**Phase 1 gate**: schema-valid emails returned. Cache hit ratio > 0 on second call within TTL.

---

## Phase 2 — Decisions and memory recent (RFC §6.2, §5, §11.6)

**Goal**: full `/decide` SSE pipeline with idempotency, clamps, embeddings retrieval, and `recent` memory updates. End-of-month and competitors still stubbed.

### 2.1 `POST /players` (RFC §11.1)

Implement before `/decide` (we need a real player). Side effects (RFC §11.1):
- Insert `players` row from `industries.starting_state_json`.
- Seed 4 `competitors` rows from RFC §3.11 templates (id `p<player>:<template>`).
- Insert empty `memories` row.
- Append `MONTH_STARTED` event for month 0 metadata only — no emails generated; `/start-month` is what triggers emails.
- Idempotent on `Idempotency-Key` (RFC §1 pillar 7).

### 2.2 `services/embeddings.py`

- `embed(text) -> bytes` — one OR call to `voyage-3-lite`, returns 512×float32 LE blob.
- `retrieve(player_id, query_text, k=3, min_importance=0.4) -> list[Decision]` — brute-force cosine over `decision_embeddings JOIN decisions WHERE player_id=? AND importance>=?`. Returns top-k with similarity scores. Empty list if <3 candidate rows.
- Uses `numpy.frombuffer(blob, dtype="<f4")` for vector reads.

### 2.3 `POST /players/{id}/decide` (RFC §11.6)

Pipeline matches RFC §2 SCENE-DECISION:

1. Preconditions:
   - Player exists + not game over (else 404 / 409).
   - Month is started (i.e. there exists `MONTH_STARTED` for `current_month + 1` with no `MONTH_ENDED`). 409 otherwise.
   - Decision count this month < 10 (count `DECISION_RESOLVED` events). 409 otherwise.
   - `cost_spent_usd + estimated_cost ≤ cost_cap_usd` if cap set; 402 otherwise.
2. Idempotency check: replay returns the prior `result` SSE event with no LLM call (RFC §11.6 last paragraph).
3. Embed `decision_text`, retrieve top-3 past similar decisions.
4. Build cached system + dynamic block (now includes `THIS MONTH'S INBOX`, `RETRIEVED PAST DECISIONS`, the decision text instruction).
5. Stream `resolve_decision` from Sonnet (balanced default, overridable per-call via `?model=` allowlist).
6. As partial tool-call args arrive, emit `narrative.chunk` SSE events (chunk on whole-token boundaries from the streamed tool-call args delta).
7. On stream end: validators (clamps, vocab, etc.); persist `decisions`, `decision_embeddings`, update `flags` / `relationships` / `threads` per validated args; append `DECISION_PROPOSED`, `DECISION_RESOLVED` events; rebuild player projection columns.
8. Trigger competitor FSM checks (Phase 3 — stub for Phase 2).
9. Emit final `result` SSE with `updated_state` (rebuilt projection).

### 2.4 Tests for Phase 2

- `tests/test_idempotency.py` (full): post `/decide` twice with same key → second call writes 0 new `llm_calls` rows; response identical.
- `tests/test_clamps.py`:
  - Fake LLM returning `cash_impact = -10_000_000` → persisted as `-5_000_000` (auto clamp); narrative gets " (Note: scope reduced)" appended.
  - Unknown flag in `flag_updates` → dropped; warning row in `llm_calls.error`.
  - Unknown relationship key/value → dropped.
- `tests/test_embedding_retrieval.py`: insert N synthetic decisions w/ known vectors; assert top-3 cosine returns expected ids.

**Phase 2 gate**: `pytest tests/test_idempotency.py tests/test_clamps.py` green. Manual: a single decision in month 1 returns coherent narrative referencing inbox emails.

---

## Phase 3 — End-of-month, competitors, world events (RFC §9, §11.7)

**Goal**: full month loop. The A1 fix lands here.

### 3.1 `services/competitors.py`

- `apply_posture_transitions(comp, player, month) -> bool` — implements every row of RFC §9.6 table. Each transition is data: a list of triggers in `core/config.py:POSTURE_RULES`. Reactions emit `COMPETITOR_REACTED` events.
- `end_month_competitor_tick(comp, player, month, rng)` — verbatim implementation from RFC §9.5.
- `seeded_rng(player, comp) -> random.Random` — `Random(hash((player.id, comp.id, player.current_month)))`. Note: `player.current_month` here is the **just-ended** month for reproducibility.

### 3.2 `services/world.py`

- `pending_for_month(industry_id, month) -> list[WorldEvent]` — those whose `fire_at_month == month` (newly firing).
- `active_for_month(industry_id, month) -> list[WorldEvent]` — `fire_at_month <= month < fire_at_month + duration_months` (already used by projection in Phase 0).
- `apply_mechanical_effects(player, month, world_events)` — implements RFC §9.4 application order:
  1. `requires_flag` check; if missing apply `if_missing_flag_penalty`.
  2. Global effects on player (`revenue_multiplier`, `cash_delta_per_month`, `market_share_drift`).
  3. Competitor effects (`all` first, then `by_template`).
  4. Each effect appends a `WORLD_EVENT_FIRED` event with affected entity in payload.

### 3.3 `services/memory.py` (compaction)

- `compact_memory(player)` — implements RFC §5.2:
  1. Always rebuild `recent` from current month's decisions: top-1 by importance (or "Quiet month").
  2. If `recent` would exceed 3 lines, oldest line absorbs into `period_summary`.
  3. If `period_summary` covers >20 months, oldest 5 absorb into `origin_story`.
  4. Single Haiku tool call with prior `recent / period_summary / origin_story` + this month's top-3 decisions + flag/relationship deltas.
  5. Validator (RFC §6.3 wrapper) discards LLM-returned `period_summary` / `origin_story` if not due for rewrite per the rule above.
  6. Append `MEMORY_COMPACTED`.

### 3.4 `POST /players/{id}/end-month` (RFC §9.7, §11.7)

Implements the end-of-month flow exactly as RFC §9.7 pseudocode. Order matters:

1. Idempotency replay check.
2. Conflict checks (`game_over`, `month_is_active`).
3. `apply_world_events(p, p.current_month)` (active set this month).
4. **A1 fix** (RFC §9.2):
   ```
   payroll = employees * payroll_per_employee
   overhead = base_overhead
   burn = payroll + overhead
   cash += revenue - burn
   ```
   Append `FINANCES_APPLIED` with `{burn, revenue}` payload.
5. For each competitor: `end_month_competitor_tick`; append `COMPETITOR_TICK`.
6. `compact_memory(p)` → `MEMORY_COMPACTED`.
7. `take_snapshot(p)` → write `monthly_snapshots` row (RFC §3.4) with computed `leaderboard_rank` from the `leaderboard` view.
8. `p.current_month += 1` (RFC change A6 — only here).
9. Elimination: if `cash < 0`, set `game_over=True, eliminated_at=current_month`, append `ELIMINATED`, run `autopsy_summary` (Phase 5; Phase 3 stubs out the autopsy with `null`).
10. Append `MONTH_ENDED` with idempotency key.
11. Return RFC §11.7 response shape.

### 3.5 Tests for Phase 3

- `tests/test_money_flow.py` (the **A1 regression**): bot decisions drive a player to month 4 with positive revenue; assert cash trajectory matches manual hand-calculation. This is non-negotiable; if this fails, the MVP is broken.
- `tests/test_competitor_fsm.py`: trigger each row of RFC §9.6 table; assert posture + duration + `COMPETITOR_REACTED` event emitted.
- `tests/test_world_events.py`:
  - chip_shortage_2026 fires at M3, expires at M5; player revenue × 0.88 over those months.
  - eu_emissions_2026: missing `ev_platform_launched` flag → cash penalty applied; with flag → no penalty.
- `tests/test_memory_compaction.py`:
  - Month 4 transition: line moves from `recent` to `period_summary`.
  - At month 25: oldest 5 months in `period_summary` move to `origin_story`.
  - Haiku-returned fields not due for rewrite are discarded.

**Phase 3 gate**: all three tests green. A scripted 24-month bot game produces `monthly_snapshots` with sensible leaderboard movement (manual eyeball — captured in §6.6 below as automated check).

---

## Phase 4 — Frontend (RFC §1 vision, §15 frontend tree)

**Goal**: the three-panel CEO interface. Football-Manager-feel: dense, professional, no game-y chrome.

### 4.1 Dependencies

```
react@19, react-dom@19, vite@5, @microsoft/fetch-event-source (SSE POST client)
```

`@microsoft/fetch-event-source` because native `EventSource` does not support `POST` + custom headers (we need `Idempotency-Key`).

### 4.2 Components (RFC §15)

- `App.jsx` — three-panel CSS grid (left: cash + leaderboard, center: chat + inbox, right: model picker + cost badge). `localStorage.player_id` bootstraps the session (RFC §14: "Auth: None"). If absent, show `NewPlayerModal`.
- `CashPanel.jsx` — current cash, burn rate, `cash_runway` bucket, current month. Color-codes runway critical/tight/healthy/comfortable.
- `Inbox.jsx` — list of this-month emails. Click → marks `is_read`. `requires_action` flagged visually.
- `ChatPanel.jsx` — the only player input. Submits to `/decide` via SSE (POST + `fetch-event-source`). Renders `narrative.chunk` events token-by-token; on `result` event, shows the impact line (`-$480K cash, +$120K rev/mo, +2 employees`) and refreshes state.
- `Leaderboard.jsx` — `GET /leaderboard`. Player highlighted.
- `ModelPicker.jsx` — `cheap | balanced | premium`. Updates `players.model_tier` via `PATCH /players/{id}` (add this minor endpoint in Phase 4 — not in original §11 but small).
- `CostBadge.jsx` — shows `cost_spent_usd / cost_cap_usd`. Pulls from `GET /players/{id}/cost`.
- `AutopsyCard.jsx` — rendered when `game_over=true`. (Phase 5 fully wires it.)
- `NewPlayerModal.jsx` — collects name, company, style, risk tolerance, model tier. POSTs `/players`.
- `lib/sse.js` — thin wrapper around `fetchEventSource` returning an async iterator of `{event, data}`.

### 4.3 Buttons

Per RFC core loop §2: "Chat is the only input. No buttons except Start Month, End Month, Model Picker." Frontend enforces this rigidly. **No** retry button, **no** undo, **no** save. The chat box is the only mutating UI besides those three.

### 4.4 Phase 4 gate

Manual: a real human plays month 1 → month 3, makes ≥3 decisions per month, sees streaming narrative, sees competitor brief change, sees cash decline through burn. The vibe check is the gate: does it feel like Football Manager? If yes → ship; if no → iterate visual density before Phase 5.

---

## Phase 5 — Autopsy (RFC §6.4, §11.7)

**Goal**: the player says "one more game" after losing.

### 5.1 `services/autopsy.py`

- `generate_autopsy(player) -> dict` — single Sonnet tool call with `autopsy_summary` schema (RFC §6.4). Inputs: full `monthly_snapshots`, top-10 `decisions` by `importance`, final state. Persisted as the payload of `AUTOPSY_GENERATED` event.
- Triggered in two places:
  - `end_month` when `cash < 0` (RFC §9.7 step 9.1).
  - `GET /players/{id}/autopsy` after M24 — voluntary "see the recap" path even if not eliminated (small new endpoint; spec follows §6.4 schema).

### 5.2 `AutopsyCard.jsx`

Renders:
- Headline as marquee.
- `arc_summary` paragraph.
- `pivotal_decisions` rows: month, one-liner, color-coded verdict pill (`brilliant | sound | risky | fatal`).
- `cause_of_death` block.
- `board_quote` blockquote.
- "Share" → copies a public URL `/autopsy/<player_id>` (read-only view; trivially served because the autopsy event payload is self-contained).
- "Play again" → resets `localStorage.player_id` and re-shows `NewPlayerModal`.

### 5.3 Phase 5 gate

A real loss in <30 minutes of play produces an autopsy that names a real-feeling pivotal decision. If the autopsy reads generic ("you struggled with cash flow"), tune the system prompt context (top-10 decisions input) before shipping.

---

## Phase 6 — Telemetry, balance, cost cap (RFC §13, §16)

### 6.1 Cache hit alerting

- `core/cache.py` records `cached_tokens / in_tokens` per call into `llm_calls.cache_hit_ratio`.
- A scheduled task (or `GET /admin/health` for MVP) computes mean ratio for `current_month >= 4` calls in the last hour. If < 0.70 → log WARN. Surface in dev console.

### 6.2 Cost cap UI

- `GET /players/{id}/cost` already exists (§11.11). `CostBadge.jsx` shows percentage of cap. At 90% → yellow; at 100% → red and inputs disabled with copy "Game cost cap reached. Raise it in settings to continue."
- `PATCH /players/{id} {cost_cap_usd: ...}` to raise the cap mid-game.

### 6.3 Balance simulation in CI

- `tests/test_balance_simulation.py` — runs N=50 (CI) / N=1000 (nightly) bot games end-to-end. The bot is a small heuristic: each month, pick the highest-`requires_action` email, send a one-line decision keyed off its category. Assert:
  - Median game length ∈ [M14, M22] (RFC §16 phase 6 acceptance band).
  - At least 1 in 4 games reaches M24 alive.
  - Per-game median cost ≤ $2.50 on balanced.
- Bot uses a fake OpenRouter (recorded fixtures). The point isn't to validate the LLM — it's to validate that the **kernel** produces a sensible difficulty curve given representative LLM outputs.

### 6.4 Vocab-violation rate

- A SQL view `vocab_violation_rate` over `llm_calls.error` JSON. Surface as a dashboard line. If a single industry+prompt_version exceeds 5% violation rate, that's a schema-drift signal — bump `prompt_version` and tighten the prompt.

### 6.5 Phase 6 gate

`pytest tests/test_balance_simulation.py` green at N=50 in CI. Cost-cap UI exercised manually. Cache hit alert wired to console (Slack/email out of scope for MVP).

---

## Cross-cutting work (touches every phase)

These are not phases; they're disciplines.

| Discipline | Where it lives | Why |
|---|---|---|
| **Versioning** | Every event stamped with `(prompt_version, schema_version, model, seed)` | RFC §1 pillar 8, §3.3. Required for replay, A/B compare, balance sim reproducibility. |
| **Validation at the edge** | `core/validators.py` only | RFC §1 pillar 14. Never enforce vocab/length via prompt prose. |
| **Idempotency-first APIs** | Every mutating endpoint takes `Idempotency-Key`, every event stores it, every endpoint replays from event log on key match | RFC §1 pillar 7, §11. |
| **Closed vocabularies** | `industries` table is the single registry; validators enforce; tool schemas reference but don't duplicate | RFC §1 pillar 6, §1 pillar 10. |
| **No industry constants in code** | All thresholds, clamps, vocabs come from `industries` row | RFC §1 pillar 6. Only structural code is industry-agnostic. |
| **Event log is authoritative** | Numeric columns on `players` are projections; rebuild always works | RFC §1 pillar 3. |
| **Cost as first-class metric** | Every LLM call → `llm_calls`; players see `cost_spent_usd` in the UI | RFC §1 pillar 13, §13. |

---

## What we are explicitly NOT building (RFC §17)

Auth · multiplayer · WebSocket · charts · sound · save/load (event log makes it trivial later) · mobile responsive · multiple industries (data layout supports; only automotive content) · admin dashboard · rate limiting · content moderation · undo · bear-1.1 compression (hook in place, no-op).

Defer Phase-2 candidates from RFC §16: compression hook, sqlite-vec migration, additional industries, save/load, multiplayer.

---

## Sequencing summary

```
Phase −1 (decisions)   ──>  Phase 0 (schema + projection)
                              │
                              ├──>  Phase 1 (LLM gateway + /start-month)
                              │       │
                              │       └──>  Phase 2 (/decide + embeddings + recent memory)
                              │              │
                              │              └──>  Phase 3 (/end-month + competitors + world + compaction)
                              │                     │
                              └─────────────────────└──>  Phase 4 (frontend) ──>  Phase 5 (autopsy) ──>  Phase 6 (telemetry/balance)
```

Phases 0–3 are the engine. Phase 4 is the face. Phase 5 is the hook. Phase 6 is the safety net.


